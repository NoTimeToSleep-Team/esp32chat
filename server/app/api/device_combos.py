from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.models import ClientKind
from app.services.auth import AuthError, AuthService
from app.services.device_combos import (
    DeviceComboError,
    DeviceComboRecord,
    DeviceComboService,
)


router = APIRouter(prefix="/devices/api/combos", tags=["device-combos"])


class DeviceComboRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    device_id: str = Field(min_length=1, max_length=256)
    actions: list[str] = Field(min_length=3, max_length=32)


class DeviceComboVerifyRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    device_id: str = Field(min_length=1, max_length=256)
    actions: list[str] = Field(min_length=1, max_length=32)


class DeviceComboResetRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    device_id: str = Field(min_length=1, max_length=256)


def _auth_service(request: Request) -> AuthService:
    data_layer = request.app.state.data_layer
    return AuthService(db_path=data_layer.database_path)


def _combo_service(request: Request) -> DeviceComboService:
    data_layer = request.app.state.data_layer
    return DeviceComboService(db_path=data_layer.database_path)


def _resolve_device_user_id(
    request: Request,
    session_token: str,
    *,
    device_id: str | None = None,
) -> int:
    service = _auth_service(request)
    try:
        session = service.get_session(session_token, client_kind=ClientKind.DEVICE)
    except AuthError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    if session.user.user_id is None:
        raise HTTPException(
            status_code=500,
            detail={"code": "invalid_user", "message": "Authenticated user id is missing"},
        )
    bound_device_id = (session.session.device_id or "").strip()
    requested_device_id = (device_id or "").strip()
    if bound_device_id and requested_device_id and bound_device_id != requested_device_id:
        raise HTTPException(
            status_code=403,
            detail={"code": "device_scope_mismatch", "message": "Session is bound to another device"},
        )
    return session.user.user_id


def _combo_payload(record: DeviceComboRecord | None) -> dict[str, object] | None:
    if record is None:
        return None
    return {
        "user_id": record.user_id,
        "device_id": record.device_id,
        "combo_actions_count": record.combo_actions_count,
        "failure_count": record.failure_count,
        "locked_until_ms": record.locked_until_ms,
        "created_at_ms": record.created_at_ms,
        "updated_at_ms": record.updated_at_ms,
        "verified_at_ms": record.verified_at_ms,
        "reset_at_ms": record.reset_at_ms,
    }


def _raise_combo_error(exc: DeviceComboError) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": exc.message},
    ) from exc


@router.post("/set")
async def set_device_combo(payload: DeviceComboRequest, request: Request) -> dict[str, object]:
    user_id = _resolve_device_user_id(
        request,
        payload.session_token,
        device_id=payload.device_id,
    )
    service = _combo_service(request)
    try:
        record = service.set_combo(
            user_id=user_id,
            device_id=payload.device_id,
            actions=payload.actions,
        )
    except DeviceComboError as exc:
        _raise_combo_error(exc)
    return {"status": "ok", "combo": _combo_payload(record)}


@router.post("/verify")
async def verify_device_combo(payload: DeviceComboVerifyRequest, request: Request) -> dict[str, object]:
    user_id = _resolve_device_user_id(
        request,
        payload.session_token,
        device_id=payload.device_id,
    )
    service = _combo_service(request)
    try:
        result = service.verify_combo(
            user_id=user_id,
            device_id=payload.device_id,
            actions=payload.actions,
        )
    except DeviceComboError as exc:
        _raise_combo_error(exc)
    return {
        "status": "ok",
        "verified": result.verified,
        "combo": _combo_payload(result.record),
    }


@router.post("/reset")
async def reset_device_combo(
    payload: DeviceComboResetRequest,
    request: Request,
) -> dict[str, object]:
    user_id = _resolve_device_user_id(
        request,
        payload.session_token,
        device_id=payload.device_id,
    )
    service = _combo_service(request)
    try:
        record = service.reset_combo(user_id=user_id, device_id=payload.device_id)
    except DeviceComboError as exc:
        _raise_combo_error(exc)
    return {"status": "ok", "combo": _combo_payload(record)}
