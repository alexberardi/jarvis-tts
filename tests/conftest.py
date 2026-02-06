"""Shared test fixtures for jarvis-tts.

Mocks piper, onnxruntime, and jarvis_log_client at the module level
so that app.main can be imported without requiring actual model files
or external service dependencies.
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
# Fake Piper objects
# ---------------------------------------------------------------------------

@dataclass
class FakeAudioChunk:
    """Mimics a piper audio chunk with 16-bit PCM silence."""

    sample_rate: int = 22050
    sample_channels: int = 1
    sample_width: int = 2  # bytes (16-bit)
    num_frames: int = 1024

    @property
    def audio_int16_bytes(self) -> bytes:
        return struct.pack(f"<{self.num_frames}h", *([0] * self.num_frames))


class FakePiperVoice:
    """Fake PiperVoice that yields silent audio chunks."""

    @classmethod
    def load(cls, model_path=None, config_path=None) -> "FakePiperVoice":
        return cls()

    def synthesize(self, text: str):
        yield FakeAudioChunk()


# ---------------------------------------------------------------------------
# Module-level mocks injected before app.main import
# ---------------------------------------------------------------------------

def _install_mock_modules() -> None:
    """Inject mock piper / onnxruntime / jarvis_log_client into sys.modules."""

    # --- piper (force override so model files aren't needed) ---
    piper_mod = types.ModuleType("piper")
    piper_mod.PiperVoice = FakePiperVoice  # type: ignore[attr-defined]
    sys.modules["piper"] = piper_mod

    # --- piper.voice (some installs expose this) ---
    piper_voice_mod = types.ModuleType("piper.voice")
    piper_voice_mod.PiperVoice = FakePiperVoice  # type: ignore[attr-defined]
    sys.modules["piper.voice"] = piper_voice_mod

    # --- onnxruntime (force override to suppress model loading) ---
    ort_mod = types.ModuleType("onnxruntime")
    ort_mod.set_default_logger_severity = lambda *a, **kw: None  # type: ignore[attr-defined]
    sys.modules["onnxruntime"] = ort_mod

    # --- jarvis_log_client (may not be installed in CI) ---
    if "jarvis_log_client" not in sys.modules:
        log_mod = types.ModuleType("jarvis_log_client")
        log_mod.JarvisLogHandler = MagicMock  # type: ignore[attr-defined]
        log_mod.init = MagicMock()  # type: ignore[attr-defined]
        sys.modules["jarvis_log_client"] = log_mod


_install_mock_modules()


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
def client():
    """FastAPI TestClient with auth dependency overridden."""
    from app.main import app, verify_app_auth

    app.dependency_overrides[verify_app_auth] = lambda: _make_auth_result()
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def unauthenticated_client():
    """FastAPI TestClient without auth override (real auth dependency)."""
    from app.main import app

    app.dependency_overrides.clear()
    yield TestClient(app)
    app.dependency_overrides.clear()
