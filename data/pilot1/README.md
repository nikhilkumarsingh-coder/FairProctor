# First hostel pilot (29 Oct 2026), anonymised

Ten participants followed secret role cards (see `pilot/PILOT.md`); roles are in `sessions.csv` (`role`, `kind`, `partner`).
Names, roll numbers, login codes and typed short-answer text are removed; sessions are `PILOT1-P01` … `PILOT1-P10`.
Camera data is numbers only (no images).

Used by `backend/tests/test_pilot_replay.py` so every change to the scoring code is run on real candidate behaviour
(answers changed, questions revisited, tests clicked through in a minute). It is a regression fixture, **not** evidence:
the scoring fixes made after this pilot were designed while looking at it, so only a new pilot can show whether they help.
