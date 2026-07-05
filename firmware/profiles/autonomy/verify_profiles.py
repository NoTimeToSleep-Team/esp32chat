from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REQUIRED_AUTONOMY_KEYS = (
    "autonomy_profile_id",
    "autonomy_class",
    "requires_persistent_storage",
    "offline_behavior",
    "sync_profile",
    "allowed_when_server_unreachable",
    "not_promised",
)


def main() -> None:
    project_root = Path(__file__).resolve().parents[3]
    profiles_dir = project_root / "firmware" / "profiles"
    autonomy_dir = profiles_dir / "autonomy"

    device_profiles = sorted(profiles_dir.glob("*.json"))
    if not device_profiles:
        raise RuntimeError("no device profiles found in firmware/profiles")

    referenced_autonomy_ids: set[str] = set()
    for profile_path in device_profiles:
        payload = _load_json(profile_path)
        autonomy_id = payload.get("autonomy_profile")
        if not isinstance(autonomy_id, str) or not autonomy_id.strip():
            raise RuntimeError(f"profile missing autonomy_profile: {profile_path}")
        referenced_autonomy_ids.add(autonomy_id.strip())

    loaded_autonomy: dict[str, dict[str, Any]] = {}
    for autonomy_id in sorted(referenced_autonomy_ids):
        autonomy_path = autonomy_dir / f"{autonomy_id}.json"
        if not autonomy_path.exists():
            raise RuntimeError(f"autonomy profile file is missing: {autonomy_path}")
        payload = _load_json(autonomy_path)
        _validate_autonomy_payload(payload=payload, path=autonomy_path)
        loaded_autonomy[autonomy_id] = payload

    print("DEVICE_PROFILE_COUNT", len(device_profiles))
    print("AUTONOMY_PROFILE_COUNT", len(loaded_autonomy))
    print("AUTONOMY_PROFILE_IDS", sorted(loaded_autonomy))


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON root must be object: {path}")
    return payload


def _validate_autonomy_payload(*, payload: dict[str, Any], path: Path) -> None:
    missing = [key for key in REQUIRED_AUTONOMY_KEYS if key not in payload]
    if missing:
        raise RuntimeError(f"autonomy profile missing keys {missing}: {path}")

    if not isinstance(payload["autonomy_profile_id"], str):
        raise RuntimeError(f"autonomy_profile_id must be string: {path}")
    if not isinstance(payload["autonomy_class"], str):
        raise RuntimeError(f"autonomy_class must be string: {path}")

    if not isinstance(payload["offline_behavior"], dict):
        raise RuntimeError(f"offline_behavior must be object: {path}")
    if not isinstance(payload["sync_profile"], dict):
        raise RuntimeError(f"sync_profile must be object: {path}")

    if not isinstance(payload["allowed_when_server_unreachable"], list):
        raise RuntimeError(f"allowed_when_server_unreachable must be array: {path}")
    if not isinstance(payload["not_promised"], list):
        raise RuntimeError(f"not_promised must be array: {path}")


if __name__ == "__main__":
    main()
