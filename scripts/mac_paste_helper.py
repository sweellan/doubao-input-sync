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
from http.client import RemoteDisconnected
from typing import Iterator
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def normalize_payload(payload: dict) -> dict:
    if "latest_archive" not in payload:
        history = payload.get("history") or []
        payload["latest_archive"] = history[-1] if history else None
    return payload


def fetch_json(url: str, request_timeout_seconds: float, curl_resolve: list[str]) -> dict:
    curl_args = [
        "curl",
        "-fsS",
        "--max-time",
        str(request_timeout_seconds),
        "--connect-timeout",
        str(min(8.0, request_timeout_seconds)),
        "-H",
        "ngrok-skip-browser-warning: 1",
        "-A",
        "doubao-input-sync-helper/1.0",
    ]
    for resolve_entry in curl_resolve:
        curl_args.extend(["--resolve", resolve_entry])
    curl_args.append(url)

    try:
        curl_proc = subprocess.run(
            curl_args,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        curl_proc = None

    if curl_proc is not None:
        if curl_proc.returncode == 0:
            try:
                return json.loads(curl_proc.stdout.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise URLError(f"curl returned invalid JSON: {exc}") from exc

        reason = curl_proc.stderr.decode("utf-8", errors="replace").strip() or f"curl exited {curl_proc.returncode}"
        if curl_proc.returncode == 22 and "404" in reason:
            raise HTTPError(url, 404, reason, hdrs=None, fp=None)
        raise URLError(reason)

    request = Request(
        url,
        headers={
            "ngrok-skip-browser-warning": "1",
            "User-Agent": "doubao-input-sync-helper/1.0",
        },
    )
    try:
        with urlopen(request, timeout=request_timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except (RemoteDisconnected, ConnectionError, TimeoutError, OSError) as exc:
        raise URLError(str(exc)) from exc


def fetch_state(server_url: str, room_id: str, request_timeout_seconds: float, curl_resolve: list[str]) -> dict:
    query = urlencode({"room_id": room_id})
    helper_url = f"{server_url.rstrip('/')}/api/helper-state?{query}"
    state_url = f"{server_url.rstrip('/')}/api/state?{query}"

    try:
        return fetch_json(helper_url, request_timeout_seconds, curl_resolve)
    except HTTPError as exc:
        if exc.code != 404:
            raise
    except (URLError, socket.timeout):
        pass

    payload = fetch_json(state_url, request_timeout_seconds, curl_resolve)
    return normalize_payload(payload)


def parse_sse_event(lines: list[str]) -> dict | None:
    event_name = ""
    data_lines: list[str] = []
    for line in lines:
        if line.startswith("event:"):
            event_name = line.removeprefix("event:").strip()
        elif line.startswith("data:"):
            data_lines.append(line.removeprefix("data:").lstrip())

    if event_name and event_name != "room_state":
        return None
    if not data_lines:
        return None
    try:
        return normalize_payload(json.loads("\n".join(data_lines)))
    except json.JSONDecodeError as exc:
        raise URLError(f"SSE returned invalid JSON: {exc}") from exc


def stream_payloads(server_url: str, room_id: str, request_timeout_seconds: float, curl_resolve: list[str]) -> Iterator[dict]:
    query = urlencode({"room_id": room_id})
    stream_url = f"{server_url.rstrip('/')}/api/stream?{query}"
    curl_args = [
        "curl",
        "-fsS",
        "-N",
        "--connect-timeout",
        str(min(8.0, request_timeout_seconds)),
        "-H",
        "ngrok-skip-browser-warning: 1",
        "-A",
        "doubao-input-sync-helper/1.0",
    ]
    for resolve_entry in curl_resolve:
        curl_args.extend(["--resolve", resolve_entry])
    curl_args.append(stream_url)

    try:
        proc = subprocess.Popen(
            curl_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError as exc:
        raise URLError("curl executable was not found") from exc

    assert proc.stdout is not None
    lines: list[str] = []
    try:
        for raw_line in proc.stdout:
            line = raw_line.rstrip("\n")
            if not line:
                payload = parse_sse_event(lines)
                lines = []
                if payload is not None:
                    yield payload
                continue
            if line.startswith(":"):
                continue
            lines.append(line)
    finally:
        proc.stdout.close()
        if proc.poll() is None:
            proc.terminate()

    stderr = proc.stderr.read() if proc.stderr is not None else ""
    return_code = proc.wait()
    reason = stderr.strip() or f"stream exited with code {return_code}"
    raise URLError(reason)


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
    parser.add_argument("--server-url", default="http://127.0.0.1:18766")
    parser.add_argument("--room-id", default="doubao")
    parser.add_argument("--interval-seconds", type=float, default=0.5)
    parser.add_argument("--request-timeout-seconds", type=float, default=12.0)
    parser.add_argument(
        "--transport",
        choices=["stream", "poll"],
        default="stream",
        help="stream uses the relay SSE feed; poll repeatedly fetches helper-state.",
    )
    parser.add_argument(
        "--curl-resolve",
        action="append",
        default=[],
        help="Optional curl --resolve entry. Repeat or pass comma-separated HOST:PORT:ADDR values.",
    )
    parser.add_argument("--mode", choices=["clipboard", "paste"], default="clipboard")
    parser.add_argument(
        "--trigger",
        choices=["archive", "live"],
        default="archive",
        help="archive waits for a settled history item; live reacts to every new version.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        default=True,
        help="Ignore the latest existing version/archive at startup and only react to newer content.",
    )
    parser.add_argument("--stop-after-updates", type=int, default=0)
    return parser


def parse_curl_resolve(values: list[str]) -> list[str]:
    entries: list[str] = []
    for value in values:
        for entry in value.split(","):
            entry = entry.strip()
            if entry:
                entries.append(entry)
    return entries


def process_payload(args: argparse.Namespace, payload: dict, state: dict) -> bool:
    version = payload.get("version", 0)
    text = payload.get("text", "")
    latest_archive = payload.get("latest_archive")
    trigger_ref = None

    if args.skip_existing and not state["startup_seeded"]:
        state["last_version"] = max(state["last_version"], version)
        if latest_archive:
            state["last_archive_id"] = max(state["last_archive_id"], latest_archive.get("archive_id", 0))
        state["startup_seeded"] = True
        return False

    if args.trigger == "archive":
        if not latest_archive:
            return False

        archive_id = latest_archive.get("archive_id", 0)
        if archive_id <= state["last_archive_id"]:
            return False

        state["last_archive_id"] = archive_id
        text = latest_archive.get("text", "")
        trigger_ref = f"archive:{archive_id}"
    else:
        if version <= state["last_version"]:
            return False
        state["last_version"] = version
        trigger_ref = f"version:{version}"

    if not text:
        return False

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
        try:
            if args.mode == "clipboard":
                copy_to_clipboard(text)
            else:
                paste_to_active_app(text)
            record["action"] = "applied"
            print(json.dumps(record, ensure_ascii=False), flush=True)
        except subprocess.CalledProcessError as exc:
            error_record = {
                "status": "apply_failed",
                "room_id": args.room_id,
                "mode": args.mode,
                "trigger": args.trigger,
                "trigger_ref": trigger_ref,
                "reason": str(exc),
            }
            if args.mode == "paste":
                error_record["hint"] = "Grant Accessibility permission to the terminal app that runs this helper."
            print(json.dumps(error_record, ensure_ascii=False), flush=True)
            return False

    state["applied_updates"] += 1
    return bool(args.stop_after_updates and state["applied_updates"] >= args.stop_after_updates)


def main() -> int:
    args = build_parser().parse_args()
    curl_resolve = parse_curl_resolve(args.curl_resolve)
    state = {
        "last_version": -1,
        "last_archive_id": -1,
        "applied_updates": 0,
        "startup_seeded": False,
    }
    connection_refused_count = 0
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    while True:
        try:
            if args.transport == "stream":
                for payload in stream_payloads(args.server_url, args.room_id, args.request_timeout_seconds, curl_resolve):
                    connection_refused_count = 0
                    if process_payload(args, payload, state):
                        return 0
                continue
            else:
                payload = fetch_state(args.server_url, args.room_id, args.request_timeout_seconds, curl_resolve)
                connection_refused_count = 0
                if process_payload(args, payload, state):
                    return 0
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


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
