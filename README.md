# Doubao Input Sync

Turn phone-side text input into desktop text insertion.

`Doubao Input Sync` is a tiny local relay that lets you type or paste a long block of text on your phone, either send it automatically after a quiet window or pause for as long as you need before sending manually, and optionally auto-paste the final text into the macOS or Windows app that currently owns the cursor.

This is an unofficial utility and is not affiliated with Doubao or its input method product team.

Friendly disclaimer: this repo was built as a practical personal tool, not as polished production software. I am not a professional developer, so installation and edge cases may still be a little rough 🙈. In practice, the easiest path is often to let an AI coding agent help you run or tweak it.

Chinese documentation: [README.zh-CN.md](README.zh-CN.md)

## Why This Exists

Some mobile-first input experiences are excellent, but the desktop version is missing or less convenient. This project does not try to reimplement the input method itself. It only bridges the result:

- phone input area
- local relay server
- desktop monitor page
- optional auto-paste to the current cursor position on macOS or Windows

## Features

- Two easy-to-switch rhythms: `Flow mode` auto-sends after a quiet window, while `Breathing mode` waits for an explicit send no matter how long you pause
- Auto-capture in Flow mode only after the text stops changing for about 2 seconds by default
- Drafts still sync in Breathing mode, and `Done — send` captures immediately when you are ready
- Random pairing code by default instead of a shared hard-coded room name
- Strong 1 phone + 1 desktop slot matching per room, with conflict warning
- Room-level theme colors shared by the phone and desktop pages
- Desktop history list with per-item copy actions
- Optional auto-paste to the active desktop input on macOS or Windows
- Zero Python dependencies beyond the standard library
- Temporary public testing via tunnel tools if phone and desktop are not on the same LAN
- Subtle visual flash when a settled batch is captured and synced
- Polling fallback when SSE reconnect is flaky over a public tunnel

## How It Works

```text
Phone browser
  -> POST /api/update
Local Python relay
  -> in-memory room state
  -> SSE updates to desktop page
  -> Flow mode: archive snapshot after idle window
  -> Breathing mode: archive immediately on explicit capture
macOS helper
  -> watches latest archive item
  -> copies or pastes into active app
Windows helper
  -> watches latest archive item
  -> writes Unicode clipboard text and can send Ctrl+V to the foreground cursor
```

## Repository Layout

```text
app/
  server.py          # local relay server
  static/            # mobile + desktop web UI
scripts/
  run_local_server.sh
  run_autopaste_local.sh
  run_tunnelmole.sh
  run_helper_daemon.sh
  install_launch_agent.sh
  uninstall_launch_agent.sh
  launch_agent_status.sh
  start_tmux_helper.sh
  stop_tmux_helper.sh
  mac_paste_helper.py
  windows_paste_helper.py
  run_windows_clipboard_helper.ps1
  run_windows_paste_helper.ps1
  smoke_test.py
docs/
  REMOTE_TAILSCALE_RELAY.md
  WINDOWS_HELPER_PLAN.md
```

## Quick Start

### 1. Start the local relay server

```bash
./scripts/run_local_server.sh
```

This starts the relay on `http://127.0.0.1:18766`.

### 2. Open the phone page

If your phone and desktop are on the same LAN:

```text
http://<your-desktop-lan-ip>:18766/mobile/doubao
```

If your phone is only on the public internet, use a tunnel:

```bash
./scripts/run_tunnelmole.sh
```

Then open the generated HTTPS URL plus `/mobile/doubao`.

### 3. Open the desktop page

```text
http://127.0.0.1:18766/pc/doubao
```

### 4. Optional: auto-paste into the current cursor position

macOS:

```bash
./scripts/run_autopaste_local.sh
```

Windows PowerShell:

```powershell
.\scripts\run_windows_paste_helper.ps1
```

Both commands watch the latest archived snapshot and paste it into the
currently focused desktop input. The macOS wrapper can start its local relay;
the Windows runner connects to the configured relay.

The Windows helper defaults to the public relay and the isolated
`doubao-win-test` room. Keep the intended input focused when the archive
arrives, and do not run clipboard and paste helpers for the same room at once.

## Choose An Input Rhythm

The phone editor has two mode buttons attached to it:

- `⚡ Flow mode` keeps the original behavior: a full quiet window sends the current text automatically.
- `🌿 Breathing mode` lets you pause to read, think, or breathe for as long as needed. Drafts remain synced, but nothing enters the archive or desktop helper until you press `Done — send`.

The current room keeps its mode while the relay stays alive. A relay restart safely defaults back to Flow mode. Switching back to Flow mode starts the normal quiet-window timer for the current draft.

## Stable Shared-Tunnel Deployment

If you already have a fixed tunnel hostname that is currently pointing at another local service, the most practical no-new-domain setup is:

```text
fixed public tunnel hostname
  -> local reverse proxy on the host machine
     -> /doubao/* -> Doubao Input Sync
     -> everything else -> your existing local service
```

This repo now supports subpath deployment, so you can run it under a prefix such as `/doubao` instead of taking over `/`.

Start the relay in subpath mode:

