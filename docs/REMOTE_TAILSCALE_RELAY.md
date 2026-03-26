# Remote Tailscale Relay Notes

This note captures the working setup where:

- the phone keeps talking to a remote relay
- the desktop helper runs on macOS
- the macOS helper reads state through a Tailscale-only proxy
- the final text is pasted into the current desktop cursor position

## Current Working Topology

```text
Phone browser
  -> remote relay input page
Remote Linux relay
  -> 127.0.0.1:8765
Remote Tailscale-only proxy
  -> 100.69.170.35:18765/doubao
Local macOS helper
  -> polls remote state through Tailscale
  -> pastes settled archive items into the active desktop app
```

## Observed Status

- Remote relay itself is healthy
- Tailscale proxy is reachable from the Mac
- `curl` against the remote `/api/state` works reliably
- Python `urllib` against the same proxy path could intermittently receive `502 Bad Gateway`
- To make the Mac helper robust in this mode, the helper now prefers `curl` for remote state fetch and falls back to `urllib` only when needed

## Important Consequence

If you use the remote Tailscale relay mode, the Mac helper should be started with a remote `SERVER_URL`, not with the default local relay URL.

## macOS Command

```bash
cd <repo-root>
SERVER_URL="http://100.69.170.35:18765/doubao" \
ROOM_ID="testroom" \
MODE="paste" \
./scripts/run_autopaste_local.sh
```

For a safer verification run:

```bash
cd <repo-root>
SERVER_URL="http://100.69.170.35:18765/doubao" \
ROOM_ID="testroom" \
MODE="clipboard" \
./scripts/run_autopaste_local.sh --stop-after-updates 1
```

## What The Mac Does Not Need In This Mode

- It does not need to start a local relay
- It does not need to expose its own tunnel
- It does not need the desktop monitor page open in order to auto-paste

The only requirement is:

- keep the target input focused on macOS

## Why Old Text Should Not Immediately Re-Paste

The helper starts with `skip-existing` behavior by default.
That means:

- existing archive entries are treated as baseline
- only newly created archive items after helper startup will trigger paste

So the helper should not replay stale history on startup.

## Remote Codex Handoff Message

Below is a short status note that can be sent to the remote Codex worker:

```text
Mac-side validation is now aligned with the remote Tailscale relay setup.

Confirmed on the Mac side:
- Tailscale proxy ping works: http://100.69.170.35:18765/doubao/api/ping
- Direct curl to /api/state works
- The main incompatibility was helper-side urllib polling receiving intermittent 502 Bad Gateway on the proxy path, while curl remained stable

Local fix applied:
- mac_paste_helper.py now prefers curl for remote state fetch and falls back to urllib only as a backup
- run_autopaste_local.sh now respects SERVER_URL override cleanly, so the Mac can point to the remote relay without spawning a local relay
- helper startup ignores existing archive items by default and only reacts to newly created archive items

Current intended Mac command:
cd <repo-root>
SERVER_URL="http://100.69.170.35:18765/doubao" \
ROOM_ID="testroom" \
MODE="paste" \
./scripts/run_autopaste_local.sh

At this point, if more issues appear, they are more likely to be around remote relay stability, room workflow, or macOS paste permissions rather than repo path or helper bootstrap.
```
