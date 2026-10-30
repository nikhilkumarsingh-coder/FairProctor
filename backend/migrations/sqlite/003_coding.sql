-- Coding tests: a test is either 'mcq' (questions with options or short answers) or 'coding' (programming problems).
ALTER TABLE tests ADD COLUMN kind TEXT NOT NULL DEFAULT 'mcq';

-- extra numbers for an event, as JSON (e.g. typing stats for a code editor window: inserted, deleted, keys)
ALTER TABLE events ADD COLUMN meta TEXT;

-- test cases of a coding problem; hidden ones never leave the server
CREATE TABLE code_tests (
    id              INTEGER PRIMARY KEY,
    test_id         INTEGER NOT NULL REFERENCES tests(id) ON DELETE CASCADE,
    item            INTEGER NOT NULL,            -- the problem's position in the test
    n               INTEGER NOT NULL,
    input           TEXT NOT NULL,
    expected        TEXT NOT NULL,
    hidden          INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX code_tests_item ON code_tests (test_id, item, n);

-- every Run and Submit with the code, for marks, the similarity check and the reviewer
CREATE TABLE code_runs (
    id              INTEGER PRIMARY KEY,
    session_id      TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    item            INTEGER NOT NULL,
    kind            TEXT NOT NULL CHECK (kind IN ('run', 'submit')),
    language        TEXT NOT NULL,
    code            TEXT NOT NULL,
    verdict         TEXT NOT NULL,
    passed          INTEGER NOT NULL DEFAULT 0,
    total           INTEGER NOT NULL DEFAULT 0,
    t               REAL,                        -- seconds into the test, from the browser's clock
    at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX code_runs_session ON code_runs (session_id, item, kind);
