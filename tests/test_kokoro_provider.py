"""Tests for the Kokoro TTS provider.

The real `kokoro` package is not installed in CI; conftest.py injects a
FakeKPipeline into sys.modules so the provider imports cleanly. These
tests exercise the provider logic itself — voice prefix → lang_code
inference, float→int16 PCM conversion, and the streaming generator.
"""

import numpy as np
import pytest

# conftest.py installs the kokoro mock before this import
from app.providers.base import AudioChunk, AudioFormat
from app.providers.kokoro_provider import (
    KokoroTTSProvider,
    _float_to_int16_bytes,
    _lang_code_for_voice,
)


class TestLangCodeForVoice:

    @pytest.mark.parametrize("voice,expected", [
        ("bm_george", "b"),
        ("bm_fable", "b"),
        ("af_heart", "a"),
        ("am_adam", "a"),
        ("jf_alpha", "j"),
        ("Bm_George", "b"),  # uppercase first char
    ])
    def test_prefix_maps_to_lang_code(self, voice, expected):
        assert _lang_code_for_voice(voice) == expected

    def test_empty_voice_defaults_to_american(self):
        assert _lang_code_for_voice("") == "a"


class TestFloatToInt16Bytes:

    def test_zero_samples_produce_silence(self):
        samples = np.zeros(10, dtype=np.float32)
        pcm = _float_to_int16_bytes(samples)
        assert len(pcm) == 20  # 10 samples × 2 bytes
        assert all(b == 0 for b in pcm)

    def test_positive_peak_maps_to_int16_max(self):
        samples = np.array([1.0], dtype=np.float32)
        pcm = _float_to_int16_bytes(samples)
        # Little-endian int16 max-ish: 32767 = 0x7FFF
        assert pcm == b"\xff\x7f"

    def test_negative_peak_maps_close_to_int16_min(self):
        samples = np.array([-1.0], dtype=np.float32)
        pcm = _float_to_int16_bytes(samples)
        # -1.0 * 32767 = -32767 = 0x8001 little-endian
        assert pcm == b"\x01\x80"

    def test_values_outside_range_are_clipped(self):
        samples = np.array([2.0, -2.0], dtype=np.float32)
        pcm = _float_to_int16_bytes(samples)
        # Both clip to ±1.0 then scale to ±32767
        assert len(pcm) == 4
        assert pcm[:2] == b"\xff\x7f"
        assert pcm[2:] == b"\x01\x80"


class TestKokoroTTSProvider:

    def test_name_is_kokoro(self):
        provider = KokoroTTSProvider()
        assert provider.name == "kokoro"

    def test_default_constructor(self):
        provider = KokoroTTSProvider()
        assert provider._voice == "bm_george"
        assert provider._speed == 1.0

    def test_custom_voice_and_speed(self):
        provider = KokoroTTSProvider(voice="bm_fable", speed=1.25)
        assert provider._voice == "bm_fable"
        assert provider._speed == 1.25

    def test_speed_coerced_to_float(self):
        provider = KokoroTTSProvider(speed=1)
        assert isinstance(provider._speed, float)
        assert provider._speed == 1.0

    def test_get_audio_format_reports_24k_mono_16bit(self):
        provider = KokoroTTSProvider()
        fmt = provider.get_audio_format()
        assert fmt == AudioFormat(sample_rate=24000, sample_width=2, channels=1)

    def test_pipeline_initialized_with_lang_code_from_voice(self):
        provider = KokoroTTSProvider(voice="bm_george")
        assert provider._pipeline.lang_code == "b"

        american = KokoroTTSProvider(voice="af_heart")
        assert american._pipeline.lang_code == "a"

    def test_synthesize_yields_audio_chunks(self):
        provider = KokoroTTSProvider()
        chunks = list(provider.synthesize("hello"))
        # FakeKPipeline yields 2 segments
        assert len(chunks) == 2
        for chunk in chunks:
            assert isinstance(chunk, AudioChunk)
            assert chunk.format.sample_rate == 24000
            assert chunk.format.channels == 1
            assert chunk.format.sample_width == 2
            assert len(chunk.audio_bytes) == 2048  # 1024 samples × 2 bytes

    def test_synthesize_skips_none_audio(self, monkeypatch):
        """If the pipeline yields None for audio, skip that segment."""
        def fake_pipeline(text, voice, speed):
            yield ("g", "p", None)
            yield ("g", "p", np.zeros(512, dtype=np.float32))

        provider = KokoroTTSProvider()
        monkeypatch.setattr(provider, "_pipeline", fake_pipeline)
        chunks = list(provider.synthesize("hi"))
        assert len(chunks) == 1

    def test_synthesize_skips_empty_audio(self, monkeypatch):
        """Zero-length arrays yield no bytes and should be skipped."""
        def fake_pipeline(text, voice, speed):
            yield ("g", "p", np.array([], dtype=np.float32))
            yield ("g", "p", np.zeros(256, dtype=np.float32))

        provider = KokoroTTSProvider()
        monkeypatch.setattr(provider, "_pipeline", fake_pipeline)
        chunks = list(provider.synthesize("hi"))
        assert len(chunks) == 1

    def test_synthesize_handles_torch_tensor_audio(self, monkeypatch):
        """Pipeline may yield torch tensors; handle .detach().cpu().numpy() path."""
        class FakeTensor:
            def __init__(self, arr):
                self._arr = arr
            def detach(self):
                return self
            def cpu(self):
                return self
            def numpy(self):
                return self._arr

        def fake_pipeline(text, voice, speed):
            yield ("g", "p", FakeTensor(np.zeros(128, dtype=np.float32)))

        provider = KokoroTTSProvider()
        monkeypatch.setattr(provider, "_pipeline", fake_pipeline)
        chunks = list(provider.synthesize("hi"))
        assert len(chunks) == 1
        assert len(chunks[0].audio_bytes) == 256  # 128 × 2


class TestKokoroRegistry:
    """With the kokoro mock installed, the registry should register it."""

    def test_kokoro_registered(self):
        from app.providers import registry as registry_mod
        assert "kokoro" in registry_mod.available_providers()

    def test_load_kokoro_via_registry(self):
        from app.providers import registry as registry_mod
        provider = registry_mod.load_provider("kokoro", voice="bm_george", speed=1.25)
        assert provider.name == "kokoro"
