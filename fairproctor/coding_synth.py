"""Synthetic coding sittings for training and testing the coding integrity model.

The three problems are the demo coding test (second largest, balanced brackets, pairs with sum k). Programs are
real Python / C++ source built from interchangeable parts, so the similarity check runs on actual code.

Honest candidates (with hard look-alikes):
  * type their solution with edits, pauses, sample runs and wrong submissions, at a pace set by their skill;
  * some move their own lines with small pastes, some leave the tab briefly for a notification;
  * fast experts type quickly with few mistakes and often pass on the first submit.
Malpractice (about 6 % of candidates, on 1–3 of the 3 problems):
  * web_paste    leave the tab, come back and paste most of a solution found online (online solutions repeat);
  * copy_pair    two candidates share code: one solves, the other pastes or types the same program later;
  * transcribe   a long still pause, then the whole solution typed fast with almost no corrections
                 (reading it from a phone or a helper);
  * inject       large text insertions that are not pastes (an extension or a remote tool typing).
"""
from __future__ import annotations

import random
import re

import numpy as np
import pandas as pd

PROBLEMS = [dict(item=0, title="Second largest", typical=480.0, hard=0.9),
            dict(item=1, title="Balanced brackets", typical=720.0, hard=0.75),
            dict(item=2, title="Pairs with sum k", typical=1080.0, hard=0.55)]
N_HIDDEN = [8, 4, 8]

