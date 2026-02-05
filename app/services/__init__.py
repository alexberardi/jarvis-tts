"""Services module for jarvis-tts."""

from app.services.settings_definitions import SETTINGS_DEFINITIONS
from app.services.settings_service import TTSSettingsService, get_settings_service

__all__ = ["SETTINGS_DEFINITIONS", "TTSSettingsService", "get_settings_service"]
