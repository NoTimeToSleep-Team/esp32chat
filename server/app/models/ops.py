from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class BackupStatus(str, Enum):
    DRY_RUN = "dry_run"
    COMPLETED = "completed"
    FAILED = "failed"


class IncidentLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class IncidentStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"


class ShutdownRunKind(str, Enum):
    DRY_RUN = "dry_run"
    EXECUTE = "execute"


class ShutdownRunStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class BackupRecord:
    backup_id: int
    backup_name: str
    backup_path: str
    status: BackupStatus
    reason: str | None
    trigger_kind: str
    actor_user_id: int | None
    created_at_ms: int
    completed_at_ms: int | None
    size_bytes: int | None
    checksum_sha256: str | None
    error_message: str | None


@dataclass(frozen=True)
class BackupRestorePlan:
    backup_name: str
    backup_path: str
    database_path: str
    backup_size_bytes: int
    dry_run: bool


@dataclass(frozen=True)
class IncidentRecord:
    incident_id: int
    incident_key: str
    level: IncidentLevel
    title: str
    details_json: str
    source: str | None
    status: IncidentStatus
    created_at_ms: int
    updated_at_ms: int
    resolved_at_ms: int | None
    created_by_user_id: int | None
    resolved_by_user_id: int | None
    resolution_note: str | None


@dataclass(frozen=True)
class RuntimeState:
    degraded_mode: bool
    reason: str | None
    updated_by_user_id: int | None
    updated_at_ms: int


@dataclass(frozen=True)
class ShutdownRunRecord:
    run_id: int
    run_kind: ShutdownRunKind
    requested_by_user_id: int | None
    reason: str | None
    status: ShutdownRunStatus
    started_at_ms: int
    finished_at_ms: int | None
    steps_json: str
