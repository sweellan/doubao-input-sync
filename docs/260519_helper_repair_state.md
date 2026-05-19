# 260519 Helper Repair State

## Before Fix Snapshot

- Time: 2026-05-19 12:17 Asia/Shanghai.
- User-visible symptom: PC page at `https://versicolor-charla-nonmutinously.ngrok-free.dev/doubao/pc/doubao` could copy text normally, but Mac automatic paste helper was not consuming that route.
- Tailscale node `100.69.170.35` was online and `tailscale ping` succeeded via DERP, but HTTP checks to `http://100.69.170.35:18765/doubao/api/ping` returned `Empty reply from server`.
- Host-header checks against Tailscale ports `18765`, `18766`, and `18889` also returned `Empty reply from server`.
- The fixed ngrok route was healthy: `https://versicolor-charla-nonmutinously.ngrok-free.dev/doubao/api/ping` returned HTTP 200, and `/api/helper-state?room_id=doubao` returned archive `1046`.
- Local helpers were drifted:
  - LaunchAgent helper was configured with `MODE=clipboard` and `SERVER_URL=http://100.69.170.35:18765/doubao`.
  - Foreground Terminal helper was configured with `MODE=paste` but still used `SERVER_URL=http://100.69.170.35:18765/doubao`.

Interpretation: Tailscale network reachability was present, but the Tailscale HTTP relay/proxy path was not returning valid Doubao API responses. The user-facing ngrok page worked because it was a different healthy route.

## After Fix Snapshot

- Time: 2026-05-19 12:21 Asia/Shanghai.
- Local helper consumption path was moved to fixed ngrok:
  - `SERVER_URL=https://versicolor-charla-nonmutinously.ngrok-free.dev/doubao`
  - `ROOM_ID=doubao`
  - `MODE=paste`
  - `TRIGGER=archive`
  - `REQUEST_TIMEOUT_SECONDS=45`
- The old LaunchAgent helper was unloaded so there is no longer a background `MODE=clipboard` helper competing with the foreground paste helper.
- The stale control-plane run from 2026-04-27 was marked stopped with return code `143`, because its Python helper had already been killed but the SQLite state still said `running`.
- A new foreground paste helper was started through the control-plane persistent Terminal runner.
- Current process check showed the active helper as:

```text
scripts/mac_paste_helper.py --server-url https://versicolor-charla-nonmutinously.ngrok-free.dev/doubao --room-id doubao --mode paste --trigger archive --request-timeout-seconds 45
```

- Current run log: `__sys/automation/doubao_input_sync_control_plane/runtime/runs/260519_1219__doubao-foreground-paste-helper/stdout.log`.
- The helper intentionally skipped existing archive `1046` on startup because `skip-existing` is the default; a fresh mobile archive is required to verify a new `action=applied` line.

Current routing decision: Tailscale is still the preferred private path when its relay/proxy is healthy, but the active Mac helper now uses the fixed ngrok domain because the Tailscale HTTP API path is currently broken while ngrok is healthy.

## Latency Optimization Snapshot

- Time: 2026-05-19 14:55 Asia/Shanghai.
- Original Tailscale path was rechecked:
  - `tailscale ping 100.69.170.35` still succeeded via DERP.
  - TCP ports `18765`, `18766`, and `18889` were open.
  - HTTP checks to `http://100.69.170.35:18765/doubao/api/ping` still timed out or returned no valid response.
- Fixed ngrok route was slow through normal `curl` DNS resolution, with repeated resolver timeouts.
- Direct `curl --resolve` checks against ngrok edge IPv4 addresses returned HTTP 200 in roughly 1.1-1.8 seconds.
- Helper changes:
  - `mac_paste_helper.py` now accepts `--curl-resolve` and passes entries to curl.
  - `run_foreground_paste_helper.sh` now defaults to ngrok IPv4 resolve entries.
  - Foreground helper request timeout was reduced from `45` seconds to `4` seconds.
  - Foreground helper poll interval was reduced from `0.5` seconds to `0.25` seconds.
- Runtime change:
  - The remote `doubao` room archive idle setting was reduced from `4.0` seconds to `1.2` seconds via `/api/settings`.

Current expected latency: after the user stops input, the main fixed wait is now about `1.2s` for archive debounce plus roughly `1-2s` for ngrok API response and up to `0.25s` polling interval. This is still slower than a healthy private Tailscale relay, but avoids the previous long DNS/request stalls.
