# FairProctor — demo guide

Everything you need to show FairProctor in about three minutes: how to start it, the logins, and what to click.
All people in the demo are made up.

## Start it

**One command (Docker):**

```bash
docker compose up --build        # then open http://localhost:8000
```

**Without Docker (Windows CMD, from the project folder):**

```bat
cd /d D:\path\to\fairproctor
pip install -r requirements.txt
python -m backend.scripts.seed_demo --reset
python -m uvicorn backend.app:app --port 8000
```

Open **http://127.0.0.1:8000**. The backend serves the built frontend from `frontend/dist`, so `npm` is only
needed to change the frontend (`cd frontend && npm install && npm run dev`, then http://localhost:5173).

`seed_demo --reset` deletes the local demo database and builds a fresh one (about 10 seconds).

## Logins

The login page has a **Try the demo** box with one-click buttons for all of these (shown in demo mode only:
local SQLite, or `FP_DEMO=1`).

| Who | Login | What they see |
|---|---|---|
| Admin | `admin@fairproctor.demo` / `Admin@2026` (Email tab) | Tests, sittings, live monitor, close & score, fairness report |
| Reviewer | `reviewer@fairproctor.demo` / `Review@2026` (Email tab) | Review queue, evidence, decisions, appeals |
| Priya Sharma | roll no. `STORY01`, code `PRIYA1` | Honest; 2G, phone held low, dim room, people walking past. Result: cleared |
| Rahul Verma | roll no. `STORY02`, code `RAHUL1` | Second phone below the camera. Result: being reviewed, can explain |
| New candidate | "Question test" button on the candidate login page (`/login`) | The question test, live |
| New coder | "Coding test" button on the candidate login page | The coding test, live |
| Admin / reviewer | Buttons on the staff login page (`/staff/login`) | Admin and reviewer screens |
| Team logins | `TEAM01`–`TEAM03`, `CODE01`–`CODE03` with the codes in `backend/data/demo_logins.txt` | Fixed live candidates |

## The three-minute demo

**The story in one line:** old proctoring tools flag the honest candidate in a bad room and miss the one with a
second phone. FairProctor does the opposite, and shows its evidence.

1. **Rahul is at the top (reviewer, 40 s).** Click *Reviewer*. In the queue tick **Hide reference sessions**:
   Rahul is in *Review first* with priority 97. Open him: *11 long pauses with no touch or key input on hard
   questions, each followed by a correct answer; head down 76% of the time in those pauses vs 5% otherwise.*
   Click a moment chip to jump to it on the timeline. (The old frame-by-frame rules rank him only around #80 of 202,
   because nothing on camera looks strange.)
2. **Priya is cleared, and the system says why (reviewer, 30 s).** Switch to the *All* tab and open Priya
   (Auto-cleared). The **Not counted against this candidate** box lists: 2G video (a frame every 12 s), face not
   clear in 40% of frames (dim room), two people walking past, leaving the test window once (with no quick correct
   answer after it), phone held low. The old rules put
   her in the top 10 of 202: 63% of her camera checks raised a flag.
3. **Prove it is fair, not lucky (admin, 40 s).** Log in as *Admin* → *Morning sitting — already scored* →
   **Fairness report**. Honest candidates on a phone: old rules flag them 86 points more often than laptop users;
   FairProctor shows no clear difference. Switch to **Review first**: FairProctor puts 0% of honest candidates there,
   in every group.
4. **Live (admin + candidate, 40 s).** In a second browser window (or a phone), click *Take a test as a new
   candidate* and start the test. As admin open *Demo sitting* → **Live monitor**. Switch tabs on the candidate:
   the candidate gets a calm "you left the test screen" note, and the admin sees the alert appear.
5. **Candidates can answer back (30 s).** Click *Rahul* on the login page: he sees what was noticed, with times
   and question numbers, and an **Explain this** button. Priya sees "no issues were found" and the same
   "not counted" list in plain language (English / हिन्दी).

**If there is more time:** the coding test (*Coding test* button → paste a solution after leaving the tab →
admin closes and scores the coding sitting → the paste case is in *Review first* with the program shown), dark
mode, and the Hindi toggle.

## If something goes wrong

| Problem | Fix |
|---|---|
| `No module named 'backend'` | Run the commands from the project folder (the one with `backend/` and `frontend/`). In CMD use `cd /d D:\...` to change drive too |
| Login says the server is unreachable | Something else is on port 8000: `netstat -ano \| findstr :8000`, then `taskkill /PID <pid> /F`, and start the backend again |
| C++, Java or JavaScript missing in the coding test | That compiler is not installed on this computer (g++, a JDK, Node). Python always works; Docker has all four |
| The queue is empty | Run `python -m backend.scripts.seed_demo --reset` again; the *Morning sitting* is scored during the seed |
| Want a clean demo again | `seed_demo --reset` rebuilds everything, including Priya and Rahul |
