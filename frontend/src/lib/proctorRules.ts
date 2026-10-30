// Proctoring rules on the device, fed once per second by the camera checks. Pure state machines (no React), so they
// are easy to test. The server keeps its own counts and ends the test too (backend/services/rules.py).
//   2+ faces for 5 s in a row      → one "multi_face" episode; more than `multiFace` episodes ends the test
//   no face for 5 s in a row       → the "keep your face in view" notice (never a reason to end)
//   phone in ≥ 2 of the last 5 s   → one "phone_seen"; the first is a warning, the next ends the test
//   leaving the tab or app         → counted; more than `tabSwitch` ends the test
export type Reason = "phone" | "multiple_faces" | "tab_switch";
export type Limits = { phone_warnings: number; multi_face: number; tab_switch: number };
export const DEFAULT_LIMITS: Limits = { phone_warnings: 1, multi_face: 5, tab_switch: 5 };
export const WINDOW_S = 5;

export class FaceRule {
  private multi = 0; private calm = 0; private inEpisode = false; private none = 0;
  constructor(public episodes = 0, private limit = DEFAULT_LIMITS.multi_face) {}
  /** One camera check. Returns what the page should do now. */
  check(faces: number | null): { episode: boolean; people: boolean; noFace: boolean; end: boolean } {
    if (faces === null) return { episode: false, people: this.inEpisode, noFace: false, end: false };
    this.none = faces === 0 ? this.none + 1 : 0;
    let episode = false;
    if (faces >= 2) {
      this.multi += 1; this.calm = 0;
      if (!this.inEpisode && this.multi >= WINDOW_S) { this.inEpisode = true; this.episodes += 1; episode = true; }
    } else {
      this.multi = 0; this.calm += 1;
      if (this.inEpisode && this.calm >= 3) this.inEpisode = false;     // gone for 3 s: the next one is a new episode
    }
    return { episode, people: this.inEpisode, noFace: this.none >= WINDOW_S, end: episode && this.episodes > this.limit };
  }
}

export class PhoneRule {
  private last: boolean[] = []; private inEpisode = false; private clean = 0; private since = 0;
  constructor(public seen = 0, private warnings = DEFAULT_LIMITS.phone_warnings) {}
  /** One phone check (null = could not check). `t` in seconds. */
  check(phone: boolean | null, t: number): { seen: boolean; warn: boolean; end: boolean } {
    if (phone === null) return { seen: false, warn: false, end: false };
    this.last = [...this.last, phone].slice(-WINDOW_S);
    this.clean = phone ? 0 : this.clean + 1;
    // an episode ends after 5 clean seconds, or 15 s after it began (holding the phone up stays a new sighting)
    if (this.inEpisode && (this.clean >= WINDOW_S || t - this.since >= 15)) { this.inEpisode = false; this.last = phone ? [phone] : []; }
    if (!this.inEpisode && this.last.filter(Boolean).length >= 2) {
      this.inEpisode = true; this.since = t; this.seen += 1;
      return { seen: true, warn: this.seen <= this.warnings, end: this.seen > this.warnings };
    }
    return { seen: false, warn: false, end: false };
  }
}

export function tabSwitchEnds(count: number, limits: Limits = DEFAULT_LIMITS): boolean {
  return count > limits.tab_switch;
}
