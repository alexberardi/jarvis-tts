"""Kokoro TTS provider.

Wraps the Kokoro KPipeline streaming API. Voice weights are downloaded
to HF_HOME on first use, not baked into the image — set the env var (or
a Docker volume mount) so weights persist across container restarts.

Audio comes out of the pipeline as float32 samples at 24 kHz; we convert
to 16-bit signed PCM to match Piper's output format so downstream players
can be format-agnostic between providers.
"""

import logging
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


def _lang_code_for_voice(voice: str) -> str:
    """Infer Kokoro language code from voice prefix.

    Kokoro voice IDs encode language+gender: `bm_george` = British Male.
    The pipeline needs a lang_code ('a' American, 'b' British, 'j' Japanese, …)
    so we derive it from the first character of the voice ID.
    """
    if not voice:
        return "a"
    return voice[0].lower()


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
        self._device = device
        self._gain = float(gain)
        lang_code = _lang_code_for_voice(voice)
        logger.info(
            f"Loading Kokoro pipeline (lang_code='{lang_code}', voice='{voice}', "
            f"speed={speed}, device='{device}', gain={gain})"
        )
        # device='cpu' is KPipeline's default; pass through unconditionally
        # so future values ('cuda', 'mps') work without branching here.
        self._pipeline = KPipeline(lang_code=lang_code, device=device)

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
            generator = self._pipeline(text, voice=self._voice, speed=self._speed)
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