# ---------------------------------------------------------------- program parts: [alternatives] per slot
PY = {
    0: [["import sys\ndata = sys.stdin.read().split()\nn = int(data[0])\na = list(map(int, data[1:1 + n]))\n",
         "n = int(input())\na = list(map(int, input().split()))\n",
         "import sys\ninput = sys.stdin.readline\nn = int(input())\na = [int(x) for x in input().split()]\n",
         "import sys\nn, *a = map(int, sys.stdin.read().split())\na = a[:n]\n"],
        ["s = sorted(set(a), reverse=True)\nans = s[1] if len(s) > 1 else -1\n",
         "s = sorted(set(a))\nans = s[-2] if len(s) >= 2 else -1\n",
         "m = max(a)\nrest = [x for x in a if x != m]\nans = max(rest) if rest else -1\n",
         "first = second = None\nfor x in a:\n    if first is None or x > first:\n        if first is not None:\n            second = first\n        first = x\n    elif x != first and (second is None or x > second):\n        second = x\nans = second if second is not None else -1\n",
         "import heapq\ntop = heapq.nlargest(2, set(a))\nans = top[1] if len(top) == 2 else -1\n"],
        ["print(ans)\n", "sys.stdout.write(str(ans) + '\\n')\n", "print(str(ans))\n"]],
    1: [["import sys\nlines = sys.stdin.read().split('\\n')\nt = int(lines[0])\nrows = lines[1:1 + t]\n",
         "t = int(input())\nrows = [input().strip() for _ in range(t)]\n",
         "import sys\ndata = sys.stdin.read().split()\nt = int(data[0])\nrows = data[1:1 + t]\n"],
        ["pairs = {')': '(', ']': '[', '}': '{'}\n", "match = dict(zip(')]}', '([{'))\npairs = match\n",
         "opening = '([{'\nclosing = ')]}'\npairs = {c: o for o, c in zip(opening, closing)}\n"],
        ["def ok(s):\n    st = []\n    for c in s:\n        if c in '([{':\n            st.append(c)\n        elif not st or st.pop() != pairs[c]:\n            return False\n    return not st\n",
         "def ok(s):\n    stack = []\n    for ch in s.strip():\n        if ch in pairs.values():\n            stack.append(ch)\n        else:\n            if len(stack) == 0 or stack[-1] != pairs[ch]:\n                return False\n            stack.pop()\n    return len(stack) == 0\n",
         "def ok(s):\n    st = ['#']\n    for c in s:\n        if c in pairs:\n            if st.pop() != pairs[c]:\n                return False\n        else:\n            st.append(c)\n    return len(st) == 1\n"],
        ["out = []\nfor s in rows:\n    out.append('YES' if ok(s) else 'NO')\nprint('\\n'.join(out))\n",
         "for s in rows:\n    print('YES' if ok(s) else 'NO')\n",
         "print('\\n'.join('YES' if ok(r) else 'NO' for r in rows))\n"]],
    2: [["import sys\ndata = sys.stdin.read().split()\nn, k = int(data[0]), int(data[1])\na = list(map(int, data[2:2 + n]))\n",
         "n, k = map(int, input().split())\na = list(map(int, input().split()))\n",
         "import sys\nn, k, *a = map(int, sys.stdin.read().split())\n"],
        ["seen = {}\ncount = 0\nfor x in a:\n    count += seen.get(k - x, 0)\n    seen[x] = seen.get(x, 0) + 1\n",
         "from collections import Counter\nc = Counter(a)\ncount = 0\nfor x, f in c.items():\n    y = k - x\n    if y > x:\n        count += f * c.get(y, 0)\n    elif y == x:\n        count += f * (f - 1) // 2\n",
         "from collections import defaultdict\nfreq = defaultdict(int)\ncount = 0\nfor x in a:\n    count += freq[k - x]\n    freq[x] += 1\n",
         "a.sort()\ni, j = 0, len(a) - 1\ncount = 0\nwhile i < j:\n    s = a[i] + a[j]\n    if s < k:\n        i += 1\n    elif s > k:\n        j -= 1\n    else:\n        if a[i] == a[j]:\n            m = j - i + 1\n            count += m * (m - 1) // 2\n            break\n        li = ri = 1\n        while i + li < j and a[i + li] == a[i]:\n            li += 1\n        while j - ri > i and a[j - ri] == a[j]:\n            ri += 1\n        count += li * ri\n        i += li\n        j -= ri\n"],
        ["print(count)\n", "sys.stdout.write(str(count) + '\\n')\n"]],
}
CPP_HEAD = ["#include <bits/stdc++.h>\nusing namespace std;\n", "#include <iostream>\n#include <vector>\n#include <algorithm>\nusing namespace std;\n"]
CPP = {
    0: [["int main() {\n    int n;\n    cin >> n;\n    vector<long long> a(n);\n    for (auto &x : a) cin >> x;\n",
         "int main() {\n    ios::sync_with_stdio(false);\n    cin.tie(nullptr);\n    int n;\n    cin >> n;\n    vector<long long> a(n);\n    for (int i = 0; i < n; i++) cin >> a[i];\n"],
        ["    sort(a.begin(), a.end());\n    a.erase(unique(a.begin(), a.end()), a.end());\n    long long ans = a.size() > 1 ? a[a.size() - 2] : -1;\n",
         "    long long m1 = LLONG_MIN, m2 = LLONG_MIN;\n    for (long long x : a) {\n        if (x > m1) { m2 = m1; m1 = x; }\n        else if (x < m1 && x > m2) m2 = x;\n    }\n    long long ans = m2 == LLONG_MIN ? -1 : m2;\n",
         "    set<long long> s(a.begin(), a.end());\n    long long ans = -1;\n    if (s.size() >= 2) { auto it = s.rbegin(); ++it; ans = *it; }\n"],
        ["    cout << ans << endl;\n    return 0;\n}\n", "    cout << ans << \"\\n\";\n}\n", "    printf(\"%lld\\n\", ans);\n    return 0;\n}\n"]],
    1: [["int main() {\n    int t;\n    cin >> t;\n    while (t--) {\n        string s;\n        cin >> s;\n",
         "int main() {\n    ios::sync_with_stdio(false);\n    int t;\n    cin >> t;\n    for (int q = 0; q < t; q++) {\n        string s;\n        cin >> s;\n"],
        ["        vector<char> st;\n        bool ok = true;\n        for (char c : s) {\n            if (c == '(' || c == '[' || c == '{') st.push_back(c);\n            else {\n                char want = c == ')' ? '(' : c == ']' ? '[' : '{';\n                if (st.empty() || st.back() != want) { ok = false; break; }\n                st.pop_back();\n            }\n        }\n        ok = ok && st.empty();\n",
         "        stack<char> st;\n        bool ok = true;\n        map<char, char> m = {{')', '('}, {']', '['}, {'}', '{'}};\n        for (char c : s) {\n            if (m.count(c)) {\n                if (st.empty() || st.top() != m[c]) { ok = false; break; }\n                st.pop();\n            } else st.push(c);\n        }\n        if (!st.empty()) ok = false;\n"],
        ["        cout << (ok ? \"YES\" : \"NO\") << \"\\n\";\n    }\n    return 0;\n}\n", "        puts(ok ? \"YES\" : \"NO\");\n    }\n}\n"]],
    2: [["int main() {\n    int n;\n    long long k;\n    cin >> n >> k;\n    vector<long long> a(n);\n    for (auto &x : a) cin >> x;\n",
         "int main() {\n    ios::sync_with_stdio(false);\n    cin.tie(nullptr);\n    int n;\n    long long k;\n    cin >> n >> k;\n    vector<long long> a(n);\n    for (int i = 0; i < n; i++) cin >> a[i];\n"],
        ["    unordered_map<long long, long long> seen;\n    long long cnt = 0;\n    for (long long x : a) {\n        auto it = seen.find(k - x);\n        if (it != seen.end()) cnt += it->second;\n        seen[x]++;\n    }\n",
         "    map<long long, long long> f;\n    long long cnt = 0;\n    for (long long x : a) {\n        cnt += f[k - x];\n        f[x] += 1;\n    }\n",
         "    sort(a.begin(), a.end());\n    long long cnt = 0;\n    for (int i = 0; i < n; i++) {\n        auto r = equal_range(a.begin() + i + 1, a.end(), k - a[i]);\n        cnt += r.second - r.first;\n    }\n"],
        ["    cout << cnt << endl;\n    return 0;\n}\n", "    printf(\"%lld\\n\", cnt);\n}\n"]],
}
# small personal habits that change the program's structure (inserted between parts)
PY_EXTRA = ["if n == 0:\n    print(-1)\n", "assert n >= 1\n", "res = None\n", "debug = False\n", "if len(a) != n:\n    a = a[:n]\n",
            "total = 0\n", "MOD = 10 ** 9 + 7\n", "def helper(v):\n    return v\n"]
