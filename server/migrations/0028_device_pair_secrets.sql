-- 0028_device_pair_secrets: secure device pairing (6-digit code + per-device secret)
-- Device shows a short-lived code, user claims it in the web UI, and only then
-- the device receives access. device-session will require an HMAC proof of the
-- stored secret, so knowing a device_id is no longer enough.

CREATE TABLE IF NOT EXISTS device_pair_requests (
    pairing_id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    device_type TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL DEFAULT '',
    code TEXT NOT NULL,
    device_secret_hash TEXT NOT NULL,
    created_at_ms INTEGER NOT NULL,
    expires_at_ms INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','claimed','expired'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_device_pair_requests_active_code
    ON device_pair_requests(code) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_device_pair_requests_device
    ON device_pair_requests(device_id, status);

ALTER TABLE device_pairings ADD COLUMN device_secret_hash TEXT NOT NULL DEFAULT '';
ALTER TABLE device_pairings ADD COLUMN last_seen_ms INTEGER NOT NULL DEFAULT 0;
ALTER TABLE device_pairings ADD COLUMN name TEXT NOT NULL DEFAULT '';
