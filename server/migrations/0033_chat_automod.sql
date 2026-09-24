PRAGMA foreign_keys = ON;

-- ===== Auto-moderation: reports land in the normal moderation queue =====

ALTER TABLE user_reports ADD COLUMN source TEXT NOT NULL DEFAULT 'user';
ALTER TABLE user_reports ADD COLUMN matched_words TEXT;
ALTER TABLE user_reports ADD COLUMN message_id INTEGER;
ALTER TABLE user_reports ADD COLUMN chat_id INTEGER;

CREATE INDEX IF NOT EXISTS idx_user_reports_auto_message
ON user_reports(message_id, source, status);

CREATE TABLE IF NOT EXISTS auto_moderation_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    enabled INTEGER NOT NULL DEFAULT 1,
    extra_words TEXT,
    whitelist TEXT,
    updated_at_ms INTEGER NOT NULL
);

INSERT OR IGNORE INTO auto_moderation_settings(id, enabled, extra_words, whitelist, updated_at_ms)
VALUES (1, 1, '', '', 0);
