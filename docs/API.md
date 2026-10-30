# FairProctor web API

Base URL: `http://127.0.0.1:8000` locally, or the Render URL when deployed. Interactive docs: **`/docs`** (Swagger).
All bodies are JSON unless marked CSV. The backend is **FastAPI**; the database is **PostgreSQL** in production
(SQLite locally when `DATABASE_URL` is not set).

**Auth = JWT.** Login returns `access_token`. Send it on every request:

```
Authorization: Bearer <access_token>
```

The token expires after 12 hours (`expires_at`). Logout revokes it. (Login also sets an HttpOnly cookie
`fp_token`, which only helps when the frontend is served by the same server.)

**Errors** always look like:

```json
{"error": {"code": "not_logged_in", "message": "Please log in."}}
```

`422 invalid` also carries `fields: [{field, problem}]`; CSV uploads with bad rows return `400 bad_rows` with `rows: [{line, problem}]`.

| Status | Meaning |
|---|---|
| 401 `not_logged_in` | no, expired or revoked token → send to `/login` (staff: `/staff/login`) |
| 401 `session_expired` | the password was changed on another device (or an admin reset the login code) → send to the login page |
| 403 `not_allowed` | wrong role for this page |
| 409 | the action is not possible in the current state (message says why, show it to the user) |
| 429 `locked` | 5 wrong logins → wait 5 minutes |

## Roles

| Role | Who | How they get an account |
|---|---|---|
| `candidate` (the "user" role) | test takers | imported by an admin (roll no. + login code); there is no self sign-up |
| `reviewer` | integrity reviewers | created by an admin |
| `admin` | the test team | the first one from `FP_ADMIN_EMAIL` / `FP_ADMIN_PASSWORD`; more via `POST /api/admin/users` |

## Auth (everyone)

| Method | Path | Body → Response |
|---|---|---|
| POST | `/api/auth/signup` | off: `410 signup_disabled` (only with `ALLOW_SIGNUP=1`) |
| POST | `/api/auth/login` | `{email, password}` (staff) or `{roll_no, code}` (candidate), plus `app: "candidate"\|"staff"` → `{access_token, token_type, expires_at, user}` · 403 `wrong_app` when the account belongs to the other app |
| POST | `/api/demo/candidate` | demo mode only: `{kind: mcq\|coding, language}` → a fresh demo candidate already in the demo sitting, `201 {access_token, …}` |
| POST | `/api/auth/logout` | → `{ok}` (the token stops working) |
| GET | `/api/me` | → `{id, role, name, email, roll_no, sitting_id, language, created_at, has_password}` (`has_password` is false for roll no. + code candidates) |
| PATCH | `/api/me` | `{name?, language?: en\|hi}` → the same as `GET /api/me`. Role, email and roll no. cannot be changed here; an imported candidate's name is locked (`400 name_locked`) |
| POST | `/api/auth/change-password` | `{current_password, new_password (8+, letters and numbers)}` → a fresh `{access_token, …}` for this device; every other token of this user stops working (`401 session_expired`). `400 wrong_password` (counts towards the 5-try lock) · `422 same_password` · `400 no_password` for roll no. + code candidates |

After login, route by `user.role`: `admin` → `/admin`, `reviewer` → `/review`, `candidate` → `/exam`.

**Demo mode.** `GET /api/demo` (no login) → `{enabled: false}`, or in demo mode `{enabled: true, staff[{role, email,
password}], story[{key, roll_no, code, name}], join_codes{mcq?, coding?}}`: the public demo logins the login page
shows as one-click buttons. Demo mode is on with `FP_DEMO=1`, off with `FP_DEMO=0`, and when unset only with the
local SQLite database (never on PostgreSQL by default). It also needs the demo accounts from `seed_demo`.

## Candidate (`role = candidate`)

