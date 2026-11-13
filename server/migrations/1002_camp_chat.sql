PRAGMA foreign_keys = ON;

-- Camp chat channels: one staff channel and one channel per unit.  This table
-- is additive; the shared chat tables remain the source of truth for messages
-- and membership.
CREATE TABLE IF NOT EXISTS camp_chat_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    unit_id INTEGER NOT NULL DEFAULT 0,
    scope TEXT NOT NULL CHECK (scope IN ('staff', 'unit')),
    chat_id INTEGER NOT NULL UNIQUE,
    title TEXT NOT NULL,
    created_at_ms INTEGER NOT NULL,
    UNIQUE (session_id, scope, unit_id),
    FOREIGN KEY (session_id) REFERENCES camp_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_camp_chat_links_session
ON camp_chat_links(session_id, scope, unit_id);
