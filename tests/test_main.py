"""Tests for app/main.py – endpoints and startup logic.

Covers:
- GET /ping
- GET /health
- POST /speak
- POST /generate-wake-response
- _setup_remote_logging()
- startup event
"""

import json
import struct
import wave
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# conftest.py installs mock modules before this import
from app.main import app, _setup_remote_logging

from tests.conftest import FakeAudioChunk, FakePiperVoice


# ---------------------------------------------------------------------------
# GET /ping
# ---------------------------------------------------------------------------

class TestPingEndpoint:

    def test_ping_returns_pong(self, client):
        resp = client.get("/ping")
        assert resp.status_code == 200
        assert resp.json() == {"message": "pong"}

    def test_ping_no_auth_required(self, unauthenticated_client):
        resp = unauthenticated_client.get("/ping")
        assert resp.status_code == 200
        assert resp.json() == {"message": "pong"}


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

class TestHealthEndpoint:

    def test_health_returns_healthy(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "healthy"}

    def test_health_no_auth_required(self, unauthenticated_client):
        resp = unauthenticated_client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "healthy"}


# ---------------------------------------------------------------------------
# POST /speak
# ---------------------------------------------------------------------------

class TestSpeakEndpoint:

    def test_speak_returns_wav_audio(self, client):
        resp = client.post("/speak", json={"text": "Hello world"})
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "audio/wav"

    def test_speak_wav_has_valid_header(self, client):
        resp = client.post("/speak", json={"text": "Test audio"})
        buf = BytesIO(resp.content)
        with wave.open(buf, "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 22050

    def test_speak_empty_text_returns_error(self, client):
        resp = client.post("/speak", json={"text": ""})
        assert resp.status_code == 200
        assert resp.json() == {"error": "No text provided"}

    def test_speak_missing_text_key_returns_error(self, client):
        resp = client.post("/speak", json={"foo": "bar"})
        assert resp.status_code == 200
        assert resp.json() == {"error": "No text provided"}

    def test_speak_requires_auth(self, unauthenticated_client):
        resp = unauthenticated_client.post("/speak", json={"text": "Hi"})
        assert resp.status_code in (401, 422)

    def test_speak_multiple_chunks_concatenated(self, client):
        """When the voice yields multiple chunks, all frames appear in the WAV."""
        chunks = [
            FakeAudioChunk(num_frames=100),
            FakeAudioChunk(num_frames=200),
            FakeAudioChunk(num_frames=300),
        ]

        class MultiChunkVoice(FakePiperVoice):
            def synthesize(self, text: str):
                yield from chunks

        import app.main as main_mod
        original_voice = main_mod.voice
        main_mod.voice = MultiChunkVoice()
        try:
            resp = client.post("/speak", json={"text": "multi"})
        finally:
            main_mod.voice = original_voice

        assert resp.status_code == 200
        buf = BytesIO(resp.content)
        with wave.open(buf, "rb") as wf:
            assert wf.getnframes() == 600  # 100 + 200 + 300


# ---------------------------------------------------------------------------
# POST /generate-wake-response
# ---------------------------------------------------------------------------

class TestGenerateWakeResponse:

    @staticmethod
    def _openai_response(text: str) -> dict:
        """Build an OpenAI-compatible chat completion response payload."""
        return {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 0,
            "model": "live",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

    @pytest.fixture
    def env_vars(self, monkeypatch):
        monkeypatch.setenv("JARVIS_LLM_PROXY_API_URL", "http://llm-proxy:8000")
        monkeypatch.setenv("JARVIS_APP_ID", "jarvis-tts")
        monkeypatch.setenv("JARVIS_APP_KEY", "test-key")

    @staticmethod
    def _mock_client_with_response(status: int = 200, payload: dict | None = None) -> AsyncMock:
        http_response = httpx.Response(
            status_code=status,
            content=json.dumps(payload or {}).encode(),
            request=httpx.Request("POST", "http://llm-proxy:8000/v1/chat/completions"),
        )
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=http_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        return mock_client

    def test_wake_response_returns_text(self, client, env_vars):
        mock_client = self._mock_client_with_response(
            payload=self._openai_response("At your service!")
        )
        with patch("app.main.httpx.AsyncClient", return_value=mock_client):
            resp = client.post("/generate-wake-response")

        assert resp.status_code == 200
        assert resp.json() == {"text": "At your service!"}

    def test_wake_response_strips_whitespace(self, client, env_vars):
        mock_client = self._mock_client_with_response(
            payload=self._openai_response("  Hello!  ")
        )
        with patch("app.main.httpx.AsyncClient", return_value=mock_client):
            resp = client.post("/generate-wake-response")

        assert resp.json()["text"] == "Hello!"

    def test_wake_response_fallback_on_empty_content(self, client, env_vars):
        """Empty LLM content falls back to 'Yes?' instead of returning blank."""
        mock_client = self._mock_client_with_response(
            payload=self._openai_response("")
        )
        with patch("app.main.httpx.AsyncClient", return_value=mock_client):
            resp = client.post("/generate-wake-response")

        assert resp.json() == {"text": "Yes?"}

    def test_wake_response_fallback_on_llm_proxy_error(self, client, env_vars):
        """HTTP error from LLM proxy falls back to 'Yes?' — never 500s."""
        mock_client = self._mock_client_with_response(status=500)
        with patch("app.main.httpx.AsyncClient", return_value=mock_client):
            resp = client.post("/generate-wake-response")

        assert resp.status_code == 200
        assert resp.json() == {"text": "Yes?"}

    def test_wake_response_fallback_on_network_error(self, client, env_vars):
        """Network error falls back to 'Yes?' without raising."""
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            side_effect=httpx.ConnectError("connection refused")
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        with patch("app.main.httpx.AsyncClient", return_value=mock_client):
            resp = client.post("/generate-wake-response")

        assert resp.status_code == 200
        assert resp.json() == {"text": "Yes?"}

    def test_wake_response_fallback_on_malformed_response(self, client, env_vars):
        """Response without choices falls back to 'Yes?'."""
        mock_client = self._mock_client_with_response(payload={"choices": []})
        with patch("app.main.httpx.AsyncClient", return_value=mock_client):
            resp = client.post("/generate-wake-response")

        assert resp.json() == {"text": "Yes?"}

    def test_wake_response_sends_auth_headers(self, client, env_vars):
        """App auth headers reach the LLM proxy."""
        mock_client = self._mock_client_with_response(
            payload=self._openai_response("Hi")
        )
        with patch("app.main.httpx.AsyncClient", return_value=mock_client):
            client.post("/generate-wake-response")

        call_kwargs = mock_client.post.await_args.kwargs
        assert call_kwargs["headers"]["X-Jarvis-App-Id"] == "jarvis-tts"
        assert call_kwargs["headers"]["X-Jarvis-App-Key"] == "test-key"

    def test_wake_response_uses_correct_llm_url(self, client, monkeypatch):
        monkeypatch.setenv("JARVIS_LLM_PROXY_API_URL", "http://custom-host:9000")
        monkeypatch.setenv("JARVIS_APP_ID", "jarvis-tts")
        monkeypatch.setenv("JARVIS_APP_KEY", "k")

        mock_client = self._mock_client_with_response(
            payload=self._openai_response("Hi")
        )
        with patch("app.main.httpx.AsyncClient", return_value=mock_client):
            client.post("/generate-wake-response")

        assert (
            mock_client.post.await_args.args[0]
            == "http://custom-host:9000/v1/chat/completions"
        )

    def test_wake_response_requires_auth(self, unauthenticated_client):
        resp = unauthenticated_client.post("/generate-wake-response")
        assert resp.status_code in (401, 422)


# ---------------------------------------------------------------------------
# _setup_remote_logging
# ---------------------------------------------------------------------------

class TestSetupRemoteLogging:

    def test_disabled_when_no_log_client(self):
        with patch("app.main._jarvis_log_available", False):
            _setup_remote_logging()
            # Should return early; no error

    def test_disabled_when_no_app_key(self):
        with patch("app.main._jarvis_log_available", True), \
             patch.dict("os.environ", {"JARVIS_APP_KEY": ""}, clear=False):
            _setup_remote_logging()
            # Should return early; no error

    def test_enabled_with_valid_config(self):
        mock_init = MagicMock()
        mock_handler_cls = MagicMock()

        with patch("app.main._jarvis_log_available", True), \
             patch("app.main.init_log_client", mock_init), \
             patch("app.main.JarvisLogHandler", mock_handler_cls), \
             patch.dict("os.environ", {
                 "JARVIS_APP_ID": "jarvis-tts",
                 "JARVIS_APP_KEY": "test-key",
             }):
            _setup_remote_logging()

        mock_init.assert_called_once_with(app_id="jarvis-tts", app_key="test-key")
        mock_handler_cls.assert_called_once()


# ---------------------------------------------------------------------------
# Startup event
# ---------------------------------------------------------------------------

class TestStartupEvent:

    def test_startup_calls_setup_remote_logging(self):
        with patch("app.main._setup_remote_logging") as mock_setup, \
             patch("app.main.service_config") as mock_config:
            import asyncio
            from app.main import startup_event
            asyncio.run(startup_event())
            mock_setup.assert_called_once()
            mock_config.init.assert_called_once()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _async_line_iter(lines: list[str]):
    """Return a callable that produces an async iterator over *lines*."""
    async def _iter():
        for line in lines:
            yield line
    return _iter


class _FakeStreamCtx:
    """Async context manager wrapping a mock response object."""

    def __init__(self, resp):
        self._resp = resp

    async def __aenter__(self):
        return self._resp

    async def __aexit__(self, *exc):
        return None


def _fake_stream_context(mock_resp):
    """Return a callable that mimics ``httpx.AsyncClient.stream(...)``."""
    def _stream(*args, **kwargs):
        return _FakeStreamCtx(mock_resp)
    return _stream
