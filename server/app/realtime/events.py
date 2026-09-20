from __future__ import annotations

from app.models import ChatMessage


def chat_message_payload(message: ChatMessage) -> dict[str, object]:
    return {
        "message_id": message.message_id,
        "chat_id": message.chat_id,
        "author_user_id": message.author_user_id,
        "author_login": message.author_login,
        "author_avatar_emoji": message.author_avatar_emoji,
        "body_text": message.body_text,
        "client_message_id": message.client_message_id,
        "created_at_ms": message.created_at_ms,
        "edited_at_ms": message.edited_at_ms,
        "attachments": [
            {
                "attachment_id": item.attachment_id,
                "filename": item.original_filename,
                "mime_type": item.mime_type,
                "media_kind": item.media_kind.value,
                "size_bytes": item.size_bytes,
                "download_url": f"/media/api/attachments/{item.attachment_id}/download",
            }
            for item in message.attachments
        ],
    }


def chat_message_event(message: ChatMessage) -> dict[str, object]:
    return {
        "type": "chat.message",
        "message": chat_message_payload(message),
    }


def chat_protocol_event_payload(message: ChatMessage) -> dict[str, object]:
    return {
        "chat_id": str(message.chat_id),
        "message_id": f"chatmsg-{message.message_id}",
        "server_seq": message.message_id,
        "author_user_id": str(message.author_user_id),
        "text": message.body_text,
        "created_at_ms": message.created_at_ms,
    }
