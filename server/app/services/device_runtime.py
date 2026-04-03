from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from time import time
from typing import Mapping

from app.models import DeviceNodeRecord


def _now_ms() -> int:
    return int(time() * 1000)


@dataclass(frozen=True)
class DeviceRuntimeError(RuntimeError):
    code: str
    message: str
    status_code: int

    def __str__(self) -> str:
        return self.message


class DeviceRuntimeService:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)

    def register_device(
        self,
        *,
        actor_user_id: int,
        device_id: str,
        device_type: str,
        boot_id: str | None,
        transport: str | None,
        metadata: Mapping[str, object] | None,
    ) -> DeviceNodeRecord:
        normalized_device_id = self._normalize_key(device_id)
        normalized_device_type = self._normalize_key(device_type)
        if not normalized_device_id:
            raise DeviceRuntimeError("invalid_device_id", "Device id must not be empty", 422)
        if not normalized_device_type:
            raise DeviceRuntimeError("invalid_device_type", "Device type must not be empty", 422)

        now_ms = _now_ms()
        with self._connect() as connection:
            existing = self._read_row(connection, device_id=normalized_device_id)
            merged_metadata = self._decode_metadata(existing["metadata_json"]) if existing is not None else {}

            registration_payload: dict[str, object] = {
                "actor_user_id": actor_user_id,
                "registered_at_ms": now_ms,
            }
            if boot_id is not None and boot_id.strip():
                registration_payload["boot_id"] = boot_id.strip()
            if transport is not None and transport.strip():
                registration_payload["transport"] = transport.strip()
            if metadata:
                registration_payload["metadata"] = dict(metadata)

            merged_metadata["device_uid"] = normalized_device_id
            merged_metadata["device_type"] = normalized_device_type
            merged_metadata["registration"] = registration_payload

            self._upsert(
                connection,
                device_id=normalized_device_id,
                device_type=normalized_device_type,
                status="registered",
                last_seen_ms=now_ms,
                metadata=merged_metadata,
            )

            row = self._read_row(connection, device_id=normalized_device_id)
            if row is None:
                raise DeviceRuntimeError("device_register_failed", "Failed to register device", 500)
            return self._row_to_record(row)

    def record_heartbeat(
        self,
        *,
        actor_user_id: int,
        device_id: str,
        device_type: str,
        heartbeat_status: str,
        uptime_ms: int,
        queue_depth: int,
        metrics: Mapping[str, object] | None,
    ) -> DeviceNodeRecord:
        normalized_device_id = self._normalize_key(device_id)
        normalized_device_type = self._normalize_key(device_type)
        normalized_status = self._normalize_status(heartbeat_status)
        if not normalized_device_id:
            raise DeviceRuntimeError("invalid_device_id", "Device id must not be empty", 422)
        if not normalized_device_type:
            raise DeviceRuntimeError("invalid_device_type", "Device type must not be empty", 422)
        if uptime_ms < 0:
            raise DeviceRuntimeError("invalid_uptime", "Heartbeat uptime must be >= 0", 422)
        if queue_depth < 0:
            raise DeviceRuntimeError("invalid_queue_depth", "Heartbeat queue_depth must be >= 0", 422)

        now_ms = _now_ms()
        with self._connect() as connection:
            row = self._read_row(connection, device_id=normalized_device_id)
            if row is None:
                raise DeviceRuntimeError("device_not_registered", "Device is not registered", 404)
            if str(row["device_type"]) != normalized_device_type:
                raise DeviceRuntimeError("device_type_mismatch", "Registered device type mismatch", 409)

            merged_metadata = self._decode_metadata(row["metadata_json"])
            merged_metadata["last_heartbeat"] = {
                "actor_user_id": actor_user_id,
                "status": normalized_status,
                "uptime_ms": int(uptime_ms),
                "queue_depth": int(queue_depth),
                "metrics": dict(metrics or {}),
                "reported_at_ms": now_ms,
            }

            self._upsert(
                connection,
                device_id=normalized_device_id,
                device_type=normalized_device_type,
                status=f"heartbeat_{normalized_status}",
                last_seen_ms=now_ms,
                metadata=merged_metadata,
            )

            updated = self._read_row(connection, device_id=normalized_device_id)
            if updated is None:
                raise DeviceRuntimeError("heartbeat_update_failed", "Failed to store heartbeat", 500)
            return self._row_to_record(updated)

    def record_telemetry(
        self,
        *,
        actor_user_id: int,
        device_id: str,
        device_type: str,
        snapshot: Mapping[str, object],
        source_message_id: str | None,
    ) -> DeviceNodeRecord:
        normalized_device_id = self._normalize_key(device_id)
        normalized_device_type = self._normalize_key(device_type)
        if not normalized_device_id:
            raise DeviceRuntimeError("invalid_device_id", "Device id must not be empty", 422)
        if not normalized_device_type:
            raise DeviceRuntimeError("invalid_device_type", "Device type must not be empty", 422)

        now_ms = _now_ms()
        with self._connect() as connection:
            row = self._read_row(connection, device_id=normalized_device_id)
            if row is None:
                raise DeviceRuntimeError("device_not_registered", "Device is not registered", 404)
            if str(row["device_type"]) != normalized_device_type:
                raise DeviceRuntimeError("device_type_mismatch", "Registered device type mismatch", 409)

            merged_metadata = self._decode_metadata(row["metadata_json"])
            telemetry_payload: dict[str, object] = {
                "actor_user_id": actor_user_id,
                "snapshot": dict(snapshot),
                "reported_at_ms": now_ms,
            }
            if source_message_id is not None and source_message_id.strip():
                telemetry_payload["source_message_id"] = source_message_id.strip()
            merged_metadata["last_telemetry"] = telemetry_payload

            self._upsert(
                connection,
                device_id=normalized_device_id,
                device_type=normalized_device_type,
                status="telemetry",
                last_seen_ms=now_ms,
                metadata=merged_metadata,
            )

            updated = self._read_row(connection, device_id=normalized_device_id)
            if updated is None:
                raise DeviceRuntimeError("telemetry_update_failed", "Failed to store telemetry", 500)
            return self._row_to_record(updated)

    def get_device_status(self, *, device_id: str) -> DeviceNodeRecord:
        normalized_device_id = self._normalize_key(device_id)
        if not normalized_device_id:
            raise DeviceRuntimeError("invalid_device_id", "Device id must not be empty", 422)

        with self._connect() as connection:
            row = self._read_row(connection, device_id=normalized_device_id)
            if row is None:
                raise DeviceRuntimeError("device_not_found", "Device node was not found", 404)
            return self._row_to_record(row)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _read_row(connection: sqlite3.Connection, *, device_id: str) -> sqlite3.Row | None:
        return connection.execute(
            "SELECT id, device_type, status, last_seen_ms, metadata_json FROM device_registry WHERE id = ?",
            (device_id,),
        ).fetchone()

    @staticmethod
    def _upsert(
        connection: sqlite3.Connection,
        *,
        device_id: str,
        device_type: str,
        status: str,
        last_seen_ms: int,
        metadata: Mapping[str, object],
    ) -> None:
        connection.execute(
            """
            INSERT INTO device_registry(id, device_type, status, last_seen_ms, metadata_json)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id)
            DO UPDATE SET
                device_type = excluded.device_type,
                status = excluded.status,
                last_seen_ms = excluded.last_seen_ms,
                metadata_json = excluded.metadata_json
            """,
            (
                device_id,
                device_type,
                status,
                int(last_seen_ms),
                json.dumps(dict(metadata), ensure_ascii=False, separators=(",", ":")),
            ),
        )

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> DeviceNodeRecord:
        return DeviceNodeRecord(
            device_id=str(row["id"]),
            device_type=str(row["device_type"]),
            status=str(row["status"]),
            last_seen_ms=int(row["last_seen_ms"]) if row["last_seen_ms"] is not None else None,
            metadata=DeviceRuntimeService._decode_metadata(row["metadata_json"]),
        )

    @staticmethod
    def _decode_metadata(raw: object) -> dict[str, object]:
        if not isinstance(raw, str) or not raw.strip():
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if not isinstance(parsed, dict):
            return {}
        return dict(parsed)

    @staticmethod
    def _normalize_key(value: str) -> str:
        return value.strip()

    @staticmethod
    def _normalize_status(value: str) -> str:
        normalized = value.strip().lower().replace("-", "_")
        if not normalized:
            return "unknown"
        clean = "".join(ch for ch in normalized if ch.isalnum() or ch == "_")
        return clean or "unknown"
