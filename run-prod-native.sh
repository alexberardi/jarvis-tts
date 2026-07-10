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
    # Pick a Python >=3.11 (this project requires it). macOS system python3 is
    # usually 3.9, and `brew install python@3.11` provides `python3.11` — NOT a
    # bare `python3` — so prefer explicitly-versioned interpreters, and only
    # accept `python3` when it is new enough. Fail loudly instead of building a
    # 3.9 venv that pip then rejects dependency-by-dependency.
    BASE_PY=""
    for _cand in python3.13 python3.12 python3.11; do
        if command -v "$_cand" >/dev/null 2>&1; then BASE_PY="$_cand"; break; fi
    done
    if [[ -z "$BASE_PY" ]] && command -v python3 >/dev/null 2>&1 \
        && python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
        BASE_PY="python3"
    fi
    if [[ -z "$BASE_PY" ]]; then
        echo "[tts-native] ERROR: Python >=3.11 is required but was not found." >&2
        echo "[tts-native]        Install it (e.g. 'brew install python@3.11') and retry." >&2
        exit 1
    fi
    echo "[tts-native] creating venv at $VENV using $BASE_PY ($("$BASE_PY" --version 2>&1))"
    "$BASE_PY" -m venv "$VENV"
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
