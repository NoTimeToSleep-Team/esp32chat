PRAGMA foreign_keys = ON;

ALTER TABLE users ADD COLUMN phone TEXT;
ALTER TABLE users ADD COLUMN registration_device_id TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_phone_unique
ON users(phone)
WHERE phone IS NOT NULL AND phone <> '';

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_registration_device_unique
ON users(registration_device_id)
WHERE registration_device_id IS NOT NULL AND registration_device_id <> '';
