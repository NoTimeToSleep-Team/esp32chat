from __future__ import annotations

from pathlib import Path

from firmware.common.protocol import MessageType, from_json, to_json


def verify_contract_samples() -> tuple[int, int]:
    project_root = Path(__file__).resolve().parents[3]
    samples_dir = project_root / "contracts" / "messages"

    sample_files = sorted(samples_dir.glob("*.json"))
    if not sample_files:
        raise RuntimeError(f"No contract sample files found in: {samples_dir}")

    validated = 0
    round_tripped = 0
    supported_types = {item.value for item in MessageType}

    for sample_file in sample_files:
        raw = sample_file.read_text(encoding="utf-8")
        envelope = from_json(raw)
        validated += 1

        if envelope.message_type not in supported_types:
            raise RuntimeError(f"Unsupported message type in sample {sample_file.name}")

        raw_round_trip = to_json(envelope)
        from_json(raw_round_trip)
        round_tripped += 1

    return validated, round_tripped


def main() -> None:
    validated, round_tripped = verify_contract_samples()
    print("CONTRACT_SAMPLES_VALIDATED", validated)
    print("CONTRACT_SAMPLES_ROUNDTRIP", round_tripped)


if __name__ == "__main__":
    main()
