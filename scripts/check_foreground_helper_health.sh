#!/bin/zsh
set -euo pipefail

SERVER_URL="${SERVER_URL:-https://openclaw.ciaobella.cc/doubao}"
ROOM_ID="${ROOM_ID:-doubao}"

client_id="$(/usr/bin/security find-generic-password -a macbook -s doubao-input-sync-cloudflare-client-id -w)"
client_secret="$(/usr/bin/security find-generic-password -a macbook -s doubao-input-sync-cloudflare-client-secret -w)"

{
  print -r -- "header = \"CF-Access-Client-Id: ${client_id}\""
  print -r -- "header = \"CF-Access-Client-Secret: ${client_secret}\""
} | /usr/bin/curl --config - -fsS --location --max-redirs 0 --http1.1 \
  --max-time 6 --connect-timeout 4 \
  -H 'ngrok-skip-browser-warning: 1' \
  -A 'doubao-input-sync-healthcheck/1.0' \
  "${SERVER_URL}/api/helper-state?room_id=${ROOM_ID}" \
  | /usr/bin/python3 -c 'import json,sys; payload=json.load(sys.stdin); assert payload.get("room_id") == sys.argv[1]; assert isinstance(payload.get("version"), int)' "$ROOM_ID"
