from contextlib import asynccontextmanager
from pathlib import Path
import sys
from time import monotonic

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.account import router as account_router
from app.api.admin.content import router as admin_content_router
from app.api.admin.mode import router as admin_mode_router
from app.api.admin.users import router as admin_users_router
from app.api.admin.network import router as admin_network_router
from app.api.auth import router as auth_router
from app.api.applications import router as applications_router
from app.api.blog import router as blog_router
from app.api.chat import router as chat_router
from app.api.chat_private import router as chat_private_router
from app.api.devices import router as devices_router
from app.api.device_combos import router as device_combos_router
from app.api.deployment import router as deployment_router
try:
    from app.api.discovery import router as discovery_router
except ImportError:
    discovery_router = None
try:
    from app.api.device_runtime import router as device_runtime_router
except ImportError:
    device_runtime_router = None
try:
    from app.api.edge_nodes import router as edge_nodes_router
except ImportError:
    edge_nodes_router = None
try:
    from app.api.module_control import router as module_control_router
except ImportError:
    module_control_router = None
try:
    from app.api.sync import router as sync_router
except ImportError:
    sync_router = None
try:
    from app.api.rfid import router as rfid_router
except ImportError:
    rfid_router = None
from app.api.health import router as health_router
from app.api.mode import router as mode_router
from app.api.media import router as media_router
from app.api.moderation import router as moderation_router
from app.api.ops import router as ops_router
from app.api.realtime import router as realtime_router
from app.api.support import router as support_router
from app.config import ConfigError, get_settings
from app.db import initialize_data_layer
from app.logging import configure_logging, get_logger
from app.realtime import ChatRealtimeBroker
from app.security import InMemoryRateLimiter, SecurityAuditService
from app.services.chat import ChatService
from app.services.module_registry import ModuleRegistryService
from app.services.auto_moderator import AutoModerator
from app.api.system_health import router as system_health_router


def _now_ms() -> int:
    return int(monotonic() * 1000)


