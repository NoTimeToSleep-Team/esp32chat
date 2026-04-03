from __future__ import annotations

import os
import sqlite3
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Mapping

from .command_map import M5CARDPUTER_CONSOLE_BLOG_COMMANDS, blog_command_path_set
from ..config import M5CardputerConsoleConfig
from ..controller import M5CardputerConsoleController
from ..server_api import CommandSender, ConsoleAuthGateway


class TestClientCommandSender(CommandSender):
    def __init__(self, client: Any) -> None:
        self._client = client

    def send(
        self,
        *,
        method: str,
        path: str,
        query: Mapping[str, str] | None = None,
        json_payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_method = method.upper()
        if normalized_method == "GET":
            response = self._client.get(path, params=dict(query or {}))
        elif normalized_method == "POST":
            response = self._client.post(path, params=dict(query or {}), json=dict(json_payload or {}))
        else:
            raise RuntimeError(f"unsupported method in test sender: {method}")

        payload = response.json()
        if response.status_code >= 400:
            raise RuntimeError(f"HTTP {response.status_code} for {method} {path}: {payload}")
        if not isinstance(payload, dict):
            raise RuntimeError("response payload must be object")
        return payload


def main() -> None:
    project_root = Path(__file__).resolve().parents[4]
    server_root = project_root / "server"

    db_name = f"local_chat_m5cardputer_blog_test_{uuid.uuid4().hex}.db"
    os.environ["LCS_PROFILE"] = "test"
    os.environ["LCS_DATABASE_URL"] = f"sqlite:///data/sqlite/{db_name}"
    os.environ["LCS_STORAGE_ROOT"] = "data"
    os.environ["LCS_RELOAD"] = "false"

    if str(server_root) not in sys.path:
        sys.path.insert(0, str(server_root))

    from fastapi.testclient import TestClient  # type: ignore
    from app.config import get_settings  # type: ignore
    from app.main import create_app  # type: ignore
    from app.services.auth import hash_password  # type: ignore

    get_settings(refresh=True)
    app = create_app()

    with TestClient(app) as client:
        route_map: dict[str, set[str]] = {}
        for route in app.routes:
            methods = {item.upper() for item in getattr(route, "methods", set())}
            existing = route_map.get(route.path)
            if existing is None:
                existing = set()
                route_map[route.path] = existing
            existing.update(methods)
        _verify_command_map(route_map)

        db_path = app.state.data_layer.database_path
        now_ms = int(time.time() * 1000)
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            """
            INSERT INTO users(login, password_hash, role, status, created_at_ms, updated_at_ms)
            VALUES (?, ?, 'admin', 'active', ?, ?)
            """,
            ("console-blog-admin", hash_password("console-blog-admin-secret"), now_ms, now_ms),
        )
        conn.execute(
            """
            INSERT INTO users(login, password_hash, role, status, created_at_ms, updated_at_ms)
            VALUES (?, ?, 'user', 'active', ?, ?)
            """,
            ("console-blog-user", hash_password("console-blog-user-secret"), now_ms + 1, now_ms + 1),
        )
        conn.commit()
        conn.close()

        admin_login = client.post(
            "/auth/login",
            json={
                "login": "console-blog-admin",
                "password": "console-blog-admin-secret",
                "client_kind": "web",
            },
        )
        if admin_login.status_code != 200:
            raise RuntimeError(f"admin login failed: {admin_login.status_code} {admin_login.text}")
        admin_token = admin_login.json()["session"]["token"]

        published = client.post(
            "/admin/content/blog/posts",
            json={
                "session_token": admin_token,
                "title": "Console Blog Verification",
                "body_text": "Post published for m5cardputer blog-read flow",
            },
        )
        if published.status_code != 200:
            raise RuntimeError(f"admin blog publish failed: {published.status_code} {published.text}")
        expected_post_id = int(published.json()["post"]["post_id"])

        sender = TestClientCommandSender(client)
        auth_gateway = ConsoleAuthGateway(sender)
        controller = M5CardputerConsoleController(
            config=M5CardputerConsoleConfig(client_kind="device"),
            gateway=auth_gateway,
        )

        controller.start_shell(now_ms=7101)
        login_state = controller.secure_login(
            login="console-blog-user",
            password="console-blog-user-secret",
            now_ms=7102,
        )
        if login_state.session is None:
            raise RuntimeError("secure_login did not return session")
        token = login_state.session.token

        posts = controller.blog.list_posts(session_token=token, limit=20)
        if not posts.items:
            raise RuntimeError("blog list is empty")
        target = _find_post(posts.items, expected_post_id)
        loaded = controller.blog.get_post(session_token=token, post_id=target.post_id)

        print("COMMAND_MAP_COUNT", len(M5CARDPUTER_CONSOLE_BLOG_COMMANDS))
        print("COMMAND_PATHS", sorted(blog_command_path_set()))
        print("POSTS_COUNT", posts.count)
        print("TARGET_POST", target.post_id, target.title)
        print("LOADED_POST", loaded.post_id, loaded.title)

        if target.post_id != expected_post_id:
            raise RuntimeError("published blog post is not visible to console user")
        if loaded.post_id != expected_post_id:
            raise RuntimeError("loaded blog post id mismatch")
        if "Verification" not in loaded.title:
            raise RuntimeError("loaded blog post title mismatch")


def _verify_command_map(route_map: dict[str, set[str]]) -> None:
    for command in M5CARDPUTER_CONSOLE_BLOG_COMMANDS:
        methods = route_map.get(command.path_template)
        if methods is None:
            raise RuntimeError(f"missing server route for command: {command.path_template}")
        if command.method.upper() not in methods:
            raise RuntimeError(
                f"method mismatch for route {command.path_template}: expected {command.method}, actual {sorted(methods)}"
            )

    forbidden_paths = {
        "/blog/api/posts",
    }
    overlap = sorted(forbidden_paths & blog_command_path_set())
    if not overlap:
        raise RuntimeError("blog command map must include /blog/api/posts")


def _find_post(items: tuple[Any, ...], post_id: int) -> Any:
    for item in items:
        if int(getattr(item, "post_id", -1)) == post_id:
            return item
    raise RuntimeError(f"post not found in list: {post_id}")


if __name__ == "__main__":
    main()
