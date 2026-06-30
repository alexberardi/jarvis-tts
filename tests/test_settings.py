"""Tests for the settings service and definitions.

These tests cover:
- Settings definitions
- Settings service behavior
- Helper methods
"""

import importlib.util
import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from jarvis_settings_client import SettingDefinition
from jarvis_settings_client.service import SettingsService
from jarvis_settings_client.types import SettingValue

from app.services.settings_definitions import SETTINGS_DEFINITIONS
from app.services.settings_service import (
    get_settings_service,
    reset_settings_service,
)


class TestSettingsDefinitions:
    """Tests for settings definitions."""

    def test_all_definitions_have_required_fields(self):
        """Test that all definitions have required fields."""
        for definition in SETTINGS_DEFINITIONS:
            assert definition.key, f"Missing key for definition"
            assert definition.category, f"Missing category for {definition.key}"
            assert definition.value_type in ("string", "int", "float", "bool", "json"), \
                f"Invalid value_type for {definition.key}: {definition.value_type}"

    def test_no_duplicate_keys(self):
        """Test that there are no duplicate keys."""
        keys = [d.key for d in SETTINGS_DEFINITIONS]
        assert len(keys) == len(set(keys)), "Duplicate keys found in SETTINGS_DEFINITIONS"

    def test_key_format(self):
        """Test that keys follow the expected format."""
        for definition in SETTINGS_DEFINITIONS:
            # Keys should be lowercase with dots
            assert "." in definition.key, f"Key should contain dots: {definition.key}"
            assert definition.key == definition.key.lower(), \
                f"Key should be lowercase: {definition.key}"

    def test_expected_settings_exist(self):
        """Test that expected TTS settings are defined."""
        keys = [d.key for d in SETTINGS_DEFINITIONS]
        assert "tts.llm_proxy_version" in keys
        assert "tts.default_voice" in keys
        assert "server.port" in keys
        assert "auth.cache_ttl_seconds" in keys

    def test_tts_provider_defaults_to_piper(self):
        """tts.provider must default to piper (local, zero runtime egress).

        Kokoro downloads HF weights on first use, so it stays an explicit
        opt-in. The definition default is what a fresh install lands on when
        no DB row and no env override exist.
        """
        provider_def = next(
            d for d in SETTINGS_DEFINITIONS if d.key == "tts.provider"
        )
        assert provider_def.default == "piper"
        assert provider_def.env_fallback == "TTS_PROVIDER"
        assert "piper" in provider_def.options
        assert "kokoro" in provider_def.options


