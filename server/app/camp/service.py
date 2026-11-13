"""Camp Edition domain service.

The module is additive: all state lives in ``camp_*`` tables.  The shared
chat/account domain remains untouched and available for normal use.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from time import time
from typing import Any, Iterable, Mapping

from app.camp import policy
from app.db.connection import connect_sqlite


CAMP_ROLES = set(policy.CAMP_ROLES)
STAFF_ROLES = set(policy.STAFF_ROLES)
MANAGE_ROLES = {"director"}
COUNSELOR_ROLES = {"counselor", "director"}


def _now_ms() -> int:
    return int(time() * 1000)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _json_load(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


class CampError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}

    def as_detail(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            payload["details"] = self.details
        return payload


class CampService:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)

    # -- infrastructure -------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        return connect_sqlite(self._db_path)

    @staticmethod
    def _audit(
        connection: sqlite3.Connection,
        actor: Mapping[str, Any] | None,
        action: str,
        *,
        person_id: int | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        connection.execute(
            """
            INSERT INTO camp_audit(actor_user_id, action, person_id, details_json, created_at_ms)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                int(actor["user_id"]) if actor and actor.get("user_id") else None,
                action,
                person_id,
                _json(dict(details or {})),
                _now_ms(),
            ),
        )

    @staticmethod
    def _require_role(actor: Mapping[str, Any], roles: set[str]) -> None:
        if str(actor.get("role") or "") not in roles:
            raise CampError(
                "role_forbidden",
                "This action is not allowed for your camp role",
                status_code=403,
                details={"role": actor.get("role"), "allowed": sorted(roles)},
            )

    @staticmethod
    def _person_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return dict(row)

    def _session(self, connection: sqlite3.Connection, session_id: int) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM camp_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            raise CampError("session_not_found", "Camp session not found", status_code=404)
        return row

    def _default_session_id(self, connection: sqlite3.Connection) -> int | None:
        row = connection.execute(
            """
            SELECT id FROM camp_sessions
            ORDER BY CASE status WHEN 'active' THEN 0 WHEN 'planned' THEN 1 ELSE 2 END,
                     starts_at_ms DESC, id DESC
            LIMIT 1
            """
        ).fetchone()
        return int(row["id"]) if row else None

    def _resolve_session_id(
        self,
        connection: sqlite3.Connection,
        actor: Mapping[str, Any],
        session_id: int | None,
    ) -> int:
        candidate = session_id or actor.get("session_id")
        if candidate is None:
            candidate = self._default_session_id(connection)
        if candidate is None:
            raise CampError(
                "session_required",
                "Create a camp session first",
                status_code=409,
            )
        self._guard_session(actor, int(candidate))
        self._session(connection, int(candidate))
        return int(candidate)

    @staticmethod
    def _guard_session(actor: Mapping[str, Any], session_id: int) -> None:
        actor_session = actor.get("session_id")
        if actor_session is not None and int(actor_session) != int(session_id):
            raise CampError(
                "session_forbidden",
                "This record belongs to another camp session",
                status_code=403,
            )

    def get_actor_for_user(
        self,
        user_id: int,
        *,
        session_id: int | None = None,
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            params: list[Any] = [user_id]
            where = "user_id = ? AND status = 'active'"
            if session_id is not None:
                where += " AND session_id = ?"
                params.append(session_id)
            row = connection.execute(
                f"""
                SELECT * FROM camp_people
                WHERE {where}
                ORDER BY CASE role WHEN 'director' THEN 0 WHEN 'counselor' THEN 1 ELSE 2 END,
                         id DESC
                LIMIT 1
                """,
                params,
            ).fetchone()
            if row is not None:
                person = dict(row)
                return {
                    "user_id": user_id,
                    "camp_person_id": int(person["id"]),
                    "role": str(person["role"]),
                    "session_id": int(person["session_id"]),
                    "unit_id": person["unit_id"],
                    "display_name": str(person["display_name"]),
                    "age_band": str(person["age_band"]),
                }
            user = connection.execute(
                "SELECT id, role, status FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            if user is not None and str(user["role"]) == "admin":
                return {
                    "user_id": user_id,
                    "camp_person_id": None,
                    "role": "director",
                    "session_id": session_id,
                    "unit_id": None,
                    "display_name": "Administrator",
                    "age_band": "adult",
                }
            return None

    # -- sessions, units and settings -----------------------------------

    def list_sessions(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM camp_sessions ORDER BY starts_at_ms DESC, id DESC"
            ).fetchall()
            return [dict(row) for row in rows]

    def get_session(self, session_id: int) -> dict[str, Any]:
        with self._connect() as connection:
            return dict(self._session(connection, session_id))

    def create_session(
        self,
        actor: Mapping[str, Any],
        *,
        name: str,
        starts_at_ms: int | None = None,
        ends_at_ms: int | None = None,
        retention_days: int = 30,
        status: str = "planned",
    ) -> dict[str, Any]:
        self._require_role(actor, MANAGE_ROLES)
        clean_name = name.strip()
        if not clean_name:
            raise CampError("invalid_name", "Session name must not be empty")
        if status not in {"planned", "active", "closed", "archived"}:
            raise CampError("invalid_status", "Invalid session status")
        now = _now_ms()
        start = int(starts_at_ms or now)
        end = int(ends_at_ms or (start + 14 * 86_400_000))
        if end <= start:
            raise CampError("invalid_dates", "Session end must be after start")
        if not 1 <= int(retention_days) <= 3650:
            raise CampError("invalid_retention", "Retention must be 1..3650 days")
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO camp_sessions(
                    name, starts_at_ms, ends_at_ms, status, retention_days, created_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (clean_name, start, end, status, int(retention_days), now),
            )
            session_id = int(cursor.lastrowid)
            connection.execute(
                """
                INSERT INTO camp_settings(session_id, updated_at_ms)
                VALUES (?, ?)
                """,
                (session_id, now),
            )
            self._audit(
                connection,
                actor,
                "session.created",
                details={"session_id": session_id, "name": clean_name},
            )
            return dict(self._session(connection, session_id))

    def create_unit(
        self,
        actor: Mapping[str, Any],
        *,
        session_id: int | None = None,
        name: str,
        kind: str = "squad",
    ) -> dict[str, Any]:
        self._require_role(actor, COUNSELOR_ROLES)
        clean_name = name.strip()
        if not clean_name:
            raise CampError("invalid_name", "Unit name must not be empty")
        if kind not in {"squad", "staff", "other"}:
            raise CampError("invalid_kind", "Invalid unit kind")
        with self._connect() as connection:
            resolved_session = self._resolve_session_id(connection, actor, session_id)
            try:
                cursor = connection.execute(
                    """
                    INSERT INTO camp_units(session_id, name, kind, created_at_ms)
                    VALUES (?, ?, ?, ?)
                    """,
                    (resolved_session, clean_name, kind, _now_ms()),
                )
            except sqlite3.IntegrityError as exc:
                raise CampError(
                    "unit_exists",
                    "A unit with this name already exists in the session",
                    status_code=409,
                ) from exc
            unit_id = int(cursor.lastrowid)
            self._audit(
                connection,
                actor,
                "unit.created",
                details={"session_id": resolved_session, "unit_id": unit_id, "name": clean_name},
            )
            row = connection.execute(
                "SELECT * FROM camp_units WHERE id = ?", (unit_id,)
            ).fetchone()
            return dict(row)

    def list_units(self, actor: Mapping[str, Any], *, session_id: int | None = None) -> list[dict[str, Any]]:
        with self._connect() as connection:
            resolved_session = self._resolve_session_id(connection, actor, session_id)
            if str(actor.get("role") or "") == "counselor" and actor.get("unit_id") is not None:
                rows = connection.execute(
                    "SELECT * FROM camp_units WHERE session_id = ? AND id = ? ORDER BY kind, name",
                    (resolved_session, int(actor["unit_id"])),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM camp_units WHERE session_id = ? ORDER BY kind, name",
                    (resolved_session,),
                ).fetchall()
            return [dict(row) for row in rows]

    def get_settings(self, actor: Mapping[str, Any], *, session_id: int | None = None) -> dict[str, Any]:
        with self._connect() as connection:
            resolved_session = self._resolve_session_id(connection, actor, session_id)
            row = connection.execute(
                "SELECT * FROM camp_settings WHERE session_id = ?",
                (resolved_session,),
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO camp_settings(session_id, updated_at_ms) VALUES (?, ?)",
                    (resolved_session, _now_ms()),
                )
                row = connection.execute(
                    "SELECT * FROM camp_settings WHERE session_id = ?",
                    (resolved_session,),
                ).fetchone()
            payload = dict(row)
            payload["quiet_start_minutes"] = int(payload["quiet_start_minutes"])
            payload["quiet_end_minutes"] = int(payload["quiet_end_minutes"])
            return payload

    def update_settings(
        self,
        actor: Mapping[str, Any],
        *,
        session_id: int | None = None,
        quiet_start_minutes: int | None = None,
        quiet_end_minutes: int | None = None,
        allow_child_dm: bool | None = None,
        allow_child_media: bool | None = None,
        require_two_adults_for_dm: bool | None = None,
        photo_watermark: str | None = None,
    ) -> dict[str, Any]:
        self._require_role(actor, MANAGE_ROLES)
        with self._connect() as connection:
            resolved_session = self._resolve_session_id(connection, actor, session_id)
            current = connection.execute(
                "SELECT * FROM camp_settings WHERE session_id = ?",
                (resolved_session,),
            ).fetchone()
            if current is None:
                connection.execute(
                    "INSERT INTO camp_settings(session_id, updated_at_ms) VALUES (?, ?)",
                    (resolved_session, _now_ms()),
                )
                current = connection.execute(
                    "SELECT * FROM camp_settings WHERE session_id = ?",
                    (resolved_session,),
                ).fetchone()
            start = int(quiet_start_minutes if quiet_start_minutes is not None else current["quiet_start_minutes"])
            end = int(quiet_end_minutes if quiet_end_minutes is not None else current["quiet_end_minutes"])
            if not 0 <= start <= 1439 or not 0 <= end <= 1439:
                raise CampError("invalid_quiet_hours", "Quiet hours must be 0..1439 minutes")
            connection.execute(
                """
                UPDATE camp_settings
                SET quiet_start_minutes = ?, quiet_end_minutes = ?,
                    allow_child_dm = ?, allow_child_media = ?,
                    require_two_adults_for_dm = ?, photo_watermark = ?,
                    updated_at_ms = ?
                WHERE session_id = ?
                """,
                (
                    start,
                    end,
                    1 if (allow_child_dm if allow_child_dm is not None else bool(current["allow_child_dm"])) else 0,
                    1 if (allow_child_media if allow_child_media is not None else bool(current["allow_child_media"])) else 0,
                    1 if (
                        require_two_adults_for_dm
                        if require_two_adults_for_dm is not None
                        else bool(current["require_two_adults_for_dm"])
                    ) else 0,
                    photo_watermark if photo_watermark is not None else current["photo_watermark"],
                    _now_ms(),
                    resolved_session,
                ),
            )
            self._audit(connection, actor, "settings.updated", details={"session_id": resolved_session})
            updated = connection.execute(
                "SELECT * FROM camp_settings WHERE session_id = ?",
                (resolved_session,),
            ).fetchone()
            return dict(updated)

    # -- people and imports ---------------------------------------------

    def create_person(
        self,
        actor: Mapping[str, Any],
        *,
        session_id: int | None = None,
        unit_id: int | None = None,
        user_id: int | None = None,
        role: str = "child",
        age_band: str | None = None,
        display_name: str,
        birth_date: str | None = None,
        login_name: str | None = None,
        room: str | None = None,
        badge_code: str | None = None,
    ) -> dict[str, Any]:
        self._require_role(actor, COUNSELOR_ROLES)
        clean_name = display_name.strip()
        if not clean_name:
            raise CampError("invalid_name", "Display name must not be empty")
        if role not in CAMP_ROLES:
            raise CampError("invalid_role", "Invalid camp role")
        band = age_band or policy.age_band_from_birth_date(birth_date) or ("adult" if role != "child" else None)
        if band not in policy.AGE_BANDS:
            raise CampError("invalid_age_band", "A valid age_band or birth_date is required")
        with self._connect() as connection:
            resolved_session = self._resolve_session_id(connection, actor, session_id)
            if unit_id is not None:
                unit = connection.execute(
                    "SELECT id FROM camp_units WHERE id = ? AND session_id = ?",
                    (unit_id, resolved_session),
                ).fetchone()
                if unit is None:
                    raise CampError("unit_not_found", "Unit not found in this session", status_code=404)
            now = _now_ms()
            try:
                cursor = connection.execute(
                    """
                    INSERT INTO camp_people(
                        session_id, unit_id, user_id, role, age_band, login_name,
                        display_name, birth_date, room, badge_code, status,
                        created_at_ms, updated_at_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
                    """,
                    (
                        resolved_session,
                        unit_id,
                        user_id,
                        role,
                        band,
                        login_name,
                        clean_name,
                        birth_date,
                        room,
                        badge_code,
                        now,
                        now,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise CampError(
                    "person_conflict",
                    "A person with this badge code already exists",
                    status_code=409,
                ) from exc
            person_id = int(cursor.lastrowid)
            if not badge_code:
                badge = f"CAMP-{resolved_session:02d}-{person_id:05d}"
                connection.execute(
                    "UPDATE camp_people SET badge_code = ? WHERE id = ?",
                    (badge, person_id),
                )
            self._audit(
                connection,
                actor,
                "person.created",
                person_id=person_id,
                details={"session_id": resolved_session, "role": role},
            )
            row = connection.execute(
                "SELECT * FROM camp_people WHERE id = ?", (person_id,)
            ).fetchone()
            return dict(row)

    def _can_view_person(
        self,
        connection: sqlite3.Connection,
        actor: Mapping[str, Any],
        person: Mapping[str, Any],
    ) -> bool:
        role = str(actor.get("role") or "")
        if role in STAFF_ROLES:
            return True
        if actor.get("camp_person_id") == person.get("id"):
            return True
        if role == "parent":
            row = connection.execute(
                "SELECT 1 FROM camp_guardians WHERE person_id = ? AND parent_person_id = ?",
                (person.get("id"), actor.get("camp_person_id")),
            ).fetchone()
            return row is not None
        if role == "child":
            return (
                person.get("role") == "child"
                and actor.get("unit_id") is not None
                and actor.get("unit_id") == person.get("unit_id")
            )
        return False

    def list_people(
        self,
        actor: Mapping[str, Any],
        *,
        session_id: int | None = None,
        unit_id: int | None = None,
        role: str | None = None,
        q: str = "",
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            resolved_session = self._resolve_session_id(connection, actor, session_id)
            clauses = ["p.session_id = ?", "p.status = 'active'"]
            params: list[Any] = [resolved_session]
            if unit_id is not None:
                clauses.append("p.unit_id = ?")
                params.append(unit_id)
            if role:
                if role not in CAMP_ROLES:
                    raise CampError("invalid_role", "Invalid camp role")
                clauses.append("p.role = ?")
                params.append(role)
            if q.strip():
                clauses.append("(p.display_name LIKE ? OR p.badge_code LIKE ? OR p.login_name LIKE ?)")
                needle = f"%{q.strip()}%"
                params.extend([needle, needle, needle])
            actor_role = str(actor.get("role") or "")
            if actor_role == "child":
                clauses.append("p.unit_id = ?")
                params.append(actor.get("unit_id"))
            elif actor_role == "counselor":
                clauses.append("p.unit_id = ?")
                params.append(actor.get("unit_id"))
            elif actor_role == "parent":
                clauses.append(
                    "p.id IN (SELECT person_id FROM camp_guardians WHERE parent_person_id = ?)"
                )
                params.append(actor.get("camp_person_id"))
            elif actor_role not in STAFF_ROLES:
                raise CampError("role_forbidden", "No access to camp people", status_code=403)
            params.append(max(1, min(int(limit), 500)))
            rows = connection.execute(
                f"""
                SELECT p.*, u.name AS unit_name
                FROM camp_people p
                LEFT JOIN camp_units u ON u.id = p.unit_id
                WHERE {' AND '.join(clauses)}
                ORDER BY p.display_name COLLATE NOCASE
                LIMIT ?
                """,
                params,
            ).fetchall()
            return [dict(row) for row in rows]

    def get_person(self, actor: Mapping[str, Any], person_id: int) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT p.*, u.name AS unit_name
                FROM camp_people p
                LEFT JOIN camp_units u ON u.id = p.unit_id
                WHERE p.id = ?
                """,
                (person_id,),
            ).fetchone()
            if row is None:
                raise CampError("person_not_found", "Person not found", status_code=404)
            person = dict(row)
            if not self._can_view_person(connection, actor, person):
                raise CampError("person_forbidden", "No access to this person", status_code=403)
            return person

    def _normalize_import_row(
        self,
        row: Mapping[str, Any],
        index: int,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        errors: list[dict[str, Any]] = []
        name = str(row.get("display_name") or row.get("name") or row.get("full_name") or "").strip()
        if not name:
            errors.append({"row": index, "field": "display_name", "code": "required"})
        role = str(row.get("role") or "child").strip().lower()
        if role not in CAMP_ROLES:
            errors.append({"row": index, "field": "role", "code": "invalid"})
            role = "child"
        birth_date = str(row.get("birth_date") or "").strip() or None
        band = str(row.get("age_band") or "").strip() or None
        if band is not None and band not in policy.AGE_BANDS:
            errors.append({"row": index, "field": "age_band", "code": "invalid"})
            band = None
        if band is None:
            try:
                band = policy.age_band_from_birth_date(birth_date)
            except ValueError:
                errors.append({"row": index, "field": "birth_date", "code": "invalid"})
                band = None
        if band is None:
            band = "adult" if role != "child" else None
        if band is None:
            errors.append({"row": index, "field": "age_band", "code": "required"})
        badge = str(row.get("badge_code") or "").strip() or None
        unit_name = str(row.get("unit_name") or row.get("unit") or "").strip() or None
        if role == "child" and not unit_name:
            errors.append({"row": index, "field": "unit_name", "code": "required"})
        return (
            {
                "row": index,
                "display_name": name,
                "role": role,
                "age_band": band,
                "birth_date": birth_date,
                "unit_name": unit_name,
                "badge_code": badge,
                "login_name": str(row.get("login_name") or "").strip() or None,
                "room": str(row.get("room") or "").strip() or None,
            },
            errors,
        )

    def import_preview(self, rows: Iterable[Mapping[str, Any]], *, session_id: int) -> dict[str, Any]:
        normalized: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        duplicates: list[dict[str, Any]] = []
        within: set[tuple[str, str | None]] = set()
        with self._connect() as connection:
            session = self._session(connection, session_id)
            for index, raw in enumerate(rows, start=1):
                if not isinstance(raw, Mapping):
                    errors.append({"row": index, "field": "row", "code": "must_be_object"})
                    continue
                item, row_errors = self._normalize_import_row(raw, index)
                errors.extend(row_errors)
                key = (item["display_name"].casefold(), item.get("birth_date"))
                if key in within:
                    duplicates.append(
                        {
                            "row": index,
                            "code": "duplicate_in_file",
                            "display_name": item["display_name"],
                        }
                    )
                    errors.append({"row": index, "field": "display_name", "code": "duplicate"})
                within.add(key)
                if item.get("badge_code"):
                    existing = connection.execute(
                        "SELECT id FROM camp_people WHERE badge_code = ?",
                        (item["badge_code"],),
                    ).fetchone()
                    if existing is not None:
                        duplicates.append(
                            {
                                "row": index,
                                "code": "badge_exists",
                                "person_id": int(existing["id"]),
                            }
                        )
                        errors.append({"row": index, "field": "badge_code", "code": "duplicate"})
                existing = connection.execute(
                    """
                    SELECT id FROM camp_people
                    WHERE session_id = ? AND lower(display_name) = lower(?)
                      AND COALESCE(birth_date, '') = COALESCE(?, '')
                    """,
                    (session_id, item["display_name"], item.get("birth_date")),
                ).fetchone()
                if existing is not None:
                    duplicates.append(
                        {
                            "row": index,
                            "code": "person_exists",
                            "person_id": int(existing["id"]),
                        }
                    )
                    errors.append({"row": index, "field": "display_name", "code": "duplicate"})
                normalized.append(item)
            return {
                "status": "ok" if not errors else "needs_fix",
                "session_id": session_id,
                "session_name": str(session["name"]),
                "rows": normalized,
                "errors": errors,
                "duplicates": duplicates,
                "summary": {
                    "rows": len(normalized),
                    "valid": len(normalized) - len({e["row"] for e in errors}),
                    "errors": len(errors),
                    "duplicates": len(duplicates),
                },
            }

    def import_commit(
        self,
        actor: Mapping[str, Any],
        *,
        session_id: int | None,
        rows: Iterable[Mapping[str, Any]],
    ) -> dict[str, Any]:
        self._require_role(actor, COUNSELOR_ROLES)
        with self._connect() as connection:
            resolved_session = self._resolve_session_id(connection, actor, session_id)
        preview = self.import_preview(rows, session_id=resolved_session)
        if preview["errors"]:
            raise CampError(
                "import_has_errors",
                "Fix import errors before committing",
                status_code=422,
                details={"errors": preview["errors"], "duplicates": preview["duplicates"]},
            )
        inserted: list[int] = []
        now = _now_ms()
        with self._connect() as connection:
            resolved_session = self._resolve_session_id(connection, actor, resolved_session)
            for item in preview["rows"]:
                unit_id: int | None = None
                if item.get("unit_name"):
                    existing_unit = connection.execute(
                        "SELECT id FROM camp_units WHERE session_id = ? AND lower(name) = lower(?)",
                        (resolved_session, item["unit_name"]),
                    ).fetchone()
                    if existing_unit is None:
                        cursor = connection.execute(
                            "INSERT INTO camp_units(session_id, name, kind, created_at_ms) VALUES (?, ?, 'squad', ?)",
                            (resolved_session, item["unit_name"], now),
                        )
                        unit_id = int(cursor.lastrowid)
                    else:
                        unit_id = int(existing_unit["id"])
                cursor = connection.execute(
                    """
                    INSERT INTO camp_people(
                        session_id, unit_id, role, age_band, login_name, display_name,
                        birth_date, room, badge_code, status, created_at_ms, updated_at_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
                    """,
                    (
                        resolved_session,
                        unit_id,
                        item["role"],
                        item["age_band"],
                        item.get("login_name"),
                        item["display_name"],
                        item.get("birth_date"),
                        item.get("room"),
                        item.get("badge_code"),
                        now,
                        now,
                    ),
                )
                person_id = int(cursor.lastrowid)
                if not item.get("badge_code"):
                    connection.execute(
                        "UPDATE camp_people SET badge_code = ? WHERE id = ?",
                        (f"CAMP-{resolved_session:02d}-{person_id:05d}", person_id),
                    )
                inserted.append(person_id)
            cursor = connection.execute(
                """
                INSERT INTO camp_import_batches(
                    session_id, created_by, status, rows_json, errors_json, result_json,
                    created_at_ms, committed_at_ms
                ) VALUES (?, ?, 'committed', ?, '[]', ?, ?, ?)
                """,
                (
                    resolved_session,
                    actor.get("user_id"),
                    _json(preview["rows"]),
                    _json({"inserted_ids": inserted}),
                    now,
                    now,
                ),
            )
            batch_id = int(cursor.lastrowid)
            self._audit(
                connection,
                actor,
                "people.imported",
                details={
                    "session_id": resolved_session,
                    "batch_id": batch_id,
                    "count": len(inserted),
                },
            )
            return {
                "status": "ok",
                "batch_id": batch_id,
                "inserted_ids": inserted,
                "count": len(inserted),
            }

    def undo_import(
        self,
        actor: Mapping[str, Any],
        *,
        batch_id: int,
        max_age_ms: int = 10 * 60_000,
    ) -> dict[str, Any]:
        self._require_role(actor, COUNSELOR_ROLES)
        with self._connect() as connection:
            batch = connection.execute(
                "SELECT * FROM camp_import_batches WHERE id = ?",
                (batch_id,),
            ).fetchone()
            if batch is None:
                raise CampError("batch_not_found", "Import batch not found", status_code=404)
            if str(batch["status"]) != "committed":
                raise CampError("batch_not_active", "This batch cannot be undone", status_code=409)
            if actor.get("role") != "director" and batch["created_by"] != actor.get("user_id"):
                raise CampError("batch_forbidden", "Only the author can undo this import", status_code=403)
            if _now_ms() - int(batch["committed_at_ms"] or 0) > max_age_ms:
                raise CampError("undo_window_expired", "Undo is only available for 10 minutes", status_code=409)
            result = _json_load(batch["result_json"], {})
            deleted = 0
            skipped: list[int] = []
            for person_id in result.get("inserted_ids", []):
                if not isinstance(person_id, int):
                    continue
                activity = connection.execute(
                    """
                    SELECT 1 FROM camp_requests WHERE child_id = ?
                    UNION ALL SELECT 1 FROM camp_scans WHERE person_id = ?
                    UNION ALL SELECT 1 FROM camp_attendance_marks WHERE person_id = ?
                    UNION ALL SELECT 1 FROM camp_movements WHERE person_id = ?
                    UNION ALL SELECT 1 FROM camp_digest WHERE person_id = ?
                    LIMIT 1
                    """,
                    (person_id, person_id, person_id, person_id, person_id),
                ).fetchone()
                if activity is not None:
                    skipped.append(person_id)
                    continue
                connection.execute("DELETE FROM camp_people WHERE id = ?", (person_id,))
                deleted += 1
            connection.execute(
                "UPDATE camp_import_batches SET status = 'undone' WHERE id = ?",
                (batch_id,),
            )
            self._audit(
                connection,
                actor,
                "people.import_undone",
                details={"batch_id": batch_id, "deleted": deleted, "skipped": skipped},
            )
            return {"status": "ok", "deleted": deleted, "skipped": skipped}

    def transfer_person(
        self,
        actor: Mapping[str, Any],
        *,
        person_id: int,
        unit_id: int,
    ) -> dict[str, Any]:
        self._require_role(actor, COUNSELOR_ROLES)
        with self._connect() as connection:
            person = connection.execute(
                "SELECT * FROM camp_people WHERE id = ?", (person_id,)
            ).fetchone()
            if person is None:
                raise CampError("person_not_found", "Person not found", status_code=404)
            unit = connection.execute(
                "SELECT id FROM camp_units WHERE id = ? AND session_id = ?",
                (unit_id, int(person["session_id"])),
            ).fetchone()
            if unit is None:
                raise CampError("unit_not_found", "Unit not found in this session", status_code=404)
            connection.execute(
                "UPDATE camp_people SET unit_id = ?, updated_at_ms = ? WHERE id = ?",
                (unit_id, _now_ms(), person_id),
            )
            self._audit(
                connection,
                actor,
                "person.transferred",
                person_id=person_id,
                details={"from_unit_id": person["unit_id"], "to_unit_id": unit_id},
            )
            updated = connection.execute(
                "SELECT * FROM camp_people WHERE id = ?", (person_id,)
            ).fetchone()
            return dict(updated)

    def merge_people(
        self,
        actor: Mapping[str, Any],
        *,
        source_id: int,
        target_id: int,
    ) -> dict[str, Any]:
        self._require_role(actor, MANAGE_ROLES)
        if source_id == target_id:
            raise CampError("same_person", "Cannot merge a person with themselves")
        reference_tables = (
            ("camp_scans", "person_id"),
            ("camp_attendance_marks", "person_id"),
            ("camp_requests", "child_id"),
            ("camp_consents", "person_id"),
            ("camp_dietary", "person_id"),
            ("camp_digest", "person_id"),
            ("camp_pickup_auth", "person_id"),
            ("camp_movements", "person_id"),
            ("camp_guardians", "person_id"),
            ("camp_guardians", "parent_person_id"),
        )
        with self._connect() as connection:
            source = connection.execute("SELECT * FROM camp_people WHERE id = ?", (source_id,)).fetchone()
            target = connection.execute("SELECT * FROM camp_people WHERE id = ?", (target_id,)).fetchone()
            if source is None or target is None:
                raise CampError("person_not_found", "Person not found", status_code=404)
            if int(source["session_id"]) != int(target["session_id"]):
                raise CampError("different_sessions", "People must belong to the same session")
            for table, column in reference_tables:
                connection.execute(
                    f"UPDATE OR IGNORE {table} SET {column} = ? WHERE {column} = ?",
                    (target_id, source_id),
                )
            connection.execute("DELETE FROM camp_people WHERE id = ?", (source_id,))
            self._audit(
                connection,
                actor,
                "person.merged",
                person_id=target_id,
                details={"source_id": source_id, "target_id": target_id},
            )
            merged = connection.execute(
                "SELECT * FROM camp_people WHERE id = ?", (target_id,)
            ).fetchone()
            return dict(merged)

    # -- counselor request queue ----------------------------------------

    def create_request(
        self,
        actor: Mapping[str, Any],
        *,
        session_id: int | None = None,
        kind: str = "call_counselor",
        note: str | None = None,
    ) -> dict[str, Any]:
        if peer := self._actor_person(actor):
            decision = policy.check_request(peer)
            if not decision.allowed:
                raise CampError(decision.code, decision.message, status_code=403)
        else:
            raise CampError("camp_person_required", "A camp profile is required", status_code=403)
        if kind not in {"call_counselor", "parent_question", "help"}:
            raise CampError("invalid_kind", "Invalid request kind")
        with self._connect() as connection:
            resolved_session = self._resolve_session_id(connection, actor, session_id)
            person = connection.execute(
                "SELECT * FROM camp_people WHERE id = ? AND session_id = ?",
                (actor.get("camp_person_id"), resolved_session),
            ).fetchone()
            if person is None:
                raise CampError("camp_person_required", "A camp profile is required", status_code=403)
            cursor = connection.execute(
                """
                INSERT INTO camp_requests(
                    session_id, unit_id, child_id, kind, status, note, created_at_ms
                ) VALUES (?, ?, ?, ?, 'open', ?, ?)
                """,
                (
                    resolved_session,
                    person["unit_id"],
                    int(person["id"]),
                    kind,
                    (note or "").strip()[:2000] or None,
                    _now_ms(),
                ),
            )
            request_id = int(cursor.lastrowid)
            self._audit(
                connection,
                actor,
                "request.created",
                person_id=int(person["id"]),
                details={"request_id": request_id, "kind": kind},
            )
            return dict(
                connection.execute(
                    "SELECT * FROM camp_requests WHERE id = ?", (request_id,)
                ).fetchone()
            )

    @staticmethod
    def _actor_person(actor: Mapping[str, Any]) -> dict[str, Any] | None:
        if not actor.get("camp_person_id"):
            return None
        return dict(actor)

    def list_requests(
        self,
        actor: Mapping[str, Any],
        *,
        session_id: int | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            resolved_session = self._resolve_session_id(connection, actor, session_id)
            clauses = ["r.session_id = ?"]
            params: list[Any] = [resolved_session]
            if status:
                if status not in {"open", "claimed", "closed"}:
                    raise CampError("invalid_status", "Invalid request status")
                clauses.append("r.status = ?")
                params.append(status)
            role = str(actor.get("role") or "")
            if role == "child":
                clauses.append("r.child_id = ?")
                params.append(actor.get("camp_person_id"))
            elif role == "counselor":
                clauses.append("r.unit_id = ?")
                params.append(actor.get("unit_id"))
            elif role not in {"director", "security", "medic"}:
                raise CampError("role_forbidden", "No access to the request queue", status_code=403)
            params.append(max(1, min(int(limit), 500)))
            rows = connection.execute(
                f"""
                SELECT r.*, p.display_name AS child_name, u.name AS unit_name
                FROM camp_requests r
                JOIN camp_people p ON p.id = r.child_id
                LEFT JOIN camp_units u ON u.id = r.unit_id
                WHERE {' AND '.join(clauses)}
                ORDER BY CASE r.status WHEN 'open' THEN 0 WHEN 'claimed' THEN 1 ELSE 2 END,
                         r.created_at_ms DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
            return [dict(row) for row in rows]

    def claim_request(self, actor: Mapping[str, Any], request_id: int) -> dict[str, Any]:
        self._require_role(actor, {"counselor", "director", "security"})
        with self._connect() as connection:
            request = connection.execute(
                "SELECT * FROM camp_requests WHERE id = ?", (request_id,)
            ).fetchone()
            if request is None:
                raise CampError("request_not_found", "Request not found", status_code=404)
            if actor.get("role") == "counselor" and request["unit_id"] != actor.get("unit_id"):
                raise CampError("request_forbidden", "This request belongs to another unit", status_code=403)
            updated = connection.execute(
                """
                UPDATE camp_requests
                SET status = 'claimed', claimed_by = ?, claimed_at_ms = ?
                WHERE id = ? AND status = 'open'
                """,
                (actor.get("user_id"), _now_ms(), request_id),
            ).rowcount
            if updated == 0:
                raise CampError(
                    "request_already_claimed",
                    "Another counselor has already claimed this request",
                    status_code=409,
                )
            self._audit(
                connection,
                actor,
                "request.claimed",
                person_id=int(request["child_id"]),
                details={"request_id": request_id},
            )
            return dict(
                connection.execute(
                    "SELECT * FROM camp_requests WHERE id = ?", (request_id,)
                ).fetchone()
            )

    def close_request(
        self,
        actor: Mapping[str, Any],
        request_id: int,
        *,
        note: str | None = None,
    ) -> dict[str, Any]:
        self._require_role(actor, {"counselor", "director", "security"})
        with self._connect() as connection:
            request = connection.execute(
                "SELECT * FROM camp_requests WHERE id = ?", (request_id,)
            ).fetchone()
            if request is None:
                raise CampError("request_not_found", "Request not found", status_code=404)
            if actor.get("role") != "director" and request["claimed_by"] != actor.get("user_id"):
                raise CampError("request_forbidden", "Only the claiming counselor can close it", status_code=403)
            if str(request["status"]) == "closed":
                raise CampError("request_closed", "Request is already closed", status_code=409)
            extra = (note or "").strip()[:2000]
            combined = request["note"] or ""
            if extra:
                combined = f"{combined} | {extra}".strip(" |")
            connection.execute(
                """
                UPDATE camp_requests
                SET status = 'closed', closed_at_ms = ?, note = ?
                WHERE id = ?
                """,
                (_now_ms(), combined or None, request_id),
            )
            self._audit(
                connection,
                actor,
                "request.closed",
                person_id=int(request["child_id"]),
                details={"request_id": request_id},
            )
            return dict(
                connection.execute(
                    "SELECT * FROM camp_requests WHERE id = ?", (request_id,)
                ).fetchone()
            )

    # -- attendance -----------------------------------------------------

    def _attendance_event_payload(
        self,
        connection: sqlite3.Connection,
        event_id: int,
        *,
        viewer: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        event = connection.execute(
            """
            SELECT e.*, u.name AS unit_name
            FROM camp_attendance_events e
            JOIN camp_units u ON u.id = e.unit_id
            WHERE e.id = ?
            """,
            (event_id,),
        ).fetchone()
        if event is None:
            raise CampError("attendance_not_found", "Attendance event not found", status_code=404)
        people = connection.execute(
            """
            SELECT p.id, p.display_name, p.badge_code, p.room, p.age_band,
                   m.status AS mark_status, m.note AS mark_note,
                   m.marked_at_ms, m.marked_by
            FROM camp_people p
            LEFT JOIN camp_attendance_marks m
              ON m.person_id = p.id AND m.event_id = ?
            WHERE p.unit_id = ? AND p.role = 'child' AND p.status = 'active'
            ORDER BY p.display_name COLLATE NOCASE
            """,
            (event_id, int(event["unit_id"])),
        ).fetchall()
        items = [dict(row) for row in people]
        if viewer is not None and str(viewer.get("role") or "") == "child":
            items = [item for item in items if item["id"] == viewer.get("camp_person_id")]
        statuses = [str(item["mark_status"]) for item in items if item["mark_status"]]
        counts = {name: statuses.count(name) for name in ("present", "absent", "sick", "medic", "parent", "left")}
        marked = sum(1 for item in items if item.get("mark_status"))
        unmarked = sum(1 for item in items if not item.get("mark_status"))
        missing = [
            item
            for item in items
            if not item.get("mark_status") or item.get("mark_status") in {"absent", "left"}
        ]
        payload = dict(event)
        payload["items"] = items
        payload["summary"] = {
            "total": len(items),
            "marked": marked,
            "unmarked": unmarked,
            **counts,
        }
        payload["missing"] = missing
        payload["overdue"] = (
            str(event["status"]) == "open" and int(event["deadline_at_ms"]) < _now_ms()
        )
        return payload

    def create_attendance_event(
        self,
        actor: Mapping[str, Any],
        *,
        session_id: int | None = None,
        unit_id: int,
        kind: str = "roll_call",
        deadline_at_ms: int | None = None,
    ) -> dict[str, Any]:
        self._require_role(actor, {"counselor", "director", "security"})
        if kind not in {"roll_call", "lights_out", "custom"}:
            raise CampError("invalid_kind", "Invalid attendance kind")
        now = _now_ms()
        with self._connect() as connection:
            resolved_session = self._resolve_session_id(connection, actor, session_id)
            unit = connection.execute(
                "SELECT * FROM camp_units WHERE id = ? AND session_id = ?",
                (unit_id, resolved_session),
            ).fetchone()
            if unit is None:
                raise CampError("unit_not_found", "Unit not found in this session", status_code=404)
            if actor.get("role") == "counselor" and actor.get("unit_id") != unit_id:
                raise CampError("unit_forbidden", "Counselors mark only their own unit", status_code=403)
            deadline = int(deadline_at_ms or (now + 15 * 60_000))
            if deadline <= now:
                raise CampError("invalid_deadline", "Deadline must be in the future")
            cursor = connection.execute(
                """
                INSERT INTO camp_attendance_events(
                    session_id, unit_id, kind, deadline_at_ms, status, created_by, created_at_ms
                ) VALUES (?, ?, ?, ?, 'open', ?, ?)
                """,
                (resolved_session, unit_id, kind, deadline, actor.get("user_id"), now),
            )
            event_id = int(cursor.lastrowid)
            self._audit(
                connection,
                actor,
                "attendance.created",
                details={"event_id": event_id, "unit_id": unit_id, "kind": kind},
            )
            return self._attendance_event_payload(connection, event_id, viewer=actor)

    def list_attendance_events(
        self,
        actor: Mapping[str, Any],
        *,
        session_id: int | None = None,
        unit_id: int | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        role = str(actor.get("role") or "")
        if role not in STAFF_ROLES and role != "child":
            raise CampError("role_forbidden", "No access to attendance", status_code=403)
        with self._connect() as connection:
            resolved_session = self._resolve_session_id(connection, actor, session_id)
            clauses = ["e.session_id = ?"]
            params: list[Any] = [resolved_session]
            if unit_id is not None:
                clauses.append("e.unit_id = ?")
                params.append(unit_id)
            if status:
                if status not in {"open", "closed"}:
                    raise CampError("invalid_status", "Invalid attendance status")
                clauses.append("e.status = ?")
                params.append(status)
            if role == "child":
                clauses.append("e.unit_id = ?")
                params.append(actor.get("unit_id"))
            elif role == "counselor":
                clauses.append("e.unit_id = ?")
                params.append(actor.get("unit_id"))
            params.append(max(1, min(int(limit), 300)))
            rows = connection.execute(
                f"""
                SELECT e.id FROM camp_attendance_events e
                WHERE {' AND '.join(clauses)}
                ORDER BY CASE e.status WHEN 'open' THEN 0 ELSE 1 END,
                         e.created_at_ms DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
            return [self._attendance_event_payload(connection, int(row["id"]), viewer=actor) for row in rows]

    def get_attendance_event(self, actor: Mapping[str, Any], *, event_id: int) -> dict[str, Any]:
        role = str(actor.get("role") or "")
        if role not in STAFF_ROLES and role != "child":
            raise CampError("role_forbidden", "No access to attendance", status_code=403)
        with self._connect() as connection:
            event = connection.execute(
                "SELECT * FROM camp_attendance_events WHERE id = ?", (event_id,)
            ).fetchone()
            if event is None:
                raise CampError("attendance_not_found", "Attendance event not found", status_code=404)
            self._guard_session(actor, int(event["session_id"]))
            if role == "child" and actor.get("unit_id") != int(event["unit_id"]):
                raise CampError("unit_forbidden", "No access to another unit's attendance", status_code=403)
            return self._attendance_event_payload(connection, event_id, viewer=actor)

    def mark_attendance(
        self,
        actor: Mapping[str, Any],
        *,
        event_id: int,
        person_id: int,
        status: str,
        note: str | None = None,
    ) -> dict[str, Any]:
        self._require_role(actor, {"counselor", "director", "security", "medic"})
        if status not in {"present", "absent", "sick", "medic", "parent", "left"}:
            raise CampError("invalid_mark", "Invalid attendance mark")
        with self._connect() as connection:
            event = connection.execute(
                "SELECT * FROM camp_attendance_events WHERE id = ?", (event_id,)
            ).fetchone()
            if event is None:
                raise CampError("attendance_not_found", "Attendance event not found", status_code=404)
            self._guard_session(actor, int(event["session_id"]))
            if str(event["status"]) != "open":
                raise CampError("attendance_closed", "Attendance event is closed", status_code=409)
            if actor.get("role") == "counselor" and actor.get("unit_id") != int(event["unit_id"]):
                raise CampError("unit_forbidden", "Counselors mark only their own unit", status_code=403)
            person = connection.execute(
                "SELECT * FROM camp_people WHERE id = ? AND session_id = ?",
                (person_id, int(event["session_id"])),
            ).fetchone()
            if person is None or person["role"] != "child" or person["unit_id"] != event["unit_id"]:
                raise CampError("person_not_in_unit", "Child is not in this unit", status_code=404)
            connection.execute(
                """
                INSERT INTO camp_attendance_marks(event_id, person_id, status, note, marked_by, marked_at_ms)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id, person_id) DO UPDATE SET
                    status = excluded.status,
                    note = excluded.note,
                    marked_by = excluded.marked_by,
                    marked_at_ms = excluded.marked_at_ms
                """,
                (
                    event_id,
                    person_id,
                    status,
                    (note or "").strip()[:1000] or None,
                    actor.get("user_id"),
                    _now_ms(),
                ),
            )
            self._audit(
                connection,
                actor,
                "attendance.marked",
                person_id=person_id,
                details={"event_id": event_id, "status": status},
            )
            return self._attendance_event_payload(connection, event_id, viewer=actor)

    def mark_all_present(self, actor: Mapping[str, Any], *, event_id: int) -> dict[str, Any]:
        self._require_role(actor, {"counselor", "director", "security"})
        with self._connect() as connection:
            event = connection.execute(
                "SELECT * FROM camp_attendance_events WHERE id = ?", (event_id,)
            ).fetchone()
            if event is None:
                raise CampError("attendance_not_found", "Attendance event not found", status_code=404)
            self._guard_session(actor, int(event["session_id"]))
            if str(event["status"]) != "open":
                raise CampError("attendance_closed", "Attendance event is closed", status_code=409)
            if actor.get("role") == "counselor" and actor.get("unit_id") != int(event["unit_id"]):
                raise CampError("unit_forbidden", "Counselors mark only their own unit", status_code=403)
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO camp_attendance_marks(
                    event_id, person_id, status, marked_by, marked_at_ms
                )
                SELECT ?, p.id, 'present', ?, ?
                FROM camp_people p
                WHERE p.unit_id = ? AND p.role = 'child' AND p.status = 'active'
                """,
                (event_id, actor.get("user_id"), _now_ms(), int(event["unit_id"])),
            )
            self._audit(
                connection,
                actor,
                "attendance.all_present",
                details={"event_id": event_id, "new_marks": cursor.rowcount},
            )
            return self._attendance_event_payload(connection, event_id, viewer=actor)

    def close_attendance(
        self,
        actor: Mapping[str, Any],
        *,
        event_id: int,
        force: bool = False,
        note: str | None = None,
    ) -> dict[str, Any]:
        self._require_role(actor, {"counselor", "director", "security"})
        with self._connect() as connection:
            event = connection.execute(
                "SELECT * FROM camp_attendance_events WHERE id = ?", (event_id,)
            ).fetchone()
            if event is None:
                raise CampError("attendance_not_found", "Attendance event not found", status_code=404)
            self._guard_session(actor, int(event["session_id"]))
            if str(event["status"]) == "closed":
                raise CampError("attendance_closed", "Attendance event is already closed", status_code=409)
            if actor.get("role") == "counselor" and actor.get("unit_id") != int(event["unit_id"]):
                raise CampError("unit_forbidden", "Counselors close only their own unit", status_code=403)
            payload = self._attendance_event_payload(connection, event_id, viewer=actor)
            unmarked = [
                item for item in payload["items"] if not item.get("mark_status")
            ]
            if unmarked and not force:
                raise CampError(
                    "attendance_incomplete",
                    "Mark every child before closing, or force-close with a reason",
                    status_code=409,
                    details={
                        "unmarked": [
                            {"id": item["id"], "display_name": item["display_name"]}
                            for item in unmarked
                        ]
                    },
                )
            connection.execute(
                """
                UPDATE camp_attendance_events
                SET status = 'closed', closed_at_ms = ?
                WHERE id = ?
                """,
                (_now_ms(), event_id),
            )
            self._audit(
                connection,
                actor,
                "attendance.closed",
                details={"event_id": event_id, "forced": bool(force), "note": (note or "")[:1000]},
            )
            return self._attendance_event_payload(connection, event_id, viewer=actor)

    def attendance_overdue(
        self,
        actor: Mapping[str, Any],
        *,
        session_id: int | None = None,
    ) -> list[dict[str, Any]]:
        self._require_role(actor, STAFF_ROLES)
        with self._connect() as connection:
            resolved_session = self._resolve_session_id(connection, actor, session_id)
            rows = connection.execute(
                """
                SELECT id FROM camp_attendance_events
                WHERE session_id = ? AND status = 'open' AND deadline_at_ms < ?
                ORDER BY deadline_at_ms
                """,
                (resolved_session, _now_ms()),
            ).fetchall()
            return [self._attendance_event_payload(connection, int(row["id"]), viewer=actor) for row in rows]

    # -- alerts and drills ----------------------------------------------

    def list_alert_playbooks(self, actor: Mapping[str, Any]) -> list[dict[str, Any]]:
        self._require_role(actor, STAFF_ROLES)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM camp_alert_playbooks WHERE active = 1 ORDER BY title"
            ).fetchall()
            return [
                {
                    **dict(row),
                    "steps": _json_load(row["steps_json"], []),
                    "roles": _json_load(row["roles_json"], []),
                }
                for row in rows
            ]

    def _alert_payload(self, connection: sqlite3.Connection, alert_id: int) -> dict[str, Any]:
        row = connection.execute(
            """
            SELECT a.*, p.title, p.steps_json, p.roles_json,
                   u.login AS created_by_login, z.name AS zone_name
            FROM camp_alerts a
            JOIN camp_alert_playbooks p ON p.id = a.playbook_id
            LEFT JOIN users u ON u.id = a.created_by
            LEFT JOIN camp_zones z ON z.id = a.zone_id
            WHERE a.id = ?
            """,
            (alert_id,),
        ).fetchone()
        if row is None:
            raise CampError("alert_not_found", "Alert not found", status_code=404)
        acks = connection.execute(
            """
            SELECT ack.user_id, ack.step_index, ack.acked_at_ms,
                   u.login, COALESCE(cp.display_name, u.login) AS display_name,
                   COALESCE(cp.role, 'unknown') AS camp_role
            FROM camp_alert_acks ack
            JOIN users u ON u.id = ack.user_id
            LEFT JOIN camp_people cp ON cp.user_id = u.id AND cp.session_id = ?
            WHERE ack.alert_id = ?
            ORDER BY ack.acked_at_ms
            """,
            (int(row["session_id"]), alert_id),
        ).fetchall()
        payload = dict(row)
        payload["steps"] = _json_load(row["steps_json"], [])
        payload["required_roles"] = _json_load(row["roles_json"], [])
        payload["acks"] = [dict(ack) for ack in acks]
        payload["ack_count"] = len({int(ack["user_id"]) for ack in acks})
        return payload

    def start_alert(
        self,
        actor: Mapping[str, Any],
        *,
        session_id: int | None = None,
        kind: str,
        drill: bool = False,
        zone_id: int | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        actor_role = str(actor.get("role") or "")
        if actor_role not in {"director", "security"} and not (
            actor_role == "medic" and kind == "medical"
        ):
            raise CampError(
                "alert_forbidden",
                "Only director/security can start this alert",
                status_code=403,
            )
        with self._connect() as connection:
            resolved_session = self._resolve_session_id(connection, actor, session_id)
            playbook = connection.execute(
                "SELECT * FROM camp_alert_playbooks WHERE kind = ? AND active = 1",
                (kind,),
            ).fetchone()
            if playbook is None:
                raise CampError("playbook_not_found", "Unknown alert playbook", status_code=404)
            if zone_id is not None:
                zone = connection.execute(
                    "SELECT id FROM camp_zones WHERE id = ? AND session_id = ?",
                    (zone_id, resolved_session),
                ).fetchone()
                if zone is None:
                    raise CampError("zone_not_found", "Zone not found", status_code=404)
            if not drill:
                existing = connection.execute(
                    """
                    SELECT id FROM camp_alerts
                    WHERE session_id = ? AND kind = ? AND drill = 0 AND status != 'closed'
                    LIMIT 1
                    """,
                    (resolved_session, kind),
                ).fetchone()
                if existing is not None:
                    raise CampError(
                        "alert_already_open",
                        "This alert is already open; acknowledge it instead",
                        status_code=409,
                        details={"alert_id": int(existing["id"])},
                    )
            cursor = connection.execute(
                """
                INSERT INTO camp_alerts(
                    session_id, playbook_id, kind, drill, status, zone_id, note, created_by, created_at_ms
                ) VALUES (?, ?, ?, ?, 'open', ?, ?, ?, ?)
                """,
                (
                    resolved_session,
                    int(playbook["id"]),
                    kind,
                    1 if drill else 0,
                    zone_id,
                    (note or "").strip()[:2000] or None,
                    actor.get("user_id"),
                    _now_ms(),
                ),
            )
            alert_id = int(cursor.lastrowid)
            self._audit(
                connection,
                actor,
                "alert.started",
                details={"alert_id": alert_id, "kind": kind, "drill": bool(drill)},
            )
            return self._alert_payload(connection, alert_id)

    def list_alerts(
        self,
        actor: Mapping[str, Any],
        *,
        session_id: int | None = None,
        status: str | None = None,
        kind: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        self._require_role(actor, STAFF_ROLES)
        with self._connect() as connection:
            resolved_session = self._resolve_session_id(connection, actor, session_id)
            clauses = ["session_id = ?"]
            params: list[Any] = [resolved_session]
            if status:
                if status not in {"open", "acknowledged", "closed"}:
                    raise CampError("invalid_status", "Invalid alert status")
                clauses.append("status = ?")
                params.append(status)
            if kind:
                clauses.append("kind = ?")
                params.append(kind)
            params.append(max(1, min(int(limit), 300)))
            rows = connection.execute(
                f"""
                SELECT id FROM camp_alerts
                WHERE {' AND '.join(clauses)}
                ORDER BY CASE status WHEN 'open' THEN 0 WHEN 'acknowledged' THEN 1 ELSE 2 END,
                         created_at_ms DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
            return [self._alert_payload(connection, int(row["id"])) for row in rows]

    def get_alert(self, actor: Mapping[str, Any], *, alert_id: int) -> dict[str, Any]:
        self._require_role(actor, STAFF_ROLES)
        with self._connect() as connection:
            return self._alert_payload(connection, alert_id)

    def acknowledge_alert(
        self,
        actor: Mapping[str, Any],
        *,
        alert_id: int,
        step_index: int = 0,
        note: str | None = None,
    ) -> dict[str, Any]:
        self._require_role(actor, STAFF_ROLES)
        with self._connect() as connection:
            alert = connection.execute(
                "SELECT * FROM camp_alerts WHERE id = ?", (alert_id,)
            ).fetchone()
            if alert is None:
                raise CampError("alert_not_found", "Alert not found", status_code=404)
            self._guard_session(actor, int(alert["session_id"]))
            if str(alert["status"]) == "closed":
                raise CampError("alert_closed", "Alert is already closed", status_code=409)
            playbook = connection.execute(
                "SELECT steps_json FROM camp_alert_playbooks WHERE id = ?",
                (int(alert["playbook_id"]),),
            ).fetchone()
            steps = _json_load(playbook["steps_json"], []) if playbook else []
            if step_index < 0 or step_index >= max(1, len(steps)):
                raise CampError("invalid_step", "Unknown playbook step")
            connection.execute(
                """
                INSERT OR IGNORE INTO camp_alert_acks(alert_id, user_id, step_index, acked_at_ms)
                VALUES (?, ?, ?, ?)
                """,
                (alert_id, actor.get("user_id"), step_index, _now_ms()),
            )
            connection.execute(
                "UPDATE camp_alerts SET status = 'acknowledged' WHERE id = ? AND status = 'open'",
                (alert_id,),
            )
            self._audit(
                connection,
                actor,
                "alert.acknowledged",
                details={
                    "alert_id": alert_id,
                    "step_index": step_index,
                    "note": (note or "")[:1000],
                },
            )
            return self._alert_payload(connection, alert_id)

    def close_alert(
        self,
        actor: Mapping[str, Any],
        *,
        alert_id: int,
        note: str | None = None,
        after_action: str | None = None,
    ) -> dict[str, Any]:
        self._require_role(actor, {"director", "security", "medic"})
        with self._connect() as connection:
            alert = connection.execute(
                "SELECT * FROM camp_alerts WHERE id = ?", (alert_id,)
            ).fetchone()
            if alert is None:
                raise CampError("alert_not_found", "Alert not found", status_code=404)
            self._guard_session(actor, int(alert["session_id"]))
            if str(alert["status"]) == "closed":
                raise CampError("alert_closed", "Alert is already closed", status_code=409)
            if actor.get("role") not in {"director", "security"} and alert["created_by"] != actor.get("user_id"):
                raise CampError("alert_forbidden", "Only security, director or the creator can close it", status_code=403)
            connection.execute(
                """
                UPDATE camp_alerts
                SET status = 'closed', closed_by = ?, closed_at_ms = ?,
                    note = COALESCE(?, note), after_action = COALESCE(?, after_action)
                WHERE id = ?
                """,
                (
                    actor.get("user_id"),
                    _now_ms(),
                    (note or "").strip()[:2000] or None,
                    (after_action or "").strip()[:4000] or None,
                    alert_id,
                ),
            )
            self._audit(
                connection,
                actor,
                "alert.closed",
                details={"alert_id": alert_id, "drill": bool(alert["drill"])},
            )
            return self._alert_payload(connection, alert_id)

    # -- zones and scans -------------------------------------------------

    def create_zone(
        self,
        actor: Mapping[str, Any],
        *,
        session_id: int | None = None,
        name: str,
        kind: str = "checkpoint",
        parent_id: int | None = None,
    ) -> dict[str, Any]:
        self._require_role(actor, {"director", "security"})
        clean = name.strip()
        if not clean:
            raise CampError("invalid_name", "Zone name must not be empty")
        if kind not in {"checkpoint", "building", "gate", "medical", "other"}:
            raise CampError("invalid_kind", "Invalid zone kind")
        with self._connect() as connection:
            resolved_session = self._resolve_session_id(connection, actor, session_id)
            if parent_id is not None:
                parent = connection.execute(
                    "SELECT id FROM camp_zones WHERE id = ? AND session_id = ?",
                    (parent_id, resolved_session),
                ).fetchone()
                if parent is None:
                    raise CampError("zone_not_found", "Parent zone not found", status_code=404)
            try:
                cursor = connection.execute(
                    "INSERT INTO camp_zones(session_id, name, kind, parent_id) VALUES (?, ?, ?, ?)",
                    (resolved_session, clean, kind, parent_id),
                )
            except sqlite3.IntegrityError as exc:
                raise CampError("zone_exists", "Zone already exists", status_code=409) from exc
            zone_id = int(cursor.lastrowid)
            self._audit(
                connection,
                actor,
                "zone.created",
                details={"zone_id": zone_id, "name": clean, "kind": kind},
            )
            return dict(
                connection.execute("SELECT * FROM camp_zones WHERE id = ?", (zone_id,)).fetchone()
            )

    def list_zones(
        self,
        actor: Mapping[str, Any],
        *,
        session_id: int | None = None,
    ) -> list[dict[str, Any]]:
        self._require_role(actor, STAFF_ROLES)
        with self._connect() as connection:
            resolved_session = self._resolve_session_id(connection, actor, session_id)
            rows = connection.execute(
                "SELECT * FROM camp_zones WHERE session_id = ? ORDER BY kind, name",
                (resolved_session,),
            ).fetchall()
            return [dict(row) for row in rows]

    def scan_person(
        self,
        actor: Mapping[str, Any],
        *,
        zone_id: int,
        person_id: int | None = None,
        badge_code: str | None = None,
        source: str = "staff",
        device_id: str | None = None,
        scanned_at_ms: int | None = None,
    ) -> dict[str, Any]:
        self._require_role(actor, {"counselor", "director", "security", "medic"})
        if (person_id is None) == (not badge_code):
            raise CampError("scan_target_required", "Provide exactly one of person_id or badge_code")
        if source not in {"staff", "kiosk", "import"}:
            raise CampError("invalid_source", "Invalid scan source")
        with self._connect() as connection:
            zone = connection.execute("SELECT * FROM camp_zones WHERE id = ?", (zone_id,)).fetchone()
            if zone is None:
                raise CampError("zone_not_found", "Zone not found", status_code=404)
            self._guard_session(actor, int(zone["session_id"]))
            if person_id is not None:
                person = connection.execute(
                    "SELECT * FROM camp_people WHERE id = ? AND session_id = ?",
                    (person_id, int(zone["session_id"])),
                ).fetchone()
            else:
                person = connection.execute(
                    "SELECT * FROM camp_people WHERE badge_code = ? AND session_id = ?",
                    (badge_code, int(zone["session_id"])),
                ).fetchone()
            if person is None:
                raise CampError("person_not_found", "Badge or person not found in this session", status_code=404)
            at = int(scanned_at_ms or _now_ms())
            cursor = connection.execute(
                """
                INSERT INTO camp_scans(person_id, zone_id, scanned_at_ms, device_id, source, created_at_ms)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (int(person["id"]), zone_id, at, device_id, source, _now_ms()),
            )
            scan_id = int(cursor.lastrowid)
            self._audit(
                connection,
                actor,
                "scan.recorded",
                person_id=int(person["id"]),
                details={"scan_id": scan_id, "zone_id": zone_id, "source": source},
            )
            return {
                "scan": dict(
                    connection.execute("SELECT * FROM camp_scans WHERE id = ?", (scan_id,)).fetchone()
                ),
                "person": dict(person),
                "zone": dict(zone),
            }

    def last_seen(self, actor: Mapping[str, Any], *, person_id: int) -> dict[str, Any]:
        self._require_role(actor, STAFF_ROLES)
        with self._connect() as connection:
            person = connection.execute(
                "SELECT * FROM camp_people WHERE id = ?", (person_id,)
            ).fetchone()
            if person is None:
                raise CampError("person_not_found", "Person not found", status_code=404)
            self._guard_session(actor, int(person["session_id"]))
            row = connection.execute(
                """
                SELECT s.*, z.name AS zone_name, z.kind AS zone_kind
                FROM camp_scans s
                JOIN camp_zones z ON z.id = s.zone_id
                WHERE s.person_id = ?
                ORDER BY s.scanned_at_ms DESC, s.id DESC
                LIMIT 1
                """,
                (person_id,),
            ).fetchone()
            return {"person": dict(person), "last_seen": dict(row) if row else None}

    def zone_monitor(
        self,
        actor: Mapping[str, Any],
        *,
        session_id: int | None = None,
        minutes: int = 120,
    ) -> list[dict[str, Any]]:
        self._require_role(actor, STAFF_ROLES)
        with self._connect() as connection:
            resolved_session = self._resolve_session_id(connection, actor, session_id)
            since = _now_ms() - max(1, min(int(minutes), 1440)) * 60_000
            rows = connection.execute(
                """
                SELECT z.id, z.name, z.kind,
                       COUNT(s.id) AS scan_count,
                       COUNT(DISTINCT s.person_id) AS people_count,
                       MAX(s.scanned_at_ms) AS last_scan_ms
                FROM camp_zones z
                LEFT JOIN camp_scans s ON s.zone_id = z.id AND s.scanned_at_ms >= ?
                WHERE z.session_id = ?
                GROUP BY z.id
                ORDER BY z.kind, z.name
                """,
                (since, resolved_session),
            ).fetchall()
            return [dict(row) for row in rows]

    def list_zone_scans(
        self,
        actor: Mapping[str, Any],
        *,
        zone_id: int,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        self._require_role(actor, STAFF_ROLES)
        with self._connect() as connection:
            zone = connection.execute("SELECT * FROM camp_zones WHERE id = ?", (zone_id,)).fetchone()
            if zone is None:
                raise CampError("zone_not_found", "Zone not found", status_code=404)
            self._guard_session(actor, int(zone["session_id"]))
            rows = connection.execute(
                """
                SELECT s.*, p.display_name, p.badge_code, p.role, p.room
                FROM camp_scans s
                JOIN camp_people p ON p.id = s.person_id
                WHERE s.zone_id = ?
                ORDER BY s.scanned_at_ms DESC, s.id DESC
                LIMIT ?
                """,
                (zone_id, max(1, min(int(limit), 500))),
            ).fetchall()
            return [dict(row) for row in rows]

    # -- duty and handover ----------------------------------------------

    def _staff_person_for_user(
        self,
        connection: sqlite3.Connection,
        *,
        user_id: int,
        session_id: int,
    ) -> sqlite3.Row:
        row = connection.execute(
            """
            SELECT * FROM camp_people
            WHERE user_id = ? AND session_id = ? AND role IN
                ('counselor','director','security','medic','it','kitchen')
              AND status = 'active'
            """,
            (user_id, session_id),
        ).fetchone()
        if row is None:
            raise CampError("staff_not_found", "User is not active staff in this session", status_code=404)
        return row

    def create_duty_shift(
        self,
        actor: Mapping[str, Any],
        *,
        session_id: int | None = None,
        user_id: int,
        role: str = "counselor",
        starts_at_ms: int,
        ends_at_ms: int,
        note: str | None = None,
    ) -> dict[str, Any]:
        self._require_role(actor, MANAGE_ROLES)
        if role not in STAFF_ROLES:
            raise CampError("invalid_role", "Duty role must be a staff role")
        if int(ends_at_ms) <= int(starts_at_ms):
            raise CampError("invalid_dates", "Shift end must be after start")
        with self._connect() as connection:
            resolved_session = self._resolve_session_id(connection, actor, session_id)
            person = self._staff_person_for_user(
                connection, user_id=user_id, session_id=resolved_session
            )
            cursor = connection.execute(
                """
                INSERT INTO camp_duty_shifts(session_id, user_id, role, starts_at_ms, ends_at_ms, note)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    resolved_session,
                    user_id,
                    role,
                    int(starts_at_ms),
                    int(ends_at_ms),
                    (note or "").strip()[:1000] or None,
                ),
            )
            shift_id = int(cursor.lastrowid)
            self._audit(
                connection,
                actor,
                "duty.created",
                person_id=int(person["id"]),
                details={"shift_id": shift_id, "user_id": user_id},
            )
            return dict(
                connection.execute("SELECT * FROM camp_duty_shifts WHERE id = ?", (shift_id,)).fetchone()
            )

    def list_duty_shifts(
        self,
        actor: Mapping[str, Any],
        *,
        session_id: int | None = None,
        from_ms: int | None = None,
        to_ms: int | None = None,
    ) -> list[dict[str, Any]]:
        self._require_role(actor, STAFF_ROLES)
        with self._connect() as connection:
            resolved_session = self._resolve_session_id(connection, actor, session_id)
            clauses = ["d.session_id = ?"]
            params: list[Any] = [resolved_session]
            if from_ms is not None:
                clauses.append("d.ends_at_ms >= ?")
                params.append(int(from_ms))
            if to_ms is not None:
                clauses.append("d.starts_at_ms <= ?")
                params.append(int(to_ms))
            rows = connection.execute(
                f"""
                SELECT d.*, COALESCE(p.display_name, u.login) AS display_name,
                       (SELECT COUNT(*) FROM camp_handover h WHERE h.session_id = d.session_id) AS handover_count
                FROM camp_duty_shifts d
                LEFT JOIN camp_people p ON p.user_id = d.user_id AND p.session_id = d.session_id
                LEFT JOIN users u ON u.id = d.user_id
                WHERE {' AND '.join(clauses)}
                ORDER BY d.starts_at_ms
                """,
                params,
            ).fetchall()
            return [dict(row) for row in rows]

    def create_handover(
        self,
        actor: Mapping[str, Any],
        *,
        session_id: int | None = None,
        to_user_id: int,
        notes: str,
        open_items: list[Any] | None = None,
    ) -> dict[str, Any]:
        self._require_role(actor, {"counselor", "director", "security"})
        if not notes.strip():
            raise CampError("invalid_notes", "Handover notes must not be empty")
        with self._connect() as connection:
            resolved_session = self._resolve_session_id(connection, actor, session_id)
            self._staff_person_for_user(connection, user_id=to_user_id, session_id=resolved_session)
            cursor = connection.execute(
                """
                INSERT INTO camp_handover(
                    session_id, from_user_id, to_user_id, notes, open_items_json, created_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    resolved_session,
                    actor.get("user_id"),
                    to_user_id,
                    notes.strip()[:4000],
                    _json(open_items or []),
                    _now_ms(),
                ),
            )
            handover_id = int(cursor.lastrowid)
            self._audit(
                connection,
                actor,
                "handover.created",
                details={"handover_id": handover_id, "to_user_id": to_user_id},
            )
            return self._handover_payload(connection, handover_id)

    def _handover_payload(self, connection: sqlite3.Connection, handover_id: int) -> dict[str, Any]:
        row = connection.execute(
            """
            SELECT h.*, fu.login AS from_login, tu.login AS to_login,
                   COALESCE(fp.display_name, fu.login) AS from_display_name,
                   COALESCE(tp.display_name, tu.login) AS to_display_name
            FROM camp_handover h
            LEFT JOIN users fu ON fu.id = h.from_user_id
            LEFT JOIN users tu ON tu.id = h.to_user_id
            LEFT JOIN camp_people fp ON fp.user_id = h.from_user_id AND fp.session_id = h.session_id
            LEFT JOIN camp_people tp ON tp.user_id = h.to_user_id AND tp.session_id = h.session_id
            WHERE h.id = ?
            """,
            (handover_id,),
        ).fetchone()
        if row is None:
            raise CampError("handover_not_found", "Handover not found", status_code=404)
        payload = dict(row)
        payload["open_items"] = _json_load(row["open_items_json"], [])
        payload["acknowledged"] = row["acknowledged_at_ms"] is not None
        return payload

    def list_handovers(
        self,
        actor: Mapping[str, Any],
        *,
        session_id: int | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        self._require_role(actor, STAFF_ROLES)
        with self._connect() as connection:
            resolved_session = self._resolve_session_id(connection, actor, session_id)
            clauses = ["session_id = ?"]
            params: list[Any] = [resolved_session]
            if actor.get("role") == "counselor":
                clauses.append("(from_user_id = ? OR to_user_id = ?)")
                params.extend([actor.get("user_id"), actor.get("user_id")])
            params.append(max(1, min(int(limit), 300)))
            rows = connection.execute(
                f"""
                SELECT id FROM camp_handover
                WHERE {' AND '.join(clauses)}
                ORDER BY created_at_ms DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
            return [self._handover_payload(connection, int(row["id"])) for row in rows]

    def acknowledge_handover(self, actor: Mapping[str, Any], *, handover_id: int) -> dict[str, Any]:
        self._require_role(actor, STAFF_ROLES)
        with self._connect() as connection:
            handover = connection.execute(
                "SELECT * FROM camp_handover WHERE id = ?", (handover_id,)
            ).fetchone()
            if handover is None:
                raise CampError("handover_not_found", "Handover not found", status_code=404)
            self._guard_session(actor, int(handover["session_id"]))
            if actor.get("role") != "director" and handover["to_user_id"] != actor.get("user_id"):
                raise CampError("handover_forbidden", "Only the receiving staff member can acknowledge", status_code=403)
            if handover["acknowledged_at_ms"] is not None:
                return self._handover_payload(connection, handover_id)
            connection.execute(
                "UPDATE camp_handover SET acknowledged_at_ms = ? WHERE id = ?",
                (_now_ms(), handover_id),
            )
            self._audit(
                connection,
                actor,
                "handover.acknowledged",
                details={"handover_id": handover_id},
            )
            return self._handover_payload(connection, handover_id)

    # -- pickup and gate movements --------------------------------------

    def create_pickup_auth(
        self,
        actor: Mapping[str, Any],
        *,
        person_id: int,
        adult_name: str,
        relationship: str | None = None,
        adult_document: str | None = None,
        restrictions: str | None = None,
    ) -> dict[str, Any]:
        self._require_role(actor, {"counselor", "director", "security"})
        clean_name = adult_name.strip()
        if not clean_name:
            raise CampError("invalid_name", "Adult name must not be empty")
        with self._connect() as connection:
            person = connection.execute(
                "SELECT * FROM camp_people WHERE id = ?", (person_id,)
            ).fetchone()
            if person is None:
                raise CampError("person_not_found", "Person not found", status_code=404)
            self._guard_session(actor, int(person["session_id"]))
            if person["role"] != "child":
                raise CampError("pickup_child_only", "Pickup authorisations apply to children only")
            qr_code = "PICKUP-" + secrets.token_urlsafe(18)
            cursor = connection.execute(
                """
                INSERT INTO camp_pickup_auth(
                    person_id, adult_name, adult_document, relationship, qr_code,
                    restrictions, active, created_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    person_id,
                    clean_name,
                    (adult_document or "").strip()[:200] or None,
                    (relationship or "").strip()[:120] or None,
                    qr_code,
                    (restrictions or "").strip()[:1000] or None,
                    _now_ms(),
                ),
            )
            auth_id = int(cursor.lastrowid)
            self._audit(
                connection,
                actor,
                "pickup.authorised",
                person_id=person_id,
                details={"auth_id": auth_id},
            )
            return dict(
                connection.execute("SELECT * FROM camp_pickup_auth WHERE id = ?", (auth_id,)).fetchone()
            )

    def list_pickup_auth(
        self,
        actor: Mapping[str, Any],
        *,
        person_id: int | None = None,
        include_inactive: bool = False,
    ) -> list[dict[str, Any]]:
        self._require_role(actor, {"counselor", "director", "security"})
        with self._connect() as connection:
            clauses = ["1 = 1"]
            params: list[Any] = []
            if actor.get("session_id") is not None:
                clauses.append("p.session_id = ?")
                params.append(int(actor["session_id"]))
            if person_id is not None:
                clauses.append("a.person_id = ?")
                params.append(person_id)
            if not include_inactive:
                clauses.append("a.active = 1")
            rows = connection.execute(
                f"""
                SELECT a.*, p.display_name, p.badge_code, p.unit_id
                FROM camp_pickup_auth a
                JOIN camp_people p ON p.id = a.person_id
                WHERE {' AND '.join(clauses)}
                ORDER BY a.created_at_ms DESC
                """,
                params,
            ).fetchall()
            return [dict(row) for row in rows]

    def verify_pickup(self, actor: Mapping[str, Any], *, qr_code: str) -> dict[str, Any]:
        self._require_role(actor, {"counselor", "director", "security"})
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT a.*, p.display_name, p.badge_code, p.role, p.status AS person_status,
                       p.session_id, u.name AS unit_name
                FROM camp_pickup_auth a
                JOIN camp_people p ON p.id = a.person_id
                LEFT JOIN camp_units u ON u.id = p.unit_id
                WHERE a.qr_code = ? AND a.active = 1
                """,
                (qr_code.strip(),),
            ).fetchone()
            if row is None:
                raise CampError("pickup_not_found", "Pickup authorisation not found", status_code=404)
            self._guard_session(actor, int(row["session_id"]))
            return dict(row)

    def record_movement(
        self,
        actor: Mapping[str, Any],
        *,
        person_id: int,
        direction: str,
        qr_code: str | None = None,
        zone_id: int | None = None,
        override_reason: str | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        self._require_role(actor, {"counselor", "director", "security"})
        if direction not in {"out", "in"}:
            raise CampError("invalid_direction", "Direction must be out or in")
        with self._connect() as connection:
            person = connection.execute(
                "SELECT * FROM camp_people WHERE id = ?", (person_id,)
            ).fetchone()
            if person is None:
                raise CampError("person_not_found", "Person not found", status_code=404)
            self._guard_session(actor, int(person["session_id"]))
            if person["role"] != "child":
                raise CampError("movement_child_only", "Gate movements apply to children only")
            last = connection.execute(
                """
                SELECT direction FROM camp_movements
                WHERE person_id = ?
                ORDER BY at_ms DESC, id DESC
                LIMIT 1
                """,
                (person_id,),
            ).fetchone()
            current = str(last["direction"]) if last else "in"
            if current == direction:
                raise CampError(
                    "movement_conflict",
                    f"Child is already marked {direction}",
                    status_code=409,
                )
            auth_id: int | None = None
            if direction == "out":
                if qr_code:
                    auth = connection.execute(
                        """
                        SELECT * FROM camp_pickup_auth
                        WHERE qr_code = ? AND person_id = ? AND active = 1
                        """,
                        (qr_code.strip(), person_id),
                    ).fetchone()
                    if auth is None:
                        raise CampError("pickup_not_found", "Pickup authorisation does not match this child", status_code=404)
                    if auth["restrictions"] and not (override_reason or "").strip():
                        raise CampError(
                            "pickup_restricted",
                            "This pickup has restrictions; record an override reason",
                            status_code=409,
                            details={"restrictions": auth["restrictions"]},
                        )
                    auth_id = int(auth["id"])
                elif not (override_reason or "").strip():
                    raise CampError(
                        "pickup_auth_required",
                        "Scan a pickup QR or record an override reason",
                        status_code=409,
                    )
            if zone_id is not None:
                zone = connection.execute(
                    "SELECT id FROM camp_zones WHERE id = ? AND session_id = ?",
                    (zone_id, int(person["session_id"])),
                ).fetchone()
                if zone is None:
                    raise CampError("zone_not_found", "Zone not found", status_code=404)
            cursor = connection.execute(
                """
                INSERT INTO camp_movements(
                    person_id, direction, zone_id, authorized_by, pickup_auth_id, at_ms, note
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    person_id,
                    direction,
                    zone_id,
                    actor.get("user_id"),
                    auth_id,
                    _now_ms(),
                    (note or "").strip()[:1000] or None,
                ),
            )
            movement_id = int(cursor.lastrowid)
            self._audit(
                connection,
                actor,
                "movement.recorded",
                person_id=person_id,
                details={
                    "movement_id": movement_id,
                    "direction": direction,
                    "override": (override_reason or "")[:1000],
                },
            )
            return dict(
                connection.execute("SELECT * FROM camp_movements WHERE id = ?", (movement_id,)).fetchone()
            )

    def gate_log(
        self,
        actor: Mapping[str, Any],
        *,
        session_id: int | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        self._require_role(actor, {"counselor", "director", "security"})
        with self._connect() as connection:
            resolved_session = self._resolve_session_id(connection, actor, session_id)
            rows = connection.execute(
                """
                SELECT m.*, p.display_name, p.badge_code, u.name AS unit_name,
                       z.name AS zone_name, a.adult_name, a.restrictions
                FROM camp_movements m
                JOIN camp_people p ON p.id = m.person_id
                LEFT JOIN camp_units u ON u.id = p.unit_id
                LEFT JOIN camp_zones z ON z.id = m.zone_id
                LEFT JOIN camp_pickup_auth a ON a.id = m.pickup_auth_id
                WHERE p.session_id = ?
                ORDER BY m.at_ms DESC, m.id DESC
                LIMIT ?
                """,
                (resolved_session, max(1, min(int(limit), 500))),
            ).fetchall()
            return [dict(row) for row in rows]

    # -- dietary and digest ---------------------------------------------

    def set_dietary(
        self,
        actor: Mapping[str, Any],
        *,
        person_id: int,
        restriction: str,
        note: str | None = None,
        valid_to_ms: int | None = None,
    ) -> dict[str, Any]:
        self._require_role(actor, {"counselor", "director", "medic", "kitchen"})
        clean = restriction.strip()
        if not clean:
            raise CampError("invalid_restriction", "Restriction must not be empty")
        with self._connect() as connection:
            person = connection.execute(
                "SELECT * FROM camp_people WHERE id = ?", (person_id,)
            ).fetchone()
            if person is None:
                raise CampError("person_not_found", "Person not found", status_code=404)
            self._guard_session(actor, int(person["session_id"]))
            if person["role"] != "child":
                raise CampError("dietary_child_only", "Dietary records apply to children only")
            connection.execute(
                """
                INSERT INTO camp_dietary(person_id, restriction, confirmed_by, valid_to_ms, note)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(person_id, restriction) DO UPDATE SET
                    confirmed_by = excluded.confirmed_by,
                    valid_to_ms = excluded.valid_to_ms,
                    note = excluded.note
                """,
                (
                    person_id,
                    clean[:200],
                    actor.get("user_id"),
                    int(valid_to_ms) if valid_to_ms is not None else None,
                    (note or "").strip()[:1000] or None,
                ),
            )
            self._audit(
                connection,
                actor,
                "dietary.set",
                person_id=person_id,
                details={"restriction": clean[:200]},
            )
            return dict(
                connection.execute(
                    "SELECT * FROM camp_dietary WHERE person_id = ? AND restriction = ?",
                    (person_id, clean[:200]),
                ).fetchone()
            )

    def remove_dietary(
        self,
        actor: Mapping[str, Any],
        *,
        person_id: int,
        restriction: str,
    ) -> dict[str, Any]:
        self._require_role(actor, {"counselor", "director", "medic", "kitchen"})
        with self._connect() as connection:
            person = connection.execute(
                "SELECT session_id FROM camp_people WHERE id = ?", (person_id,)
            ).fetchone()
            if person is None:
                raise CampError("person_not_found", "Person not found", status_code=404)
            self._guard_session(actor, int(person["session_id"]))
            deleted = connection.execute(
                "DELETE FROM camp_dietary WHERE person_id = ? AND restriction = ?",
                (person_id, restriction.strip()[:200]),
            ).rowcount
            if deleted == 0:
                raise CampError("dietary_not_found", "Dietary record not found", status_code=404)
            self._audit(
                connection,
                actor,
                "dietary.removed",
                person_id=person_id,
                details={"restriction": restriction[:200]},
            )
            return {"status": "ok", "deleted": deleted}

    def list_dietary(
        self,
        actor: Mapping[str, Any],
        *,
        session_id: int | None = None,
        unit_id: int | None = None,
    ) -> list[dict[str, Any]]:
        self._require_role(actor, {"counselor", "director", "medic", "kitchen", "security"})
        with self._connect() as connection:
            resolved_session = self._resolve_session_id(connection, actor, session_id)
            clauses = ["p.session_id = ?", "p.role = 'child'", "p.status = 'active'"]
            params: list[Any] = [resolved_session]
            if unit_id is not None:
                clauses.append("p.unit_id = ?")
                params.append(unit_id)
            rows = connection.execute(
                f"""
                SELECT d.*, p.display_name, p.badge_code, p.room, u.name AS unit_name
                FROM camp_dietary d
                JOIN camp_people p ON p.id = d.person_id
                LEFT JOIN camp_units u ON u.id = p.unit_id
                WHERE {' AND '.join(clauses)}
                ORDER BY u.name, p.display_name, d.restriction
                """,
                params,
            ).fetchall()
            return [dict(row) for row in rows]

    def link_guardian(
        self,
        actor: Mapping[str, Any],
        *,
        person_id: int,
        parent_person_id: int,
        relationship: str | None = None,
    ) -> dict[str, Any]:
        self._require_role(actor, {"counselor", "director"})
        with self._connect() as connection:
            child = connection.execute(
                "SELECT * FROM camp_people WHERE id = ?", (person_id,)
            ).fetchone()
            parent = connection.execute(
                "SELECT * FROM camp_people WHERE id = ?", (parent_person_id,)
            ).fetchone()
            if child is None or parent is None:
                raise CampError("person_not_found", "Person not found", status_code=404)
            self._guard_session(actor, int(child["session_id"]))
            if child["role"] != "child" or parent["role"] != "parent":
                raise CampError("guardian_roles", "Link a child to a parent profile")
            if int(child["session_id"]) != int(parent["session_id"]):
                raise CampError("different_sessions", "Child and parent must be in the same session")
            connection.execute(
                """
                INSERT INTO camp_guardians(person_id, parent_person_id, relationship, created_at_ms)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(person_id, parent_person_id) DO UPDATE SET
                    relationship = excluded.relationship
                """,
                (
                    person_id,
                    parent_person_id,
                    (relationship or "").strip()[:120] or None,
                    _now_ms(),
                ),
            )
            self._audit(
                connection,
                actor,
                "guardian.linked",
                person_id=person_id,
                details={"parent_person_id": parent_person_id},
            )
            return dict(
                connection.execute(
                    "SELECT * FROM camp_guardians WHERE person_id = ? AND parent_person_id = ?",
                    (person_id, parent_person_id),
                ).fetchone()
            )

    def list_guardians(
        self,
        actor: Mapping[str, Any],
        *,
        person_id: int | None = None,
    ) -> list[dict[str, Any]]:
        role = str(actor.get("role") or "")
        if role not in STAFF_ROLES and role != "parent":
            raise CampError("role_forbidden", "No access to guardians", status_code=403)
        with self._connect() as connection:
            clauses = ["1 = 1"]
            params: list[Any] = []
            if actor.get("session_id") is not None:
                clauses.append("child.session_id = ?")
                params.append(int(actor["session_id"]))
            if person_id is not None:
                clauses.append("g.person_id = ?")
                params.append(person_id)
            if role == "parent":
                clauses.append("g.parent_person_id = ?")
                params.append(actor.get("camp_person_id"))
            rows = connection.execute(
                f"""
                SELECT g.*, child.display_name AS child_name, parent.display_name AS parent_name
                FROM camp_guardians g
                JOIN camp_people child ON child.id = g.person_id
                JOIN camp_people parent ON parent.id = g.parent_person_id
                WHERE {' AND '.join(clauses)}
                ORDER BY child.display_name
                """,
                params,
            ).fetchall()
            return [dict(row) for row in rows]

    def upsert_digest(
        self,
        actor: Mapping[str, Any],
        *,
        person_id: int,
        date: str,
        text: str,
        photo_id: int | None = None,
    ) -> dict[str, Any]:
        self._require_role(actor, {"counselor", "director"})
        try:
            datetime.strptime(date[:10], "%Y-%m-%d")
        except ValueError as exc:
            raise CampError("invalid_date", "Date must be YYYY-MM-DD") from exc
        clean = text.strip()
        if not clean:
            raise CampError("invalid_text", "Digest text must not be empty")
        with self._connect() as connection:
            person = connection.execute(
                "SELECT * FROM camp_people WHERE id = ?", (person_id,)
            ).fetchone()
            if person is None:
                raise CampError("person_not_found", "Person not found", status_code=404)
            self._guard_session(actor, int(person["session_id"]))
            if person["role"] != "child":
                raise CampError("digest_child_only", "Digests apply to children only")
            connection.execute(
                """
                INSERT INTO camp_digest(person_id, date, text, photo_id, created_by)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(person_id, date) DO UPDATE SET
                    text = excluded.text,
                    photo_id = excluded.photo_id,
                    created_by = excluded.created_by
                """,
                (person_id, date[:10], clean[:4000], photo_id, actor.get("user_id")),
            )
            self._audit(
                connection,
                actor,
                "digest.upserted",
                person_id=person_id,
                details={"date": date[:10]},
            )
            return dict(
                connection.execute(
                    "SELECT * FROM camp_digest WHERE person_id = ? AND date = ?",
                    (person_id, date[:10]),
                ).fetchone()
            )

    def list_digests(
        self,
        actor: Mapping[str, Any],
        *,
        session_id: int | None = None,
        person_id: int | None = None,
        date: str | None = None,
    ) -> list[dict[str, Any]]:
        role = str(actor.get("role") or "")
        if role not in STAFF_ROLES and role not in {"parent", "child"}:
            raise CampError("role_forbidden", "No access to digests", status_code=403)
        with self._connect() as connection:
            resolved_session = self._resolve_session_id(connection, actor, session_id)
            clauses = ["p.session_id = ?"]
            params: list[Any] = [resolved_session]
            if person_id is not None:
                clauses.append("d.person_id = ?")
                params.append(person_id)
            if date:
                clauses.append("d.date = ?")
                params.append(date[:10])
            if role == "parent":
                clauses.append(
                    "d.person_id IN (SELECT person_id FROM camp_guardians WHERE parent_person_id = ?)"
                )
                params.append(actor.get("camp_person_id"))
            elif role == "child":
                clauses.append("d.person_id = ?")
                params.append(actor.get("camp_person_id"))
            rows = connection.execute(
                f"""
                SELECT d.*, p.display_name, p.badge_code, u.name AS unit_name
                FROM camp_digest d
                JOIN camp_people p ON p.id = d.person_id
                LEFT JOIN camp_units u ON u.id = p.unit_id
                WHERE {' AND '.join(clauses)}
                ORDER BY d.date DESC, p.display_name
                """,
                params,
            ).fetchall()
            return [dict(row) for row in rows]

    def mark_digest_sent(
        self,
        actor: Mapping[str, Any],
        *,
        person_id: int,
        date: str,
    ) -> dict[str, Any]:
        self._require_role(actor, {"counselor", "director"})
        with self._connect() as connection:
            person = connection.execute(
                "SELECT session_id FROM camp_people WHERE id = ?", (person_id,)
            ).fetchone()
            if person is None:
                raise CampError("person_not_found", "Person not found", status_code=404)
            self._guard_session(actor, int(person["session_id"]))
            updated = connection.execute(
                "UPDATE camp_digest SET sent_at_ms = ? WHERE person_id = ? AND date = ?",
                (_now_ms(), person_id, date[:10]),
            ).rowcount
            if updated == 0:
                raise CampError("digest_not_found", "Digest not found", status_code=404)
            self._audit(
                connection,
                actor,
                "digest.sent",
                person_id=person_id,
                details={"date": date[:10]},
            )
            return dict(
                connection.execute(
                    "SELECT * FROM camp_digest WHERE person_id = ? AND date = ?",
                    (person_id, date[:10]),
                ).fetchone()
            )

    # -- policy and audit -----------------------------------------------

    def policy_check(
        self,
        actor: Mapping[str, Any],
        *,
        kind: str,
        target_person_id: int | None = None,
        minute_of_day: int | None = None,
        has_consent: bool = False,
    ) -> dict[str, Any]:
        with self._connect() as connection:
            session_id = self._resolve_session_id(connection, actor, None)
            settings_row = connection.execute(
                "SELECT * FROM camp_settings WHERE session_id = ?", (session_id,)
            ).fetchone()
            settings = dict(settings_row) if settings_row else {}
            actor_person = dict(actor)
            target_person = None
            if target_person_id is not None:
                row = connection.execute(
                    "SELECT * FROM camp_people WHERE id = ?", (target_person_id,)
                ).fetchone()
                if row is None:
                    raise CampError("person_not_found", "Target person not found", status_code=404)
                target_person = dict(row)
            if minute_of_day is None:
                local = datetime.now(tz=timezone.utc)
                minute_of_day = local.hour * 60 + local.minute
            if kind == "direct_message":
                if target_person is None:
                    raise CampError("target_required", "target_person_id is required")
                decision = policy.check_direct_message(actor_person, target_person, settings)
            elif kind == "media":
                decision = policy.check_media(actor_person, settings, has_consent=has_consent)
            elif kind == "forward":
                decision = policy.check_forward(actor_person)
            elif kind == "post":
                decision = policy.check_post(actor_person, settings, minute_of_day=int(minute_of_day))
            elif kind == "group":
                if target_person is None:
                    raise CampError("target_required", "target_person_id is required")
                decision = policy.check_group_membership(actor_person, target_person)
            else:
                raise CampError("invalid_policy_kind", "Unknown policy check")
            payload = decision.as_dict()
            payload["policy"] = kind
            payload["session_id"] = session_id
            return payload

    def list_audit(self, actor: Mapping[str, Any], *, limit: int = 100) -> list[dict[str, Any]]:
        self._require_role(actor, MANAGE_ROLES)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM camp_audit ORDER BY id DESC LIMIT ?",
                (max(1, min(int(limit), 500)),),
            ).fetchall()
            return [
                {
                    **dict(row),
                    "details": _json_load(row["details_json"], {}),
                }
                for row in rows
            ]

    # -- media consent --------------------------------------------------

    def set_consent(
        self,
        actor: Mapping[str, Any],
        *,
        person_id: int,
        kind: str,
        granted: bool,
        note: str | None = None,
    ) -> dict[str, Any]:
        self._require_role(actor, {"counselor", "director", "parent"})
        if kind not in {"internal_chat", "parent_digest", "promo", "none"}:
            raise CampError("invalid_consent", "Invalid consent kind")
        with self._connect() as connection:
            person = connection.execute(
                "SELECT * FROM camp_people WHERE id = ?", (person_id,)
            ).fetchone()
            if person is None:
                raise CampError("person_not_found", "Person not found", status_code=404)
            self._guard_session(actor, int(person["session_id"]))
            if person["role"] != "child":
                raise CampError("consent_child_only", "Photo consent applies to children only")
            if actor.get("role") == "parent":
                link = connection.execute(
                    "SELECT 1 FROM camp_guardians WHERE person_id = ? AND parent_person_id = ?",
                    (person_id, actor.get("camp_person_id")),
                ).fetchone()
                if link is None:
                    raise CampError("guardian_forbidden", "Parent is not linked to this child", status_code=403)
            connection.execute(
                """
                INSERT INTO camp_consents(person_id, kind, granted, note, updated_at_ms)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(person_id, kind) DO UPDATE SET
                    granted = excluded.granted,
                    note = excluded.note,
                    updated_at_ms = excluded.updated_at_ms
                """,
                (
                    person_id,
                    kind,
                    1 if granted else 0,
                    (note or "").strip()[:1000] or None,
                    _now_ms(),
                ),
            )
            self._audit(
                connection,
                actor,
                "consent.updated",
                person_id=person_id,
                details={"kind": kind, "granted": bool(granted)},
            )
            return dict(
                connection.execute(
                    "SELECT * FROM camp_consents WHERE person_id = ? AND kind = ?",
                    (person_id, kind),
                ).fetchone()
            )

    def get_consents(self, actor: Mapping[str, Any], *, person_id: int) -> dict[str, Any]:
        role = str(actor.get("role") or "")
        if role not in STAFF_ROLES and role not in {"parent", "child"}:
            raise CampError("role_forbidden", "No access to consents", status_code=403)
        with self._connect() as connection:
            person = connection.execute(
                "SELECT * FROM camp_people WHERE id = ?", (person_id,)
            ).fetchone()
            if person is None:
                raise CampError("person_not_found", "Person not found", status_code=404)
            self._guard_session(actor, int(person["session_id"]))
            if not self._can_view_person(connection, actor, dict(person)):
                raise CampError("person_forbidden", "No access to this child", status_code=403)
            rows = connection.execute(
                "SELECT * FROM camp_consents WHERE person_id = ? ORDER BY kind",
                (person_id,),
            ).fetchall()
            values = {str(row["kind"]): dict(row) for row in rows}
            return {
                "person": dict(person),
                "consents": values,
                "internal_chat": bool(values.get("internal_chat", {}).get("granted")),
                "parent_digest": bool(values.get("parent_digest", {}).get("granted")),
                "promo": bool(values.get("promo", {}).get("granted")),
            }

    def consent_matrix(
        self,
        actor: Mapping[str, Any],
        *,
        session_id: int | None = None,
    ) -> list[dict[str, Any]]:
        self._require_role(actor, STAFF_ROLES)
        with self._connect() as connection:
            resolved_session = self._resolve_session_id(connection, actor, session_id)
            rows = connection.execute(
                """
                SELECT p.id, p.display_name, p.badge_code, u.name AS unit_name,
                       c.kind, c.granted
                FROM camp_people p
                LEFT JOIN camp_units u ON u.id = p.unit_id
                LEFT JOIN camp_consents c ON c.person_id = p.id
                WHERE p.session_id = ? AND p.role = 'child' AND p.status = 'active'
                ORDER BY u.name, p.display_name, c.kind
                """,
                (resolved_session,),
            ).fetchall()
            children: dict[int, dict[str, Any]] = {}
            for row in rows:
                child = children.setdefault(
                    int(row["id"]),
                    {
                        "person_id": int(row["id"]),
                        "display_name": row["display_name"],
                        "badge_code": row["badge_code"],
                        "unit_name": row["unit_name"],
                        "consents": {
                            "internal_chat": False,
                            "parent_digest": False,
                            "promo": False,
                            "none": False,
                        },
                    },
                )
                if row["kind"]:
                    child["consents"][str(row["kind"])] = bool(row["granted"])
            return list(children.values())

    def consent_allows(self, person_id: int, *, kind: str = "internal_chat") -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT granted FROM camp_consents WHERE person_id = ? AND kind = ?",
                (person_id, kind),
            ).fetchone()
            return bool(row and int(row["granted"]))

    # -- kiosks and offline sync ----------------------------------------

    @staticmethod
    def _public_kiosk(row: sqlite3.Row) -> dict[str, Any]:
        payload = dict(row)
        payload.pop("token_hash", None)
        payload["active"] = payload.get("revoked_at_ms") is None
        return payload

    def create_kiosk(
        self,
        actor: Mapping[str, Any],
        *,
        session_id: int | None = None,
        device_id: str,
        zone_id: int,
        scopes: str = "scan",
    ) -> dict[str, Any]:
        self._require_role(actor, {"director", "security"})
        clean_device = device_id.strip()
        if not clean_device:
            raise CampError("invalid_device", "Device id must not be empty")
        scope_set = {part.strip() for part in scopes.split(",") if part.strip()}
        if not scope_set or not scope_set.issubset({"scan"}):
            raise CampError("invalid_scopes", "Supported kiosk scope: scan")
        with self._connect() as connection:
            resolved_session = self._resolve_session_id(connection, actor, session_id)
            zone = connection.execute(
                "SELECT * FROM camp_zones WHERE id = ? AND session_id = ?",
                (zone_id, resolved_session),
            ).fetchone()
            if zone is None:
                raise CampError("zone_not_found", "Zone not found", status_code=404)
            token = "KIOSK-" + secrets.token_urlsafe(24)
            token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
            try:
                cursor = connection.execute(
                    """
                    INSERT INTO camp_kiosks(device_id, zone_id, token_hash, scopes, created_at_ms)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (clean_device[:128], zone_id, token_hash, ",".join(sorted(scope_set)), _now_ms()),
                )
            except sqlite3.IntegrityError as exc:
                raise CampError("kiosk_exists", "Device id is already registered", status_code=409) from exc
            kiosk_id = int(cursor.lastrowid)
            self._audit(
                connection,
                actor,
                "kiosk.created",
                details={"kiosk_id": kiosk_id, "device_id": clean_device[:128], "zone_id": zone_id},
            )
            row = connection.execute(
                "SELECT * FROM camp_kiosks WHERE id = ?", (kiosk_id,)
            ).fetchone()
            return {"item": self._public_kiosk(row), "token": token}

    def list_kiosks(
        self,
        actor: Mapping[str, Any],
        *,
        session_id: int | None = None,
    ) -> list[dict[str, Any]]:
        self._require_role(actor, {"director", "security"})
        with self._connect() as connection:
            resolved_session = self._resolve_session_id(connection, actor, session_id)
            rows = connection.execute(
                """
                SELECT k.*, z.name AS zone_name, z.session_id AS session_id
                FROM camp_kiosks k
                JOIN camp_zones z ON z.id = k.zone_id
                WHERE z.session_id = ?
                ORDER BY k.created_at_ms DESC
                """,
                (resolved_session,),
            ).fetchall()
            now = _now_ms()
            items = []
            for row in rows:
                item = self._public_kiosk(row)
                item["stale"] = item["active"] and (
                    item.get("last_seen_ms") is None
                    or now - int(item["last_seen_ms"]) > 10 * 60_000
                )
                items.append(item)
            return items

    def revoke_kiosk(self, actor: Mapping[str, Any], *, kiosk_id: int) -> dict[str, Any]:
        self._require_role(actor, {"director", "security"})
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT k.*, z.session_id AS session_id
                FROM camp_kiosks k
                JOIN camp_zones z ON z.id = k.zone_id
                WHERE k.id = ?
                """,
                (kiosk_id,),
            ).fetchone()
            if row is None:
                raise CampError("kiosk_not_found", "Kiosk not found", status_code=404)
            self._guard_session(actor, int(row["session_id"]))
            connection.execute(
                "UPDATE camp_kiosks SET revoked_at_ms = ? WHERE id = ?",
                (_now_ms(), kiosk_id),
            )
            self._audit(
                connection,
                actor,
                "kiosk.revoked",
                details={"kiosk_id": kiosk_id, "device_id": row["device_id"]},
            )
            return self._public_kiosk(
                connection.execute("SELECT * FROM camp_kiosks WHERE id = ?", (kiosk_id,)).fetchone()
            )

    def kiosk_scan(
        self,
        *,
        kiosk_token: str,
        person_id: int | None = None,
        badge_code: str | None = None,
        scanned_at_ms: int | None = None,
    ) -> dict[str, Any]:
        if (person_id is None) == (not badge_code):
            raise CampError("scan_target_required", "Provide exactly one of person_id or badge_code")
        token_hash = hashlib.sha256(kiosk_token.strip().encode("utf-8")).hexdigest()
        with self._connect() as connection:
            kiosk = connection.execute(
                """
                SELECT k.*, z.session_id AS session_id
                FROM camp_kiosks k
                JOIN camp_zones z ON z.id = k.zone_id
                WHERE k.token_hash = ?
                """,
                (token_hash,),
            ).fetchone()
            if kiosk is None:
                raise CampError("kiosk_invalid", "Kiosk token is not valid", status_code=401)
            if kiosk["revoked_at_ms"] is not None:
                raise CampError("kiosk_revoked", "Kiosk token has been revoked", status_code=403)
            scopes = {part.strip() for part in str(kiosk["scopes"] or "").split(",")}
            if "scan" not in scopes:
                raise CampError("kiosk_scope", "Kiosk is not allowed to scan", status_code=403)
            if person_id is not None:
                person = connection.execute(
                    "SELECT * FROM camp_people WHERE id = ? AND session_id = ?",
                    (person_id, int(kiosk["session_id"])),
                ).fetchone()
            else:
                person = connection.execute(
                    "SELECT * FROM camp_people WHERE badge_code = ? AND session_id = ?",
                    (badge_code, int(kiosk["session_id"])),
                ).fetchone()
            if person is None:
                raise CampError("person_not_found", "Badge or person not found", status_code=404)
            if person["role"] != "child":
                raise CampError("scan_child_only", "Kiosk scans are for children", status_code=403)
            at = int(scanned_at_ms or _now_ms())
            cursor = connection.execute(
                """
                INSERT INTO camp_scans(person_id, zone_id, scanned_at_ms, device_id, source, created_at_ms)
                VALUES (?, ?, ?, ?, 'kiosk', ?)
                """,
                (int(person["id"]), int(kiosk["zone_id"]), at, kiosk["device_id"], _now_ms()),
            )
            connection.execute(
                "UPDATE camp_kiosks SET last_seen_ms = ? WHERE id = ?",
                (_now_ms(), int(kiosk["id"])),
            )
            scan_id = int(cursor.lastrowid)
            self._audit(
                connection,
                None,
                "kiosk.scan",
                person_id=int(person["id"]),
                details={"scan_id": scan_id, "kiosk_id": int(kiosk["id"]), "source": "kiosk"},
            )
            return {
                "scan": dict(connection.execute("SELECT * FROM camp_scans WHERE id = ?", (scan_id,)).fetchone()),
                "person": dict(person),
                "zone": dict(connection.execute("SELECT * FROM camp_zones WHERE id = ?", (int(kiosk["zone_id"]),)).fetchone()),
                "kiosk": self._public_kiosk(kiosk),
            }

    def sync_offline(
        self,
        actor: Mapping[str, Any],
        *,
        device_id: str | None,
        operations: list[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        self._require_role(actor, STAFF_ROLES)
        if not operations:
            return []
        if len(operations) > 100:
            raise CampError("too_many_operations", "At most 100 operations per sync")
        results: list[dict[str, Any]] = []
        with self._connect() as connection:
            resolved_session = self._resolve_session_id(connection, actor, None)
            for raw in operations:
                op = dict(raw or {})
                op_id = str(op.get("op_id") or "").strip()
                kind = str(op.get("kind") or "").strip()
                payload = op.get("payload") if isinstance(op.get("payload"), dict) else {}
                client_at_ms = op.get("client_at_ms")
                if not op_id or len(op_id) > 128 or not kind:
                    results.append(
                        {"op_id": op_id, "status": "rejected", "error": "op_id and kind are required"}
                    )
                    continue
                existing = connection.execute(
                    "SELECT status, server_at_ms FROM camp_sync_ops WHERE op_id = ?",
                    (op_id,),
                ).fetchone()
                if existing is not None:
                    results.append(
                        {
                            "op_id": op_id,
                            "status": str(existing["status"]),
                            "server_time_ms": int(existing["server_at_ms"]),
                            "replayed": True,
                        }
                    )
                    continue
                status = "accepted"
                error: str | None = None
                try:
                    if kind == "scan":
                        zone_id = int(payload.get("zone_id"))
                        zone = connection.execute(
                            "SELECT * FROM camp_zones WHERE id = ? AND session_id = ?",
                            (zone_id, resolved_session),
                        ).fetchone()
                        if zone is None:
                            raise CampError("zone_not_found", "Zone not found", status_code=404)
                        person_ref = payload.get("person_id")
                        badge_ref = payload.get("badge_code")
                        if (person_ref is None) == (not badge_ref):
                            raise CampError("scan_target_required", "Provide exactly one scan target")
                        if person_ref is not None:
                            person = connection.execute(
                                "SELECT * FROM camp_people WHERE id = ? AND session_id = ?",
                                (int(person_ref), resolved_session),
                            ).fetchone()
                        else:
                            person = connection.execute(
                                "SELECT * FROM camp_people WHERE badge_code = ? AND session_id = ?",
                                (str(badge_ref), resolved_session),
                            ).fetchone()
                        if person is None:
                            raise CampError("person_not_found", "Person not found", status_code=404)
                        at = int(payload.get("scanned_at_ms") or client_at_ms or _now_ms())
                        connection.execute(
                            """
                            INSERT INTO camp_scans(person_id, zone_id, scanned_at_ms, device_id, source, created_at_ms)
                            VALUES (?, ?, ?, ?, 'import', ?)
                            """,
                            (int(person["id"]), zone_id, at, (device_id or "")[:128] or None, _now_ms()),
                        )
                    elif kind == "attendance_mark":
                        event_id = int(payload.get("event_id"))
                        person_id = int(payload.get("person_id"))
                        mark_status = str(payload.get("status") or "")
                        if mark_status not in {"present", "absent", "sick", "medic", "parent", "left"}:
                            raise CampError("invalid_mark", "Invalid attendance mark")
                        event = connection.execute(
                            "SELECT * FROM camp_attendance_events WHERE id = ?", (event_id,)
                        ).fetchone()
                        if event is None:
                            raise CampError("attendance_not_found", "Attendance event not found", status_code=404)
                        self._guard_session(actor, int(event["session_id"]))
                        if str(event["status"]) != "open":
                            raise CampError("attendance_closed", "Attendance event is closed", status_code=409)
                        person = connection.execute(
                            "SELECT * FROM camp_people WHERE id = ? AND session_id = ?",
                            (person_id, resolved_session),
                        ).fetchone()
                        if person is None or person["unit_id"] != event["unit_id"]:
                            raise CampError("person_not_in_unit", "Child is not in this unit", status_code=404)
                        connection.execute(
                            """
                            INSERT INTO camp_attendance_marks(event_id, person_id, status, marked_by, marked_at_ms)
                            VALUES (?, ?, ?, ?, ?)
                            ON CONFLICT(event_id, person_id) DO UPDATE SET
                                status = excluded.status,
                                marked_by = excluded.marked_by,
                                marked_at_ms = excluded.marked_at_ms
                            """,
                            (event_id, person_id, mark_status, actor.get("user_id"), _now_ms()),
                        )
                    else:
                        raise CampError("unsupported_sync_kind", f"Unsupported sync kind: {kind}")
                except (CampError, TypeError, ValueError) as exc:
                    status = "rejected"
                    error = getattr(exc, "message", str(exc))
                server_at = _now_ms()
                connection.execute(
                    """
                    INSERT INTO camp_sync_ops(op_id, device_id, kind, payload_json, client_at_ms, status, server_at_ms)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        op_id,
                        (device_id or "")[:128] or None,
                        kind[:64],
                        _json(dict(payload)),
                        int(client_at_ms) if isinstance(client_at_ms, int) else None,
                        status,
                        server_at,
                    ),
                )
                self._audit(
                    connection,
                    actor,
                    "sync.operation",
                    details={"op_id": op_id, "kind": kind, "status": status},
                )
                result: dict[str, Any] = {
                    "op_id": op_id,
                    "status": status,
                    "server_time_ms": server_at,
                }
                if error:
                    result["error"] = error
                results.append(result)
        return results

    # -- report and status ----------------------------------------------

    def session_report(
        self,
        actor: Mapping[str, Any],
        *,
        session_id: int | None = None,
    ) -> dict[str, Any]:
        self._require_role(actor, STAFF_ROLES)
        with self._connect() as connection:
            resolved_session = self._resolve_session_id(connection, actor, session_id)
            session = dict(self._session(connection, resolved_session))
            by_role_rows = connection.execute(
                "SELECT role, COUNT(*) AS count FROM camp_people WHERE session_id = ? AND status = 'active' GROUP BY role",
                (resolved_session,),
            ).fetchall()
            by_role = {str(row["role"]): int(row["count"]) for row in by_role_rows}
            units = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT u.id, u.name, u.kind, COUNT(p.id) AS child_count
                    FROM camp_units u
                    LEFT JOIN camp_people p ON p.unit_id = u.id AND p.role = 'child' AND p.status = 'active'
                    WHERE u.session_id = ?
                    GROUP BY u.id
                    ORDER BY u.name
                    """,
                    (resolved_session,),
                ).fetchall()
            ]
            attendance = dict(
                connection.execute(
                    """
                    SELECT COUNT(*) AS events,
                           SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) AS open,
                           SUM(CASE WHEN status = 'closed' THEN 1 ELSE 0 END) AS closed
                    FROM camp_attendance_events WHERE session_id = ?
                    """,
                    (resolved_session,),
                ).fetchone()
            )
            marks = {
                str(row["status"]): int(row["count"])
                for row in connection.execute(
                    """
                    SELECT m.status, COUNT(*) AS count
                    FROM camp_attendance_marks m
                    JOIN camp_attendance_events e ON e.id = m.event_id
                    WHERE e.session_id = ?
                    GROUP BY m.status
                    """,
                    (resolved_session,),
                ).fetchall()
            }
            requests = {
                str(row["status"]): int(row["count"])
                for row in connection.execute(
                    "SELECT status, COUNT(*) AS count FROM camp_requests WHERE session_id = ? GROUP BY status",
                    (resolved_session,),
                ).fetchall()
            }
            alerts = dict(
                connection.execute(
                    """
                    SELECT COUNT(*) AS total,
                           SUM(CASE WHEN status != 'closed' THEN 1 ELSE 0 END) AS open,
                           SUM(CASE WHEN drill = 1 THEN 1 ELSE 0 END) AS drills
                    FROM camp_alerts WHERE session_id = ?
                    """,
                    (resolved_session,),
                ).fetchone()
            )
            scan_row = connection.execute(
                """
                SELECT COUNT(*) AS total
                FROM camp_scans s JOIN camp_zones z ON z.id = s.zone_id
                WHERE z.session_id = ?
                """,
                (resolved_session,),
            ).fetchone()
            scan_24h = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM camp_scans s JOIN camp_zones z ON z.id = s.zone_id
                WHERE z.session_id = ? AND s.scanned_at_ms >= ?
                """,
                (resolved_session, _now_ms() - 24 * 60 * 60_000),
            ).fetchone()
            movement_rows = connection.execute(
                """
                SELECT m.direction, COUNT(*) AS count
                FROM camp_movements m JOIN camp_people p ON p.id = m.person_id
                WHERE p.session_id = ?
                GROUP BY m.direction
                """,
                (resolved_session,),
            ).fetchall()
            movements = {str(row["direction"]): int(row["count"]) for row in movement_rows}
            currently_out = connection.execute(
                """
                SELECT COUNT(*) AS count FROM camp_movements m
                WHERE m.id = (SELECT MAX(m2.id) FROM camp_movements m2 WHERE m2.person_id = m.person_id)
                  AND m.direction = 'out'
                  AND m.person_id IN (SELECT id FROM camp_people WHERE session_id = ?)
                """,
                (resolved_session,),
            ).fetchone()
            dietary = connection.execute(
                """
                SELECT COUNT(*) AS records, COUNT(DISTINCT d.person_id) AS children
                FROM camp_dietary d JOIN camp_people p ON p.id = d.person_id
                WHERE p.session_id = ?
                """,
                (resolved_session,),
            ).fetchone()
            digest = connection.execute(
                """
                SELECT COUNT(*) AS total, SUM(CASE WHEN d.sent_at_ms IS NOT NULL THEN 1 ELSE 0 END) AS sent
                FROM camp_digest d JOIN camp_people p ON p.id = d.person_id
                WHERE p.session_id = ?
                """,
                (resolved_session,),
            ).fetchone()
            kiosks = connection.execute(
                """
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN k.revoked_at_ms IS NULL THEN 1 ELSE 0 END) AS active
                FROM camp_kiosks k JOIN camp_zones z ON z.id = k.zone_id
                WHERE z.session_id = ?
                """,
                (resolved_session,),
            ).fetchone()
            consents = connection.execute(
                """
                SELECT COUNT(*) AS records, SUM(CASE WHEN c.granted = 1 THEN 1 ELSE 0 END) AS granted
                FROM camp_consents c JOIN camp_people p ON p.id = c.person_id
                WHERE p.session_id = ?
                """,
                (resolved_session,),
            ).fetchone()
            audit_count = connection.execute(
                "SELECT COUNT(*) AS count FROM camp_audit WHERE created_at_ms >= ?",
                (int(session["starts_at_ms"]),),
            ).fetchone()
            return {
                "session": session,
                "generated_at_ms": _now_ms(),
                "people": {
                    "total": sum(by_role.values()),
                    "children": by_role.get("child", 0),
                    "staff": sum(count for role, count in by_role.items() if role in STAFF_ROLES),
                    "by_role": by_role,
                },
                "units": units,
                "attendance": {
                    "events": int(attendance["events"] or 0),
                    "open": int(attendance["open"] or 0),
                    "closed": int(attendance["closed"] or 0),
                    "marks": marks,
                },
                "requests": requests,
                "alerts": {
                    "total": int(alerts["total"] or 0),
                    "open": int(alerts["open"] or 0),
                    "drills": int(alerts["drills"] or 0),
                },
                "scans": {
                    "total": int(scan_row["total"] or 0),
                    "last_24h": int(scan_24h["count"] or 0),
                },
                "movements": {
                    "out": movements.get("out", 0),
                    "in": movements.get("in", 0),
                    "currently_out": int(currently_out["count"] or 0),
                },
                "dietary": {
                    "records": int(dietary["records"] or 0),
                    "children": int(dietary["children"] or 0),
                },
                "digests": {
                    "total": int(digest["total"] or 0),
                    "sent": int(digest["sent"] or 0),
                },
                "kiosks": {
                    "total": int(kiosks["total"] or 0),
                    "active": int(kiosks["active"] or 0),
                },
                "consents": {
                    "records": int(consents["records"] or 0),
                    "granted": int(consents["granted"] or 0),
                },
                "audit_events": int(audit_count["count"] or 0),
            }

    def report_csv(self, actor: Mapping[str, Any], *, session_id: int | None = None) -> str:
        import csv
        import io

        report = self.session_report(actor, session_id=session_id)
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(["section", "metric", "value"])
        for key in (
            "attendance",
            "requests",
            "alerts",
            "scans",
            "movements",
            "dietary",
            "digests",
            "kiosks",
            "consents",
        ):
            for name, value in report.get(key, {}).items():
                writer.writerow([key, name, value])
        for unit in report.get("units", []):
            writer.writerow(["unit", unit.get("name"), unit.get("child_count")])
        writer.writerow(["people", "total", report["people"]["total"]])
        writer.writerow(["people", "children", report["people"]["children"]])
        writer.writerow(["people", "staff", report["people"]["staff"]])
        writer.writerow(["session", "name", report["session"].get("name")])
        return "\ufeff" + buffer.getvalue()

    def report_html(self, actor: Mapping[str, Any], *, session_id: int | None = None) -> str:
        import html as html_module

        report = self.session_report(actor, session_id=session_id)

        def esc(value: Any) -> str:
            return html_module.escape(str(value))

        rows = "".join(
            "<tr><td>{}</td><td>{}</td><td>{}</td></tr>".format(
                esc(unit.get("name")),
                esc(unit.get("kind")),
                esc(unit.get("child_count")),
            )
            for unit in report.get("units", [])
        )
        metrics = [
            ("Children", report["people"]["children"]),
            ("Staff", report["people"]["staff"]),
            ("Attendance events", report["attendance"]["events"]),
            ("Attendance marks", sum(report["attendance"]["marks"].values())),
            ("Open requests", report["requests"].get("open", 0)),
            ("Alerts", report["alerts"]["total"]),
            ("Scans", report["scans"]["total"]),
            ("Currently out", report["movements"]["currently_out"]),
            ("Dietary records", report["dietary"]["records"]),
            ("Digests", report["digests"]["total"]),
            ("Kiosks active", report["kiosks"]["active"]),
        ]
        metric_rows = "".join(
            f"<tr><td>{esc(name)}</td><td>{esc(value)}</td></tr>" for name, value in metrics
        )
        return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Camp report - {esc(report['session'].get('name'))}</title>
<style>
body{{font-family:system-ui,sans-serif;margin:24px;color:#111}}
h1{{font-size:22px}} h2{{font-size:16px;margin-top:24px}}
table{{width:100%;border-collapse:collapse;margin-top:8px}}
th,td{{border:1px solid #999;padding:6px;text-align:left}}
th{{background:#eee}} @media print{{body{{margin:0}}}}
</style></head><body>
<h1>Camp report: {esc(report['session'].get('name'))}</h1>
<p>Generated: {esc(report['generated_at_ms'])}</p>
<h2>Units</h2>
<table><thead><tr><th>Unit</th><th>Kind</th><th>Children</th></tr></thead>
<tbody>{rows or '<tr><td colspan="3">No units</td></tr>'}</tbody></table>
<h2>Metrics</h2>
<table><tbody>{metric_rows}</tbody></table>
</body></html>"""

    def system_status(self) -> dict[str, Any]:
        now = _now_ms()
        with self._connect() as connection:
            db_ok = connection.execute("SELECT 1").fetchone() is not None
            quick = connection.execute("PRAGMA quick_check").fetchone()
            quick_check = str(quick[0]) if quick else "unknown"
            connection.execute("CREATE TEMP TABLE IF NOT EXISTS _camp_status_probe (value INTEGER)")
            connection.execute("INSERT INTO _camp_status_probe(value) VALUES (1)")
            write_ok = connection.execute("SELECT COUNT(*) FROM _camp_status_probe").fetchone()[0] > 0
            db_now = connection.execute("SELECT CAST(strftime('%s','now') AS INTEGER) * 1000").fetchone()[0]
            sessions = connection.execute(
                "SELECT COUNT(*) FROM camp_sessions WHERE status IN ('planned','active')"
            ).fetchone()[0]
            active = connection.execute(
                "SELECT COUNT(*) FROM camp_sessions WHERE status = 'active'"
            ).fetchone()[0]
            kiosk_rows = connection.execute(
                "SELECT last_seen_ms FROM camp_kiosks WHERE revoked_at_ms IS NULL"
            ).fetchall()
            last_audit = connection.execute("SELECT MAX(created_at_ms) FROM camp_audit").fetchone()[0]
        try:
            disk = shutil.disk_usage(self._db_path.parent)
            disk_free_mb = int(disk.free / (1024 * 1024))
        except OSError:
            disk_free_mb = 0
        stale_kiosks = sum(
            1
            for row in kiosk_rows
            if row["last_seen_ms"] is None or now - int(row["last_seen_ms"]) > 10 * 60_000
        )
        network_ssid = os.environ.get("CAMP_AP_SSID", "CAMP-CHAT")
        network_address = os.environ.get("CAMP_AP_ADDRESS", "192.168.50.1")
        portal_port = os.environ.get("CAMP_PORTAL_PORT", "18080")
        if not portal_port.isdigit():
            portal_port = "18080"
        network_mode = "nat" if os.environ.get("CAMP_AP_NAT_ENABLED") == "1" else "offline"
        network_open = os.environ.get("CAMP_AP_OPEN", "1") == "1"
        captive_enabled = os.environ.get("CAMP_CAPTIVE_PORTAL", "1") == "1"
        captive_port = os.environ.get("CAMP_CAPTIVE_PORTAL_PORT", "80")
        if not captive_port.isdigit():
            captive_port = "80"
        network = {
            "ssid": network_ssid,
            "address": network_address,
            "portal_url": f"http://{network_address}:{portal_port}/camp",
            "mode": network_mode,
            "internet": network_mode == "nat",
            "open": network_open,
            "security": "open" if network_open else "WPA2-PSK",
            "captive_portal": captive_enabled,
            "captive_url": f"http://{network_address}:{captive_port}/" if captive_enabled else None,
            "note": "Configured on the host by server/scripts/configure_camp_ap.sh; this block reflects CAMP_AP_* environment values.",
        }
        return {
            "status": "ok" if db_ok and write_ok and quick_check == "ok" and disk_free_mb > 100 else "degraded",
            "checks": {
                "db_read": bool(db_ok),
                "db_write": bool(write_ok),
                "db_quick_check": quick_check,
                "disk_free_mb": disk_free_mb,
                "clock_skew_ms": abs(int(db_now or 0) - now),
            },
            "sessions": {"open": int(sessions or 0), "active": int(active or 0)},
            "kiosks": {"active": len(kiosk_rows), "stale": stale_kiosks},
            "network": network,
            "last_audit_ms": int(last_audit) if last_audit else None,
            "backup_hint": "Create a SQLite snapshot before the session and keep it off-device.",
            "checked_at_ms": now,
        }
