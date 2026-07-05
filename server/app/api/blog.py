from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.models import BlogPost, BlogPostDraft, ClientKind
from app.services.auth import AuthError, AuthService
from app.services.blog import BlogError, BlogService


router = APIRouter(tags=["blog"])


class PublishPostRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    title: str = Field(min_length=1, max_length=256)
    body_text: str = Field(min_length=1, max_length=12000)


def _template_path() -> Path:
    return Path(__file__).resolve().parents[1] / "templates" / "blog" / "index.html"


def _auth_service(request: Request) -> AuthService:
    data_layer = request.app.state.data_layer
    return AuthService(db_path=data_layer.database_path)


def _blog_service(request: Request) -> BlogService:
    data_layer = request.app.state.data_layer
    return BlogService(db_path=data_layer.database_path)


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


def _post_payload(post: BlogPost) -> dict[str, object]:
    return {
        "post_id": post.post_id,
        "title": post.title,
        "body_text": post.body_text,
        "author_user_id": post.author_user_id,
        "published_at_ms": post.published_at_ms,
        "updated_at_ms": post.updated_at_ms,
    }


def _raise_blog_error(exc: BlogError) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail={
            "code": exc.code,
            "message": exc.message,
        },
    )


@router.get("/blog", response_class=HTMLResponse)
async def blog_page() -> HTMLResponse:
    template = _template_path()
    html = template.read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@router.get("/blog/api/posts")
async def list_blog_posts(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    user_id = _resolve_user_id(request, session_token)
    service = _blog_service(request)

    try:
        posts = service.list_posts(requester_user_id=user_id, limit=limit, offset=offset)
    except BlogError as exc:
        _raise_blog_error(exc)

    return {
        "status": "ok",
        "count": len(posts),
        "items": [_post_payload(post) for post in posts],
    }


@router.get("/blog/api/posts/{post_id}")
async def get_blog_post(
    request: Request,
    post_id: int,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, object]:
    user_id = _resolve_user_id(request, session_token)
    service = _blog_service(request)

    try:
        post = service.get_post(requester_user_id=user_id, post_id=post_id)
    except BlogError as exc:
        _raise_blog_error(exc)

    return {
        "status": "ok",
        "post": _post_payload(post),
    }


@router.post("/blog/api/posts")
async def publish_blog_post(request: Request, payload: PublishPostRequest) -> dict[str, object]:
    user_id = _resolve_user_id(request, payload.session_token)
    service = _blog_service(request)

    try:
        post = service.publish_post(
            author_user_id=user_id,
            draft=BlogPostDraft(title=payload.title, body_text=payload.body_text),
        )
    except (BlogError, ValueError) as exc:
        if isinstance(exc, BlogError):
            _raise_blog_error(exc)
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_post_payload",
                "message": str(exc),
            },
        )

    return {
        "status": "ok",
        "post": _post_payload(post),
    }
