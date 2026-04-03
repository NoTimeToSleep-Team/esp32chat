from __future__ import annotations

import json
from pathlib import Path

from .models import HandheldVariant

_PROFILE_IDS = ("m5cardputer_client", "m5cardputer_adv")


def load_handheld_variants() -> dict[str, HandheldVariant]:
    profiles_root = Path(__file__).resolve().parents[2] / "profiles"
    variants: dict[str, HandheldVariant] = {}

    for profile_id in _PROFILE_IDS:
        profile_path = profiles_root / f"{profile_id}.json"
        payload = json.loads(profile_path.read_text(encoding="utf-8"))

        variants[profile_id] = HandheldVariant(
            profile_id=str(payload.get("profile_id", "")),
            display_name=str(payload.get("device_display_name", "")),
            firmware_path=str(payload.get("firmware_path", "")),
            category=str(payload.get("category", "")),
            autonomy_profile=str(payload.get("autonomy_profile", "")),
        )

    return variants
