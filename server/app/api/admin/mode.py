from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.models import AccessMode, ClientKind, UserRole
from app.services.auth import AuthError, AuthService
from app.services.mode import ModeError, ModeService


router = APIRouter(prefix="/admin/mode", tags=["admin-mode"])

_REQUIRED_HOLD_SECONDS = 5


class AdminSetModeRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    access_mode: AccessMode
    hold_seconds: int = Field(default=_REQUIRED_HOLD_SECONDS, ge=1, le=30)


def _template_path() -> Path:
    return Path(__file__).resolve().parents[2] / "templates" / "admin" / "mode" / "index.html"


def _auth_service(request: Request) -> AuthService:
    data_layer = request.app.state.data_layer
    return AuthService(db_path=data_layer.database_path)


def _mode_service(request: Request) -> ModeService:
    data_layer = request.app.state.data_layer
    return ModeService(db_path=data_layer.database_path)


def _resolve_admin_user_id(request: Request, session_token: str) -> int:
    service = _auth_service(request)
    try:
        session = service.get_session(session_token, client_kind=ClientKind.WEB)
    except AuthError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    if session.user.role != UserRole.ADMIN or not session.user.can_access_admin_features():
        raise HTTPException(
            status_code=403,
            detail={"code": "admin_only", "message": "Admin role is required"},
        )

    if session.user.user_id is None:
        raise HTTPException(
            status_code=500,
            detail={"code": "invalid_user", "message": "Admin user id is missing"},
        )
    return session.user.user_id


def _safe_sequence() -> list[str]:
    return [
        "hold_toggle_button",
        "stop_new_sessions",
        "flush_db_writes",
        "drain_realtime_buffers",
        "apply_mode_change",
    ]


@router.get("/panel", response_class=HTMLResponse)
async def admin_mode_panel() -> HTMLResponse:
    template = _template_path()
    html = template.read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@router.get("/state")
async def get_admin_mode_state(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, object]:
    _resolve_admin_user_id(request, session_token)
    service = _mode_service(request)
    access_mode = service.get_mode()
    return {
        "status": "ok",
        "access_mode": access_mode.value,
        "required_hold_seconds": _REQUIRED_HOLD_SECONDS,
        "safe_sequence": _safe_sequence(),
    }


@router.post("/set")
async def set_admin_mode(
    request: Request,
    payload: AdminSetModeRequest,
) -> dict[str, object]:
    admin_user_id = _resolve_admin_user_id(request, payload.session_token)

    if payload.hold_seconds < _REQUIRED_HOLD_SECONDS:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "hold_too_short",
                "message": f"hold_seconds must be >= {_REQUIRED_HOLD_SECONDS}",
            },
        )

    service = _mode_service(request)
    try:
        updated_mode = service.set_mode(payload.access_mode)
    except ModeError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    # When switching to "closed", revoke all sessions except the current admin
    if payload.access_mode.value == "closed":
        try:
            auth = _auth_service(request)
            auth.revoke_all_sessions_except(admin_user_id)
        except Exception:
            pass

    return {
        "status": "ok",
        "access_mode": updated_mode.value,
        "updated_by_user_id": admin_user_id,
        "hold_seconds": payload.hold_seconds,
        "required_hold_seconds": _REQUIRED_HOLD_SECONDS,
        "safe_sequence": _safe_sequence(),
    }
