from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from app.models import (
    ChatDraft,
    ChatMemberRole,
    ChatMessage,
    ChatRoom,
    ChatType,
    ClientKind,
    MessageDraft,
    UserRole,
)
from app.realtime import chat_message_event, chat_message_payload
from app.services.activity_log import ActivityLogService
from app.services.auth import AuthError, AuthService
from app.services.avatars import AvatarPayloadError, decode_avatar_payload
from app.services.chat import ChatError, ChatService
from app.services.presence import presence


router = APIRouter(tags=["chat"])


class SendMessageRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    body_text: str = Field(min_length=0, max_length=4000)
    client_message_id: str | None = Field(default=None, max_length=128)
    attachment_ids: list[int] = Field(default_factory=list, max_length=8)
    reply_to_message_id: int | None = None


class CreateChatRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    title: str = Field(min_length=1, max_length=256)
    description: str | None = Field(default=None, max_length=2000)
    member_ids: list[int] = Field(default_factory=list, max_length=200)
    chat_type: str | None = Field(default=None, max_length=16)
    username: str | None = Field(default=None, max_length=64)
    is_public: bool | None = None
    history_visible: bool | None = None


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

    presence.touch(session.user.user_id)
    return session.user.user_id


def _parse_chat_type(value: str | None) -> ChatType | None:
    if not value:
        return None
    try:
        chat_type = ChatType(value.strip().lower())
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_chat_type", "message": "Chat type must be group or channel"},
        ) from exc
    if chat_type == ChatType.DM:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_chat_type", "message": "Direct chats are created separately"},
        )
    return chat_type


def _parse_member_role(value: str | None) -> ChatMemberRole | None:
    if not value:
        return None
    try:
        role = ChatMemberRole(value.strip().lower())
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_role", "message": "Unknown member role"},
        ) from exc
    if role == ChatMemberRole.OWNER:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_role", "message": "Use ownership transfer to change the owner"},
        )
    return role


def _chat_payload(chat: ChatRoom, session_token: str | None = None) -> dict[str, object]:
    avatar_url = chat.avatar_url
    if chat.avatar_path:
        avatar_url = f"/chat/api/chats/{chat.chat_id}/avatar?v={chat.updated_at_ms}"
        if session_token:
            avatar_url += f"&session_token={session_token}"
    return {
        "chat_id": chat.chat_id,
        "kind": chat.kind.value,
        "title": chat.title,
        "description": chat.description,
        "owner_user_id": chat.owner_user_id,
        "is_private": chat.is_private,
        "avatar_url": avatar_url,
        "has_avatar": bool(chat.avatar_path),
        "has_room_code": chat.has_room_code,
        "created_at_ms": chat.created_at_ms,
        "updated_at_ms": chat.updated_at_ms,
        "chat_type": chat.chat_type.value,
        "username": chat.username,
        "is_public": chat.is_public,
        "slow_mode_seconds": chat.slow_mode_seconds,
        "pinned_message_id": chat.pinned_message_id,
        "history_visible": chat.history_visible,
    }


def _chat_summary_payload(summary: dict[str, object], session_token: str) -> dict[str, object]:
    chat = summary.get("chat")
    payload = _chat_payload(chat, session_token) if isinstance(chat, ChatRoom) else {}
    payload.update(
        {
            "my_role": summary.get("my_role"),
            "is_member": summary.get("is_member"),
            "is_muted": summary.get("is_muted"),
            "is_archived": summary.get("is_archived"),
            "is_pinned": summary.get("is_pinned"),
            "unread_count": summary.get("unread_count") or 0,
            "draft_text": summary.get("draft_text"),
            "last_message_text": summary.get("last_message_text"),
            "last_message_at_ms": summary.get("last_message_at_ms"),
        }
    )
    return payload


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
        summaries = service.list_chat_summaries(user_id=user_id)
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
        "count": len(summaries),
        "items": [_chat_summary_payload(item, session_token) for item in summaries],
    }


@router.get("/chat/api/updates")
async def list_chat_updates(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    since_ms: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, object]:
    user_id = _resolve_user_id(request, session_token)
    service = _chat_service(request)

    try:
        items = service.list_updates(user_id=user_id, since_ms=since_ms, limit=limit)
    except ChatError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    import time as _time

    return {
        "status": "ok",
        "count": len(items),
        "items": items,
        "server_time_ms": int(_time.time() * 1000),
    }


