PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS device_catalog (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    short_description TEXT NOT NULL,
    firmware_archive_url TEXT,
    install_guide TEXT NOT NULL,
    pairing_guide TEXT NOT NULL,
    combo_reset_guide TEXT NOT NULL,
    is_published INTEGER NOT NULL CHECK (is_published IN (0, 1)),
    created_by_user_id INTEGER NOT NULL,
    created_at_ms INTEGER NOT NULL,
    updated_at_ms INTEGER NOT NULL,
    published_at_ms INTEGER,
    FOREIGN KEY (created_by_user_id) REFERENCES users(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_device_catalog_published
ON device_catalog(is_published, published_at_ms DESC, id DESC);

CREATE TABLE IF NOT EXISTS user_device_flags (
    user_id INTEGER NOT NULL,
    device_id INTEGER NOT NULL,
    has_device INTEGER NOT NULL CHECK (has_device IN (0, 1)),
    updated_at_ms INTEGER NOT NULL,
    PRIMARY KEY (user_id, device_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (device_id) REFERENCES device_catalog(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_user_device_flags_device
ON user_device_flags(device_id, updated_at_ms DESC);
