from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SweepCommand:
    name: str
    group: str
    args: tuple[str, ...]


GROUPS = (
    "contracts",
    "devices",
    "integration",
    "profiles",
    "native",
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run software verification sweep")
    parser.add_argument(
        "--project-root",
        default=str(Path(__file__).resolve().parents[2]),
        help="Project root path",
    )
    parser.add_argument(
        "--python-exe",
        default=sys.executable,
        help="Python executable path used to run checks",
    )
    parser.add_argument(
        "--continue-on-fail",
        action="store_true",
        help="Continue running after a failed command",
    )
    parser.add_argument(
        "--with-compileall",
        action="store_true",
        help="Also run compileall across server/app and firmware",
    )
    parser.add_argument(
        "--group",
        action="append",
        choices=GROUPS,
        help="Run only selected verification group (can be repeated)",
    )
    parser.add_argument(
        "--list-groups",
        action="store_true",
        help="List supported groups and exit",
    )
    args = parser.parse_args()

    if args.list_groups:
        print("SWEEP_GROUPS", list(GROUPS))
        return

    project_root = Path(args.project_root).resolve()
    python_exe = args.python_exe

    commands = _build_commands(with_compileall=args.with_compileall)
    selected_groups = set(args.group or GROUPS)
    selected_commands = [command for command in commands if command.group in selected_groups]
    if not selected_commands:
        raise RuntimeError("no verification commands selected")

    failures: list[str] = []

    print("SWEEP_GROUPS_SELECTED", sorted(selected_groups))
    print("SWEEP_COMMAND_COUNT", len(selected_commands))
    for index, command in enumerate(selected_commands, start=1):
        call_args = [python_exe, *command.args]
        print("SWEEP_STEP", index, command.name)
        print("SWEEP_CMD", _format_cmd(call_args))
        result = subprocess.run(call_args, cwd=project_root)
        if result.returncode != 0:
            failures.append(command.name)
            print("SWEEP_STEP_STATUS", command.name, "fail", result.returncode)
            if not args.continue_on_fail:
                break
        else:
            print("SWEEP_STEP_STATUS", command.name, "pass")

    if failures:
        print("SWEEP_STATUS", "FAIL")
        print("SWEEP_FAILED_STEPS", failures)
        raise SystemExit(1)

    print("SWEEP_STATUS", "PASS")


def _build_commands(*, with_compileall: bool) -> list[SweepCommand]:
    commands: list[SweepCommand] = [
        SweepCommand("contracts_protocol", "contracts", ("-m", "firmware.common.protocol.verify_contract_samples")),
        SweepCommand("shared_transport", "contracts", ("-m", "firmware.common.transport.verify_transport_queue")),
        SweepCommand("shared_uart_framing", "contracts", ("-m", "firmware.common.transport.verify_uart_framing")),
        SweepCommand(
            "shared_uart_adapter",
            "contracts",
            ("-m", "firmware.common.transport.verify_uart_transport_adapter"),
        ),
        SweepCommand(
            "shared_uart_sync_retry",
            "contracts",
            ("-m", "firmware.common.transport.verify_uart_sync_retry"),
        ),
        SweepCommand("esp32_service_mvp", "devices", ("-m", "firmware.devices.esp32_service.verify_mvp")),
        SweepCommand(
            "esp32_sync_transport",
            "devices",
            ("-m", "firmware.devices.esp32_service.verify_sync_transport"),
        ),
        SweepCommand("m5stamp_mvp", "devices", ("-m", "firmware.devices.m5stamp.verify_mvp")),
        SweepCommand("atom_s3_mvp", "devices", ("-m", "firmware.devices.atom_s3.verify_mvp")),
        SweepCommand("m5tab_mvp", "devices", ("-m", "firmware.devices.m5tab.verify_mvp")),
        SweepCommand(
            "m5tab_admin_users",
            "devices",
            ("-m", "firmware.devices.m5tab.screens.admin_users.verify_flow"),
        ),
        SweepCommand("m5tab_admin_ops", "devices", ("-m", "firmware.devices.m5tab.screens.admin_ops.verify_flow")),
        SweepCommand(
            "m5cardputer_console_mvp",
            "devices",
            ("-m", "firmware.devices.m5cardputer_console.verify_mvp"),
        ),
        SweepCommand(
            "m5cardputer_console_chat",
            "devices",
            ("-m", "firmware.devices.m5cardputer_console.chat.verify_flow"),
        ),
        SweepCommand(
            "m5cardputer_console_blog",
            "devices",
            ("-m", "firmware.devices.m5cardputer_console.blog.verify_flow"),
        ),
        SweepCommand(
            "m5cardputer_console_service_actions",
            "devices",
            ("-m", "firmware.devices.m5cardputer_console.service_actions.verify_flow"),
        ),
        SweepCommand(
            "m5cardputer_client_alignment",
            "devices",
            ("-m", "firmware.devices.m5cardputer_client.verify_alignment"),
        ),
        SweepCommand("m5cardputer_client_ui", "devices", ("-m", "firmware.devices.m5cardputer_client.ui.verify_flow")),
        SweepCommand("m5stickc_plus2_mvp", "devices", ("-m", "firmware.devices.m5stickc_plus2.verify_mvp")),
        SweepCommand("m5stickc_plus2_ui", "devices", ("-m", "firmware.devices.m5stickc_plus2.ui.verify_flow")),
        SweepCommand("t_embed_cc1101_mvp", "devices", ("-m", "firmware.devices.t_embed_cc1101.verify_mvp")),
        SweepCommand("t_embed_cc1101_ui", "devices", ("-m", "firmware.devices.t_embed_cc1101.ui.verify_flow")),
        SweepCommand("flipper_zero_mvp", "devices", ("-m", "firmware.devices.flipper_zero.verify_mvp")),
        SweepCommand("flipper_zero_ui", "devices", ("-m", "firmware.devices.flipper_zero.ui.verify_flow")),
        SweepCommand(
            "esp32_registration_e2e",
            "integration",
            ("-m", "firmware.devices.esp32_service.verify_registration_e2e"),
        ),
        SweepCommand("integration_chat_e2e", "integration", ("-m", "firmware.integration.verify_chat_e2e")),
        SweepCommand("integration_ops_e2e", "integration", ("-m", "firmware.integration.verify_ops_e2e")),
        SweepCommand(
            "profile_json_parse",
            "profiles",
            (
                "-c",
                "import json, pathlib; [json.loads(p.read_text(encoding='utf-8')) for p in pathlib.Path('firmware/profiles').glob('*.json')]; print('profiles_ok')",
            ),
        ),
        SweepCommand("autonomy_profiles", "profiles", ("firmware/profiles/autonomy/verify_profiles.py",)),
        SweepCommand("native_layout", "native", ("firmware/arduino/verify_native_layout.py",)),
    ]

    if with_compileall:
        commands.append(SweepCommand("compileall", "native", ("-m", "compileall", "server/app", "firmware")))

    return commands


def _format_cmd(args: list[str]) -> str:
    escaped: list[str] = []
    for item in args:
        if " " in item:
            escaped.append(f'"{item}"')
        else:
            escaped.append(item)
    return " ".join(escaped)


if __name__ == "__main__":
    main()
