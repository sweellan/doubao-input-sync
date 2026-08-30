#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

SERVER_URL="${SERVER_URL:-https://openclaw.ciaobella.cc/doubao}"
ROOM_ID="${ROOM_ID:-doubao}"
TRIGGER="${TRIGGER:-archive}"
REQUEST_TIMEOUT_SECONDS="${REQUEST_TIMEOUT_SECONDS:-12}"
STREAM_MAX_TIME_SECONDS="${STREAM_MAX_TIME_SECONDS:-90}"
INTERVAL_SECONDS="${INTERVAL_SECONDS:-0.25}"
CURL_RESOLVE="${CURL_RESOLVE:-openclaw.ciaobella.cc:443:172.67.208.237}"
TRANSPORT="${TRANSPORT:-stream}"

if [[ "$SERVER_URL" == https://openclaw.ciaobella.cc/doubao* ]]; then
  CF_ACCESS_CLIENT_ID="${CF_ACCESS_CLIENT_ID:-$(/usr/bin/security find-generic-password -a macbook -s doubao-input-sync-cloudflare-client-id -w)}"
  CF_ACCESS_CLIENT_SECRET="${CF_ACCESS_CLIENT_SECRET:-$(/usr/bin/security find-generic-password -a macbook -s doubao-input-sync-cloudflare-client-secret -w)}"
  if [[ -z "$CF_ACCESS_CLIENT_ID" || -z "$CF_ACCESS_CLIENT_SECRET" ]]; then
    echo "Missing Cloudflare Access credentials in macOS Keychain" >&2
    exit 1
  fi
  export CF_ACCESS_CLIENT_ID CF_ACCESS_CLIENT_SECRET
fi

cd "$PROJECT_ROOT"

echo "Starting foreground paste helper"
echo "server_url=${SERVER_URL}"
echo "room_id=${ROOM_ID}"
echo "trigger=${TRIGGER}"
echo "request_timeout_seconds=${REQUEST_TIMEOUT_SECONDS}"
echo "stream_max_time_seconds=${STREAM_MAX_TIME_SECONDS}"
echo "interval_seconds=${INTERVAL_SECONDS}"
echo "curl_resolve=${CURL_RESOLVE}"
echo "transport=${TRANSPORT}"
echo "mode=paste"
if [[ -n "${CF_ACCESS_CLIENT_ID:-}" ]]; then
  echo "cloudflare_access=service_token"
fi

helper_args=(
  --server-url "$SERVER_URL" \
  --room-id "$ROOM_ID" \
  --interval-seconds "$INTERVAL_SECONDS" \
  --mode paste \
  --trigger "$TRIGGER" \
  --transport "$TRANSPORT" \
  --request-timeout-seconds "$REQUEST_TIMEOUT_SECONDS" \
  --stream-max-time-seconds "$STREAM_MAX_TIME_SECONDS"
)

if [[ -n "$CURL_RESOLVE" ]]; then
  helper_args+=(--curl-resolve "$CURL_RESOLVE")
fi

exec /usr/bin/python3 scripts/mac_paste_helper.py "${helper_args[@]}"
