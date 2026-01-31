#!/bin/bash
set -a
source "$(dirname "$0")/.env"
set +a

# Activate venv if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Install jarvis-log-client from local path
pip install -q -e ../jarvis-log-client 2>/dev/null || echo "Note: jarvis-log-client not found, remote logging disabled"

uvicorn app.main:app --host 0.0.0.0 --port ${TTS_PORT:-8009} --reload
