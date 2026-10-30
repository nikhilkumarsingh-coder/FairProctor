-- A reviewer can reopen a test that a proctoring rule ended, while the sitting's time window is still open.
-- extra_seconds: time given back (the minutes the test stood ended); rules_reset: per event type, the exam-clock time
-- up to which that rule's earlier events no longer count; rule_history: ended / reopened, with who and why.
ALTER TABLE sessions ADD COLUMN extra_seconds REAL NOT NULL DEFAULT 0;
ALTER TABLE sessions ADD COLUMN rules_reset TEXT;
ALTER TABLE sessions ADD COLUMN rule_history TEXT
