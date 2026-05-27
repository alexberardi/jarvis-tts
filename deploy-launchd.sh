#!/usr/bin/env bash
# (Re)deploy the launchd agent that runs jarvis-tts natively on login.
#
# Native mode on macOS lets Kokoro use MPS (Apple Silicon GPU) instead of CPU.
# Set `tts.kokoro_device=mps` in settings to take advantage of it.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
ROOT="$SCRIPT_DIR"

LABEL="${LAUNCHD_LABEL:-com.jarvis.tts}"
PORT="${TTS_PORT:-7707}"
ENV_FILE_PATH="${ENV_FILE_PATH:-$HOME/.jarvis/compose/.env}"

PLIST_TEMPLATE="$ROOT/scripts/launchd/$LABEL.plist"
AGENTS_DIR="$HOME/Library/LaunchAgents"
TARGET_PLIST="$AGENTS_DIR/$LABEL.plist"
LOG_DIR="$HOME/Library/Logs/jarvis-tts"

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "❌ deploy-launchd.sh only supports macOS (detected $(uname -s))"
    exit 1
fi

if [[ ! -f "$PLIST_TEMPLATE" ]]; then
    echo "❌ launchd template not found at $PLIST_TEMPLATE"
    exit 1
fi

mkdir -p "$AGENTS_DIR" "$LOG_DIR"

sed -e "s#__ROOT__#$ROOT#g" \
    -e "s#__USER__#$USER#g" \
    -e "s#__PORT__#$PORT#g" \
    -e "s#__ENV_FILE__#$ENV_FILE_PATH#g" \
    "$PLIST_TEMPLATE" > "$TARGET_PLIST"

echo "📄 Installed launchd plist to $TARGET_PLIST"

echo "🔄 Reloading launchd service $LABEL..."
launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$TARGET_PLIST"
launchctl enable "gui/$(id -u)/$LABEL"
launchctl kickstart -k "gui/$(id -u)/$LABEL"

echo "✅ LaunchAgent ready. Check status with: launchctl print gui/$(id -u)/$LABEL"
echo "📜 Logs: $LOG_DIR/{out,err}.log"
