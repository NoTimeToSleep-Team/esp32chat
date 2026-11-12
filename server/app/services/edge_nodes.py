# DEPRECATED RPi-Only: edge node deployment requires ESP32-S3/M5Stamp S3 internal controllers.
# Код сохранён для полноты ТЗ 3.4, но не активен в RPi-only архитектуре.
from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from time import time
from typing import Any

from app.models import ModuleInfo, ModuleKind, ModuleStatus, UserRole, UserStatus
from app.services.module_registry import ModuleRegistryService
from app.db.connection import connect_sqlite


ACTIVE_EDGE_STATUSES = {"requested", "provisioning", "active", "degraded"}
EDGE_MODULE_KINDS = {ModuleKind.M5STAMP_S3, ModuleKind.ESP32_S3}
USABLE_MODULE_STATUSES = {ModuleStatus.DETECTED, ModuleStatus.DEGRADED, ModuleStatus.OK}


def _now_ms() -> int:
    return int(time() * 1000)


@dataclass(frozen=True)
class EdgeNodeError(RuntimeError):
    code: str
    message: str
    status_code: int

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True)
class EdgeNodeDeployment:
    deployment_id: int
    module_id: str
    network_ssid: str
    network_password_hash: str
    status: str
    local_profile: dict[str, Any]
    local_ip: str | None
    mdns_name: str | None
    created_at_ms: int
    updated_at_ms: int
    deployed_by_admin_user_id: int


