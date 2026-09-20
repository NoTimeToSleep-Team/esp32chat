-- Debug tracing for client actions (temporary debug mode)
-- stage 'server': request received by server (middleware, X-Debug-Trace header)
-- stage 'client': client-side outcome (stage 1 = sent, 2 = response received, 3 = acknowledged)
-- stage 'toast': error toast shown in UI

CREATE TABLE IF NOT EXISTS debug_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at_ms INTEGER NOT NULL,
    stage TEXT NOT NULL,
    trace_id TEXT,
    action TEXT,
    method TEXT,
    status INTEGER,
    ok INTEGER,
    stages_done INTEGER,
    error TEXT,
    details TEXT,
    user_login TEXT,
    ip TEXT,
    t1_ms INTEGER,
    t2_ms INTEGER,
    t3_ms INTEGER
);

CREATE INDEX IF NOT EXISTS idx_debug_events_time
ON debug_events(created_at_ms DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_debug_events_trace
ON debug_events(trace_id);
