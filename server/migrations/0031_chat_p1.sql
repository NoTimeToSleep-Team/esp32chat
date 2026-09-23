PRAGMA foreign_keys = ON;

-- Replies and forwards.
ALTER TABLE chat_messages ADD COLUMN reply_to_message_id INTEGER;
ALTER TABLE chat_messages ADD COLUMN forwarded_from_chat_id INTEGER;
ALTER TABLE chat_messages ADD COLUMN forwarded_from_message_id INTEGER;
ALTER TABLE chat_messages ADD COLUMN forwarded_from_user_id INTEGER;
ALTER TABLE chat_messages ADD COLUMN forwarded_from_login TEXT;

-- Reactions (a small fixed set, one reaction per user per message).
CREATE TABLE IF NOT EXISTS chat_message_reactions (
    message_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    emoji TEXT NOT NULL,
    created_at_ms INTEGER NOT NULL,
    PRIMARY KEY (message_id, user_id, emoji),
    FOREIGN KEY (message_id) REFERENCES chat_messages(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chat_reactions_message ON chat_message_reactions(message_id);

-- Read state, drafts and per-chat user state already live in chat_members
-- (last_read_message_id, draft_text, draft_updated_at_ms, is_muted, is_archived,
-- is_pinned, cleared_at_ms) — added by migration 0030.
