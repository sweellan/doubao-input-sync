# Doubao Input Sync Operations

This is the first place to check when Doubao Input Sync needs adjustment.

## What Owns What

- Project source and operational notes live here: `/Users/yangchao/Sync/Meituan/Workspace/10_projects/260324_DoubaoInputSync__pilot`.
- There is currently no separate `doubao` Codex skill installed.
- The foreground runner is managed through the existing `codex-desktop-control-plane` skill pattern, with runtime state under `__sys/automation/doubao_input_sync_control_plane/`.
- The fixed public relay entry is `https://openclaw.ciaobella.cc/doubao`.
- The historical private relay entry is `http://100.69.170.35:18765/doubao`; prefer it only when `/doubao/api/ping` and `/doubao/api/helper-state?room_id=doubao` return valid responses.

## Current Helper Path

The intended Mac helper is the foreground Terminal paste helper, not the LaunchAgent clipboard helper.

Check current helper:

```bash
ps aux | rg -i 'mac_paste_helper|doubao-foreground-paste-helper|run_helper_daemon' | rg -v rg
```

The healthy helper command should include:

```text
--server-url https://openclaw.ciaobella.cc/doubao
--room-id doubao
--mode paste
--request-timeout-seconds 12
--interval-seconds 0.25
--stream-max-time-seconds 90
--curl-resolve openclaw.ciaobella.cc:443:172.67.208.237
--transport stream
```

The current foreground run log is under:

```text
__sys/automation/doubao_input_sync_control_plane/runtime/runs/
```

## Parameters

Do not lower `archive_idle_seconds` just to improve desktop paste latency.

That setting is the phone-side input stabilization window. Doubao IME may emit a draft and then revise it; if this window is too short, incomplete text can be archived and pasted. The user's current preferred value is `3.7`.

Safe optimization targets:

- helper request timeout
- helper poll interval
- helper transport; prefer SSE `stream` over HTTPS polling for the public route
- SSE stream max lifetime; recycle the stream periodically so a silently stale connection can self-heal
- curl DNS / `--resolve`; currently prefer `openclaw.ciaobella.cc:443:172.67.208.237`
- foreground runner health and logs
- restoring the private Tailscale relay/proxy

Risky optimization target:

- `archive_idle_seconds`; only change it when the user explicitly asks.

## Current Transfer Strategy

The mobile page sends a full draft snapshot after a short browser debounce. The relay pushes every draft version to SSE subscribers in both capture modes.

- In `capture_mode=auto` (`⚡ 顺口模式`), every draft resets the archive timer. After `archive_idle_seconds` of no new updates, the relay writes one stable archive entry.
- In `capture_mode=manual` (`🌿 换气模式`), draft updates never start an archive timer. `POST /api/capture` writes the current version immediately after the phone user presses `说完了，发送`.

The macOS helper remains unchanged and uses `trigger=archive`, so both modes converge on the same archive -> helper -> paste -> acknowledgement path.

The room state is the capture-mode source of truth. Switching modes is sent atomically with the latest mobile draft. Switching from auto to manual cancels any pending archive timer; switching back to auto starts a fresh quiet-window timer for the current draft. A relay restart defaults rooms back to `auto`.

The relay keeps versions and archive ids in memory, so a restart resets both sequences. The helper detects a version rollback, clears its old archive cursor and stale pending acknowledgements, and can consume fresh archive ids from the restarted relay without requiring a manual helper restart.

The PC web page should treat live draft text as preview-only. Its main output should show the latest archive entry; otherwise long voice input will visibly grow, shrink, and regrow as the mobile IME revises intermediate text.

If a fresh archive exists but `desktop_received_at` remains empty, check the helper stream first. A long-lived public SSE connection can stay alive but stop delivering events. The helper should use HTTP/1.1 and a finite `--stream-max-time-seconds` so reconnects can pick up missed archive entries from the initial stream state.

## Quick Health Checks

Public route:

```bash
curl -sS --max-time 4 --connect-timeout 2 \
  --resolve openclaw.ciaobella.cc:443:172.67.208.237 \
  -H 'ngrok-skip-browser-warning: 1' \
  -A 'doubao-input-sync-helper/1.0' \
  'https://openclaw.ciaobella.cc/doubao/api/helper-state?room_id=doubao'
```

Private Tailscale route:

```bash
curl -sS -i --max-time 5 \
  -H 'ngrok-skip-browser-warning: 1' \
  -A 'doubao-input-sync-helper/1.0' \
  'http://100.69.170.35:18765/doubao/api/ping'
```

Room setting check:

```bash
curl -sS --max-time 4 --connect-timeout 2 \
  --resolve openclaw.ciaobella.cc:443:172.67.208.237 \
  -H 'ngrok-skip-browser-warning: 1' \
  -A 'doubao-input-sync-helper/1.0' \
  'https://openclaw.ciaobella.cc/doubao/api/state?room_id=doubao' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin).get("settings"))'
```

## Restart Helper

If the helper needs to be restarted, prefer the control-plane runner so it keeps using the foreground Terminal permission surface.

Current manual restart pattern:

```bash
cd /Users/yangchao/Sync/Meituan/Workspace/10_projects/260324_DoubaoInputSync__pilot
/usr/bin/python3 /Users/yangchao/.codex/skills/codex-desktop-control-plane/scripts/codex_control_plane.py run-once \
  --root /Users/yangchao/Sync/Meituan/Workspace/10_projects/260324_DoubaoInputSync__pilot/__sys/automation/doubao_input_sync_control_plane/runtime \
  --job doubao-foreground-paste-helper
```

If control-plane says the job is already running but no helper process exists, inspect:

```bash
sqlite3 __sys/automation/doubao_input_sync_control_plane/runtime/state/control_plane.db \
  'select id,job_id,status,started_at,ended_at,run_dir,error from runs order by id desc limit 5;'
```

Only mark a stale run as stopped after verifying the process is gone.
