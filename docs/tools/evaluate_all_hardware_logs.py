from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
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


@dataclass(frozen=True)
class LogEval:
    path: Path
    decision: str
    pass_count: int
    fail_count: int
    blocked_count: int
    pending_count: int
    date_key: str
    session_key: int


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate all hardware validation logs")
    parser.add_argument(
        "--docs-dir",
        default=str(Path(__file__).resolve().parents[1]),
        help="Docs directory path",
    )
    args = parser.parse_args()

    docs_dir = Path(args.docs_dir).resolve()
    evaluations = _collect_evaluations(docs_dir)

    print("HW_LOG_COUNT", len(evaluations))
    for item in evaluations:
        print(
            "HW_LOG",
            item.path.name,
            item.decision,
            f"pass={item.pass_count}",
            f"fail={item.fail_count}",
            f"blocked={item.blocked_count}",
            f"pending={item.pending_count}",
        )

    if not evaluations:
        print("HW_LATEST", "none")
        print("HW_LATEST_DECISION", "NONE")
        return

    latest = evaluations[-1]
    print("HW_LATEST", latest.path.name)
    print("HW_LATEST_DECISION", latest.decision)


def _collect_evaluations(docs_dir: Path) -> list[LogEval]:
    items: list[LogEval] = []
    for path in docs_dir.glob("hardware-validation-log-*.md"):
        date_key, session_key = _extract_sort_key(path.name)
        if date_key == "0000-00-00":
            continue
        parsed = _parse_log(path)
        pass_count, fail_count, blocked_count, pending_count = _count_outcomes(parsed)
        if fail_count > 0:
            decision = "NO-GO"
        elif blocked_count > 0 or pending_count > 0:
            decision = "PENDING"
        else:
            decision = "GO"
        items.append(
            LogEval(
                path=path,
                decision=decision,
                pass_count=pass_count,
                fail_count=fail_count,
                blocked_count=blocked_count,
                pending_count=pending_count,
                date_key=date_key,
                session_key=session_key,
            )
        )

    items.sort(key=lambda item: (item.date_key, item.session_key, item.path.name))
    return items


def _extract_sort_key(filename: str) -> tuple[str, int]:
    match = re.match(r"hardware-validation-log-(\d{4}-\d{2}-\d{2})-session-(\d+)\.md$", filename)
    if match is None:
        return ("0000-00-00", 0)
    return match.group(1), int(match.group(2))


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


if __name__ == "__main__":
    main()
