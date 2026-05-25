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

## Archive Idle Correction

- Time: 2026-05-19 15:00 Asia/Shanghai.
- User clarified that archive idle time should not be reduced for desktop latency, because Doubao IME may revise the text after the first draft.
- The user manually restored `archive_idle_seconds` to `3.7`.
- Follow-up checks confirmed the remote room setting is `{'archive_idle_seconds': 3.7}`.

Current rule: do not change `archive_idle_seconds` unless the user explicitly asks. Optimize helper/network/runner behavior instead.

## Public Domain Migration

- Time: 2026-05-20 15:12 Asia/Shanghai.
- Public relay entry moved from `https://versicolor-charla-nonmutinously.ngrok-free.dev/doubao` to `https://openclaw.ciaobella.cc/doubao`.
- New route health checks passed:
  - `/doubao/api/ping` returned `{"ok": true, ...}`.
  - `/doubao/api/helper-state?room_id=doubao` returned HTTP 200 in about 1.1-1.3 seconds without hardcoded curl resolve entries.
  - `/doubao/api/state?room_id=doubao` confirmed `archive_idle_seconds` remains `3.7`.
- Helper configuration was moved to the new public route and old ngrok-specific `CURL_RESOLVE` entries were cleared.

Current rule: use `https://openclaw.ciaobella.cc/doubao` as the default helper route. Keep `CURL_RESOLVE` empty unless DNS latency or resolver failures reappear.

## OpenClaw DNS Timeout Repair

- Time: 2026-05-20 15:24 Asia/Shanghai.
- Symptom: helper process was still alive and pointed to `https://openclaw.ciaobella.cc/doubao`, but recent stdout was repeated `curl: (28) Resolving timed out after 2000ms`.
- Plain `curl` to `https://openclaw.ciaobella.cc/doubao/api/ping` reproduced the DNS timeout.
- `curl --resolve` with Cloudflare edge IPs returned HTTP 200 in about 1.1-1.3 seconds:
  - `openclaw.ciaobella.cc:443:104.21.61.99`
  - `openclaw.ciaobella.cc:443:172.67.208.237`
- Helper config was updated to use those `CURL_RESOLVE` entries.
- `/doubao/api/state?room_id=doubao` still reports `archive_idle_seconds` as `3.7`.

Current rule: keep the OpenClaw `CURL_RESOLVE` entries while the local resolver keeps timing out. Do not change `archive_idle_seconds` for this issue.

## Helper Exit Repair

- Time: 2026-05-25 11:40 Asia/Shanghai.
- Symptom: no `mac_paste_helper.py` process was running. The last control-plane run had ended at 2026-05-23 16:00 Asia/Shanghai with return code `1`.
- Root cause in stderr: `http.client.RemoteDisconnected: Remote end closed connection without response` escaped the helper retry loop after curl had fallen through to urllib.
- Remote route was still alive: `/doubao/api/ping` returned OK and `/doubao/api/state?room_id=doubao` showed `archive_idle_seconds` remained `3.7`.
- Helper changes:
  - curl failures now become retryable `URLError` values instead of falling through to urllib, except helper-state 404 for older relays.
  - urllib `RemoteDisconnected` and related connection errors are wrapped as retryable `URLError`.
  - foreground helper timeout increased from `4` seconds to `12` seconds.
  - curl connect timeout now uses up to `8` seconds instead of being capped at `2` seconds, because Cloudflare TLS handshakes occasionally exceed 2 seconds.

Current rule: transient OpenClaw network failures must keep the foreground helper alive and retrying. Do not change `archive_idle_seconds` for this issue.
