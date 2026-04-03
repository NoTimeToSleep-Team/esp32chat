from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.models import (
    ApplicationRecord,
    ApplicationStatus,
    BlogPost,
    BlogPostDraft,
    ClientKind,
    SupportMessage,
    SupportMessageDraft,
    SupportTicket,
    SupportTicketStatus,
    UserRole,
)
from app.services.applications import ApplicationError, ApplicationService
from app.services.auth import AuthError, AuthService
from app.services.blog import BlogError, BlogService
from app.services.support import SupportError, SupportService


router = APIRouter(prefix="/admin/content", tags=["admin-content"])


class UpdateApplicationStatusRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    status: ApplicationStatus
    review_note: str | None = Field(default=None, max_length=2048)


class SendSupportReplyRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    body_text: str = Field(min_length=1, max_length=8000)


class UpdateSupportStatusRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    status: SupportTicketStatus


class PublishAdminBlogPostRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    title: str = Field(min_length=1, max_length=256)
    body_text: str = Field(min_length=1, max_length=12000)


def _template_path() -> Path:
    return Path(__file__).resolve().parents[2] / "templates" / "admin" / "content" / "index.html"


def _auth_service(request: Request) -> AuthService:
    data_layer = request.app.state.data_layer
    return AuthService(db_path=data_layer.database_path)


def _application_service(request: Request) -> ApplicationService:
    data_layer = request.app.state.data_layer
    return ApplicationService(db_path=data_layer.database_path)


def _support_service(request: Request) -> SupportService:
    data_layer = request.app.state.data_layer
    return SupportService(db_path=data_layer.database_path)


def _blog_service(request: Request) -> BlogService:
    data_layer = request.app.state.data_layer
    return BlogService(db_path=data_layer.database_path)


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


def _application_payload(record: ApplicationRecord) -> dict[str, object]:
    return {
        "application_id": record.application_id,
        "first_name": record.first_name,
        "last_name": record.last_name,
        "phone": record.phone,
        "email": record.email,
        "class_group": record.class_group,
        "is_school_member": record.is_school_member,
        "status": record.status.value,
        "review_note": record.review_note,
        "reviewed_by_user_id": record.reviewed_by_user_id,
        "created_at_ms": record.created_at_ms,
        "updated_at_ms": record.updated_at_ms,
    }


def _support_ticket_payload(ticket: SupportTicket) -> dict[str, object]:
    return {
        "ticket_id": ticket.ticket_id,
        "user_id": ticket.user_id,
        "title": ticket.title,
        "status": ticket.status.value,
        "created_at_ms": ticket.created_at_ms,
        "updated_at_ms": ticket.updated_at_ms,
        "last_message_at_ms": ticket.last_message_at_ms,
    }


def _support_message_payload(message: SupportMessage) -> dict[str, object]:
    return {
        "message_id": message.message_id,
        "ticket_id": message.ticket_id,
        "author_user_id": message.author_user_id,
        "body_text": message.body_text,
        "created_at_ms": message.created_at_ms,
    }


def _blog_post_payload(post: BlogPost) -> dict[str, object]:
    return {
        "post_id": post.post_id,
        "title": post.title,
        "body_text": post.body_text,
        "author_user_id": post.author_user_id,
        "published_at_ms": post.published_at_ms,
        "updated_at_ms": post.updated_at_ms,
    }


def _raise_service_error(status_code: int, code: str, message: str) -> None:
    raise HTTPException(status_code=status_code, detail={"code": code, "message": message})


@router.get("/panel", response_class=HTMLResponse)
async def admin_content_panel() -> HTMLResponse:
    template = _template_path()
    html = template.read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@router.get("/applications")
