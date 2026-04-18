"""Shared test fixtures for jarvis-tts.

Mocks piper, onnxruntime, and jarvis_log_client at the module level so
that app.main can be imported without requiring actual model files or
external service dependencies.
"""

import struct
import sys
import types
from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from jarvis_auth_client.models import AppAuthResult, AppValidationResult, RequestContext


# ---------------------------------------------------------------------------
# Fake Piper objects (legacy — kept for any tests still using them directly)
# ---------------------------------------------------------------------------

@dataclass
class FakeAudioChunk:
    """Mimics a piper audio chunk with 16-bit PCM silence."""

    sample_rate: int = 22050
    sample_channels: int = 1
    sample_width: int = 2
    num_frames: int = 1024

    @property
    def audio_int16_bytes(self) -> bytes:
        return struct.pack(f"<{self.num_frames}h", *([0] * self.num_frames))


class FakePiperVoice:
    """Fake PiperVoice that yields silent audio chunks."""

    @classmethod
    def load(cls, model_path=None, config_path=None) -> "FakePiperVoice":
        return cls()

    class _Config:
        sample_rate = 22050

    def __init__(self) -> None:
        self.config = self._Config()

    def synthesize(self, text: str):
        yield FakeAudioChunk()


# ---------------------------------------------------------------------------
# Module-level mocks injected before app.main import
# ---------------------------------------------------------------------------

def _install_mock_modules() -> None:
    piper_mod = types.ModuleType("piper")
    piper_mod.PiperVoice = FakePiperVoice  # type: ignore[attr-defined]
    sys.modules["piper"] = piper_mod

    piper_voice_mod = types.ModuleType("piper.voice")
    piper_voice_mod.PiperVoice = FakePiperVoice  # type: ignore[attr-defined]
    sys.modules["piper.voice"] = piper_voice_mod

    ort_mod = types.ModuleType("onnxruntime")
    ort_mod.set_default_logger_severity = lambda *a, **kw: None  # type: ignore[attr-defined]
    sys.modules["onnxruntime"] = ort_mod

    if "jarvis_log_client" not in sys.modules:
        log_mod = types.ModuleType("jarvis_log_client")
        log_mod.JarvisLogHandler = MagicMock  # type: ignore[attr-defined]
        log_mod.init = MagicMock()  # type: ignore[attr-defined]
        sys.modules["jarvis_log_client"] = log_mod


_install_mock_modules()


# ---------------------------------------------------------------------------
# Fake provider for endpoint tests
# ---------------------------------------------------------------------------

from app.providers.base import AudioChunk, AudioFormat, TTSProvider


class FakeTTSProvider(TTSProvider):
    """Deterministic provider that yields a single chunk of silence."""

    def __init__(self, name: str = "fake", sample_rate: int = 22050, num_chunks: int = 1,
                 frames_per_chunk: int = 1024):
        self._name = name
        self._format = AudioFormat(sample_rate=sample_rate, sample_width=2, channels=1)
        self._num_chunks = num_chunks
        self._frames_per_chunk = frames_per_chunk
        self.calls: list[str] = []

    @property
    def name(self) -> str:
        return self._name

    def get_audio_format(self) -> AudioFormat:
        return self._format

    def synthesize(self, text: str):
        self.calls.append(text)
        silent = struct.pack(f"<{self._frames_per_chunk}h", *([0] * self._frames_per_chunk))
        for _ in range(self._num_chunks):
            yield AudioChunk(audio_bytes=silent, format=self._format)


# ---------------------------------------------------------------------------
# Auth fixtures
# ---------------------------------------------------------------------------

def _make_auth_result(
    app_id: str = "command-center",
    household_id: str | None = "household-123",
    node_id: str | None = "kitchen-pi",
    user_id: int | None = None,
) -> AppAuthResult:
    return AppAuthResult(
        app=AppValidationResult(valid=True, app_id=app_id),
        context=RequestContext(
            household_id=household_id,
            node_id=node_id,
            user_id=user_id,
        ),
    )


@pytest.fixture
def fake_provider():
    return FakeTTSProvider()


@pytest.fixture
def client(fake_provider):
    """FastAPI TestClient with auth + provider dependency overrides."""
    from app.main import app, verify_app_auth
    from app.services.provider_manager import get_active_provider

    app.dependency_overrides[verify_app_auth] = lambda: _make_auth_result()
    app.dependency_overrides[get_active_provider] = lambda: fake_provider
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def unauthenticated_client():
    """FastAPI TestClient with no overrides (real auth dependency)."""
    from app.main import app

    app.dependency_overrides.clear()
    yield TestClient(app)
    app.dependency_overrides.clear()
