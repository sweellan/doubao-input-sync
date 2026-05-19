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
