"""Active TTS provider manager.

Reads provider selection + per-provider config from the settings service
(which is 60s-cached) and keeps a single live provider instance. When any
TTS setting changes, the next call reloads the provider transparently.
If reload fails, we keep the previous provider and log — never crash the
request path.
"""

import logging
import threading
from dataclasses import dataclass

from app.providers.base import TTSProvider
from app.providers.registry import load_provider
from app.services.settings_service import get_settings_service

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _ProviderFingerprint:
    """Settings state that should trigger a provider reload when changed."""
    provider: str
    piper_voice: str
    kokoro_voice: str
    kokoro_speed: float
    # Default "cpu" so older callers (tests / external tooling) that
    # predate this field still construct a valid fingerprint.
    kokoro_device: str = "cpu"


def _read_fingerprint() -> _ProviderFingerprint:
    settings = get_settings_service()
    return _ProviderFingerprint(
        provider=settings.get_str("tts.provider", "kokoro"),
        piper_voice=settings.get_str("tts.default_voice", "en_GB-alan-low"),
        kokoro_voice=settings.get_str("tts.kokoro_voice", "bm_george"),
        kokoro_speed=settings.get_float("tts.kokoro_speed", 1.25),
        kokoro_device=settings.get_str("tts.kokoro_device", "cpu"),
    )


def _build_provider(fp: _ProviderFingerprint) -> TTSProvider:
    if fp.provider == "piper":
        return load_provider("piper", voice_name=fp.piper_voice)
    if fp.provider == "kokoro":
        return load_provider(
            "kokoro",
            voice=fp.kokoro_voice,
            speed=fp.kokoro_speed,
            device=fp.kokoro_device,
        )
    return load_provider(fp.provider)


class ProviderManager:

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._provider: TTSProvider | None = None
        self._fingerprint: _ProviderFingerprint | None = None

    def get(self) -> TTSProvider:
        fp = _read_fingerprint()
        with self._lock:
            if self._provider is not None and self._fingerprint == fp:
                return self._provider

            logger.info(
                f"Loading TTS provider: {fp.provider} "
                f"(piper_voice={fp.piper_voice}, kokoro_voice={fp.kokoro_voice}, "
                f"kokoro_speed={fp.kokoro_speed}, kokoro_device={fp.kokoro_device})"
            )
            try:
                new_provider = _build_provider(fp)
            except Exception as e:
                if self._provider is not None:
                    logger.warning(
                        f"Failed to reload provider for fingerprint {fp}: {e}. "
                        f"Keeping previous provider '{self._provider.name}'.",
                        exc_info=True,
                    )
                    return self._provider
                raise

            self._provider = new_provider
            self._fingerprint = fp
            return new_provider

    def reset(self) -> None:
        """Drop the cached provider. Next `get()` rebuilds from settings."""
        with self._lock:
            self._provider = None
            self._fingerprint = None


_manager: ProviderManager | None = None


def get_provider_manager() -> ProviderManager:
    global _manager
    if _manager is None:
        _manager = ProviderManager()
    return _manager


def get_active_provider() -> TTSProvider:
    return get_provider_manager().get()


def reset_provider_manager() -> None:
    """Test helper — resets the singleton."""
    global _manager
    _manager = None
