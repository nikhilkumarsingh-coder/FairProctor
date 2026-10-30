#!/bin/sh
# Start FairProctor in a container: wait for the database, optionally load the demo data once, then serve.
set -e

python - <<'PY'
import os, time
url = os.environ.get("DATABASE_URL") or os.environ.get("FP_DATABASE_URL") or ""
if url.startswith(("postgres://", "postgresql://")):
    import psycopg
    url = url.replace("postgres://", "postgresql://", 1)
    for attempt in range(60):
        try:
            psycopg.connect(url, connect_timeout=3).close()
            break
        except Exception as e:
            print(f"waiting for the database ({type(e).__name__}) ...", flush=True)
            time.sleep(2)
    else:
        raise SystemExit("database not reachable")
PY

# FP_SEED_DEMO=1: build the demo data (logins, tests, sittings, Priya and Rahul) the first time only
if [ "${FP_SEED_DEMO:-0}" = "1" ]; then
    python -m backend.scripts.seed_demo --if-empty
fi

# one process: the scoring job queue and the live-monitor cache live inside it
exec python -m uvicorn backend.app:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips="*"
