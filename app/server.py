#!/usr/bin/env python3
"""Local relay server for phone-to-PC text sync."""

from __future__ import annotations

import argparse
import json
import os
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
ARCHIVE_IDLE_SECONDS = float(os.environ.get("ARCHIVE_IDLE_SECONDS", "2.0"))
CLAIM_TTL_SECONDS = float(os.environ.get("CLAIM_TTL_SECONDS", "45.0"))
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


def parse_archive_idle_seconds(raw_value: str) -> float:
    value = float(raw_value)
    if value < 0.5:
        raise ValueError("archive idle seconds must be >= 0.5")
    return value


def parse_claim_ttl_seconds(raw_value: str) -> float:
    value = float(raw_value)
    if value < 10:
        raise ValueError("claim ttl seconds must be >= 10")
    return value


def normalize_base_path(raw_value: str) -> str:
    value = (raw_value or "").strip()
    if not value or value == "/":
        return ""
    if not value.startswith("/"):
        value = f"/{value}"
    return value.rstrip("/")


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
class RoleClaim:
    role: str
    client_id: str
    claimed_at: str
    last_seen_at: str
    client_label: str = ""

    def payload(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class RoomState:
    room_id: str
    text: str = ""
    version: int = 0
    updated_at: str = ""
    source: str = ""
    archive_idle_seconds: float = ARCHIVE_IDLE_SECONDS
    claims: Dict[str, RoleClaim] = field(default_factory=dict)
    history: List[ArchiveEntry] = field(default_factory=list)

    def payload(self) -> Dict[str, object]:
        return {
            "room_id": self.room_id,
            "text": self.text,
            "version": self.version,
            "updated_at": self.updated_at,
            "source": self.source,
            "settings": {
                "archive_idle_seconds": self.archive_idle_seconds,
            },
            "claims": {role: claim.payload() for role, claim in self.claims.items()},
            "history": [entry.payload() for entry in self.history],
        }

    def helper_payload(self) -> Dict[str, object]:
        latest_archive = self.history[-1].payload() if self.history else None
        return {
            "room_id": self.room_id,
            "text": self.text,
            "version": self.version,
            "updated_at": self.updated_at,
            "source": self.source,
            "latest_archive": latest_archive,
        }

    def clone(self) -> "RoomState":
        return RoomState(
            room_id=self.room_id,
            text=self.text,
            version=self.version,
            updated_at=self.updated_at,
            source=self.source,
            archive_idle_seconds=self.archive_idle_seconds,
            claims={
                role: RoleClaim(
                    role=claim.role,
                    client_id=claim.client_id,
                    claimed_at=claim.claimed_at,
                    last_seen_at=claim.last_seen_at,
                    client_label=claim.client_label,
                )
                for role, claim in self.claims.items()
            },
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
    def __init__(self, archive_idle_seconds: float, claim_ttl_seconds: float) -> None:
        self._lock = threading.Lock()
        self._rooms: Dict[str, RoomState] = {}
        self._subscribers: Dict[str, List[queue.Queue]] = {}
        self._archive_timers: Dict[str, threading.Timer] = {}
        self._archive_ids: Dict[str, int] = {}
        self._default_archive_idle_seconds = archive_idle_seconds
        self._claim_ttl_seconds = claim_ttl_seconds

    def _ensure_room(self, room_id: str) -> RoomState:
        room = self._rooms.get(room_id)
        if room is None:
            room = RoomState(room_id=room_id, archive_idle_seconds=self._default_archive_idle_seconds)
            self._rooms[room_id] = room
        return room

    def get(self, room_id: str) -> RoomState:
        with self._lock:
            room = self._ensure_room(room_id)
            self._purge_expired_claims(room)
            return room.clone()

    def update(self, room_id: str, text: str, source: str) -> RoomState:
        with self._lock:
            room = self._ensure_room(room_id)
            self._purge_expired_claims(room)
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
            timer = threading.Timer(room.archive_idle_seconds, self._archive_if_idle, args=(room_id, version))
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

    def update_settings(self, room_id: str, archive_idle_seconds: float) -> RoomState:
        with self._lock:
            room = self._ensure_room(room_id)
            self._purge_expired_claims(room)
            room.archive_idle_seconds = archive_idle_seconds
            payload = room.payload()
            subscribers = list(self._subscribers.get(room_id, []))

        for subscriber in subscribers:
            subscriber.put(payload)

        return room.clone()

    def claim_role(self, room_id: str, role: str, client_id: str, client_label: str) -> Dict[str, object]:
        with self._lock:
            room = self._ensure_room(room_id)
            self._purge_expired_claims(room)
            existing_claim = room.claims.get(role)
            conflict = existing_claim is not None and existing_claim.client_id != client_id

            if not conflict:
                now = utc_now_iso()
                room.claims[role] = RoleClaim(
                    role=role,
                    client_id=client_id,
                    claimed_at=existing_claim.claimed_at if existing_claim is not None else now,
                    last_seen_at=now,
                    client_label=client_label,
                )
                payload = room.payload()
                subscribers = list(self._subscribers.get(room_id, []))
            else:
                payload = room.payload()
                subscribers = []
                conflict_payload = existing_claim.payload()

        for subscriber in subscribers:
            subscriber.put(payload)

        response = {
            "ok": not conflict,
            "conflict": conflict,
            "role": role,
            "room_id": room_id,
            "state": payload,
        }
        if conflict:
            response["occupant"] = conflict_payload
        return response

    def release_role(self, room_id: str, role: str, client_id: str) -> Dict[str, object]:
        with self._lock:
            room = self._ensure_room(room_id)
            self._purge_expired_claims(room)
            existing_claim = room.claims.get(role)
            released = existing_claim is not None and existing_claim.client_id == client_id
            if released:
                room.claims.pop(role, None)
                payload = room.payload()
                subscribers = list(self._subscribers.get(room_id, []))
            else:
                payload = room.payload()
                subscribers = []

        for subscriber in subscribers:
            subscriber.put(payload)

        return {
            "ok": True,
            "released": released,
            "role": role,
            "room_id": room_id,
            "state": payload,
        }

    def _purge_expired_claims(self, room: RoomState) -> None:
        expired_roles = [
            role
            for role, claim in room.claims.items()
            if self._claim_is_expired(claim)
        ]
        for role in expired_roles:
            room.claims.pop(role, None)

    def _claim_is_expired(self, claim: RoleClaim) -> bool:
        last_seen_at = claim.last_seen_at or claim.claimed_at
        try:
            last_seen = datetime.fromisoformat(last_seen_at)
        except ValueError:
            return True
        age_seconds = (datetime.now(timezone.utc) - last_seen).total_seconds()
        return age_seconds > self._claim_ttl_seconds

    def _archive_if_idle(self, room_id: str, expected_version: int) -> None:
        with self._lock:
            room = self._rooms.get(room_id)
            if room is None or room.version != expected_version:
                return
            self._purge_expired_claims(room)

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

    @property
    def base_path(self) -> str:
        return self.server.base_path  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = self._strip_base_path(parsed.path)
        if path is None:
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        if path == "/api/ping":
            self._send_json({"ok": True, "ts": utc_now_iso()})
            return

        if path == "/api/server-info":
            self._send_json(
                {
                    "host": self.server.server_address[0],
                    "port": self.server.server_address[1],
                    "default_room": self.default_room,
                    "base_path": self.base_path,
                    "local_ip": self.local_ip,
                    "local_base_url": f"http://{self.local_ip}:{self.server.server_address[1]}{self.base_path}",
                    "archive_idle_seconds": self.server.archive_idle_seconds,  # type: ignore[attr-defined]
                    "claim_ttl_seconds": self.server.claim_ttl_seconds,  # type: ignore[attr-defined]
                }
            )
            return

        if path == "/api/state":
            room_id = self._room_id_from_query(parsed.query)
            self._send_json(self.store.get(room_id).payload())
            return

        if path == "/api/helper-state":
            room_id = self._room_id_from_query(parsed.query)
            self._send_json(self.store.get(room_id).helper_payload())
            return

        if path == "/api/stream":
            room_id = self._room_id_from_query(parsed.query)
            self._stream_room(room_id)
            return

        if path == "/" or path.startswith("/mobile/") or path.startswith("/pc/"):
            self._serve_index()
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
        path = self._strip_base_path(parsed.path)
        if path is None:
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        if path == "/api/settings":
            self._handle_settings_update()
            return

        if path == "/api/claim":
            self._handle_claim()
            return

        if path == "/api/release":
            self._handle_release()
            return

        if path != "/api/update":
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

    def _handle_settings_update(self) -> None:
        content_length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(content_length) or b"{}")
        room_id = (payload.get("room_id") or self.default_room).strip()
        raw_archive_idle_seconds = payload.get("archive_idle_seconds")

        if not room_id:
            self._send_json({"error": "room_id is required"}, status=HTTPStatus.BAD_REQUEST)
            return

        try:
            archive_idle_seconds = parse_archive_idle_seconds(str(raw_archive_idle_seconds))
        except (TypeError, ValueError):
            self._send_json({"error": "archive_idle_seconds must be a number >= 0.5"}, status=HTTPStatus.BAD_REQUEST)
            return

        room = self.store.update_settings(room_id=room_id, archive_idle_seconds=archive_idle_seconds)
        self._send_json(room.payload(), status=HTTPStatus.OK)

    def _handle_claim(self) -> None:
        content_length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(content_length) or b"{}")
        room_id = (payload.get("room_id") or self.default_room).strip()
        role = (payload.get("role") or "").strip()
        client_id = (payload.get("client_id") or "").strip()
        client_label = (payload.get("client_label") or "").strip()

        if not room_id:
            self._send_json({"error": "room_id is required"}, status=HTTPStatus.BAD_REQUEST)
            return
        if role not in {"mobile", "pc"}:
            self._send_json({"error": "role must be mobile or pc"}, status=HTTPStatus.BAD_REQUEST)
            return
        if not client_id:
            self._send_json({"error": "client_id is required"}, status=HTTPStatus.BAD_REQUEST)
            return

        result = self.store.claim_role(room_id=room_id, role=role, client_id=client_id, client_label=client_label)
        status = HTTPStatus.CONFLICT if result["conflict"] else HTTPStatus.OK
        self._send_json(result, status=status)

    def _handle_release(self) -> None:
        content_length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(content_length) or b"{}")
        room_id = (payload.get("room_id") or self.default_room).strip()
        role = (payload.get("role") or "").strip()
        client_id = (payload.get("client_id") or "").strip()

        if not room_id:
            self._send_json({"error": "room_id is required"}, status=HTTPStatus.BAD_REQUEST)
            return
        if role not in {"mobile", "pc"}:
            self._send_json({"error": "role must be mobile or pc"}, status=HTTPStatus.BAD_REQUEST)
            return
        if not client_id:
            self._send_json({"error": "client_id is required"}, status=HTTPStatus.BAD_REQUEST)
            return

        result = self.store.release_role(room_id=room_id, role=role, client_id=client_id)
        self._send_json(result, status=HTTPStatus.OK)

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

    def _serve_index(self) -> None:
        html = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")
        body = html.replace("__BASE_PATH__", self.base_path).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _strip_base_path(self, path: str) -> str | None:
        if not self.base_path:
            return path
        if path == self.base_path:
            return "/"
        if path.startswith(f"{self.base_path}/"):
            return path[len(self.base_path) :]
        return None

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
    parser.add_argument("--archive-idle-seconds", type=parse_archive_idle_seconds, default=ARCHIVE_IDLE_SECONDS)
    parser.add_argument("--claim-ttl-seconds", type=parse_claim_ttl_seconds, default=parse_claim_ttl_seconds(os.environ.get("CLAIM_TTL_SECONDS", str(CLAIM_TTL_SECONDS))))
    parser.add_argument("--base-path", type=normalize_base_path, default=normalize_base_path(os.environ.get("BASE_PATH", "")))
    return parser