def _resolve_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        first = forwarded_for.split(",", 1)[0].strip()
        if first:
            return first
    client = request.client
    if client and client.host:
        return client.host
    return "unknown"


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    try:
        settings = get_settings()
    except ConfigError as exc:
        raise RuntimeError(f"Configuration validation failed: {exc}") from exc

    configure_logging(settings)
    logger = get_logger("app.main")

    def _is_pn532_enabled(app: FastAPI) -> bool:
        data_layer = getattr(app.state, "data_layer", None)
        if data_layer is None:
            return False
        service = ModuleRegistryService(db_path=data_layer.database_path)
        return service.is_module_enabled("pn532")

    def _include_rfid_router_once(app: FastAPI) -> None:
        if getattr(app.state, "rfid_router_included", False):
            return
        app.include_router(rfid_router)
        app.state.rfid_router_included = True

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.started_at_monotonic = monotonic()
        app.state.data_layer = initialize_data_layer(settings, logger=logger)
        app.state.realtime_broker = ChatRealtimeBroker()
        app.state.rate_limiter = InMemoryRateLimiter(
            global_limit=settings.rate_limit_max_requests,
            global_window_ms=settings.rate_limit_window_ms,
            auth_limit=settings.auth_rate_limit_max_requests,
            auth_window_ms=settings.auth_rate_limit_window_ms,
        )
        app.state.security_audit = SecurityAuditService(
            db_path=app.state.data_layer.database_path
        )

        chat_service = ChatService(app.state.data_layer.database_path)
        default_chat = chat_service.ensure_default_common_chat()

        auto_moderator = AutoModerator(app.state.data_layer.database_path)
        auto_moderator.start()
        app.state.auto_moderator = auto_moderator

        if _is_pn532_enabled(app):
            _include_rfid_router_once(app)

        logger.info(
            "Application startup profile=%s host=%s port=%s default_common_chat_id=%s",
            settings.profile,
            settings.host,
            settings.port,
            default_chat.chat_id,
        )

        # Boot self-test
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
            from boot_selftest import run_boot_self_test
            boot_result = run_boot_self_test()
            logger.info("Boot self-test: %s", boot_result.summary())
            if not boot_result.is_healthy():
                logger.warning("Boot self-test issues: %s", boot_result.to_dict())
        except Exception as boot_err:
            logger.warning("Boot self-test skipped: %s", boot_err)

        try:
            yield
        finally:
            uptime_ms = int((monotonic() - app.state.started_at_monotonic) * 1000)
            logger.info(
                "Application shutdown profile=%s uptime_ms=%s",
                settings.profile,
                uptime_ms,
            )

    app = FastAPI(
        title="Local Chat Server",
        version="0.6.6",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.state.settings = settings
    app.state.rfid_router_included = False
    app.state.enable_rfid_router = lambda: _include_rfid_router_once(app)

    @app.middleware("http")
    async def body_size_limit_middleware(request: Request, call_next):
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            content_length = request.headers.get("content-length")
            if content_length and int(content_length) > 10 * 1024 * 1024:
                return JSONResponse({"detail": {"code": "payload_too_large", "message": "Max 10MB"}}, status_code=413)
        return await call_next(request)

    @app.middleware("http")
    async def rfid_gate_middleware(request: Request, call_next):
        path = request.url.path
        if path == "/rfid" or path.startswith("/rfid/"):
            if not _is_pn532_enabled(request.app):
                return JSONResponse(
                    status_code=404,
                    content={
                        "detail": {
                            "code": "rfid_disabled",
                            "message": "RFID module is disabled",
                        }
                    },
                )
        return await call_next(request)

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        path = request.url.path
        if InMemoryRateLimiter.is_exempt(path):
            return await call_next(request)

        limiter: InMemoryRateLimiter = request.app.state.rate_limiter
        decision = limiter.check(
            ip_address=_resolve_client_ip(request),
            path=path,
            now_ms=_now_ms(),
        )

        if not decision.allowed:
            audit: SecurityAuditService = request.app.state.security_audit
            ip_address = _resolve_client_ip(request)
            audit.log_event(
                "security.rate_limit_block",
                actor_kind="ip",
                actor_id=ip_address,
                details={
                    "path": path,
                    "method": request.method,
                    "bucket": decision.bucket,
                    "retry_after_ms": decision.retry_after_ms,
                    "limit": decision.limit,
                    "window_ms": decision.window_ms,
                },
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": {
                        "code": "rate_limited",
                        "message": "Too many requests",
                        "retry_after_ms": decision.retry_after_ms,
                    }
                },
            )

        return await call_next(request)

    static_dir = Path(__file__).resolve().parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    app.include_router(account_router)
    app.include_router(admin_content_router)
    app.include_router(admin_mode_router)
    app.include_router(admin_users_router)
    app.include_router(admin_network_router)
    app.include_router(auth_router)
    app.include_router(applications_router)
    app.include_router(blog_router)
    app.include_router(support_router)
    app.include_router(devices_router)
    app.include_router(device_combos_router)
    app.include_router(chat_router)
    app.include_router(chat_private_router)
    app.include_router(media_router)
    app.include_router(mode_router)
    app.include_router(ops_router)
    app.include_router(moderation_router)
    if device_runtime_router:
        app.include_router(device_runtime_router)
    if discovery_router:
        app.include_router(discovery_router)
    app.include_router(deployment_router)
    if edge_nodes_router:
        app.include_router(edge_nodes_router)
    if module_control_router:
        app.include_router(module_control_router)
    if sync_router:
        app.include_router(sync_router)
    if rfid_router:
        app.include_router(rfid_router)
    app.include_router(realtime_router)
    app.include_router(health_router)
    app.include_router(system_health_router)

    @app.get("/", tags=["meta"], response_class=HTMLResponse)
    async def root() -> HTMLResponse:
        template = Path(__file__).resolve().parent / "templates" / "index.html"
        return HTMLResponse(content=template.read_text(encoding="utf-8"))

    @app.get("/api/status", tags=["meta"])
    async def api_status() -> dict[str, str]:
        return {
            "service": "local-chat-server",
            "stage": "deploy",
            "status": "bootstrap",
            "profile": settings.profile,
        }

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger = get_logger(__name__)
        logger.error("Unhandled exception at %s: %s", request.url.path, exc, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": {"code": "internal_error", "message": "Internal server error"}},
        )


    # Captive portal proxy for WiFi login pages
    @app.post('/captive-proxy')
    async def captive_proxy(request: Request):
        try:
            import requests
        except ImportError:
            return JSONResponse(
                {'status': 'error', 'message': 'Proxy support unavailable (requests module missing)'},
                status_code=503,
            )
        target_url = None
        try:
            with open('/tmp/captive_info.txt') as f:
                for line in f:
                    if line.startswith('REDIR='):
                        target_url = line.split('=',1)[1].strip()
        except: pass
        if not target_url:
            return JSONResponse({'status': 'error', 'message': 'No captive portal'})
        form_data = await request.form()
        try:
            resp = requests.post(target_url, data=dict(form_data), allow_redirects=True, timeout=15)
        except Exception as exc:
            return JSONResponse({'status': 'error', 'message': f'Upstream request failed: {exc}'}, status_code=502)
        return HTMLResponse(content=resp.text, status_code=200)
    return app


app = create_app()
