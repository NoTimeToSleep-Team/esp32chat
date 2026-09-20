-- Rebuild attachment link tables with ON DELETE CASCADE for attachment_id.
-- Previously ON DELETE RESTRICT made user deletion fail (500) when the user
-- owned any attachment (chat message, support message, report or blog post).
-- Link rows are only references; cascading them away is safe.

PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS chat_message_attachments;
CREATE TABLE chat_message_attachments (
    message_id INTEGER NOT NULL,
    attachment_id INTEGER NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (message_id, attachment_id),
    FOREIGN KEY (message_id) REFERENCES chat_messages(id) ON DELETE CASCADE,
    FOREIGN KEY (attachment_id) REFERENCES media_attachments(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chat_message_attachments_attachment
ON chat_message_attachments(attachment_id);

DROP TABLE IF EXISTS support_message_attachments;
CREATE TABLE support_message_attachments (
    message_id INTEGER NOT NULL,
    attachment_id INTEGER NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (message_id, attachment_id),
    FOREIGN KEY (message_id) REFERENCES support_messages(id) ON DELETE CASCADE,
    FOREIGN KEY (attachment_id) REFERENCES media_attachments(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_support_message_attachments_attachment
ON support_message_attachments(attachment_id);

DROP TABLE IF EXISTS report_attachments;
CREATE TABLE report_attachments (
    report_id INTEGER NOT NULL,
    attachment_id INTEGER NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (report_id, attachment_id),
    FOREIGN KEY (report_id) REFERENCES user_reports(id) ON DELETE CASCADE,
    FOREIGN KEY (attachment_id) REFERENCES media_attachments(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_report_attachments_attachment
ON report_attachments(attachment_id);

DROP TABLE IF EXISTS blog_post_attachments;
CREATE TABLE blog_post_attachments (
    post_id INTEGER NOT NULL,
    attachment_id INTEGER NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (post_id, attachment_id),
    FOREIGN KEY (post_id) REFERENCES blog_posts(id) ON DELETE CASCADE,
    FOREIGN KEY (attachment_id) REFERENCES media_attachments(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_blog_post_attachments_attachment
ON blog_post_attachments(attachment_id);
