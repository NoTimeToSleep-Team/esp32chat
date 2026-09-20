-- Attachments for user reports (evidence) and blog posts

CREATE TABLE IF NOT EXISTS report_attachments (
    report_id INTEGER NOT NULL,
    attachment_id INTEGER NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (report_id, attachment_id),
    FOREIGN KEY (report_id) REFERENCES user_reports(id) ON DELETE CASCADE,
    FOREIGN KEY (attachment_id) REFERENCES media_attachments(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_report_attachments_attachment
ON report_attachments(attachment_id);

CREATE TABLE IF NOT EXISTS blog_post_attachments (
    post_id INTEGER NOT NULL,
    attachment_id INTEGER NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (post_id, attachment_id),
    FOREIGN KEY (post_id) REFERENCES blog_posts(id) ON DELETE CASCADE,
    FOREIGN KEY (attachment_id) REFERENCES media_attachments(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_blog_post_attachments_attachment
ON blog_post_attachments(attachment_id);
