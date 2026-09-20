from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.models import ClientKind, UserRole
from app.services.admin_users import AdminUsersError, AdminUsersService
from app.services.auth import AuthError, AuthService

router = APIRouter(tags=["moderation"])


class ResolveReportRequest(BaseModel):
    session_token: str = Field(min_length=8, max_length=512)
    report_id: int = Field(ge=1)
    action: str = Field(default="dismiss", max_length=16)


def _resolve_moderator(request: Request, session_token: str):
    service = AuthService(db_path=request.app.state.data_layer.database_path)
    try:
        session = service.get_session(session_token, client_kind=ClientKind.WEB)
    except AuthError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    if session.user.role not in {UserRole.ADMIN, UserRole.MODERATOR}:
        raise HTTPException(
            status_code=403,
            detail={"code": "forbidden", "message": "Admin or moderator required"},
        )
    if session.user.user_id is None:
        raise HTTPException(
            status_code=500,
            detail={"code": "invalid_user", "message": "Missing user id"},
        )
    return session


@router.get("/moderation/api/admin/reports")
async def get_reports(
    request: Request,
    session_token: str = Query(..., min_length=8, max_length=512),
    status: str | None = Query(default=None, max_length=32),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, object]:
    _resolve_moderator(request, session_token)
    mod = getattr(request.app.state, "auto_moderator", None)
    if mod is None:
        return {"status": "ok", "reports": [], "pending_count": 0, "total": 0}
    reports = mod.get_reports(status=status, limit=limit)
    pending = len(mod.get_reports(status="pending", limit=1000))
    return {
        "status": "ok",
        "reports": reports,
        "pending_count": pending,
        "total": len(reports),
    }


@router.post("/moderation/api/admin/reports/resolve")
async def resolve_report(
    request: Request,
    payload: ResolveReportRequest,
) -> dict[str, object]:
    session = _resolve_moderator(request, payload.session_token)
    action = payload.action.strip().lower()
    if action not in {"ban", "warn", "dismiss"}:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_action", "message": "action must be ban, warn or dismiss"},
        )
    mod = getattr(request.app.state, "auto_moderator", None)
    if mod is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "moderation_unavailable", "message": "Moderation is not running"},
        )
    report = mod.get_report(payload.report_id)
    if report is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "report_not_found", "message": "Report not found"},
        )

    if action == "ban":
        target_user_id = report.get("user_id")
        if not target_user_id:
            raise HTTPException(
                status_code=422,
                detail={"code": "report_without_user", "message": "Report has no author to ban"},
            )
        service = AdminUsersService(db_path=request.app.state.data_layer.database_path)
        try:
            service.ban_user(
                actor_user_id=session.user.user_id,
                target_user_id=int(target_user_id),
                reason=f"auto-moderation report #{payload.report_id}",
            )
        except AdminUsersError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail={"code": exc.code, "message": exc.message},
            ) from exc

    mod.resolve(payload.report_id, action, session.user.login)
    return {"status": "ok", "report_id": payload.report_id, "action": action}
