PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    login TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('guest', 'user', 'admin')),
    status TEXT NOT NULL CHECK (status IN ('active', 'blocked', 'banned')),
    created_at_ms INTEGER NOT NULL,
    updated_at_ms INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    created_at_ms INTEGER NOT NULL,
    expires_at_ms INTEGER NOT NULL,
    revoked_at_ms INTEGER,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expires_at_ms ON sessions(expires_at_ms);

CREATE TABLE IF NOT EXISTS mode_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    access_mode TEXT NOT NULL CHECK (access_mode IN ('open', 'closed')),
    updated_at_ms INTEGER NOT NULL
);

INSERT OR IGNORE INTO mode_state (id, access_mode, updated_at_ms)
VALUES (1, 'closed', 0);

CREATE TABLE IF NOT EXISTS device_registry (
    id TEXT PRIMARY KEY,
    device_type TEXT NOT NULL,
    status TEXT NOT NULL,
    last_seen_ms INTEGER,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    actor_kind TEXT,
    actor_id TEXT,
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at_ms INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_log_event_type ON audit_log(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_log_created_at_ms ON audit_log(created_at_ms);
