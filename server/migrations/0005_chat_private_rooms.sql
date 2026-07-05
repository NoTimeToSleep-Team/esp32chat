PRAGMA foreign_keys = ON;

ALTER TABLE chats ADD COLUMN is_private INTEGER NOT NULL DEFAULT 0;
ALTER TABLE chats ADD COLUMN room_code_hash TEXT;
ALTER TABLE chats ADD COLUMN avatar_url TEXT;

CREATE INDEX IF NOT EXISTS idx_chats_private_kind
ON chats(is_private, kind);
