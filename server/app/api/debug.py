from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.models import ClientKind, UserRole
from app.services.auth import AuthError, AuthService
from app.services.debug_log import DebugLogService

router = APIRouter(prefix="/debug", tags=["debug"])

_STAGES = {"client", "server", "toast"}


class ClientEventRequest(BaseModel):
    trace_id: str = Field(default="", max_length=64)
    action: str = Field(default="", max_length=512)
    method: str = Field(default="", max_length=16)
    stage: str = Field(default="client", max_length=16)
    ok: bool | None = None
    status: int | None = Field(default=None, ge=0, le=599)
    stages_done: int = Field(default=0, ge=0, le=3)
    error: str | None = Field(default=None, max_length=1000)
    details: str | None = Field(default=None, max_length=2000)
    t1_ms: int | None = None
    t2_ms: int | None = None
    t3_ms: int | None = None
    session_token: str | None = Field(default=None, max_length=512)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",", 1)[0].strip()
        if first:
            return first
    client = request.client
    return client.host if client and client.host else "unknown"


@router.post("/api/client-event")
async def client_event(request: Request, payload: ClientEventRequest) -> dict[str, object]:
    user_login = None
    if payload.session_token:
        try:
            session = AuthService(db_path=request.app.state.data_layer.database_path).get_session(
                payload.session_token,
                client_kind=ClientKind.WEB,
            )
            user_login = session.user.login
        except AuthError:
            user_login = None
    stage = payload.stage if payload.stage in _STAGES else "client"
    DebugLogService(db_path=request.app.state.data_layer.database_path).log(
        stage=stage,
        trace_id=(payload.trace_id or "").strip() or None,
        action=(payload.action or "").strip() or None,
        method=(payload.method or "").strip() or None,
        status=payload.status,
        ok=payload.ok,
        stages_done=payload.stages_done or None,
        error=(payload.error or "").strip() or None,
        details=(payload.details or "").strip() or None,
        user_login=user_login,
        ip=_client_ip(request),
        t1_ms=payload.t1_ms,
        t2_ms=payload.t2_ms,
        t3_ms=payload.t3_ms,
    )
    return {"status": "ok"}


def _require_admin(request: Request, session_token: str) -> None:
    try:
        session = AuthService(db_path=request.app.state.data_layer.database_path).get_session(
            session_token,
            client_kind=ClientKind.WEB,
        )
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    if session.user.role not in {UserRole.ADMIN, UserRole.MODERATOR}:
        raise HTTPException(status_code=403, detail={"code": "forbidden", "message": "Admin or moderator required"})


@router.get("/api/events")
async def list_events(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    limit: int = Query(default=200, ge=1, le=1000),
    trace_id: str | None = Query(default=None, max_length=64),
) -> dict[str, object]:
    _require_admin(request, session_token)
    events = DebugLogService(db_path=request.app.state.data_layer.database_path).list_events(
        limit=limit,
        trace_id=(trace_id or "").strip() or None,
    )
    return {"status": "ok", "count": len(events), "items": events}
