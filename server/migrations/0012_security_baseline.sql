PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS auth_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    login TEXT NOT NULL,
    ip_address TEXT NOT NULL,
    success INTEGER NOT NULL CHECK (success IN (0, 1)),
    created_at_ms INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_auth_attempts_login_created
ON auth_attempts(login, created_at_ms DESC);

CREATE INDEX IF NOT EXISTS idx_auth_attempts_ip_created
ON auth_attempts(ip_address, created_at_ms DESC);

CREATE TABLE IF NOT EXISTS ip_blocks (
    ip_address TEXT PRIMARY KEY,
    blocked_until_ms INTEGER NOT NULL,
    reason TEXT,
    created_at_ms INTEGER NOT NULL,
    updated_at_ms INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ip_blocks_blocked_until
ON ip_blocks(blocked_until_ms);
