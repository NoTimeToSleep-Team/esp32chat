PRAGMA foreign_keys = ON;

-- Sessions, units and people -------------------------------------------------

CREATE TABLE IF NOT EXISTS camp_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    starts_at_ms INTEGER NOT NULL,
    ends_at_ms INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'planned'
        CHECK (status IN ('planned', 'active', 'closed', 'archived')),
    retention_days INTEGER NOT NULL DEFAULT 30,
    created_at_ms INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS camp_units (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'squad'
        CHECK (kind IN ('squad', 'staff', 'other')),
    created_at_ms INTEGER NOT NULL,
    UNIQUE (session_id, name),
    FOREIGN KEY (session_id) REFERENCES camp_sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS camp_people (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    unit_id INTEGER,
    user_id INTEGER,
    role TEXT NOT NULL
        CHECK (role IN ('child', 'counselor', 'director', 'security', 'medic', 'parent', 'it', 'kitchen')),
    age_band TEXT NOT NULL
        CHECK (age_band IN ('under10', '10_13', '14_17', 'adult')),
    login_name TEXT,
    display_name TEXT NOT NULL,
    birth_date TEXT,
    room TEXT,
    badge_code TEXT UNIQUE,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'left', 'archived')),
    created_at_ms INTEGER NOT NULL,
    updated_at_ms INTEGER NOT NULL,
    FOREIGN KEY (session_id) REFERENCES camp_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (unit_id) REFERENCES camp_units(id) ON DELETE SET NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_camp_people_session ON camp_people(session_id, role, status);
CREATE INDEX IF NOT EXISTS idx_camp_people_unit ON camp_people(unit_id, display_name);
CREATE INDEX IF NOT EXISTS idx_camp_people_badge ON camp_people(badge_code);
CREATE INDEX IF NOT EXISTS idx_camp_people_login ON camp_people(login_name);

CREATE TABLE IF NOT EXISTS camp_guardians (
    person_id INTEGER NOT NULL,
    parent_person_id INTEGER NOT NULL,
    relationship TEXT,
    created_at_ms INTEGER NOT NULL,
    PRIMARY KEY (person_id, parent_person_id),
    FOREIGN KEY (person_id) REFERENCES camp_people(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_person_id) REFERENCES camp_people(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS camp_settings (
    session_id INTEGER PRIMARY KEY,
    quiet_start_minutes INTEGER NOT NULL DEFAULT 1290,
    quiet_end_minutes INTEGER NOT NULL DEFAULT 450,
    allow_child_dm INTEGER NOT NULL DEFAULT 0,
    allow_child_media INTEGER NOT NULL DEFAULT 0,
    require_two_adults_for_dm INTEGER NOT NULL DEFAULT 1,
    photo_watermark TEXT,
    updated_at_ms INTEGER NOT NULL,
    FOREIGN KEY (session_id) REFERENCES camp_sessions(id) ON DELETE CASCADE
);

-- Counselor request queue ----------------------------------------------------

CREATE TABLE IF NOT EXISTS camp_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    unit_id INTEGER,
    child_id INTEGER NOT NULL,
    kind TEXT NOT NULL DEFAULT 'call_counselor'
        CHECK (kind IN ('call_counselor', 'parent_question', 'help')),
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'claimed', 'closed')),
    claimed_by INTEGER,
    note TEXT,
    created_at_ms INTEGER NOT NULL,
    claimed_at_ms INTEGER,
    closed_at_ms INTEGER,
    FOREIGN KEY (session_id) REFERENCES camp_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (child_id) REFERENCES camp_people(id) ON DELETE CASCADE,
    FOREIGN KEY (claimed_by) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_camp_requests_queue
ON camp_requests(session_id, status, created_at_ms);

-- Attendance -----------------------------------------------------------------

CREATE TABLE IF NOT EXISTS camp_attendance_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    unit_id INTEGER NOT NULL,
    kind TEXT NOT NULL DEFAULT 'roll_call'
        CHECK (kind IN ('roll_call', 'lights_out', 'custom')),
    deadline_at_ms INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'closed')),
    created_by INTEGER NOT NULL,
    created_at_ms INTEGER NOT NULL,
    closed_at_ms INTEGER,
    FOREIGN KEY (session_id) REFERENCES camp_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (unit_id) REFERENCES camp_units(id) ON DELETE CASCADE,
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS camp_attendance_marks (
    event_id INTEGER NOT NULL,
    person_id INTEGER NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('present', 'absent', 'sick', 'medic', 'parent', 'left')),
    note TEXT,
    marked_by INTEGER,
    marked_at_ms INTEGER NOT NULL,
    PRIMARY KEY (event_id, person_id),
    FOREIGN KEY (event_id) REFERENCES camp_attendance_events(id) ON DELETE CASCADE,
    FOREIGN KEY (person_id) REFERENCES camp_people(id) ON DELETE CASCADE,
    FOREIGN KEY (marked_by) REFERENCES users(id) ON DELETE SET NULL
);

