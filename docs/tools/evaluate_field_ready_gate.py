from __future__ import annotations

import argparse
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

OPS_SCENARIOS = ("HW-OPS-01", "HW-OPS-02", "HW-OPS-03", "HW-OPS-04")
SAFE_SCENARIOS = ("HW-SAFE-01", "HW-SAFE-02", "HW-SAFE-03", "HW-SAFE-04")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate field-ready gate status")
    parser.add_argument("--log", required=True, help="Path to hardware validation markdown log")
    parser.add_argument(
        "--project-root",
        default=str(Path(__file__).resolve().parents[2]),
        help="Project root path",
    )
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    log_path = Path(args.log).resolve()
    if not log_path.exists():
        raise SystemExit(f"hardware log not found: {log_path}")

    verification_report_path = project_root / "docs" / "verification-report-2026-04-03.md"
    known_limitations_path = project_root / "docs" / "known-limitations.md"

    outcomes = _parse_log(log_path)
    pass_count, fail_count, blocked_count, pending_count = _count_outcomes(outcomes)

    gate01 = _gate01_software_acceptance(verification_report_path)
    gate02 = _gate02_hardware_scenarios(fail_count, blocked_count, pending_count)
    gate03 = _gate03_blocked_handling(blocked_count)
    gate04 = _gate04_limitations(known_limitations_path)
    gate05 = _gate05_operator_evidence(outcomes)

    states = {
        "GATE-01": gate01,
        "GATE-02": gate02,
        "GATE-03": gate03,
        "GATE-04": gate04,
        "GATE-05": gate05,
    }

    if any(value == "fail" for value in states.values()):
        decision = "NO-GO"
    elif all(value == "pass" for value in states.values()):
        decision = "GO"
    else:
        decision = "PENDING"

    print("FIELD_READY_LOG", log_path)
    print("FIELD_READY_HW_PASS", pass_count)
    print("FIELD_READY_HW_FAIL", fail_count)
    print("FIELD_READY_HW_BLOCKED", blocked_count)
    print("FIELD_READY_HW_PENDING", pending_count)
    print("FIELD_READY_GATE_01", gate01)
    print("FIELD_READY_GATE_02", gate02)
    print("FIELD_READY_GATE_03", gate03)
    print("FIELD_READY_GATE_04", gate04)
    print("FIELD_READY_GATE_05", gate05)
    print("FIELD_READY_DECISION", decision)


def _gate01_software_acceptance(report_path: Path) -> str:
    if not report_path.exists():
        return "pending"
    content = report_path.read_text(encoding="utf-8")
    if "Overall status: `pass`" in content:
        return "pass"
    return "pending"


def _gate02_hardware_scenarios(fail_count: int, blocked_count: int, pending_count: int) -> str:
    if fail_count > 0:
        return "fail"
    if blocked_count > 0 or pending_count > 0:
        return "pending"
    return "pass"


def _gate03_blocked_handling(blocked_count: int) -> str:
    if blocked_count > 0:
        return "pending"
    return "pass"


def _gate04_limitations(path: Path) -> str:
    if not path.exists():
        return "pending"
    content = path.read_text(encoding="utf-8")
    if "## Known Limitations" in content or "# Known Limitations" in content:
        return "pass"
    return "pending"


def _gate05_operator_evidence(outcomes: dict[str, str]) -> str:
    relevant = list(OPS_SCENARIOS) + list(SAFE_SCENARIOS)
    values = [outcomes.get(item, "pending") for item in relevant]
    if any(value == "fail" for value in values):
        return "fail"
    if all(value == "pass" for value in values):
        return "pass"
    return "pending"


def _count_outcomes(outcomes: dict[str, str]) -> tuple[int, int, int, int]:
    pass_count = 0
    fail_count = 0
    blocked_count = 0
    pending_count = 0

    for scenario in SCENARIO_IDS:
        value = outcomes.get(scenario, "pending")
        if value == "pass":
            pass_count += 1
        elif value == "fail":
            fail_count += 1
        elif value == "blocked":
            blocked_count += 1
        else:
            pending_count += 1

    return pass_count, fail_count, blocked_count, pending_count


def _parse_log(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line.startswith("|"):
            continue
        parts = [cell.strip() for cell in line.split("|")]
        if len(parts) < 4:
            continue
        scenario = parts[1].replace("`", "")
        if not scenario.startswith("HW-"):
            continue
        outcome = parts[2].strip().lower().replace("`", "")
        if outcome not in {"pass", "fail", "blocked"}:
            outcome = "pending"
        result[scenario] = outcome
    return result


if __name__ == "__main__":
    main()
