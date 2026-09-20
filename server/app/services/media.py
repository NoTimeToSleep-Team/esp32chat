from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import unicodedata
import uuid
from dataclasses import dataclass
from pathlib import Path
from time import time

from app.models import MediaAttachment, MediaDownload, MediaKind, UserRole


MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_ATTACHMENTS_PER_MESSAGE = 8
MIN_FREE_BYTES_DEFAULT = 200 * 1024 * 1024


def _min_free_bytes() -> int:
    raw = os.environ.get("LCS_MIN_FREE_MB", "").strip()
    if raw:
        try:
            value = int(float(raw))
            if value >= 0:
                return value * 1024 * 1024
        except ValueError:
            pass
    return MIN_FREE_BYTES_DEFAULT

IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
AUDIO_MIME_TYPES = {"audio/mpeg", "audio/ogg", "audio/wav", "audio/webm", "audio/mp4"}
FILE_MIME_TYPES = {
    "application/pdf",
    "text/plain",
    "application/zip",
    "application/octet-stream",
    "image/heic",
    "image/heif",
    "video/mp4",
    "video/webm",
    "video/quicktime",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/csv",
    "application/json",
}
ALLOWED_MIME_TYPES = IMAGE_MIME_TYPES | AUDIO_MIME_TYPES | FILE_MIME_TYPES


def _now_ms() -> int:
    return int(time() * 1000)


@dataclass(frozen=True)
class MediaError(RuntimeError):
    code: str
    message: str
    status_code: int

    def __str__(self) -> str:
        return self.message


