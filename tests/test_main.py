"""Tests for app/main.py — endpoints and startup logic.

Covers:
- GET /ping
- GET /health
- GET /audio/format
- POST /speak
- POST /speak/stream
- POST /generate-wake-response
- _setup_remote_logging()
- startup event
"""

import json
import wave
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# conftest.py installs mock modules before this import
from app.main import app, _setup_remote_logging

from tests.conftest import FakeTTSProvider


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
# GET /audio/format
# ---------------------------------------------------------------------------

class TestAudioFormatEndpoint:

    def test_audio_format_returns_provider_format(self, client, fake_provider):
        resp = client.get("/audio/format")
        assert resp.status_code == 200
        body = resp.json()
        assert body["sample_rate"] == 22050
        assert body["channels"] == 1
        assert body["sample_width"] == 2
        assert body["provider"] == "fake"


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

    def test_speak_multiple_chunks_concatenated(self):
        """When the provider yields multiple chunks, all frames appear in the WAV."""
        from app.main import app, verify_app_auth
        from app.services.provider_manager import get_active_provider
        from tests.conftest import _make_auth_result
        from fastapi.testclient import TestClient

        multi_provider = FakeTTSProvider(num_chunks=3, frames_per_chunk=100)
        app.dependency_overrides[verify_app_auth] = lambda: _make_auth_result()
        app.dependency_overrides[get_active_provider] = lambda: multi_provider
        try:
            with TestClient(app) as tc:
                resp = tc.post("/speak", json={"text": "multi"})
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        buf = BytesIO(resp.content)
        with wave.open(buf, "rb") as wf:
            assert wf.getnframes() == 300


# ---------------------------------------------------------------------------
# POST /speak/stream
# ---------------------------------------------------------------------------

class TestSpeakStreamEndpoint:

    def test_stream_returns_raw_pcm(self, client):
        resp = client.post("/speak/stream", json={"text": "Hello"})
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "audio/raw"

    def test_stream_sets_audio_headers(self, client):
        resp = client.post("/speak/stream", json={"text": "Hello"})
        assert resp.headers["x-audio-sample-rate"] == "22050"
        assert resp.headers["x-audio-channels"] == "1"
        assert resp.headers["x-audio-sample-width"] == "2"
        assert resp.headers["x-audio-provider"] == "fake"

    def test_stream_empty_text_returns_error(self, client):
        resp = client.post("/speak/stream", json={"text": ""})
        assert resp.status_code == 200
        assert resp.json() == {"error": "No text provided"}


# ---------------------------------------------------------------------------
# POST /generate-wake-response
# ---------------------------------------------------------------------------

class TestGenerateWakeResponse:

    @staticmethod
    def _openai_response(text: str) -> dict:
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
        mock_client = self._mock_client_with_response(
            payload=self._openai_response("")
        )
        with patch("app.main.httpx.AsyncClient", return_value=mock_client):
            resp = client.post("/generate-wake-response")

        assert resp.json() == {"text": "Yes?"}

    def test_wake_response_fallback_on_llm_proxy_error(self, client, env_vars):
        mock_client = self._mock_client_with_response(status=500)
        with patch("app.main.httpx.AsyncClient", return_value=mock_client):
            resp = client.post("/generate-wake-response")

        assert resp.status_code == 200
        assert resp.json() == {"text": "Yes?"}

    def test_wake_response_fallback_on_network_error(self, client, env_vars):
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
        mock_client = self._mock_client_with_response(payload={"choices": []})
        with patch("app.main.httpx.AsyncClient", return_value=mock_client):
            resp = client.post("/generate-wake-response")

        assert resp.json() == {"text": "Yes?"}

    def test_wake_response_sends_auth_headers(self, client, env_vars):
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

    def test_disabled_when_no_app_key(self):
        with patch("app.main._jarvis_log_available", True), \
             patch.dict("os.environ", {"JARVIS_APP_KEY": ""}, clear=False):
            _setup_remote_logging()

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
             patch("app.main.service_config") as mock_config, \
             patch("app.main.get_active_provider") as mock_provider:
            import asyncio
            from app.main import startup_event
            mock_provider.return_value = MagicMock(name="stub-provider")
            asyncio.run(startup_event())
            mock_setup.assert_called_once()
            mock_config.init.assert_called_once()
