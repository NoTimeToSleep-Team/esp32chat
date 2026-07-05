from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ApplicationStatus(str, Enum):
    PENDING = "pending"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True)
class ApplicationDraft:
    first_name: str
    last_name: str
    phone: str
    email: str
    class_group: str
    is_school_member: bool

    def __post_init__(self) -> None:
        if not self.first_name.strip():
            raise ValueError("first_name must not be empty")
        if not self.last_name.strip():
            raise ValueError("last_name must not be empty")
        if not self.phone.strip():
            raise ValueError("phone must not be empty")
        if not self.email.strip():
            raise ValueError("email must not be empty")
        if not self.class_group.strip():
            raise ValueError("class_group must not be empty")


@dataclass(frozen=True)
class ApplicationRecord:
    application_id: int
    first_name: str
    last_name: str
    phone: str
    email: str
    class_group: str
    is_school_member: bool
    status: ApplicationStatus
    review_note: str | None
    reviewed_by_user_id: int | None
    created_at_ms: int
    updated_at_ms: int
