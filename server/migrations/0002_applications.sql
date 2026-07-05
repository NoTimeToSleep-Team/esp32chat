PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    phone TEXT NOT NULL,
    email TEXT NOT NULL,
    class_group TEXT NOT NULL,
    is_school_member INTEGER NOT NULL CHECK (is_school_member IN (0, 1)),
    status TEXT NOT NULL CHECK (status IN ('pending', 'in_review', 'approved', 'rejected')),
    review_note TEXT,
    reviewed_by_user_id INTEGER,
    created_at_ms INTEGER NOT NULL,
    updated_at_ms INTEGER NOT NULL,
    FOREIGN KEY (reviewed_by_user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);
CREATE INDEX IF NOT EXISTS idx_applications_created_at_ms ON applications(created_at_ms);
CREATE INDEX IF NOT EXISTS idx_applications_phone ON applications(phone);
CREATE INDEX IF NOT EXISTS idx_applications_email ON applications(email);
