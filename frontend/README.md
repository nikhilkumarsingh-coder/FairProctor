# FairProctor web app (frontend)

React 19 + TypeScript + Vite, Tailwind CSS v4 with shadcn/ui-style components. Talks to the FastAPI backend in
`../backend` over its REST API with a JWT (Bearer header).

| Who | Screens |
|---|---|
| Candidate (phone first, English + हिन्दी) | Log in with roll no. + code (no sign-up; the test centre adds candidates) → what is recorded (consent) → pre-check (connection, light, light behind, face, sharpness) → the test, one question per screen, with a small camera bubble → submitted → result, "what was noticed", "not counted against you", explain (appeal), how long the data is kept. During the test: a popup when they come back after leaving the test screen, a banner when no face or a second person is in view for ~10–15 s, a note when they paste — each says what is recorded and never accuses |
| Candidate, coding test | Problem tabs → statement and sample tests on the left, a code editor on the right (Python, C++, Java, JavaScript; syntax colours, line numbers, Tab indent, auto-indent, Ctrl+Enter runs) → **Run samples** (input, expected, your output, errors), **Run with my input**, **Submit** (hidden tests: only pass/fail per test) → result with marks per problem. Code is kept on the device as you type, so a reload never loses it |
| Reviewer | Review queue ranked by priority (tabs, reason filters, search, J/K keys) → session: timeline of answers, focus, pauses, paste and camera numbers, reasons with clickable moments, decision with note → appeals. For coding sessions: each final program, the other candidate's program side by side with the matching lines highlighted, and a timeline of runs, submits, typing, pastes and leaving the window |
| Admin | Tests (CSV question upload with row errors, or a coding test with problems uploaded as JSON — reference solutions are checked on every test first) and sittings (candidate CSV import with one-time login codes, open, live counts, close & score with progress, a link to each candidate's evidence) |
| Fairness report (admin) | `/admin/sittings/:id/fairness`: for each group (other people around, connection, light, device, framing; language for coding) the share sent to review by FairProctor and by the old rules at the same workload, bars with 95% intervals, the gap to the reference group, and every number in a table. Toggles: *Sent to review / Review first*, *Honest candidates / Everyone* |
| Demo | A **Try the demo** box on the login page (only when the backend is in demo mode): admin, reviewer, a fresh candidate for the question or coding test, and Priya's and Rahul's results |
| Live (reviewer + admin) | Live monitor (`/review/live`): while a sitting is written, the trained model re-scores the answers so far every 45 s; candidates ranked by live risk with reasons, and a feed of alerts (left the test screen, pasted, a second person in view) that also pops up as it arrives |
| Everyone | My account (`/account`, the person icon in the header): name, language (candidates), change password — other devices are logged out |

Light and dark mode everywhere. All forms check input in the browser and show the backend's field errors too.

## Run it

Start the backend first (from the project root): `python -m backend.scripts.seed_demo --reset` then
`python -m uvicorn backend.app:app --port 8000`.

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173 — /api is proxied to http://127.0.0.1:8000
```

Backend on another port? `VITE_PROXY_TARGET=http://127.0.0.1:8001 npm run dev`
(PowerShell: `$env:VITE_PROXY_TARGET="http://127.0.0.1:8001"; npm run dev`).

Demo logins (printed by the seed script and saved in `backend/data/demo_logins.txt`):

| Role | Login |
|---|---|
| Admin | `admin@fairproctor.demo` / `Admin@2026` (Email tab) |
| Reviewer | `reviewer@fairproctor.demo` / `Review@2026` (Email tab) |
| Candidates | `TEAM01`–`TEAM03` with the codes the seed printed (Roll no. tab) |
| Coding candidates | `CODE01`–`CODE03` with the codes the seed printed (Roll no. tab) |
| New candidate | "Question test" or "Coding test" on the candidate login page (`/login`); staff demo on `/staff/login` |

## Build and deploy

```bash
npm run build        # type-check + production build into dist/
npm run preview
```

- **Same server:** the backend serves `frontend/dist` if it exists, so one Render service can host both.
- **Vercel / Netlify:** set `VITE_API_URL=https://<your-backend>.onrender.com` at build time, and add the frontend's
  URL to the backend's `FP_CORS_ORIGINS`. `vercel.json` and `public/_redirects` send every path to `index.html`.

The camera needs HTTPS on phones (localhost is fine on a computer).

## How it is organised

```
src/
  App.tsx              routes and role guards (candidate / reviewer / admin)
  lib/api.ts           the only place that calls the backend; JWT in localStorage "fp-token"
  lib/auth.tsx         login (per app), logout, current user
  App.tsx, main.tsx    the candidate app (/)
  staff/App.tsx, staff/main.tsx   the staff app (/staff, /admin, /review); staff/index.html is its page
  lib/i18n.tsx         English + Hindi text for candidate screens
  lib/serverText.ts    Hindi for the sentences the scoring engine writes for candidates
  lib/examEngine.ts    exam recorder + uploader: every event gets a sequence number, goes to IndexedDB,
                       then to the server every 10 s; safe to resend on 2G (the server stores each seq once)
  lib/camera.ts        one camera stream, face detector, light/sharpness numbers, the pre-check rules
  components/DemoPanel.tsx    the "Try the demo" box on the login page
  pages/admin/Fairness.tsx    fairness report (bars + intervals; colours in styles.css .viz)
  components/CodeEditor.tsx   code editor (textarea over highlight.js) that also counts typed / deleted characters
  components/CodeReview.tsx   reviewer's program view (side-by-side match) and coding timeline
  pages/exam/Coding.tsx       the coding test screen
  lib/router.tsx       a tiny history router
  components/ui/       Button, Card, Badge, Input, Dialog, Tabs, Toast … (shadcn/ui style, cva + tailwind-merge)
  components/          app shells, camera bubble, review and admin pieces
  pages/auth|exam|review|admin|account
```

What the exam sends: answers (MCQ letter or typed short answer), when each question was shown, leaving and
returning to the test tab, pauses of 20 s or more with no mouse/touch/keyboard input, and the length of pasted
text (never the text). Camera numbers every 5 s: faces in view, face visible, head direction against the
candidate's own first frames, light and sharpness. No image leaves the device. If the browser has no face
detector (most desktop browsers), MediaPipe's is loaded on a fast connection; otherwise no camera numbers are
sent and the score relies on the other signals.

Coding tests also send typing numbers every 5 s (characters typed and deleted, key presses, the largest single
insert, the program length) — never keystrokes or their timing one by one. Runs and submits are recorded by the
server.

Offline: answers stay on the phone (IndexedDB) and are sent when the connection returns; a reload resumes the
test where it was, and submit waits until everything is sent.
