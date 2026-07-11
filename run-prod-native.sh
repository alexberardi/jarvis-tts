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

# Native macOS service env: the Docker compose injects service-discovery URLs +
# DATABASE_URL per container; native services must derive them from the shared
# .env. config-service + postgres are published on the host (localhost).
#
# Service discovery: without JARVIS_CONFIG_URL the service can't find jarvis-auth.
if [[ -z "${JARVIS_CONFIG_URL:-}" ]]; then
    export JARVIS_CONFIG_URL="http://localhost:${CONFIG_SERVICE_PORT:-7700}"
fi

# DB: postgres runs in Docker, published on the host at 127.0.0.1:${POSTGRES_PORT}.
if [[ -z "${DATABASE_URL:-}" ]]; then
    export DATABASE_URL="postgresql+psycopg2://${DB_USER:-jarvis}:${POSTGRES_PASSWORD:-}@127.0.0.1:${POSTGRES_PORT:-5432}/jarvis_tts"
fi
if [[ -z "${MIGRATIONS_DATABASE_URL:-}" ]]; then
    export MIGRATIONS_DATABASE_URL="$DATABASE_URL"
fi

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

# Piper voice model. The Dockerfile bakes this in at build time (it's always the
# fallback TTS provider), but a native git clone has no image layer to inherit it
# from — so fetch it here when absent. Public model; idempotent across restarts.
# Download the .onnx LAST so its presence is a reliable "fully downloaded" guard
# (a mid-download failure aborts under `set -e` before the guard file exists).
PIPER_DIR="$ROOT/app/models"
PIPER_ONNX="$PIPER_DIR/en_GB-alan-low.onnx"
PIPER_BASE="https://huggingface.co/csukuangfj/vits-piper-en_GB-alan-low/resolve/main"
if [[ ! -f "$PIPER_ONNX" ]]; then
    echo "[tts-native] downloading Piper voice (en_GB-alan-low)"
    mkdir -p "$PIPER_DIR"
    curl -fsSL "$PIPER_BASE/en_GB-alan-low.onnx.json" -o "$PIPER_ONNX.json"
    curl -fsSL "$PIPER_BASE/en_GB-alan-low.onnx" -o "$PIPER_ONNX"
fi

echo "[tts-native] running alembic migrations"
"$PY" -m alembic upgrade head

echo "[tts-native] starting uvicorn on ${SERVER_HOST}:${TTS_PORT}"
exec "$VENV/bin/uvicorn" app.main:app --host "$SERVER_HOST" --port "$TTS_PORT"
