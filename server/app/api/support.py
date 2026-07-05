from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.models import (
    ClientKind,
    SupportMessage,
    SupportMessageDraft,
    SupportTicket,
    SupportTicketDraft,
    SupportTicketStatus,
)
from app.services.auth import AuthError, AuthService
from app.services.support import SupportError, SupportService


router = APIRouter(tags=["support"])


class CreateSupportTicketRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    title: str = Field(min_length=1, max_length=256)
    body_text: str = Field(min_length=1, max_length=8000)


class SendSupportMessageRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    body_text: str = Field(min_length=1, max_length=8000)


class UpdateSupportTicketStatusRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    status: SupportTicketStatus


def _template_path() -> Path:
    return Path(__file__).resolve().parents[1] / "templates" / "support" / "index.html"


def _auth_service(request: Request) -> AuthService:
    data_layer = request.app.state.data_layer
    return AuthService(db_path=data_layer.database_path)


def _support_service(request: Request) -> SupportService:
    data_layer = request.app.state.data_layer
    return SupportService(db_path=data_layer.database_path)


def _resolve_user_id(request: Request, session_token: str) -> int:
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

    if session.user.user_id is None:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "invalid_user",
                "message": "Authenticated user id is missing",
            },
        )
    return session.user.user_id


def _ticket_payload(ticket: SupportTicket) -> dict[str, object]:
    return {
        "ticket_id": ticket.ticket_id,
        "user_id": ticket.user_id,
        "title": ticket.title,
        "status": ticket.status.value,
        "created_at_ms": ticket.created_at_ms,
        "updated_at_ms": ticket.updated_at_ms,
        "last_message_at_ms": ticket.last_message_at_ms,
    }


def _message_payload(message: SupportMessage) -> dict[str, object]:
    return {
        "message_id": message.message_id,
        "ticket_id": message.ticket_id,
        "author_user_id": message.author_user_id,
        "body_text": message.body_text,
        "created_at_ms": message.created_at_ms,
    }


def _raise_support_error(exc: SupportError) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail={
            "code": exc.code,
            "message": exc.message,
        },
    )


@router.get("/support", response_class=HTMLResponse)
async def support_page() -> HTMLResponse:
    template = _template_path()
    html = template.read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@router.post("/support/api/tickets")
async def create_support_ticket(
    request: Request,
    payload: CreateSupportTicketRequest,
) -> dict[str, object]:
    user_id = _resolve_user_id(request, payload.session_token)
    service = _support_service(request)

    try:
        ticket = service.create_ticket(
            requester_user_id=user_id,
            draft=SupportTicketDraft(
                title=payload.title,
                body_text=payload.body_text,
            ),
        )
    except (SupportError, ValueError) as exc:
        if isinstance(exc, SupportError):
            _raise_support_error(exc)
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_support_payload",
                "message": str(exc),
            },
        )

    return {
        "status": "ok",
        "ticket": _ticket_payload(ticket),
    }


@router.get("/support/api/tickets")
async def list_support_tickets(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    status: SupportTicketStatus | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=300),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    user_id = _resolve_user_id(request, session_token)
    service = _support_service(request)

    try:
        tickets = service.list_tickets(
            requester_user_id=user_id,
            status=status,
            limit=limit,
            offset=offset,
        )
    except SupportError as exc:
        _raise_support_error(exc)

    return {
        "status": "ok",
        "count": len(tickets),
        "items": [_ticket_payload(ticket) for ticket in tickets],
    }


@router.get("/support/api/tickets/{ticket_id}/messages")
async def list_support_messages(
    request: Request,
    ticket_id: int,
    session_token: str = Query(..., min_length=8, max_length=512),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    user_id = _resolve_user_id(request, session_token)
    service = _support_service(request)

    try:
        messages = service.list_messages(
            ticket_id=ticket_id,
            requester_user_id=user_id,
            limit=limit,
            offset=offset,
        )
    except SupportError as exc:
        _raise_support_error(exc)

    return {
        "status": "ok",
        "count": len(messages),
        "items": [_message_payload(message) for message in messages],
    }


@router.post("/support/api/tickets/{ticket_id}/messages")
async def send_support_message(
    request: Request,
    ticket_id: int,
    payload: SendSupportMessageRequest,
) -> dict[str, object]:
    user_id = _resolve_user_id(request, payload.session_token)
    service = _support_service(request)

    try:
        message = service.send_message(
            ticket_id=ticket_id,
            author_user_id=user_id,
            draft=SupportMessageDraft(body_text=payload.body_text),
        )
    except (SupportError, ValueError) as exc:
        if isinstance(exc, SupportError):
            _raise_support_error(exc)
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_support_payload",
                "message": str(exc),
            },
        )

    return {
        "status": "ok",
        "message": _message_payload(message),
    }


@router.post("/support/api/tickets/{ticket_id}/status")
async def update_support_ticket_status(
    request: Request,
    ticket_id: int,
    payload: UpdateSupportTicketStatusRequest,
) -> dict[str, object]:
    user_id = _resolve_user_id(request, payload.session_token)
    service = _support_service(request)

    try:
        ticket = service.set_ticket_status(
            ticket_id=ticket_id,
            actor_user_id=user_id,
            status=payload.status,
        )
    except SupportError as exc:
        _raise_support_error(exc)

    return {
        "status": "ok",
        "ticket": _ticket_payload(ticket),
    }