@router.post("/chat/api/chats")
async def create_chat(
    request: Request,
    payload: CreateChatRequest,
) -> dict[str, object]:
    user_id = _resolve_user_id(request, payload.session_token)
    service = _chat_service(request)

    parsed_type = _parse_chat_type(payload.chat_type)
    try:
        chat = service.create_custom_chat(
            creator_user_id=user_id,
            draft=ChatDraft(title=payload.title, description=payload.description),
            member_ids=payload.member_ids,
            require_members=parsed_type != ChatType.CHANNEL,
            chat_type=parsed_type,
            username=payload.username,
            is_public=payload.is_public,
            history_visible=payload.history_visible,
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

    return {"status": "ok", "chat": _chat_payload(chat, payload.session_token)}


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
                attachment_ids=tuple(payload.attachment_ids),
                reply_to_message_id=payload.reply_to_message_id,
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

    ActivityLogService(db_path=request.app.state.data_layer.database_path).log(
        "message_sent", user_id=user_id,
        details=f"chat_id={chat_id} len={len(payload.body_text)}"
    )

    return {
        "status": "ok",
        "message": _message_payload(message),
        "delivered_to": delivered_to,
    }


# --- DM (Direct Message) ---


@router.get("/chat/api/users/search")
async def search_chat_users(request: Request, session_token: str = Query(..., min_length=8, max_length=512), q: str = Query(default="", max_length=128)) -> dict[str, object]:
    user_id = _resolve_user_id(request, session_token)
    chat_service = _chat_service(request)
    results = chat_service.search_users(q, viewer_user_id=user_id)
    return {"status": "ok", "items": results}


class StartDMRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    target_user_id: int


@router.post("/chat/api/dm")
async def start_dm(request: Request, payload: StartDMRequest) -> dict[str, object]:
    user_id = _resolve_user_id(request, payload.session_token)
    chat_service = _chat_service(request)
    try:
        chat = chat_service.get_or_create_dm(user_id, payload.target_user_id)
    except ChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    return {"status": "ok", "chat": _chat_payload(chat, payload.session_token)}


# --- Message deletion (moderator/admin) ---

class DeleteMessageRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)


@router.delete("/chat/api/chats/{chat_id}/messages/{message_id}")
async def delete_chat_message(request: Request, chat_id: int, message_id: int, payload: DeleteMessageRequest) -> dict[str, object]:
    auth_service = _auth_service(request)
    try:
        session = auth_service.get_session(payload.session_token, client_kind=ClientKind.WEB)
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    if session.user.user_id is None:
        raise HTTPException(status_code=500, detail={"code": "invalid_user", "message": "Missing user id"})
    chat_service = _chat_service(request)
    is_privileged = session.user.role in {UserRole.ADMIN, UserRole.MODERATOR}
    if not is_privileged:
        author_id = chat_service.get_message_author(message_id)
        if author_id is None:
            raise HTTPException(status_code=404, detail={"code": "message_not_found", "message": "Message not found"})
        if author_id != session.user.user_id:
            raise HTTPException(status_code=403, detail={"code": "forbidden", "message": "You can delete only your own messages"})
    try:
        chat_service.delete_message(chat_id=chat_id, message_id=message_id, actor_user_id=session.user.user_id)
    except ChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    return {"status": "ok"}


# --- Add member to group ---

class AddMemberRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    user_id: int
    role: str | None = Field(default=None, max_length=16)


@router.post("/chat/api/chats/{chat_id}/members")
async def add_chat_member(request: Request, chat_id: int, payload: AddMemberRequest) -> dict[str, object]:
    user_id = _resolve_user_id(request, payload.session_token)
    chat_service = _chat_service(request)
    try:
        chat_service.add_member(
            chat_id=chat_id,
            target_user_id=payload.user_id,
            actor_user_id=user_id,
            role=_parse_member_role(payload.role),
        )
    except ChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    return {"status": "ok"}



class BulkAddMembersRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    add_all: bool = False


@router.post("/chat/api/chats/{chat_id}/members/bulk")
async def bulk_add_members(request: Request, chat_id: int, payload: BulkAddMembersRequest) -> dict[str, object]:
    user_id = _resolve_user_id(request, payload.session_token)
    from app.models import UserRole
    import sqlite3
    conn = sqlite3.connect(request.app.state.data_layer.database_path)
    conn.row_factory = sqlite3.Row
    actor = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
    if not actor or actor["role"] != "admin":
        conn.close()
        raise HTTPException(status_code=403, detail={"code": "admin_only", "message": "Only admin can add all users"})
    if not payload.add_all:
        conn.close()
        raise HTTPException(status_code=422, detail={"code": "add_all_required", "message": "Set add_all=true"})
    users = conn.execute("SELECT id FROM users WHERE status = 'active' AND role != 'guest' AND id != ?", (user_id,)).fetchall()
    conn.close()
    chat_service = _chat_service(request)
    added = 0
    for u in users:
        try:
            chat_service.add_member(chat_id=chat_id, target_user_id=u["id"], actor_user_id=user_id)
            added += 1
        except Exception:
            pass
    return {"status": "ok", "added_count": added}