| Method | Path | Body → Response |
|---|---|---|
| POST | `/api/exam/join` | `{join_code}` (e.g. `FP-DEMO26`) → same as `/api/exam/me` · 404 `bad_join_code` |
| GET | `/api/exam/me` | → `{join_needed, session{id,status,started_at,deadline,reopened}, sitting{title,starts_at,ends_at,status}, test{title,duration_min,n_items}, consent{given,version_needed,…}, can_start, result_ready, retention_days, server_now, seb{required, exempt?: "phone", …}, kiosk}` (SEB is required on laptops only: a phone gets `required: false, exempt: "phone"`; `kiosk`: run in full screen) |
| POST | `/api/exam/consent` | `{version, understood: true, camera_ok, precheck_share_ok}` → `{ok}` · `version` must equal `consent.version_needed` |
| POST | `/api/exam/precheck` | numbers only `{brightness, backlight, face_found, face_size, blur, down_kbps, up_kbps, camera_ok, passed}` → `{stored}` (stored only if the candidate allowed it) |
| GET / POST | `/api/precheck/probe?kb=200` | speed test: GET downloads random bytes, POST uploads any bytes → `{bytes}` |
| POST | `/api/exam/start` | `{signals{touch, w, h, coarse, fullscreen, wake_lock} (for the device check), device: phone\|desktop, bandwidth_class: low\|normal, precheck_light: ok\|dim\|bright\|backlit, precheck_framing: ok\|off_centre\|too_far\|no_face}` → `{session_id, started_at, deadline, server_now, elapsed_s, last_seq, items[{item, kind, text, options}], answers{item: option}}`. Calling it again **resumes** (refresh-safe). Correct answers are never sent. |
| POST | `/api/exam/events` | batch, see below → `{saved, duplicates, rejected, saved_upto}` |
| POST | `/api/exam/submit` | → `{status: "submitted"}` |
| GET | `/api/exam/result` | → `{state, message, not_counted[], summary?, points[{title, text, when, questions}], can_appeal, appeal?, reviewer_note?}` |
| POST | `/api/exam/appeal` | `{text (5–4000 chars), moments: [seconds]}` → `{ok, message}` |
| POST | `/api/exam/delete-request` | → `{ok, message}` |

When `join_needed` is true (the candidate is in no sitting), show "Ask your test centre" — there is no join code any more.

`state` is one of `pending`, `clear`, `under_review`, `cleared_after_review`, `confirmed`, `cleared_after_appeal`. The candidate never sees a score.

### Event batch (Parts 5–7)

Every record gets a **`seq` from one counter per session** (events and frames share it, starting at 1).
Keep unsent records in IndexedDB, send the oldest first every ~10 s, and delete everything `≤ saved_upto` after a 200.
Sending the same batch twice is safe: records are stored once.

```json
{
  "events": [
    {"seq": 1, "t": 2.1,  "type": "item_shown", "item": 0},
    {"seq": 2, "t": 31.8, "type": "answer", "item": 0, "option": "C"},
    {"seq": 3, "t": 40.0, "type": "focus_lost"},
    {"seq": 4, "t": 52.5, "type": "focus_gained"},
    {"seq": 5, "t": 60.2, "type": "paste", "item": 1, "chars": 42},
    {"seq": 6, "t": 95.0, "type": "answer", "item": 25, "option": "210"}
  ],
  "frames": [
    {"seq": 7, "t": 5.0, "faces": 1, "face_visible": true, "gaze": "centre", "brightness": 118, "blur": 0.12}
  ]
}
```

- `t` = seconds since the exam started, from `performance.now()`, not the wall clock.
- `type`: `item_shown`, `answer`, `focus_lost`, `focus_gained`, `paste`, `idle_start`, `idle_end` (idle = no touch/key for 20 s); coding tests add `code_typing`.
- `answer.option`: the letter for MCQ, the typed answer (≤ 40 chars) for `kind: "short"`. The server decides right/wrong.
- `paste`: send only `chars` (length). Never the pasted text.
- `frames`: numbers computed on the phone every ~5 s. `gaze` is the coarse **head** direction: `centre`, `down`, `left`, `right`, `away`, `unknown`. Never send images.
- After the sitting closes, batches get `409 sitting_closed`; before that, late batches after submit are still accepted (2G catch-up).
- Coding tests also send `code_typing` every ~5 s while the candidate types: `{"type": "code_typing", "item": 0, "meta": {"ins": 212, "dele": 31, "keys": 160, "max_ins": 4, "clear": 0, "len": 390}}`
  (characters inserted and deleted by typing, key presses, the largest single insert, a big deletion such as clearing the
  starter code, and the program length). Pastes are still sent as `paste` with `chars` only. `meta` is a few short values only (≤ 12 keys).
- Proctoring rules: `phone_seen`, `multi_face`, `offline_start`, `offline_end` (see `backend/services/rules.py`).
- Kiosk mode: `fullscreen_exit` / `fullscreen_enter` when the page leaves or re-enters full screen. Noted for the
  reviewer only, never a rule. `/api/exam/start` returns `kiosk` (false inside SEB or with `FP_KIOSK=off`).
- Microphone check (when the candidate allowed it): `mic_on` once when it starts; `speech_like` for a 5-second window
  the phone judged speech-like, at the window's end, with `"meta": {"s": 2.1, "a": 3.0}` (voiced and active seconds);
  `mic_off` with `option` = `blocked` | `slow` | `ended` | `error`. Never audio. These never change the score: see
  `backend/services/audio.py`. `/api/exam/me` and `/api/exam/start` return `mic`: `off` | `optional` | `required`
  (server setting `FP_MIC`, default `optional`).

