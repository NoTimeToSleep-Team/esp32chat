from __future__ import annotations

import sqlite3
from dataclasses import dataclass, replace
from pathlib import Path
from time import time

from app.models import BlogPost, BlogPostDraft, UserRole, UserStatus
from app.services.media import MAX_ATTACHMENTS_PER_MESSAGE, MediaService


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
    def __init__(self, db_path: str | Path, storage_root: str | Path | None = None) -> None:
        self._db_path = Path(db_path)
        self._storage_root = storage_root

    def _media(self) -> MediaService | None:
        if self._storage_root is None:
            return None
        return MediaService(db_path=self._db_path, storage_root=self._storage_root)

    def publish_post(self, *, author_user_id: int, draft: BlogPostDraft) -> BlogPost:
        ids = self._normalize_attachment_ids(draft.attachment_ids)
        with self._connect() as connection:
            author = self._require_active_user(connection, author_user_id)
            if str(author["role"]) != UserRole.ADMIN.value:
                raise BlogError("admin_only", "Only admin can publish blog posts", 403)

            for attachment_id in ids:
                attachment = connection.execute(
                    "SELECT owner_user_id FROM media_attachments WHERE id = ?",
                    (attachment_id,),
                ).fetchone()
                if attachment is None:
                    raise BlogError("attachment_not_found", "Attachment not found", 404)
                if int(attachment["owner_user_id"]) != int(author_user_id):
                    raise BlogError(
                        "forbidden_attachment",
                        "Cannot attach a file owned by another user",
                        403,
                    )

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
            for position, attachment_id in enumerate(ids):
                connection.execute(
                    """
                    INSERT OR IGNORE INTO blog_post_attachments(post_id, attachment_id, position)
                    VALUES (?, ?, ?)
                    """,
                    (post_id, attachment_id, position),
                )

            row = connection.execute(
                "SELECT * FROM blog_posts WHERE id = ?",
                (post_id,),
            ).fetchone()
            if row is None:
                raise BlogError("publish_failed", "Failed to publish blog post", 500)
            post = self._row_to_post(row)
        return self._with_attachments([post])[0]

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
            posts = [self._row_to_post(row) for row in rows]
        return self._with_attachments(posts)

    def get_post(self, *, requester_user_id: int, post_id: int) -> BlogPost:
        with self._connect() as connection:
            self._require_active_user(connection, requester_user_id)
            row = connection.execute(
                "SELECT * FROM blog_posts WHERE id = ?",
                (post_id,),
            ).fetchone()
            if row is None:
                raise BlogError("post_not_found", "Blog post was not found", 404)
            post = self._row_to_post(row)
        return self._with_attachments([post])[0]

    def _with_attachments(self, posts: list[BlogPost]) -> list[BlogPost]:
        media = self._media()
        if media is None or not posts:
            return posts
        grouped = media.attachments_for_blog_posts([post.post_id for post in posts])
        return [
            replace(post, attachments=grouped.get(post.post_id, ())) for post in posts
        ]

    @staticmethod
    def _normalize_attachment_ids(attachment_ids: tuple[int, ...]) -> tuple[int, ...]:
        ids = tuple(dict.fromkeys(int(value) for value in attachment_ids if int(value) > 0))
        if len(ids) > MAX_ATTACHMENTS_PER_MESSAGE:
            raise BlogError("too_many_attachments", "Too many attachments for one post", 422)
        return ids

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
