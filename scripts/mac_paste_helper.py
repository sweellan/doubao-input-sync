#!/usr/bin/env python3
"""Optional macOS helper: copy synced text to clipboard or paste into active input."""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen


def fetch_state(server_url: str, room_id: str, request_timeout_seconds: float) -> dict:
    query = urlencode({"room_id": room_id})
    url = f"{server_url.rstrip('/')}/api/state?{query}"

    curl_proc = subprocess.run(
        [
            "curl",
            "-fsS",
            "--max-time",
            str(request_timeout_seconds),
            url,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if curl_proc.returncode == 0:
        return json.loads(curl_proc.stdout)

    # Fallback to urllib in case curl is unavailable or the environment differs.
    with urlopen(url, timeout=request_timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def copy_to_clipboard(text: str) -> None:
    subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)


def paste_to_active_app(text: str) -> None:
    copy_to_clipboard(text)
    subprocess.run(
        [
            "osascript",
            "-e",
            'tell application "System Events" to keystroke "v" using command down',
        ],
        check=True,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Watch synced text and project it to macOS.")
    parser.add_argument("--server-url", default="http://127.0.0.1:8765")
    parser.add_argument("--room-id", default="doubao")
    parser.add_argument("--interval-seconds", type=float, default=0.5)
    parser.add_argument("--request-timeout-seconds", type=float, default=8.0)
    parser.add_argument("--mode", choices=["clipboard", "paste"], default="clipboard")
    parser.add_argument(
        "--trigger",
        choices=["archive", "live"],
        default="archive",
        help="archive waits for a settled history item; live reacts to every new version.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--stop-after-updates", type=int, default=0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    last_version = -1
    last_archive_id = -1
    applied_updates = 0
    connection_refused_count = 0
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    while True:
        try:
            payload = fetch_state(args.server_url, args.room_id, args.request_timeout_seconds)
            connection_refused_count = 0
        except (URLError, socket.timeout) as exc:
            connection_refused_count += 1
            reason = str(getattr(exc, "reason", exc))
            record = {"status": "retrying", "reason": reason, "server_url": args.server_url}
            if connection_refused_count == 1:
                record["hint"] = (
                    "relay server is not reachable; start it with "
                    f"`cd {project_root} && ./scripts/run_local_server.sh` "
                    "or use `./scripts/run_autopaste_local.sh` for one-command startup"
                )
            print(json.dumps(record, ensure_ascii=False), flush=True)
            time.sleep(args.interval_seconds)
            continue

        version = payload.get("version", 0)
        text = payload.get("text", "")
        history = payload.get("history") or []
        trigger_ref = None

        if args.trigger == "archive":
            if not history:
                time.sleep(args.interval_seconds)
                continue

            latest_archive = history[-1]
            archive_id = latest_archive.get("archive_id", 0)
            if archive_id <= last_archive_id:
                time.sleep(args.interval_seconds)
                continue

            last_archive_id = archive_id
            text = latest_archive.get("text", "")
            trigger_ref = f"archive:{archive_id}"
        else:
            if version <= last_version:
                time.sleep(args.interval_seconds)
                continue
            last_version = version
            trigger_ref = f"version:{version}"

        if not text:
            time.sleep(args.interval_seconds)
            continue

        record = {
            "status": "updated",
            "room_id": args.room_id,
            "version": version,
            "mode": args.mode,
            "trigger": args.trigger,
            "trigger_ref": trigger_ref,
            "chars": len(text),
        }

        if args.dry_run:
            record["action"] = "dry_run"
            print(json.dumps(record, ensure_ascii=False), flush=True)
        else:
            if sys.platform != "darwin":
                raise RuntimeError("mac_paste_helper.py only supports macOS live mode.")
            if args.mode == "clipboard":
                copy_to_clipboard(text)
            else:
                paste_to_active_app(text)
            record["action"] = "applied"
            print(json.dumps(record, ensure_ascii=False), flush=True)

        applied_updates += 1
        if args.stop_after_updates and applied_updates >= args.stop_after_updates:
            return 0

        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
