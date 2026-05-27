#!/bin/bash
# Development server.
# Usage:
#   ./run.sh                  # local mode (default) — start the server
#   ./run.sh --setup          # local mode — install deps only, then exit
#   ./run.sh --docker         # docker mode — start the container
#   ./run.sh --docker --rebuild

set -e
cd "$(dirname "$0")"

SETUP_ONLY="false"
DOCKER_MODE="false"
DOCKER_REBUILD_FLAG=""
for arg in "$@"; do
    case "$arg" in
        --docker)  DOCKER_MODE="true" ;;
        --setup)   SETUP_ONLY="true" ;;
        --rebuild) DOCKER_REBUILD_FLAG="--rebuild" ;;
        --build)   DOCKER_REBUILD_FLAG="--build" ;;
    esac
done

if [[ "$DOCKER_MODE" == "true" ]]; then
    BUILD_FLAGS=""
    if [[ "$DOCKER_REBUILD_FLAG" == "--rebuild" ]]; then
        docker compose --env-file .env -f docker-compose.dev.yaml build --no-cache
        BUILD_FLAGS="--build"
    elif [[ "$DOCKER_REBUILD_FLAG" == "--build" ]]; then
        BUILD_FLAGS="--build"
    fi
    docker compose --env-file .env -f docker-compose.dev.yaml up $BUILD_FLAGS -d
    exit 0
fi

# ── Local mode ────────────────────────────────────────────────────────────
# Required for the macOS local-override path in the top-level `jarvis`
# script — Docker on Mac can't reach Metal, so Kokoro with mps device only
# works when jarvis-tts runs natively against the host's torch.

# Create venv if missing
if [ ! -d ".venv" ]; then
    echo "🐍 Creating venv (.venv)…"
    python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

# Load env (.env is optional during --setup)
set -a
[ -f .env ] && source .env
set +a

# Install jarvis client libraries (idempotent — install-clients.sh is
# version-pinned and only re-installs on tag changes)
JARVIS_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "${JARVIS_ROOT}/scripts/install-clients.sh"
install_jarvis_clients log-client config-client auth-client settings-client

# Install project + kokoro extras (kokoro pulls in torch, which provides
# the mps backend on Apple Silicon). pip skips already-satisfied deps so
# this is cheap on warm runs.
pip install -q -e ".[kokoro]"

if [[ "$SETUP_ONLY" == "true" ]]; then
    echo "✅ Setup complete — dependencies installed"
    exit 0
fi

uvicorn app.main:app --host 0.0.0.0 --port "${TTS_PORT:-7707}" --reload
