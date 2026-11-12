# DEPRECATED RPi-Only: требует внутренние контроллеры, не активно в RPi-only архитектуре.
from __future__ import annotations

"""Edge sync event queue.

Conflict resolution strategy: duplicates are resolved with last-write-wins by
``created_at_ms`` unless an event carries an explicit manual conflict marker
(``conflict_resolution == "manual"`` or payload ``conflict_marker``). Manual
conflicts are retained with status ``conflict`` for operator review; automatic
duplicates tombstone older events and keep the latest event active.
"""

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from time import time
from typing import Any

from app.config import get_settings
from app.db.migrate import _extract_sqlite_path
from app.db.connection import connect_sqlite


PENDING_STATUS = "pending"
SENT_STATUS = "sent"
ACKNOWLEDGED_STATUS = "acknowledged"
CONFLICT_STATUS = "conflict"
EXPIRED_STATUS = "expired"
VALID_STATUSES = {PENDING_STATUS, SENT_STATUS, ACKNOWLEDGED_STATUS, CONFLICT_STATUS, EXPIRED_STATUS}
DEFAULT_TTL_MS = 7 * 24 * 60 * 60 * 1000


def _now_ms() -> int:
    return int(time() * 1000)


def _canonical_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _make_idempotency_key(event_type: str, payload: dict[str, Any], source_id: str, target_id: str) -> str:
    explicit = payload.get("idempotency_key") or payload.get("_idempotency_key")
    if explicit is not None and str(explicit).strip():
        return str(explicit).strip()
    material = _canonical_payload(
        {
            "event_type": event_type,
            "payload": payload,
            "source_node_id": source_id,
            "target_node_id": target_id,
        }
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _default_db_path() -> Path:
    return _extract_sqlite_path(get_settings().database_url)


@dataclass(frozen=True)
class SyncEvent:
    id: int
    event_type: str
    payload: dict[str, Any]
    source_node_id: str
    target_node_id: str
    idempotency_key: str
    status: str
    created_at_ms: int
    last_attempt_at_ms: int | None
    attempt_count: int
    expires_at_ms: int | None
    conflict_resolution: str | None


class SyncQueueService:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)

    def enqueue_event(self, event_type: str, payload: dict[str, Any], source_id: str, target_id: str) -> SyncEvent:
        event_type = self._require_text(event_type, "event_type")
        source_id = self._require_text(source_id, "source_id")
        target_id = self._require_text(target_id, "target_id")
        payload = dict(payload or {})
        now_ms = int(payload.get("created_at_ms") or _now_ms())
        expires_at_ms = payload.get("expires_at_ms")
        if expires_at_ms is None:
            expires_at_ms = now_ms + DEFAULT_TTL_MS
        conflict_resolution = payload.get("conflict_resolution")
        if conflict_resolution is not None:
            conflict_resolution = str(conflict_resolution)
        idempotency_key = _make_idempotency_key(event_type, payload, source_id, target_id)
        payload_json = _canonical_payload(payload)

        with self._connect() as connection:
            self._ensure_schema(connection)
            existing = self._fetch_by_idempotency_key(connection, idempotency_key)
            if existing is not None:
                return self.resolve_duplicates(idempotency_key)
            cursor = connection.execute(
                """
                INSERT INTO sync_event_queue(
                    event_type, payload_json, source_node_id, target_node_id,
                    idempotency_key, status, created_at_ms, last_attempt_at_ms,
                    attempt_count, expires_at_ms, conflict_resolution
                )
                VALUES (?, ?, ?, ?, ?, 'pending', ?, NULL, 0, ?, ?)
                """,
                (
                    event_type,
                    payload_json,
                    source_id,
                    target_id,
                    idempotency_key,
                    now_ms,
                    int(expires_at_ms) if expires_at_ms is not None else None,
                    conflict_resolution,
                ),
            )
            return self._get_event(connection, int(cursor.lastrowid))

    def dequeue_pending(self, limit: int, target_node_id: str | None = None) -> list[SyncEvent]:
        safe_limit = max(1, min(int(limit), 500))
        now_ms = _now_ms()
        with self._connect() as connection:
            self._ensure_schema(connection)
            self._expire_events(connection, now_ms)
            if target_node_id:
                rows = connection.execute(
                    """
                    SELECT * FROM sync_event_queue
                    WHERE status = 'pending' AND target_node_id = ?
                    ORDER BY created_at_ms ASC, id ASC
                    LIMIT ?
                    """,
                    (target_node_id, safe_limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM sync_event_queue
                    WHERE status = 'pending'
                    ORDER BY created_at_ms ASC, id ASC
                    LIMIT ?
                    """,
                    (safe_limit,),
                ).fetchall()
            return [self._row_to_event(row) for row in rows]

    def mark_sent(self, event_id: int) -> SyncEvent:
        now_ms = _now_ms()
        with self._connect() as connection:
            self._ensure_schema(connection)
            connection.execute(
                """
                UPDATE sync_event_queue
                SET status = 'sent', last_attempt_at_ms = ?, attempt_count = attempt_count + 1
                WHERE id = ? AND status IN ('pending', 'sent')
                """,
                (now_ms, int(event_id)),
            )
            return self._get_event(connection, int(event_id))

    def mark_acknowledged(self, event_id: int) -> SyncEvent:
        now_ms = _now_ms()
        with self._connect() as connection:
            self._ensure_schema(connection)
            connection.execute(
                """
                UPDATE sync_event_queue
                SET status = 'acknowledged', last_attempt_at_ms = ?
                WHERE id = ?
                """,
                (now_ms, int(event_id)),
            )
            return self._get_event(connection, int(event_id))

    def mark_conflict(self, event_id: int, reason: str) -> SyncEvent:
        now_ms = _now_ms()
        reason = str(reason or "manual_conflict")
        with self._connect() as connection:
            self._ensure_schema(connection)
            connection.execute(
                """
                UPDATE sync_event_queue
                SET status = 'conflict', conflict_resolution = COALESCE(conflict_resolution, 'manual')
                WHERE id = ?
                """,
                (int(event_id),),
            )
            connection.execute(
                """
                INSERT INTO sync_tombstones(event_id, tombstoned_at_ms, reason)
                VALUES (?, ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET
                    tombstoned_at_ms = excluded.tombstoned_at_ms,
                    reason = excluded.reason
                """,
                (int(event_id), now_ms, reason),
            )
            return self._get_event(connection, int(event_id))

    def garbage_collect_expired(self) -> int:
        now_ms = _now_ms()
        with self._connect() as connection:
            self._ensure_schema(connection)
            return self._expire_events(connection, now_ms)

    def resolve_duplicates(self, idempotency_key: str) -> SyncEvent:
        key = self._require_text(idempotency_key, "idempotency_key")
        now_ms = _now_ms()
        with self._connect() as connection:
            self._ensure_schema(connection)
            rows = connection.execute(
                """
                SELECT * FROM sync_event_queue
                WHERE idempotency_key = ?
                ORDER BY created_at_ms DESC, id DESC
                """,
                (key,),
            ).fetchall()
            if not rows:
                raise KeyError(f"sync event idempotency key not found: {key}")
            winner = rows[0]
            manual = any(
                str(row["conflict_resolution"] or "").lower() == "manual"
                or bool(self._payload_from_row(row).get("conflict_marker"))
                for row in rows
            )
            if manual:
                for row in rows:
                    connection.execute(
                        "UPDATE sync_event_queue SET status = 'conflict', conflict_resolution = 'manual' WHERE id = ?",
                        (int(row["id"]),),
                    )
                return self._get_event(connection, int(winner["id"]))

            for row in rows[1:]:
                connection.execute(
                    "UPDATE sync_event_queue SET status = 'expired' WHERE id = ?",
                    (int(row["id"]),),
                )
                connection.execute(
                    """
                    INSERT INTO sync_tombstones(event_id, tombstoned_at_ms, reason)
                    VALUES (?, ?, 'duplicate_last_write_wins')
                    ON CONFLICT(event_id) DO UPDATE SET
                        tombstoned_at_ms = excluded.tombstoned_at_ms,
                        reason = excluded.reason
                    """,
                    (int(row["id"]), now_ms),
                )
            return self._get_event(connection, int(winner["id"]))

    def _connect(self) -> sqlite3.Connection:
        return connect_sqlite(self._db_path)

    @staticmethod
    def _ensure_schema(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sync_event_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                source_node_id TEXT NOT NULL,
                target_node_id TEXT NOT NULL,
                idempotency_key TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','sent','acknowledged','conflict','expired')),
                created_at_ms INTEGER NOT NULL,
                last_attempt_at_ms INTEGER,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                expires_at_ms INTEGER,
                conflict_resolution TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sync_tombstones (
                event_id INTEGER PRIMARY KEY,
                tombstoned_at_ms INTEGER NOT NULL,
                reason TEXT NOT NULL,
                FOREIGN KEY (event_id) REFERENCES sync_event_queue(id) ON DELETE CASCADE
            )
            """
        )

    def _expire_events(self, connection: sqlite3.Connection, now_ms: int) -> int:
        rows = connection.execute(
            """
            SELECT id FROM sync_event_queue
            WHERE status IN ('pending', 'sent') AND expires_at_ms IS NOT NULL AND expires_at_ms <= ?
            """,
            (now_ms,),
        ).fetchall()
        for row in rows:
            event_id = int(row["id"])
            connection.execute("UPDATE sync_event_queue SET status = 'expired' WHERE id = ?", (event_id,))
            connection.execute(
                """
                INSERT INTO sync_tombstones(event_id, tombstoned_at_ms, reason)
                VALUES (?, ?, 'expired')
                ON CONFLICT(event_id) DO UPDATE SET
                    tombstoned_at_ms = excluded.tombstoned_at_ms,
                    reason = excluded.reason
                """,
                (event_id, now_ms),
            )
        return len(rows)

    @staticmethod
    def _require_text(value: str, field: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError(f"{field} is required")
        return normalized

    def _fetch_by_idempotency_key(self, connection: sqlite3.Connection, key: str) -> sqlite3.Row | None:
        return connection.execute("SELECT * FROM sync_event_queue WHERE idempotency_key = ?", (key,)).fetchone()

    def _get_event(self, connection: sqlite3.Connection, event_id: int) -> SyncEvent:
        row = connection.execute("SELECT * FROM sync_event_queue WHERE id = ?", (event_id,)).fetchone()
        if row is None:
            raise KeyError(f"sync event not found: {event_id}")
        return self._row_to_event(row)

    @staticmethod
    def _payload_from_row(row: sqlite3.Row) -> dict[str, Any]:
        try:
            parsed = json.loads(str(row["payload_json"]))
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @classmethod
    def _row_to_event(cls, row: sqlite3.Row) -> SyncEvent:
        return SyncEvent(
            id=int(row["id"]),
            event_type=str(row["event_type"]),
            payload=cls._payload_from_row(row),
            source_node_id=str(row["source_node_id"]),
            target_node_id=str(row["target_node_id"]),
            idempotency_key=str(row["idempotency_key"]),
            status=str(row["status"]),
            created_at_ms=int(row["created_at_ms"]),
            last_attempt_at_ms=int(row["last_attempt_at_ms"]) if row["last_attempt_at_ms"] is not None else None,
            attempt_count=int(row["attempt_count"]),
            expires_at_ms=int(row["expires_at_ms"]) if row["expires_at_ms"] is not None else None,
            conflict_resolution=str(row["conflict_resolution"]) if row["conflict_resolution"] is not None else None,
        )


def _service(db_path: str | Path | None = None) -> SyncQueueService:
    return SyncQueueService(db_path or _default_db_path())


def enqueue_event(event_type: str, payload: dict[str, Any], source_id: str, target_id: str) -> SyncEvent:
    return _service().enqueue_event(event_type, payload, source_id, target_id)


def dequeue_pending(limit: int) -> list[SyncEvent]:
    return _service().dequeue_pending(limit)


def mark_sent(event_id: int) -> SyncEvent:
    return _service().mark_sent(event_id)


def mark_acknowledged(event_id: int) -> SyncEvent:
    return _service().mark_acknowledged(event_id)


def mark_conflict(event_id: int, reason: str) -> SyncEvent:
    return _service().mark_conflict(event_id, reason)


def garbage_collect_expired() -> int:
    return _service().garbage_collect_expired()


def resolve_duplicates(idempotency_key: str) -> SyncEvent:
    return _service().resolve_duplicates(idempotency_key)
