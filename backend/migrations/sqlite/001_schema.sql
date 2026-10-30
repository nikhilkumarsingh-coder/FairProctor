-- FairProctor schema (SQLite, local development). Camera images are never stored: frame_stats holds numbers only.

CREATE TABLE users (
    id              INTEGER PRIMARY KEY,
    role            TEXT NOT NULL CHECK (role IN ('admin', 'reviewer', 'candidate')),
    name            TEXT NOT NULL,
    email           TEXT UNIQUE,                 -- email login (staff, and candidates who sign up)
    roll_no         TEXT,                        -- candidate imported by the admin: roll no. + code login
    sitting_id      INTEGER REFERENCES sittings(id) ON DELETE CASCADE,
    secret_hash     TEXT NOT NULL,               -- password or login code, scrypt hash
    language        TEXT NOT NULL DEFAULT 'en',
    failed_logins   INTEGER NOT NULL DEFAULT 0,
    locked_until    TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE UNIQUE INDEX users_roll ON users (sitting_id, roll_no) WHERE roll_no IS NOT NULL;

-- logged-out JWTs (by id) until they would have expired anyway
CREATE TABLE revoked_tokens (
    jti             TEXT PRIMARY KEY,
    expires_at      TEXT NOT NULL
);

CREATE TABLE tests (
    id              INTEGER PRIMARY KEY,
    title           TEXT NOT NULL,
    duration_min    INTEGER NOT NULL CHECK (duration_min BETWEEN 1 AND 600),
    created_by      INTEGER REFERENCES users(id),
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE items (
    id              INTEGER PRIMARY KEY,
    test_id         INTEGER NOT NULL REFERENCES tests(id) ON DELETE CASCADE,
    position        INTEGER NOT NULL,            -- 0-based; this is the "item" number the scorer uses
    kind            TEXT NOT NULL DEFAULT 'mcq',
    text            TEXT NOT NULL,
    options         TEXT NOT NULL,               -- JSON {"A": "...", "B": "...", ...}
    correct_option  TEXT NOT NULL,
    difficulty      REAL,
    UNIQUE (test_id, position)
);

CREATE TABLE sittings (
    id              INTEGER PRIMARY KEY,
    test_id         INTEGER NOT NULL REFERENCES tests(id),
    title           TEXT NOT NULL,
    starts_at       TEXT NOT NULL,
    ends_at         TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'scheduled'
                    CHECK (status IN ('scheduled', 'live', 'closed', 'scoring', 'scored')),
    join_code       TEXT NOT NULL UNIQUE,        -- candidates who signed up join with this
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    closed_at       TEXT,
    scored_at       TEXT
);

CREATE TABLE sessions (
    id              TEXT PRIMARY KEY,
    sitting_id      INTEGER NOT NULL REFERENCES sittings(id) ON DELETE CASCADE,
    user_id         INTEGER REFERENCES users(id) ON DELETE SET NULL,   -- NULL for synthetic reference sessions
    status          TEXT NOT NULL DEFAULT 'not_started'
                    CHECK (status IN ('not_started', 'in_progress', 'submitted')),
    started_at      TEXT,
    submitted_at    TEXT,
    device          TEXT NOT NULL DEFAULT 'desktop',
    bandwidth_class TEXT NOT NULL DEFAULT 'normal',     -- reporting only, never a model input
    precheck_light  TEXT NOT NULL DEFAULT 'ok',
    precheck_framing TEXT NOT NULL DEFAULT 'ok',
    is_synthetic    INTEGER NOT NULL DEFAULT 0,
    last_seq        INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX sessions_sitting ON sessions (sitting_id);
CREATE INDEX sessions_user ON sessions (user_id);

CREATE TABLE events (
    session_id      TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    seq             INTEGER NOT NULL,
    t               REAL NOT NULL,               -- seconds since the session started (phone clock, monotonic)
    type            TEXT NOT NULL,
    item            INTEGER NOT NULL DEFAULT -1,
    option          TEXT NOT NULL DEFAULT '',
    correct         INTEGER NOT NULL DEFAULT -1, -- filled by the server, never sent by the browser
    chars           INTEGER NOT NULL DEFAULT 0,  -- paste length only, never the text
    PRIMARY KEY (session_id, seq)
);
CREATE INDEX events_time ON events (session_id, t);

CREATE TABLE frame_stats (
    session_id      TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    seq             INTEGER NOT NULL,
    t               REAL NOT NULL,
    faces           INTEGER NOT NULL,
    face_visible    INTEGER NOT NULL,
    gaze            TEXT NOT NULL,               -- coarse head direction: centre/down/left/right/away/unknown
    brightness      REAL,
    blur            REAL,
    PRIMARY KEY (session_id, seq)
);

CREATE TABLE consents (
    id              INTEGER PRIMARY KEY,
    session_id      TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    version         TEXT NOT NULL,
    camera_ok       INTEGER NOT NULL,
    precheck_share_ok INTEGER NOT NULL,
    accepted_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE precheck_results (
    id              INTEGER PRIMARY KEY,
    session_id      TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    data            TEXT NOT NULL,               -- JSON of numbers only
    at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE scores (
    session_id      TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
    sitting_id      INTEGER NOT NULL REFERENCES sittings(id) ON DELETE CASCADE,
    raw             REAL NOT NULL,
    prob            REAL NOT NULL,
    priority        INTEGER NOT NULL,            -- 0-100, 50 = review line; not a probability of cheating
    band            TEXT NOT NULL CHECK (band IN ('review_first', 'review', 'clear')),
    rank            INTEGER NOT NULL,
    families        TEXT NOT NULL,               -- JSON list, for filtering
    explanation     TEXT NOT NULL,               -- JSON from fairproctor.explain
    model_version   TEXT NOT NULL,
    scored_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX scores_queue ON scores (sitting_id, band, priority DESC);

CREATE TABLE reviews (
    id              INTEGER PRIMARY KEY,
    session_id      TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    reviewer_id     INTEGER REFERENCES users(id),
    decision        TEXT NOT NULL CHECK (decision IN ('confirm', 'clear', 'need_more')),
    note            TEXT NOT NULL DEFAULT '',
    at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE session_views (
    session_id      TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    reviewer_id     INTEGER NOT NULL REFERENCES users(id),
    at              TEXT NOT NULL,
    PRIMARY KEY (session_id, reviewer_id)
);

CREATE TABLE appeals (
    id              INTEGER PRIMARY KEY,
    session_id      TEXT NOT NULL UNIQUE REFERENCES sessions(id) ON DELETE CASCADE,
    text            TEXT NOT NULL,
    moments         TEXT NOT NULL DEFAULT '[]',
    status          TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'decided')),
    outcome         TEXT CHECK (outcome IN ('upheld', 'overturned')),
    response        TEXT,
    reviewer_id     INTEGER REFERENCES users(id),
    at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    decided_at      TEXT
);

CREATE TABLE deletion_requests (
    id              INTEGER PRIMARY KEY,
    session_id      TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    status          TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'done', 'rejected')),
    at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE jobs (
    id              INTEGER PRIMARY KEY,
    kind            TEXT NOT NULL,
    target          TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'done', 'failed')),
    progress        REAL NOT NULL DEFAULT 0,
    message         TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    finished_at     TEXT
);

-- kept after a session is deleted, so it is never tied to the deleted row
CREATE TABLE audit_log (
    id              INTEGER PRIMARY KEY,
    actor_id        INTEGER,
    action          TEXT NOT NULL,
    target          TEXT NOT NULL DEFAULT '',
    detail          TEXT NOT NULL DEFAULT '{}',
    at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