class TestProviderSeedMigration:
    """Guards the alembic seed value for tts.provider.

    There's no migration harness in this repo, so this is a string/AST-level
    guard rather than a fresh-upgrade DB assertion: it loads migration 003's
    NEW_SETTINGS list and asserts the seeded tts.provider value is 'piper'.

    Fresh DBs seed piper (local, zero runtime egress). Already-migrated DBs
    keep whatever row they have — there is deliberately NO flip-everyone
    migration, so existing kokoro rows are left untouched.
    """

    def _load_migration_003(self):
        migration_path = (
            Path(__file__).resolve().parents[1]
            / "alembic"
            / "versions"
            / "003_seed_multi_provider_settings.py"
        )
        spec = importlib.util.spec_from_file_location(
            "migration_003_seed_multi_provider_settings", migration_path
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_seed_value_for_tts_provider_is_piper(self):
        module = self._load_migration_003()
        seed = next(s for s in module.NEW_SETTINGS if s["key"] == "tts.provider")
        assert seed["value"] == "piper"

    def test_no_flip_everyone_update_for_tts_provider(self):
        """The migration must not contain an UPDATE that rewrites existing
        tts.provider rows (existing kokoro installs stay put)."""
        migration_path = (
            Path(__file__).resolve().parents[1]
            / "alembic"
            / "versions"
            / "003_seed_multi_provider_settings.py"
        )
        source = migration_path.read_text()
        # The only UPDATE in this migration touches tts.default_voice metadata,
        # never tts.provider. A flip-everyone change would add an UPDATE keyed
        # on tts.provider.
        assert "UPDATE settings" in source  # the existing default_voice update
        assert "key = 'tts.provider'" not in source


class TestSettingsServiceCache:
    """Tests for SettingsService caching behavior."""

    @pytest.fixture
    def service(self):
        """Create a service instance for testing."""
        return SettingsService(
            definitions=SETTINGS_DEFINITIONS,
            get_db_session=lambda: None,
            setting_model=None,
        )

    def test_cache_hit(self, service):
        """Test that cached values are returned without DB query."""
        # Manually populate cache
        cache_key = service._make_cache_key("tts.llm_proxy_version")
        service._cache[cache_key] = SettingValue(
            value=2,
            value_type="int",
            requires_reload=False,
            is_secret=False,
            env_fallback="JARVIS_LLM_PROXY_API_VERSION",
            from_db=True,
            cached_at=time.time(),
        )

        # Should return cached value without DB query
        result = service.get("tts.llm_proxy_version")
        assert result == 2

    def test_cache_expiry(self, service):
        """Test that expired cache entries are not used."""
        # Populate cache with expired entry
        cache_key = service._make_cache_key("tts.llm_proxy_version")
        service._cache[cache_key] = SettingValue(
            value=2,
            value_type="int",
            requires_reload=False,
            is_secret=False,
            env_fallback="JARVIS_LLM_PROXY_API_VERSION",
            from_db=True,
            cached_at=time.time() - 120,  # 2 minutes ago (expired)
        )

        # Should fall through to env/default since cache is expired
        with patch.dict(os.environ, {"JARVIS_LLM_PROXY_API_VERSION": "3"}):
            result = service.get("tts.llm_proxy_version")
            assert result == 3

    def test_invalidate_all(self, service):
        """Test invalidating entire cache."""
        key1_cache = service._make_cache_key("test.key1")
        key2_cache = service._make_cache_key("test.key2")

        service._cache[key1_cache] = SettingValue(
            value="value1",
            value_type="string",
            requires_reload=False,
            is_secret=False,
            env_fallback=None,
            from_db=True,
            cached_at=time.time(),
        )
        service._cache[key2_cache] = SettingValue(
            value="value2",
            value_type="string",
            requires_reload=False,
            is_secret=False,
            env_fallback=None,
            from_db=True,
            cached_at=time.time(),
        )

        service.invalidate_cache()

        assert len(service._cache) == 0


class TestSettingsServiceEnvFallback:
    """Tests for environment variable fallback."""

    @pytest.fixture
    def service(self):
        """Create a service instance for testing."""
        return SettingsService(
            definitions=SETTINGS_DEFINITIONS,
            get_db_session=lambda: None,
            setting_model=None,
        )

    def test_env_fallback_when_db_unavailable(self, service):
        """Test that env vars are used when DB is unavailable."""
        with patch.dict(os.environ, {"JARVIS_LLM_PROXY_API_VERSION": "2"}):
            result = service.get("tts.llm_proxy_version")
            assert result == 2

    def test_default_when_no_env(self, service):
        """Test that defaults are used when no env var is set."""
        with patch.dict(os.environ, {}, clear=True):
            result = service.get("tts.llm_proxy_version")
            # Should return definition default (1)
            assert result == 1

    def test_unknown_key_returns_none(self, service):
        """Test that unknown keys return None."""
        result = service.get("unknown.key")
        assert result is None


class TestSettingsServiceTypedGetters:
    """Tests for typed getter methods."""

    @pytest.fixture
    def service(self):
        """Create a service instance for testing."""
        return SettingsService(
            definitions=SETTINGS_DEFINITIONS,
            get_db_session=lambda: None,
            setting_model=None,
        )

    def test_get_int(self, service):
        """Test get_int method."""
        with patch.dict(os.environ, {"JARVIS_LLM_PROXY_API_VERSION": "3"}):
            result = service.get_int("tts.llm_proxy_version", 0)
            assert result == 3
            assert isinstance(result, int)

    def test_get_str(self, service):
        """Test get_str method."""
        with patch.dict(os.environ, {"TTS_DEFAULT_VOICE": "en_US-joe-medium"}):
            result = service.get_str("tts.default_voice", "")
            assert result == "en_US-joe-medium"
            assert isinstance(result, str)


class TestSettingsServiceListMethods:
    """Tests for listing methods."""

    @pytest.fixture
    def service(self):
        """Create a service instance for testing."""
        return SettingsService(
            definitions=SETTINGS_DEFINITIONS,
            get_db_session=lambda: None,
            setting_model=None,
        )

    def test_list_categories(self, service):
        """Test list_categories returns unique categories."""
        categories = service.list_categories()

        assert isinstance(categories, list)
        assert len(categories) > 0
        assert "tts" in categories
        assert "server" in categories
        # Should be sorted
        assert categories == sorted(categories)

    def test_list_all(self, service):
        """Test list_all returns all settings."""
        settings = service.list_all()

        assert isinstance(settings, list)
        assert len(settings) == len(SETTINGS_DEFINITIONS)

        # Check structure of first setting
        first = settings[0]
        assert "key" in first
        assert "value" in first
        assert "value_type" in first
        assert "category" in first
        assert "from_db" in first

    def test_list_all_with_category_filter(self, service):
        """Test list_all with category filter."""
        settings = service.list_all(category="tts")

        assert all(s["category"] == "tts" for s in settings)
        assert len(settings) > 0


class TestSingleton:
    """Tests for singleton behavior via get_settings_service."""

    @pytest.fixture(autouse=True)
    def reset(self):
        """Reset singleton before and after each test."""
        reset_settings_service()
        yield
        reset_settings_service()

    def test_singleton_instance(self):
        """Test that get_settings_service returns same instance."""
        # Mock the db imports to avoid actual DB connection
        mock_setting = MagicMock()
        mock_session_local = MagicMock()

        with patch("app.db.session.get_session_local", return_value=mock_session_local):
            with patch("app.db.models.Setting", mock_setting):
                service1 = get_settings_service()
                service2 = get_settings_service()

                assert service1 is service2
