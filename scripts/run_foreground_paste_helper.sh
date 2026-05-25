#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

SERVER_URL="${SERVER_URL:-https://openclaw.ciaobella.cc/doubao}"
ROOM_ID="${ROOM_ID:-doubao}"
TRIGGER="${TRIGGER:-archive}"
REQUEST_TIMEOUT_SECONDS="${REQUEST_TIMEOUT_SECONDS:-12}"
INTERVAL_SECONDS="${INTERVAL_SECONDS:-0.25}"
CURL_RESOLVE="${CURL_RESOLVE:-openclaw.ciaobella.cc:443:104.21.61.99,openclaw.ciaobella.cc:443:172.67.208.237}"
TRANSPORT="${TRANSPORT:-stream}"

cd "$PROJECT_ROOT"

echo "Starting foreground paste helper"
echo "server_url=${SERVER_URL}"
echo "room_id=${ROOM_ID}"
echo "trigger=${TRIGGER}"
echo "request_timeout_seconds=${REQUEST_TIMEOUT_SECONDS}"
echo "interval_seconds=${INTERVAL_SECONDS}"
echo "curl_resolve=${CURL_RESOLVE}"
echo "transport=${TRANSPORT}"
echo "mode=paste"

helper_args=(
  --server-url "$SERVER_URL" \
  --room-id "$ROOM_ID" \
  --interval-seconds "$INTERVAL_SECONDS" \
  --mode paste \
  --trigger "$TRIGGER" \
  --transport "$TRANSPORT" \
  --request-timeout-seconds "$REQUEST_TIMEOUT_SECONDS"
)

if [[ -n "$CURL_RESOLVE" ]]; then
  helper_args+=(--curl-resolve "$CURL_RESOLVE")
fi

exec /usr/bin/python3 scripts/mac_paste_helper.py "${helper_args[@]}"
