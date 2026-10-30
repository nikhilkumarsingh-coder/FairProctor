// Response shapes from the FastAPI backend (see docs/API.md).
export type Role = "admin" | "reviewer" | "candidate";
export type Me = { id: number; role: Role; name: string; email?: string | null; roll_no?: string | null; sitting_id?: number | null; language: "en" | "hi"; created_at?: string; has_password?: boolean };

export type ExamMe = {
  join_needed: boolean;
  session: null | { id: string; status: "not_started" | "in_progress" | "submitted"; started_at?: string | null; submitted_at?: string | null; deadline?: string | null; reopened?: boolean };
  sitting?: { id: number; title: string; starts_at: string; ends_at: string; status: string };
  test?: { title: string; duration_min: number; n_items: number; kind?: "mcq" | "coding" };
  consent: { given: boolean; version_needed: string; camera_ok?: boolean; precheck_share_ok?: boolean };
  seb?: { required: boolean; verified?: boolean; in_seb?: boolean; config_url?: string | null; download_url?: string; exempt?: string };
  kiosk?: boolean;
  can_start: boolean;
  result_ready: boolean;
  retention_days: number;
  server_now: string;
  mic?: "off" | "optional" | "required";
};

export type CodeProblem = { title: string; languages: { key: string; label: string }[]; time_limit: number; starter: Record<string, string>;
  samples: { input: string; output: string }[]; hidden_tests: number };
export type Item = { item: number; kind: "mcq" | "short" | "code"; text: string; options: Record<string, string>; code?: CodeProblem };
export type Verdict = "accepted" | "wrong_answer" | "compile_error" | "runtime_error" | "time_limit" | "output_limit" | "memory_limit";
export type CodeState = Record<string, { language: string; code: string; best: null | { verdict: string; passed: number; total: number } }>;
export type RunResult = { mode: "samples"; verdict: Verdict; passed: number; total: number; compile_output: string; seconds: number;
  tests: { n: number; status: string; input: string; expected: string; output: string; stderr: string; seconds: number }[] }
  | { mode: "custom"; status: string; output?: string; stderr?: string; compile_output?: string; seconds?: number };
export type SubmitResult = { verdict: Verdict; passed: number; total: number; seconds: number; tests: { n: number; status: string }[]; compile_output: string };
export type StartRes = {
  session_id: string; started_at: string; deadline: string; server_now: string; elapsed_s: number; last_seq: number;
  items: Item[]; answers: Record<string, string>; test_kind?: "mcq" | "coding"; code_state?: CodeState;
  rules?: { phone: number; multi_face: number; tab_switch: number; limits: { phone_warnings: number; multi_face: number; tab_switch: number } };
  mic?: "off" | "optional" | "required";
  kiosk?: boolean;
};

export type Point = { title: string; text: string; when: string; questions: number[] };
export type ResultState = "pending" | "clear" | "under_review" | "cleared_after_review" | "confirmed" | "cleared_after_appeal";
export type Result = {
  state: ResultState; message: string; retention_days: number; can_appeal: boolean;
  not_counted?: string[]; summary?: string; points?: Point[]; reviewer_note?: string;
  appeal: null | { text: string; status: "open" | "decided"; outcome?: "upheld" | "overturned" | null; response?: string | null; at: string };
  test_kind?: "mcq" | "coding";
  coding?: { marks: number; out_of: number; problems: { item: number; title: string; marks: number; verdict: string; passed: number; total: number }[] };
  terminated?: { reason: string; text: string; at: string };
};

export type Band = "review_first" | "review" | "clear";
export type QueueRow = {
  session_id: string; pseudonym: string; sitting_id: number; priority: number; band: Band; rank: number;
  families: string[]; headline: string; status: string; bandwidth: string; device: string; reference: boolean; submitted_at?: string;
};
export type Queue = { total: number; counts: Partial<Record<Band, number>>; open_appeals: number; rows: QueueRow[]; priority_lines: { review: number; review_first: number | null } };

