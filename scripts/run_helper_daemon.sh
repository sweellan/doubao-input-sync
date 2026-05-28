#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

CONFIG_DIR="${HOME}/.config/doubao-input-sync"
CONFIG_FILE="${CONFIG_DIR}/helper.env"

if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "Missing config file: $CONFIG_FILE" >&2
  exit 1
fi

set -a
source "$CONFIG_FILE"
set +a

SERVER_URL="${SERVER_URL:?SERVER_URL is required in helper.env}"
ROOM_ID="${ROOM_ID:?ROOM_ID is required in helper.env}"
MODE="${MODE:-paste}"
TRIGGER="${TRIGGER:-archive}"
REQUEST_TIMEOUT_SECONDS="${REQUEST_TIMEOUT_SECONDS:-12}"
TRANSPORT="${TRANSPORT:-stream}"
CURL_RESOLVE="${CURL_RESOLVE:-}"

cd "$PROJECT_ROOT"

helper_args=(
  --server-url "$SERVER_URL"
  --room-id "$ROOM_ID"
  --mode "$MODE"
  --trigger "$TRIGGER"
  --transport "$TRANSPORT"
  --request-timeout-seconds "$REQUEST_TIMEOUT_SECONDS"
)

if [[ -n "$CURL_RESOLVE" ]]; then
  helper_args+=(--curl-resolve "$CURL_RESOLVE")
fi

exec /usr/bin/python3 scripts/mac_paste_helper.py "${helper_args[@]}"