CPP_EXTRA = ["    // read input\n    int dummy = 0;\n", "    const int MAXN = 200005;\n", "    if (n == 0) { cout << -1; return 0; }\n",
             "    long long tmp = 0;\n", "    bool debug = false;\n"]
NAMES = ["a", "arr", "nums", "v", "xs", "values", "lst", "data", "num", "x", "s", "st", "res", "ans", "out", "cnt", "i", "j", "k2",
         "best", "second", "first", "m1", "m2", "top", "freq", "seen", "count", "total", "line", "word", "buf"]


def _rename(code: str, rng: random.Random) -> str:
    """A copier's disguise: some variable names changed (the similarity check is meant to see through this)."""
    for old in rng.sample(["a", "ans", "count", "seen", "s", "st", "first", "second", "rows", "cnt", "f", "m1", "m2"], 5):
        code = re.sub(rf"\b{old}\b", rng.choice(NAMES) + str(rng.randint(1, 9)), code)
    return code


_PY_FILL = ["_ = 0", "pass", "tmp = None", "flag = True", "steps = 0", "x0 = 0", "ok_flag = False"]
_CPP_FILL = ["(void)0;", "int tmp = 0;", "bool flag = true;", "long long z = 0;", "int steps = 0;"]
_NO_BEFORE = re.compile(r"^\s*(else|elif|except|finally|}|#include|using|int main)")


def mutate(code: str, lang: str, rng: random.Random, n: int) -> str:
    """Small personal differences two people writing 'the same' solution still have."""
    for _ in range(n):
        r = rng.random()
        if r < 0.2:
            code = re.sub(r"(\b\w+) \+= 1\b", r"\1 = \1 + 1", code, count=1)
        elif r < 0.35:
            code = re.sub(r"\b(\w+) > (\w+)\b", r"\2 < \1", code, count=1)
        elif r < 0.5:
            lines = [i for i, ln in enumerate(code.split("\n")) if re.search(r" = [^=\n]+$", ln)]
            if lines:
                L = code.split("\n")
                i = rng.choice(lines)
                head, _, expr = L[i].partition(" = ")
                L[i] = f"{head} = ({expr.rstrip(';')})" + (";" if expr.rstrip().endswith(";") else "")
                code = "\n".join(L)
        else:
            L = code.split("\n")
            spots = [i for i, ln in enumerate(L) if ln.strip() and not _NO_BEFORE.match(ln) and i > 0]
            if spots:
                i = rng.choice(spots)
                indent = re.match(r"\s*", L[i]).group(0)
                L.insert(i, indent + rng.choice(_PY_FILL if lang == "python" else _CPP_FILL))
                code = "\n".join(L)
    return code