def main() -> None:
    args = build_parser().parse_args()
    server = ThreadingHTTPServer((args.host, args.port), RelayHandler)
    server.store = RoomStore(archive_idle_seconds=args.archive_idle_seconds, claim_ttl_seconds=args.claim_ttl_seconds)  # type: ignore[attr-defined]
    server.default_room = args.default_room  # type: ignore[attr-defined]
    server.local_ip = detect_local_ip()  # type: ignore[attr-defined]
    server.archive_idle_seconds = args.archive_idle_seconds  # type: ignore[attr-defined]
    server.claim_ttl_seconds = args.claim_ttl_seconds  # type: ignore[attr-defined]
    server.base_path = args.base_path  # type: ignore[attr-defined]

    local_base = f"http://127.0.0.1:{args.port}{args.base_path}"
    lan_base = f"http://{server.local_ip}:{args.port}{args.base_path}"  # type: ignore[attr-defined]
    print(f"Doubao Input Sync server running on {local_base}")
    print(f"LAN access: {lan_base}")
    print(f"Default mobile page: {lan_base}/mobile/{args.default_room}")
    print(f"Default PC page: {local_base}/pc/{args.default_room}")
    print(f"Archive idle seconds: {args.archive_idle_seconds}")
    print(f"Claim TTL seconds: {args.claim_ttl_seconds}")
    print(f"Base path: {args.base_path or '/'}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
