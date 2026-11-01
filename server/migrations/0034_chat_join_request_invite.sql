-- Remember which invite produced an approval-based join request so that the
-- invite use counter is incremented on approval, not only on the direct path.
ALTER TABLE chat_join_requests ADD COLUMN invite_id INTEGER;
CREATE INDEX IF NOT EXISTS idx_chat_join_requests_invite
ON chat_join_requests(invite_id);