```bash
BASE_PATH=/doubao ./scripts/run_local_server.sh --host 127.0.0.1 --port 18766
```

Then put a local reverse proxy in front of both services. An example Caddy config is included at [`deploy/Caddyfile.ngrok-subpath.example`](deploy/Caddyfile.ngrok-subpath.example).

Example layout:

- existing local service stays on `127.0.0.1:18789`
- Doubao Input Sync runs on `127.0.0.1:18766` with `BASE_PATH=/doubao`
- Caddy listens on `127.0.0.1:18889`
- your fixed tunnel endpoint forwards to `127.0.0.1:18889`

In that setup:

- phone page: `https://<your-fixed-hostname>/doubao/mobile/<room>`
- PC page: `https://<your-fixed-hostname>/doubao/pc/<room>`

This is usually lower-maintenance than trying to find a second free long-lived public hostname.

## Main Commands

Start only the relay:

```bash
./scripts/run_local_server.sh
```

Start relay + auto-paste helper:

```bash
./scripts/run_autopaste_local.sh
```

By default this generates a random room id like `pair-a1b2c3` and prints the corresponding phone page URL.

Safe dry run:

```bash
MODE=clipboard ./scripts/run_autopaste_local.sh --dry-run
```

Expose the local relay through a temporary public tunnel:

```bash
./scripts/run_tunnelmole.sh
```

Run the smoke test:

```bash
python3 scripts/smoke_test.py --room-id smoke-room --output-json /tmp/doubao-smoke.json
```

Tune the settle window if your input method revises text in multiple passes:

```bash
ARCHIVE_IDLE_SECONDS=3.2 ./scripts/run_autopaste_local.sh
```

The mobile page also lets you change the capture wait time in the UI.
Flow mode is debounce-style, not interval-style: every new input resets the timer, and capture happens only after a full quiet window with no new changes. Breathing mode ignores this timer.

## Data Isolation

Clones do not conflict with each other by default.

Each local process keeps its own in-memory state, so separate users who clone and run the project on their own machines get fully isolated archives. Data only mixes when multiple clients intentionally talk to the same running relay server and use the same `room_id`.

The mobile page also includes an `Auto clear after archive` option, and it is enabled by default. Turn it off if you prefer to review text before clearing.

## Pairing Rules

Each room allows:

- one mobile slot
- one desktop slot

If another phone or another desktop page tries to take the same slot in the same room, the UI shows a conflict warning and asks the user to switch to a different room id.

## Keeping The Tunnel Alive

Temporary tunnels are convenient, but not especially durable.

The more stable long-running options are:

- `cloudflared tunnel` with a named tunnel plus macOS `launchd`
- `ngrok` with an authenticated account and a reserved endpoint
- your own small VPS or reverse proxy if you want full control

For quick demos, `tunnelmole` is still fine. For daily use, a named `cloudflared` tunnel would be the most practical next step.

## Remote Relay Mode

If the phone input page already lives on a remote Linux relay and your Mac only needs to consume that relay over Tailscale, see [docs/REMOTE_TAILSCALE_RELAY.md](docs/REMOTE_TAILSCALE_RELAY.md).

## Running Without An Open Terminal

If you start the helper directly from Terminal, that Terminal session must stay alive.

For a persistent macOS setup, install the user LaunchAgent once:

```bash
SERVER_URL="https://openclaw.ciaobella.cc/doubao" \
ROOM_ID="testroom" \
MODE="paste" \
./scripts/install_launch_agent.sh
```

Useful follow-up commands:

```bash
./scripts/launch_agent_status.sh
./scripts/uninstall_launch_agent.sh
```

If you prefer a foreground helper that still survives shell disconnects, you can use tmux instead:

```bash
./scripts/start_tmux_helper.sh
tmux attach -t doubao-paste
```

## macOS Permissions

Auto-paste requires `Accessibility` permission for the host app that runs the helper, such as Terminal or Codex.

Without that permission:

- the relay still works
- the desktop page still works
- clipboard mode still works
- direct paste will fail or do nothing

## Public Internet Testing

This repo includes a helper script for [Tunnelmole](https://tunnelmole.com/) because it is fast to start from `npx` and works well for temporary testing.

Security notes:

- use random room ids for ad hoc public tests
- do not leave a public tunnel open longer than needed
- this relay stores data in memory only
- archived history is cleared when the server stops

## Limitations

- macOS-focused for direct cursor insertion
- in-memory history only
- no built-in application authentication; the hosted OpenClaw route relies on external Cloudflare Access policies and per-device service tokens
- not intended for multi-user production use

## Development

No build step is required.

Useful checks:

```bash
python3 -m py_compile app/server.py scripts/mac_paste_helper.py scripts/windows_paste_helper.py scripts/smoke_test.py
python3 -m unittest tests.test_windows_paste_helper -v
node --check app/static/client.js
python3 scripts/smoke_test.py --room-id smoke-room --output-json /tmp/doubao-smoke.json
python3 scripts/smoke_test.py --room-id smoke-room --base-path /doubao --output-json /tmp/doubao-smoke-subpath.json
```

## License

MIT
