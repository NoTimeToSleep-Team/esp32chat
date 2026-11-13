"""Camp Edition domain service.

The module is additive: all state lives in ``camp_*`` tables.  The shared
chat/account domain remains untouched and available for normal use.
"""

from __future__ import annotations

import json
import secrets
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
        self._session(connection, int(candidate))
        return int(candidate)

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
