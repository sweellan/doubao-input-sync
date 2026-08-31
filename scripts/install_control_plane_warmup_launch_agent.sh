#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LABEL="com.yangchao.codex_desktop_control_plane_doubao_warmup"
SOURCE_PLIST="${PROJECT_ROOT}/launchd/${LABEL}.plist.template"
INSTALLED_PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
STATE_DIR="${PROJECT_ROOT}/__sys/automation/doubao_input_sync_control_plane/runtime/state"
DOMAIN="gui/$(id -u)"

/usr/bin/plutil -lint "$SOURCE_PLIST"
/bin/mkdir -p "${HOME}/Library/LaunchAgents" "$STATE_DIR"

/bin/launchctl bootout "${DOMAIN}/${LABEL}" >/dev/null 2>&1 || true
/usr/bin/install -m 0644 "$SOURCE_PLIST" "$INSTALLED_PLIST"
/usr/bin/plutil -replace ProgramArguments -json "[\"/bin/zsh\",\"${PROJECT_ROOT}/scripts/bootstrap_foreground_helper_via_control_plane.sh\"]" "$INSTALLED_PLIST"
/usr/bin/plutil -replace WorkingDirectory -string "$PROJECT_ROOT" "$INSTALLED_PLIST"
/usr/bin/plutil -replace StandardOutPath -string "${STATE_DIR}/helper_warmup.launchd.stdout.log" "$INSTALLED_PLIST"
/usr/bin/plutil -replace StandardErrorPath -string "${STATE_DIR}/helper_warmup.launchd.stderr.log" "$INSTALLED_PLIST"
/usr/bin/plutil -lint "$INSTALLED_PLIST"
/bin/launchctl bootstrap "$DOMAIN" "$INSTALLED_PLIST"
/bin/launchctl enable "${DOMAIN}/${LABEL}"
/bin/launchctl kickstart "${DOMAIN}/${LABEL}"

print -r -- "Installed one-shot Doubao helper warmup LaunchAgent: ${LABEL}"
print -r -- "Installed plist: ${INSTALLED_PLIST}"
print -r -- "The LaunchAgent triggers the formal persistent-Terminal job and stores no Cloudflare token values."
