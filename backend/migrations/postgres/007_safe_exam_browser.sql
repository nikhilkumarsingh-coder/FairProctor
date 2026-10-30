-- Safe Exam Browser (optional, per sitting; laptop/iPad exams only: SEB has no Android version).
-- seb_config_key: the Config Key from the SEB Config Tool (64 hex). seb_file: the .seb file (base64) candidates open.
ALTER TABLE sittings ADD COLUMN seb_required INTEGER NOT NULL DEFAULT 0;
ALTER TABLE sittings ADD COLUMN seb_config_key TEXT;
ALTER TABLE sittings ADD COLUMN seb_file TEXT;
ALTER TABLE sittings ADD COLUMN seb_token TEXT
