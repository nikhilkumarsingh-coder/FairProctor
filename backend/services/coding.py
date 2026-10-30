"""Coding tests: problems and their test cases, Run / Submit during the exam, and marks.

A coding test holds programming problems (items with kind = 'code'). Sample tests are shown to the candidate;
hidden tests decide the marks and never leave the server. Every Run and Submit is stored with its code
(code_runs), which the similarity check and the reviewer use later.
"""
from __future__ import annotations

import datetime as dt
import json
import threading

from .. import db
from ..http import ApiError
from . import runner

_busy: set[str] = set()
_busy_lock = threading.Lock()


# ------------------------------------------------------------------ admin: problems
def check_solutions(problems) -> list[dict]:
    """Run each reference solution on the problem's samples + hidden tests. Rows in the CSV 'bad_rows' shape."""
    rows = []
    for i, p in enumerate(problems, start=1):
        if not p.solution:
            continue
        if not runner.available().get(p.solution.language):
            rows.append(dict(line=i, problem=f"'{p.title}': {runner.LANGS[p.solution.language].label} is not installed on this "
                                             "server, so the reference solution could not be checked"))
            continue
        cases = [dict(input=c.input, expected=c.output) for c in [*p.samples, *p.tests]]
        v = runner.judge(p.solution.language, p.solution.code, cases, p.time_limit, show=False)
        if v.verdict != "accepted":
            first = next((t for t in v.tests if t["status"] != "passed"), None)
            where = f" on test {first['n']} ({'sample' if first['n'] <= len(p.samples) else 'hidden'}: {first['status']})" if first else ""
            msg = v.compile_output.splitlines()[0] if v.compile_output else ""
            rows.append(dict(line=i, problem=f"'{p.title}': the reference solution got {v.verdict}{where}. {msg}".strip()))
    return rows


def replace_problems(con, test_id: int, problems) -> int:
    t = db.one(con, "SELECT * FROM tests WHERE id = ?", test_id)
    if t["kind"] != "coding":
        raise ApiError(409, "not_coding", "This is a question test. Upload questions as CSV, or create a coding test.")
    if db.one(con, "SELECT 1 FROM sittings WHERE test_id = ? AND status != 'scheduled'", test_id):
        raise ApiError(409, "test_in_use", "Problems cannot change once a sitting of this test has started.")
    con.execute("DELETE FROM code_tests WHERE test_id = ?", (test_id,))
    con.execute("DELETE FROM items WHERE test_id = ?", (test_id,))
    for pos, p in enumerate(problems):
        opts = dict(title=p.title, languages=list(dict.fromkeys(p.languages)), time_limit=p.time_limit,
                    starter={k: v for k, v in p.starter.items() if k in p.languages})
        con.execute("""INSERT INTO items (test_id, position, kind, text, options, correct_option, difficulty)
                       VALUES (?, ?, 'code', ?, ?, '', NULL)""", (test_id, pos, p.statement, json.dumps(opts, ensure_ascii=False)))
        cases = [(c, 0) for c in p.samples] + [(c, 1) for c in p.tests]
        con.executemany("INSERT INTO code_tests (test_id, item, n, input, expected, hidden) VALUES (?, ?, ?, ?, ?, ?)",
                        [(test_id, pos, n, c.input, c.output, h) for n, (c, h) in enumerate(cases, start=1)])
    return len(problems)


def admin_problems(con, test_id: int) -> list[dict]:
    out = []
    for r in db.all_(con, "SELECT position, text, options FROM items WHERE test_id = ? AND kind = 'code' ORDER BY position", test_id):
        o = json.loads(r["options"])
        cases = db.all_(con, "SELECT n, input, expected, hidden FROM code_tests WHERE test_id = ? AND item = ? ORDER BY n",
                        test_id, r["position"])
        out.append(dict(item=r["position"], title=o.get("title", ""), statement=r["text"], languages=o.get("languages", []),
                        time_limit=o.get("time_limit", 2), starter=o.get("starter", {}),
                        samples=[dict(input=c["input"], output=c["expected"]) for c in cases if not c["hidden"]],
                        hidden=[dict(input=c["input"], output=c["expected"]) for c in cases if c["hidden"]]))
    return out


# ------------------------------------------------------------------ exam
def problem_payload(con, test_id: int, row: dict) -> dict:
    """What the candidate's browser gets for one problem: statement, samples, starter code. Never hidden tests."""
    o = json.loads(row["options"])
    av = runner.available()
    samples = db.all_(con, "SELECT input, expected FROM code_tests WHERE test_id = ? AND item = ? AND hidden = 0 ORDER BY n",
                      test_id, row["position"])
    n_hidden = db.one(con, "SELECT COUNT(*) n FROM code_tests WHERE test_id = ? AND item = ? AND hidden = 1",
                      test_id, row["position"])["n"]
    langs = [dict(key=k, label=runner.LANGS[k].label) for k in o.get("languages", []) if av.get(k)]
    return dict(item=row["position"], kind="code", text=row["text"], options={},
                code=dict(title=o.get("title", ""), languages=langs, time_limit=o.get("time_limit", 2),
                          starter=o.get("starter", {}), samples=[dict(input=s["input"], output=s["expected"]) for s in samples],
                          hidden_tests=n_hidden))


def code_state(con, session_id: str) -> dict:
    """Per problem: the last code the candidate ran or submitted (to restore the editor) and the best submission."""
    out: dict[int, dict] = {}
    for r in db.all_(con, """SELECT item, kind, language, code, verdict, passed, total, id FROM code_runs
                             WHERE session_id = ? ORDER BY id""", session_id):
        s = out.setdefault(r["item"], dict(language=r["language"], code=r["code"], best=None))
        s.update(language=r["language"], code=r["code"])
        if r["kind"] == "submit":
            b = s["best"]
            if b is None or r["passed"] >= b["passed"]:
                s["best"] = dict(verdict=r["verdict"], passed=r["passed"], total=r["total"])
    return {str(k): v for k, v in out.items()}


