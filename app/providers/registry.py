"""Provider registry + safe loader.

Registry is populated at import time. Optional providers (Kokoro) are
wrapped in try/except so missing packages don't break the module import.
`load_provider()` guarantees a working provider — if the requested one
fails to instantiate, it logs a warning and returns Piper.
"""

import logging
from typing import Any

from app.providers.base import TTSProvider
from app.providers.piper_provider import PiperTTSProvider

logger = logging.getLogger(__name__)

_PROVIDERS: dict[str, type[TTSProvider]] = {}


def register(name: str, cls: type[TTSProvider]) -> None:
    _PROVIDERS[name] = cls


def available_providers() -> list[str]:
    return sorted(_PROVIDERS.keys())


def load_provider(name: str, **kwargs: Any) -> TTSProvider:
    """Instantiate the named provider, or fall back to Piper on any failure.

    Piper is always registered and its model is baked into the image, so
    the fallback is always available.
    """
    cls = _PROVIDERS.get(name)
    if cls is None:
        logger.warning(
            f"Unknown TTS provider '{name}'; known: {available_providers()}. "
            f"Falling back to Piper."
        )
        return PiperTTSProvider()

    try:
        return cls(**kwargs)
    except Exception as e:
        logger.warning(
            f"Failed to load TTS provider '{name}': {e}. Falling back to Piper.",
            exc_info=True,
        )
        return PiperTTSProvider()


register("piper", PiperTTSProvider)

try:
    from app.providers.kokoro_provider import KokoroTTSProvider
    register("kokoro", KokoroTTSProvider)
except ImportError as e:
    logger.info(f"Kokoro provider not available (package missing): {e}")
