"""Seed default settings

Revision ID: 002
Revises: 001
Create Date: 2026-02-05 17:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


# Settings definitions from app/services/settings_definitions.py
# All settings are safe to seed (no secrets or URLs)
SETTINGS = [
    # TTS configuration
    {
        "key": "tts.llm_proxy_version",
        "value": "1",
        "value_type": "int",
        "category": "tts",
        "description": "LLM Proxy API version for wake responses",
        "env_fallback": "JARVIS_LLM_PROXY_API_VERSION",
        "requires_reload": False,
        "is_secret": False,
    },
    {
        "key": "tts.default_voice",
        "value": "en_GB-alan-low",
        "value_type": "string",
        "category": "tts",
        "description": "Default voice model for TTS",
        "env_fallback": "TTS_DEFAULT_VOICE",
        "requires_reload": True,
        "is_secret": False,
    },
    {
        "key": "tts.wake_system_prompt",
        "value": "You are Jarvis, a voice assistant butler. The user has just called you for help. Please keep the greeting gender neutral. Please keep the greeting to one or two short sentences, but make it charming. The entire response should be less than 10 words if possible. Generate a short greeting like 'At your service', 'How may I help you?', etc.",
        "value_type": "string",
        "category": "tts",
        "description": "System prompt for generating wake responses",
        "env_fallback": "TTS_WAKE_SYSTEM_PROMPT",
        "requires_reload": False,
        "is_secret": False,
    },
    # Server configuration
    {
        "key": "server.port",
        "value": "8009",
        "value_type": "int",
        "category": "server",
        "description": "API server port",
        "env_fallback": "TTS_PORT",
        "requires_reload": True,
        "is_secret": False,
    },
    {
        "key": "server.log_console_level",
        "value": "INFO",
        "value_type": "string",
        "category": "server",
        "description": "Console logging level (DEBUG, INFO, WARNING, ERROR)",
        "env_fallback": "JARVIS_LOG_CONSOLE_LEVEL",
        "requires_reload": False,
        "is_secret": False,
    },
    {
        "key": "server.log_remote_level",
        "value": "DEBUG",
        "value_type": "string",
        "category": "server",
        "description": "Remote logging level (DEBUG, INFO, WARNING, ERROR)",
        "env_fallback": "JARVIS_LOG_REMOTE_LEVEL",
        "requires_reload": False,
        "is_secret": False,
    },
    # Auth configuration
    {
        "key": "auth.cache_ttl_seconds",
        "value": "60",
        "value_type": "int",
        "category": "auth",
        "description": "Auth validation cache TTL in seconds",
        "env_fallback": "NODE_AUTH_CACHE_TTL",
        "requires_reload": False,
        "is_secret": False,
    },
]


def upgrade() -> None:
    conn = op.get_bind()
    is_postgres = conn.dialect.name == 'postgresql'

    for setting in SETTINGS:
        if is_postgres:
            conn.execute(
                sa.text("""
                    INSERT INTO settings (key, value, value_type, category, description,
                                         env_fallback, requires_reload, is_secret,
                                         household_id, node_id, user_id)
                    VALUES (:key, :value, :value_type, :category, :description,
                           :env_fallback, :requires_reload, :is_secret,
                           NULL, NULL, NULL)
                    ON CONFLICT (key, household_id, node_id, user_id) DO NOTHING
                """),
                setting
            )
        else:
            conn.execute(
                sa.text("""
                    INSERT OR IGNORE INTO settings (key, value, value_type, category, description,
                                                   env_fallback, requires_reload, is_secret,
                                                   household_id, node_id, user_id)
                    VALUES (:key, :value, :value_type, :category, :description,
                           :env_fallback, :requires_reload, :is_secret,
                           NULL, NULL, NULL)
                """),
                setting
            )


def downgrade() -> None:
    conn = op.get_bind()
    for setting in SETTINGS:
        conn.execute(
            sa.text("""
                DELETE FROM settings
                WHERE key = :key
                  AND household_id IS NULL
                  AND node_id IS NULL
                  AND user_id IS NULL
            """),
            {"key": setting["key"]}
        )
