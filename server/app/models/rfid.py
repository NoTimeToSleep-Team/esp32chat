# DEPRECATED in RPi-Only architecture (v1.00.00). Code kept for reference.
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.models.user import AccessMode


class RfidEventAction(str, Enum):
    CARD_ENROLL = "card_enroll"
    CARD_TOGGLE_ACTIVE = "card_toggle_active"
    CARD_DELETE = "card_delete"
    CARD_VERIFY = "card_verify"
    MODE_SWITCH = "mode_switch"


@dataclass(frozen=True)
class RfidCard:
    card_id: int
    uid_mask: str
    card_label: str
    note: str | None
    is_active: bool
    created_by_user_id: int
    created_at_ms: int
    updated_at_ms: int
    last_used_at_ms: int | None


@dataclass(frozen=True)
class RfidCardDraft:
    card_uid: str
    card_label: str
    note: str | None = None

    def __post_init__(self) -> None:
        if not self.card_uid.strip():
            raise ValueError("RFID card UID must not be empty")
        if not self.card_label.strip():
            raise ValueError("RFID card label must not be empty")


@dataclass(frozen=True)
class RfidAccessEvent:
    event_id: int
    card_id: int | None
    uid_mask: str | None
    action: RfidEventAction
    granted: bool
    requested_mode: AccessMode | None
    resolved_mode: AccessMode | None
    reason: str | None
    source: str | None
    actor_user_id: int | None
    created_at_ms: int


@dataclass(frozen=True)
class RfidModeDecision:
    granted: bool
    access_mode: AccessMode
    card_id: int | None
    card_label: str | None
    uid_mask: str | None
    reason: str | None