def program(item: int, lang: str, rng: random.Random, n_extra: float = 1.2, personal: bool = True) -> str:
    parts = (PY if lang == "python" else CPP)[item]
    chosen = [rng.choice(p) for p in parts]
    extras = PY_EXTRA if lang == "python" else CPP_EXTRA
    for _ in range(np.random.default_rng(rng.randint(0, 10 ** 9)).poisson(n_extra)):
        pos = rng.randint(1, len(chosen) - 1)
        chosen.insert(pos, rng.choice(extras))
    code = (rng.choice(CPP_HEAD) if lang == "cpp" else "") + "".join(chosen)
    if personal:
        code = mutate(code, lang, rng, 1 + np.random.default_rng(rng.randint(0, 10 ** 9)).poisson(3))
        if rng.random() < 0.85:                                         # people pick their own names
            code = _rename(code, rng)
    return code


WEB = {(it, lang): [program(it, lang, random.Random(1000 + 10 * it + j + (0 if lang == "python" else 5)), n_extra=0, personal=False)
                    for j in range(2)] for it in range(3) for lang in ("python", "cpp")}


# ---------------------------------------------------------------- one candidate on one problem
class Timeline:
    def __init__(self, sid: str):
        self.sid, self.ev, self.runs, self.seq = sid, [], [], 0

    def add(self, t, type_, item, chars=0, meta=None, option=""):
        self.seq += 1
        self.ev.append(dict(session_id=self.sid, seq=self.seq, t=round(float(t), 2), type=type_, item=item, option=option,
                            chars=int(chars), meta=meta))

    def run(self, t, item, kind, lang, code, verdict, passed, total):
        self.runs.append(dict(session_id=self.sid, item=item, kind=kind, language=lang, code=code, verdict=verdict,
                              passed=passed, total=total, t=round(float(t), 2)))


def _type(tl: Timeline, item: int, t: float, chars: int, cps: float, edit: float, rng: random.Random, length0: int,
          max_ins=(1, 3), pause=(0.15, 0.45)) -> tuple[float, int]:
    """Typing in 5 s windows (inserted / deleted chars), with thinking pauses. Returns end time and code length."""
    length, left = length0, chars
    while left > 0:
        if rng.random() < pause[0]:                                     # a thinking pause
            t += rng.uniform(8, 60) if rng.random() < pause[1] else rng.uniform(5, 15)
            continue
        ins = max(1, int(rng.gauss(cps, cps * 0.25) * 5))
        ins = min(ins, left)
        dele = int(ins * edit * rng.uniform(0.5, 1.5)) if rng.random() < 0.7 else 0
        length += ins - min(dele, length)
        left -= ins
        tl.add(t + 5, "code_typing", item, meta=dict(ins=ins + dele, dele=dele, keys=ins + dele + rng.randint(0, 6),
                                                    max_ins=rng.randint(*max_ins), len=length))
        t += 5
    return t, length