### Coding tests

For a test with `kind: "coding"`, `/api/exam/start` also returns `test_kind: "coding"` and `code_state`, and each item is
a problem: `{item, kind: "code", text (statement), code{title, languages[{key, label}], time_limit, starter{lang: code}, samples[{input, output}], hidden_tests}}`.
Only the languages installed on the server are listed. Hidden tests never leave the server.
`code_state` is `{item: {language, code, best{verdict, passed, total}}}` so a reload restores the editor.

| Method | Path | Body → Response |
|---|---|---|
| GET | `/api/code/languages` | → `[{key: python\|cpp\|java\|javascript, label, available}]` (no login needed) |
| POST | `/api/exam/code/run` | `{item, language, code, t, input?}`. Without `input`: runs the **sample** tests → `{mode: "samples", verdict, passed, total, compile_output, seconds, tests[{n, status, seconds, input, expected, output, stderr}]}`. With `input`: one run on that text → `{mode: "custom", status, stdout, stderr, seconds, compile_output}` |
| POST | `/api/exam/code/submit` | `{item, language, code, t}` → judged on the **hidden** tests → `{verdict, passed, total, seconds, tests[{n, status}], compile_output}`. Only pass / fail per test comes back. Marks use the best submission per problem |

`verdict` / `status`: `accepted`, `wrong_answer`, `time_limit`, `runtime_error`, `output_limit`, `compile_error`
(`passed` for a single sample). Errors: `429 busy` (your previous run is still going), `409 time_over`,
`409 not_in_progress`, `422 language_not_allowed`, `503 language_unavailable`.
Output is compared ignoring trailing spaces and trailing blank lines.

`/api/exam/result` for a coding test adds `test_kind: "coding"` and `coding{marks, out_of, problems[{item, title, marks, verdict, passed, total}]}`
(each problem is worth 100 marks, shared equally by its hidden tests).

## Reviewer (`role = reviewer` or `admin`)

