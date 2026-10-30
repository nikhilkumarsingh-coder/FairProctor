-- Changing a password (or an admin resetting a login code) bumps token_version; tokens that carry an older
-- version stop working, so other devices are logged out.
ALTER TABLE users ADD COLUMN password_changed_at TEXT;
ALTER TABLE users ADD COLUMN token_version INTEGER NOT NULL DEFAULT 0;
