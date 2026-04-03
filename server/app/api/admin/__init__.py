"""Admin API package."""

from app.api.admin.content import router as admin_content_router
from app.api.admin.mode import router as admin_mode_router
from app.api.admin.users import router as admin_users_router

__all__ = ["admin_content_router", "admin_mode_router", "admin_users_router"]
