from __future__ import annotations

import inspect
import sqlite3
from pathlib import Path

from app.api import auth, chat, health, media, realtime
from app.config import _default_threadpool_size, load_settings
from app.db.connection import connect_sqlite
from app.db.migrate import apply_sql_migrations


def test_threadpool_size_has_safe_default_and_can_be_overridden() -> None:
    settings = load_settings({"LCS_PROFILE": "test", "LCS_RELOAD": "false"})
    assert settings.threadpool_size == _default_threadpool_size()
    assert 8 <= settings.threadpool_size <= 32

    overridden = load_settings(
        {
            "LCS_PROFILE": "test",
            "LCS_RELOAD": "false",
            "LCS_THREADPOOL_SIZE": "12",
        }
    )
    assert overridden.threadpool_size == 12


def test_sqlite_connections_are_configured_for_concurrency(tmp_path: Path) -> None:
    db_path = tmp_path / "test.sqlite3"
    connection = connect_sqlite(db_path)
    try:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        assert connection.execute("PRAGMA temp_store").fetchone()[0] == 2
        assert connection.execute("PRAGMA cache_size").fetchone()[0] == -8192
    finally:
        connection.close()

    read_only = connect_sqlite(db_path, read_only=True)
    try:
        assert read_only.execute("PRAGMA query_only").fetchone()[0] == 1
    finally:
        read_only.close()


def test_performance_indexes_are_created(tmp_path: Path) -> None:
    db_path = tmp_path / "test.sqlite3"
    apply_sql_migrations(f"sqlite:///{db_path.as_posix()}")

    with sqlite3.connect(db_path) as connection:
        message_indexes = {
            row[1] for row in connection.execute("PRAGMA index_list(chat_messages)")
        }
        media_indexes = {
            row[1]
            for row in connection.execute("PRAGMA index_list(media_attachments)")
        }

    assert "idx_chat_messages_chat_id_id" in message_indexes
    assert "idx_chat_messages_created_at" in message_indexes
    assert "idx_media_attachments_owner_created" in media_indexes


def test_hot_routes_run_in_the_threadpool() -> None:
    for handler in (
        auth.login,
        auth.get_session,
        chat.list_chats,
        chat.list_chat_updates,
        chat.list_chat_messages,
        health.health,
        media.list_my_attachments,
    ):
        assert not inspect.iscoroutinefunction(handler), handler.__name__

    assert inspect.iscoroutinefunction(realtime.realtime_chat)
    assert inspect.iscoroutinefunction(realtime.get_online_users)
