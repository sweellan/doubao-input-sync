#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEFAULT_ROOM_ID="$(python3 - <<'PY'
import secrets
print(f"pair-{secrets.token_hex(3)}", end="")
PY
)"

ROOM_ID="${ROOM_ID:-$DEFAULT_ROOM_ID}"
PORT="${PORT:-8765}"
MODE="${MODE:-paste}"
TRIGGER="${TRIGGER:-archive}"
ARCHIVE_IDLE_SECONDS_VALUE="${ARCHIVE_IDLE_SECONDS:-5.0}"

SERVER_URL="http://127.0.0.1:${PORT}"
STARTED_SERVER=0
SERVER_PID=""

cleanup() {
  if [[ "$STARTED_SERVER" == "1" && -n "$SERVER_PID" ]]; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
    wait "$SERVER_PID" >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT INT TERM

cd "$PROJECT_ROOT"

if ! curl -fsS "${SERVER_URL}/api/ping" >/dev/null 2>&1; then
  echo "No relay server detected on ${SERVER_URL}, starting one locally..."
  python3 app/server.py --host 0.0.0.0 --port "$PORT" --default-room "$ROOM_ID" --archive-idle-seconds "$ARCHIVE_IDLE_SECONDS_VALUE" &
  SERVER_PID=$!
  STARTED_SERVER=1
  for _ in {1..40}; do
    if curl -fsS "${SERVER_URL}/api/ping" >/dev/null 2>&1; then
      break
    fi
    sleep 0.25
  done
fi

if ! curl -fsS "${SERVER_URL}/api/ping" >/dev/null 2>&1; then
  echo "Relay server failed to start on ${SERVER_URL}" >&2
  exit 1
fi

echo "Auto paste helper is watching ${SERVER_URL} room=${ROOM_ID} mode=${MODE} trigger=${TRIGGER} archive_idle_seconds=${ARCHIVE_IDLE_SECONDS_VALUE}"
echo "Phone page: ${SERVER_URL/127.0.0.1/$(python3 - <<'PY'
import socket
s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    s.connect(("8.8.8.8",80))
    print(s.getsockname()[0], end="")
except OSError:
    print("127.0.0.1", end="")
finally:
    s.close()
PY
)}/mobile/${ROOM_ID}"

python3 scripts/mac_paste_helper.py \
  --server-url "$SERVER_URL" \
  --room-id "$ROOM_ID" \
  --mode "$MODE" \
  --trigger "$TRIGGER" \
  "${@:1}"
