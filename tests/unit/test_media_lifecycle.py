from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.db.migrate import apply_sql_migrations
from app.services.media import MediaError, MediaService


def _make_db(tmp_path: Path) -> tuple[Path, Path]:
    db_path = tmp_path / "test.sqlite3"
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    apply_sql_migrations(f"sqlite:///{db_path.as_posix()}")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO users(login, password_hash, role, status, created_at_ms, updated_at_ms) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("owner", "hash", "user", "active", 1, 1),
        )
        connection.execute(
            "INSERT INTO users(login, password_hash, role, status, created_at_ms, updated_at_ms) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("other", "hash", "user", "active", 1, 1),
        )
        connection.execute(
            "INSERT INTO users(login, password_hash, role, status, created_at_ms, updated_at_ms) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("admin", "hash", "admin", "active", 1, 1),
        )
    return db_path, storage_root


def _service(tmp_path: Path) -> MediaService:
    db_path, storage_root = _make_db(tmp_path)
    return MediaService(db_path=db_path, storage_root=storage_root)


def test_owner_can_delete_unreferenced_attachment(tmp_path: Path) -> None:
    service = _service(tmp_path)
    attachment = service.create_attachment(
        owner_user_id=1,
        original_filename="note.txt",
        mime_type="text/plain",
        content=b"hello",
    )
    absolute_path = Path(service._storage_root) / attachment.storage_path  # noqa: SLF001
    assert absolute_path.is_file()

    with pytest.raises(MediaError) as other_error:
        service.delete_owned_attachment(owner_user_id=2, attachment_id=attachment.attachment_id)
    assert other_error.value.status_code == 403

    deleted = service.delete_owned_attachment(owner_user_id=1, attachment_id=attachment.attachment_id)
    assert deleted.attachment_id == attachment.attachment_id
    assert not absolute_path.exists()
    assert service.list_owned_attachments(owner_user_id=1) == []


def test_attachment_used_by_message_is_not_deleted(tmp_path: Path) -> None:
    service = _service(tmp_path)
    attachment = service.create_attachment(
        owner_user_id=1,
        original_filename="photo.png",
        mime_type="image/png",
        content=b"\x89PNG\r\n\x1a\n",
    )
    with sqlite3.connect(Path(service._db_path)) as connection:  # noqa: SLF001
        connection.execute(
            "INSERT INTO chats(kind, title, created_at_ms, updated_at_ms) VALUES ('custom', 'test', 1, 1)"
        )
        chat_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        connection.execute(
            "INSERT INTO chat_messages(chat_id, author_user_id, body_text, created_at_ms) VALUES (?, 1, 'x', 1)",
            (chat_id,),
        )
        message_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        connection.execute(
            "INSERT INTO chat_message_attachments(message_id, attachment_id, position) VALUES (?, ?, 0)",
            (message_id, attachment.attachment_id),
        )

    with pytest.raises(MediaError) as error:
        service.delete_owned_attachment(owner_user_id=1, attachment_id=attachment.attachment_id)
    assert error.value.code == "attachment_in_use"


def test_user_stats_and_orphan_cleanup(tmp_path: Path) -> None:
    service = _service(tmp_path)
    orphan = service.create_attachment(
        owner_user_id=1,
        original_filename="orphan.txt",
        mime_type="text/plain",
        content=b"orphan",
    )
    stats = service.user_storage_stats(owner_user_id=1)
    assert stats["count"] == 1
    assert stats["total_bytes"] == len(b"orphan")

    result = service.cleanup_orphan_attachments()
    assert result["deleted"] == 1
    assert result["freed_bytes"] == len(b"orphan")
    assert service.list_owned_attachments(owner_user_id=1) == []
    assert not (Path(service._storage_root) / orphan.storage_path).exists()  # noqa: SLF001