# --- Chat profile: title, description, photo, members ---


class UpdateChatRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    title: str | None = Field(default=None, max_length=256)
    description: str | None = Field(default=None, max_length=2000)
    slow_mode_seconds: int | None = Field(default=None, ge=0, le=3600)
    history_visible: bool | None = None
    is_public: bool | None = None
    username: str | None = Field(default=None, max_length=64)


class ChatAvatarRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    image_base64: str = Field(min_length=1, max_length=4_000_000)
    image_mime_type: str | None = Field(default=None, max_length=64)


class ChatMemberActionRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)


class TransferChatOwnerRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    target_user_id: int


def _member_profile_payload(item: dict[str, object], session_token: str) -> dict[str, object]:
    payload = dict(item)
    if item.get("has_avatar"):
        payload["avatar_url"] = (
            f"/account/api/profile/avatar?session_token={session_token}"
            f"&user_id={item.get('user_id')}&v={item.get('avatar_updated_at_ms') or 0}"
        )
    else:
        payload["avatar_url"] = None
    return payload


@router.get("/chat/api/chats/{chat_id}")
async def get_chat(
    request: Request,
    chat_id: int,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, object]:
    user_id = _resolve_user_id(request, session_token)
    service = _chat_service(request)
    try:
        view = service.get_chat_view(chat_id=chat_id, requester_user_id=user_id)
    except ChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc

    chat = view.get("chat")
    payload = dict(view)
    payload["chat"] = _chat_payload(chat, session_token) if isinstance(chat, ChatRoom) else None
    return {"status": "ok", "chat": payload["chat"], "view": payload}


@router.patch("/chat/api/chats/{chat_id}")
async def update_chat(request: Request, chat_id: int, payload: UpdateChatRequest) -> dict[str, object]:
    user_id = _resolve_user_id(request, payload.session_token)
    service = _chat_service(request)
    try:
        chat = service.update_chat(
            chat_id=chat_id,
            actor_user_id=user_id,
            title=payload.title,
            description=payload.description,
            slow_mode_seconds=payload.slow_mode_seconds,
            history_visible=payload.history_visible,
            is_public=payload.is_public,
            username=payload.username,
        )
    except ChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    return {"status": "ok", "chat": _chat_payload(chat, payload.session_token)}


@router.post("/chat/api/chats/{chat_id}/avatar")
async def set_chat_avatar(request: Request, chat_id: int, payload: ChatAvatarRequest) -> dict[str, object]:
    user_id = _resolve_user_id(request, payload.session_token)
    service = _chat_service(request)
    try:
        avatar = decode_avatar_payload(
            image_base64=payload.image_base64,
            image_mime_type=payload.image_mime_type,
        )
    except AvatarPayloadError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc

    try:
        chat = service.set_chat_avatar(chat_id=chat_id, actor_user_id=user_id, avatar=avatar)
    except ChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    return {"status": "ok", "chat": _chat_payload(chat, payload.session_token)}


@router.post("/chat/api/chats/{chat_id}/avatar/remove")
async def clear_chat_avatar(
    request: Request,
    chat_id: int,
    payload: ChatMemberActionRequest,
) -> dict[str, object]:
    user_id = _resolve_user_id(request, payload.session_token)
    service = _chat_service(request)
    try:
        chat = service.clear_chat_avatar(chat_id=chat_id, actor_user_id=user_id)
    except ChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    return {"status": "ok", "chat": _chat_payload(chat, payload.session_token)}


@router.get("/chat/api/chats/{chat_id}/avatar")
async def get_chat_avatar(
    request: Request,
    chat_id: int,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> FileResponse:
    user_id = _resolve_user_id(request, session_token)
    service = _chat_service(request)
    try:
        file_path, mime_type = service.get_chat_avatar_file(
            chat_id=chat_id,
            requester_user_id=user_id,
        )
    except ChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    return FileResponse(path=str(file_path), media_type=mime_type)


@router.get("/chat/api/chats/{chat_id}/members")
async def list_chat_members(
    request: Request,
    chat_id: int,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, object]:
    user_id = _resolve_user_id(request, session_token)
    service = _chat_service(request)
    try:
        items = service.list_member_profiles(chat_id=chat_id, requester_user_id=user_id)
    except ChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    return {
        "status": "ok",
        "count": len(items),
        "items": [_member_profile_payload(item, session_token) for item in items],
    }


@router.get("/chat/api/chats/{chat_id}/online")
async def chat_online_members(
    request: Request,
    chat_id: int,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, object]:
    """Online members of one chat (presence comes from recent authenticated activity)."""
    user_id = _resolve_user_id(request, session_token)
    service = _chat_service(request)
    try:
        items = service.list_member_profiles(chat_id=chat_id, requester_user_id=user_id)
    except ChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    online_ids = [int(item["user_id"]) for item in items if presence.is_online(int(item["user_id"]))]
    return {"status": "ok", "count": len(online_ids), "user_ids": online_ids}


class PresencePingRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)


