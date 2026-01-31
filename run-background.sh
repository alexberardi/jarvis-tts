#!/bin/bash

# Load environment variables from .env
set -a
source "$(dirname "$0")/.env"
set +a

# Default port if not set
TTS_PORT="${TTS_PORT:-8009}"

docker run -d \
    --init \
    --name jarvis-tts \
    --restart unless-stopped \
    -p "${TTS_PORT}:${TTS_PORT}" \
    -e TTS_PORT="${TTS_PORT}" \
    --env-file .env \
    jarvis-tts

echo "jarvis-tts running on port ${TTS_PORT}"
echo "Stop with: docker stop jarvis-tts"
echo "Logs: docker logs -f jarvis-tts"
