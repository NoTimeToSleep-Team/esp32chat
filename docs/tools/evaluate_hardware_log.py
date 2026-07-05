from __future__ import annotations

import argparse
from pathlib import Path

SCENARIO_IDS = [
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
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate hardware validation markdown log")
    parser.add_argument("log_path", help="Path to hardware validation log markdown file")
    args = parser.parse_args()

    path = Path(args.log_path)
    if not path.exists():
        raise SystemExit(f"log file not found: {path}")

    parsed = _parse_log(path)

    missing_rows = [scenario for scenario in SCENARIO_IDS if scenario not in parsed]
    pass_count = 0
    fail_count = 0
    blocked_count = 0
    pending_count = 0

    for scenario in SCENARIO_IDS:
        value = parsed.get(scenario, "").strip().lower()
        value = value.replace("`", "")
        if value == "pass":
            pass_count += 1
        elif value == "fail":
            fail_count += 1
        elif value == "blocked":
            blocked_count += 1
        else:
            pending_count += 1

    if fail_count > 0:
        decision = "NO-GO"
    elif blocked_count > 0 or pending_count > 0 or missing_rows:
        decision = "PENDING"
    else:
        decision = "GO"

    print("HW_LOG_FILE", str(path))
    print("HW_SCENARIOS_EXPECTED", len(SCENARIO_IDS))
    print("HW_SCENARIOS_PRESENT", len(parsed))
    print("HW_PASS", pass_count)
    print("HW_FAIL", fail_count)
    print("HW_BLOCKED", blocked_count)
    print("HW_PENDING", pending_count)
    print("HW_MISSING_ROWS", len(missing_rows))
    if missing_rows:
        print("HW_MISSING_LIST", missing_rows)
    print("HW_GATE_DECISION", decision)


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
        outcome = parts[2]
        result[scenario] = outcome
    return result


if __name__ == "__main__":
    main()
