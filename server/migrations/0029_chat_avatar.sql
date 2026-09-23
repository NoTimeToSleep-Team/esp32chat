PRAGMA foreign_keys = ON;

-- Chat photo: file name inside <storage_root>/chat_avatars.
ALTER TABLE chats ADD COLUMN avatar_path TEXT;
