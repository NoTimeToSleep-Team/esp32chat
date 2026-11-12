# PARTIAL RPi-Only: отслеживание RPi активно, строки ESP32/M5Stamp/Atom/PN532 — заглушки для ТЗ 3.4, не активны.
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from time import time
from typing import Iterable, Mapping

from app.models.module_registry import (
    ModuleCriticality,
    ModuleInfo,
    ModuleKind,
    ModuleStatus,
    ModuleTransport,
)
from app.db.connection import connect_sqlite


def _now_ms() -> int:
    return int(time() * 1000)


DEFAULT_MODULES: tuple[ModuleInfo, ...] = (
    ModuleInfo(
        id="raspberry-pi-host",
        slug="raspberry-pi",
        display_name="Raspberry Pi host",
        kind=ModuleKind.RASPBERRY_PI,
        transport=ModuleTransport.INTERNAL,
        criticality=ModuleCriticality.HARD_CRITICAL,
        status=ModuleStatus.OK,
        feature_flags={"server_core": True, "local_storage": True},
        notes="Host module is assumed present when the server is running.",
    ),
    ModuleInfo(
        id="pn532-i2c",
        slug="pn532",
        display_name="PN532 RFID reader",
        kind=ModuleKind.PN532,
        transport=ModuleTransport.I2C,
        criticality=ModuleCriticality.SOFT_CRITICAL,
        status=ModuleStatus.ABSENT,
        feature_flags={"rfid": False},
        notes="I2C detection placeholder; defaults to absent until explicitly enabled.",
    ),
    ModuleInfo(
        id="m5tab-hmi",
        slug="m5tab",
        display_name="M5Tab HMI",
        kind=ModuleKind.M5TAB,
        transport=ModuleTransport.WIFI,
        criticality=ModuleCriticality.OPTIONAL,
        status=ModuleStatus.ABSENT,
        feature_flags={"structured_hmi": False},
    ),
    ModuleInfo(
        id="esp32-s3-edge",
        slug="esp32-s3",
        display_name="ESP32-S3 edge node",
        kind=ModuleKind.ESP32_S3,
        transport=ModuleTransport.WIFI,
        criticality=ModuleCriticality.OPTIONAL,
        status=ModuleStatus.ABSENT,
        feature_flags={"edge_node": False},
    ),
    ModuleInfo(
        id="m5stamp-s3-edge",
        slug="m5stamp-s3",
        display_name="M5Stamp S3 edge node",
        kind=ModuleKind.M5STAMP_S3,
        transport=ModuleTransport.WIFI,
        criticality=ModuleCriticality.OPTIONAL,
        status=ModuleStatus.ABSENT,
        feature_flags={"edge_node": False},
    ),
    ModuleInfo(
        id="atom-s3-client",
        slug="atom-s3",
        display_name="Atom S3 client",
        kind=ModuleKind.ATOM_S3,
        transport=ModuleTransport.USB_SERIAL,
        criticality=ModuleCriticality.OPTIONAL,
        status=ModuleStatus.ABSENT,
        feature_flags={"device_client": False},
    ),
    ModuleInfo(
        id="external-clients",
        slug="external-clients",
        display_name="External clients",
        kind=ModuleKind.EXTERNAL_CLIENT,
        transport=ModuleTransport.WIFI,
        criticality=ModuleCriticality.OPTIONAL,
        status=ModuleStatus.ABSENT,
        feature_flags={"external_clients": False},
    ),
)


