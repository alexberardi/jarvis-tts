"""Seed tts.kokoro_device setting

Adds the new Kokoro device setting so it shows up in the admin UI and
can be toggled without a prior write. Default is 'cpu' — the current
production state. Switching to 'cuda' (when nvidia-docker is configured
on the TTS container) or 'mps' (Apple Silicon) is a single settings
update; the provider manager reloads within its ~60s cache window.

Revision ID: 004
Revises: 003
Create Date: 2026-04-23 16:30:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


NEW_SETTING = {
    "key": "tts.kokoro_device",
    "value": "cpu",
    "value_type": "string",
    "category": "tts",
    "description": "PyTorch device for Kokoro inference (cpu, cuda, mps)",
    "env_fallback": "TTS_KOKORO_DEVICE",
    "requires_reload": False,
    "is_secret": False,
}


def upgrade() -> None:
    conn = op.get_bind()
    is_postgres = conn.dialect.name == 'postgresql'

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
            NEW_SETTING,
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
            NEW_SETTING,
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("""
            DELETE FROM settings
            WHERE key = :key
              AND household_id IS NULL
              AND node_id IS NULL
              AND user_id IS NULL
        """),
        {"key": NEW_SETTING["key"]},
    )