-- Alerts and playbooks -------------------------------------------------------

CREATE TABLE IF NOT EXISTS camp_alert_playbooks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    steps_json TEXT NOT NULL,
    roles_json TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS camp_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    playbook_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    drill INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'acknowledged', 'closed')),
    zone_id INTEGER,
    note TEXT,
    after_action TEXT,
    created_by INTEGER NOT NULL,
    created_at_ms INTEGER NOT NULL,
    closed_by INTEGER,
    closed_at_ms INTEGER,
    FOREIGN KEY (session_id) REFERENCES camp_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (playbook_id) REFERENCES camp_alert_playbooks(id) ON DELETE RESTRICT,
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (closed_by) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS camp_alert_acks (
    alert_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    step_index INTEGER NOT NULL DEFAULT 0,
    acked_at_ms INTEGER NOT NULL,
    PRIMARY KEY (alert_id, user_id, step_index),
    FOREIGN KEY (alert_id) REFERENCES camp_alerts(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Zones and discrete scans ---------------------------------------------------

CREATE TABLE IF NOT EXISTS camp_zones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'checkpoint',
    parent_id INTEGER,
    UNIQUE (session_id, name),
    FOREIGN KEY (session_id) REFERENCES camp_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_id) REFERENCES camp_zones(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS camp_scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL,
    zone_id INTEGER NOT NULL,
    scanned_at_ms INTEGER NOT NULL,
    device_id TEXT,
    source TEXT NOT NULL DEFAULT 'staff'
        CHECK (source IN ('staff', 'kiosk', 'import')),
    created_at_ms INTEGER NOT NULL,
    FOREIGN KEY (person_id) REFERENCES camp_people(id) ON DELETE CASCADE,
    FOREIGN KEY (zone_id) REFERENCES camp_zones(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_camp_scans_person
ON camp_scans(person_id, scanned_at_ms DESC);
CREATE INDEX IF NOT EXISTS idx_camp_scans_zone
ON camp_scans(zone_id, scanned_at_ms DESC);

-- Pickup and gate movements --------------------------------------------------

CREATE TABLE IF NOT EXISTS camp_pickup_auth (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL,
    adult_name TEXT NOT NULL,
    adult_document TEXT,
    relationship TEXT,
    qr_code TEXT NOT NULL UNIQUE,
    restrictions TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at_ms INTEGER NOT NULL,
    FOREIGN KEY (person_id) REFERENCES camp_people(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS camp_movements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('out', 'in')),
    zone_id INTEGER,
    authorized_by INTEGER,
    pickup_auth_id INTEGER,
    at_ms INTEGER NOT NULL,
    note TEXT,
    FOREIGN KEY (person_id) REFERENCES camp_people(id) ON DELETE CASCADE,
    FOREIGN KEY (zone_id) REFERENCES camp_zones(id) ON DELETE SET NULL,
    FOREIGN KEY (authorized_by) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (pickup_auth_id) REFERENCES camp_pickup_auth(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_camp_movements_person
ON camp_movements(person_id, at_ms DESC);

-- Consent, digest, dietary ---------------------------------------------------

CREATE TABLE IF NOT EXISTS camp_consents (
    person_id INTEGER NOT NULL,
    kind TEXT NOT NULL
        CHECK (kind IN ('internal_chat', 'parent_digest', 'promo', 'none')),
    granted INTEGER NOT NULL DEFAULT 0,
    note TEXT,
    updated_at_ms INTEGER NOT NULL,
    PRIMARY KEY (person_id, kind),
    FOREIGN KEY (person_id) REFERENCES camp_people(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS camp_digest (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    text TEXT NOT NULL,
    photo_id INTEGER,
    created_by INTEGER,
    sent_at_ms INTEGER,
    UNIQUE (person_id, date),
    FOREIGN KEY (person_id) REFERENCES camp_people(id) ON DELETE CASCADE,
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS camp_dietary (
    person_id INTEGER NOT NULL,
    restriction TEXT NOT NULL,
    confirmed_by INTEGER,
    valid_to_ms INTEGER,
    note TEXT,
    PRIMARY KEY (person_id, restriction),
    FOREIGN KEY (person_id) REFERENCES camp_people(id) ON DELETE CASCADE,
    FOREIGN KEY (confirmed_by) REFERENCES users(id) ON DELETE SET NULL
);

-- Duty, handover, imports, audit, kiosks ------------------------------------

CREATE TABLE IF NOT EXISTS camp_duty_shifts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    role TEXT NOT NULL DEFAULT 'counselor',
    starts_at_ms INTEGER NOT NULL,
    ends_at_ms INTEGER NOT NULL,
    note TEXT,
    FOREIGN KEY (session_id) REFERENCES camp_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS camp_handover (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    from_user_id INTEGER,
    to_user_id INTEGER,
    notes TEXT,
    open_items_json TEXT NOT NULL DEFAULT '[]',
    created_at_ms INTEGER NOT NULL,
    acknowledged_at_ms INTEGER,
    FOREIGN KEY (session_id) REFERENCES camp_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (from_user_id) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (to_user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS camp_import_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    created_by INTEGER,
    status TEXT NOT NULL DEFAULT 'preview',
    rows_json TEXT NOT NULL,
    errors_json TEXT NOT NULL DEFAULT '[]',
    result_json TEXT NOT NULL DEFAULT '{}',
    created_at_ms INTEGER NOT NULL,
    committed_at_ms INTEGER,
    FOREIGN KEY (session_id) REFERENCES camp_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS camp_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_user_id INTEGER,
    action TEXT NOT NULL,
    person_id INTEGER,
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at_ms INTEGER NOT NULL,
    FOREIGN KEY (actor_user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS camp_kiosks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL UNIQUE,
    zone_id INTEGER NOT NULL,
    token_hash TEXT NOT NULL,
    scopes TEXT NOT NULL DEFAULT 'scan',
    revoked_at_ms INTEGER,
    last_seen_ms INTEGER,
    created_at_ms INTEGER NOT NULL,
    FOREIGN KEY (zone_id) REFERENCES camp_zones(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS camp_sync_ops (
    op_id TEXT PRIMARY KEY,
    device_id TEXT,
    kind TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    client_at_ms INTEGER,
    status TEXT NOT NULL DEFAULT 'accepted',
    server_at_ms INTEGER NOT NULL
);

-- Default playbooks ----------------------------------------------------------

INSERT OR IGNORE INTO camp_alert_playbooks(kind, title, steps_json, roles_json)
VALUES
('missing_child', 'Пропал ребёнок',
 '[{"step":"Проверить последнюю зону и сканы"},{"step":"Опросить вожатого и отряд"},{"step":"Осмотреть территорию по зонам"},{"step":"Сообщить директору и охране"},{"step":"При необходимости вызвать полицию/родителей"}]',
 '["counselor","director","security"]'),
('evacuation', 'Эвакуация',
 '[{"step":"Включить сирену/оповещение"},{"step":"Вывести отряды в точку сбора"},{"step":"Перекличка по бейджам"},{"step":"Доложить директору"},{"step":"Не возвращаться до разрешения"}]',
 '["counselor","director","security","medic"]'),
('medical', 'Медицинский случай',
 '[{"step":"Не перемещать ребёнка без необходимости"},{"step":"Вызвать медика"},{"step":"Оказать первую помощь"},{"step":"Зафиксировать время и обстоятельства"},{"step":"Связаться с родителем"}]',
 '["counselor","medic","director"]'),
('intruder', 'Посторонний на территории',
 '[{"step":"Не вступать в контакт"},{"step":"Сообщить охране и директору"},{"step":"Увести детей в корпус"},{"step":"Зафиксировать приметы"},{"step":"Дождаться полиции"}]',
 '["security","director","counselor"]'),
('lockdown', 'Lockdown',
 '[{"step":"Закрыть корпуса"},{"step":"Дети в комнатах, тишина"},{"step":"Перекличка по отрядам"},{"step":"Ждать команды директора"},{"step":"Открыть после подтверждения"}]',
 '["security","director","counselor"]');

INSERT OR IGNORE INTO camp_settings(session_id, updated_at_ms)
SELECT id, strftime('%s','now') * 1000 FROM camp_sessions;
