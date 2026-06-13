# Windows Helper Plan

This document is the Windows-side handoff for Doubao Input Sync.

Remote document:

```text
https://github.com/sweellan/doubao-input-sync/blob/main/docs/WINDOWS_HELPER_PLAN.md
```

## One-line Bootstrap

Paste this into Windows PowerShell to fetch the repo and open this document:

```powershell
$repo='https://github.com/sweellan/doubao-input-sync.git'; $dir=Join-Path $env:USERPROFILE 'doubao-input-sync'; if (Test-Path $dir) { git -C $dir pull --ff-only } else { git clone $repo $dir }; notepad (Join-Path $dir 'docs\WINDOWS_HELPER_PLAN.md')
```

Prerequisite: Git for Windows must be installed and available as `git`.

## Goal

Use one phone as the input surface, then quickly send settled text to one or more computers.

The current system already has the shared relay and web pages:

- phone page: input text on mobile
- PC page: view the latest stable archive for a room
- helper process: watches one room and delivers the latest stable archive to the local computer

macOS delivery already exists in `scripts/mac_paste_helper.py`. Windows needs an equivalent helper.

## Current Transfer Contract

The phone sends live draft snapshots while the user is typing or using voice input. These drafts can grow, shrink, and change because mobile IME voice input keeps revising intermediate text.

The relay only creates a stable archive after `archive_idle_seconds` of no changes. Helpers should use archive entries as the delivery trigger, not live draft text.

The delivery contract for any desktop helper is:

1. Watch a single `room_id`.
2. Ignore live draft churn.
3. Deliver only new archive entries.
4. Acknowledge delivery through `/api/archive-ack`.
5. Reconnect or poll safely when the public SSE stream gets stale.

## Multi-computer Strategy

Use one room per destination computer or destination workflow.

Examples:

- `doubao-mac-main`
- `doubao-win-office`
- `doubao-win-home`
- `doubao-notes`
- `doubao-browser-a`

On the phone, open or bookmark different mobile URLs for different rooms. On each computer, run a helper bound to its own room.

This avoids mixing destinations. It also keeps each computer's paste history and acknowledgement state independent.

## Windows Minimal Version

Start with clipboard-only delivery. This is safer and should work before we attempt foreground paste.

Expected behavior:

1. Windows helper watches the relay room.
2. When a new archive appears, it writes the archive text to the Windows clipboard.
3. It posts `/api/archive-ack` with `action=clipboard`.
4. The phone can auto-clear only after the ack is visible.

Implementation shape:

- Use Python standard library where possible.
- Fetch initial room state through `/api/helper-state`.
- Prefer SSE from `/api/stream` when stable.
- Fall back to polling `/api/helper-state` if SSE is unreliable on Windows.
- Set clipboard through PowerShell:

```powershell
Set-Clipboard -Value $text
```

For a Python helper, the clipboard write can call PowerShell as a subprocess.

## Windows Foreground Paste Version

After clipboard-only is reliable, add foreground paste.

Possible approaches:

- AutoHotkey v2: most practical for reliable `Ctrl+V` into the active window.
- PowerShell COM: `New-Object -ComObject WScript.Shell` then `SendKeys('^v')`; simpler but more fragile.
- pywinauto: useful later if app-specific targeting becomes necessary.

Expected behavior:

1. Write archive text to clipboard.
2. Send `Ctrl+V` to the currently focused window.
3. Post `/api/archive-ack` with `action=paste`.
4. Log each delivery as JSON so failures can be inspected.

## Suggested File Layout

Add these files when implementing Windows support:

```text
scripts/windows_paste_helper.py
scripts/run_windows_clipboard_helper.ps1
scripts/run_windows_paste_helper.ps1
docs/WINDOWS_HELPER_PLAN.md
```

Keep macOS and Windows delivery code separate at first. The relay protocol is shared, but OS clipboard and foreground-paste behavior are different enough that early abstraction would make debugging harder.

## First Test Checklist

1. Start from clipboard mode, not paste mode.
2. Use a new room id such as `doubao-win-test`.
3. Open the phone page for that room.
4. Enter a long voice-input paragraph.
5. Confirm the PC page shows only stable archive text in the main output.
6. Confirm Windows clipboard updates only once per archive.
7. Confirm `/api/helper-state?room_id=doubao-win-test` shows `desktop_received_at` on the latest archive.
8. Only then enable foreground paste.

## Public Relay Defaults

Current daily route:

```text
https://openclaw.ciaobella.cc/doubao
```

Known useful room:

```text
doubao
```

For Windows testing, use a separate room first:

```text
doubao-win-test
```

## Current Mac Reference Command

The macOS helper currently uses the stable archive trigger and finite SSE stream lifetime:

```bash
./scripts/run_foreground_paste_helper.sh
```

Equivalent Windows helpers should preserve these settings conceptually:

- trigger: `archive`
- transport: `stream`, with polling fallback
- request timeout: about 12 seconds
- stream max lifetime: about 90 seconds
- delivery ack: required after clipboard or paste
