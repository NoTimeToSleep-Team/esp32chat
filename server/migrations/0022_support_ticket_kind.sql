-- Support ticket kinds and user reports
-- kind: 'support' (regular help desk) or 'report' (user report on another user)
-- target_user_id: the reported user for kind='report', NULL for regular tickets

PRAGMA foreign_keys = ON;

ALTER TABLE support_tickets ADD COLUMN kind TEXT NOT NULL DEFAULT 'support';
ALTER TABLE support_tickets ADD COLUMN target_user_id INTEGER;

CREATE INDEX IF NOT EXISTS idx_support_tickets_kind
ON support_tickets(kind, status, updated_at_ms DESC);
