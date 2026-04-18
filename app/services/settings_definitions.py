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
        key="tts.provider",
        category="tts",
        value_type="string",
        default="kokoro",
        description="Active TTS provider backend",
        env_fallback="TTS_PROVIDER",
        options=["piper", "kokoro"],
    ),
    SettingDefinition(
        key="tts.default_voice",
        category="tts",
        value_type="string",
        default="en_GB-alan-low",
        description="Piper voice model name (looks up app/models/<name>.onnx)",
        env_fallback="TTS_DEFAULT_VOICE",
    ),
    SettingDefinition(
        key="tts.kokoro_voice",
        category="tts",
        value_type="string",
        default="bm_george",
        description="Kokoro voice ID (e.g., bm_george, bm_fable, af_heart)",
        env_fallback="TTS_KOKORO_VOICE",
    ),
    SettingDefinition(
        key="tts.kokoro_speed",
        category="tts",
        value_type="float",
        default=1.25,
        description="Kokoro speech speed multiplier",
        env_fallback="TTS_KOKORO_SPEED",
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
        default=7707,
        description="API server port",
        env_fallback="TTS_PORT",
        requires_reload=True,
    ),
    SettingDefinition(
        key="server.log_console_level",
        category="server",
        value_type="string",
        default="INFO",
        description="Console logging level",
        env_fallback="JARVIS_LOG_CONSOLE_LEVEL",
        options=["DEBUG", "INFO", "WARNING", "ERROR"],
    ),
    SettingDefinition(
        key="server.log_remote_level",
        category="server",
        value_type="string",
        default="DEBUG",
        description="Remote logging level",
        env_fallback="JARVIS_LOG_REMOTE_LEVEL",
        options=["DEBUG", "INFO", "WARNING", "ERROR"],
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
