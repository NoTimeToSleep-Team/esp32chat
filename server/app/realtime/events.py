from __future__ import annotations

from app.models import ChatMessage


def chat_message_payload(
    message: ChatMessage,
    *,
    include_reply_preview: bool = True,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "message_id": message.message_id,
        "chat_id": message.chat_id,
        "author_user_id": message.author_user_id,
        "author_login": message.author_login,
        "author_avatar_emoji": message.author_avatar_emoji,
        "body_text": message.body_text,
        "client_message_id": message.client_message_id,
        "created_at_ms": message.created_at_ms,
        "edited_at_ms": message.edited_at_ms,
        "reply_to_message_id": message.reply_to_message_id,
        "forwarded_from_login": message.forwarded_from_login,
        "forwarded_from_chat_id": message.forwarded_from_chat_id,
        "reactions": [
            {"emoji": item.emoji, "count": item.count, "mine": item.mine}
            for item in message.reactions
        ],
        "poll": None if message.poll is None else {
            "poll_id": message.poll.poll_id,
            "question": message.poll.question,
            "options": [
                {
                    "index": option.index,
                    "text": option.text,
                    "votes": option.votes,
                    "mine": option.mine,
                    "voters": [
                        {
                            "user_id": voter.user_id,
                            "login": voter.login,
                            "display_name": voter.display_name,
                            "avatar_emoji": voter.avatar_emoji,
                        }
                        for voter in option.voters
                    ],
                }
                for option in message.poll.options
            ],
            "total_votes": message.poll.total_votes,
            "is_multiple": message.poll.is_multiple,
            "is_anonymous": message.poll.is_anonymous,
            "closed": message.poll.closed,
        },
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
    if include_reply_preview:
        payload["reply_to_login"] = message.reply_to_login
        payload["reply_to_text"] = (message.reply_to_text or "")[:200] or None
    return payload


def chat_message_event(message: ChatMessage) -> dict[str, object]:
    # Broadcasts are shared by every room member.  A reply preview must be
    # filtered per viewer because history_visible=false can hide the parent
    # message from newly joined members.  Send only the id; the client can
    # resolve the preview through the per-viewer HTTP history endpoint.
    return {
        "type": "chat.message",
        "message": chat_message_payload(message, include_reply_preview=False),
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
