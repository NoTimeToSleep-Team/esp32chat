"""HTTP surface for Camp Edition.

All routes are additive under ``/camp``.  Authentication reuses the shared
web session token; camp membership is resolved from the per-session
``camp_people`` table.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
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