export type Moment = { t: number; label: string };
export type Evidence = { key: string; t0: number; t1: number; items: number[]; text: string; strength?: number; moments: Moment[] };
export type Reason = { family: string; title: string; weight: number; evidence: Evidence[]; fallback?: string | null };
export type SessionDetail = {
  session_id: string; pseudonym: string; identity: null | { name: string; roll_no?: string | null; email?: string | null };
  sitting: { id: number; title: string };
  meta: { device: string; bandwidth_class: string; precheck_light: string; precheck_framing: string; reference: boolean; started_at?: string; submitted_at?: string };
  rules?: RulesInfo;
  score: { priority: number; band: Band; rank: number; model_version: string; scored_at: string };
  explanation: { headline: string; reasons: Reason[]; context: string[]; moments: { t: number; at: string; label: string }[]; partners: { session_id: string; pseudonym: string }[]; score?: number };
  events: { seq: number; t: number; type: string; item: number; option: string; correct: number; chars: number; meta?: Record<string, number> | null }[];
  frames: { t: number; faces: number; face_visible: number; gaze: string; phone?: number | null }[];
  reviews: { decision: string; note: string; at: string; reviewer: string }[];
  appeal: null | { id: number; text: string; status: string; outcome?: string; response?: string; at: string };
  also_viewing: string[];
  kind?: "mcq" | "coding";
  code?: { item: number; title: string; language: string; code: string; verdict: string; passed: number; total: number; t: number; attempts: number; runs: number;
    match?: { session_id: string; pseudonym: string; similarity: number; lines: number[]; partner_lines: number[]; code: string; language: string } }[];
  runs?: { item: number; kind: "run" | "submit"; verdict: string; passed: number; total: number; t: number }[];
  priority_lines?: { review: number; review_first: number | null };
};
export type Appeal = { id: number; session_id: string; pseudonym: string; text: string; moments: number[]; status: string; outcome?: string; response?: string; band?: Band; priority?: number; at: string };

export type Test = { id: number; title: string; duration_min: number; n_items: number; created_at: string; kind?: "mcq" | "coding" };
export type Sitting = { id: number; test_id: number; test_title: string; title: string; starts_at: string; ends_at: string; status: string; join_code: string; n_candidates: number };
export type Job = { id: number; status: "queued" | "running" | "done" | "failed"; progress: number; message: string };

export type LiveSitting = { id: number; title: string; status: string; starts_at: string; ends_at: string; writing: number; submitted: number };
export type LiveCandidate = {
  session_id: string; who: string; name?: string | null; roll_no?: string | null; email?: string | null;
  status: "in_progress" | "submitted"; answered: number; n_items: number; device?: string; bandwidth?: string; last_seen?: string | null;
  signals: { left_tab: number; away_s: number; pastes: number; paste_chars: number; two_faces: number; frames: number; no_face_pct: number | null; face_now: [boolean, number] | null; pauses: number; speech?: number; mic?: "on" | "off" | null };
  risk: number | null; band: Band | null; families: string[]; headline: string; trend?: number | null;
  rules?: RulesInfo; terminated?: string | null;
};
export type RuleCounts = { phone: number; multi_face: number; tab_switch: number; disconnects: number; answered_after_reconnect: number; relogins: number; terminated: string | null;
  history?: { reason: string; ended_at: string; reopened_at: string; by: string; note: string; minutes_back: number }[];
  fullscreen_exits?: number; device?: { mode?: string; mobile?: boolean; seb_exempt?: boolean; mismatch?: boolean; note?: string } | null };
export type RulesInfo = { counts: RuleCounts; flags: { key: string; level: "high" | "medium" | "info"; text: string }[] };
export type LiveAlert = { at: string; session_id: string; who: string; kind: "left_tab" | "paste" | "second_person" | "phone" | "terminated"; text: string };
export type LiveSnapshot = {
  sitting: { id: number; title: string; status: string; starts_at: string; ends_at: string; join_code: string };
  counts: { not_started: number; in_progress: number; submitted: number }; n_items: number;
  candidates: LiveCandidate[]; alerts: LiveAlert[]; priority_lines: { review: number; review_first: number | null };
  model: { ran_at: string | null; every_s: number; min_answers: number; version?: string; error?: string | null; pending?: boolean };
  kind?: "mcq" | "coding";
};

// fairness report (GET /api/admin/sittings/{id}/fairness)
export type FairRate = { k: number; n: number; rate: number | null; lo: number | null; hi: number | null };
export type FairGap = { diff: number | null; lo: number | null; hi: number | null; verdict: "higher" | "lower" | "no_clear_difference" | "too_few" };
export type FairGroup = { key: string; label: string; n: number; reference: boolean; ours: FairRate; old: FairRate; gap?: { ours: FairGap; old: FairGap } };
export type FairLargest = FairGap & { dimension: string; group: string; reference: string };
export type FairView = {
  n: number; overall: { ours: FairRate; old: FairRate };
  dimensions: { key: string; title: string; note: string; groups: FairGroup[] }[];
  skipped: { key: string; title: string; reason: string }[];
  largest: { ours: FairLargest | null; old: FairLargest | null };
};
export type Fairness = {
  sitting: { id: number; title: string; status: string; kind: "mcq" | "coding"; scored_at: string | null };
  old_rules: string; ready: boolean; n: number;
  labels?: { honest: number; malpractice: number; pending: number; reference: number };
  workload?: Record<"any" | "first", { n: number; share: number }>;
  views?: Record<string, FairView>;
};

// demo mode (GET /api/demo): public demo logins for the login page
export type Demo = { enabled: boolean; staff?: { role: "admin" | "reviewer"; email: string; password: string }[];
  story?: { key: string; roll_no: string; code: string; name: string }[]; join_codes?: Partial<Record<"mcq" | "coding", string>> };
