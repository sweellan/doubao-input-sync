#!/bin/zsh
set -euo pipefail

LABEL="com.sweellan.doubao-input-sync.helper"

echo "LaunchAgent label: ${LABEL}"
launchctl print "gui/$(id -u)/${LABEL}" 2>/dev/null || {
  echo "LaunchAgent is not loaded."
  exit 1
}
