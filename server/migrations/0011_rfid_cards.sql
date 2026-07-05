-- DEPRECATED in RPi-Only architecture (v1.00.00). Table kept for reference, not applied.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS rfid_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid_hash TEXT NOT NULL UNIQUE,
    uid_mask TEXT NOT NULL,
    card_label TEXT NOT NULL,
    note TEXT,
    is_active INTEGER NOT NULL CHECK (is_active IN (0, 1)),
    created_by_user_id INTEGER NOT NULL,
    created_at_ms INTEGER NOT NULL,
    updated_at_ms INTEGER NOT NULL,
    last_used_at_ms INTEGER,
    FOREIGN KEY (created_by_user_id) REFERENCES users(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_rfid_cards_active
ON rfid_cards(is_active, updated_at_ms DESC, id DESC);

CREATE TABLE IF NOT EXISTS rfid_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id INTEGER,
    uid_mask TEXT,
    action TEXT NOT NULL CHECK (
        action IN (
            'card_enroll',
            'card_toggle_active',
            'card_delete',
            'card_verify',
            'mode_switch'
        )
    ),
    granted INTEGER NOT NULL CHECK (granted IN (0, 1)),
    requested_mode TEXT CHECK (requested_mode IN ('open', 'closed')),
    resolved_mode TEXT CHECK (resolved_mode IN ('open', 'closed')),
    reason TEXT,
    source TEXT,
    actor_user_id INTEGER,
    created_at_ms INTEGER NOT NULL,
    FOREIGN KEY (card_id) REFERENCES rfid_cards(id) ON DELETE SET NULL,
    FOREIGN KEY (actor_user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_rfid_events_created
ON rfid_events(created_at_ms DESC, id DESC);
