PRAGMA foreign_keys = ON;

-- Per-chat message lookups (last message, unread counter) filter by chat_id
-- and walk by id.  The existing (chat_id, created_at_ms) index needs a
-- temporary B-tree for ORDER BY id; this index removes that sort.
CREATE INDEX IF NOT EXISTS idx_chat_messages_chat_id_id
ON chat_messages(chat_id, id DESC);

-- /chat/api/updates reads messages newer than a timestamp across all chats.
CREATE INDEX IF NOT EXISTS idx_chat_messages_created_at
ON chat_messages(created_at_ms DESC);

-- "My Files" lists one owner's newest attachments first.
CREATE INDEX IF NOT EXISTS idx_media_attachments_owner_created
ON media_attachments(owner_user_id, created_at_ms DESC);