async def list_admin_applications(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    status: ApplicationStatus | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    _resolve_admin_user_id(request, session_token)
    service = _application_service(request)

    records = service.list_queue(status=status, limit=limit, offset=offset)
    return {
        "status": "ok",
        "count": len(records),
        "items": [_application_payload(record) for record in records],
    }


@router.post("/applications/{application_id}/status")
async def update_admin_application_status(
    request: Request,
    application_id: int,
    payload: UpdateApplicationStatusRequest,
) -> dict[str, object]:
    admin_user_id = _resolve_admin_user_id(request, payload.session_token)
    service = _application_service(request)

    try:
        record = service.set_status(
            application_id=application_id,
            new_status=payload.status,
            reviewed_by_user_id=admin_user_id,
            review_note=payload.review_note,
        )
    except ApplicationError as exc:
        _raise_service_error(exc.status_code, exc.code, exc.message)

    return {"status": "ok", "application": _application_payload(record)}


@router.get("/support/tickets")
async def list_admin_support_tickets(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    status: SupportTicketStatus | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=300),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    admin_user_id = _resolve_admin_user_id(request, session_token)
    service = _support_service(request)

    try:
        tickets = service.list_tickets(
            requester_user_id=admin_user_id,
            status=status,
            limit=limit,
            offset=offset,
        )
    except SupportError as exc:
        _raise_service_error(exc.status_code, exc.code, exc.message)

    return {
        "status": "ok",
        "count": len(tickets),
        "items": [_support_ticket_payload(ticket) for ticket in tickets],
    }


@router.get("/support/tickets/{ticket_id}/messages")
async def list_admin_support_messages(
    request: Request,
    ticket_id: int,
    session_token: str = Query(..., min_length=8, max_length=512),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    admin_user_id = _resolve_admin_user_id(request, session_token)
    service = _support_service(request)

    try:
        messages = service.list_messages(
            ticket_id=ticket_id,
            requester_user_id=admin_user_id,
            limit=limit,
            offset=offset,
        )
    except SupportError as exc:
        _raise_service_error(exc.status_code, exc.code, exc.message)

    return {
        "status": "ok",
        "count": len(messages),
        "items": [_support_message_payload(message) for message in messages],
    }


@router.post("/support/tickets/{ticket_id}/reply")
async def reply_admin_support_ticket(
    request: Request,
    ticket_id: int,
    payload: SendSupportReplyRequest,
) -> dict[str, object]:
    admin_user_id = _resolve_admin_user_id(request, payload.session_token)
    service = _support_service(request)

    try:
        message = service.send_message(
            ticket_id=ticket_id,
            author_user_id=admin_user_id,
            draft=SupportMessageDraft(body_text=payload.body_text),
        )
    except (SupportError, ValueError) as exc:
        if isinstance(exc, SupportError):
            _raise_service_error(exc.status_code, exc.code, exc.message)
        _raise_service_error(422, "invalid_support_payload", str(exc))

    return {"status": "ok", "message": _support_message_payload(message)}


@router.post("/support/tickets/{ticket_id}/status")
async def update_admin_support_ticket_status(
    request: Request,
    ticket_id: int,
    payload: UpdateSupportStatusRequest,
) -> dict[str, object]:
    admin_user_id = _resolve_admin_user_id(request, payload.session_token)
    service = _support_service(request)

    try:
        ticket = service.set_ticket_status(
            ticket_id=ticket_id,
            actor_user_id=admin_user_id,
            status=payload.status,
        )
    except SupportError as exc:
        _raise_service_error(exc.status_code, exc.code, exc.message)

    return {"status": "ok", "ticket": _support_ticket_payload(ticket)}


@router.get("/blog/posts")
async def list_admin_blog_posts(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    admin_user_id = _resolve_admin_user_id(request, session_token)
    service = _blog_service(request)

    try:
        posts = service.list_posts(requester_user_id=admin_user_id, limit=limit, offset=offset)
    except BlogError as exc:
        _raise_service_error(exc.status_code, exc.code, exc.message)

    return {
        "status": "ok",
        "count": len(posts),
        "items": [_blog_post_payload(post) for post in posts],
    }


@router.post("/blog/posts")
async def publish_admin_blog_post(
    request: Request,
    payload: PublishAdminBlogPostRequest,
) -> dict[str, object]:
    admin_user_id = _resolve_admin_user_id(request, payload.session_token)
    service = _blog_service(request)

    try:
        post = service.publish_post(
            author_user_id=admin_user_id,
            draft=BlogPostDraft(title=payload.title, body_text=payload.body_text),
        )
    except (BlogError, ValueError) as exc:
        if isinstance(exc, BlogError):
            _raise_service_error(exc.status_code, exc.code, exc.message)
        _raise_service_error(422, "invalid_post_payload", str(exc))

    return {"status": "ok", "post": _blog_post_payload(post)}
