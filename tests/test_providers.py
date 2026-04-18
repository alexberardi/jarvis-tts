"""Tests for the provider registry, Piper provider wrapper, and provider manager."""

from unittest.mock import MagicMock, patch

import pytest

# conftest.py installs module mocks before this import
from app.providers.base import AudioChunk, AudioFormat, TTSProvider
from app.providers import registry as registry_mod
from app.providers.piper_provider import PiperTTSProvider


class _GoodProvider(TTSProvider):
    @property
    def name(self) -> str:
        return "good"

    def get_audio_format(self) -> AudioFormat:
        return AudioFormat(sample_rate=24000, sample_width=2, channels=1)

    def synthesize(self, text):
        yield AudioChunk(audio_bytes=b"\x00\x00", format=self.get_audio_format())


class _BrokenProvider(TTSProvider):
    def __init__(self):
        raise RuntimeError("cannot initialize")

    @property
    def name(self) -> str:
        return "broken"

    def get_audio_format(self) -> AudioFormat:
        raise NotImplementedError

    def synthesize(self, text):
        raise NotImplementedError


class TestPiperProvider:

    def test_piper_provider_loads(self):
        provider = PiperTTSProvider()
        assert provider.name == "piper"
        fmt = provider.get_audio_format()
        assert fmt.sample_rate == 22050
        assert fmt.channels == 1
        assert fmt.sample_width == 2

    def test_piper_synthesize_yields_chunks(self):
        provider = PiperTTSProvider()
        chunks = list(provider.synthesize("hello"))
        assert len(chunks) >= 1
        assert isinstance(chunks[0], AudioChunk)
        assert chunks[0].audio_bytes


class TestRegistry:

    def test_piper_always_registered(self):
        assert "piper" in registry_mod.available_providers()

    def test_load_known_provider(self):
        prov = registry_mod.load_provider("piper")
        assert prov.name == "piper"

    def test_load_unknown_provider_falls_back_to_piper(self):
        prov = registry_mod.load_provider("nonexistent-provider-xyz")
        assert prov.name == "piper"

    def test_load_broken_provider_falls_back_to_piper(self):
        registry_mod.register("broken-test", _BrokenProvider)
        try:
            prov = registry_mod.load_provider("broken-test")
            assert prov.name == "piper"
        finally:
            registry_mod._PROVIDERS.pop("broken-test", None)

    def test_load_custom_provider_with_kwargs(self):
        registry_mod.register("good-test", _GoodProvider)
        try:
            prov = registry_mod.load_provider("good-test")
            assert prov.name == "good"
        finally:
            registry_mod._PROVIDERS.pop("good-test", None)


class TestProviderManager:

    @pytest.fixture(autouse=True)
    def reset_manager(self):
        from app.services.provider_manager import reset_provider_manager
        reset_provider_manager()
        yield
        reset_provider_manager()

    def test_get_returns_provider(self):
        from app.services.provider_manager import get_active_provider
        prov = get_active_provider()
        assert isinstance(prov, TTSProvider)

    def test_caches_same_fingerprint(self):
        from app.services.provider_manager import get_active_provider
        first = get_active_provider()
        second = get_active_provider()
        assert first is second

    def test_reloads_when_fingerprint_changes(self):
        from app.services.provider_manager import get_provider_manager

        manager = get_provider_manager()
        with patch("app.services.provider_manager._read_fingerprint") as mock_fp, \
             patch("app.services.provider_manager._build_provider") as mock_build:
            from app.services.provider_manager import _ProviderFingerprint

            fp1 = _ProviderFingerprint(
                provider="piper", piper_voice="v1",
                kokoro_voice="bm_george", kokoro_speed=1.0,
            )
            fp2 = _ProviderFingerprint(
                provider="piper", piper_voice="v2",
                kokoro_voice="bm_george", kokoro_speed=1.0,
            )
            p1 = MagicMock(name="p1", spec=TTSProvider)
            p2 = MagicMock(name="p2", spec=TTSProvider)

            mock_fp.side_effect = [fp1, fp2, fp2]
            mock_build.side_effect = [p1, p2]

            first = manager.get()
            second = manager.get()
            third = manager.get()

            assert first is p1
            assert second is p2
            assert third is p2
            assert mock_build.call_count == 2

    def test_keeps_previous_on_reload_failure(self):
        from app.services.provider_manager import get_provider_manager, _ProviderFingerprint

        manager = get_provider_manager()
        with patch("app.services.provider_manager._read_fingerprint") as mock_fp, \
             patch("app.services.provider_manager._build_provider") as mock_build:

            fp1 = _ProviderFingerprint(
                provider="piper", piper_voice="v1",
                kokoro_voice="bm_george", kokoro_speed=1.0,
            )
            fp2 = _ProviderFingerprint(
                provider="kokoro", piper_voice="v1",
                kokoro_voice="bm_george", kokoro_speed=1.0,
            )
            p1 = MagicMock(name="piper-instance", spec=TTSProvider)
            p1.name = "piper"

            mock_fp.side_effect = [fp1, fp2]
            mock_build.side_effect = [p1, RuntimeError("kokoro failed")]

            first = manager.get()
            second = manager.get()

            # Reload failed → previous provider should be reused
            assert first is p1
            assert second is p1