class EdgeNodeService:
    """M5Tab edge-node deployment records; no hardware I/O in phase 1."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._registry = ModuleRegistryService(self._db_path)

    def deploy_node(
        self,
        admin_user_id: int,
        module_id: str,
        ssid: str,
        password: str,
        profile_options: dict[str, Any] | None,
    ) -> int:
        normalized_module_id = module_id.strip()
        normalized_ssid = ssid.strip()
        if not normalized_module_id:
            raise EdgeNodeError("invalid_module_id", "module_id is required", 422)
        if not normalized_ssid:
            raise EdgeNodeError("invalid_ssid", "ssid is required", 422)
        if not password:
            raise EdgeNodeError("invalid_password", "password is required", 422)

        modules = self._registry.load_registry()
        module = self._resolve_edge_module(modules, normalized_module_id)
        edge_limit = self._registry.recompute_edge_node_limit(modules)

        with self._connect() as connection:
            self._ensure_schema(connection)
            self._require_active_admin(connection, admin_user_id)
            active_count = self._active_deployment_count(connection)
            if active_count >= edge_limit:
                raise EdgeNodeError(
                    "edge_node_limit_reached",
                    "No available detected M5Stamp S3/ESP32-S3 edge capacity",
                    409,
                )
            existing = connection.execute(
                """
                SELECT id FROM edge_node_deployments
                WHERE module_id = ? AND status IN ('requested', 'provisioning', 'active', 'degraded')
                LIMIT 1
                """,
                (module.id,),
            ).fetchone()
            if existing is not None:
                raise EdgeNodeError(
                    "module_already_deployed",
                    "Selected module already has an active deployment",
                    409,
                )

            now_ms = _now_ms()
            profile = dict(profile_options or {})
            profile.setdefault("hardware_io", False)
            profile.setdefault("encryption_note", "SSID obfuscation is a placeholder for proper encryption/vault storage.")
            mdns_name = str(profile.get("mdns_name") or profile.get("mDNS_name") or f"edge-{module.slug}.local")
            cursor = connection.execute(
                """
                INSERT INTO edge_node_deployments(
                    module_id, network_ssid, network_password_hash, status,
                    local_profile, local_ip, mDNS_name, created_at_ms,
                    updated_at_ms, deployed_by_admin_user_id
                )
                VALUES (?, ?, ?, 'requested', ?, ?, ?, ?, ?, ?)
                """,
                (
                    module.id,
                    self._obfuscate_ssid(normalized_ssid),
                    self._hash_password(password),
                    json.dumps(profile, ensure_ascii=False, separators=(",", ":")),
                    profile.get("local_ip"),
                    mdns_name,
                    now_ms,
                    now_ms,
                    admin_user_id,
                ),
            )
            return int(cursor.lastrowid)

    def stop_node(self, deployment_id: int) -> EdgeNodeDeployment:
        with self._connect() as connection:
            self._ensure_schema(connection)
            row = connection.execute(
                "SELECT * FROM edge_node_deployments WHERE id = ?",
                (deployment_id,),
            ).fetchone()
            if row is None:
                raise EdgeNodeError("deployment_not_found", "Deployment was not found", 404)
            now_ms = _now_ms()
            connection.execute(
                "UPDATE edge_node_deployments SET status = 'stopped', updated_at_ms = ? WHERE id = ?",
                (now_ms, deployment_id),
            )
            updated = connection.execute(
                "SELECT * FROM edge_node_deployments WHERE id = ?",
                (deployment_id,),
            ).fetchone()
            return self._row_to_deployment(updated)

    def list_deployments(self) -> list[EdgeNodeDeployment]:
        with self._connect() as connection:
            self._ensure_schema(connection)
            rows = connection.execute(
                """
                SELECT * FROM edge_node_deployments
                ORDER BY updated_at_ms DESC, id DESC
                """,
            ).fetchall()
            return [self._row_to_deployment(row) for row in rows]

    def get_deployment(self, deployment_id: int) -> EdgeNodeDeployment:
        with self._connect() as connection:
            self._ensure_schema(connection)
            row = connection.execute(
                "SELECT * FROM edge_node_deployments WHERE id = ?",
                (deployment_id,),
            ).fetchone()
            if row is None:
                raise EdgeNodeError("deployment_not_found", "Deployment was not found", 404)
            return self._row_to_deployment(row)

    def active_deployment_count(self) -> int:
        with self._connect() as connection:
            self._ensure_schema(connection)
            return self._active_deployment_count(connection)

    def _connect(self) -> sqlite3.Connection:
        return connect_sqlite(self._db_path)

    @staticmethod
    def _ensure_schema(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS edge_node_deployments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                module_id TEXT NOT NULL,
                network_ssid TEXT NOT NULL,
                network_password_hash TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('requested','provisioning','active','degraded','stopped')),
                local_profile TEXT NOT NULL DEFAULT '{}',
                local_ip TEXT,
                mDNS_name TEXT,
                created_at_ms INTEGER NOT NULL,
                updated_at_ms INTEGER NOT NULL,
                deployed_by_admin_user_id INTEGER NOT NULL,
                FOREIGN KEY (module_id) REFERENCES modules(id) ON DELETE RESTRICT,
                FOREIGN KEY (deployed_by_admin_user_id) REFERENCES users(id) ON DELETE RESTRICT
            )
            """,
        )

    @staticmethod
    def _require_active_admin(connection: sqlite3.Connection, admin_user_id: int) -> None:
        row = connection.execute(
            "SELECT id, role, status FROM users WHERE id = ?",
            (admin_user_id,),
        ).fetchone()
        if row is None:
            raise EdgeNodeError("admin_not_found", "Admin user was not found", 404)
        if str(row["role"]) != UserRole.ADMIN.value or str(row["status"]) != UserStatus.ACTIVE.value:
            raise EdgeNodeError("admin_only", "Admin role is required", 403)

    @staticmethod
    def _active_deployment_count(connection: sqlite3.Connection) -> int:
        row = connection.execute(
            """
            SELECT COUNT(*) AS total FROM edge_node_deployments
            WHERE status IN ('requested', 'provisioning', 'active', 'degraded')
            """,
        ).fetchone()
        return int(row["total"] if row is not None else 0)

    @staticmethod
    def _resolve_edge_module(modules: list[ModuleInfo], requested: str) -> ModuleInfo:
        requested_lower = requested.lower()
        for module in modules:
            if module.id.lower() == requested_lower or module.slug.lower() == requested_lower:
                if module.kind not in EDGE_MODULE_KINDS:
                    raise EdgeNodeError("not_edge_module", "Module is not an edge-node capable Stamp S3/ESP32-S3", 422)
                if module.status not in USABLE_MODULE_STATUSES:
                    raise EdgeNodeError("module_not_detected", "Module is not detected in registry", 409)
                return module
        raise EdgeNodeError("module_not_found", "Module was not found", 404)

    @staticmethod
    def _obfuscate_ssid(ssid: str) -> str:
        # Placeholder only: prevents plaintext DB storage until proper encryption/vault integration lands.
        return "obf:v1:" + base64.urlsafe_b64encode(ssid.encode("utf-8")).decode("ascii")

    @staticmethod
    def _hash_password(password: str) -> str:
        return "sha256:v1:" + hashlib.sha256(password.encode("utf-8")).hexdigest()

    @staticmethod
    def _row_to_deployment(row: sqlite3.Row) -> EdgeNodeDeployment:
        try:
            profile = json.loads(str(row["local_profile"] or "{}"))
        except json.JSONDecodeError:
            profile = {}
        if not isinstance(profile, dict):
            profile = {}
        return EdgeNodeDeployment(
            deployment_id=int(row["id"]),
            module_id=str(row["module_id"]),
            network_ssid=str(row["network_ssid"]),
            network_password_hash=str(row["network_password_hash"]),
            status=str(row["status"]),
            local_profile=profile,
            local_ip=str(row["local_ip"]) if row["local_ip"] is not None else None,
            mdns_name=str(row["mDNS_name"]) if row["mDNS_name"] is not None else None,
            created_at_ms=int(row["created_at_ms"]),
            updated_at_ms=int(row["updated_at_ms"]),
            deployed_by_admin_user_id=int(row["deployed_by_admin_user_id"]),
        )
