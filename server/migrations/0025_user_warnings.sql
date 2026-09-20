-- User warnings issued from user reports (warn action)
-- users.warn_count: current warning counter (reset to 0 after the 3rd warning triggers a 3-day ban)

CREATE TABLE IF NOT EXISTS user_warnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    report_id INTEGER,
    issued_by_login TEXT NOT NULL,
    created_at_ms INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_user_warnings_user
ON user_warnings(user_id, created_at_ms DESC);

ALTER TABLE users ADD COLUMN warn_count INTEGER NOT NULL DEFAULT 0;