def _context(con, user: dict, item: int, language: str) -> tuple[dict, dict, dict]:
    from .exam import deadline, my_session, sitting_and_test
    s = my_session(con, user)
    sit, test, _ = sitting_and_test(con, s["sitting_id"])
    if test["kind"] != "coding":
        raise ApiError(409, "not_coding", "This test has no coding problems.")
    if s["status"] != "in_progress":
        raise ApiError(409, "not_in_progress", "The test is not in progress." if s["status"] == "not_started"
                       else "This test has already been submitted.")
    if sit["status"] != "live":
        raise ApiError(409, "sitting_closed", "This sitting is closed.")
    dl = deadline(s, sit, test)
    if dl and dt.datetime.now(dt.timezone.utc) > dl + dt.timedelta(seconds=30):
        raise ApiError(409, "time_over", "Time is over for this test.")
    row = db.one(con, "SELECT * FROM items WHERE test_id = ? AND position = ? AND kind = 'code'", test["id"], item)
    if not row:
        raise ApiError(404, "no_problem", "No such problem in this test.")
    opts = json.loads(row["options"])
    if language not in opts.get("languages", []):
        raise ApiError(422, "language_not_allowed", f"{runner.LANGS[language].label} is not allowed for this problem.")
    if not runner.available().get(language):
        raise ApiError(503, "language_unavailable", f"{runner.LANGS[language].label} is not installed on this server.")
    return s, test, opts


def _one_at_a_time(session_id: str):
    with _busy_lock:
        if session_id in _busy:
            raise ApiError(429, "busy", "Your previous run is still going. Please wait a moment.")
        _busy.add(session_id)


def _done(session_id: str):
    with _busy_lock:
        _busy.discard(session_id)


def run(user: dict, body) -> dict:
    """Run on the sample tests (inputs, outputs and errors shown), or once on the candidate's own input."""
    with db.tx() as con:
        s, test, opts = _context(con, user, body.item, body.language)
        samples = db.all_(con, "SELECT input, expected FROM code_tests WHERE test_id = ? AND item = ? AND hidden = 0 ORDER BY n",
                          test["id"], body.item)
    _one_at_a_time(s["id"])
    try:
        if body.input is not None:
            r = runner.run_custom(body.language, body.code, body.input, opts.get("time_limit", 2))
            out = dict(mode="custom", **r)
            verdict, passed, total = r["status"], 0, 0
        else:
            v = runner.judge(body.language, body.code, [dict(input=x["input"], expected=x["expected"]) for x in samples],
                             opts.get("time_limit", 2), show=True)
            out = dict(mode="samples", verdict=v.verdict, passed=v.passed, total=v.total, compile_output=v.compile_output,
                       tests=v.tests, seconds=v.seconds)
            verdict, passed, total = v.verdict, v.passed, v.total
    finally:
        _done(s["id"])
    with db.tx() as con:
        con.execute("""INSERT INTO code_runs (session_id, item, kind, language, code, verdict, passed, total, t)
                       VALUES (?, ?, 'run', ?, ?, ?, ?, ?, ?)""", (s["id"], body.item, body.language, body.code, verdict,
                                                                    passed, total, body.t))
    return out


def submit(user: dict, body) -> dict:
    """Judge on the hidden tests. Only pass / fail per test comes back, never the tests themselves."""
    with db.tx() as con:
        s, test, opts = _context(con, user, body.item, body.language)
        cases = db.all_(con, "SELECT input, expected FROM code_tests WHERE test_id = ? AND item = ? AND hidden = 1 ORDER BY n",
                        test["id"], body.item)
    _one_at_a_time(s["id"])
    try:
        v = runner.judge(body.language, body.code, [dict(input=x["input"], expected=x["expected"]) for x in cases],
                         opts.get("time_limit", 2), show=False)
    finally:
        _done(s["id"])
    with db.tx() as con:
        con.execute("""INSERT INTO code_runs (session_id, item, kind, language, code, verdict, passed, total, t)
                       VALUES (?, ?, 'submit', ?, ?, ?, ?, ?, ?)""", (s["id"], body.item, body.language, body.code, v.verdict,
                                                                       v.passed, v.total, body.t))
        db.audit(con, user["id"], "code_submitted", s["id"], item=body.item, verdict=v.verdict, passed=v.passed, total=v.total)
    first = v.compile_output.strip()
    return dict(verdict=v.verdict, passed=v.passed, total=v.total, seconds=v.seconds,
                tests=[dict(n=t["n"], status=t["status"]) for t in v.tests], compile_output=first[:3000])


def marks(con, session_id: str, test_id: int) -> dict:
    """Best submission per problem; each problem is worth 100 marks shared equally by its hidden tests."""
    probs = db.all_(con, "SELECT position, options FROM items WHERE test_id = ? AND kind = 'code' ORDER BY position", test_id)
    state = code_state(con, session_id)
    rows, total = [], 0.0
    for p in probs:
        best = (state.get(str(p["position"])) or {}).get("best")
        m = round(100 * best["passed"] / best["total"], 1) if best and best["total"] else 0.0
        total += m
        rows.append(dict(item=p["position"], title=json.loads(p["options"]).get("title", ""), marks=m,
                         verdict=best["verdict"] if best else "not_submitted",
                         passed=best["passed"] if best else 0, total=best["total"] if best else 0))
    return dict(problems=rows, marks=round(total, 1), out_of=100 * len(probs))
