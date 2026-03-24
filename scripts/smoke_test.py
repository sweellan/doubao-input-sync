#!/usr/bin/env python3
"""Smoke test for the local relay server and macOS helper contract."""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Dict, List
from urllib.parse import urlencode
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for_ping(server_url: str, timeout_seconds: float = 10) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urlopen(f"{server_url}/api/ping", timeout=1) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if payload.get("ok"):
                return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError("server failed to answer /api/ping before timeout")


def read_sse_event(server_url: str, room_id: str, results: List[Dict[str, object]], stop_after: int = 2) -> None:
    stream_url = f"{server_url}/api/stream?{urlencode({'room_id': room_id})}"
    with urlopen(stream_url, timeout=10) as response:
        event_name = None
        for raw_line in response:
            line = raw_line.decode("utf-8").strip()
            if not line:
                continue
            if line.startswith(":"):
                continue
            if line.startswith("event:"):
                event_name = line.split(":", 1)[1].strip()
                continue
            if line.startswith("data:") and event_name == "room_state":
                payload = json.loads(line.split(":", 1)[1].strip())
                results.append(payload)
                if len(results) >= stop_after:
                    return


def post_update(server_url: str, room_id: str, text: str, source: str) -> dict:
    body = json.dumps({"room_id": room_id, "text": text, "source": source}).encode("utf-8")
    request = Request(
        f"{server_url}/api/update",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=3) as response:
        return json.loads(response.read().decode("utf-8"))


def get_state(server_url: str, room_id: str) -> dict:
    with urlopen(f"{server_url}/api/state?{urlencode({'room_id': room_id})}", timeout=3) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_for_archive(server_url: str, room_id: str, timeout_seconds: float = 8) -> dict:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        payload = get_state(server_url, room_id)
        if payload.get("history"):
            return payload
        time.sleep(0.15)
    raise RuntimeError("archive history did not appear before timeout")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Doubao Input Sync smoke test.")
    parser.add_argument("--room-id", default="smoke-room")
    parser.add_argument("--output-json", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    port = find_free_port()
    server_url = f"http://127.0.0.1:{port}"

    with tempfile.TemporaryDirectory(prefix="doubao_sync_smoke_") as temp_dir:
        temp_path = Path(temp_dir)
        server_log = temp_path / "server.log"
        helper_log = temp_path / "helper.log"

        with server_log.open("w", encoding="utf-8") as server_handle:
            server_proc = subprocess.Popen(
                [sys.executable, "app/server.py", "--host", "127.0.0.1", "--port", str(port), "--default-room", args.room_id],
                cwd=PROJECT_ROOT,
                stdout=server_handle,
                stderr=subprocess.STDOUT,
            )

        try:
            wait_for_ping(server_url)

            sse_events: List[Dict[str, object]] = []
            sse_thread = threading.Thread(
                target=read_sse_event,
                args=(server_url, args.room_id, sse_events),
                daemon=True,
            )
            sse_thread.start()
            time.sleep(0.3)

            with helper_log.open("w", encoding="utf-8") as helper_handle:
                helper_proc = subprocess.Popen(
                    [
                        sys.executable,
                        "scripts/mac_paste_helper.py",
                        "--server-url",
                        server_url,
                        "--room-id",
                        args.room_id,
                        "--mode",
                        "clipboard",
                        "--dry-run",
                        "--stop-after-updates",
                        "1",
                    ],
                    cwd=PROJECT_ROOT,
                    stdout=helper_handle,
                    stderr=subprocess.STDOUT,
                )

            time.sleep(0.4)
            posted = post_update(server_url, args.room_id, "来自手机端的同步测试文本", "smoke-test")
            state = get_state(server_url, args.room_id)
            archived_state = wait_for_archive(server_url, args.room_id)

            sse_thread.join(timeout=5)
            helper_exit = helper_proc.wait(timeout=5)

            helper_output = helper_log.read_text(encoding="utf-8").strip().splitlines()
            report = {
                "status": "passed",
                "server_url": server_url,
                "room_id": args.room_id,
                "posted": posted,
                "state": state,
                "archived_state": archived_state,
                "sse_events": sse_events,
                "helper_exit_code": helper_exit,
                "helper_output": helper_output,
                "checks": {
                    "state_reflects_update": state.get("text") == "来自手机端的同步测试文本",
                    "sse_received_update": any(event.get("version") == posted.get("version") for event in sse_events),
                    "helper_saw_update": any('"status": "updated"' in line for line in helper_output),
                    "history_archived_latest": bool(archived_state.get("history")) and archived_state["history"][-1].get("text") == "来自手机端的同步测试文本",
                },
            }

            if not all(report["checks"].values()):
                report["status"] = "failed"
                raise AssertionError(json.dumps(report, ensure_ascii=False, indent=2))

            Path(args.output_json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            return 0
        finally:
            server_proc.terminate()
            try:
                server_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                server_proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
