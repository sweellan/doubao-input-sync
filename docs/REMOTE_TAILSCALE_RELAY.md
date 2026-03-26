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

## Known Issues

### Mobile auto-clear can still fail intermittently

Observed behavior:

- the phone page can archive successfully
- sync to the remote relay can still succeed
- but the mobile textarea may occasionally fail to clear itself afterward

Current working assumption:

- this is likely related to mobile browser lifecycle or event-delivery behavior
- it is not yet pinned down to a single root cause

Current workaround:

- use the manual `清空输入框` button if the text stays visible
- if a room becomes behaviorally inconsistent, switch to a fresh room id

This is a known issue for now and should not be treated as proof that the relay itself is down.

### Mac helper still needs explicit observability

When the Mac helper is running against a remote relay, there are two separate things to monitor:

- whether it is successfully pulling state
- whether it is successfully pasting into the focused macOS app

These can fail independently, so treat them as separate checkpoints.

## Recommended Monitoring

### Quick pull-path verification

Use a clipboard-only single-update run first:

```bash
cd <repo-root>
SERVER_URL="http://100.69.170.35:18765/doubao" \
ROOM_ID="testroom" \
MODE="clipboard" \
./scripts/run_autopaste_local.sh --stop-after-updates 1
```

If this succeeds, the helper is able to read the remote relay and process a fresh archive item.

### LaunchAgent status and logs

If the helper is installed as a LaunchAgent:

```bash
cd <repo-root>
./scripts/launch_agent_status.sh
tail -f ~/Library/Logs/doubao-input-sync/helper.stdout.log
tail -f ~/Library/Logs/doubao-input-sync/helper.stderr.log
```

Recommended interpretation:

- `stdout` answers whether new archive items are being consumed
- `stderr` is where transport or runtime failures are most likely to show up

### tmux-supervised helper

If the helper is running under tmux:

```bash
cd <repo-root>
./scripts/start_tmux_helper.sh
tmux attach -t doubao-paste
```

This is useful when you want a persistent foreground view of helper activity without relying on the LaunchAgent logs.

### Paste-path verification

If remote pulling looks healthy but text still does not land in the target app, the remaining failure domain is usually local macOS paste execution:

- Accessibility permission for the host app
- current focused input not actually being active
- target app rejecting synthetic paste at that moment

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
