-- Camera snapshots taken only at flagged moments (a second person, no face, a phone in view, returning to the test tab).
-- Small JPEGs stored as base64; seen only by reviewers and the candidate; deleted after SNAPSHOT_DAYS (default 30).
-- Never an input to the model.
CREATE TABLE snapshots (
    id              INTEGER PRIMARY KEY,
    session_id      TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    t               REAL NOT NULL,
    reason          TEXT NOT NULL,
    phase           TEXT NOT NULL DEFAULT 'at',
    image           TEXT NOT NULL,
    bytes           INTEGER NOT NULL,
    created_at      TEXT NOT NULL
);
CREATE INDEX snapshots_session ON snapshots (session_id, t);
CREATE INDEX snapshots_created ON snapshots (created_at);
