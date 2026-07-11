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
from typing import Dict, List, Optional
from urllib.parse import parse_qs, urlparse


APP_ROOT = Path(__file__).resolve().parent
STATIC_ROOT = APP_ROOT / "static"
ARCHIVE_IDLE_SECONDS = float(os.environ.get("ARCHIVE_IDLE_SECONDS", "2.0"))
CLAIM_TTL_SECONDS = float(os.environ.get("CLAIM_TTL_SECONDS", "45.0"))
MAX_HISTORY_ITEMS = 50
CAPTURE_MODES = {"auto", "manual"}
THEMES = {"warm", "green", "blue", "rose", "slate"}


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


def parse_capture_mode(raw_value: str) -> str:
    value = (raw_value or "").strip().lower()
    if value not in CAPTURE_MODES:
        raise ValueError("capture mode must be auto or manual")
    return value


def parse_theme(raw_value: str) -> str:
    value = (raw_value or "").strip().lower()
    if value not in THEMES:
        raise ValueError("theme is not supported")
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
    desktop_received_at: str = ""
    desktop_received_by: str = ""
    desktop_delivery_action: str = ""

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
    capture_mode: str = "auto"
    theme: str = ""
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
                "capture_mode": self.capture_mode,
                "theme": self.theme,
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
            capture_mode=self.capture_mode,
            theme=self.theme,
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
                    desktop_received_at=entry.desktop_received_at,
                    desktop_received_by=entry.desktop_received_by,
                    desktop_delivery_action=entry.desktop_delivery_action,
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
        self._archive_generations: Dict[str, int] = {}
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

    def update(
        self,
        room_id: str,
        text: str,
        source: str,
        capture_mode: Optional[str] = None,
    ) -> RoomState:
        timer: Optional[threading.Timer] = None
        with self._lock:
            room = self._ensure_room(room_id)
            self._purge_expired_claims(room)
            generation = self._invalidate_archive_timer_locked(room_id)
            room.text = text
            room.source = source
            if capture_mode is not None:
                room.capture_mode = capture_mode
            room.version += 1
            room.updated_at = utc_now_iso()
            version = room.version
            payload = room.payload()
            subscribers = list(self._subscribers.get(room_id, []))
            timer = self._new_archive_timer_locked(room, version, generation)

        for subscriber in subscribers:
            subscriber.put(payload)

        if timer is not None:
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

    def update_settings(
        self,
        room_id: str,
        archive_idle_seconds: Optional[float] = None,
        capture_mode: Optional[str] = None,
        theme: Optional[str] = None,
    ) -> RoomState:
        timer: Optional[threading.Timer] = None
        with self._lock:
            room = self._ensure_room(room_id)
            self._purge_expired_claims(room)
            affects_archive_timer = archive_idle_seconds is not None or capture_mode is not None
            generation = self._archive_generations.get(room_id, 0)
            if affects_archive_timer:
                generation = self._invalidate_archive_timer_locked(room_id)
            if archive_idle_seconds is not None:
                room.archive_idle_seconds = archive_idle_seconds
            if capture_mode is not None:
                room.capture_mode = capture_mode
            if theme is not None:
                room.theme = theme
            payload = room.payload()
            subscribers = list(self._subscribers.get(room_id, []))
            if affects_archive_timer:
                timer = self._new_archive_timer_locked(room, room.version, generation)

        for subscriber in subscribers:
            subscriber.put(payload)

        if timer is not None:
            timer.start()
        return room.clone()

    def capture_now(self, room_id: str, expected_version: Optional[int] = None) -> Dict[str, object]:
        with self._lock:
            room = self._ensure_room(room_id)
            self._purge_expired_claims(room)

            if expected_version is not None and room.version != expected_version:
                return {
                    "ok": False,
                    "error": "version_conflict",
                    "expected_version": expected_version,
                    "actual_version": room.version,
                    "state": room.payload(),
                }

            self._invalidate_archive_timer_locked(room_id)

            if not room.text.strip():
                return {
                    "ok": False,
                    "error": "empty_text",
                    "state": room.payload(),
                }

            if room.history and room.history[-1].version == room.version:
                return {
                    "ok": True,
                    "archived": False,
                    "reason": "already_captured",
                    "archive": room.history[-1].payload(),
                    "state": room.payload(),
                }

            archive = self._append_archive_locked(room)
            payload = room.payload()
            subscribers = list(self._subscribers.get(room_id, []))

        for subscriber in subscribers:
            subscriber.put(payload)

        return {
            "ok": True,
            "archived": True,
            "archive": archive.payload(),
            "state": payload,
        }

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

    def acknowledge_archive(self, room_id: str, archive_id: int, client_id: str, action: str) -> Dict[str, object]:
        with self._lock:
            room = self._ensure_room(room_id)
            self._purge_expired_claims(room)
            target = next((entry for entry in room.history if entry.archive_id == archive_id), None)
            if target is None:
                return {
                    "ok": False,
                    "error": "archive_id not found",
                    "room_id": room_id,
                    "archive_id": archive_id,
                    "state": room.payload(),
                }

            target.desktop_received_at = target.desktop_received_at or utc_now_iso()
            target.desktop_received_by = client_id
            target.desktop_delivery_action = action
            payload = room.payload()
            subscribers = list(self._subscribers.get(room_id, []))

        for subscriber in subscribers:
            subscriber.put(payload)

        return {
            "ok": True,
            "room_id": room_id,
            "archive_id": archive_id,
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

    def _invalidate_archive_timer_locked(self, room_id: str) -> int:
        previous_timer = self._archive_timers.pop(room_id, None)
        if previous_timer is not None:
            previous_timer.cancel()
        generation = self._archive_generations.get(room_id, 0) + 1
        self._archive_generations[room_id] = generation
        return generation

    def _new_archive_timer_locked(
        self,
        room: RoomState,
        expected_version: int,
        expected_generation: int,
    ) -> Optional[threading.Timer]:
        if room.capture_mode != "auto" or not room.text.strip():
            return None
        if room.history and room.history[-1].version == room.version:
            return None
        timer = threading.Timer(
            room.archive_idle_seconds,
            self._archive_if_idle,
            args=(room.room_id, expected_version, expected_generation),
        )
        timer.daemon = True
        self._archive_timers[room.room_id] = timer
        return timer

    def _append_archive_locked(self, room: RoomState) -> ArchiveEntry:
        next_archive_id = self._archive_ids.get(room.room_id, 0) + 1
        self._archive_ids[room.room_id] = next_archive_id
        archive = ArchiveEntry(
            archive_id=next_archive_id,
            text=room.text,
            chars=len(room.text),
            source=room.source,
            version=room.version,
            archived_at=utc_now_iso(),
        )
        room.history.append(archive)
        room.history = room.history[-MAX_HISTORY_ITEMS:]
        return archive

    def _archive_if_idle(self, room_id: str, expected_version: int, expected_generation: int) -> None:
        with self._lock:
            room = self._rooms.get(room_id)
            if (
                room is None
                or room.version != expected_version
                or room.capture_mode != "auto"
                or self._archive_generations.get(room_id) != expected_generation
            ):
                return
            self._purge_expired_claims(room)

            self._archive_timers.pop(room_id, None)

            if not room.text.strip():
                return

            if room.history and room.history[-1].text == room.text:
                return

            self._append_archive_locked(room)
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
                    "capture_modes": sorted(CAPTURE_MODES),
                    "themes": sorted(THEMES),
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

        if path == "/api/archive-ack":
            self._handle_archive_ack()
            return

        if path == "/api/capture":
            self._handle_capture()
            return

        if path != "/api/update":
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(content_length) or b"{}")
        room_id = (payload.get("room_id") or self.default_room).strip()
        text = payload.get("text", "")
        source = (payload.get("source") or "unknown").strip()
        raw_capture_mode = payload.get("capture_mode")

        if not room_id:
            self._send_json({"error": "room_id is required"}, status=HTTPStatus.BAD_REQUEST)
            return

        if not isinstance(text, str):
            self._send_json({"error": "text must be a string"}, status=HTTPStatus.BAD_REQUEST)
            return

        capture_mode: Optional[str] = None
        if raw_capture_mode is not None:
            try:
                capture_mode = parse_capture_mode(str(raw_capture_mode))
            except (TypeError, ValueError):
                self._send_json({"error": "capture_mode must be auto or manual"}, status=HTTPStatus.BAD_REQUEST)
                return

        room = self.store.update(
            room_id=room_id,
            text=text,
            source=source,
            capture_mode=capture_mode,
        )
        self._send_json(room.payload(), status=HTTPStatus.CREATED)

    def _handle_settings_update(self) -> None:
        content_length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(content_length) or b"{}")
        room_id = (payload.get("room_id") or self.default_room).strip()
        has_archive_idle_seconds = "archive_idle_seconds" in payload
        has_capture_mode = "capture_mode" in payload
        has_theme = "theme" in payload

        if not room_id:
            self._send_json({"error": "room_id is required"}, status=HTTPStatus.BAD_REQUEST)
            return

        if not has_archive_idle_seconds and not has_capture_mode and not has_theme:
            self._send_json(
                {"error": "archive_idle_seconds, capture_mode, or theme is required"},
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        archive_idle_seconds: Optional[float] = None
        if has_archive_idle_seconds:
            try:
                archive_idle_seconds = parse_archive_idle_seconds(str(payload.get("archive_idle_seconds")))
            except (TypeError, ValueError):
                self._send_json({"error": "archive_idle_seconds must be a number >= 0.5"}, status=HTTPStatus.BAD_REQUEST)
                return

        capture_mode: Optional[str] = None
        if has_capture_mode:
            try:
                capture_mode = parse_capture_mode(str(payload.get("capture_mode")))
            except (TypeError, ValueError):
                self._send_json({"error": "capture_mode must be auto or manual"}, status=HTTPStatus.BAD_REQUEST)
                return

        theme: Optional[str] = None
        if has_theme:
            try:
                theme = parse_theme(str(payload.get("theme")))
            except (TypeError, ValueError):
                self._send_json({"error": "theme is not supported"}, status=HTTPStatus.BAD_REQUEST)
                return

        room = self.store.update_settings(
            room_id=room_id,
            archive_idle_seconds=archive_idle_seconds,
            capture_mode=capture_mode,
            theme=theme,
        )
        self._send_json(room.payload(), status=HTTPStatus.OK)

    def _handle_capture(self) -> None:
        content_length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(content_length) or b"{}")
        room_id = (payload.get("room_id") or self.default_room).strip()

        if not room_id:
            self._send_json({"error": "room_id is required"}, status=HTTPStatus.BAD_REQUEST)
            return

        expected_version: Optional[int] = None
        if payload.get("expected_version") is not None:
            try:
                expected_version = int(payload.get("expected_version"))
            except (TypeError, ValueError):
                self._send_json({"error": "expected_version must be an integer"}, status=HTTPStatus.BAD_REQUEST)
                return

        result = self.store.capture_now(room_id=room_id, expected_version=expected_version)
        if result.get("ok"):
            status = HTTPStatus.OK
        elif result.get("error") == "version_conflict":
            status = HTTPStatus.CONFLICT
        elif result.get("error") == "empty_text":
            status = HTTPStatus.UNPROCESSABLE_ENTITY
        else:
            status = HTTPStatus.BAD_REQUEST
        self._send_json(result, status=status)

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

    def _handle_archive_ack(self) -> None:
        content_length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(content_length) or b"{}")
        room_id = (payload.get("room_id") or self.default_room).strip()
        client_id = (payload.get("client_id") or "desktop-helper").strip()
        action = (payload.get("action") or "received").strip()

        if not room_id:
            self._send_json({"error": "room_id is required"}, status=HTTPStatus.BAD_REQUEST)
            return
        try:
            archive_id = int(payload.get("archive_id"))
        except (TypeError, ValueError):
            self._send_json({"error": "archive_id must be an integer"}, status=HTTPStatus.BAD_REQUEST)
            return
        if archive_id <= 0:
            self._send_json({"error": "archive_id must be positive"}, status=HTTPStatus.BAD_REQUEST)
            return

        result = self.store.acknowledge_archive(
            room_id=room_id,
            archive_id=archive_id,
            client_id=client_id,
            action=action,
        )
        status = HTTPStatus.OK if result["ok"] else HTTPStatus.NOT_FOUND
        self._send_json(result, status=status)

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
    parser.add_argument("--port", type=int, default=18766)
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