| Method | Path | Body → Response |
|---|---|---|
| GET | `/api/review/live` | sittings being written now → `[{id, title, status, starts_at, ends_at, writing, submitted}]` |
| GET | `/api/review/live/{sitting_id}` | live monitor → `{sitting, counts, n_items, priority_lines, model{ran_at, every_s, min_answers, version, error}, candidates[{session_id, who (pseudonym), name/roll_no/email (admins only), status, answered, last_seen, signals{left_tab, away_s, pastes, paste_chars, two_faces, frames, no_face_pct, face_now, pauses}, risk, band, families[], headline, trend}], alerts[{at, session_id, who, kind: left_tab\|paste\|second_person, text}]}`. `risk` is the trained model on the answers so far (re-run at most every 45 s, from 3 answers); `null` = too early |
| GET | `/api/review/queue?sitting_id=&band=queue\|review_first\|review\|clear\|all&family=&bandwidth=&q=&limit=&offset=&include_reference=1` | → `{total, counts{band:n}, open_appeals, priority_lines{review:50, review_first}, rows[{session_id, pseudonym, priority, band, rank, families[], headline, status, bandwidth, device, reference, submitted_at}]}` sorted by priority |
| GET | `/api/review/sessions/{id}` | → `{pseudonym, identity (only after confirm), sitting, meta, score{priority,band,rank}, explanation{headline, reasons[{family,title,weight,evidence[{text,t0,t1,items,moments[]}]}], context[] (= not counted), moments[], partners[{session_id, pseudonym}]}, events[], frames[], reviews[], appeal, also_viewing[], priority_lines{review, review_first}}` |
| POST | `/api/review/sessions/{id}/reinstate` | `{note}` (≥ 5 chars): reopens a test a proctoring rule ended, while the sitting is open → `{status: "in_progress", minutes_back, deadline}`. Answers kept, closed minutes added (capped at the sitting's end), that rule's count restarts. Errors: `not_ended_by_rule` (409; also when another reviewer reopened it first), `window_closed` (409). Any reviewer or admin. |
| POST | `/api/review/sessions/{id}/decision` | `{decision: confirm\|clear\|need_more, note}` (confirm needs a note ≥ 10 chars) |
| GET | `/api/review/appeals?status=open\|decided` | → list |
| POST | `/api/review/appeals/{id}/decide` | `{outcome: upheld\|overturned, response}` |

For a coding sitting the session detail also has `kind: "coding"`, `runs[{item, kind: run\|submit, verdict, passed, total, t}]`
and `code[{item, title, language, code, verdict, passed, total, t, attempts, runs, match?{session_id, pseudonym, similarity, lines[], partner_lines[], code, language}}]`
(the final program of each problem; `match` is the other candidate's program when the code matches, with the matching lines).
Events carry `meta` (the typing numbers above).

`family` values: `match` (answers shared with another candidate), `timing`, `pause`, `focus`, `paste`, `person`;
for coding tests `code_match`, `paste`, `typing`, `timing`.
`priority` is 0–100: 50 = review line, `priority_lines.review_first` (~92) = review first. It is **not** a probability of cheating.
`reference: true` rows are the demo's synthetic reference candidates; filter them out with `include_reference=0`.

## Admin (`role = admin`)

| Method | Path | Body → Response |
|---|---|---|
| POST / GET | `/api/admin/users` | POST `{role: admin\|reviewer, name, email, password (≥ 8)}` · GET `?role=` lists accounts |
| GET / POST | `/api/admin/tests` | POST `{title, duration_min, kind?: mcq\|coding}` → `{id}` |
| GET | `/api/admin/tests/{id}` | test with `items` (including answers); a coding test has `problems[]` instead, with samples, hidden tests and starter code |
| POST | `/api/admin/tests/{id}/items` | **CSV** body (`Content-Type: text/csv`): `text, option_a, option_b, option_c, option_d, correct, [difficulty], [kind]` → `{n_items}`. A `short` row has empty options and the expected answer in `correct`. Replaces all questions; refused once a sitting has started (`409 coding_test` for a coding test). |
| POST | `/api/admin/tests/{id}/problems` | coding tests, **JSON** `{problems: [{title, statement, languages[], time_limit (s, ≤ 10), starter{lang: code}, samples[{input, output}] (1–10, shown), tests[{input, output}] (1–50, hidden), solution?{language, code}}]}` → `{n_items, checked}`. A reference `solution` is run on every test first; if it fails → `400 bad_rows` with `rows[{line: problem no., problem}]`. Replaces all problems; refused once a sitting has started. Example: `backend/demo_data/coding_problems.json` |
| GET / POST | `/api/admin/sittings` | POST `{test_id, title, starts_at, ends_at}` (ISO 8601 with zone) → `{id, join_code}` |
| GET | `/api/admin/sittings/{id}` | → sitting + `live{not_started, in_progress, submitted, bands}` + `candidates[]` + `jobs[]` |
| POST | `/api/admin/sittings/{id}/candidates` | **CSV** `roll_no, name, [language]` → `{candidates[{roll_no, name, code}], csv}`. **Codes are shown once.** Send `Accept: text/csv` to get the file directly. |
| POST | `/api/admin/candidates/{user_id}/reset-code` | → `{roll_no, code}` |
| POST | `/api/admin/sittings/{id}/open` | scheduled → live |
| POST | `/api/admin/sittings/{id}/close` | auto-submits, closes, queues scoring → `202 {job_id, auto_submitted}` |
| GET | `/api/admin/jobs/{id}` | → `{status: queued\|running\|done\|failed, progress 0–1, message}` (poll every 1–2 s) |
| GET | `/api/admin/sittings/{id}/fairness` | fairness report of a scored sitting → `{sitting, ready, n, old_rules, labels{honest, malpractice, pending, reference}, workload{any\|first: {n, share}}, views{"honest.any"\|"honest.first"\|"all.any"\|"all.first": {n, overall{ours, old}, dimensions[{key, title, note, groups[{key, label, n, reference, ours, old, gap?{ours, old}}]}], skipped[], largest{ours, old}}}}`. A rate is `{k, n, rate, lo, hi}` (95% Wilson); a gap is `{diff, lo, hi, verdict: higher\|lower\|no_clear_difference\|too_few}` against the group marked `reference` (95% Newcombe). `ours` = FairProctor's bands; `old` = the old frame-by-frame rules given the same number of review slots. Dimensions: `room` (a second face in 1%+ of camera checks), `bandwidth`, `light`, `device`, `framing`; for coding tests `language`. `ready: false` until the sitting is scored |
| GET | `/api/admin/deletion-requests` | open requests |
| DELETE | `/api/admin/sessions/{id}` | deletes the session's data and the candidate login |
| GET | `/api/admin/audit?limit=100` | audit log |

## Frontend setup

**Development:** API on :8000, Vite on :5173. Either proxy `/api` in `vite.config.ts`
(`server: { proxy: { "/api": "http://127.0.0.1:8000" } }`) or call the API URL directly with the Bearer token
and add `http://localhost:5173` to `FP_CORS_ORIGINS`.

**Deployed:** frontend on Vercel/Netlify calls `https://<your-api>.onrender.com/api/...` with the Bearer token;
the backend allows that origin through `FP_CORS_ORIGINS`. Keep the API base URL in `VITE_API_URL`.
