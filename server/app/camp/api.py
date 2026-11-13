"""HTTP surface for Camp Edition.

All routes are additive under ``/camp``.  Authentication reuses the shared
web session token; camp membership is resolved from the per-session
``camp_people`` table.
"""

from __future__ import annotations

import html
from pathlib import Path
from time import time
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field

from app.models import ClientKind
from app.services.auth import AuthError, AuthService
from app.camp.service import CampError, CampService


router = APIRouter(prefix="/camp", tags=["camp"])


class SessionCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    starts_at_ms: int | None = None
    ends_at_ms: int | None = None
    retention_days: int = Field(default=30, ge=1, le=3650)
    status: str = Field(default="planned", pattern="^(planned|active|closed|archived)$")


class UnitCreateRequest(BaseModel):
    session_id: int | None = None
    name: str = Field(min_length=1, max_length=120)
    kind: str = Field(default="squad", pattern="^(squad|staff|other)$")


class PersonCreateRequest(BaseModel):
    session_id: int | None = None
    unit_id: int | None = None
    user_id: int | None = None
    role: str = Field(default="child", max_length=20)
    age_band: str | None = Field(default=None, max_length=20)
    display_name: str = Field(min_length=1, max_length=200)
    birth_date: str | None = Field(default=None, max_length=20)
    login_name: str | None = Field(default=None, max_length=128)
    room: str | None = Field(default=None, max_length=64)
    badge_code: str | None = Field(default=None, max_length=128)


class ImportRequest(BaseModel):
    session_id: int | None = None
    rows: list[dict[str, Any]] = Field(min_length=1, max_length=500)


class TransferRequest(BaseModel):
    unit_id: int


class MergeRequest(BaseModel):
    source_id: int
    target_id: int


class RequestCreateRequest(BaseModel):
    session_id: int | None = None
    kind: str = Field(default="call_counselor", pattern="^(call_counselor|parent_question|help)$")
    note: str | None = Field(default=None, max_length=2000)


class RequestCloseRequest(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


class SettingsUpdateRequest(BaseModel):
    session_id: int | None = None
    quiet_start_minutes: int | None = Field(default=None, ge=0, le=1439)
    quiet_end_minutes: int | None = Field(default=None, ge=0, le=1439)
    allow_child_dm: bool | None = None
    allow_child_media: bool | None = None
    require_two_adults_for_dm: bool | None = None
    photo_watermark: str | None = Field(default=None, max_length=200)


class PolicyCheckRequest(BaseModel):
    kind: str = Field(pattern="^(direct_message|media|forward|post|group)$")
    target_person_id: int | None = None
    minute_of_day: int | None = Field(default=None, ge=0, le=1439)
    has_consent: bool = False


class AttendanceCreateRequest(BaseModel):
    session_id: int | None = None
    unit_id: int
    kind: str = Field(default="roll_call", pattern="^(roll_call|lights_out|custom)$")
    deadline_at_ms: int | None = None


class AttendanceMarkRequest(BaseModel):
    person_id: int
    status: str = Field(pattern="^(present|absent|sick|medic|parent|left)$")
    note: str | None = Field(default=None, max_length=1000)


class AttendanceCloseRequest(BaseModel):
    force: bool = False
    note: str | None = Field(default=None, max_length=1000)


class AlertStartRequest(BaseModel):
    session_id: int | None = None
    kind: str = Field(min_length=1, max_length=64)
    drill: bool = False
    zone_id: int | None = None
    note: str | None = Field(default=None, max_length=2000)


class AlertAckRequest(BaseModel):
    step_index: int = Field(default=0, ge=0, le=100)
    note: str | None = Field(default=None, max_length=1000)


class AlertCloseRequest(BaseModel):
    note: str | None = Field(default=None, max_length=2000)
    after_action: str | None = Field(default=None, max_length=4000)


class ZoneCreateRequest(BaseModel):
    session_id: int | None = None
    name: str = Field(min_length=1, max_length=120)
    kind: str = Field(default="checkpoint", pattern="^(checkpoint|building|gate|medical|other)$")
    parent_id: int | None = None


class ScanCreateRequest(BaseModel):
    zone_id: int
    person_id: int | None = None
    badge_code: str | None = Field(default=None, max_length=128)
    source: str = Field(default="staff", pattern="^(staff|kiosk|import)$")
    device_id: str | None = Field(default=None, max_length=128)
    scanned_at_ms: int | None = None


class DutyShiftCreateRequest(BaseModel):
    session_id: int | None = None
    user_id: int
    role: str = Field(default="counselor", max_length=20)
    starts_at_ms: int
    ends_at_ms: int
    note: str | None = Field(default=None, max_length=1000)


class HandoverCreateRequest(BaseModel):
    session_id: int | None = None
    to_user_id: int
    notes: str = Field(min_length=1, max_length=4000)
    open_items: list[Any] = Field(default_factory=list, max_length=100)


class PickupAuthCreateRequest(BaseModel):
    person_id: int
    adult_name: str = Field(min_length=1, max_length=200)
    relationship: str | None = Field(default=None, max_length=120)
    adult_document: str | None = Field(default=None, max_length=200)
    restrictions: str | None = Field(default=None, max_length=1000)


class MovementCreateRequest(BaseModel):
    person_id: int
    direction: str = Field(pattern="^(out|in)$")
    qr_code: str | None = Field(default=None, max_length=256)
    zone_id: int | None = None
    override_reason: str | None = Field(default=None, max_length=1000)
    note: str | None = Field(default=None, max_length=1000)


class DietarySetRequest(BaseModel):
    person_id: int
    restriction: str = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=1000)
    valid_to_ms: int | None = None


