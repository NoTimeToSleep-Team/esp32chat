from __future__ import annotations

from enum import Enum


class QueueEventState(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    ACKED = "acked"
    DUPLICATE = "duplicate"
    REJECTED = "rejected"
