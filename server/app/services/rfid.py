# DEPRECATED in RPi-Only architecture (v1.00.00). Code kept for reference.
from __future__ import annotations

import hashlib
import hmac
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from time import time

from app.models import (
    AccessMode,
    RfidAccessEvent,
    RfidCard,
    RfidCardDraft,
    RfidEventAction,
    RfidModeDecision,
    UserRole,
    UserStatus,
)


def _now_ms() -> int:
    return int(time() * 1000)


@dataclass(frozen=True)
class RfidError(RuntimeError):
    code: str
    message: str
    status_code: int

    def __str__(self) -> str:
        return self.message


class RfidService:
    def __init__(self, db_path: str | Path, *, uid_pepper: str) -> None:
        self._db_path = Path(db_path)
        self._uid_pepper = uid_pepper

    def enroll_card(
        self,
        *,
        actor_user_id: int,
        draft: RfidCardDraft,
        is_active: bool = True,
    ) -> RfidCard:
        with self._connect() as connection:
            self._require_active_admin(connection, actor_user_id)

            normalized_uid = self._normalize_uid(draft.card_uid)
            uid_hash = self._uid_hash(normalized_uid)
            uid_mask = self._uid_mask(normalized_uid)

            now_ms = _now_ms()
            connection.execute(
                """
                INSERT INTO rfid_cards(
                    uid_hash,
                    uid_mask,
                    card_label,
                    note,
                    is_active,
                    created_by_user_id,
                    created_at_ms,
                    updated_at_ms,
                    last_used_at_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
                ON CONFLICT(uid_hash)
                DO UPDATE SET
                    uid_mask = excluded.uid_mask,
                    card_label = excluded.card_label,
                    note = excluded.note,
                    is_active = excluded.is_active,
                    updated_at_ms = excluded.updated_at_ms
                """,
                (
                    uid_hash,
                    uid_mask,
                    draft.card_label.strip(),
                    (draft.note or "").strip() or None,
                    1 if is_active else 0,
                    actor_user_id,
                    now_ms,
                    now_ms,
                ),
            )

            row = connection.execute(
                "SELECT * FROM rfid_cards WHERE uid_hash = ?",
                (uid_hash,),
            ).fetchone()
            if row is None:
                raise RfidError("card_enroll_failed", "Failed to enroll RFID card", 500)

            card = self._row_to_card(row)
            self._insert_event(
                connection,
                card_id=card.card_id,
                uid_mask=card.uid_mask,
                action=RfidEventAction.CARD_ENROLL,
                granted=True,
                requested_mode=None,
                resolved_mode=self._read_mode(connection),
                reason=None,
                source="admin_panel",
                actor_user_id=actor_user_id,
                created_at_ms=now_ms,
            )
            return card

    def list_cards(
        self,
        *,
        actor_user_id: int,
        include_inactive: bool = True,
        limit: int = 200,
        offset: int = 0,
    ) -> list[RfidCard]:
        safe_limit = min(max(limit, 1), 500)
        safe_offset = max(offset, 0)

        with self._connect() as connection:
            self._require_active_admin(connection, actor_user_id)

            if include_inactive:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM rfid_cards
                    ORDER BY updated_at_ms DESC, id DESC
                    LIMIT ? OFFSET ?
                    """,
                    (safe_limit, safe_offset),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM rfid_cards
                    WHERE is_active = 1
                    ORDER BY updated_at_ms DESC, id DESC
                    LIMIT ? OFFSET ?
                    """,
                    (safe_limit, safe_offset),
                ).fetchall()

            return [self._row_to_card(row) for row in rows]

    def set_card_active(
        self,
        *,
        actor_user_id: int,
        card_id: int,
        is_active: bool,
    ) -> RfidCard:
        with self._connect() as connection:
            self._require_active_admin(connection, actor_user_id)

            now_ms = _now_ms()
            updated = connection.execute(
                """
                UPDATE rfid_cards
                SET is_active = ?,
                    updated_at_ms = ?
                WHERE id = ?
                """,
                (1 if is_active else 0, now_ms, card_id),
            ).rowcount
            if updated <= 0:
                raise RfidError("card_not_found", "RFID card was not found", 404)

            row = connection.execute(
                "SELECT * FROM rfid_cards WHERE id = ?",
                (card_id,),
            ).fetchone()
            if row is None:
                raise RfidError("card_not_found", "RFID card was not found", 404)

            card = self._row_to_card(row)
            self._insert_event(
                connection,
                card_id=card.card_id,
                uid_mask=card.uid_mask,
                action=RfidEventAction.CARD_TOGGLE_ACTIVE,
                granted=True,
                requested_mode=None,
                resolved_mode=self._read_mode(connection),
                reason=f"is_active={str(card.is_active).lower()}",
                source="admin_panel",
                actor_user_id=actor_user_id,
                created_at_ms=now_ms,
            )
            return card

    def delete_card(self, *, actor_user_id: int, card_id: int) -> tuple[int, str]:
        with self._connect() as connection:
            self._require_active_admin(connection, actor_user_id)

            row = connection.execute(
                "SELECT * FROM rfid_cards WHERE id = ?",
                (card_id,),
            ).fetchone()
            if row is None:
                raise RfidError("card_not_found", "RFID card was not found", 404)

            card = self._row_to_card(row)
            connection.execute("DELETE FROM rfid_cards WHERE id = ?", (card_id,))

            self._insert_event(
                connection,
                card_id=None,
                uid_mask=card.uid_mask,
                action=RfidEventAction.CARD_DELETE,
                granted=True,
                requested_mode=None,
                resolved_mode=self._read_mode(connection),
                reason=None,
                source="admin_panel",
                actor_user_id=actor_user_id,
                created_at_ms=_now_ms(),
            )
            return card.card_id, card.card_label

    def verify_card(self, *, card_uid: str, source: str | None = None) -> RfidModeDecision:
        with self._connect() as connection:
            mode = self._read_mode(connection)
            now_ms = _now_ms()

            normalized_uid = self._normalize_uid(card_uid)
            uid_hash = self._uid_hash(normalized_uid)
            fallback_mask = self._uid_mask(normalized_uid)

            row = connection.execute(
                "SELECT * FROM rfid_cards WHERE uid_hash = ?",
                (uid_hash,),
            ).fetchone()

            if row is None or not bool(int(row["is_active"])):
                self._insert_event(
                    connection,
                    card_id=int(row["id"]) if row is not None else None,
                    uid_mask=str(row["uid_mask"]) if row is not None else fallback_mask,
                    action=RfidEventAction.CARD_VERIFY,
                    granted=False,
                    requested_mode=None,
                    resolved_mode=mode,
                    reason="card_not_found_or_inactive",
                    source=(source or "").strip() or None,
                    actor_user_id=None,
                    created_at_ms=now_ms,
                )
                return RfidModeDecision(
                    granted=False,
                    access_mode=mode,
                    card_id=int(row["id"]) if row is not None else None,
                    card_label=str(row["card_label"]) if row is not None else None,
                    uid_mask=str(row["uid_mask"]) if row is not None else fallback_mask,
                    reason="card_not_found_or_inactive",
                )

            connection.execute(
                "UPDATE rfid_cards SET last_used_at_ms = ?, updated_at_ms = ? WHERE id = ?",
                (now_ms, now_ms, int(row["id"])),
            )

            self._insert_event(
                connection,
                card_id=int(row["id"]),
                uid_mask=str(row["uid_mask"]),
                action=RfidEventAction.CARD_VERIFY,
                granted=True,
                requested_mode=None,
                resolved_mode=mode,
                reason=None,
                source=(source or "").strip() or None,
                actor_user_id=None,
                created_at_ms=now_ms,
            )

            return RfidModeDecision(
                granted=True,
                access_mode=mode,
                card_id=int(row["id"]),
                card_label=str(row["card_label"]),
                uid_mask=str(row["uid_mask"]),
                reason=None,
            )

    def switch_mode_by_card(
        self,
        *,
        card_uid: str,
        target_mode: AccessMode,
        source: str | None = None,
    ) -> RfidModeDecision:
        with self._connect() as connection:
            now_ms = _now_ms()
            normalized_uid = self._normalize_uid(card_uid)
            uid_hash = self._uid_hash(normalized_uid)
            fallback_mask = self._uid_mask(normalized_uid)

            row = connection.execute(
                "SELECT * FROM rfid_cards WHERE uid_hash = ?",
                (uid_hash,),
            ).fetchone()

            if row is None or not bool(int(row["is_active"])):
                current_mode = self._read_mode(connection)
                self._insert_event(
                    connection,
                    card_id=int(row["id"]) if row is not None else None,
                    uid_mask=str(row["uid_mask"]) if row is not None else fallback_mask,
                    action=RfidEventAction.MODE_SWITCH,
                    granted=False,
                    requested_mode=target_mode,
                    resolved_mode=current_mode,
                    reason="card_not_found_or_inactive",
                    source=(source or "").strip() or None,
                    actor_user_id=None,
                    created_at_ms=now_ms,
                )
                return RfidModeDecision(
                    granted=False,
                    access_mode=current_mode,
                    card_id=int(row["id"]) if row is not None else None,
                    card_label=str(row["card_label"]) if row is not None else None,
                    uid_mask=str(row["uid_mask"]) if row is not None else fallback_mask,
                    reason="card_not_found_or_inactive",
                )

            connection.execute(
                """
                INSERT INTO mode_state(id, access_mode, updated_at_ms)
                VALUES (1, ?, ?)
                ON CONFLICT(id)
                DO UPDATE SET
                    access_mode = excluded.access_mode,
                    updated_at_ms = excluded.updated_at_ms
                """,
                (target_mode.value, now_ms),
            )

            connection.execute(
                "UPDATE rfid_cards SET last_used_at_ms = ?, updated_at_ms = ? WHERE id = ?",
                (now_ms, now_ms, int(row["id"])),
            )

            resolved_mode = self._read_mode(connection)
            self._insert_event(
                connection,
                card_id=int(row["id"]),
                uid_mask=str(row["uid_mask"]),
                action=RfidEventAction.MODE_SWITCH,
                granted=True,
                requested_mode=target_mode,
                resolved_mode=resolved_mode,
                reason=None,
                source=(source or "").strip() or None,
                actor_user_id=None,
                created_at_ms=now_ms,
            )

            return RfidModeDecision(
                granted=True,
                access_mode=resolved_mode,
                card_id=int(row["id"]),
                card_label=str(row["card_label"]),
                uid_mask=str(row["uid_mask"]),
                reason=None,
            )

    def list_events(
        self,
        *,
        actor_user_id: int,
        limit: int = 200,
        offset: int = 0,
    ) -> list[RfidAccessEvent]:
        safe_limit = min(max(limit, 1), 500)
        safe_offset = max(offset, 0)

        with self._connect() as connection:
            self._require_active_admin(connection, actor_user_id)
            rows = connection.execute(
                """
                SELECT *
                FROM rfid_events
                ORDER BY created_at_ms DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                (safe_limit, safe_offset),
            ).fetchall()
            return [self._row_to_event(row) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _require_active_admin(connection: sqlite3.Connection, user_id: int) -> sqlite3.Row:
        row = connection.execute(
            "SELECT id, role, status FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            raise RfidError("admin_not_found", "Admin user was not found", 404)
        if str(row["status"]) != UserStatus.ACTIVE.value or str(row["role"]) != UserRole.ADMIN.value:
            raise RfidError("admin_only", "Admin role is required", 403)
        return row

    def _uid_hash(self, normalized_uid: str) -> str:
        return hmac.new(
            self._uid_pepper.encode("utf-8"),
            normalized_uid.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def _normalize_uid(uid: str) -> str:
        raw = (
            uid.strip()
            .upper()
            .replace(" ", "")
            .replace(":", "")
            .replace("-", "")
        )
        if raw.startswith("0X"):
            raw = raw[2:]

        if len(raw) < 4 or len(raw) > 64:
            raise RfidError("invalid_uid", "RFID UID length must be in range 4..64", 422)

        allowed = set("0123456789ABCDEF")
        if any(ch not in allowed for ch in raw):
            raise RfidError("invalid_uid", "RFID UID must be hex-compatible", 422)
        return raw

    @staticmethod
    def _uid_mask(normalized_uid: str) -> str:
        if len(normalized_uid) <= 8:
            return normalized_uid
        return f"{normalized_uid[:4]}...{normalized_uid[-4:]}"

    @staticmethod
    def _read_mode(connection: sqlite3.Connection) -> AccessMode:
        row = connection.execute("SELECT access_mode FROM mode_state WHERE id = 1").fetchone()
        if row is None:
            return AccessMode.CLOSED
        try:
            return AccessMode(str(row["access_mode"]))
        except ValueError:
            return AccessMode.CLOSED

    @staticmethod
    def _insert_event(
        connection: sqlite3.Connection,
        *,
        card_id: int | None,
        uid_mask: str | None,
        action: RfidEventAction,
        granted: bool,
        requested_mode: AccessMode | None,
        resolved_mode: AccessMode | None,
        reason: str | None,
        source: str | None,
        actor_user_id: int | None,
        created_at_ms: int,
    ) -> None:
        connection.execute(
            """
            INSERT INTO rfid_events(
                card_id,
                uid_mask,
                action,
                granted,
                requested_mode,
                resolved_mode,
                reason,
                source,
                actor_user_id,
                created_at_ms
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                card_id,
                uid_mask,
                action.value,
                1 if granted else 0,
                requested_mode.value if requested_mode is not None else None,
                resolved_mode.value if resolved_mode is not None else None,
                reason,
                source,
                actor_user_id,
                created_at_ms,
            ),
        )

    @staticmethod
    def _row_to_card(row: sqlite3.Row) -> RfidCard:
        return RfidCard(
            card_id=int(row["id"]),
            uid_mask=str(row["uid_mask"]),
            card_label=str(row["card_label"]),
            note=str(row["note"]) if row["note"] is not None else None,
            is_active=bool(int(row["is_active"])),
            created_by_user_id=int(row["created_by_user_id"]),
            created_at_ms=int(row["created_at_ms"]),
            updated_at_ms=int(row["updated_at_ms"]),
            last_used_at_ms=int(row["last_used_at_ms"])
            if row["last_used_at_ms"] is not None
            else None,
        )

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> RfidAccessEvent:
        requested_mode_raw = row["requested_mode"]
        resolved_mode_raw = row["resolved_mode"]

        requested_mode = None
        if requested_mode_raw is not None:
            try:
                requested_mode = AccessMode(str(requested_mode_raw))
            except ValueError:
                requested_mode = None

        resolved_mode = None
        if resolved_mode_raw is not None:
            try:
                resolved_mode = AccessMode(str(resolved_mode_raw))
            except ValueError:
                resolved_mode = None

        return RfidAccessEvent(
            event_id=int(row["id"]),
            card_id=int(row["card_id"]) if row["card_id"] is not None else None,
            uid_mask=str(row["uid_mask"]) if row["uid_mask"] is not None else None,
            action=RfidEventAction(str(row["action"])),
            granted=bool(int(row["granted"])),
            requested_mode=requested_mode,
            resolved_mode=resolved_mode,
            reason=str(row["reason"]) if row["reason"] is not None else None,
            source=str(row["source"]) if row["source"] is not None else None,
            actor_user_id=int(row["actor_user_id"]) if row["actor_user_id"] is not None else None,
            created_at_ms=int(row["created_at_ms"]),
        )
