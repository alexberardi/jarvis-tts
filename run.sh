#!/bin/bash

# Load environment variables from .env
set -a
source "$(dirname "$0")/.env"
set +a

# Default port if not set
TTS_PORT="${TTS_PORT:-8009}"

docker run --rm -it \
    --init \
    -p "${TTS_PORT}:${TTS_PORT}" \
    -e TTS_PORT="${TTS_PORT}" \
    --env-file .env \
    jarvis-tts
