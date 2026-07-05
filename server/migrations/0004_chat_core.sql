PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS chats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL CHECK (kind IN ('common', 'custom')),
    title TEXT NOT NULL,
    description TEXT,
    owner_user_id INTEGER,
    created_at_ms INTEGER NOT NULL,
    updated_at_ms INTEGER NOT NULL,
    FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_chats_kind ON chats(kind);
CREATE INDEX IF NOT EXISTS idx_chats_updated_at_ms ON chats(updated_at_ms);

CREATE TABLE IF NOT EXISTS chat_members (
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('owner', 'member')),
    joined_at_ms INTEGER NOT NULL,
    PRIMARY KEY (chat_id, user_id),
    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chat_members_user_id ON chat_members(user_id);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    author_user_id INTEGER NOT NULL,
    body_text TEXT NOT NULL,
    client_message_id TEXT,
    created_at_ms INTEGER NOT NULL,
    edited_at_ms INTEGER,
    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE,
    FOREIGN KEY (author_user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_chat_created
ON chat_messages(chat_id, created_at_ms);

CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_messages_client_message_id_unique
ON chat_messages(chat_id, client_message_id)
WHERE client_message_id IS NOT NULL AND client_message_id <> '';