class GuardianLinkRequest(BaseModel):
    person_id: int
    parent_person_id: int
    relationship: str | None = Field(default=None, max_length=120)


class DigestUpsertRequest(BaseModel):
    person_id: int
    date: str = Field(min_length=10, max_length=10)
    text: str = Field(min_length=1, max_length=4000)
    photo_id: int | None = None


class DigestSentRequest(BaseModel):
    person_id: int
    date: str = Field(min_length=10, max_length=10)


class ConsentSetRequest(BaseModel):
    person_id: int
    kind: str = Field(pattern="^(internal_chat|parent_digest|promo|none)$")
    granted: bool
    note: str | None = Field(default=None, max_length=1000)


class KioskCreateRequest(BaseModel):
    session_id: int | None = None
    device_id: str = Field(min_length=1, max_length=128)
    zone_id: int
    scopes: str = Field(default="scan", max_length=64)


class KioskScanRequest(BaseModel):
    person_id: int | None = None
    badge_code: str | None = Field(default=None, max_length=128)
    scanned_at_ms: int | None = None


class SyncRequest(BaseModel):
    device_id: str | None = Field(default=None, max_length=128)
    operations: list[dict[str, Any]] = Field(min_length=1, max_length=100)


def _service(request: Request) -> CampService:
    return CampService(request.app.state.data_layer.database_path)


def _auth(request: Request, session_token: str) -> dict[str, Any]:
    auth_service = AuthService(db_path=request.app.state.data_layer.database_path)
    try:
        result = auth_service.get_session(session_token, client_kind=ClientKind.WEB)
    except AuthError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    if result.user.user_id is None:
        raise HTTPException(
            status_code=500,
            detail={"code": "invalid_user", "message": "Authenticated user id is missing"},
        )
    actor = _service(request).get_actor_for_user(result.user.user_id)
    if actor is None:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "camp_access_required",
                "message": "This account has no camp profile. Ask the director to import it.",
            },
        )
    return actor


def _fail(exc: CampError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.as_detail())


@router.get("", response_class=HTMLResponse, include_in_schema=False)
@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def camp_page() -> HTMLResponse:
    path = Path(__file__).resolve().parents[1] / "static" / "camp" / "camp.html"
    if not path.exists():
        return HTMLResponse("<h1>Camp Edition</h1><p>UI is being installed.</p>")
    return HTMLResponse(content=path.read_text(encoding="utf-8"))


@router.get("/status")
def camp_status(request: Request) -> dict[str, Any]:
    try:
        payload = _service(request).system_status()
    except CampError as exc:
        raise _fail(exc) from exc
    payload["status"] = payload.get("status", "ok")
    payload["service"] = "local-chat-server"
    payload["edition"] = request.app.state.settings.edition
    return payload


@router.get("/api/me")
def me(request: Request, session_token: str = Query(..., min_length=8, max_length=512)) -> dict[str, Any]:
    actor = _auth(request, session_token)
    service = _service(request)
    try:
        sessions = service.list_sessions()
        current = None
        if actor.get("session_id"):
            current = service.get_session(int(actor["session_id"]))
        settings = service.get_settings(actor) if current else None
        units = service.list_units(actor) if current else []
    except CampError as exc:
        raise _fail(exc) from exc
    return {
        "status": "ok",
        "actor": actor,
        "sessions": sessions,
        "current_session": current,
        "settings": settings,
        "units": units,
    }


