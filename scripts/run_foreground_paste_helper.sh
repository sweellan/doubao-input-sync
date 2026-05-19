#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

SERVER_URL="${SERVER_URL:-https://versicolor-charla-nonmutinously.ngrok-free.dev/doubao}"
ROOM_ID="${ROOM_ID:-doubao}"
TRIGGER="${TRIGGER:-archive}"
REQUEST_TIMEOUT_SECONDS="${REQUEST_TIMEOUT_SECONDS:-4}"
INTERVAL_SECONDS="${INTERVAL_SECONDS:-0.25}"
CURL_RESOLVE="${CURL_RESOLVE:-versicolor-charla-nonmutinously.ngrok-free.dev:443:13.56.217.111,versicolor-charla-nonmutinously.ngrok-free.dev:443:50.18.8.146,versicolor-charla-nonmutinously.ngrok-free.dev:443:52.8.87.87,versicolor-charla-nonmutinously.ngrok-free.dev:443:54.193.184.75,versicolor-charla-nonmutinously.ngrok-free.dev:443:184.72.44.51,versicolor-charla-nonmutinously.ngrok-free.dev:443:54.183.107.205}"

cd "$PROJECT_ROOT"

echo "Starting foreground paste helper"
echo "server_url=${SERVER_URL}"
echo "room_id=${ROOM_ID}"
echo "trigger=${TRIGGER}"
echo "request_timeout_seconds=${REQUEST_TIMEOUT_SECONDS}"
echo "interval_seconds=${INTERVAL_SECONDS}"
echo "curl_resolve=${CURL_RESOLVE}"
echo "mode=paste"

exec /usr/bin/python3 scripts/mac_paste_helper.py \
  --server-url "$SERVER_URL" \
  --room-id "$ROOM_ID" \
  --interval-seconds "$INTERVAL_SECONDS" \
  --mode paste \
  --trigger "$TRIGGER" \
  --request-timeout-seconds "$REQUEST_TIMEOUT_SECONDS" \
  --curl-resolve "$CURL_RESOLVE"
