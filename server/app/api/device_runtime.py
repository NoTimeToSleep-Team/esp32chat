from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.models import ClientKind, DeviceNodeRecord, UserRole
from app.services.auth import AuthError, AuthService
from app.services.device_runtime import DeviceRuntimeError, DeviceRuntimeService


router = APIRouter(tags=["ops"])


class DeviceRegisterRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    device_id: str = Field(min_length=1, max_length=128)
    device_type: str = Field(min_length=1, max_length=64)
    boot_id: str | None = Field(default=None, max_length=128)
    transport: str | None = Field(default=None, max_length=64)
    metadata: dict[str, object] | None = None


class DeviceHeartbeatRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    device_id: str = Field(min_length=1, max_length=128)
    device_type: str = Field(min_length=1, max_length=64)
    heartbeat_status: str = Field(min_length=1, max_length=64)
    uptime_ms: int = Field(ge=0)
    queue_depth: int = Field(ge=0)
    metrics: dict[str, object] | None = None


class DeviceTelemetryRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    device_id: str = Field(min_length=1, max_length=128)
    device_type: str = Field(min_length=1, max_length=64)
    snapshot: dict[str, object]
    source_message_id: str | None = Field(default=None, max_length=128)


def _auth_service(request: Request) -> AuthService:
    data_layer = request.app.state.data_layer
    return AuthService(db_path=data_layer.database_path)


def _device_runtime_service(request: Request) -> DeviceRuntimeService:
    data_layer = request.app.state.data_layer
    return DeviceRuntimeService(db_path=data_layer.database_path)


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


def _raise_runtime_error(exc: DeviceRuntimeError) -> None:
    raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})


def _node_payload(record: DeviceNodeRecord) -> dict[str, object]:
    return {
        "device_id": record.device_id,
        "device_type": record.device_type,
        "status": record.status,
        "last_seen_ms": record.last_seen_ms,
        "metadata": record.metadata,
    }


@router.post("/ops/api/devices/register")
async def register_device_node(request: Request, payload: DeviceRegisterRequest) -> dict[str, object]:
    admin_user_id = _resolve_admin_user_id(request, payload.session_token)
    service = _device_runtime_service(request)

    try:
        node = service.register_device(
            actor_user_id=admin_user_id,
            device_id=payload.device_id,
            device_type=payload.device_type,
            boot_id=payload.boot_id,
            transport=payload.transport,
            metadata=payload.metadata,
        )
    except DeviceRuntimeError as exc:
        _raise_runtime_error(exc)

    return {"status": "ok", "device": _node_payload(node)}


@router.post("/ops/api/devices/heartbeat")
async def submit_device_heartbeat(request: Request, payload: DeviceHeartbeatRequest) -> dict[str, object]:
    admin_user_id = _resolve_admin_user_id(request, payload.session_token)
    service = _device_runtime_service(request)

    try:
        node = service.record_heartbeat(
            actor_user_id=admin_user_id,
            device_id=payload.device_id,
            device_type=payload.device_type,
            heartbeat_status=payload.heartbeat_status,
            uptime_ms=payload.uptime_ms,
            queue_depth=payload.queue_depth,
            metrics=payload.metrics,
        )
    except DeviceRuntimeError as exc:
        _raise_runtime_error(exc)

    return {"status": "ok", "device": _node_payload(node)}


@router.post("/ops/api/devices/telemetry")
async def submit_device_telemetry(request: Request, payload: DeviceTelemetryRequest) -> dict[str, object]:
    admin_user_id = _resolve_admin_user_id(request, payload.session_token)
    service = _device_runtime_service(request)

    try:
        node = service.record_telemetry(
            actor_user_id=admin_user_id,
            device_id=payload.device_id,
            device_type=payload.device_type,
            snapshot=payload.snapshot,
            source_message_id=payload.source_message_id,
        )
    except DeviceRuntimeError as exc:
        _raise_runtime_error(exc)

    return {"status": "ok", "device": _node_payload(node)}


@router.get("/ops/api/devices/{device_id}/status")
async def get_device_node_status(
    request: Request,
    device_id: str,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, object]:
    _resolve_admin_user_id(request, session_token)
    service = _device_runtime_service(request)

    try:
        node = service.get_device_status(device_id=device_id)
    except DeviceRuntimeError as exc:
        _raise_runtime_error(exc)

    return {"status": "ok", "device": _node_payload(node)}