@router.get("/api/sessions")
def list_sessions(request: Request, session_token: str = Query(..., min_length=8, max_length=512)) -> dict[str, Any]:
    _auth(request, session_token)
    try:
        return {"status": "ok", "items": _service(request).list_sessions()}
    except CampError as exc:
        raise _fail(exc) from exc


@router.post("/api/sessions")
def create_session(
    request: Request,
    payload: SessionCreateRequest,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        item = _service(request).create_session(
            actor,
            name=payload.name,
            starts_at_ms=payload.starts_at_ms,
            ends_at_ms=payload.ends_at_ms,
            retention_days=payload.retention_days,
            status=payload.status,
        )
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "item": item}


@router.get("/api/units")
def list_units(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    session_id: int | None = None,
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        return {"status": "ok", "items": _service(request).list_units(actor, session_id=session_id)}
    except CampError as exc:
        raise _fail(exc) from exc


@router.post("/api/units")
def create_unit(
    request: Request,
    payload: UnitCreateRequest,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        item = _service(request).create_unit(
            actor, session_id=payload.session_id, name=payload.name, kind=payload.kind
        )
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "item": item}


@router.get("/api/people")
def list_people(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    session_id: int | None = None,
    unit_id: int | None = None,
    role: str | None = Query(default=None, max_length=20),
    q: str = Query(default="", max_length=128),
    limit: int = Query(default=200, ge=1, le=500),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        items = _service(request).list_people(
            actor,
            session_id=session_id,
            unit_id=unit_id,
            role=role,
            q=q,
            limit=limit,
        )
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "count": len(items), "items": items}


@router.get("/api/staff")
def list_staff(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    session_id: int | None = None,
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        items = _service(request).list_staff(actor, session_id=session_id)
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "count": len(items), "items": items}


@router.get("/api/people/{person_id}")
def get_person(
    request: Request,
    person_id: int,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        item = _service(request).get_person(actor, person_id)
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "item": item}


@router.post("/api/people")
def create_person(
    request: Request,
    payload: PersonCreateRequest,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        item = _service(request).create_person(
            actor,
            session_id=payload.session_id,
            unit_id=payload.unit_id,
            user_id=payload.user_id,
            role=payload.role,
            age_band=payload.age_band,
            display_name=payload.display_name,
            birth_date=payload.birth_date,
            login_name=payload.login_name,
            room=payload.room,
            badge_code=payload.badge_code,
        )
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "item": item}


@router.post("/api/import/preview")
def import_preview(
    request: Request,
    payload: ImportRequest,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        session_id = payload.session_id or actor.get("session_id")
        if session_id is None:
            raise CampError("session_required", "session_id is required")
        result = _service(request).import_preview(payload.rows, session_id=int(session_id))
    except CampError as exc:
        raise _fail(exc) from exc
    return result


@router.post("/api/import/commit")
def import_commit(
    request: Request,
    payload: ImportRequest,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        result = _service(request).import_commit(
            actor, session_id=payload.session_id, rows=payload.rows
        )
    except CampError as exc:
        raise _fail(exc) from exc
    return result


@router.post("/api/import/{batch_id}/undo")
def undo_import(
    request: Request,
    batch_id: int,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        result = _service(request).undo_import(actor, batch_id=batch_id)
    except CampError as exc:
        raise _fail(exc) from exc
    return result


@router.post("/api/people/{person_id}/transfer")
def transfer_person(
    request: Request,
    person_id: int,
    payload: TransferRequest,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        item = _service(request).transfer_person(actor, person_id=person_id, unit_id=payload.unit_id)
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "item": item}


@router.post("/api/people/merge")
def merge_people(
    request: Request,
    payload: MergeRequest,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        item = _service(request).merge_people(actor, source_id=payload.source_id, target_id=payload.target_id)
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "item": item}


@router.get("/api/requests")
def list_requests(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    session_id: int | None = None,
    status: str | None = Query(default=None, max_length=20),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        items = _service(request).list_requests(
            actor, session_id=session_id, status=status, limit=limit
        )
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "count": len(items), "items": items}


@router.post("/api/requests")
def create_request(
    request: Request,
    payload: RequestCreateRequest,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        item = _service(request).create_request(
            actor, session_id=payload.session_id, kind=payload.kind, note=payload.note
        )
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "item": item}


@router.post("/api/requests/{request_id}/claim")
def claim_request(
    request: Request,
    request_id: int,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        item = _service(request).claim_request(actor, request_id)
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "item": item}


@router.post("/api/requests/{request_id}/close")
def close_request(
    request: Request,
    request_id: int,
    payload: RequestCloseRequest,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        item = _service(request).close_request(actor, request_id, note=payload.note)
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "item": item}


@router.get("/api/settings")
def get_settings(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    session_id: int | None = None,
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        return {"status": "ok", "item": _service(request).get_settings(actor, session_id=session_id)}
    except CampError as exc:
        raise _fail(exc) from exc


@router.patch("/api/settings")
def update_settings(
    request: Request,
    payload: SettingsUpdateRequest,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        item = _service(request).update_settings(
            actor,
            session_id=payload.session_id,
            quiet_start_minutes=payload.quiet_start_minutes,
            quiet_end_minutes=payload.quiet_end_minutes,
            allow_child_dm=payload.allow_child_dm,
            allow_child_media=payload.allow_child_media,
            require_two_adults_for_dm=payload.require_two_adults_for_dm,
            photo_watermark=payload.photo_watermark,
        )
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "item": item}


@router.post("/api/policy/check")
def policy_check(
    request: Request,
    payload: PolicyCheckRequest,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        result = _service(request).policy_check(
            actor,
            kind=payload.kind,
            target_person_id=payload.target_person_id,
            minute_of_day=payload.minute_of_day,
            has_consent=payload.has_consent,
        )
    except CampError as exc:
        raise _fail(exc) from exc
    return result


@router.get("/api/audit")
def list_audit(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        return {"status": "ok", "items": _service(request).list_audit(actor, limit=limit)}
    except CampError as exc:
        raise _fail(exc) from exc

# -- cycle 2: attendance, alerts, zones, duty, pickup, dietary, digest --


@router.post("/api/attendance/events")
def create_attendance_event(
    request: Request,
    payload: AttendanceCreateRequest,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        item = _service(request).create_attendance_event(
            actor,
            session_id=payload.session_id,
            unit_id=payload.unit_id,
            kind=payload.kind,
            deadline_at_ms=payload.deadline_at_ms,
        )
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "item": item}


@router.get("/api/attendance/events")
def list_attendance_events(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    session_id: int | None = None,
    unit_id: int | None = None,
    status: str | None = Query(default=None, max_length=20),
    limit: int = Query(default=100, ge=1, le=300),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        items = _service(request).list_attendance_events(
            actor,
            session_id=session_id,
            unit_id=unit_id,
            status=status,
            limit=limit,
        )
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "count": len(items), "items": items}


@router.get("/api/attendance/events/{event_id}")
def get_attendance_event(
    request: Request,
    event_id: int,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        return {"status": "ok", "item": _service(request).get_attendance_event(actor, event_id=event_id)}
    except CampError as exc:
        raise _fail(exc) from exc


@router.post("/api/attendance/events/{event_id}/marks")
def mark_attendance(
    request: Request,
    event_id: int,
    payload: AttendanceMarkRequest,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        item = _service(request).mark_attendance(
            actor,
            event_id=event_id,
            person_id=payload.person_id,
            status=payload.status,
            note=payload.note,
        )
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "item": item}


@router.post("/api/attendance/events/{event_id}/all-present")
def mark_all_present(
    request: Request,
    event_id: int,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        item = _service(request).mark_all_present(actor, event_id=event_id)
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "item": item}


@router.post("/api/attendance/events/{event_id}/close")
def close_attendance(
    request: Request,
    event_id: int,
    payload: AttendanceCloseRequest,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        item = _service(request).close_attendance(
            actor, event_id=event_id, force=payload.force, note=payload.note
        )
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "item": item}


@router.get("/api/attendance/overdue")
def attendance_overdue(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    session_id: int | None = None,
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        items = _service(request).attendance_overdue(actor, session_id=session_id)
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "count": len(items), "items": items}


@router.get("/api/alert-playbooks")
def list_alert_playbooks(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        return {"status": "ok", "items": _service(request).list_alert_playbooks(actor)}
    except CampError as exc:
        raise _fail(exc) from exc


@router.get("/api/alerts")
def list_alerts(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    session_id: int | None = None,
    status: str | None = Query(default=None, max_length=20),
    kind: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=100, ge=1, le=300),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        items = _service(request).list_alerts(
            actor, session_id=session_id, status=status, kind=kind, limit=limit
        )
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "count": len(items), "items": items}


@router.post("/api/alerts")
def start_alert(
    request: Request,
    payload: AlertStartRequest,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        item = _service(request).start_alert(
            actor,
            session_id=payload.session_id,
            kind=payload.kind,
            drill=payload.drill,
            zone_id=payload.zone_id,
            note=payload.note,
        )
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "item": item}


@router.get("/api/alerts/{alert_id}")
def get_alert(
    request: Request,
    alert_id: int,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        return {"status": "ok", "item": _service(request).get_alert(actor, alert_id=alert_id)}
    except CampError as exc:
        raise _fail(exc) from exc


@router.post("/api/alerts/{alert_id}/ack")
def acknowledge_alert(
    request: Request,
    alert_id: int,
    payload: AlertAckRequest,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        item = _service(request).acknowledge_alert(
            actor, alert_id=alert_id, step_index=payload.step_index, note=payload.note
        )
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "item": item}


@router.post("/api/alerts/{alert_id}/close")
def close_alert(
    request: Request,
    alert_id: int,
    payload: AlertCloseRequest,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        item = _service(request).close_alert(
            actor, alert_id=alert_id, note=payload.note, after_action=payload.after_action
        )
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "item": item}


@router.post("/api/zones")
def create_zone(
    request: Request,
    payload: ZoneCreateRequest,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        item = _service(request).create_zone(
            actor,
            session_id=payload.session_id,
            name=payload.name,
            kind=payload.kind,
            parent_id=payload.parent_id,
        )
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "item": item}


@router.get("/api/zones")
def list_zones(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    session_id: int | None = None,
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        return {"status": "ok", "items": _service(request).list_zones(actor, session_id=session_id)}
    except CampError as exc:
        raise _fail(exc) from exc


@router.get("/api/zones/monitor")
def zone_monitor(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    session_id: int | None = None,
    minutes: int = Query(default=120, ge=1, le=1440),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        items = _service(request).zone_monitor(actor, session_id=session_id, minutes=minutes)
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "items": items}


@router.post("/api/scans")
def scan_person(
    request: Request,
    payload: ScanCreateRequest,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        item = _service(request).scan_person(
            actor,
            zone_id=payload.zone_id,
            person_id=payload.person_id,
            badge_code=payload.badge_code,
            source=payload.source,
            device_id=payload.device_id,
            scanned_at_ms=payload.scanned_at_ms,
        )
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "item": item}


@router.get("/api/zones/{zone_id}/scans")
def list_zone_scans(
    request: Request,
    zone_id: int,
    session_token: str = Query(..., min_length=8, max_length=512),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        items = _service(request).list_zone_scans(actor, zone_id=zone_id, limit=limit)
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "count": len(items), "items": items}


@router.get("/api/people/{person_id}/last-seen")
def person_last_seen(
    request: Request,
    person_id: int,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        return {"status": "ok", "item": _service(request).last_seen(actor, person_id=person_id)}
    except CampError as exc:
        raise _fail(exc) from exc


@router.post("/api/duty")
def create_duty_shift(
    request: Request,
    payload: DutyShiftCreateRequest,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        item = _service(request).create_duty_shift(
            actor,
            session_id=payload.session_id,
            user_id=payload.user_id,
            role=payload.role,
            starts_at_ms=payload.starts_at_ms,
            ends_at_ms=payload.ends_at_ms,
            note=payload.note,
        )
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "item": item}


@router.get("/api/duty")
def list_duty_shifts(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    session_id: int | None = None,
    from_ms: int | None = None,
    to_ms: int | None = None,
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        items = _service(request).list_duty_shifts(
            actor, session_id=session_id, from_ms=from_ms, to_ms=to_ms
        )
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "items": items}


@router.post("/api/handovers")
def create_handover(
    request: Request,
    payload: HandoverCreateRequest,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        item = _service(request).create_handover(
            actor,
            session_id=payload.session_id,
            to_user_id=payload.to_user_id,
            notes=payload.notes,
            open_items=payload.open_items,
        )
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "item": item}


@router.get("/api/handovers")
def list_handovers(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    session_id: int | None = None,
    limit: int = Query(default=100, ge=1, le=300),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        items = _service(request).list_handovers(actor, session_id=session_id, limit=limit)
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "items": items}


@router.post("/api/handovers/{handover_id}/ack")
def acknowledge_handover(
    request: Request,
    handover_id: int,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        item = _service(request).acknowledge_handover(actor, handover_id=handover_id)
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "item": item}


@router.post("/api/pickup")
def create_pickup_auth(
    request: Request,
    payload: PickupAuthCreateRequest,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        item = _service(request).create_pickup_auth(
            actor,
            person_id=payload.person_id,
            adult_name=payload.adult_name,
            relationship=payload.relationship,
            adult_document=payload.adult_document,
            restrictions=payload.restrictions,
        )
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "item": item}


@router.get("/api/pickup")
def list_pickup_auth(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    person_id: int | None = None,
    include_inactive: bool = False,
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        items = _service(request).list_pickup_auth(
            actor, person_id=person_id, include_inactive=include_inactive
        )
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "items": items}


@router.get("/api/pickup/verify")
def verify_pickup(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    qr_code: str = Query(..., min_length=8, max_length=256),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        return {"status": "ok", "item": _service(request).verify_pickup(actor, qr_code=qr_code)}
    except CampError as exc:
        raise _fail(exc) from exc


@router.post("/api/movements")
def record_movement(
    request: Request,
    payload: MovementCreateRequest,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        item = _service(request).record_movement(
            actor,
            person_id=payload.person_id,
            direction=payload.direction,
            qr_code=payload.qr_code,
            zone_id=payload.zone_id,
            override_reason=payload.override_reason,
            note=payload.note,
        )
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "item": item}


@router.get("/api/movements")
def gate_log(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    session_id: int | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        items = _service(request).gate_log(actor, session_id=session_id, limit=limit)
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "count": len(items), "items": items}


@router.post("/api/dietary")
def set_dietary(
    request: Request,
    payload: DietarySetRequest,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        item = _service(request).set_dietary(
            actor,
            person_id=payload.person_id,
            restriction=payload.restriction,
            note=payload.note,
            valid_to_ms=payload.valid_to_ms,
        )
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "item": item}


@router.get("/api/dietary")
def list_dietary(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    session_id: int | None = None,
    unit_id: int | None = None,
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        items = _service(request).list_dietary(actor, session_id=session_id, unit_id=unit_id)
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "count": len(items), "items": items}


@router.delete("/api/dietary")
def remove_dietary(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    person_id: int = Query(...),
    restriction: str = Query(..., min_length=1, max_length=200),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        return _service(request).remove_dietary(actor, person_id=person_id, restriction=restriction)
    except CampError as exc:
        raise _fail(exc) from exc


@router.get("/api/dietary/print", response_class=HTMLResponse)
def dietary_print(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    session_id: int | None = None,
    unit_id: int | None = None,
) -> HTMLResponse:
    actor = _auth(request, session_token)
    try:
        items = _service(request).list_dietary(actor, session_id=session_id, unit_id=unit_id)
    except CampError as exc:
        raise _fail(exc) from exc
    rows = "".join(
        "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            html.escape(str(item.get("unit_name") or "")),
            html.escape(str(item.get("display_name") or "")),
            html.escape(str(item.get("room") or "")),
            html.escape(str(item.get("restriction") or "")),
            html.escape(str(item.get("note") or "")),
        )
        for item in items
    )
    document = f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<title>Dietary list</title>
<style>
body{{font-family:system-ui,sans-serif;margin:24px;color:#111}}
h1{{font-size:22px}} table{{width:100%;border-collapse:collapse}}
th,td{{border:1px solid #999;padding:6px;text-align:left;vertical-align:top}}
th{{background:#eee}} @media print{{body{{margin:0}}}}
</style></head><body>
<h1>Dietary list</h1>
<table><thead><tr><th>Unit</th><th>Child</th><th>Room</th><th>Restriction</th><th>Note</th></tr></thead>
<tbody>{rows or '<tr><td colspan="5">No dietary records</td></tr>'}</tbody></table>
</body></html>"""
    return HTMLResponse(document)


@router.post("/api/guardians")
def link_guardian(
    request: Request,
    payload: GuardianLinkRequest,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        item = _service(request).link_guardian(
            actor,
            person_id=payload.person_id,
            parent_person_id=payload.parent_person_id,
            relationship=payload.relationship,
        )
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "item": item}


@router.get("/api/guardians")
def list_guardians(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    person_id: int | None = None,
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        return {"status": "ok", "items": _service(request).list_guardians(actor, person_id=person_id)}
    except CampError as exc:
        raise _fail(exc) from exc


@router.post("/api/digests")
def upsert_digest(
    request: Request,
    payload: DigestUpsertRequest,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        item = _service(request).upsert_digest(
            actor,
            person_id=payload.person_id,
            date=payload.date,
            text=payload.text,
            photo_id=payload.photo_id,
        )
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "item": item}


@router.get("/api/digests")
def list_digests(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    session_id: int | None = None,
    person_id: int | None = None,
    date: str | None = Query(default=None, max_length=10),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        items = _service(request).list_digests(
            actor, session_id=session_id, person_id=person_id, date=date
        )
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "items": items}


@router.post("/api/digests/sent")
def mark_digest_sent(
    request: Request,
    payload: DigestSentRequest,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        item = _service(request).mark_digest_sent(
            actor, person_id=payload.person_id, date=payload.date
        )
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "item": item}


@router.post("/api/kiosks")
def create_kiosk(
    request: Request,
    payload: KioskCreateRequest,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        item = _service(request).create_kiosk(
            actor,
            session_id=payload.session_id,
            device_id=payload.device_id,
            zone_id=payload.zone_id,
            scopes=payload.scopes,
        )
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", **item}


@router.get("/api/kiosks")
def list_kiosks(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    session_id: int | None = None,
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        items = _service(request).list_kiosks(actor, session_id=session_id)
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "items": items}


@router.post("/api/kiosks/{kiosk_id}/revoke")
def revoke_kiosk(
    request: Request,
    kiosk_id: int,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        item = _service(request).revoke_kiosk(actor, kiosk_id=kiosk_id)
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "item": item}


@router.post("/api/kiosk/scan")
def kiosk_scan(
    request: Request,
    payload: KioskScanRequest,
    kiosk_token: str = Query(..., min_length=8, max_length=256),
) -> dict[str, Any]:
    try:
        item = _service(request).kiosk_scan(
            kiosk_token=kiosk_token,
            person_id=payload.person_id,
            badge_code=payload.badge_code,
            scanned_at_ms=payload.scanned_at_ms,
        )
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", **item}


@router.post("/api/sync")
def sync_offline(
    request: Request,
    payload: SyncRequest,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        results = _service(request).sync_offline(
            actor, device_id=payload.device_id, operations=payload.operations
        )
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "server_time_ms": int(time() * 1000), "results": results}


@router.post("/api/consents")
def set_consent(
    request: Request,
    payload: ConsentSetRequest,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        item = _service(request).set_consent(
            actor,
            person_id=payload.person_id,
            kind=payload.kind,
            granted=payload.granted,
            note=payload.note,
        )
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "item": item}


@router.get("/api/consents/matrix")
def consent_matrix(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    session_id: int | None = None,
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        items = _service(request).consent_matrix(actor, session_id=session_id)
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "items": items}


@router.get("/api/consents")
def get_consents(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    person_id: int = Query(...),
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        item = _service(request).get_consents(actor, person_id=person_id)
    except CampError as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "item": item}


@router.get("/api/report")
def session_report(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    session_id: int | None = None,
) -> dict[str, Any]:
    actor = _auth(request, session_token)
    try:
        return {"status": "ok", "item": _service(request).session_report(actor, session_id=session_id)}
    except CampError as exc:
        raise _fail(exc) from exc


@router.get("/api/report.csv", response_class=PlainTextResponse)
def session_report_csv(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    session_id: int | None = None,
) -> PlainTextResponse:
    actor = _auth(request, session_token)
    try:
        body = _service(request).report_csv(actor, session_id=session_id)
    except CampError as exc:
        raise _fail(exc) from exc
    return PlainTextResponse(
        body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="camp-report.csv"'},
    )


@router.get("/api/report.html", response_class=HTMLResponse)
def session_report_html(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    session_id: int | None = None,
) -> HTMLResponse:
    actor = _auth(request, session_token)
    try:
        body = _service(request).report_html(actor, session_id=session_id)
    except CampError as exc:
        raise _fail(exc) from exc
    return HTMLResponse(body)
