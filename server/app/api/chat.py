from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.models import ChatDraft, ChatMessage, ChatRoom, ClientKind, MessageDraft, UserRole
from app.realtime import chat_message_event, chat_message_payload
from app.services.activity_log import ActivityLogService
from app.services.auth import AuthError, AuthService
from app.services.chat import ChatError, ChatService


router = APIRouter(tags=["chat"])


class SendMessageRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    body_text: str = Field(min_length=0, max_length=4000)
    client_message_id: str | None = Field(default=None, max_length=128)
    attachment_ids: list[int] = Field(default_factory=list, max_length=8)


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
                attachment_ids=tuple(payload.attachment_ids),
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
    _resolve_user_id(request, session_token)
    chat_service = _chat_service(request)
    results = chat_service.search_users(q)
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
    return {"status": "ok", "chat": _chat_payload(chat)}


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


@router.post("/chat/api/chats/{chat_id}/members")
async def add_chat_member(request: Request, chat_id: int, payload: AddMemberRequest) -> dict[str, object]:
    user_id = _resolve_user_id(request, payload.session_token)
    chat_service = _chat_service(request)
    try:
        chat_service.add_member(chat_id=chat_id, target_user_id=payload.user_id, actor_user_id=user_id)
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
    users = conn.execute("SELECT id FROM users WHERE status = 'active' AND id != ?", (user_id,)).fetchall()
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
