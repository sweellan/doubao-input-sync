#!/usr/bin/env python3
"""Local relay server for phone-to-PC text sync."""

from __future__ import annotations

import argparse
import json
import queue
import socket
import threading
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List
from urllib.parse import parse_qs, urlparse


APP_ROOT = Path(__file__).resolve().parent
STATIC_ROOT = APP_ROOT / "static"
ARCHIVE_IDLE_SECONDS = 1.2
MAX_HISTORY_ITEMS = 50


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def detect_local_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


@dataclass
class ArchiveEntry:
    archive_id: int
    text: str
    chars: int
    source: str
    version: int
    archived_at: str

    def payload(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class RoomState:
    room_id: str
    text: str = ""
    version: int = 0
    updated_at: str = ""
    source: str = ""
    history: List[ArchiveEntry] = field(default_factory=list)

    def payload(self) -> Dict[str, object]:
        return {
            "room_id": self.room_id,
            "text": self.text,
            "version": self.version,
            "updated_at": self.updated_at,
            "source": self.source,
            "history": [entry.payload() for entry in self.history],
        }

    def clone(self) -> "RoomState":
        return RoomState(
            room_id=self.room_id,
            text=self.text,
            version=self.version,
            updated_at=self.updated_at,
            source=self.source,
            history=[
                ArchiveEntry(
                    archive_id=entry.archive_id,
                    text=entry.text,
                    chars=entry.chars,
                    source=entry.source,
                    version=entry.version,
                    archived_at=entry.archived_at,
                )
                for entry in self.history
            ],
        )


class RoomStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rooms: Dict[str, RoomState] = {}
        self._subscribers: Dict[str, List[queue.Queue]] = {}
        self._archive_timers: Dict[str, threading.Timer] = {}
        self._archive_ids: Dict[str, int] = {}

    def get(self, room_id: str) -> RoomState:
        with self._lock:
            room = self._rooms.get(room_id)
            if room is None:
                room = RoomState(room_id=room_id)
                self._rooms[room_id] = room
            return room.clone()

    def update(self, room_id: str, text: str, source: str) -> RoomState:
        with self._lock:
            room = self._rooms.get(room_id)
            if room is None:
                room = RoomState(room_id=room_id)
                self._rooms[room_id] = room
            previous_timer = self._archive_timers.pop(room_id, None)
            if previous_timer is not None:
                previous_timer.cancel()
            room.text = text
            room.source = source
            room.version += 1
            room.updated_at = utc_now_iso()
            version = room.version
            payload = room.payload()
            subscribers = list(self._subscribers.get(room_id, []))
            timer = threading.Timer(ARCHIVE_IDLE_SECONDS, self._archive_if_idle, args=(room_id, version))
            timer.daemon = True
            self._archive_timers[room_id] = timer

        for subscriber in subscribers:
            subscriber.put(payload)

        timer.start()
        return room.clone()

    def subscribe(self, room_id: str) -> queue.Queue:
        watcher: queue.Queue = queue.Queue()
        with self._lock:
            self._subscribers.setdefault(room_id, []).append(watcher)
        return watcher

    def unsubscribe(self, room_id: str, watcher: queue.Queue) -> None:
        with self._lock:
            watchers = self._subscribers.get(room_id)
            if not watchers:
                return
            if watcher in watchers:
                watchers.remove(watcher)
            if not watchers:
                self._subscribers.pop(room_id, None)

    def _archive_if_idle(self, room_id: str, expected_version: int) -> None:
        with self._lock:
            room = self._rooms.get(room_id)
            if room is None or room.version != expected_version:
                return

            self._archive_timers.pop(room_id, None)

            if not room.text.strip():
                return

            if room.history and room.history[-1].text == room.text:
                return

            next_archive_id = self._archive_ids.get(room_id, 0) + 1
            self._archive_ids[room_id] = next_archive_id
            room.history.append(
                ArchiveEntry(
                    archive_id=next_archive_id,
                    text=room.text,
                    chars=len(room.text),
                    source=room.source,
                    version=room.version,
                    archived_at=utc_now_iso(),
                )
            )
            room.history = room.history[-MAX_HISTORY_ITEMS:]
            payload = room.payload()
            subscribers = list(self._subscribers.get(room_id, []))

        for subscriber in subscribers:
            subscriber.put(payload)


class RelayHandler(BaseHTTPRequestHandler):
    server_version = "DoubaoInputSync/0.1"

    @property
    def store(self) -> RoomStore:
        return self.server.store  # type: ignore[attr-defined]

    @property
    def default_room(self) -> str:
        return self.server.default_room  # type: ignore[attr-defined]

    @property
    def local_ip(self) -> str:
        return self.server.local_ip  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/ping":
            self._send_json({"ok": True, "ts": utc_now_iso()})
            return

        if path == "/api/server-info":
            self._send_json(
                {
                    "host": self.server.server_address[0],
                    "port": self.server.server_address[1],
                    "default_room": self.default_room,
                    "local_ip": self.local_ip,
                    "local_base_url": f"http://{self.local_ip}:{self.server.server_address[1]}",
                }
            )
            return

        if path == "/api/state":
            room_id = self._room_id_from_query(parsed.query)
            self._send_json(self.store.get(room_id).payload())
            return

        if path == "/api/stream":
            room_id = self._room_id_from_query(parsed.query)
            self._stream_room(room_id)
            return

        if path == "/" or path.startswith("/mobile/") or path.startswith("/pc/"):
            self._serve_file(STATIC_ROOT / "index.html", "text/html; charset=utf-8")
            return

        if path == "/assets/client.js":
            self._serve_file(STATIC_ROOT / "client.js", "application/javascript; charset=utf-8")
            return

        if path == "/assets/styles.css":
            self._serve_file(STATIC_ROOT / "styles.css", "text/css; charset=utf-8")
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/update":
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(content_length) or b"{}")
        room_id = (payload.get("room_id") or self.default_room).strip()
        text = payload.get("text", "")
        source = (payload.get("source") or "unknown").strip()

        if not room_id:
            self._send_json({"error": "room_id is required"}, status=HTTPStatus.BAD_REQUEST)
            return

        if not isinstance(text, str):
            self._send_json({"error": "text must be a string"}, status=HTTPStatus.BAD_REQUEST)
            return

        room = self.store.update(room_id=room_id, text=text, source=source)
        self._send_json(room.payload(), status=HTTPStatus.CREATED)

    def _room_id_from_query(self, query: str) -> str:
        params = parse_qs(query)
        value = params.get("room_id", [self.default_room])[0].strip()
        return value or self.default_room

    def _send_json(self, payload: Dict[str, object], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, path: Path, content_type: str) -> None:
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _stream_room(self, room_id: str) -> None:
        watcher = self.store.subscribe(room_id)
        try:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            self.wfile.write(self._sse("room_state", self.store.get(room_id).payload()))
            self.wfile.flush()

            while True:
                try:
                    payload = watcher.get(timeout=15)
                    self.wfile.write(self._sse("room_state", payload))
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return
        finally:
            self.store.unsubscribe(room_id, watcher)

    def _sse(self, event_name: str, payload: Dict[str, object]) -> bytes:
        data = json.dumps(payload, ensure_ascii=False)
        return f"event: {event_name}\ndata: {data}\n\n".encode("utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the local Doubao input sync server.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--default-room", default="doubao")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    server = ThreadingHTTPServer((args.host, args.port), RelayHandler)
    server.store = RoomStore()  # type: ignore[attr-defined]
    server.default_room = args.default_room  # type: ignore[attr-defined]
    server.local_ip = detect_local_ip()  # type: ignore[attr-defined]

    print(f"Doubao Input Sync server running on http://127.0.0.1:{args.port}")
    print(f"LAN access: http://{server.local_ip}:{args.port}")  # type: ignore[attr-defined]
    print(f"Default mobile page: http://{server.local_ip}:{args.port}/mobile/{args.default_room}")
    print(f"Default PC page: http://127.0.0.1:{args.port}/pc/{args.default_room}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
