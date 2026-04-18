"""Provider-agnostic TTS interface.

Any new backend (Piper, Kokoro, etc.) subclasses TTSProvider and emits
AudioChunk values with their declared AudioFormat. The format is declared
once per provider so clients can set response headers before the first
chunk is produced.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Generator


@dataclass(frozen=True)
class AudioFormat:
    sample_rate: int
    sample_width: int
    channels: int


@dataclass
class AudioChunk:
    audio_bytes: bytes
    format: AudioFormat


class TTSProvider(ABC):
    """Abstract base for TTS providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def synthesize(self, text: str) -> Generator[AudioChunk, None, None]:
        ...

    @abstractmethod
    def get_audio_format(self) -> AudioFormat:
        ...

    def is_available(self) -> bool:
        return True
