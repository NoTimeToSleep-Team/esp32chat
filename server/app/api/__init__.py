"""API routers package."""

from app.api.account import router as account_router
from app.api.admin.content import router as admin_content_router
from app.api.admin.mode import router as admin_mode_router
from app.api.admin.users import router as admin_users_router
from app.api.auth import router as auth_router
from app.api.applications import router as applications_router
from app.api.blog import router as blog_router
from app.api.chat import router as chat_router
from app.api.chat_private import router as chat_private_router
from app.api.devices import router as devices_router
from app.api.device_runtime import router as device_runtime_router
from app.api.health import router as health_router
from app.api.mode import router as mode_router
from app.api.ops import router as ops_router
from app.api.realtime import router as realtime_router
from app.api.rfid import router as rfid_router
from app.api.support import router as support_router

__all__ = [
    "account_router",
    "admin_content_router",
    "admin_mode_router",
    "admin_users_router",
    "applications_router",
    "auth_router",
    "blog_router",
    "chat_router",
    "chat_private_router",
    "devices_router",
    "device_runtime_router",
    "health_router",
    "mode_router",
    "ops_router",
    "realtime_router",
    "rfid_router",
    "support_router",
]
