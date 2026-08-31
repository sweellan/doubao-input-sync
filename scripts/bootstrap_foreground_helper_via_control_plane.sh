#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUNTIME_ROOT="${DOUBAO_CONTROL_PLANE_RUNTIME_ROOT:-${PROJECT_ROOT}/__sys/automation/doubao_input_sync_control_plane/runtime}"
JOB_ID="${DOUBAO_CONTROL_PLANE_JOB_ID:-doubao-foreground-paste-helper}"
HOST="${DOUBAO_CONTROL_PLANE_HOST:-127.0.0.1}"
PORT="${DOUBAO_CONTROL_PLANE_PORT:-18767}"
WAIT_SECONDS="${DOUBAO_CONTROL_PLANE_WAIT_SECONDS:-90}"
POLL_SECONDS="${DOUBAO_CONTROL_PLANE_POLL_SECONDS:-2}"
TRIGGER_SCRIPT="${DOUBAO_CONTROL_PLANE_TRIGGER_SCRIPT:-/Users/yangchao/.codex/skills/codex-desktop-control-plane/scripts/trigger_control_plane_job.py}"

classify_status() {
  /usr/bin/curl -fsS --max-time 5 "http://${HOST}:${PORT}/api/status" 2>/dev/null \
    | /usr/bin/python3 -c '
import json
import os
import sys

expected_root = os.path.realpath(sys.argv[1])
job_id = sys.argv[2]
payload = json.load(sys.stdin)
actual_root = os.path.realpath(str(payload.get("root") or ""))
if actual_root != expected_root:
    print("wrong_root")
    raise SystemExit(0)
for job in payload.get("jobs") or []:
    if job.get("id") != job_id:
        continue
    health = (job.get("health") or {}).get("status")
    if job.get("running") and health == "passed":
        print("healthy")
    elif job.get("running"):
        print("running_unhealthy")
    else:
        print("needs_trigger")
    raise SystemExit(0)
print("job_missing")
' "$RUNTIME_ROOT" "$JOB_ID"
}

deadline=$(( SECONDS + WAIT_SECONDS ))
classification="dashboard_not_ready"
while (( SECONDS < deadline )); do
  classification="$(classify_status || print -r -- dashboard_not_ready)"
  case "$classification" in
    healthy)
      print -r -- "{\"status\":\"already_healthy\",\"job_id\":\"${JOB_ID}\",\"token_source\":\"macos_keychain_via_formal_wrapper\"}"
      exit 0
      ;;
    needs_trigger)
      break
      ;;
    running_unhealthy|dashboard_not_ready)
      /bin/sleep "$POLL_SECONDS"
      ;;
    wrong_root|job_missing)
      print -u2 -r -- "Doubao helper warmup refused: ${classification}"
      exit 1
      ;;
    *)
      print -u2 -r -- "Doubao helper warmup received unknown status: ${classification}"
      exit 1
      ;;
  esac
done

if [[ "$classification" != "needs_trigger" ]]; then
  print -u2 -r -- "Doubao helper warmup timed out waiting for a triggerable control-plane job: ${classification}"
  exit 1
fi

if [[ ! -f "$TRIGGER_SCRIPT" ]]; then
  print -u2 -r -- "Doubao helper warmup trigger script is missing: ${TRIGGER_SCRIPT}"
  exit 1
fi

/usr/bin/python3 "$TRIGGER_SCRIPT" \
  --root "$RUNTIME_ROOT" \
  --job "$JOB_ID" \
  --host "$HOST" \
  --port "$PORT" \
  --timeout 10

deadline=$(( SECONDS + WAIT_SECONDS ))
while (( SECONDS < deadline )); do
  classification="$(classify_status || print -r -- dashboard_not_ready)"
  if [[ "$classification" == "healthy" ]]; then
    print -r -- "{\"status\":\"triggered_and_healthy\",\"job_id\":\"${JOB_ID}\",\"token_source\":\"macos_keychain_via_formal_wrapper\"}"
    exit 0
  fi
  if [[ "$classification" == "wrong_root" || "$classification" == "job_missing" ]]; then
    print -u2 -r -- "Doubao helper warmup failed after trigger: ${classification}"
    exit 1
  fi
  /bin/sleep "$POLL_SECONDS"
done

print -u2 -r -- "Doubao helper warmup trigger was accepted but helper did not become healthy"
exit 1
