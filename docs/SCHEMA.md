# Event schema used by this prototype

The real IMAP proctoring event schema was not available while building, so this
prototype uses the schema below. It was written from the problem statement and
is meant to be mapped onto the IMAP schema with a thin adapter
(`fairproctor/adapters.py` is the place to add that mapping).

Nothing here stores a name, photo, gender, religion, caste, region or any other
demographic attribute. Sessions are identified only by an opaque `session_id`.

## sessions.csv — one row per session

| column | meaning |
|---|---|
| `session_id` | opaque id, e.g. `S00042` |
| `window_id` | the sitting (same paper, same time slot). Collusion is only checked inside a window. |
| `network_ip_hash` | salted hash of the public IP. Many candidates in one cyber cafe share it. Used only to explain context, never as evidence on its own. |
| `device` | `phone` or `desktop` |
| `bandwidth_class` | `low` or `normal`, derived from measured upload rate during the test |
| `precheck_light`, `precheck_framing` | outcome of the pre-test check (`ok`, `dim`, `backlit`; `ok`, `off_centre`, `too_close`) |
| `verdict` | reviewer verdict: `confirmed` (malpractice) or `cleared` |

The synthetic generator also writes `_truth_type` (which malpractice pattern was
simulated). It exists only so we can analyse results; the model never reads it.

## events.csv.gz — browser and answer events

| column | meaning |
|---|---|
| `session_id` | |
| `t` | seconds since the test clock started |
| `type` | `item_shown`, `answer`, `focus_lost`, `focus_gained`, `paste`, `idle_start`, `idle_end` |
| `item` | item index (0-based) where relevant |
| `option` | chosen option for MCQ answers (`A`–`D`); `TEXT` for short answers |
| `correct` | 1/0 for answers (scored server-side after submission) |
| `chars` | characters pasted (paste events only — never the text itself) |

`idle_start` is emitted after 20 s with no mouse, touch, scroll or key input,
`idle_end` when input resumes.

## frames.csv.gz — per-frame results of on-device / server-side video analysis

Only analysis results are kept; the frames themselves are deleted after
analysis (see README, privacy section).

| column | meaning |
|---|---|
| `session_id`, `t` | |
| `faces` | number of faces detected (detection only, no recognition) |
| `face_visible` | 1 if the candidate's face is detected with usable quality |
| `gaze` | coarse head-pose bucket: `centre`, `down`, `left`, `right`, `away`, `unknown` |
| `brightness` | mean luma 0–255 of the face region (or whole frame if no face) |
| `blur` | 0–1, higher = blurrier |

Frames arrive at whatever rate the connection allows. On a 2G-like link that is
one analysed frame every 3–8 seconds; the scorer is built to expect this.

## items.csv — the paper

`item`, `kind` (`mcq` / `short`), `n_options`, `correct_option`. Item
difficulty and expected time are **estimated from the response data**, not
supplied, so the method works on a new paper.
