from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.models import AccessMode, ClientKind, RfidAccessEvent, RfidCard, RfidCardDraft, RfidModeDecision, UserRole
from app.services.auth import AuthError, AuthService
from app.services.rfid import RfidError, RfidService


router = APIRouter(tags=["rfid"])


class EnrollRfidCardRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    card_uid: str = Field(min_length=4, max_length=64)
    card_label: str = Field(min_length=1, max_length=128)
    note: str | None = Field(default=None, max_length=2048)
    is_active: bool = True


class ToggleRfidCardActiveRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    is_active: bool


class VerifyRfidCardRequest(BaseModel):
    card_uid: str = Field(min_length=4, max_length=64)
    source: str | None = Field(default=None, max_length=128)


class SwitchModeByRfidCardRequest(BaseModel):
    card_uid: str = Field(min_length=4, max_length=64)
    target_mode: AccessMode = AccessMode.OPEN
    source: str | None = Field(default=None, max_length=128)


def _template_path() -> Path:
    return Path(__file__).resolve().parents[1] / "templates" / "rfid" / "index.html"


def _auth_service(request: Request) -> AuthService:
    data_layer = request.app.state.data_layer
    return AuthService(db_path=data_layer.database_path)


def _rfid_service(request: Request) -> RfidService:
    data_layer = request.app.state.data_layer
    settings = request.app.state.settings
    return RfidService(
        db_path=data_layer.database_path,
        uid_pepper=settings.session_secret,
    )


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


def _card_payload(card: RfidCard) -> dict[str, object]:
    return {
        "card_id": card.card_id,
        "uid_mask": card.uid_mask,
        "card_label": card.card_label,
        "note": card.note,
        "is_active": card.is_active,
        "created_by_user_id": card.created_by_user_id,
        "created_at_ms": card.created_at_ms,
        "updated_at_ms": card.updated_at_ms,
        "last_used_at_ms": card.last_used_at_ms,
    }


def _event_payload(event: RfidAccessEvent) -> dict[str, object]:
    return {
        "event_id": event.event_id,
        "card_id": event.card_id,
        "uid_mask": event.uid_mask,
        "action": event.action.value,
        "granted": event.granted,
        "requested_mode": event.requested_mode.value if event.requested_mode is not None else None,
        "resolved_mode": event.resolved_mode.value if event.resolved_mode is not None else None,
        "reason": event.reason,
        "source": event.source,
        "actor_user_id": event.actor_user_id,
        "created_at_ms": event.created_at_ms,
    }


def _decision_payload(decision: RfidModeDecision) -> dict[str, object]:
    return {
        "granted": decision.granted,
        "access_mode": decision.access_mode.value,
        "card_id": decision.card_id,
        "card_label": decision.card_label,
        "uid_mask": decision.uid_mask,
        "reason": decision.reason,
    }


def _raise_rfid_error(exc: RfidError) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": exc.message},
    )


@router.get("/rfid", response_class=HTMLResponse)
async def rfid_page() -> HTMLResponse:
    template = _template_path()
    html = template.read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@router.get("/rfid/api/cards")
async def list_rfid_cards(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    include_inactive: bool = Query(default=True),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    admin_user_id = _resolve_admin_user_id(request, session_token)
    service = _rfid_service(request)

    try:
        cards = service.list_cards(
            actor_user_id=admin_user_id,
            include_inactive=include_inactive,
            limit=limit,
            offset=offset,
        )
    except RfidError as exc:
        _raise_rfid_error(exc)

    return {
        "status": "ok",
        "count": len(cards),
        "items": [_card_payload(card) for card in cards],
    }


@router.post("/rfid/api/cards")
async def enroll_rfid_card(
    request: Request,
    payload: EnrollRfidCardRequest,
) -> dict[str, object]:
    admin_user_id = _resolve_admin_user_id(request, payload.session_token)
    service = _rfid_service(request)

    try:
        card = service.enroll_card(
            actor_user_id=admin_user_id,
            draft=RfidCardDraft(
                card_uid=payload.card_uid,
                card_label=payload.card_label,
                note=payload.note,
            ),
            is_active=payload.is_active,
        )
    except (RfidError, ValueError) as exc:
        if isinstance(exc, RfidError):
            _raise_rfid_error(exc)
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_rfid_payload", "message": str(exc)},
        )

    return {"status": "ok", "card": _card_payload(card)}


@router.post("/rfid/api/cards/{card_id}/active")
async def set_rfid_card_active(
    request: Request,
    card_id: int,
    payload: ToggleRfidCardActiveRequest,
) -> dict[str, object]:
    admin_user_id = _resolve_admin_user_id(request, payload.session_token)
    service = _rfid_service(request)

    try:
        card = service.set_card_active(
            actor_user_id=admin_user_id,
            card_id=card_id,
            is_active=payload.is_active,
        )
    except RfidError as exc:
        _raise_rfid_error(exc)

    return {"status": "ok", "card": _card_payload(card)}


@router.delete("/rfid/api/cards/{card_id}")
async def delete_rfid_card(
    request: Request,
    card_id: int,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, object]:
    admin_user_id = _resolve_admin_user_id(request, session_token)
    service = _rfid_service(request)

    try:
        deleted_card_id, deleted_label = service.delete_card(
            actor_user_id=admin_user_id,
            card_id=card_id,
        )
    except RfidError as exc:
        _raise_rfid_error(exc)

    return {
        "status": "ok",
        "deleted_card_id": deleted_card_id,
        "deleted_label": deleted_label,
    }


@router.get("/rfid/api/events")
async def list_rfid_events(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    admin_user_id = _resolve_admin_user_id(request, session_token)
    service = _rfid_service(request)

    try:
        events = service.list_events(
            actor_user_id=admin_user_id,
            limit=limit,
            offset=offset,
        )
    except RfidError as exc:
        _raise_rfid_error(exc)

    return {
        "status": "ok",
        "count": len(events),
        "items": [_event_payload(event) for event in events],
    }


@router.post("/rfid/api/verify")
async def verify_rfid_card(
    request: Request,
    payload: VerifyRfidCardRequest,
) -> dict[str, object]:
    service = _rfid_service(request)

    try:
        decision = service.verify_card(
            card_uid=payload.card_uid,
            source=payload.source,
        )
    except RfidError as exc:
        _raise_rfid_error(exc)

    return {"status": "ok", "decision": _decision_payload(decision)}


@router.post("/rfid/api/mode/switch-by-card")
async def switch_mode_by_rfid_card(
    request: Request,
    payload: SwitchModeByRfidCardRequest,
) -> dict[str, object]:
    service = _rfid_service(request)

    try:
        decision = service.switch_mode_by_card(
            card_uid=payload.card_uid,
            target_mode=payload.target_mode,
            source=payload.source,
        )
    except RfidError as exc:
        _raise_rfid_error(exc)

    return {"status": "ok", "decision": _decision_payload(decision)}
