# Doubao Input Sync

Turn phone-side text input into desktop text insertion.

`Doubao Input Sync` is a tiny local relay that lets you type or paste a long block of text on your phone, have it auto-sync to your computer, keep an archive of stable snapshots, and optionally auto-paste the final text into the desktop app that currently owns the cursor.

This is an unofficial utility and is not affiliated with Doubao or its input method product team.

Chinese documentation: [README.zh-CN.md](README.zh-CN.md)

## Why This Exists

Some mobile-first input experiences are excellent, but the desktop version is missing or less convenient. This project does not try to reimplement the input method itself. It only bridges the result:

- phone input area
- local relay server
- desktop monitor page
- optional auto-paste to the current cursor position on macOS

## Features

- Auto-sync while typing, no explicit send button
- Auto-archive after the text settles for about 1.2 seconds
- Desktop history list with per-item copy actions
- Optional auto-paste to the active desktop input on macOS
- Zero Python dependencies beyond the standard library
- Temporary public testing via tunnel tools if phone and desktop are not on the same LAN

## How It Works

```text
Phone browser
  -> POST /api/update
Local Python relay
  -> in-memory room state
  -> SSE updates to desktop page
  -> archive snapshot after idle window
macOS helper
  -> watches latest archive item
  -> copies or pastes into active app
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
  mac_paste_helper.py
  smoke_test.py
```

## Quick Start

### 1. Start the local relay server

```bash
./scripts/run_local_server.sh
```

This starts the relay on `http://127.0.0.1:8765`.

### 2. Open the phone page

If your phone and desktop are on the same LAN:

```text
http://<your-desktop-lan-ip>:8765/mobile/doubao
```

If your phone is only on the public internet, use a tunnel:

```bash
./scripts/run_tunnelmole.sh
```

Then open the generated HTTPS URL plus `/mobile/doubao`.

### 3. Open the desktop page

```text
http://127.0.0.1:8765/pc/doubao
```

### 4. Optional: auto-paste into the current cursor position

```bash
./scripts/run_autopaste_local.sh
```

This will:

- start the relay if it is not already running
- watch the latest archived snapshot
- paste it into the currently focused desktop input on macOS

## Main Commands

Start only the relay:

```bash
./scripts/run_local_server.sh
```

Start relay + auto-paste helper:

```bash
./scripts/run_autopaste_local.sh
```

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
- no authentication layer yet
- not intended for multi-user production use

## Development

No build step is required.

Useful checks:

```bash
python3 -m py_compile app/server.py scripts/mac_paste_helper.py scripts/smoke_test.py
node --check app/static/client.js
python3 scripts/smoke_test.py --room-id smoke-room --output-json /tmp/doubao-smoke.json
```

## License

MIT
