"""Web surface boundary between chat administration and host control.

The application admin is a *chat* administrator.  Host, network, service and
hardware operations are intentionally not part of the web surface, even for an
admin session.  Those actions belong to a local operator (SSH/console), not to
a browser.

The prefix list is deliberately checked before routing.  Removing the routers
is the primary control; this middleware is the second line that keeps legacy
routes, re-mounted routers or future additions from becoming browser-reachable
by accident.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

# Paths that belong to the machine/network/hardware plane.
INFRASTRUCTURE_PREFIXES: tuple[str, ...] = (
    "/ops",
    "/admin/network",
    "/admin/system",
    "/admin/api/deployment",
    "/admin/api/modules",
    "/rfid",
    "/api/m5tab",
    "/devices/api/edge",
    "/system",
)


def is_infrastructure_path(path: str) -> bool:
    """Return True for paths that must never be exposed to web clients."""
    normalized = (path or "/").rstrip("/") or "/"
    for prefix in INFRASTRUCTURE_PREFIXES:
        if normalized == prefix or normalized.startswith(prefix + "/"):
            return True
    return False


async def infrastructure_boundary_middleware(request: Request, call_next):
    """Answer infrastructure paths with a generic 404 before authentication."""
    if is_infrastructure_path(request.url.path):
        return JSONResponse(
            status_code=404,
            content={"detail": {"code": "not_found", "message": "Not found"}},
        )
    return await call_next(request)
