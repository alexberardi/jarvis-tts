"""Settings definitions for jarvis-tts.

Defines all configurable settings with their types, defaults, and metadata.
"""

from jarvis_settings_client import SettingDefinition


SETTINGS_DEFINITIONS: list[SettingDefinition] = [
    # TTS configuration
    SettingDefinition(
        key="tts.llm_proxy_version",
        category="tts",
        value_type="int",
        default=1,
        description="LLM Proxy API version for wake responses",
        env_fallback="JARVIS_LLM_PROXY_API_VERSION",
    ),
    SettingDefinition(
        key="tts.default_voice",
        category="tts",
        value_type="string",
        default="en_GB-alan-low",
        description="Default voice model for TTS",
        env_fallback="TTS_DEFAULT_VOICE",
        requires_reload=True,
    ),
    SettingDefinition(
        key="tts.wake_system_prompt",
        category="tts",
        value_type="string",
        default=(
            "You are Jarvis, a voice assistant butler. The user has just called you for help. "
            "Please keep the greeting gender neutral. Please keep the greeting to one or two short sentences, but make it charming. "
            "The entire response should be less than 10 words if possible. "
            "Generate a short greeting like 'At your service', 'How may I help you?', etc."
        ),
        description="System prompt for generating wake responses",
        env_fallback="TTS_WAKE_SYSTEM_PROMPT",
    ),

    # Server configuration
    SettingDefinition(
        key="server.port",
        category="server",
        value_type="int",
        default=8009,
        description="API server port",
        env_fallback="TTS_PORT",
        requires_reload=True,
    ),
    SettingDefinition(
        key="server.log_console_level",
        category="server",
        value_type="string",
        default="INFO",
        description="Console logging level (DEBUG, INFO, WARNING, ERROR)",
        env_fallback="JARVIS_LOG_CONSOLE_LEVEL",
    ),
    SettingDefinition(
        key="server.log_remote_level",
        category="server",
        value_type="string",
        default="DEBUG",
        description="Remote logging level (DEBUG, INFO, WARNING, ERROR)",
        env_fallback="JARVIS_LOG_REMOTE_LEVEL",
    ),

    # Auth configuration
    SettingDefinition(
        key="auth.cache_ttl_seconds",
        category="auth",
        value_type="int",
        default=60,
        description="Auth validation cache TTL in seconds",
        env_fallback="NODE_AUTH_CACHE_TTL",
    ),
]
