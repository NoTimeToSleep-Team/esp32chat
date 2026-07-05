from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path

SCENARIO_IDS = (
    "HW-ENV-01",
    "HW-ENV-02",
    "HW-ENV-03",
    "HW-ENV-04",
    "HW-NET-01",
    "HW-NET-02",
    "HW-NET-03",
    "HW-NET-04",
    "HW-PWR-01",
    "HW-PWR-02",
    "HW-PWR-03",
    "HW-PWR-04",
    "HW-OPS-01",
    "HW-OPS-02",
    "HW-OPS-03",
    "HW-OPS-04",
    "HW-SAFE-01",
    "HW-SAFE-02",
    "HW-SAFE-03",
    "HW-SAFE-04",
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a new hardware validation log")
    parser.add_argument("--date", default=dt.date.today().isoformat(), help="Date in YYYY-MM-DD format")
    parser.add_argument("--session", type=int, default=None, help="Session number override")
    parser.add_argument("--build-tag", default="RC1", help="Build/tag label")
    parser.add_argument("--overwrite", action="store_true", help="Allow overwrite if file exists")
    args = parser.parse_args()

    docs_dir = Path(__file__).resolve().parents[1]
    project_root = docs_dir.parent
    profiles_dir = project_root / "firmware" / "profiles"

    profile_ids = _load_profile_ids(profiles_dir)
    session_number = args.session if args.session is not None else _next_session_number(docs_dir, args.date)
    output_path = docs_dir / f"hardware-validation-log-{args.date}-session-{session_number:02d}.md"

    if output_path.exists() and not args.overwrite:
        raise SystemExit(f"target file already exists: {output_path}")

    content = _build_markdown(
        date_text=args.date,
        session_number=session_number,
        build_tag=args.build_tag,
        profile_ids=profile_ids,
    )
    output_path.write_text(content, encoding="utf-8")

    print("HW_NEW_LOG_PATH", output_path)
    print("HW_PROFILE_COUNT", len(profile_ids))
    print("HW_SCENARIO_COUNT", len(SCENARIO_IDS))


def _load_profile_ids(profiles_dir: Path) -> list[str]:
    profile_ids: list[str] = []
    for path in sorted(profiles_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        profile_id = payload.get("profile_id")
        if isinstance(profile_id, str) and profile_id.strip():
            profile_ids.append(profile_id.strip())
    if not profile_ids:
        raise RuntimeError(f"no profile IDs found in {profiles_dir}")
    return profile_ids


def _next_session_number(docs_dir: Path, date_text: str) -> int:
    pattern = re.compile(rf"^hardware-validation-log-{re.escape(date_text)}-session-(\d+)\.md$")
    max_session = 0
    for path in docs_dir.glob(f"hardware-validation-log-{date_text}-session-*.md"):
        match = pattern.match(path.name)
        if not match:
            continue
        value = int(match.group(1))
        if value > max_session:
            max_session = value
    return max_session + 1


def _build_markdown(
    *,
    date_text: str,
    session_number: int,
    build_tag: str,
    profile_ids: list[str],
) -> str:
    lines: list[str] = []
    lines.append(f"# Hardware Validation Log ({date_text} / Session {session_number:02d})")
    lines.append("")
    lines.append("Auto-generated session file for physical validation run.")
    lines.append("Status at creation: `not executed` (no physical run data yet).")
    lines.append("")
    lines.append("## Session Metadata")
    lines.append("")
    lines.append(f"- Date: {date_text}")
    lines.append("- Operator:")
    lines.append("- Location/Bench:")
    lines.append("- Server node (Raspberry Pi ID):")
    lines.append(f"- Build/Tag under test: `{build_tag}`")
    lines.append("- Notes:")
    lines.append("")
    lines.append("## Device Matrix")
    lines.append("")
    lines.append("| profile_id | physical unit id | firmware ref | included in run |")
    lines.append("| --- | --- | --- | --- |")
    for profile_id in profile_ids:
        lines.append(f"| `{profile_id}` | | | |")
    lines.append("")
    lines.append("## Scenario Results")
    lines.append("")
    lines.append("| scenario_id | result (`pass`/`fail`/`blocked`) | evidence pointer | notes |")
    lines.append("| --- | --- | --- | --- |")
    for scenario in SCENARIO_IDS:
        lines.append(f"| `{scenario}` | | | |")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Total scenarios: {len(SCENARIO_IDS)}")
    lines.append("- Passed:")
    lines.append("- Failed:")
    lines.append("- Blocked:")
    lines.append("- Field-ready recommendation:")
    lines.append("- Follow-up actions:")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
