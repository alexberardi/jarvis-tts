#!/usr/bin/env bash
# Native production run script (launchd entry point on macOS).
#
# Installs the [kokoro] extra so Kokoro can run on MPS (Apple Silicon GPU).
# Idempotent: reuses .venv across restarts.

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$ROOT"

ENV_FILE="${ENV_FILE:-.env}"
SERVER_HOST="${SERVER_HOST:-0.0.0.0}"
TTS_PORT="${TTS_PORT:-7707}"

VENV="$ROOT/.venv"
PY="$VENV/bin/python"
SENTINEL="$VENV/.deps_installed"

if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
fi

export OBJC_DISABLE_INITIALIZE_FORK_SAFETY="${OBJC_DISABLE_INITIALIZE_FORK_SAFETY:-YES}"

if [[ ! -x "$PY" ]]; then
    echo "[tts-native] creating venv at $VENV"
    python3 -m venv "$VENV"
fi

if [[ ! -f "$SENTINEL" || "$ROOT/pyproject.toml" -nt "$SENTINEL" ]]; then
    echo "[tts-native] installing deps (kokoro extras included for MPS support)"
    "$PY" -m pip install -q --upgrade pip
    "$PY" -m pip install -q -e "$ROOT[kokoro]"
    touch "$SENTINEL"
fi

echo "[tts-native] running alembic migrations"
"$PY" -m alembic upgrade head

echo "[tts-native] starting uvicorn on ${SERVER_HOST}:${TTS_PORT}"
exec "$VENV/bin/uvicorn" app.main:app --host "$SERVER_HOST" --port "$TTS_PORT"
