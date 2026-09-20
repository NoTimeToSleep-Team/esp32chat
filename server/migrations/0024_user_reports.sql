-- Dedicated user reports (complaints on users), separate from support tickets
-- reporter: who filed the report; target: who is being reported
-- reason: spam / abuse / profanity / ads / scam / other
-- status: pending / resolved; action: dismiss / warn / ban

CREATE TABLE IF NOT EXISTS user_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reporter_user_id INTEGER NOT NULL,
    reporter_login TEXT NOT NULL,
    target_user_id INTEGER NOT NULL,
    target_login TEXT,
    reason TEXT NOT NULL,
    comment TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    action TEXT,
    resolved_by TEXT,
    resolved_at_ms INTEGER,
    created_at_ms INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_user_reports_status
ON user_reports(status, created_at_ms DESC);

CREATE INDEX IF NOT EXISTS idx_user_reports_target
ON user_reports(target_user_id, status);
