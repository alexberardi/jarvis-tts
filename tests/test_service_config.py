"""Tests for app/service_config.py – service URL discovery.

Covers:
- init() with and without config client
- shutdown()
- _get_url() fallback chain (config client → env var → default → error)
- get_auth_url() / get_llm_proxy_url() convenience helpers
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from app import service_config


@pytest.fixture(autouse=True)
def _reset_state():
    """Reset module-level state between tests."""
    service_config._initialized = False
    yield
    service_config._initialized = False


def _inject_config_client_stubs(**overrides: MagicMock) -> dict[str, MagicMock]:
    """Inject fake config_init/config_shutdown/get_service_url onto the module.

    Returns the mocks so tests can assert on them.  The caller is responsible
    for cleaning up (the autouse fixture resets ``_initialized`` already).
    """
    mocks: dict[str, MagicMock] = {
        "config_init": overrides.get("config_init", MagicMock(return_value=True)),
        "config_shutdown": overrides.get("config_shutdown", MagicMock()),
        "get_service_url": overrides.get("get_service_url", MagicMock(return_value=None)),
    }
    for name, mock in mocks.items():
        setattr(service_config, name, mock)
    return mocks


# ---------------------------------------------------------------------------
# init()
# ---------------------------------------------------------------------------


class TestInit:

    def test_init_without_config_client(self):
        """Falls back to env vars when jarvis-config-client is not available."""
        with patch.object(service_config, "_has_config_client", False):
            result = service_config.init()

        assert result is False
        assert service_config._initialized is True

    def test_init_without_config_url_env(self):
        """Falls back to env vars when JARVIS_CONFIG_URL is not set."""
        _inject_config_client_stubs()

        with patch.object(service_config, "_has_config_client", True), \
             patch.dict(os.environ, {}, clear=False):
            os.environ.pop("JARVIS_CONFIG_URL", None)
            result = service_config.init()

        assert result is False
        assert service_config._initialized is True

    def test_init_success(self):
        """Initializes service discovery when config client is available."""
        mocks = _inject_config_client_stubs()

        with patch.object(service_config, "_has_config_client", True), \
             patch.dict(os.environ, {"JARVIS_CONFIG_URL": "http://config:7700"}):
            result = service_config.init()

        assert result is True
        assert service_config._initialized is True
        mocks["config_init"].assert_called_once_with(
            config_url="http://config:7700", refresh_interval_seconds=300
        )

    def test_init_config_client_returns_false(self):
        """Handles config_init returning False (e.g., unreachable)."""
        mocks = _inject_config_client_stubs(
            config_init=MagicMock(return_value=False),
        )

        with patch.object(service_config, "_has_config_client", True), \
             patch.dict(os.environ, {"JARVIS_CONFIG_URL": "http://config:7700"}):
            result = service_config.init()

        assert result is False
        assert service_config._initialized is True

    def test_init_config_client_raises_runtime_error(self):
        """Handles RuntimeError from config_init gracefully."""
        _inject_config_client_stubs(
            config_init=MagicMock(side_effect=RuntimeError("connection failed")),
        )

        with patch.object(service_config, "_has_config_client", True), \
             patch.dict(os.environ, {"JARVIS_CONFIG_URL": "http://config:7700"}):
            result = service_config.init()

        assert result is False
        assert service_config._initialized is True


# ---------------------------------------------------------------------------
# shutdown()
# ---------------------------------------------------------------------------


class TestShutdown:

    def test_shutdown_with_config_client(self):
        """Calls config_shutdown when config client is available."""
        mocks = _inject_config_client_stubs()
        service_config._initialized = True

        with patch.object(service_config, "_has_config_client", True):
            service_config.shutdown()

        mocks["config_shutdown"].assert_called_once()
        assert service_config._initialized is False

    def test_shutdown_without_config_client(self):
        """No-op shutdown when config client is unavailable."""
        service_config._initialized = True

        with patch.object(service_config, "_has_config_client", False):
            service_config.shutdown()

        assert service_config._initialized is False


# ---------------------------------------------------------------------------
# _get_url() fallback chain
# ---------------------------------------------------------------------------


class TestGetUrl:

    def test_returns_url_from_config_client(self):
        """Uses config client when available and initialized."""
        service_config._initialized = True
        mocks = _inject_config_client_stubs(
            get_service_url=MagicMock(return_value="http://auth-from-config:7701"),
        )

        with patch.object(service_config, "_has_config_client", True):
            result = service_config._get_url("jarvis-auth")

        assert result == "http://auth-from-config:7701"
        mocks["get_service_url"].assert_called_once_with("jarvis-auth")

    def test_falls_back_to_env_when_config_returns_none(self):
        """Falls back to env var when config client returns None."""
        service_config._initialized = True
        _inject_config_client_stubs(
            get_service_url=MagicMock(return_value=None),
        )

        with patch.object(service_config, "_has_config_client", True), \
             patch.dict(os.environ, {"JARVIS_AUTH_BASE_URL": "http://auth-from-env:7701"}):
            result = service_config._get_url("jarvis-auth")

        assert result == "http://auth-from-env:7701"

    def test_falls_back_to_env_when_config_client_raises(self):
        """Falls back to env var when config client raises an exception."""
        service_config._initialized = True
        _inject_config_client_stubs(
            get_service_url=MagicMock(side_effect=Exception("network error")),
        )

        with patch.object(service_config, "_has_config_client", True), \
             patch.dict(os.environ, {"JARVIS_AUTH_BASE_URL": "http://auth-from-env:7701"}):
            result = service_config._get_url("jarvis-auth")

        assert result == "http://auth-from-env:7701"

    def test_falls_back_to_default_when_no_env(self):
        """Uses hardcoded default when no config client and no env var."""
        with patch.object(service_config, "_has_config_client", False):
            env = dict(os.environ)
            env.pop("JARVIS_AUTH_BASE_URL", None)
            with patch.dict(os.environ, env, clear=True):
                result = service_config._get_url("jarvis-auth")

        assert result == "http://localhost:7701"

    def test_raises_for_unknown_service_without_fallback(self):
        """Raises ValueError for unknown services with no fallback chain."""
        with patch.object(service_config, "_has_config_client", False):
            with pytest.raises(ValueError, match="Cannot discover"):
                service_config._get_url("jarvis-unknown-service")

    def test_skips_config_client_when_not_initialized(self):
        """Does not query config client when not initialized."""
        service_config._initialized = False

        with patch.object(service_config, "_has_config_client", True), \
             patch.dict(os.environ, {"JARVIS_AUTH_BASE_URL": "http://auth-env:7701"}):
            result = service_config._get_url("jarvis-auth")

        assert result == "http://auth-env:7701"

    def test_env_fallback_for_llm_proxy(self):
        """Resolves LLM proxy URL from env var."""
        with patch.object(service_config, "_has_config_client", False), \
             patch.dict(os.environ, {"JARVIS_LLM_PROXY_API_URL": "http://llm:7704"}):
            result = service_config._get_url("jarvis-llm-proxy-api")

        assert result == "http://llm:7704"


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------


class TestConvenienceHelpers:

    def test_get_auth_url(self):
        """get_auth_url() delegates to _get_url('jarvis-auth')."""
        with patch.object(service_config, "_get_url", return_value="http://auth:7701") as mock:
            result = service_config.get_auth_url()

        assert result == "http://auth:7701"
        mock.assert_called_once_with("jarvis-auth")

    def test_get_llm_proxy_url(self):
        """get_llm_proxy_url() delegates to _get_url('jarvis-llm-proxy-api')."""
        with patch.object(
            service_config, "_get_url", return_value="http://llm:7704"
        ) as mock:
            result = service_config.get_llm_proxy_url()

        assert result == "http://llm:7704"
        mock.assert_called_once_with("jarvis-llm-proxy-api")
