"""Seed multi-provider TTS settings

Adds rows for the new provider-selection keys introduced with the Kokoro
TTS backend. Existing installs don't strictly need these rows (the
definition defaults + env fallback cover all lookups), but seeding makes
the settings visible in the admin UI and editable via the settings API
without a prior write.

Revision ID: 003
Revises: 002
Create Date: 2026-04-18 11:30:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


NEW_SETTINGS = [
    {
        "key": "tts.provider",
        "value": "kokoro",
        "value_type": "string",
        "category": "tts",
        "description": "Active TTS provider backend",
        "env_fallback": "TTS_PROVIDER",
        "requires_reload": False,
        "is_secret": False,
    },
    {
        "key": "tts.kokoro_voice",
        "value": "bm_george",
        "value_type": "string",
        "category": "tts",
        "description": "Kokoro voice ID (e.g., bm_george, bm_fable, af_heart)",
        "env_fallback": "TTS_KOKORO_VOICE",
        "requires_reload": False,
        "is_secret": False,
    },
    {
        "key": "tts.kokoro_speed",
        "value": "1.25",
        "value_type": "float",
        "category": "tts",
        "description": "Kokoro speech speed multiplier",
        "env_fallback": "TTS_KOKORO_SPEED",
        "requires_reload": False,
        "is_secret": False,
    },
]


def upgrade() -> None:
    conn = op.get_bind()
    is_postgres = conn.dialect.name == 'postgresql'

    # Update the existing tts.default_voice row: it no longer requires a
    # restart (the provider manager lazily reloads within the settings
    # cache window), and its description should reflect Piper specificity.
    conn.execute(
        sa.text("""
            UPDATE settings
            SET description = :description, requires_reload = :requires_reload
            WHERE key = 'tts.default_voice'
              AND household_id IS NULL AND node_id IS NULL AND user_id IS NULL
        """),
        {
            "description": "Piper voice model name (looks up app/models/<name>.onnx)",
            "requires_reload": False,
        },
    )

    # Insert the new multi-provider keys (idempotent: skip if already present).
    for setting in NEW_SETTINGS:
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
                setting,
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
                setting,
            )


def downgrade() -> None:
    conn = op.get_bind()

    # Restore the original tts.default_voice metadata.
    conn.execute(
        sa.text("""
            UPDATE settings
            SET description = :description, requires_reload = :requires_reload
            WHERE key = 'tts.default_voice'
              AND household_id IS NULL AND node_id IS NULL AND user_id IS NULL
        """),
        {
            "description": "Default voice model for TTS",
            "requires_reload": True,
        },
    )

    for setting in NEW_SETTINGS:
        conn.execute(
            sa.text("""
                DELETE FROM settings
                WHERE key = :key
                  AND household_id IS NULL
                  AND node_id IS NULL
                  AND user_id IS NULL
            """),
            {"key": setting["key"]},
        )
