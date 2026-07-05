from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.models import ChatDraft, ChatMessage, ChatRoom, ClientKind, MessageDraft
from app.realtime import chat_message_event, chat_message_payload
from app.services.auth import AuthError, AuthService
from app.services.chat import ChatError, ChatService


router = APIRouter(tags=["chat"])


class SendMessageRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    body_text: str = Field(min_length=1, max_length=4000)
    client_message_id: str | None = Field(default=None, max_length=128)


class CreateChatRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    title: str = Field(min_length=1, max_length=256)
    description: str | None = Field(default=None, max_length=2000)


def _template_path() -> Path:
    return Path(__file__).resolve().parents[1] / "templates" / "chat" / "index.html"


def _auth_service(request: Request) -> AuthService:
    data_layer = request.app.state.data_layer
    return AuthService(db_path=data_layer.database_path)


def _chat_service(request: Request) -> ChatService:
    data_layer = request.app.state.data_layer
    return ChatService(db_path=data_layer.database_path)


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


def _chat_payload(chat: ChatRoom) -> dict[str, object]:
    return {
        "chat_id": chat.chat_id,
        "kind": chat.kind.value,
        "title": chat.title,
        "description": chat.description,
        "owner_user_id": chat.owner_user_id,
        "is_private": chat.is_private,
        "avatar_url": chat.avatar_url,
        "has_room_code": chat.has_room_code,
        "created_at_ms": chat.created_at_ms,
        "updated_at_ms": chat.updated_at_ms,
    }


def _message_payload(message: ChatMessage) -> dict[str, object]:
    return chat_message_payload(message)


@router.get("/chat", response_class=HTMLResponse)
async def chat_page() -> HTMLResponse:
    template = _template_path()
    html = template.read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@router.get("/chat/api/chats")
async def list_chats(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, object]:
    user_id = _resolve_user_id(request, session_token)
    service = _chat_service(request)

    try:
        chats = service.list_user_chats(user_id=user_id)
    except ChatError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "code": exc.code,
                "message": exc.message,
            },
        ) from exc

    return {
        "status": "ok",
        "count": len(chats),
        "items": [_chat_payload(chat) for chat in chats],
    }


@router.post("/chat/api/chats")
async def create_chat(
    request: Request,
    payload: CreateChatRequest,
) -> dict[str, object]:
    user_id = _resolve_user_id(request, payload.session_token)
    service = _chat_service(request)

    try:
        chat = service.create_custom_chat(
            creator_user_id=user_id,
            draft=ChatDraft(title=payload.title, description=payload.description),
        )
    except ChatError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_chat_payload", "message": str(exc)},
        )

    return {"status": "ok", "chat": _chat_payload(chat)}


@router.get("/chat/api/chats/{chat_id}/messages")
async def list_chat_messages(
    request: Request,
    chat_id: int,
    session_token: str = Query(..., min_length=8, max_length=512),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    user_id = _resolve_user_id(request, session_token)
    service = _chat_service(request)

    try:
        messages = service.list_messages(
            chat_id=chat_id,
            requester_user_id=user_id,
            limit=limit,
            offset=offset,
        )
    except ChatError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "code": exc.code,
                "message": exc.message,
            },
        ) from exc

    return {
        "status": "ok",
        "count": len(messages),
        "items": [_message_payload(message) for message in messages],
    }


@router.post("/chat/api/chats/{chat_id}/messages")
async def post_chat_message(
    request: Request,
    chat_id: int,
    payload: SendMessageRequest,
) -> dict[str, object]:
    user_id = _resolve_user_id(request, payload.session_token)
    service = _chat_service(request)

    try:
        message = service.send_message(
            chat_id=chat_id,
            author_user_id=user_id,
            draft=MessageDraft(
                body_text=payload.body_text,
                client_message_id=(payload.client_message_id or "").strip() or None,
            ),
        )
    except (ChatError, ValueError) as exc:
        if isinstance(exc, ChatError):
            raise HTTPException(
                status_code=exc.status_code,
                detail={
                    "code": exc.code,
                    "message": exc.message,
                },
            ) from exc
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_message_payload",
                "message": str(exc),
            },
        )

    broker = getattr(request.app.state, "realtime_broker", None)
    delivered_to = 0
    if broker is not None:
        delivered_to = await broker.publish(
            chat_id=chat_id,
            event=chat_message_event(message),
        )

    return {
        "status": "ok",
        "message": _message_payload(message),
        "delivered_to": delivered_to,
    }
