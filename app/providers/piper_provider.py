"""Piper TTS provider.

Wraps piper-tts (ONNX runtime) in the TTSProvider interface. The voice
ONNX + config pair is baked into the container image at build time so
Piper always loads without network access — it is the fallback used when
any other provider fails to initialize.
"""

import logging
from pathlib import Path
from typing import Generator

from piper import PiperVoice

from app.providers.base import AudioChunk, AudioFormat, TTSProvider

logger = logging.getLogger(__name__)

_DEFAULT_VOICE = "en_GB-alan-low"
_MODELS_DIR = Path("app/models")


class PiperTTSProvider(TTSProvider):

    def __init__(self, voice_name: str = _DEFAULT_VOICE, models_dir: Path = _MODELS_DIR):
        self._voice_name = voice_name
        model_path = models_dir / f"{voice_name}.onnx"
        config_path = models_dir / f"{voice_name}.onnx.json"
        logger.info(f"Loading Piper voice '{voice_name}' from {model_path}")
        self._voice = PiperVoice.load(model_path=model_path, config_path=config_path)
        self._format = AudioFormat(
            sample_rate=self._voice.config.sample_rate,
            sample_width=2,
            channels=1,
        )

    @property
    def name(self) -> str:
        return "piper"

    def get_audio_format(self) -> AudioFormat:
        return self._format

    def synthesize(self, text: str) -> Generator[AudioChunk, None, None]:
        for chunk in self._voice.synthesize(text):
            fmt = AudioFormat(
                sample_rate=chunk.sample_rate,
                sample_width=chunk.sample_width,
                channels=chunk.sample_channels,
            )
            yield AudioChunk(audio_bytes=chunk.audio_int16_bytes, format=fmt)