def honest_problem(tl, item, lang, t, skill, rng, expert=False):
    """Returns (end time, final code, accepted)."""
    P = PROBLEMS[item]
    final = program(item, lang, rng)
    tl.add(t, "item_shown", item)
    t += rng.uniform(15, 90) * (0.4 if expert else 1)                   # reading the statement
    cps = rng.uniform(5.5, 8.5) if expert else min(7, max(0.8, rng.gauss(1.5 + 3.5 * skill, 0.7)))
    edit = rng.uniform(0.04, 0.15) if expert else rng.uniform(0.15, 0.6)
    typed_total = int(len(final) * (1 + edit) * rng.uniform(0.9, 1.2))
    solve_p = min(0.97, P["hard"] * (0.35 + 0.75 * skill) + (0.15 if expert else 0))
    solved = rng.random() < solve_p
    n_attempts = 1 if expert and rng.random() < 0.7 else rng.randint(1, 4)
    length = 0
    for k in range(n_attempts):
        chunk = typed_total // n_attempts if k else int(typed_total * rng.uniform(0.6, 0.85))
        t, length = _type(tl, item, t, chunk, cps, edit, rng, length,
                          max_ins=(2, 8) if expert else (1, 4), pause=(0.08, 0.3) if expert else (0.18, 0.5))
        if rng.random() < 0.3:                                          # moving own lines: a small paste
            c = rng.randint(15, 80)
            tl.add(t + rng.uniform(1, 4), "paste", item, chars=c)
            length += c
        if rng.random() < 0.08:                                         # a notification: leaves and comes back
            tl.add(t, "focus_lost", item)
            t += rng.uniform(3, 40)
            tl.add(t, "focus_gained", item)
        for _ in range(rng.randint(0 if expert else 1, 2)):             # sample runs
            t += rng.uniform(3, 12)
            ok_s = rng.random() < (0.85 if k == n_attempts - 1 else 0.35)
            tl.run(t, item, "run", lang, final if k == n_attempts - 1 else final[: len(final) * 3 // 4],
                   "accepted" if ok_s else "wrong_answer", 1 if ok_s else 0, 1)
        t += rng.uniform(5, 40)
        last = k == n_attempts - 1
        if last and solved:
            tl.run(t, item, "submit", lang, final, "accepted", N_HIDDEN[item], N_HIDDEN[item])
            return t, final, True
        p = rng.randint(0, N_HIDDEN[item] - 1)
        verdict = "time_limit" if item == 2 and rng.random() < 0.5 else "wrong_answer"
        tl.run(t, item, "submit", lang, final if last else final[: len(final) * 3 // 4], verdict, p, N_HIDDEN[item])
        t += rng.uniform(10, 60)
    return t, final, False


def cheat_problem(tl, item, lang, t, kind, rng, source_code=None, source_t=None):
    """One problem done with malpractice of the given kind. Returns (end time, final code)."""
    tl.add(t, "item_shown", item)
    t += rng.uniform(10, 60)
    if kind == "web_paste":
        final = rng.choice(WEB[(item, lang)])
        if rng.random() < 0.3:
            final = mutate(final, lang, rng, 1)
        if rng.random() < 0.5:                                          # a little own typing first
            t, _ = _type(tl, item, t, rng.randint(20, 120), rng.uniform(2, 4), 0.3, rng, 0)
        tl.add(t, "focus_lost", item)
        t += rng.uniform(30, 180)
        tl.add(t, "focus_gained", item)
        t += rng.uniform(1, 25)
        tl.add(t, "paste", item, chars=int(len(final) * rng.uniform(0.75, 1.0)))
        t, _ = _type(tl, item, t, rng.randint(5, 40), 2.5, 0.4, rng, len(final))
    elif kind == "copy_pair":
        final = _rename(source_code, rng) if rng.random() < 0.5 else source_code   # half do not bother renaming
        if rng.random() < 0.3:
            final = mutate(final, lang, rng, rng.randint(1, 2))
        if rng.random() < 0.15:
            final = final.replace("\n", "\n\n", 1)
        t = max(t, (source_t or t) + rng.uniform(40, 400))             # after the partner had it
        if rng.random() < 0.6:                                          # received over chat: leave, paste
            tl.add(t - rng.uniform(20, 90), "focus_lost", item)
            tl.add(t - rng.uniform(1, 15), "focus_gained", item)
            tl.add(t, "paste", item, chars=int(len(final) * rng.uniform(0.85, 1.0)))
            t, _ = _type(tl, item, t, rng.randint(5, 30), 2.5, 0.3, rng, len(final))
        else:                                                           # read off the partner's screen / phone
            t, _ = _type(tl, item, t, len(final), rng.uniform(4, 7), rng.uniform(0.0, 0.05), rng, 0, max_ins=(1, 3), pause=(0.03, 0.1))
    elif kind == "transcribe":
        final = program(item, lang, rng, n_extra=0.5)
        t += rng.uniform(60, 300)                                       # still, focused, nothing typed
        t, _ = _type(tl, item, t, len(final), rng.uniform(4, 7), rng.uniform(0.0, 0.05), rng, 0, max_ins=(1, 3), pause=(0.03, 0.1))
    else:                                                               # inject
        final = program(item, lang, rng, n_extra=0.5)
        left, length = len(final), 0
        t, length = _type(tl, item, t, rng.randint(10, 60), 3, 0.3, rng, 0)
        for _ in range(rng.randint(1, 3)):
            b = min(left, rng.randint(150, 500))
            left -= b
            length += b
            tl.add(t + 5, "code_typing", item, meta=dict(ins=b, dele=0, keys=rng.randint(0, 4), max_ins=b, len=length))
            t += 5 + rng.uniform(1, 30)
    if rng.random() < 0.4:
        t += rng.uniform(3, 10)
        tl.run(t, item, "run", lang, final, "accepted", 1, 1)
    t += rng.uniform(5, 60)
    tl.run(t, item, "submit", lang, final, "accepted", N_HIDDEN[item], N_HIDDEN[item])
    return t + rng.uniform(5, 30), final


# ---------------------------------------------------------------- whole sittings
def generate(n_sittings: int = 30, per_sitting: int = 170, seed: int = 7, cheat_rate: float = 0.06):
    rng = random.Random(seed)
    sess, ev, runs = [], [], []
    for w in range(n_sittings):
        n = per_sitting + rng.randint(-20, 20)
        ids = [f"C{w + 1}-S{i:05d}" for i in range(n)]
        kinds = {}
        cheaters = rng.sample(ids, max(2, int(n * cheat_rate)))
        pairs = []
        for sid in cheaters:
            kinds[sid] = rng.choices(["web_paste", "copy_pair", "transcribe", "inject"], [0.35, 0.3, 0.2, 0.15])[0]
        cp = [s for s in cheaters if kinds[s] == "copy_pair"]
        if len(cp) % 2:
            kinds[cp.pop()] = "web_paste"
        pairs = [(cp[i], cp[i + 1]) for i in range(0, len(cp), 2)]
        partner = {b: a for a, b in pairs}                               # b copies from a
        done: dict[str, dict] = {}
        order = [s for s in ids if s not in partner] + [s for s in ids if s in partner]
        for sid in order:
            r = random.Random(rng.randint(0, 10 ** 9))
            lang = "python" if r.random() < 0.6 else "cpp"
            if sid in partner:
                lang = done[partner[sid]]["lang"]
            skill = r.betavariate(2.2, 2)
            expert = r.random() < 0.08
            kind = kinds.get(sid, "none")
            affected = set()
            if kind != "none":
                affected = set(r.sample(range(3), r.choices([1, 2, 3], [0.4, 0.35, 0.25])[0]))
            tl = Timeline(sid)
            t = r.uniform(5, 40)
            finals, times = {}, {}
            for item in range(3):
                if t > 3500:
                    break
                if item in affected and kind == "copy_pair" and sid in partner:
                    src = done[partner[sid]]
                    t, code = cheat_problem(tl, item, lang, t, kind, r, src["finals"].get(item, program(item, lang, r)),
                                            src["times"].get(item))
                elif item in affected and kind in ("web_paste", "transcribe", "inject"):
                    t, code = cheat_problem(tl, item, lang, t, kind, r)
                else:
                    t, code, _ = honest_problem(tl, item, lang, t, skill, r, expert=expert)
                finals[item], times[item] = code, t
                t += r.uniform(10, 60)
            done[sid] = dict(lang=lang, finals=finals, times=times)
            ev += tl.ev
            runs += tl.runs
            sess.append(dict(session_id=sid, window_id=w, is_synthetic=1, device="desktop", bandwidth_class="normal",
                             verdict="confirmed" if kind != "none" else "clear", _truth_type=kind, _expert=int(expert),
                             _partner=partner.get(sid, next((b for a, b in pairs if a == sid), ""))))
    return pd.DataFrame(sess), pd.DataFrame(ev), pd.DataFrame(runs)
