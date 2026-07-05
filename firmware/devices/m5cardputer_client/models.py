from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ClientConnectionState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    AUTHENTICATED = "authenticated"
    DEGRADED = "degraded"


@dataclass(frozen=True)
class HandheldVariant:
    profile_id: str
    display_name: str
    firmware_path: str
    category: str
    autonomy_profile: str
