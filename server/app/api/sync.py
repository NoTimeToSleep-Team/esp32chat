# DEPRECATED RPi-Only: требует внутренние контроллеры, не активно в RPi-only архитектуре.
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.models import ClientKind, UserRole
from app.services.auth import AuthError, AuthService
from app.services.sync_queue import SyncEvent, SyncQueueService


router = APIRouter(prefix="/sync/api/events", tags=["edge-sync"])


class SyncEventRequest(BaseModel):
    event_type: str = Field(min_length=1, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict)
    source_node_id: str = Field(min_length=1, max_length=128)
    target_node_id: str = Field(min_length=1, max_length=128)


class SyncAckRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=512)


def _sync_service(request: Request) -> SyncQueueService:
    return SyncQueueService(db_path=request.app.state.data_layer.database_path)


def _require_admin(request: Request, session_token: str) -> None:
    service = AuthService(db_path=request.app.state.data_layer.database_path)
    try:
        session = service.get_session(session_token, client_kind=ClientKind.WEB)
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    if session.user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail={"code": "admin_only", "message": "Admin role is required"})


def _event_payload(event: SyncEvent) -> dict[str, object]:
    return {
        "id": event.id,
        "event_type": event.event_type,
        "payload": event.payload,
        "source_node_id": event.source_node_id,
        "target_node_id": event.target_node_id,
        "idempotency_key": event.idempotency_key,
        "status": event.status,
        "created_at_ms": event.created_at_ms,
        "last_attempt_at_ms": event.last_attempt_at_ms,
        "attempt_count": event.attempt_count,
        "expires_at_ms": event.expires_at_ms,
        "conflict_resolution": event.conflict_resolution,
    }


def _raise_sync_error(exc: Exception) -> None:
    if isinstance(exc, KeyError):
        raise HTTPException(status_code=404, detail={"code": "sync_event_not_found", "message": str(exc)}) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=422, detail={"code": "invalid_sync_event", "message": str(exc)}) from exc
    raise HTTPException(status_code=500, detail={"code": "sync_queue_error", "message": str(exc)}) from exc


@router.post("")
async def push_sync_event(
    payload: SyncEventRequest,
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, object]:
    _require_admin(request, session_token)
    try:
        event = _sync_service(request).enqueue_event(
            event_type=payload.event_type,
            payload=payload.payload,
            source_id=payload.source_node_id,
            target_id=payload.target_node_id,
        )
    except Exception as exc:
        _raise_sync_error(exc)
    return {"status": "ok", "event": _event_payload(event)}


@router.get("/pending")
async def pull_pending_sync_events(
    request: Request,
    target_node_id: str = Query(..., min_length=1, max_length=128),
    limit: int = Query(50, ge=1, le=500),
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, object]:
    _require_admin(request, session_token)
    try:
        service = _sync_service(request)
        events = service.dequeue_pending(limit=limit, target_node_id=target_node_id)
        for event in events:
            service.mark_sent(event.id)
        refreshed = [service.resolve_duplicates(event.idempotency_key) for event in events]
    except Exception as exc:
        _raise_sync_error(exc)
    return {"status": "ok", "count": len(refreshed), "items": [_event_payload(event) for event in refreshed]}


@router.post("/{event_id}/ack")
async def acknowledge_sync_event(
    event_id: int,
    request: Request,
    payload: SyncAckRequest | None = None,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, object]:
    _require_admin(request, session_token)
    try:
        service = _sync_service(request)
        if payload is not None and payload.reason:
            event = service.mark_conflict(event_id, payload.reason)
        else:
            event = service.mark_acknowledged(event_id)
    except Exception as exc:
        _raise_sync_error(exc)
    return {"status": "ok", "event": _event_payload(event)}
