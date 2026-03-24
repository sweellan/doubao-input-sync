#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ARCHIVE_IDLE_SECONDS_VALUE="${ARCHIVE_IDLE_SECONDS:-2.4}"

cd "$PROJECT_ROOT"
python3 app/server.py --archive-idle-seconds "$ARCHIVE_IDLE_SECONDS_VALUE" "$@"