class MediaService:
    def __init__(self, db_path: str | Path, storage_root: str | Path) -> None:
        self._db_path = Path(db_path)
        self._storage_root = Path(storage_root)
        if not self._storage_root.is_absolute():
            self._storage_root = (Path(__file__).resolve().parents[2] / self._storage_root).resolve()

    def create_attachment(
        self,
        *,
        owner_user_id: int,
        original_filename: str | None,
        mime_type: str | None,
        content: bytes,
    ) -> MediaAttachment:
        safe_mime = self._normalize_mime(mime_type)
        media_kind = self._media_kind_for_mime(safe_mime)
        if len(content) == 0:
            raise MediaError("empty_upload", "Uploaded file is empty", 422)
        if len(content) > MAX_UPLOAD_BYTES:
            raise MediaError("upload_too_large", "Uploaded file exceeds the size limit", 413)
        free_bytes = self._free_bytes()
        if free_bytes is not None and free_bytes - len(content) < _min_free_bytes():
            raise MediaError(
                "storage_full",
                "Server storage is almost full; uploads are temporarily disabled",
                507,
            )

        safe_name = self._safe_filename(original_filename)
        suffix = Path(safe_name).suffix.lower()
        stored_filename = f"{uuid.uuid4().hex}{suffix}"
        relative_dir = Path("media") / "uploads" / media_kind.value
        absolute_dir = self._storage_root / relative_dir
        absolute_dir.mkdir(parents=True, exist_ok=True)
        absolute_path = absolute_dir / stored_filename
        relative_path = (relative_dir / stored_filename).as_posix()
        sha256_hex = hashlib.sha256(content).hexdigest()

        with self._connect() as connection:
            self._require_active_user(connection, owner_user_id)
            absolute_path.write_bytes(content)
            try:
                cursor = connection.execute(
                    """
                    INSERT INTO media_attachments(
                        owner_user_id, original_filename, stored_filename, storage_path,
                        mime_type, media_kind, size_bytes, sha256_hex, created_at_ms
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        owner_user_id,
                        safe_name,
                        stored_filename,
                        relative_path,
                        safe_mime,
                        media_kind.value,
                        len(content),
                        sha256_hex,
                        _now_ms(),
                    ),
                )
                attachment_id = self._lastrowid(cursor)
            except Exception:
                try:
                    absolute_path.unlink(missing_ok=True)
                finally:
                    raise

            return self._get_attachment(connection, attachment_id)

    def list_owned_attachments(self, *, owner_user_id: int, limit: int = 100) -> list[MediaAttachment]:
        safe_limit = min(max(limit, 1), 300)
        with self._connect() as connection:
            self._require_active_user(connection, owner_user_id)
            rows = connection.execute(
                """
                SELECT * FROM media_attachments
                WHERE owner_user_id = ?
                ORDER BY created_at_ms DESC, id DESC
                LIMIT ?
                """,
                (owner_user_id, safe_limit),
            ).fetchall()
            return [self._row_to_attachment(row) for row in rows]

    def resolve_download(self, *, attachment_id: int, requester_user_id: int) -> MediaDownload:
        with self._connect() as connection:
            self._require_active_user(connection, requester_user_id)
            attachment = self._get_attachment(connection, attachment_id)
            if not self._can_access_attachment(connection, attachment_id=attachment_id, requester_user_id=requester_user_id):
                raise MediaError("forbidden", "User has no access to this attachment", 403)

        absolute_path = (self._storage_root / attachment.storage_path).resolve()
        storage_root = self._storage_root.resolve()
        try:
            absolute_path.relative_to(storage_root)
        except ValueError as exc:
            raise MediaError("invalid_storage_path", "Attachment path is outside storage", 500) from exc
        if not absolute_path.is_file():
            raise MediaError("file_missing", "Attachment file is missing", 404)
        return MediaDownload(attachment=attachment, absolute_path=str(absolute_path))

    def attach_to_chat_message(self, *, message_id: int, attachment_ids: tuple[int, ...], actor_user_id: int) -> tuple[MediaAttachment, ...]:
        ids = self._normalize_attachment_ids(attachment_ids)
        if not ids:
            return ()
        with self._connect() as connection:
            self._require_active_user(connection, actor_user_id)
            for position, attachment_id in enumerate(ids):
                attachment = self._get_attachment(connection, attachment_id)
                if attachment.owner_user_id != actor_user_id:
                    raise MediaError("forbidden_attachment", "Cannot attach a file owned by another user", 403)
                connection.execute(
                    """
                    INSERT OR IGNORE INTO chat_message_attachments(message_id, attachment_id, position)
                    VALUES (?, ?, ?)
                    """,
                    (message_id, attachment_id, position),
                )
            return self.list_for_chat_messages(connection, [message_id]).get(message_id, ())

    def attach_to_support_message(self, *, message_id: int, attachment_ids: tuple[int, ...], actor_user_id: int) -> tuple[MediaAttachment, ...]:
        ids = self._normalize_attachment_ids(attachment_ids)
        if not ids:
            return ()
        with self._connect() as connection:
            self._require_active_user(connection, actor_user_id)
            for position, attachment_id in enumerate(ids):
                attachment = self._get_attachment(connection, attachment_id)
                if attachment.owner_user_id != actor_user_id:
                    raise MediaError("forbidden_attachment", "Cannot attach a file owned by another user", 403)
                connection.execute(
                    """
                    INSERT OR IGNORE INTO support_message_attachments(message_id, attachment_id, position)
                    VALUES (?, ?, ?)
                    """,
                    (message_id, attachment_id, position),
                )
            return self.list_for_support_messages(connection, [message_id]).get(message_id, ())

    def list_for_chat_messages(self, connection: sqlite3.Connection, message_ids: list[int]) -> dict[int, tuple[MediaAttachment, ...]]:
        ids = sorted({int(message_id) for message_id in message_ids})
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        rows = connection.execute(
            f"""
            SELECT cma.message_id, ma.*
            FROM chat_message_attachments cma
            JOIN media_attachments ma ON ma.id = cma.attachment_id
            WHERE cma.message_id IN ({placeholders})
            ORDER BY cma.message_id ASC, cma.position ASC, ma.id ASC
            """,
            ids,
        ).fetchall()
        return self._group_attachment_rows(rows, "message_id")

    def list_for_support_messages(self, connection: sqlite3.Connection, message_ids: list[int]) -> dict[int, tuple[MediaAttachment, ...]]:
        ids = sorted({int(message_id) for message_id in message_ids})
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        rows = connection.execute(
            f"""
            SELECT sma.message_id, ma.*
            FROM support_message_attachments sma
            JOIN media_attachments ma ON ma.id = sma.attachment_id
            WHERE sma.message_id IN ({placeholders})
            ORDER BY sma.message_id ASC, sma.position ASC, ma.id ASC
            """,
            ids,
        ).fetchall()
        return self._group_attachment_rows(rows, "message_id")

    def list_for_reports(self, connection: sqlite3.Connection, report_ids: list[int]) -> dict[int, tuple[MediaAttachment, ...]]:
        ids = sorted({int(report_id) for report_id in report_ids})
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        rows = connection.execute(
            f"""
            SELECT ra.report_id, ma.*
            FROM report_attachments ra
            JOIN media_attachments ma ON ma.id = ra.attachment_id
            WHERE ra.report_id IN ({placeholders})
            ORDER BY ra.report_id ASC, ra.position ASC, ma.id ASC
            """,
            ids,
        ).fetchall()
        return self._group_attachment_rows(rows, "report_id")

    def list_for_blog_posts(self, connection: sqlite3.Connection, post_ids: list[int]) -> dict[int, tuple[MediaAttachment, ...]]:
        ids = sorted({int(post_id) for post_id in post_ids})
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        rows = connection.execute(
            f"""
            SELECT bpa.post_id, ma.*
            FROM blog_post_attachments bpa
            JOIN media_attachments ma ON ma.id = bpa.attachment_id
            WHERE bpa.post_id IN ({placeholders})
            ORDER BY bpa.post_id ASC, bpa.position ASC, ma.id ASC
            """,
            ids,
        ).fetchall()
        return self._group_attachment_rows(rows, "post_id")

    def attachments_for_reports(self, report_ids: list[int]) -> dict[int, tuple[MediaAttachment, ...]]:
        with self._connect() as connection:
            return self.list_for_reports(connection, report_ids)

    def attachments_for_blog_posts(self, post_ids: list[int]) -> dict[int, tuple[MediaAttachment, ...]]:
        with self._connect() as connection:
            return self.list_for_blog_posts(connection, post_ids)

    def storage_stats(self) -> dict[str, object]:
        with self._connect() as connection:
            totals = connection.execute(
                "SELECT COUNT(*) AS n, COALESCE(SUM(size_bytes), 0) AS total FROM media_attachments"
            ).fetchone()
            rows = connection.execute(
                """
                SELECT media_kind, COUNT(*) AS n, COALESCE(SUM(size_bytes), 0) AS total
                FROM media_attachments
                GROUP BY media_kind
                """
            ).fetchall()
        return {
            "count": int(totals["n"]) if totals else 0,
            "total_bytes": int(totals["total"]) if totals else 0,
            "free_bytes": self._free_bytes(),
            "min_free_bytes": _min_free_bytes(),
            "max_upload_bytes": MAX_UPLOAD_BYTES,
            "max_attachments_per_message": MAX_ATTACHMENTS_PER_MESSAGE,
            "by_kind": [
                {
                    "media_kind": str(row["media_kind"]),
                    "count": int(row["n"]),
                    "total_bytes": int(row["total"]),
                }
                for row in rows
            ],
        }

    def _free_bytes(self) -> int | None:
        target = self._storage_root
        try:
            return shutil.disk_usage(target).free
        except OSError:
            parent = target
            while not parent.exists() and parent != parent.parent:
                parent = parent.parent
            try:
                return shutil.disk_usage(parent).free
            except OSError:
                return None

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _normalize_attachment_ids(attachment_ids: tuple[int, ...]) -> tuple[int, ...]:
        ids = tuple(dict.fromkeys(int(value) for value in attachment_ids if int(value) > 0))
        if len(ids) > MAX_ATTACHMENTS_PER_MESSAGE:
            raise MediaError("too_many_attachments", "Too many attachments for one message", 422)
        return ids

    @staticmethod
    def _normalize_mime(mime_type: str | None) -> str:
        normalized = (mime_type or "application/octet-stream").split(";", 1)[0].strip().lower()
        if normalized not in ALLOWED_MIME_TYPES:
            raise MediaError("unsupported_media_type", "Uploaded file type is not allowed", 415)
        return normalized

    @staticmethod
    def _media_kind_for_mime(mime_type: str) -> MediaKind:
        if mime_type in IMAGE_MIME_TYPES:
            return MediaKind.IMAGE
        if mime_type in AUDIO_MIME_TYPES:
            return MediaKind.AUDIO
        return MediaKind.FILE

    @staticmethod
    def _safe_filename(filename: str | None) -> str:
        raw = Path(filename or "upload.bin").name.strip() or "upload.bin"
        raw = unicodedata.normalize("NFC", raw)
        forbidden = set('/\\:*?"<>|')
        cleaned = "".join(
            ch if (ch.isprintable() and ch not in forbidden) else "_" for ch in raw
        ).strip(" .")
        if not cleaned:
            cleaned = "upload.bin"
        return cleaned[:160]

    @staticmethod
    def _require_active_user(connection: sqlite3.Connection, user_id: int) -> sqlite3.Row:
        row = connection.execute("SELECT id, role, status FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise MediaError("user_not_found", "User not found", 404)
        if str(row["status"]) != "active":
            raise MediaError("user_inactive", "User account is not active", 403)
        return row

    def _can_access_attachment(self, connection: sqlite3.Connection, *, attachment_id: int, requester_user_id: int) -> bool:
        row = connection.execute("SELECT owner_user_id FROM media_attachments WHERE id = ?", (attachment_id,)).fetchone()
        if row is None:
            return False
        if int(row["owner_user_id"]) == requester_user_id:
            return True
        user = connection.execute("SELECT role FROM users WHERE id = ?", (requester_user_id,)).fetchone()
        is_admin = user is not None and str(user["role"]) == UserRole.ADMIN.value
        if is_admin:
            return True
        chat_row = connection.execute(
            """
            SELECT c.id AS chat_id, c.kind, c.owner_user_id
            FROM chat_message_attachments cma
            JOIN chat_messages cm ON cm.id = cma.message_id
            JOIN chats c ON c.id = cm.chat_id
            WHERE cma.attachment_id = ?
            LIMIT 1
            """,
            (attachment_id,),
        ).fetchone()
        if chat_row is not None:
            if str(chat_row["kind"]) == "common" or int(chat_row["owner_user_id"] or -1) == requester_user_id:
                return True
            member = connection.execute(
                "SELECT 1 FROM chat_members WHERE chat_id = ? AND user_id = ?",
                (int(chat_row["chat_id"]), requester_user_id),
            ).fetchone()
            if member is not None:
                return True
        support_row = connection.execute(
            """
            SELECT st.user_id
            FROM support_message_attachments sma
            JOIN support_messages sm ON sm.id = sma.message_id
            JOIN support_tickets st ON st.id = sm.ticket_id
            WHERE sma.attachment_id = ?
            LIMIT 1
            """,
            (attachment_id,),
        ).fetchone()
        if support_row is not None and int(support_row["user_id"]) == requester_user_id:
            return True
        if self._attachment_referenced_by(connection, "report_attachments", attachment_id):
            user = connection.execute(
                "SELECT role FROM users WHERE id = ?", (requester_user_id,)
            ).fetchone()
            if user is not None and str(user["role"]) in (
                UserRole.ADMIN.value,
                UserRole.MODERATOR.value,
            ):
                return True
        if self._attachment_referenced_by(connection, "blog_post_attachments", attachment_id):
            return True
        return False

    @staticmethod
    def _attachment_referenced_by(connection: sqlite3.Connection, table: str, attachment_id: int) -> bool:
        if table not in {"report_attachments", "blog_post_attachments"}:
            return False
        try:
            row = connection.execute(
                f"SELECT 1 FROM {table} WHERE attachment_id = ? LIMIT 1",
                (attachment_id,),
            ).fetchone()
        except sqlite3.OperationalError:
            return False
        return row is not None

    def _get_attachment(self, connection: sqlite3.Connection, attachment_id: int) -> MediaAttachment:
        row = connection.execute("SELECT * FROM media_attachments WHERE id = ?", (attachment_id,)).fetchone()
        if row is None:
            raise MediaError("attachment_not_found", "Attachment not found", 404)
        return self._row_to_attachment(row)

    @staticmethod
    def _group_attachment_rows(rows: list[sqlite3.Row], key: str) -> dict[int, tuple[MediaAttachment, ...]]:
        grouped: dict[int, list[MediaAttachment]] = {}
        for row in rows:
            grouped.setdefault(int(row[key]), []).append(MediaService._row_to_attachment(row))
        return {group_key: tuple(items) for group_key, items in grouped.items()}

    @staticmethod
    def _row_to_attachment(row: sqlite3.Row) -> MediaAttachment:
        return MediaAttachment(
            attachment_id=int(row["id"]),
            owner_user_id=int(row["owner_user_id"]),
            original_filename=str(row["original_filename"]),
            stored_filename=str(row["stored_filename"]),
            storage_path=str(row["storage_path"]),
            mime_type=str(row["mime_type"]),
            media_kind=MediaKind(str(row["media_kind"])),
            size_bytes=int(row["size_bytes"]),
            sha256_hex=str(row["sha256_hex"]),
            created_at_ms=int(row["created_at_ms"]),
        )

    @staticmethod
    def _lastrowid(cursor: sqlite3.Cursor) -> int:
        value = cursor.lastrowid
        if value is None:
            raise MediaError("invalid_data", "lastrowid is missing", 500)
        return int(value)
