-- Proctoring rules: logins during a running test are counted (never a reason to end it); a test ended by a rule
-- (phone seen twice, more than 5 multi-face episodes or tab switches) keeps the reason.
ALTER TABLE sessions ADD COLUMN relogins INTEGER NOT NULL DEFAULT 0;
ALTER TABLE sessions ADD COLUMN terminated_reason TEXT;
ALTER TABLE sessions ADD COLUMN terminated_at TEXT
