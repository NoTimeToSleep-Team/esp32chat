from __future__ import annotations

import re
from dataclasses import dataclass


_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{1,62}[a-z0-9]$")


@dataclass(frozen=True)
class DeviceProfile:
    device_id: int
    slug: str
    title: str
    short_description: str
    firmware_archive_url: str | None
    install_guide: str
    pairing_guide: str
    combo_reset_guide: str
    is_published: bool
    created_by_user_id: int
    created_at_ms: int
    updated_at_ms: int
    published_at_ms: int | None


@dataclass(frozen=True)
class DeviceProfileView:
    profile: DeviceProfile
    has_device: bool


@dataclass(frozen=True)
class DeviceProfileDraft:
    slug: str
    title: str
    short_description: str
    install_guide: str
    pairing_guide: str
    combo_reset_guide: str
    firmware_archive_url: str | None = None

    def __post_init__(self) -> None:
        normalized_slug = self.slug.strip().lower()
        if not _SLUG_RE.fullmatch(normalized_slug):
            raise ValueError(
                "Device slug must be 3-64 chars of lowercase latin letters, digits and hyphen"
            )
        if not self.title.strip():
            raise ValueError("Device title must not be empty")
        if not self.short_description.strip():
            raise ValueError("Device short_description must not be empty")
        if not self.install_guide.strip():
            raise ValueError("Device install_guide must not be empty")
        if not self.pairing_guide.strip():
            raise ValueError("Device pairing_guide must not be empty")
        if not self.combo_reset_guide.strip():
            raise ValueError("Device combo_reset_guide must not be empty")


@dataclass(frozen=True)
class DeviceOwnership:
    user_id: int
    device_id: int
    has_device: bool
    updated_at_ms: int
