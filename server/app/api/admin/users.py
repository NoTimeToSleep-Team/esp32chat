from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.models import AdminUserRecord, ClientKind, DeviceBlacklistEntry, UserRole, UserStatus
from app.services.admin_users import AdminUsersError, AdminUsersService
from app.services.auth import AuthError, AuthService


router = APIRouter(prefix="/admin/users", tags=["admin-users"])


class AdminActionRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    reason: str | None = Field(default=None, max_length=2048)


class AdminUnbanRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)


class AdminTemporaryBlockRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    duration_minutes: int = Field(ge=1, le=10080)
    reason: str | None = Field(default=None, max_length=2048)


class AdminBlacklistDeviceRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    reason: str | None = Field(default=None, max_length=2048)
    device_id: str | None = Field(default=None, max_length=256)


class AdminUnblacklistDeviceRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    device_id: str | None = Field(default=None, max_length=256)


def _template_path() -> Path:
    return Path(__file__).resolve().parents[2] / "templates" / "admin" / "users" / "index.html"


def _auth_service(request: Request) -> AuthService:
    data_layer = request.app.state.data_layer
    return AuthService(db_path=data_layer.database_path)


def _admin_users_service(request: Request) -> AdminUsersService:
    data_layer = request.app.state.data_layer
    return AdminUsersService(db_path=data_layer.database_path)


def _resolve_admin_user_id(request: Request, session_token: str) -> int:
    service = _auth_service(request)
    try:
        session = service.get_session(session_token, client_kind=ClientKind.WEB)
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


def _admin_user_payload(record: AdminUserRecord) -> dict[str, object]:
    return {
        "user_id": record.user_id,
        "login": record.login,
        "role": record.role.value,
        "status": record.status.value,
        "phone": record.phone,
        "registration_device_id": record.registration_device_id,
        "created_at_ms": record.created_at_ms,
        "updated_at_ms": record.updated_at_ms,
        "block_reason": record.block_reason,
        "blocked_until_ms": record.blocked_until_ms,
        "restriction_updated_by_user_id": record.restriction_updated_by_user_id,
        "restriction_updated_at_ms": record.restriction_updated_at_ms,
        "device_blacklisted": record.device_blacklisted,
    }


def _blacklist_payload(entry: DeviceBlacklistEntry) -> dict[str, object]:
    return {
        "device_id": entry.device_id,
        "reason": entry.reason,
        "blocked_by_user_id": entry.blocked_by_user_id,
        "created_at_ms": entry.created_at_ms,
        "updated_at_ms": entry.updated_at_ms,
    }


def _raise_admin_error(exc: AdminUsersError) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail={
            "code": exc.code,
            "message": exc.message,
        },
    )


@router.get("/panel", response_class=HTMLResponse)
async def admin_users_panel() -> HTMLResponse:
    template = _template_path()
    html = template.read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@router.get("")
async def list_admin_users(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    status: UserStatus | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    admin_user_id = _resolve_admin_user_id(request, session_token)
    service = _admin_users_service(request)

    try:
        records = service.list_users(
            actor_user_id=admin_user_id,
            status=status,
            limit=limit,
            offset=offset,
        )
    except AdminUsersError as exc:
        _raise_admin_error(exc)

    return {
        "status": "ok",
        "count": len(records),
        "items": [_admin_user_payload(record) for record in records],
    }


@router.get("/{user_id}")
async def get_admin_user(
    request: Request,
    user_id: int,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, object]:
    admin_user_id = _resolve_admin_user_id(request, session_token)
    service = _admin_users_service(request)

    try:
        record = service.get_user(actor_user_id=admin_user_id, target_user_id=user_id)
    except AdminUsersError as exc:
        _raise_admin_error(exc)

    return {
        "status": "ok",
        "user": _admin_user_payload(record),
    }


@router.post("/{user_id}/ban")
async def ban_user(
    request: Request,
    user_id: int,
    payload: AdminActionRequest,
) -> dict[str, object]:
    admin_user_id = _resolve_admin_user_id(request, payload.session_token)
    service = _admin_users_service(request)

    try:
        record = service.ban_user(
            actor_user_id=admin_user_id,
            target_user_id=user_id,
            reason=payload.reason,
        )
    except AdminUsersError as exc:
        _raise_admin_error(exc)

    return {
        "status": "ok",
        "user": _admin_user_payload(record),
    }


@router.post("/{user_id}/unban")
async def unban_user(
    request: Request,
    user_id: int,
    payload: AdminUnbanRequest,
) -> dict[str, object]:
    admin_user_id = _resolve_admin_user_id(request, payload.session_token)
    service = _admin_users_service(request)

    try:
        record = service.unban_user(
            actor_user_id=admin_user_id,
            target_user_id=user_id,
        )
    except AdminUsersError as exc:
        _raise_admin_error(exc)

    return {
        "status": "ok",
        "user": _admin_user_payload(record),
    }


@router.post("/{user_id}/temporary-block")
async def temporary_block_user(
    request: Request,
    user_id: int,
    payload: AdminTemporaryBlockRequest,
) -> dict[str, object]:
    admin_user_id = _resolve_admin_user_id(request, payload.session_token)
    service = _admin_users_service(request)

    try:
        record = service.temporary_block_user(
            actor_user_id=admin_user_id,
            target_user_id=user_id,
            duration_minutes=payload.duration_minutes,
            reason=payload.reason,
        )
    except AdminUsersError as exc:
        _raise_admin_error(exc)

    return {
        "status": "ok",
        "user": _admin_user_payload(record),
    }


@router.post("/{user_id}/blacklist-device")
async def blacklist_device(
    request: Request,
    user_id: int,
    payload: AdminBlacklistDeviceRequest,
) -> dict[str, object]:
    admin_user_id = _resolve_admin_user_id(request, payload.session_token)
    service = _admin_users_service(request)

    try:
        record, entry = service.blacklist_device(
            actor_user_id=admin_user_id,
            target_user_id=user_id,
            reason=payload.reason,
            device_id=payload.device_id,
        )
    except AdminUsersError as exc:
        _raise_admin_error(exc)

    return {
        "status": "ok",
        "user": _admin_user_payload(record),
        "blacklist_entry": _blacklist_payload(entry),
    }


@router.post("/{user_id}/unblacklist-device")
async def unblacklist_device(
    request: Request,
    user_id: int,
    payload: AdminUnblacklistDeviceRequest,
) -> dict[str, object]:
    admin_user_id = _resolve_admin_user_id(request, payload.session_token)
    service = _admin_users_service(request)

    try:
        record = service.unblacklist_device(
            actor_user_id=admin_user_id,
            target_user_id=user_id,
            device_id=payload.device_id,
        )
    except AdminUsersError as exc:
        _raise_admin_error(exc)

    return {
        "status": "ok",
        "user": _admin_user_payload(record),
    }


@router.delete("/{user_id}")
async def delete_user(
    request: Request,
    user_id: int,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, object]:
    admin_user_id = _resolve_admin_user_id(request, session_token)
    service = _admin_users_service(request)

    try:
        deleted_user_id, deleted_login = service.delete_user(
            actor_user_id=admin_user_id,
            target_user_id=user_id,
        )
    except AdminUsersError as exc:
        _raise_admin_error(exc)

    return {
        "status": "ok",
        "deleted_user_id": deleted_user_id,
        "deleted_login": deleted_login,
    }
