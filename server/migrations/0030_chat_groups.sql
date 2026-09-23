PRAGMA foreign_keys = ON;

-- ===== Member roles: owner / admin / member / subscriber =====
-- The old table only allowed (owner, member); rebuild it with room for admins,
-- subscribers, per-member permissions and per-member chat state.
-- Rows that point to deleted chats/users are dropped (orphans).
CREATE TABLE IF NOT EXISTS chat_members_v2 (
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('owner', 'admin', 'member', 'subscriber')),
    permissions TEXT,
    joined_at_ms INTEGER NOT NULL,
    is_muted INTEGER NOT NULL DEFAULT 0,
    is_archived INTEGER NOT NULL DEFAULT 0,
    is_pinned INTEGER NOT NULL DEFAULT 0,
    cleared_at_ms INTEGER,
    last_read_message_id INTEGER,
    draft_text TEXT,
    draft_updated_at_ms INTEGER,
    PRIMARY KEY (chat_id, user_id),
    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

INSERT OR IGNORE INTO chat_members_v2(chat_id, user_id, role, joined_at_ms)
SELECT m.chat_id, m.user_id, m.role, m.joined_at_ms
FROM chat_members m
JOIN chats c ON c.id = m.chat_id
JOIN users u ON u.id = m.user_id;

DROP TABLE IF EXISTS chat_members;
ALTER TABLE chat_members_v2 RENAME TO chat_members;

CREATE INDEX IF NOT EXISTS idx_chat_members_user_id ON chat_members(user_id);

-- ===== Invite links =====
CREATE TABLE IF NOT EXISTS chat_invites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    code TEXT NOT NULL UNIQUE,
    created_by INTEGER,
    created_at_ms INTEGER NOT NULL,
    expires_at_ms INTEGER,
    max_uses INTEGER,
    uses INTEGER NOT NULL DEFAULT 0,
    requires_approval INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE,
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_chat_invites_chat ON chat_invites(chat_id, created_at_ms DESC);

-- ===== Join requests =====
CREATE TABLE IF NOT EXISTS chat_join_requests (
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'declined')),
    created_at_ms INTEGER NOT NULL,
    decided_by INTEGER,
    decided_at_ms INTEGER,
    PRIMARY KEY (chat_id, user_id),
    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chat_join_requests_status
ON chat_join_requests(chat_id, status, created_at_ms DESC);

-- ===== Chat types: dm / group / channel (columns last: a re-run only needs to
-- report "duplicate column name" after everything above already applied) =====
ALTER TABLE chats ADD COLUMN chat_type TEXT NOT NULL DEFAULT 'group';
ALTER TABLE chats ADD COLUMN username TEXT;
ALTER TABLE chats ADD COLUMN is_public INTEGER NOT NULL DEFAULT 0;
ALTER TABLE chats ADD COLUMN slow_mode_seconds INTEGER NOT NULL DEFAULT 0;
ALTER TABLE chats ADD COLUMN pinned_message_id INTEGER;
ALTER TABLE chats ADD COLUMN history_visible INTEGER NOT NULL DEFAULT 1;

-- Existing one-on-one private chats (no room code, exactly two members) are DMs.
UPDATE chats
SET chat_type = 'dm'
WHERE kind = 'custom'
  AND is_private = 1
  AND room_code_hash IS NULL
  AND (SELECT COUNT(*) FROM chat_members m WHERE m.chat_id = chats.id) = 2;

CREATE UNIQUE INDEX IF NOT EXISTS idx_chats_username_unique
ON chats(username) WHERE username IS NOT NULL AND username <> '';
