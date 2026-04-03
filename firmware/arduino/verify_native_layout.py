from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def main() -> None:
    project_root = Path(__file__).resolve().parents[2]
    profiles_dir = project_root / "firmware" / "profiles"
    profile_paths = sorted(profiles_dir.glob("*.json"))
    if not profile_paths:
        raise RuntimeError("no firmware profiles found")

    checked = 0
    harness_checked = 0
    for path in profile_paths:
        payload = _load_profile(path)
        profile_id = _required_str(payload, "profile_id", path)
        firmware_path = _required_str(payload, "firmware_path", path)
        entry = _required_str(payload, "native_runtime_entry", path)
        runtime_path = project_root / "firmware" / entry
        if not runtime_path.exists():
            raise RuntimeError(f"native runtime entry missing for {profile_id}: {runtime_path}")

        harness_entries = payload.get("host_harness_entries")
        if not isinstance(harness_entries, list) or not harness_entries:
            raise RuntimeError(f"host_harness_entries must be non-empty array for {profile_id}: {path}")
        for harness_entry in harness_entries:
            if not isinstance(harness_entry, str) or not harness_entry.strip():
                raise RuntimeError(
                    f"host_harness_entries must contain non-empty strings for {profile_id}: {path}"
                )
            harness_value = harness_entry.strip()
            harness_path = project_root / "firmware" / harness_value
            if not harness_path.exists():
                raise RuntimeError(f"host harness file missing for {profile_id}: {harness_path}")
            if harness_path.suffix.lower() != ".py":
                raise RuntimeError(f"host harness entry must be .py for {profile_id}: {harness_path}")

            if not harness_value.startswith(f"{firmware_path}/"):
                raise RuntimeError(
                    f"host harness entry must stay under firmware_path for {profile_id}: {harness_value}"
                )

            harness_name = harness_path.name.lower()
            if "verify" not in harness_name:
                raise RuntimeError(
                    f"host harness file name must contain 'verify' for {profile_id}: {harness_path}"
                )
            harness_checked += 1

        preferred_stack = payload.get("preferred_stack")
        if not isinstance(preferred_stack, list) or not preferred_stack:
            raise RuntimeError(f"preferred_stack must be non-empty array: {path}")

        lower_stack = {str(item).strip().lower() for item in preferred_stack}
        if "arduino-ide" in lower_stack:
            if runtime_path.suffix.lower() != ".ino":
                raise RuntimeError(f"expected .ino native entry for Arduino profile {profile_id}: {runtime_path}")

            preset_entry = _required_str(payload, "native_preset_entry", path)
            preset_path = project_root / "firmware" / preset_entry
            if not preset_path.exists():
                raise RuntimeError(f"Arduino preset entry missing for {profile_id}: {preset_path}")

            _verify_arduino_sketch(
                profile_id=profile_id,
                sketch_path=runtime_path,
                preset_path=preset_path,
            )

        if "flipper_sdk_c_cpp" in lower_stack:
            if runtime_path.suffix.lower() != ".c":
                raise RuntimeError(f"expected .c native entry for Flipper profile {profile_id}: {runtime_path}")
            manifest = _required_str(payload, "native_manifest_entry", path)
            manifest_path = project_root / "firmware" / manifest
            if not manifest_path.exists():
                raise RuntimeError(f"flipper manifest entry missing for {profile_id}: {manifest_path}")
            _verify_flipper_runtime(
                profile_id=profile_id,
                runtime_path=runtime_path,
                manifest_path=manifest_path,
            )

        checked += 1

    print("NATIVE_LAYOUT_PROFILE_COUNT", checked)
    print("NATIVE_LAYOUT_HARNESS_COUNT", harness_checked)


def _load_profile(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"profile root must be object: {path}")
    return payload


def _required_str(payload: dict[str, Any], key: str, path: Path) -> str:
    value = payload.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise RuntimeError(f"required string key '{key}' missing in {path}")


def _verify_arduino_sketch(*, profile_id: str, sketch_path: Path, preset_path: Path) -> None:
    content = sketch_path.read_text(encoding="utf-8")

    preset_name = preset_path.name
    if preset_name not in content:
        raise RuntimeError(
            f"Arduino sketch does not include expected preset '{preset_name}' for {profile_id}: {sketch_path}"
        )

    has_runtime_include = (
        "local_chat_runtime.h" in content
        or "runtime_profiles.h" in content
        or "_preset.h" in content
        or "arduino/presets/" in content
    )
    if not has_runtime_include:
        raise RuntimeError(
            f"Arduino sketch must include local_chat_runtime/runtime_profiles or device preset helper for {profile_id}: {sketch_path}"
        )

    required_snippets = (
        "RuntimeConfig kConfig",
        "DeviceRuntime kRuntime",
        "void setup()",
        "void loop()",
    )
    for snippet in required_snippets:
        if snippet not in content:
            raise RuntimeError(f"Arduino sketch missing snippet '{snippet}' for {profile_id}: {sketch_path}")


def _verify_flipper_runtime(*, profile_id: str, runtime_path: Path, manifest_path: Path) -> None:
    manifest = manifest_path.read_text(encoding="utf-8")
    runtime = runtime_path.read_text(encoding="utf-8")

    appid_match = re.search(r'appid\s*=\s*"([^"]+)"', manifest)
    if appid_match is None:
        raise RuntimeError(f"Flipper manifest appid missing for {profile_id}: {manifest_path}")

    entry_match = re.search(r'entry_point\s*=\s*"([^"]+)"', manifest)
    if entry_match is None:
        raise RuntimeError(f"Flipper manifest entry_point missing for {profile_id}: {manifest_path}")

    entry_point = entry_match.group(1)
    if entry_point not in runtime:
        raise RuntimeError(
            f"Flipper runtime does not reference entry_point '{entry_point}' for {profile_id}: {runtime_path}"
        )

    if "local_chat_api.h" not in runtime:
        raise RuntimeError(
            f"Flipper runtime missing local_chat_api include for {profile_id}: {runtime_path}"
        )


if __name__ == "__main__":
    main()
