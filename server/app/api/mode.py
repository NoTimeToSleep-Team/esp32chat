from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from app.models import AccessMode, ClientKind, UserRole
from app.services.auth import AuthError, AuthService
from app.services.mode import ModeError, ModeService


router = APIRouter(prefix="/mode", tags=["mode"])


class UpdateModeRequest(BaseModel):
    access_mode: AccessMode


def _auth_service(request: Request) -> AuthService:
    data_layer = request.app.state.data_layer
    return AuthService(db_path=data_layer.database_path)


def _mode_service(request: Request) -> ModeService:
    data_layer = request.app.state.data_layer
    return ModeService(db_path=data_layer.database_path)


def _require_admin_user_id(request: Request, session_token: str) -> int:
    auth = _auth_service(request)
    try:
        session = auth.get_session(session_token, client_kind=ClientKind.WEB)
    except AuthError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "code": exc.code,
                "message": exc.message,
            },
        ) from exc

    if session.user.role != UserRole.ADMIN or not session.user.can_access_admin_features():
        raise HTTPException(
            status_code=403,
            detail={
                "code": "admin_only",
                "message": "Admin role is required",
            },
        )

    if session.user.user_id is None:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "invalid_user",
                "message": "Admin user id is missing",
            },
        )

    return session.user.user_id


@router.get("")
async def get_mode(request: Request) -> dict[str, object]:
    service = _mode_service(request)
    access_mode = service.get_mode()
    return {
        "status": "ok",
        "access_mode": access_mode.value,
    }


@router.post("")
async def set_mode(
    payload: UpdateModeRequest,
    request: Request,
    x_session_token: str = Header(..., alias="X-Session-Token"),
) -> dict[str, object]:
    admin_user_id = _require_admin_user_id(request, x_session_token)

    service = _mode_service(request)
    try:
        updated_mode = service.set_mode(payload.access_mode)
    except ModeError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "code": exc.code,
                "message": exc.message,
            },
        ) from exc

    return {
        "status": "ok",
        "access_mode": updated_mode.value,
        "updated_by_user_id": admin_user_id,
    }
