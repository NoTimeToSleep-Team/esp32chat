PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS blog_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    body_text TEXT NOT NULL,
    author_user_id INTEGER NOT NULL,
    published_at_ms INTEGER NOT NULL,
    updated_at_ms INTEGER NOT NULL,
    FOREIGN KEY (author_user_id) REFERENCES users(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_blog_posts_published_at
ON blog_posts(published_at_ms DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_blog_posts_author
ON blog_posts(author_user_id);
