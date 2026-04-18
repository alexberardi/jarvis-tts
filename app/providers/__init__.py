"""TTS provider abstraction layer.

Each provider implements the TTSProvider ABC and is registered in the registry.
Providers are selected at runtime via the `tts.provider` setting.
"""

from app.providers.base import AudioChunk, AudioFormat, TTSProvider

__all__ = ["AudioChunk", "AudioFormat", "TTSProvider"]