@router.post("/chat/api/presence/ping")
async def presence_ping(request: Request, payload: PresencePingRequest) -> dict[str, object]:
    """Lightweight heartbeat so idle-but-open clients stay 'online'."""
    user_id = _resolve_user_id(request, payload.session_token)
    presence.touch(user_id)
    return {"status": "ok", "user_id": user_id}


@router.delete("/chat/api/chats/{chat_id}/members/{user_id}")
async def remove_chat_member(
    request: Request,
    chat_id: int,
    user_id: int,
    payload: ChatMemberActionRequest,
) -> dict[str, object]:
    actor_id = _resolve_user_id(request, payload.session_token)
    service = _chat_service(request)
    try:
        service.remove_member(chat_id=chat_id, target_user_id=user_id, actor_user_id=actor_id)
    except ChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    return {"status": "ok"}


@router.post("/chat/api/chats/{chat_id}/leave")
async def leave_chat(
    request: Request,
    chat_id: int,
    payload: ChatMemberActionRequest,
) -> dict[str, object]:
    user_id = _resolve_user_id(request, payload.session_token)
    service = _chat_service(request)
    try:
        service.leave_chat(chat_id=chat_id, user_id=user_id)
    except ChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    return {"status": "ok"}


@router.delete("/chat/api/chats/{chat_id}")
async def delete_chat_room(
    request: Request,
    chat_id: int,
    payload: ChatMemberActionRequest,
) -> dict[str, object]:
    user_id = _resolve_user_id(request, payload.session_token)
    service = _chat_service(request)
    try:
        service.delete_chat_room(chat_id=chat_id, actor_user_id=user_id)
    except ChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    return {"status": "ok", "deleted_chat_id": chat_id}


@router.post("/chat/api/chats/{chat_id}/owner")
async def transfer_chat_owner(
    request: Request,
    chat_id: int,
    payload: TransferChatOwnerRequest,
) -> dict[str, object]:
    user_id = _resolve_user_id(request, payload.session_token)
    service = _chat_service(request)
    try:
        chat = service.transfer_owner(
            chat_id=chat_id,
            actor_user_id=user_id,
            target_user_id=payload.target_user_id,
        )
    except ChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    return {"status": "ok", "chat": _chat_payload(chat, payload.session_token)}


# --- Groups and channels: roles, permissions, invites, join requests, pin ---


class MemberRoleRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    role: str = Field(min_length=1, max_length=16)


class MemberPermissionsRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    permissions: dict[str, bool] = Field(default_factory=dict)


class InviteCreateRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    expires_in_hours: int | None = Field(default=None, ge=1, le=8760)
    max_uses: int | None = Field(default=None, ge=1, le=100000)
    requires_approval: bool = False


class JoinByCodeRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    code: str | None = Field(default=None, max_length=64)
    username: str | None = Field(default=None, max_length=64)
    chat_id: int | None = None


