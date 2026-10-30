# Running a real pilot

A pilot answers the question every judge will ask: *does it work on real people, not just synthetic data?*
In one afternoon, 12–20 people take the FairProctor test, each following a **secret role card**: honest in a hard
situation (dim room, shared room, phone held low, slow connection, interruptions) or **acting out** malpractice
(second phone, searching, sharing answers, a helper; for code: pasting from the web, copying a partner, typing from a
phone). The roles stay in a **sealed key** until scoring is done. One command then writes the results, honestly,
with intervals, into `reports/PILOT_RESULTS.md` and the README.

| What | How long |
|---|---|
| Setting up (the day before) | 15 minutes |
| The question test | 45 minutes (plus 10 for logging in) |
| The coding test (optional, can be the same people) | 60 minutes |
| Results | 1 minute |

## What you need

- **People:** 12–20 is good, 8 is the minimum that says anything. Each needs a phone or laptop with a front camera.
  One or two extra friends to walk behind the "shared room" people and to be the "helper" (they do not take the test).
- **Your computer** running FairProctor (it is the server), plugged in, with sleep turned off.
- **Internet** for your computer and for the participants (phones need an HTTPS link for the camera; see below).

## 1. The day before: make the pilot

From the project folder (Windows CMD):

```bat
cd /d D:\path\to\fairproctor
python -m backend.scripts.seed_demo            REM only if the demo tests are missing; never with --reset on pilot day
python -m pilot.prepare --people 16 --name "hostel pilot"
```

With Docker, run the same commands inside the app container, e.g.
`docker compose exec app python -m pilot.prepare --people 16 --name "hostel pilot"`; the files appear in `pilot\out`
on your computer.

Add `--coding-people 8` to also run the coding test. This creates a live pilot sitting (with 200 synthetic reference
candidates for calibration, as in the product), imports participants **P01, P02, …** (no names are stored), gives each
a balanced role (about 40% malpractice), and writes to `pilot\out\hostel-pilot\`:

| File | Use |
|---|---|
| `cards.html` | All cards to print, two per A4 page. Fold on the dashed line so the role is hidden. |
| `cards\P01.html` … | One card per person, to send privately on chat instead of printing. |
| `consent.html` | Participant information and consent (English + हिन्दी). Print one per person. |
| `logins.csv` | Every roll no. and login code (codes cannot be shown again). |
| `key-SEALED.csv` | Who has which role. **Do not open it** until the sitting is scored. |
| `pilot.json` | The sitting numbers, for the report. |

**Rehearse once (2 minutes, recommended):** with the backend running,

```bat
python -m pilot.prepare --rehearsal --people 12 --coding-people 6
python -m pilot.dry_run --dir pilot\out\rehearsal-<date>
```

Simulated participants log in, act out every role through the real API, get scored, and a `PILOT_DRYRUN.md` appears in
that folder. It proves the kit works on your computer; it is never written to the README.

## 2. On the day

1. **Start the server:** `python -m uvicorn backend.app:app --port 8000`
2. **Make an HTTPS link** (phones only allow the camera on HTTPS). Download `cloudflared-windows-amd64.exe` from
   <https://github.com/cloudflare/cloudflared/releases> and run, in a second window:
   ```bat
   cloudflared-windows-amd64.exe tunnel --url http://localhost:8000
   ```
   It prints a link like `https://some-words.trycloudflare.com`. Keep both windows open. This is not a deployment:
   the link works only while your computer and the tunnel are running.
3. **Put the link on the cards** (if you did not print yet):
   `python -m pilot.prepare --cards-only --dir pilot\out\hostel-pilot --url https://some-words.trycloudflare.com`,
   or post the link in your group. For a QR code, open the link in Chrome → address bar → **Share → Create QR code**.
4. **Brief everyone (2 minutes):** *"Your card has your login and a secret role. Play it naturally and don't tell
   anyone. It is a role-play to test the system; nothing is graded, and you can stop any time."* Collect the signed
   consent forms, then hand out the cards face down.
5. **Watch live:** log in as admin → **Live monitor** → the pilot sitting. Screen-record it: this is the best footage
   for the demo video.
6. **When everyone has submitted** (or time is up): admin → the pilot sitting → **Close & score**.

## 3. Results

```bat
python -m pilot.report --dir pilot\out\hostel-pilot --update-readme
```

This writes `reports/PILOT_RESULTS.md` (caught, flagged, the right-reason check, the old rules at the same number of
flags, every participant, the limits) and the charts `docs/charts/pilot-queue-*.svg`, and fills the **Real pilot**
section of the README. Without `--update-readme` the README is left alone.

**Optional, stronger: a blind reviewer.** Before anyone opens the key, a friend logs in as reviewer and decides each
flagged participant (confirm / clear). Run the report afterwards: it adds how many decisions matched the key.

Then open the key together and look at the surprises: an honest person flagged (read the reason on their evidence
page), a cheater missed (what did they actually do?).

## 4. Delete the data

The consent form promises deletion within 7 days:

```bat
python -m pilot.cleanup --dir pilot\out\hostel-pilot --yes
```

It deletes the pilot sittings with everything in them and the login codes, and keeps the anonymous results.

## Rules for reporting honestly

- **Report what happened**, including misses and honest people flagged. The report shows 95% intervals; with 16
  people they are wide, and that is fine to say.
- **One pilot, one report.** Don't re-run until the numbers look good. If you run a second pilot, report both.
- **Don't tune the model on the pilot** and then report the same pilot as evidence.
- **Acted is not real.** Say that people knew it was a test.

## Ethics checklist

- [ ] Everyone signed the consent form; taking part is voluntary and they can stop any time.
- [ ] No real exam, grade or job depends on it.
- [ ] No names in the system: participants are P01, P02, …
- [ ] Walkers and helpers know they may appear on camera (only numbers leave the device, never images).
- [ ] Data deleted with `pilot.cleanup` after the report.

## If something goes wrong

| Problem | Fix |
|---|---|
| The camera doesn't start on a phone | Use the `https://…trycloudflare.com` link, not `http://192.168…` or `localhost`. |
| "The test has not started yet" | The pilot sitting is live for 3 days from `pilot.prepare`; check it on the admin page. |
| Someone lost their code | Admin → the pilot sitting → **New code** next to their roll no. |
| A phone loses network | Answers stay on the phone and are sent when it is back; just continue. |
| Your computer slept | The tunnel stopped and the link changes when you restart it. Share the new link; answers already sent are safe. |
| Many people show "low bandwidth" | The speed test measures the link to *your* computer through the tunnel; a slow home upload makes everyone look slow. Bandwidth is never a model input, but the report's connection split is then less meaningful; mention it. |
