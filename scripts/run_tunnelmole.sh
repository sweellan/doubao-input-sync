#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PORT="${PORT:-18766}"

cd "$PROJECT_ROOT"

if ! curl -fsS "http://127.0.0.1:${PORT}/api/ping" >/dev/null 2>&1; then
  echo "No relay server detected on http://127.0.0.1:${PORT}. Start it first with ./scripts/run_local_server.sh or ./scripts/run_autopaste_local.sh" >&2
  exit 1
fi

npx tunnelmole "$PORT"