class JoinRequestDecision(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    approve: bool = True


class PinMessageRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    message_id: int | None = None


def _invite_payload(invite) -> dict[str, object]:
    return {
        "invite_id": invite.invite_id,
        "chat_id": invite.chat_id,
        "code": invite.code,
        "link": f"#/join/{invite.code}",
        "created_by": invite.created_by,
        "created_at_ms": invite.created_at_ms,
        "expires_at_ms": invite.expires_at_ms,
        "max_uses": invite.max_uses,
        "uses": invite.uses,
        "requires_approval": invite.requires_approval,
    }


@router.post("/chat/api/chats/{chat_id}/members/{user_id}/role")
async def set_chat_member_role(
    request: Request,
    chat_id: int,
    user_id: int,
    payload: MemberRoleRequest,
) -> dict[str, object]:
    actor_id = _resolve_user_id(request, payload.session_token)
    service = _chat_service(request)
    role = _parse_member_role(payload.role)
    try:
        member = service.set_member_role(
            chat_id=chat_id,
            target_user_id=user_id,
            actor_user_id=actor_id,
            role=role,
        )
    except ChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    return {"status": "ok", "member": {"chat_id": member.chat_id, "user_id": member.user_id, "role": member.role.value}}


@router.post("/chat/api/chats/{chat_id}/members/{user_id}/permissions")
async def set_chat_member_permissions(
    request: Request,
    chat_id: int,
    user_id: int,
    payload: MemberPermissionsRequest,
) -> dict[str, object]:
    actor_id = _resolve_user_id(request, payload.session_token)
    service = _chat_service(request)
    try:
        member = service.set_member_permissions(
            chat_id=chat_id,
            target_user_id=user_id,
            actor_user_id=actor_id,
            permissions=payload.permissions,
        )
    except ChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    return {"status": "ok", "member": {"chat_id": member.chat_id, "user_id": member.user_id, "role": member.role.value}}


@router.post("/chat/api/chats/{chat_id}/invites")
async def create_chat_invite(
    request: Request,
    chat_id: int,
    payload: InviteCreateRequest,
) -> dict[str, object]:
    actor_id = _resolve_user_id(request, payload.session_token)
    service = _chat_service(request)
    try:
        invite = service.create_invite(
            chat_id=chat_id,
            actor_user_id=actor_id,
            expires_in_hours=payload.expires_in_hours,
            max_uses=payload.max_uses,
            requires_approval=payload.requires_approval,
        )
    except ChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    return {"status": "ok", "invite": _invite_payload(invite)}


@router.get("/chat/api/chats/{chat_id}/invites")
async def list_chat_invites(
    request: Request,
    chat_id: int,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, object]:
    actor_id = _resolve_user_id(request, session_token)
    service = _chat_service(request)
    try:
        invites = service.list_invites(chat_id=chat_id, actor_user_id=actor_id)
    except ChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    return {"status": "ok", "count": len(invites), "items": [_invite_payload(item) for item in invites]}


@router.delete("/chat/api/chats/{chat_id}/invites/{invite_id}")
async def revoke_chat_invite(
    request: Request,
    chat_id: int,
    invite_id: int,
    payload: ChatMemberActionRequest,
) -> dict[str, object]:
    actor_id = _resolve_user_id(request, payload.session_token)
    service = _chat_service(request)
    try:
        service.revoke_invite(chat_id=chat_id, invite_id=invite_id, actor_user_id=actor_id)
    except ChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    return {"status": "ok"}


@router.post("/chat/api/join")
async def join_chat(request: Request, payload: JoinByCodeRequest) -> dict[str, object]:
    user_id = _resolve_user_id(request, payload.session_token)
    service = _chat_service(request)
    try:
        if payload.code:
            result = service.join_by_invite_code(code=payload.code, user_id=user_id)
        elif payload.username:
            result = service.join_public_chat(username=payload.username, user_id=user_id)
        elif payload.chat_id:
            result = service.join_public_chat(user_id=user_id, chat_id=payload.chat_id)
        else:
            raise ChatError("invite_not_found", "Provide an invite link or a public link name", 422)
    except ChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc

    chat = result.get("chat")
    return {
        "status": "ok",
        "join_status": result.get("status"),
        "already_member": bool(result.get("already_member")),
        "chat": _chat_payload(chat, payload.session_token) if isinstance(chat, ChatRoom) else None,
    }


@router.get("/chat/api/chats/{chat_id}/requests")
async def list_chat_join_requests(
    request: Request,
    chat_id: int,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, object]:
    actor_id = _resolve_user_id(request, session_token)
    service = _chat_service(request)
    try:
        items = service.list_join_requests(chat_id=chat_id, actor_user_id=actor_id)
    except ChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc

    payload_items = []
    for item in items:
        row = dict(item)
        if item.get("has_avatar"):
            row["avatar_url"] = (
                f"/account/api/profile/avatar?session_token={session_token}"
                f"&user_id={item.get('user_id')}&v={item.get('avatar_updated_at_ms') or 0}"
            )
        else:
            row["avatar_url"] = None
        payload_items.append(row)
    return {"status": "ok", "count": len(payload_items), "items": payload_items}


@router.post("/chat/api/chats/{chat_id}/requests/{user_id}")
async def decide_chat_join_request(
    request: Request,
    chat_id: int,
    user_id: int,
    payload: JoinRequestDecision,
) -> dict[str, object]:
    actor_id = _resolve_user_id(request, payload.session_token)
    service = _chat_service(request)
    try:
        result = service.decide_join_request(
            chat_id=chat_id,
            target_user_id=user_id,
            actor_user_id=actor_id,
            approve=payload.approve,
        )
    except ChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    return {"status": "ok", "request_status": result.status}


@router.post("/chat/api/chats/{chat_id}/pin")
async def pin_chat_message(
    request: Request,
    chat_id: int,
    payload: PinMessageRequest,
) -> dict[str, object]:
    actor_id = _resolve_user_id(request, payload.session_token)
    service = _chat_service(request)
    try:
        chat = service.set_pinned_message(
            chat_id=chat_id,
            actor_user_id=actor_id,
            message_id=payload.message_id,
        )
    except ChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    return {"status": "ok", "chat": _chat_payload(chat, payload.session_token)}


# --- P1: reactions, forwards, read state, drafts, per-chat state, search ---


class ReactionRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    emoji: str = Field(min_length=1, max_length=8)


class ForwardMessageRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    target_chat_id: int


class MarkReadRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    message_id: int


class DraftRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    text: str = Field(default="", max_length=4000)


class ChatUserStateRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    is_muted: bool | None = None
    is_archived: bool | None = None
    is_pinned: bool | None = None


@router.post("/chat/api/chats/{chat_id}/messages/{message_id}/reactions")
async def toggle_message_reaction(
    request: Request,
    chat_id: int,
    message_id: int,
    payload: ReactionRequest,
) -> dict[str, object]:
    user_id = _resolve_user_id(request, payload.session_token)
    service = _chat_service(request)
    try:
        message = service.toggle_reaction(
            chat_id=chat_id,
            message_id=message_id,
            user_id=user_id,
            emoji=payload.emoji,
        )
    except ChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    return {"status": "ok", "message": _message_payload(message)}


@router.post("/chat/api/chats/{chat_id}/messages/{message_id}/forward")
async def forward_chat_message(
    request: Request,
    chat_id: int,
    message_id: int,
    payload: ForwardMessageRequest,
) -> dict[str, object]:
    user_id = _resolve_user_id(request, payload.session_token)
    service = _chat_service(request)
    try:
        message = service.forward_message(
            source_chat_id=chat_id,
            message_id=message_id,
            target_chat_id=payload.target_chat_id,
            actor_user_id=user_id,
        )
    except ChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    return {"status": "ok", "message": _message_payload(message), "target_chat_id": payload.target_chat_id}


@router.post("/chat/api/chats/{chat_id}/read")
async def mark_chat_read(
    request: Request,
    chat_id: int,
    payload: MarkReadRequest,
) -> dict[str, object]:
    user_id = _resolve_user_id(request, payload.session_token)
    service = _chat_service(request)
    try:
        service.mark_read(chat_id=chat_id, user_id=user_id, message_id=payload.message_id)
    except ChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    return {"status": "ok"}


@router.post("/chat/api/chats/{chat_id}/draft")
async def save_chat_draft(
    request: Request,
    chat_id: int,
    payload: DraftRequest,
) -> dict[str, object]:
    user_id = _resolve_user_id(request, payload.session_token)
    service = _chat_service(request)
    try:
        service.save_draft(chat_id=chat_id, user_id=user_id, text=payload.text)
    except ChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    return {"status": "ok"}


@router.post("/chat/api/chats/{chat_id}/state")
async def set_chat_user_state(
    request: Request,
    chat_id: int,
    payload: ChatUserStateRequest,
) -> dict[str, object]:
    user_id = _resolve_user_id(request, payload.session_token)
    service = _chat_service(request)
    try:
        state = service.set_chat_user_state(
            chat_id=chat_id,
            user_id=user_id,
            is_muted=payload.is_muted,
            is_archived=payload.is_archived,
            is_pinned=payload.is_pinned,
        )
    except ChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    return {"status": "ok", "state": state}


@router.post("/chat/api/chats/{chat_id}/clear")
async def clear_chat_history_for_me(
    request: Request,
    chat_id: int,
    payload: ChatMemberActionRequest,
) -> dict[str, object]:
    user_id = _resolve_user_id(request, payload.session_token)
    service = _chat_service(request)
    try:
        service.clear_history_for_user(chat_id=chat_id, user_id=user_id)
    except ChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    return {"status": "ok"}


@router.get("/chat/api/messages/search")
async def search_chat_messages(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    q: str = Query(default="", max_length=256),
    chat_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, object]:
    user_id = _resolve_user_id(request, session_token)
    service = _chat_service(request)
    try:
        items = service.search_messages(user_id=user_id, query=q, chat_id=chat_id, limit=limit)
    except ChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    return {"status": "ok", "count": len(items), "items": items}


# --- P2: polls and user blocks ---


class PollCreateRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    question: str = Field(min_length=1, max_length=300)
    options: list[str] = Field(min_length=2, max_length=10)
    is_multiple: bool = False
    is_anonymous: bool = False


class PollVoteRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    option_index: int = Field(ge=0, le=9)


@router.post("/chat/api/chats/{chat_id}/polls")
async def create_chat_poll(
    request: Request,
    chat_id: int,
    payload: PollCreateRequest,
) -> dict[str, object]:
    user_id = _resolve_user_id(request, payload.session_token)
    service = _chat_service(request)
    try:
        message = service.create_poll(
            chat_id=chat_id,
            author_user_id=user_id,
            question=payload.question,
            options=tuple(payload.options),
            is_multiple=payload.is_multiple,
            is_anonymous=payload.is_anonymous,
        )
    except (ChatError, ValueError) as exc:
        if isinstance(exc, ChatError):
            raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
        raise HTTPException(status_code=422, detail={"code": "invalid_poll", "message": str(exc)}) from exc
    return {"status": "ok", "message": _message_payload(message)}


@router.post("/chat/api/chats/{chat_id}/polls/{poll_id}/vote")
async def vote_chat_poll(
    request: Request,
    chat_id: int,
    poll_id: int,
    payload: PollVoteRequest,
) -> dict[str, object]:
    user_id = _resolve_user_id(request, payload.session_token)
    service = _chat_service(request)
    try:
        message = service.vote_poll(
            chat_id=chat_id,
            poll_id=poll_id,
            user_id=user_id,
            option_index=payload.option_index,
        )
    except ChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    return {"status": "ok", "message": _message_payload(message)}


@router.get("/chat/api/blocks")
async def list_user_blocks(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, object]:
    user_id = _resolve_user_id(request, session_token)
    service = _chat_service(request)
    try:
        ids = service.list_blocked_user_ids(user_id=user_id)
    except ChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    return {"status": "ok", "count": len(ids), "user_ids": ids}


@router.post("/chat/api/blocks/{user_id}")
async def block_user(
    request: Request,
    user_id: int,
    payload: ChatMemberActionRequest,
) -> dict[str, object]:
    blocker_id = _resolve_user_id(request, payload.session_token)
    service = _chat_service(request)
    try:
        service.block_user(blocker_user_id=blocker_id, blocked_user_id=user_id)
    except ChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    return {"status": "ok", "blocked_user_id": user_id}


@router.delete("/chat/api/blocks/{user_id}")
async def unblock_user(
    request: Request,
    user_id: int,
    payload: ChatMemberActionRequest,
) -> dict[str, object]:
    blocker_id = _resolve_user_id(request, payload.session_token)
    service = _chat_service(request)
    try:
        service.unblock_user(blocker_user_id=blocker_id, blocked_user_id=user_id)
    except ChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    return {"status": "ok", "unblocked_user_id": user_id}


# --- Admin cleanup ---

class AdminCleanupRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)


class AdminFullResetRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    confirm: bool = Field(default=False)


class AdminDateRangeRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    from_date: str = Field(min_length=1, max_length=32)
    to_date: str = Field(min_length=1, max_length=32)


@router.delete("/chat/api/admin/chats/{chat_id}")
async def delete_chat(request: Request, chat_id: int, payload: AdminCleanupRequest) -> dict[str, object]:
    session = _require_admin(request, payload.session_token)
    chat_service = _chat_service(request)
    try:
        chat_service.delete_chat(chat_id=chat_id)
    except ChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    return {"status": "ok", "deleted_chat_id": chat_id}


@router.delete("/chat/api/admin/chats/{chat_id}/messages")
async def clear_chat_messages(request: Request, chat_id: int, payload: AdminCleanupRequest) -> dict[str, object]:
    session = _require_admin(request, payload.session_token)
    chat_service = _chat_service(request)
    try:
        count = chat_service.clear_chat_messages(chat_id=chat_id)
    except ChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    return {"status": "ok", "deleted_count": count}


@router.post("/chat/api/admin/chats/{chat_id}/messages/range")
async def clear_chat_messages_range(request: Request, chat_id: int, payload: AdminDateRangeRequest) -> dict[str, object]:
    session = _require_admin(request, payload.session_token)
    chat_service = _chat_service(request)
    try:
        from datetime import datetime
        fmt = "%Y-%m-%d"
        from_ms = int(datetime.strptime(payload.from_date, fmt).timestamp() * 1000)
        to_ms = int((datetime.strptime(payload.to_date, fmt).timestamp() + 86399) * 1000)
        count = chat_service.clear_chat_messages_range(chat_id=chat_id, from_ms=from_ms, to_ms=to_ms)
    except ValueError:
        raise HTTPException(status_code=422, detail={"code": "invalid_dates", "message": "Use format YYYY-MM-DD"})
    except ChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    return {"status": "ok", "deleted_count": count}


