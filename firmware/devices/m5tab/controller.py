from __future__ import annotations

from .config import M5TabConfig
from .models import InfoScreenData, ShellState
from .screens.admin_ops import AdminOpsGateway, M5TabAdminOpsController
from .screens.admin_users import AdminUsersGateway, M5TabAdminUsersController
from .server_api import TelemetryGateway
from .shell import M5TabShell


class M5TabController:
    def __init__(
        self,
        *,
        config: M5TabConfig,
        gateway: TelemetryGateway,
        shell: M5TabShell | None = None,
        admin_ops_controller: M5TabAdminOpsController | None = None,
        admin_users_controller: M5TabAdminUsersController | None = None,
    ) -> None:
        self._config = config
        self._gateway = gateway
        self._shell = shell or M5TabShell(gateway)
        self._admin_ops = admin_ops_controller or M5TabAdminOpsController(
            AdminOpsGateway(gateway.sender)
        )
        self._admin_users = admin_users_controller or M5TabAdminUsersController(
            AdminUsersGateway(gateway.sender)
        )

    @property
    def shell_state(self) -> ShellState:
        return self._shell.state

    @property
    def config(self) -> M5TabConfig:
        return self._config

    @property
    def admin_ops(self) -> M5TabAdminOpsController:
        return self._admin_ops

    @property
    def admin_users(self) -> M5TabAdminUsersController:
        return self._admin_users

    def start_shell(self, *, now_ms: int) -> ShellState:
        return self._shell.connect(now_ms=now_ms)

    def refresh_info(self, *, now_ms: int, session_token: str | None = None) -> InfoScreenData:
        return self._shell.load_info_screen(now_ms=now_ms, session_token=session_token)
