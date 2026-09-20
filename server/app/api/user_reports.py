from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.models import ClientKind, UserRole
from app.services.admin_users import AdminUsersError, AdminUsersService
from app.services.auth import AuthError, AuthService
from app.services.media import MediaService
from app.services.user_reports import (
    MAX_WARNS,
    WARN_BAN_MINUTES,
    UserReportsError,
    UserReportsService,
)

router = APIRouter(tags=["reports"])


class CreateReportRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    target_user_id: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=32)
    comment: str = Field(default="", max_length=1000)
    attachment_ids: list[int] = Field(default_factory=list, max_length=8)


class ResolveUserReportRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    report_id: int = Field(ge=1)
    action: str = Field(default="dismiss", max_length=16)


def _reports_service(request: Request) -> UserReportsService:
    return UserReportsService(db_path=request.app.state.data_layer.database_path)


def _media_service(request: Request) -> MediaService:
    data_layer = request.app.state.data_layer
    return MediaService(db_path=data_layer.database_path, storage_root=data_layer.storage_root)


def _attachment_payload(item) -> dict[str, object]:
    return {
        "attachment_id": item.attachment_id,
        "filename": item.original_filename,
        "mime_type": item.mime_type,
        "media_kind": item.media_kind.value,
        "size_bytes": item.size_bytes,
        "download_url": f"/media/api/attachments/{item.attachment_id}/download",
    }


def _session(request: Request, session_token: str, *, staff: bool):
    service = AuthService(db_path=request.app.state.data_layer.database_path)
    try:
        session = service.get_session(session_token, client_kind=ClientKind.WEB)
    except AuthError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    if session.user.user_id is None:
        raise HTTPException(
            status_code=500,
            detail={"code": "invalid_user", "message": "Authenticated user id is missing"},
        )
    if staff:
        if session.user.role not in {UserRole.ADMIN, UserRole.MODERATOR}:
            raise HTTPException(
                status_code=403,
                detail={"code": "forbidden", "message": "Admin or moderator required"},
            )
    elif session.user.role == UserRole.GUEST:
        raise HTTPException(
            status_code=403,
            detail={"code": "guests_cannot_report", "message": "Sign in to send reports"},
        )
    return session


@router.post("/reports/api/create")
async def create_report(request: Request, payload: CreateReportRequest) -> dict[str, object]:
    session = _session(request, payload.session_token, staff=False)
    try:
        report = _reports_service(request).create(
            reporter_user_id=int(session.user.user_id),
            reporter_login=session.user.login,
            target_user_id=payload.target_user_id,
            reason=payload.reason,
            comment=payload.comment,
            attachment_ids=tuple(payload.attachment_ids),
        )
    except UserReportsError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    return {"status": "ok", "report": report}


@router.get("/reports/api/list")
async def list_reports(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    status: str | None = Query(default=None, max_length=32),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, object]:
    _session(request, session_token, staff=True)
    service = _reports_service(request)
    reports = service.list_reports(status=status, limit=limit)
    target_ids = [r.get("target_user_id") for r in reports]
    warn_counts = service.warn_counts_for(target_ids)
    against_counts = service.reports_against_counts(target_ids)
    attachments = _media_service(request).attachments_for_reports(
        [int(r["id"]) for r in reports if r.get("id")]
    )
    for report in reports:
        target_id = report.get("target_user_id")
        report["target_warn_count"] = warn_counts.get(int(target_id), 0) if target_id else 0
        report["target_reports_count"] = against_counts.get(int(target_id), 0) if target_id else 0
        report["attachments"] = [
            _attachment_payload(item)
            for item in attachments.get(int(report["id"]), ())
        ]
    return {
        "status": "ok",
        "reports": reports,
        "pending_count": service.count_pending(),
        "total": len(reports),
    }


@router.get("/reports/api/my-status")
async def my_status(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
) -> dict[str, object]:
    session = _session(request, session_token, staff=False)
    return {"status": "ok", **_reports_service(request).my_status(int(session.user.user_id))}


@router.get("/reports/api/target-messages")
async def target_messages(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    target_user_id: int = Query(..., ge=1),
    limit: int = Query(default=10, ge=1, le=50),
) -> dict[str, object]:
    _session(request, session_token, staff=True)
    items = _reports_service(request).target_messages(target_user_id, limit=limit)
    return {"status": "ok", "items": items, "total": len(items)}


@router.post("/reports/api/resolve")
async def resolve_reports(
    request: Request,
    payload: ResolveUserReportRequest,
) -> dict[str, object]:
    session = _session(request, payload.session_token, staff=True)
    action = payload.action.strip().lower()
    if action not in {"ban", "warn", "dismiss"}:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_action", "message": "action must be ban, warn or dismiss"},
        )
    service = _reports_service(request)
    report = service.get(payload.report_id)
    if report is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "report_not_found", "message": "Report not found"},
        )
    if report["status"] != "pending":
        raise HTTPException(
            status_code=409,
            detail={"code": "already_resolved", "message": "Report has already been resolved"},
        )
    warn_info: dict[str, object] | None = None
    if action == "warn":
        target_user_id = int(report["target_user_id"])
        new_count = service.warn_user(
            user_id=target_user_id,
            report_id=payload.report_id,
            issued_by_login=session.user.login,
        )
        if new_count >= MAX_WARNS:
            try:
                record = AdminUsersService(
                    db_path=request.app.state.data_layer.database_path
                ).temporary_block_user(
                    actor_user_id=int(session.user.user_id),
                    target_user_id=target_user_id,
                    duration_minutes=WARN_BAN_MINUTES,
                    reason=f"{MAX_WARNS} warnings from user reports",
                )
            except AdminUsersError as exc:
                raise HTTPException(
                    status_code=exc.status_code,
                    detail={"code": exc.code, "message": exc.message},
                ) from exc
            service.reset_warnings(target_user_id)
            warn_info = {
                "warn_count": 0,
                "max_warns": MAX_WARNS,
                "banned": True,
                "blocked_until_ms": getattr(record, "blocked_until_ms", None),
            }
        else:
            warn_info = {
                "warn_count": new_count,
                "max_warns": MAX_WARNS,
                "banned": False,
                "blocked_until_ms": None,
            }
    if action == "ban":
        target_user_id = report.get("target_user_id")
        if not target_user_id:
            raise HTTPException(
                status_code=422,
                detail={"code": "report_without_target", "message": "Report has no target user"},
            )
        try:
            AdminUsersService(
                db_path=request.app.state.data_layer.database_path
            ).ban_user(
                actor_user_id=int(session.user.user_id),
                target_user_id=int(target_user_id),
                reason=f"user report #{payload.report_id}",
            )
        except AdminUsersError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail={"code": exc.code, "message": exc.message},
            ) from exc
    try:
        resolved = service.resolve(payload.report_id, action, session.user.login)
    except UserReportsError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    response: dict[str, object] = {
        "status": "ok",
        "report_id": payload.report_id,
        "action": action,
        "report": resolved,
    }
    if warn_info is not None:
        response["warn"] = warn_info
    return response