@router.post("/chat/api/admin/full-reset")
async def full_reset(request: Request, payload: AdminFullResetRequest) -> dict[str, object]:
    if not payload.confirm:
        raise HTTPException(status_code=400, detail={"code": "confirm_required", "message": "Set confirm=true"})
    session = _require_admin(request, payload.session_token)
    chat_service = _chat_service(request)
    try:
        stats = chat_service.full_reset(admin_user_id=session.user.user_id)
    except ChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    return {"status": "ok", **stats}


@router.get("/chat/api/admin/activity")
async def get_activity_log(request: Request, session_token: str = Query(..., min_length=8, max_length=512), limit: int = Query(default=100, ge=1, le=500)) -> dict[str, object]:
    _require_admin(request, session_token)
    log_service = ActivityLogService(db_path=request.app.state.data_layer.database_path)
    logs = log_service.get_logs(limit=limit)
    stats = log_service.stats()
    return {"status": "ok", "items": logs, "stats": stats}


@router.post("/chat/api/admin/clear-blog")
async def clear_blog(request: Request, payload: AdminCleanupRequest) -> dict[str, object]:
    _require_admin(request, payload.session_token)
    import sqlite3
    conn = sqlite3.connect(request.app.state.data_layer.database_path)
    count = conn.execute("DELETE FROM blog_posts").rowcount
    conn.commit()
    conn.close()
    return {"status": "ok", "deleted_count": count}


