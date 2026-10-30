"""Settings, read from environment variables each time (so tests can switch databases).

Production (Render): set DATABASE_URL (PostgreSQL, e.g. Neon), FP_JWT_SECRET, FP_CORS_ORIGINS,
FP_ADMIN_EMAIL and FP_ADMIN_PASSWORD. Local: nothing is required (SQLite file + a dev JWT secret).
"""
import os
import secrets

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "backend", "data")


def get(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def database_url() -> str:
    """postgresql://user:pass@host/db  (PostgreSQL)  or  sqlite:///path/to/file.db  (local development)."""
    url = get("DATABASE_URL") or get("FP_DATABASE_URL")
    if url:
        return url.replace("postgres://", "postgresql://", 1)   # Render/Heroku style
    return "sqlite:///" + get("FP_DB", os.path.join(DATA_DIR, "fairproctor.db"))


def is_postgres() -> bool:
    return database_url().startswith("postgresql://")


def demo_mode() -> bool:
    """Show the demo logins on the login page. FP_DEMO=1 turns it on, FP_DEMO=0 off; unset: on only with local SQLite."""
    v = (get("FP_DEMO", "") or "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return not is_postgres()


def db_path() -> str:
    """SQLite file path (only meaningful when not on PostgreSQL)."""
    return database_url()[len("sqlite:///"):]


def jwt_secret() -> str:
    s = get("FP_JWT_SECRET")
    if s:
        return s
    # development only: a random secret kept in backend/data so logins survive restarts
    path = os.path.join(DATA_DIR, ".jwt_secret")
    private_dir(DATA_DIR)
    if not os.path.exists(path):
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(secrets.token_urlsafe(48))
    _private(path, 0o600)
    with open(path) as fh:
        return fh.read().strip()


def private_dir(path: str) -> None:
    """Server-only folder: candidate code runs as an unprivileged user and must not read secrets or the database."""
    os.makedirs(path, exist_ok=True)
    _private(path, 0o700)


def _private(path: str, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError:          # e.g. a mounted volume that does not allow it; Windows ignores most modes
        pass


def artifacts_dir() -> str:
    """The scoring model: backend/model (shipped with the app), unless FAIRPROCTOR_ARTIFACTS points elsewhere."""
    if get("FAIRPROCTOR_ARTIFACTS"):
        return get("FAIRPROCTOR_ARTIFACTS")
    shipped = os.path.join(ROOT, "backend", "model")
    return shipped if os.path.exists(os.path.join(shipped, "model.pkl")) else os.path.join(ROOT, "artifacts")


def demo_data_dir() -> str:
    return get("FP_DEMO_DATA", os.path.join(ROOT, "backend", "demo_data"))


def frontend_dist() -> str:
    return get("FP_FRONTEND_DIST", os.path.join(ROOT, "frontend", "dist"))


def retention_days() -> int:
    return int(get("RETENTION_DAYS", "90"))


def allow_signup() -> bool:
    """Candidates do not create their own accounts: the admin imports them (roll no. + code). FP style override for
    old setups only: ALLOW_SIGNUP=1 brings back /api/auth/signup and /api/exam/join."""
    return get("ALLOW_SIGNUP", "0") == "1"


def token_hours() -> int:
    return int(get("FP_TOKEN_HOURS", "12"))


def cors_origins() -> list[str]:
    return [o.strip().rstrip("/") for o in get("FP_CORS_ORIGINS").split(",") if o.strip()]


CONSENT_VERSION = "2026-10-v4"        # v2: camera required, snapshots. v3: microphone check. v4: full screen (kiosk)


def snapshot_days() -> int:
    """Camera snapshots are deleted after this many days (sooner than the rest of the record)."""
    return int(get("SNAPSHOT_DAYS", "30"))


SNAPSHOT_REASONS = {"two_people", "no_face", "phone", "tab_return"}
SNAPSHOT_PHASES = {"before", "at", "after"}
SNAPSHOT_MAX_BYTES = 40_000        # one small JPEG (about 240x180)
SNAPSHOT_MAX_PER_SESSION = 30
MIN_SITTING_FOR_OWN_STATS = 50     # fewer candidates than this -> reuse the trained paper statistics
MAX_LOGIN_FAILS = 5
LOCK_MINUTES = 5
APPEAL_DAYS = 7
EVENT_TYPES = {"item_shown", "answer", "focus_lost", "focus_gained", "paste", "idle_start", "idle_end",
               "code_typing", "code_run", "code_submit",        # coding tests: typing stats every few seconds, runs, submits
               "phone_seen", "multi_face", "offline_start", "offline_end",   # proctoring rules (services/rules.py)
               "speech_like", "mic_on", "mic_off",                          # microphone check (services/audio.py)
               "fullscreen_exit", "fullscreen_enter"}                       # kiosk mode (services/device.py); never a rule
# Microphone "speech-like sound" check (frontend/src/lib/speech.ts; validated in reports/BROWSER_SPEECH_CHECK.md):
# off | optional (the candidate may allow it) | required (needed to start). It never raises a score on its own.
# Kiosk mode (services/device.py): the test runs in full screen with the screen kept on, except inside Safe Exam
# Browser. Leaving full screen is noted for the reviewer and never counted as a rule. FP_KIOSK=off switches it off.
KIOSK = os.environ.get("FP_KIOSK", "on").strip().lower() not in ("off", "0", "false", "no")
MIC_MODE = os.environ.get("FP_MIC", "optional").strip().lower()
if MIC_MODE not in ("off", "optional", "required"):
    MIC_MODE = "optional"
# Proctoring rules (services/rules.py). The device checks the camera every second; a "phone seen" is a phone in at
# least 2 of 5 seconds, a "multi-face" episode is 2+ faces for 5 seconds in a row.
PHONE_WARNINGS = 1          # the first phone seen is a warning; the next one ends the test
MULTI_FACE_MAX = 5          # more than this many multi-face episodes ends the test
TAB_SWITCH_MAX = 5          # more than this many tab/app switches ends the test
DISCONNECT_MAX = 5          # more than this many disconnects, each followed quickly by an answer: a flag, never an end
RECONNECT_ANSWER_S = 15     # "answered right after reconnecting": within this many seconds
RELOGIN_REVIEW = 2          # logging in again during the test is counted; from this many it goes to review
GAZE = {"centre", "down", "left", "right", "away", "unknown"}
