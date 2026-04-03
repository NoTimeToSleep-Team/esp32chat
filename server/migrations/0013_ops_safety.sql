PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS ops_backup_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    backup_name TEXT NOT NULL UNIQUE,
    backup_path TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('dry_run', 'completed', 'failed')),
    reason TEXT,
    trigger_kind TEXT NOT NULL CHECK (trigger_kind IN ('manual', 'shutdown', 'auto')),
    actor_user_id INTEGER,
    created_at_ms INTEGER NOT NULL,
    completed_at_ms INTEGER,
    size_bytes INTEGER,
    checksum_sha256 TEXT,
    error_message TEXT,
    FOREIGN KEY (actor_user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_ops_backup_created
ON ops_backup_history(created_at_ms DESC, id DESC);

CREATE TABLE IF NOT EXISTS ops_incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_key TEXT NOT NULL UNIQUE,
    level TEXT NOT NULL CHECK (level IN ('info', 'warning', 'critical')),
    title TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}',
    source TEXT,
    status TEXT NOT NULL CHECK (status IN ('open', 'resolved')),
    created_at_ms INTEGER NOT NULL,
    updated_at_ms INTEGER NOT NULL,
    resolved_at_ms INTEGER,
    created_by_user_id INTEGER,
    resolved_by_user_id INTEGER,
    resolution_note TEXT,
    FOREIGN KEY (created_by_user_id) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (resolved_by_user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_ops_incidents_status_created
ON ops_incidents(status, created_at_ms DESC, id DESC);

CREATE TABLE IF NOT EXISTS ops_shutdown_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_kind TEXT NOT NULL CHECK (run_kind IN ('dry_run', 'execute')),
    requested_by_user_id INTEGER,
    reason TEXT,
    status TEXT NOT NULL CHECK (status IN ('completed', 'failed')),
    started_at_ms INTEGER NOT NULL,
    finished_at_ms INTEGER,
    steps_json TEXT NOT NULL DEFAULT '[]',
    FOREIGN KEY (requested_by_user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_ops_shutdown_runs_started
ON ops_shutdown_runs(started_at_ms DESC, id DESC);

CREATE TABLE IF NOT EXISTS ops_runtime_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    degraded_mode INTEGER NOT NULL CHECK (degraded_mode IN (0, 1)),
    reason TEXT,
    updated_by_user_id INTEGER,
    updated_at_ms INTEGER NOT NULL,
    FOREIGN KEY (updated_by_user_id) REFERENCES users(id) ON DELETE SET NULL
);

INSERT OR IGNORE INTO ops_runtime_state(id, degraded_mode, reason, updated_by_user_id, updated_at_ms)
VALUES (1, 0, NULL, NULL, 0);