@router.post("/chat/api/admin/clear-support")
async def clear_support(request: Request, payload: AdminCleanupRequest) -> dict[str, object]:
    _require_admin(request, payload.session_token)
    import sqlite3
    conn = sqlite3.connect(request.app.state.data_layer.database_path)
    conn.execute("DELETE FROM support_messages")
    conn.execute("DELETE FROM support_tickets")
    count = conn.execute("SELECT total_changes()").fetchone()[0]
    conn.commit()
    conn.close()
    return {"status": "ok", "deleted_count": count}


def _require_admin(request: Request, session_token: str):
    from app.services.auth import AuthError
    auth_service = _auth_service(request)
    try:
        session = auth_service.get_session(session_token, client_kind=ClientKind.WEB)
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    if session.user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail={"code": "forbidden", "message": "Admin required"})
    return session


# --- Internet access activation ---

class ActivateInternetRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)


@router.post("/chat/api/internet/activate")
async def activate_internet(request: Request, payload: ActivateInternetRequest) -> dict[str, object]:
    user_id = _resolve_user_id(request, payload.session_token)

    import sqlite3
    conn = sqlite3.connect(request.app.state.data_layer.database_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT enabled FROM internet_access WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    if not row or not row["enabled"]:
        raise HTTPException(status_code=403, detail={"code": "internet_disabled", "message": "Internet access not granted by admin"})

    import socket
    try:
        s = socket.socket()
        s.settimeout(5)
        s.connect(("8.8.8.8", 53))
        s.close()
    except Exception:
        raise HTTPException(status_code=503, detail={"code": "no_internet", "message": "Server has no internet connection. Check uplink Wi-Fi."})

    return {"status": "ok", "message": "You can now browse the internet. Open a new tab."}


# --- Bulk operations ---

@router.post("/chat/api/admin/clear-global")
async def clear_global_chat(request: Request, payload: AdminCleanupRequest) -> dict[str, object]:
    session = _require_admin(request, payload.session_token)
    chat_service = _chat_service(request)
    try:
        count = chat_service.clear_global_chat()
    except ChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    return {"status": "ok", "deleted_count": count}


@router.post("/chat/api/admin/delete-all-chats")
async def delete_all_chats(request: Request, payload: AdminCleanupRequest) -> dict[str, object]:
    session = _require_admin(request, payload.session_token)
    chat_service = _chat_service(request)
    try:
        count = chat_service.delete_all_chats()
    except ChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    return {"status": "ok", "deleted_count": count}


@router.post("/chat/api/admin/delete-all-users")
async def delete_all_users(request: Request, payload: AdminCleanupRequest) -> dict[str, object]:
    session = _require_admin(request, payload.session_token)
    chat_service = _chat_service(request)
    try:
        count = chat_service.delete_all_users(admin_user_id=session.user.user_id)
    except ChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    return {"status": "ok", "deleted_count": count}

class EditMessageRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    body_text: str = Field(min_length=1, max_length=4000)

@router.put("/chat/api/chats/{chat_id}/messages/{message_id}")
async def edit_message(request: Request, chat_id: int, message_id: int, payload: EditMessageRequest):
    auth_service = _auth_service(request)
    try:
        session = auth_service.get_session(payload.session_token, client_kind=ClientKind.WEB)
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    if session.user.user_id is None:
        raise HTTPException(status_code=500, detail={"code": "invalid_user"})
    chat_service = _chat_service(request)
    try:
        msg = chat_service.edit_message(chat_id=chat_id, message_id=message_id, actor_user_id=session.user.user_id, body_text=payload.body_text)
    except ChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    return {"status": "ok", "message": {"message_id": msg.message_id, "body_text": msg.body_text, "edited_at_ms": msg.edited_at_ms}}
