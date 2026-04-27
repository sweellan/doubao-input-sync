#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

SERVER_URL="${SERVER_URL:-http://100.69.170.35:18765/doubao}"
ROOM_ID="${ROOM_ID:-doubao}"
TRIGGER="${TRIGGER:-archive}"
REQUEST_TIMEOUT_SECONDS="${REQUEST_TIMEOUT_SECONDS:-45}"

cd "$PROJECT_ROOT"

echo "Starting foreground paste helper"
echo "server_url=${SERVER_URL}"
echo "room_id=${ROOM_ID}"
echo "trigger=${TRIGGER}"
echo "request_timeout_seconds=${REQUEST_TIMEOUT_SECONDS}"
echo "mode=paste"

exec /usr/bin/python3 scripts/mac_paste_helper.py \
  --server-url "$SERVER_URL" \
  --room-id "$ROOM_ID" \
  --mode paste \
  --trigger "$TRIGGER" \
  --request-timeout-seconds "$REQUEST_TIMEOUT_SECONDS"
