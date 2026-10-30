# End-to-end browser test

Drives the real app in Chromium against a running backend: a candidate on a phone screen, two candidates
who copy each other (sent through the API), then the admin, the reviewer and the appeal. It saves screenshots
in `e2e/shots/` and prints any page error or unexpected failed request.

```bash
# 1. backend with fresh demo data, serving the built frontend (from the project root)
cd frontend && npm install && npm run build && cd ..
python -m backend.scripts.seed_demo --reset
uvicorn backend.app:app --port 8000

# 2. in a second terminal
cd e2e
npm install && npx playwright install chromium
python colluders.py          # TEAM02 and TEAM03 share one answer sheet
npm run candidate            # TEAM01 takes the test in the browser; the login has no sign-up
npm run staff                # admin closes and scores, reviewer confirms TEAM02, TEAM02 appeals
npm run account              # profile, Hindi, password change logs the other device out, staff account page
```

Live monitor and the candidate's live notices (on a freshly seeded database, backend running):

```bash
python colluders.py --items 15 --no-submit   # the copying pair, halfway through and still writing
npm run live                 # admin watches; TEAM01 gets the "second person" banner and the "left the screen" popup
```

Coding test (on a freshly seeded database, backend running):

```bash
npm run coding               # CODE01 solves P1 in Python, P2 in JavaScript, P3 slow Python (time limit) then C++;
                             # CODE02 leaves the tab and pastes a solution; admin live monitor, close & score;
                             # reviewer opens the paste case; CODE01 sees marks; admin coding test page
```

It needs `g++` and `node` on the machine (Java is optional). Expected: CODE02 is "Review first" for the paste.

Demo box, story and fairness report (on a freshly seeded database, backend running):

```bash
npm run demo                 # the "Try the demo" buttons; Priya cleared with what was not counted; Rahul first in the
                             # real-candidate queue with his evidence; the fairness report; fresh candidates for both tests
```

Run the steps in each block in this order on a freshly seeded database. Linux Chromium has no built-in face detector,
so the candidate script adds a stand-in that reports one centred face; on Android Chrome the real one is used.

Safe Exam Browser (on a freshly seeded database, backend running): a normal browser is stopped, "SEB" with its
JavaScript API simulated writes the test, and the admin card shows the settings.

```bash
node seb.mjs
```

Proctoring rules (on a freshly seeded database, backend running): a second face for 5 s is counted, logging in again is
counted, the 6th time the test screen is left ends the test, a reviewer reopens it from the live monitor (the candidate
continues and the count starts again), and after scoring the reviewer sees the Proctoring rules card.

```bash
node rules.mjs
```

Microphone check (on a freshly seeded database, backend running): a recording of someone reading aloud plays into the
fake microphone; the candidate allows the mic and sees the level, the test shows "Mic on", the live monitor shows a
neutral speech-like sound chip, and after scoring the reviewer sees a Sound lane and the sound under "Not counted".
Without `SPEECH_WAV` a synthetic voice is used.

```bash
SPEECH_WAV=path/to/musan/speech/librivox/speech-librivox-0000.wav node audio.mjs
```

Device decided automatically (on a freshly seeded database, backend running): the demo sitting requires Safe Exam
Browser on laptops; a phone is let in and the test opens in full screen (leaving it shows a "Back to full screen" bar),
a laptop is asked for SEB, and a laptop pretending to be a phone gets in with a "device check" in the live monitor.

```bash
node kiosk.mjs
```
