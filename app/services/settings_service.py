"""Settings service for jarvis-tts.

Provides runtime configuration that can be modified without restarting.
Settings are stored in the database with fallback to environment variables.
"""

import logging
from typing import Any

from jarvis_settings_client import SettingsService as BaseSettingsService

from app.services.settings_definitions import SETTINGS_DEFINITIONS

logger = logging.getLogger(__name__)


class TTSSettingsService(BaseSettingsService):
    """Settings service for TTS with helper methods."""

    def get_tts_config(self) -> dict[str, Any]:
        """Get TTS configuration."""
        return {
            "llm_proxy_version": self.get_int("tts.llm_proxy_version", 1),
            "default_voice": self.get_str("tts.default_voice", "en_GB-alan-low"),
            "wake_system_prompt": self.get_str("tts.wake_system_prompt", ""),
        }


# Global singleton
_settings_service: TTSSettingsService | None = None


def get_settings_service() -> TTSSettingsService:
    """Get the global SettingsService instance."""
    global _settings_service
    if _settings_service is None:
        from app.db.models import Setting
        from app.db.session import get_session_local

        SessionLocal = get_session_local()
        _settings_service = TTSSettingsService(
            definitions=SETTINGS_DEFINITIONS,
            get_db_session=SessionLocal,
            setting_model=Setting,
        )
    return _settings_service


def reset_settings_service() -> None:
    """Reset the settings service singleton (for testing)."""
    global _settings_service
    _settings_service = None
