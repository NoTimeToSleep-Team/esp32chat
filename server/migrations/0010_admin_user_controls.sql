PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS user_restrictions (
    user_id INTEGER PRIMARY KEY,
    block_reason TEXT,
    blocked_until_ms INTEGER,
    updated_by_user_id INTEGER,
    updated_at_ms INTEGER NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (updated_by_user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_user_restrictions_blocked_until
ON user_restrictions(blocked_until_ms);

CREATE TABLE IF NOT EXISTS device_blacklist (
    device_id TEXT PRIMARY KEY,
    reason TEXT,
    blocked_by_user_id INTEGER NOT NULL,
    created_at_ms INTEGER NOT NULL,
    updated_at_ms INTEGER NOT NULL,
    FOREIGN KEY (blocked_by_user_id) REFERENCES users(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_device_blacklist_updated
ON device_blacklist(updated_at_ms DESC);
