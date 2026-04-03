from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

from .command_map import M5CARDPUTER_HANDHELD_COMMANDS, command_path_set
from .profile_variants import load_handheld_variants


def main() -> None:
    project_root = Path(__file__).resolve().parents[3]
    server_root = project_root / "server"

    db_name = f"local_chat_m5cardputer_profile_align_{uuid.uuid4().hex}.db"
    os.environ["LCS_PROFILE"] = "test"
    os.environ["LCS_DATABASE_URL"] = f"sqlite:///data/sqlite/{db_name}"
    os.environ["LCS_STORAGE_ROOT"] = "data"
    os.environ["LCS_RELOAD"] = "false"

    if str(server_root) not in sys.path:
        sys.path.insert(0, str(server_root))

    from app.config import get_settings  # type: ignore
    from app.main import create_app  # type: ignore

    get_settings(refresh=True)
    app = create_app()

    route_map: dict[str, set[str]] = {}
    for route in app.routes:
        methods = {item.upper() for item in getattr(route, "methods", set())}
        existing = route_map.get(route.path)
        if existing is None:
            existing = set()
            route_map[route.path] = existing
        existing.update(methods)

    _verify_command_map(route_map)
    _verify_profiles(project_root)

    variants = load_handheld_variants()
    print("HANDHELD_COMMAND_COUNT", len(M5CARDPUTER_HANDHELD_COMMANDS))
    print("HANDHELD_COMMAND_PATHS", sorted(command_path_set()))
    print("VARIANT_IDS", sorted(variants.keys()))
    print("CLIENT_FIRMWARE_PATH", variants["m5cardputer_client"].firmware_path)
    print("ADV_FIRMWARE_PATH", variants["m5cardputer_adv"].firmware_path)


def _verify_command_map(route_map: dict[str, set[str]]) -> None:
    for command in M5CARDPUTER_HANDHELD_COMMANDS:
        methods = route_map.get(command.path_template)
        if methods is None:
            raise RuntimeError(f"missing server route for command: {command.path_template}")
        if command.method.upper() not in methods:
            raise RuntimeError(
                f"method mismatch for route {command.path_template}: expected {command.method}, actual {sorted(methods)}"
            )

    if "/auth/guest" in command_path_set():
        raise RuntimeError("handheld command map must not include guest login path")


def _verify_profiles(project_root: Path) -> None:
    profiles_root = project_root / "firmware" / "profiles"
    client_payload = _read_profile(profiles_root / "m5cardputer_client.json")
    adv_payload = _read_profile(profiles_root / "m5cardputer_adv.json")

    if client_payload.get("firmware_path") != "devices/m5cardputer_client":
        raise RuntimeError("m5cardputer_client firmware_path must stay devices/m5cardputer_client")
    if adv_payload.get("firmware_path") != "devices/m5cardputer_client":
        raise RuntimeError("m5cardputer_adv firmware_path must stay devices/m5cardputer_client")

    if bool(client_payload.get("supports_guest_login")):
        raise RuntimeError("m5cardputer_client must keep supports_guest_login=false")
    if bool(adv_payload.get("supports_guest_login")):
        raise RuntimeError("m5cardputer_adv must keep supports_guest_login=false")

    client_caps = client_payload.get("capabilities")
    adv_caps = adv_payload.get("capabilities")
    if not isinstance(client_caps, dict) or not isinstance(adv_caps, dict):
        raise RuntimeError("m5cardputer profile capabilities must be objects")

    keys = {
        "chat",
        "blog",
        "admin_panel",
        "rfid_management",
        "device_action_sequence_login",
        "media_files",
    }
    for key in keys:
        if client_caps.get(key) != adv_caps.get(key):
            raise RuntimeError(f"capability mismatch between client/adv for key: {key}")

    client_constraints = _string_set(client_payload.get("constraints"))
    adv_constraints = _string_set(adv_payload.get("constraints"))
    if "shared_codebase_with_m5cardputer_adv" not in client_constraints:
        raise RuntimeError("client constraints must declare shared codebase with adv")
    if "shares_codebase_with_m5cardputer_client_until_hardware_delta_is_proven" not in adv_constraints:
        raise RuntimeError("adv constraints must declare shared codebase with client")

    if client_payload.get("status") != "mvp_v0_11_02":
        raise RuntimeError("m5cardputer_client profile status must be mvp_v0_11_02")
    if adv_payload.get("status") != "mvp_v0_11_02":
        raise RuntimeError("m5cardputer_adv profile status must be mvp_v0_11_02")


def _read_profile(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"profile payload must be object: {path}")
    return payload


def _string_set(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    result: set[str] = set()
    for item in value:
        if isinstance(item, str):
            result.add(item)
    return result


if __name__ == "__main__":
    main()
