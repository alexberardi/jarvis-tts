"""Kokoro TTS provider.

Wraps the Kokoro KPipeline streaming API. Voice weights are downloaded
to HF_HOME on first use, not baked into the image — set the env var (or
a Docker volume mount) so weights persist across container restarts.

Audio comes out of the pipeline as float32 samples at 24 kHz; we convert
to 16-bit signed PCM to match Piper's output format so downstream players
can be format-agnostic between providers.
"""

import logging
import threading
import time
from typing import Generator

import numpy as np
from kokoro import KPipeline

from app.providers.base import AudioChunk, AudioFormat, TTSProvider

logger = logging.getLogger(__name__)

_KOKORO_SAMPLE_RATE = 24000
_AUDIO_FORMAT = AudioFormat(
    sample_rate=_KOKORO_SAMPLE_RATE,
    sample_width=2,
    channels=1,
)

# Split synthesis on sentence boundaries so audio streams sentence-by-sentence.
# KPipeline's default split_pattern (\n+) never fires on LLM voice responses
# (single paragraph, no newlines), so the whole reply synthesized as ONE chunk
# and time-to-first-audio grew linearly with length (prod: 362 chars = 4.25s
# of silence on cpu). The lookbehind keeps the punctuation with its sentence.
# Mid-sentence abbreviations ("Dr. Smith") split early — a minor prosody
# hiccup, worth it for constant first-audio latency.
_SENTENCE_SPLIT_PATTERN = r"(?<=[.!?…])\s+"


def _lang_code_for_voice(voice: str) -> str:
    """Infer Kokoro language code from voice prefix.

    Kokoro voice IDs encode language+gender: `bm_george` = British Male.
    The pipeline needs a lang_code ('a' American, 'b' British, 'j' Japanese, …)
    so we derive it from the first character of the voice ID.
    """
    if not voice:
        return "a"
    return voice[0].lower()


def _resolve_device(requested: str) -> str:
    """Degrade an unavailable device to cpu instead of failing the build.

    A bad device (e.g. `tts.kokoro_device=cuda` in a container with no GPU
    passthrough) would otherwise raise inside KPipeline *after* the model
    weights load — and the provider manager retries a failed build on every
    request, so each synth pays the full weight-load just to fail again.
    Kokoro on cpu is fast (~0.5s/synth); a working cpu provider beats a
    perpetually-failing cuda one.
    """
    if requested == "cpu":
        return "cpu"
    try:
        import torch
    except ImportError:
        logger.warning(
            "Kokoro device '%s' requested but torch is not importable — using cpu",
            requested,
        )
        return "cpu"
    if requested.startswith("cuda") and not torch.cuda.is_available():
        logger.warning(
            "Kokoro device '%s' requested but no CUDA device is available "
            "(no GPU passthrough or cpu-only torch) — using cpu", requested,
        )
        return "cpu"
    if requested.startswith("mps") and not torch.backends.mps.is_available():
        logger.warning(
            "Kokoro device '%s' requested but MPS is not available — using cpu",
            requested,
        )
        return "cpu"
    return requested


def _float_to_int16_bytes(samples: np.ndarray, gain: float = 1.0) -> bytes:
    """Convert float32 samples in [-1, 1] to little-endian 16-bit PCM bytes.

    Optional `gain` multiplies samples before clipping. Used to compensate for
    Kokoro's quiet output (~0.3-0.5 peak vs Piper's ~0.7-0.9). Clipping keeps
    over-range samples bounded — slight saturation is preferable to inaudible
    speech.
    """
    boosted = samples * gain if gain != 1.0 else samples
    clipped = np.clip(boosted, -1.0, 1.0)
    ints = (clipped * 32767.0).astype(np.int16)
    return ints.tobytes()


class KokoroTTSProvider(TTSProvider):

    def __init__(self, voice: str = "bm_george", speed: float = 1.0, device: str = "cpu", gain: float = 1.0):
        self._voice = voice
        self._speed = float(speed)
        self._device = _resolve_device(device)
        self._gain = float(gain)
        lang_code = _lang_code_for_voice(voice)
        logger.info(
            f"Loading Kokoro pipeline (lang_code='{lang_code}', voice='{voice}', "
            f"speed={speed}, device='{self._device}', gain={gain})"
        )
        self._pipeline = KPipeline(lang_code=lang_code, device=self._device)

        # Pre-warm on a background thread so /health responds immediately.
        # First inference on MPS pays an 8-9s graph-compile penalty (much
        # smaller on CPU/CUDA, but still non-trivial), and the first
        # user-perceived synth after a restart would otherwise be brutal.
        # Throwaway phrase; output is dropped.
        threading.Thread(
            target=self._warmup, name="kokoro-warmup", daemon=True
        ).start()

    def _warmup(self) -> None:
        t0 = time.monotonic()
        try:
            for _g, _p, _a in self._pipeline("warm", voice=self._voice, speed=self._speed):
                # Drain at least one chunk to ensure inference + graph compile
                # actually happen. KPipeline is lazy — iterating triggers work.
                break
        except Exception as e:
            logger.warning("Kokoro warmup failed (will pay cold cost on first real synth): %s", e)
            return
        logger.info(
            "Kokoro warm: device=%s elapsed=%.2fs (subsequent synths will be fast)",
            self._device, time.monotonic() - t0,
        )

    @property
    def name(self) -> str:
        return "kokoro"

    def get_audio_format(self) -> AudioFormat:
        return _AUDIO_FORMAT

    def synthesize(self, text: str) -> Generator[AudioChunk, None, None]:
        # Profile the pipeline so we can see where time is spent. Time to
        # first chunk covers phoneme prep + first inference pass — if that's
        # the bulk of the total, inference (GPU-addressable) is the bottleneck.
        # Large first-chunk / short total-minus-first suggests the prep is slow.
        t0 = time.monotonic()
        first_chunk_at: float | None = None
        chunk_count: int = 0
        try:
            generator = self._pipeline(
                text,
                voice=self._voice,
                speed=self._speed,
                split_pattern=_SENTENCE_SPLIT_PATTERN,
            )
            for _graphemes, _phonemes, audio in generator:
                if audio is None:
                    continue
                if first_chunk_at is None:
                    first_chunk_at = time.monotonic() - t0
                samples = audio.detach().cpu().numpy() if hasattr(audio, "detach") else np.asarray(audio)
                pcm_bytes = _float_to_int16_bytes(samples, gain=self._gain)
                if not pcm_bytes:
                    continue
                chunk_count += 1
                yield AudioChunk(audio_bytes=pcm_bytes, format=_AUDIO_FORMAT)
        finally:
            total = time.monotonic() - t0
            logger.info(
                "Kokoro synthesize done: chars=%d chunks=%d first_chunk=%.2fs total=%.2fs device=%s",
                len(text), chunk_count,
                first_chunk_at if first_chunk_at is not None else -1.0,
                total, self._device,
            )
