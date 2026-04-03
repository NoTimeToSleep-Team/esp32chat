from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from time import time

from app.models import BlogPost, BlogPostDraft, UserRole, UserStatus


def _now_ms() -> int:
    return int(time() * 1000)


@dataclass(frozen=True)
class BlogError(RuntimeError):
    code: str
    message: str
    status_code: int

    def __str__(self) -> str:
        return self.message


class BlogService:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)

    def publish_post(self, *, author_user_id: int, draft: BlogPostDraft) -> BlogPost:
        with self._connect() as connection:
            author = self._require_active_user(connection, author_user_id)
            if str(author["role"]) != UserRole.ADMIN.value:
                raise BlogError("admin_only", "Only admin can publish blog posts", 403)

            now_ms = _now_ms()
            cursor = connection.execute(
                """
                INSERT INTO blog_posts(
                    title,
                    body_text,
                    author_user_id,
                    published_at_ms,
                    updated_at_ms
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    draft.title.strip(),
                    draft.body_text.strip(),
                    author_user_id,
                    now_ms,
                    now_ms,
                ),
            )
            post_id = int(cursor.lastrowid)

            row = connection.execute(
                "SELECT * FROM blog_posts WHERE id = ?",
                (post_id,),
            ).fetchone()
            if row is None:
                raise BlogError("publish_failed", "Failed to publish blog post", 500)
            return self._row_to_post(row)

    def list_posts(self, *, requester_user_id: int, limit: int = 20, offset: int = 0) -> list[BlogPost]:
        safe_limit = min(max(limit, 1), 200)
        safe_offset = max(offset, 0)

        with self._connect() as connection:
            self._require_active_user(connection, requester_user_id)

            rows = connection.execute(
                """
                SELECT *
                FROM blog_posts
                ORDER BY published_at_ms DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                (safe_limit, safe_offset),
            ).fetchall()
            return [self._row_to_post(row) for row in rows]

    def get_post(self, *, requester_user_id: int, post_id: int) -> BlogPost:
        with self._connect() as connection:
            self._require_active_user(connection, requester_user_id)
            row = connection.execute(
                "SELECT * FROM blog_posts WHERE id = ?",
                (post_id,),
            ).fetchone()
            if row is None:
                raise BlogError("post_not_found", "Blog post was not found", 404)
            return self._row_to_post(row)

    def _require_active_user(self, connection: sqlite3.Connection, user_id: int) -> sqlite3.Row:
        row = connection.execute(
            "SELECT id, role, status FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            raise BlogError("user_not_found", "User was not found", 404)
        if str(row["status"]) != UserStatus.ACTIVE.value:
            raise BlogError("inactive_user", "User account is not active", 403)
        return row

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _row_to_post(row: sqlite3.Row) -> BlogPost:
        return BlogPost(
            post_id=int(row["id"]),
            title=str(row["title"]),
            body_text=str(row["body_text"]),
            author_user_id=int(row["author_user_id"]),
            published_at_ms=int(row["published_at_ms"]),
            updated_at_ms=int(row["updated_at_ms"]),
        )
