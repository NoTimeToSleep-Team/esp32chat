-- Bind sessions to the client class and the paired device identity.
-- Legacy sessions are invalidated deliberately: before this migration a
-- device-session token was indistinguishable from a web/admin token.
ALTER TABLE sessions ADD COLUMN client_kind TEXT NOT NULL DEFAULT 'web';
ALTER TABLE sessions ADD COLUMN device_id TEXT;

DELETE FROM sessions;

CREATE INDEX IF NOT EXISTS idx_sessions_client_kind
ON sessions(client_kind);
