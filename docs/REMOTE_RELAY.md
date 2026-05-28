# Remote Relay Notes

Use this mode when the phone talks to a relay that is not running on the Mac, and the Mac only needs to consume the settled text and paste it into the active app.

## Topology

```text
Phone browser
  -> remote relay input page
Remote relay
  -> public HTTPS tunnel, private Tailscale URL, or your own reverse proxy
Local macOS helper
  -> watches the remote room
  -> copies or pastes settled archive items into the active desktop app
```

The Mac does not need to start a local relay in this mode. It only needs a reachable `SERVER_URL`.

## Start The Helper

```bash
cd <repo-root>
SERVER_URL="https://<your-host>/doubao" \
ROOM_ID="<your-room>" \
MODE="paste" \
./scripts/run_autopaste_local.sh
```

For a safer first run, use clipboard mode and stop after one fresh archive:

```bash
cd <repo-root>
SERVER_URL="https://<your-host>/doubao" \
ROOM_ID="<your-room>" \
MODE="clipboard" \
./scripts/run_autopaste_local.sh --stop-after-updates 1
```

The helper starts with `skip-existing` behavior by default, so it ignores old archive items already present when the helper starts.

## Transport Choice

The helper defaults to stream mode:

```bash
TRANSPORT=stream ./scripts/run_autopaste_local.sh
```

Stream mode uses the relay SSE feed and is usually faster than polling. If your tunnel or proxy breaks long-lived responses, switch to polling:

```bash
TRANSPORT=poll ./scripts/run_autopaste_local.sh
```

## Fixed DNS Or CDN Workarounds

If your hostname sometimes resolves to a slow or broken edge, you can pass curl `--resolve` entries:

```bash
CURL_RESOLVE="<host>:443:<ip-address>" \
SERVER_URL="https://<host>/doubao" \
ROOM_ID="<your-room>" \
./scripts/run_autopaste_local.sh
```

Multiple entries can be comma-separated:

```bash
CURL_RESOLVE="<host>:443:<ip1>,<host>:443:<ip2>" ./scripts/run_autopaste_local.sh
```

This is optional. Most users should not need it.

## Persistent macOS Helper

For a LaunchAgent:

```bash
SERVER_URL="https://<your-host>/doubao" \
ROOM_ID="<your-room>" \
MODE="paste" \
TRANSPORT="stream" \
./scripts/install_launch_agent.sh
```

Useful commands:

```bash
./scripts/launch_agent_status.sh
tail -f ~/Library/Logs/doubao-input-sync/helper.stdout.log
tail -f ~/Library/Logs/doubao-input-sync/helper.stderr.log
./scripts/uninstall_launch_agent.sh
```

## What To Check When Paste Fails

Separate the failure domains:

- relay reachability: `curl "$SERVER_URL/api/ping"` should return JSON
- helper consumption: `helper.stdout.log` should show `status=updated` records
- paste execution: macOS Accessibility permission must be granted to Terminal, Codex, or whichever app runs the helper
- focus: the target desktop input must be active when the fresh archive arrives

If remote pulling works but nothing lands in the target app, the remaining issue is usually local macOS paste permission or app focus, not relay networking.
