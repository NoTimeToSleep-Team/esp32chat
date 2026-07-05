from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.models import ChatDraft, ChatMember, ChatRoom, ClientKind
from app.services.auth import AuthError, AuthService
from app.services.chat import ChatError, ChatService


router = APIRouter(tags=["chat-private"])


class CreatePrivateChatRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    title: str = Field(min_length=1, max_length=256)
    description: str | None = Field(default=None, max_length=2048)
    avatar_url: str | None = Field(default=None, max_length=1024)
    room_code: str | None = Field(default=None, max_length=4)


class JoinPrivateChatRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    room_code: str | None = Field(default=None, max_length=4)


class UpdatePrivateConfigRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    title: str | None = Field(default=None, max_length=256)
    description: str | None = Field(default=None, max_length=2048)
    avatar_url: str | None = Field(default=None, max_length=1024)
    room_code: str | None = Field(default=None, max_length=4)
    is_private: bool | None = None


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


def _member_payload(member: ChatMember) -> dict[str, object]:
    return {
        "chat_id": member.chat_id,
        "user_id": member.user_id,
        "role": member.role.value,
        "joined_at_ms": member.joined_at_ms,
    }


def _raise_chat_error(exc: ChatError) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail={
            "code": exc.code,
            "message": exc.message,
        },
    )


@router.post("/chat/api/private")
async def create_private_chat(
    request: Request,
    payload: CreatePrivateChatRequest,
) -> dict[str, object]:
    user_id = _resolve_user_id(request, payload.session_token)
    service = _chat_service(request)

    try:
        chat = service.create_custom_chat(
            creator_user_id=user_id,
            draft=ChatDraft(title=payload.title, description=payload.description),
            is_private=True,
            room_code=payload.room_code,
            avatar_url=payload.avatar_url,
        )
    except (ChatError, ValueError) as exc:
        if isinstance(exc, ChatError):
            _raise_chat_error(exc)
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_chat_payload",
                "message": str(exc),
            },
        )

    return {
        "status": "ok",
        "chat": _chat_payload(chat),
    }


@router.post("/chat/api/private/{chat_id}/join")
async def join_private_chat(
    request: Request,
    chat_id: int,
    payload: JoinPrivateChatRequest,
) -> dict[str, object]:
    user_id = _resolve_user_id(request, payload.session_token)
    service = _chat_service(request)

    try:
        member = service.join_private_chat(
            chat_id=chat_id,
            user_id=user_id,
            room_code=payload.room_code,
        )
    except ChatError as exc:
        _raise_chat_error(exc)

    return {
        "status": "ok",
        "member": _member_payload(member),
    }


@router.get("/chat/api/private/{chat_id}/members")
async def list_private_members(
    request: Request,
    chat_id: int,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, object]:
    user_id = _resolve_user_id(request, session_token)
    service = _chat_service(request)

    try:
        members = service.list_members(chat_id=chat_id, requester_user_id=user_id)
    except ChatError as exc:
        _raise_chat_error(exc)

    return {
        "status": "ok",
        "count": len(members),
        "items": [_member_payload(member) for member in members],
    }


@router.post("/chat/api/private/{chat_id}/config")
async def update_private_config(
    request: Request,
    chat_id: int,
    payload: UpdatePrivateConfigRequest,
) -> dict[str, object]:
    user_id = _resolve_user_id(request, payload.session_token)
    service = _chat_service(request)

    try:
        chat = service.configure_private_room(
            chat_id=chat_id,
            actor_user_id=user_id,
            title=payload.title,
            description=payload.description,
            avatar_url=payload.avatar_url,
            room_code=payload.room_code,
            is_private=payload.is_private,
        )
    except ChatError as exc:
        _raise_chat_error(exc)

    return {
        "status": "ok",
        "chat": _chat_payload(chat),
    }
