from __future__ import annotations

"""Административный CLI сервера (используется установщиком и мастером v0.1).

Примеры:
    python -m app.cli --app-root /opt/local-chat-server --env-file config/app.env \\
        create-admin --username admin --password 'пароль'
    python -m app.cli --app-root /opt/local-chat-server --env-file config/app.env \\
        set-mode --mode open
"""

import argparse
import os
import secrets
import sqlite3
import sys
from pathlib import Path
from time import time


def _now_ms() -> int:
    return int(time() * 1000)


def _load_env_file(path: str) -> None:
    env_path = Path(path)
    if not env_path.is_file():
        raise SystemExit(f"env file not found: {env_path}")
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        os.environ.setdefault(key, value.strip().strip("'\""))


def _init(env_file: str | None, app_root: str | None):
    if app_root:
        sys.path.insert(0, app_root)
    if env_file:
        _load_env_file(env_file)
    from app.config import get_settings
    from app.db.bootstrap import initialize_data_layer

    settings = get_settings(refresh=True)
    state = initialize_data_layer(settings)
    return settings, state


def cmd_create_admin(args) -> None:
    _settings, state = _init(args.env_file, args.app_root)
    username = args.username.strip()
    if len(username) < 3 or len(username) > 32:
        raise SystemExit("username must be 3..32 characters")
    if len(args.password) < 8:
        raise SystemExit("password must be at least 8 characters")

    from app.services.auth import hash_password

    connection = sqlite3.connect(str(state.database_path))
    try:
        row = connection.execute(
            "SELECT id FROM users WHERE login = ?", (username,)
        ).fetchone()
        if row is not None:
            connection.execute(
                "UPDATE users SET password_hash = ?, role = 'admin', status = 'active', "
                "updated_at_ms = ? WHERE id = ?",
                (hash_password(args.password), _now_ms(), row[0]),
            )
            connection.commit()
            print(f"admin '{username}' already exists: password updated, role=admin")
            return
    finally:
        connection.close()

    from app.models import ClientKind
    from app.services.registration import RegistrationError, RegistrationService

    service = RegistrationService(db_path=state.database_path)
    try:
        service.register_user(
            login=username,
            password=args.password,
            phone="",
            device_id="cli-admin-" + secrets.token_hex(4),
            client_kind=ClientKind.WEB,
        )
    except RegistrationError as exc:
        raise SystemExit(f"cannot create admin: {exc}")

    connection = sqlite3.connect(str(state.database_path))
    try:
        connection.execute(
            "UPDATE users SET role = 'admin', updated_at_ms = ? WHERE login = ?",
            (_now_ms(), username),
        )
        connection.commit()
    finally:
        connection.close()
    print(f"admin '{username}' created (role=admin)")


def cmd_set_mode(args) -> None:
    _settings, state = _init(args.env_file, args.app_root)
    from app.models import AccessMode
    from app.services.mode import ModeService

    mode = AccessMode(args.mode)
    ModeService(db_path=state.database_path).set_mode(mode)
    print(f"registration mode set to {mode.value}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description="Local Chat Server administration CLI (installer helper)",
    )
    parser.add_argument(
        "--app-root",
        default=None,
        help="path to the server tree (inserted at the front of sys.path)",
    )
    parser.add_argument(
        "--env-file",
        default=None,
        help="load LCS_* settings from a KEY=VALUE file before doing anything",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_admin = sub.add_parser(
        "create-admin", help="create the administrator or reset its password"
    )
    p_admin.add_argument("--username", required=True)
    p_admin.add_argument("--password", required=True)

    p_mode = sub.add_parser(
        "set-mode", help="set the portal registration mode (open|closed)"
    )
    p_mode.add_argument("--mode", required=True, choices=["open", "closed"])

    args = parser.parse_args(argv)
    if args.command == "create-admin":
        cmd_create_admin(args)
    elif args.command == "set-mode":
        cmd_set_mode(args)


if __name__ == "__main__":
    main()
