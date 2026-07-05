PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS support_tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('open', 'in_progress', 'resolved', 'closed')),
    created_at_ms INTEGER NOT NULL,
    updated_at_ms INTEGER NOT NULL,
    last_message_at_ms INTEGER NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_support_tickets_user
ON support_tickets(user_id, updated_at_ms DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_support_tickets_status
ON support_tickets(status, updated_at_ms DESC, id DESC);

CREATE TABLE IF NOT EXISTS support_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER NOT NULL,
    author_user_id INTEGER NOT NULL,
    body_text TEXT NOT NULL,
    created_at_ms INTEGER NOT NULL,
    FOREIGN KEY (ticket_id) REFERENCES support_tickets(id) ON DELETE CASCADE,
    FOREIGN KEY (author_user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_support_messages_ticket
ON support_messages(ticket_id, created_at_ms ASC, id ASC);