class ModuleRegistryService:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)

    def load_registry(self) -> list[ModuleInfo]:
        """Load module inventory, seeding conservative defaults when missing."""
        with self._connect() as connection:
            self._ensure_default_modules(connection)
            rows = connection.execute(
                """
                SELECT id, slug, display_name, kind, transport, criticality,
                       status, last_heartbeat_ms, feature_flags, notes
                FROM modules
                ORDER BY slug ASC
                """,
            ).fetchall()
            return [self._row_to_module(row) for row in rows]

    def get_module(self, module_slug: str) -> ModuleInfo | None:
        slug = module_slug.strip().lower()
        if not slug:
            return None

        with self._connect() as connection:
            self._ensure_default_modules(connection)
            row = connection.execute(
                """
                SELECT id, slug, display_name, kind, transport, criticality,
                       status, last_heartbeat_ms, feature_flags, notes
                FROM modules
                WHERE slug = ?
                """,
                (slug,),
            ).fetchone()
            if row is None:
                return None
            return self._row_to_module(row)

    def set_module_enabled(self, module_slug: str, *, enabled: bool) -> ModuleInfo:
        slug = module_slug.strip().lower()
        if not slug:
            raise ValueError("module_slug is required")

        with self._connect() as connection:
            self._ensure_default_modules(connection)
            row = connection.execute(
                """
                SELECT id, slug, display_name, kind, transport, criticality,
                       status, last_heartbeat_ms, feature_flags, notes
                FROM modules
                WHERE slug = ?
                """,
                (slug,),
            ).fetchone()
            if row is None:
                raise KeyError(slug)

            module = self._row_to_module(row)
            flags = dict(module.feature_flags)
            status = ModuleStatus.DETECTED if enabled else ModuleStatus.ABSENT
            now_ms = _now_ms() if enabled else None
            if module.kind == ModuleKind.PN532:
                flags["rfid"] = enabled

            connection.execute(
                """
                UPDATE modules
                SET status = ?, last_heartbeat_ms = ?, feature_flags = ?
                WHERE slug = ?
                """,
                (
                    status.value,
                    now_ms,
                    json.dumps(flags, ensure_ascii=False, separators=(",", ":")),
                    slug,
                ),
            )

            updated = connection.execute(
                """
                SELECT id, slug, display_name, kind, transport, criticality,
                       status, last_heartbeat_ms, feature_flags, notes
                FROM modules
                WHERE slug = ?
                """,
                (slug,),
            ).fetchone()
            return self._row_to_module(updated)

    def is_module_enabled(self, module_slug: str) -> bool:
        module = self.get_module(module_slug)
        if module is None:
            return False
        return module.status in {ModuleStatus.DETECTED, ModuleStatus.OK}

    def detect_modules(self) -> list[ModuleInfo]:
        """
        Return conservative read-only discovery state.

        Actual USB/I2C probing is intentionally not performed here. Operators or
        firmware profiles may mark optional modules detected/ok in the registry;
        everything else remains absent by default and the Raspberry Pi host is ok.
        """
        modules = self.load_registry()
        with self._connect() as connection:
            now_ms = _now_ms()
            for module in modules:
                connection.execute(
                    """
                    INSERT INTO module_detection_log(module_id, detection_method, detected_at_ms, details)
                    VALUES (?, 'placeholder_registry', ?, ?)
                    """,
                    (
                        module.id,
                        now_ms,
                        json.dumps(
                            {
                                "status": module.status.value,
                                "hardware_io": False,
                                "notes": "No USB/I2C probing in phase 2 placeholder discovery.",
                            },
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    ),
                )
        return modules

    def compute_capability_map(self) -> dict[str, bool | int]:
        modules = self.detect_modules()
        by_kind = self._modules_by_kind(modules)

        pn532_enabled = self._has_usable_module(by_kind, ModuleKind.PN532)
        m5tab_enabled = self._has_usable_module(by_kind, ModuleKind.M5TAB)
        atom_enabled = self._has_usable_module(by_kind, ModuleKind.ATOM_S3)
        external_clients_enabled = self._has_usable_module(by_kind, ModuleKind.EXTERNAL_CLIENT)
        edge_node_limit = self.recompute_edge_node_limit(modules)

        return {
            "server_core": self._has_usable_module(by_kind, ModuleKind.RASPBERRY_PI),
            "rfid": pn532_enabled,
            "pn532": pn532_enabled,
            "m5tab_hmi": m5tab_enabled,
            "structured_hmi": m5tab_enabled,
            "atom_s3_client": atom_enabled,
            "external_clients": external_clients_enabled,
            "edge_nodes": edge_node_limit > 0,
            "edge_node_limit": edge_node_limit,
        }

    def recompute_edge_node_limit(self, modules: Iterable[ModuleInfo] | None = None) -> int:
        current_modules = list(modules) if modules is not None else self.load_registry()
        count = sum(
            1
            for module in current_modules
            if module.kind in {ModuleKind.M5STAMP_S3, ModuleKind.ESP32_S3}
            and module.status in {ModuleStatus.DETECTED, ModuleStatus.DEGRADED, ModuleStatus.OK}
        )
        return max(0, min(4, count))

    def _connect(self) -> sqlite3.Connection:
        return connect_sqlite(self._db_path)

    @staticmethod
    def _ensure_default_modules(connection: sqlite3.Connection) -> None:
        for module in DEFAULT_MODULES:
            connection.execute(
                """
                INSERT INTO modules(
                    id, slug, display_name, kind, transport, criticality,
                    status, last_heartbeat_ms, feature_flags, notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO NOTHING
                """,
                (
                    module.id,
                    module.slug,
                    module.display_name,
                    module.kind.value,
                    module.transport.value,
                    module.criticality.value,
                    module.status.value,
                    module.last_heartbeat_ms,
                    json.dumps(module.feature_flags, ensure_ascii=False, separators=(",", ":")),
                    module.notes,
                ),
            )

    @staticmethod
    def _row_to_module(row: sqlite3.Row) -> ModuleInfo:
        return ModuleInfo(
            id=str(row["id"]),
            slug=str(row["slug"]),
            display_name=str(row["display_name"]),
            kind=ModuleKind(str(row["kind"])),
            transport=ModuleTransport(str(row["transport"])),
            criticality=ModuleCriticality(str(row["criticality"])),
            status=ModuleStatus(str(row["status"])),
            last_heartbeat_ms=(
                int(row["last_heartbeat_ms"])
                if row["last_heartbeat_ms"] is not None
                else None
            ),
            feature_flags=ModuleRegistryService._decode_feature_flags(row["feature_flags"]),
            notes=str(row["notes"]) if row["notes"] is not None else None,
        )

    @staticmethod
    def _decode_feature_flags(raw_flags: object) -> dict[str, object]:
        if raw_flags is None:
            return {}
        try:
            decoded = json.loads(str(raw_flags))
        except json.JSONDecodeError:
            return {}
        if isinstance(decoded, dict):
            return decoded
        return {}

    @staticmethod
    def _modules_by_kind(modules: Iterable[ModuleInfo]) -> dict[ModuleKind, list[ModuleInfo]]:
        result: dict[ModuleKind, list[ModuleInfo]] = {}
        for module in modules:
            result.setdefault(module.kind, []).append(module)
        return result

    @staticmethod
    def _has_usable_module(
        by_kind: Mapping[ModuleKind, list[ModuleInfo]],
        kind: ModuleKind,
    ) -> bool:
        return any(
            module.status in {ModuleStatus.DETECTED, ModuleStatus.OK}
            for module in by_kind.get(kind, [])
        )
