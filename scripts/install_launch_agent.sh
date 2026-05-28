#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

LABEL="com.sweellan.doubao-input-sync.helper"
PLIST_PATH="${HOME}/Library/LaunchAgents/${LABEL}.plist"
CONFIG_DIR="${HOME}/.config/doubao-input-sync"
CONFIG_FILE="${CONFIG_DIR}/helper.env"
LOG_DIR="${HOME}/Library/Logs/doubao-input-sync"

SERVER_URL="${SERVER_URL:-}"
ROOM_ID="${ROOM_ID:-}"
MODE="${MODE:-paste}"
TRIGGER="${TRIGGER:-archive}"
REQUEST_TIMEOUT_SECONDS="${REQUEST_TIMEOUT_SECONDS:-12}"
TRANSPORT="${TRANSPORT:-stream}"
CURL_RESOLVE="${CURL_RESOLVE:-}"

if [[ -z "$SERVER_URL" || -z "$ROOM_ID" ]]; then
  echo "Usage: SERVER_URL=<url> ROOM_ID=<room> [MODE=paste] [TRIGGER=archive] [TRANSPORT=stream] [CURL_RESOLVE=host:443:ip] ./scripts/install_launch_agent.sh" >&2
  exit 1
fi

mkdir -p "${HOME}/Library/LaunchAgents" "$CONFIG_DIR" "$LOG_DIR"

cat > "$CONFIG_FILE" <<EOF
SERVER_URL="${SERVER_URL}"
ROOM_ID="${ROOM_ID}"
MODE="${MODE}"
TRIGGER="${TRIGGER}"
REQUEST_TIMEOUT_SECONDS="${REQUEST_TIMEOUT_SECONDS}"
TRANSPORT="${TRANSPORT}"
CURL_RESOLVE="${CURL_RESOLVE}"
EOF

cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>${PROJECT_ROOT}/scripts/run_helper_daemon.sh</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${PROJECT_ROOT}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${LOG_DIR}/helper.stdout.log</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/helper.stderr.log</string>
  <key>ProcessType</key>
  <string>Interactive</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)" "$PLIST_PATH" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_PATH"
launchctl enable "gui/$(id -u)/${LABEL}" >/dev/null 2>&1 || true
launchctl kickstart -k "gui/$(id -u)/${LABEL}"

echo "Installed launch agent: ${LABEL}"
echo "Plist: ${PLIST_PATH}"
echo "Config: ${CONFIG_FILE}"
echo "Logs: ${LOG_DIR}"
