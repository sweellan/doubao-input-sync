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

cd "$PROJECT_ROOT"

while true; do
  printf '[%s] Starting helper supervisor loop\n' "$(date '+%Y-%m-%d %H:%M:%S')"
  ./scripts/run_helper_daemon.sh
  exit_code=$?
  printf '[%s] Helper exited with code %s, restarting in 2s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$exit_code"
  sleep 2
done
