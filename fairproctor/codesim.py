"""Code similarity that survives renaming, re-spacing and comments (the idea behind MOSS).

1. Tokenise: comments dropped, every identifier becomes V, numbers N, strings S; keywords and operators kept.
2. Fingerprint: hashes of every k consecutive tokens, thinned by winnowing (the smallest hash in each window),
   remembering the source line of each fingerprint so the reviewer can see which lines match.
3. Compare: share of the smaller program's fingerprints found in the other one (containment), after removing
   fingerprints of the starter code and fingerprints that most candidates share (reading input, printing).
"""
from __future__ import annotations

import re
import zlib

K, W = 6, 4

KEYWORDS = {
    "python": set("""False None True and as assert break class continue def del elif else except finally for from global if
                     import in is lambda nonlocal not or pass raise return try while with yield print input range len int str
                     list dict set map sorted sum min max abs enumerate zip open sys stdin read split readline append pop
                     items keys values get""".split()),
    "c": set("""auto bool break case catch char class const continue default delete do double else enum explicit extern false
                float for friend goto if inline int long namespace new nullptr operator private protected public register
                return short signed sizeof static struct switch template this throw true try typedef typename union unsigned
                using virtual void volatile while include define std vector string map unordered_map set unordered_set pair
                cin cout endl push_back size begin end sort auto main printf scanf String System out println print Scanner
                nextInt nextLong nextLine import java util io static final new class public private return length charAt
                const let var function console log require readFileSync split map Number parseInt push pop length""".split()),
}
TOKEN = re.compile(r"""
    (?P<str>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`)
  | (?P<num>\b\d[\d_]*(?:\.\d+)?(?:[eE][+-]?\d+)?[lLfFuU]*\b|\b0x[0-9a-fA-F]+\b)
  | (?P<id>[A-Za-z_][A-Za-z_0-9]*)
  | (?P<op>==|!=|<=|>=|\+\+|--|&&|\|\||<<|>>|->|::|\*\*|//|\+=|-=|\*=|/=|%=|[{}()\[\];,.:?+\-*/%<>=!&|^~@])
""", re.VERBOSE)


def _strip_comments(code: str, language: str) -> str:
    """Remove comments but keep line breaks, so line numbers still point at the original code."""
    keep_lines = lambda m: "\n" * m.group(0).count("\n")
    if language == "python":
        code = re.sub(r'("""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\')', keep_lines, code)     # docstrings
        return re.sub(r"#[^\n]*", "", code)
    code = re.sub(r"/\*[\s\S]*?\*/", keep_lines, code)
    code = re.sub(r"//[^\n]*", "", code)
    return re.sub(r"^\s*#\s*include[^\n]*", "", code, flags=re.M)                        # includes say nothing


def tokens(code: str, language: str, raw: bool = False) -> list[tuple[str, int]]:
    """(normalised token, line number) pairs. raw=True keeps names and values: a verbatim copy keeps them too."""
    kw = KEYWORDS["python" if language == "python" else "c"]
    out = []
    for ln, line in enumerate(_strip_comments(code, language).split("\n"), start=1):
        for m in TOKEN.finditer(line):
            kind = m.lastgroup
            v = m.group(0)
            if raw:
                out.append((v, ln))
            elif kind == "str":
                out.append(("S", ln))
            elif kind == "num":
                out.append(("N", ln))
            elif kind == "id":
                out.append((v if v in kw else "V", ln))
            else:
                out.append((v, ln))
    return out


def fingerprints(code: str, language: str, raw: bool = False) -> dict[int, set[int]]:
    """Winnowed k-gram hashes → the source lines they cover."""
    tk = tokens(code, language, raw)
    if len(tk) < K:
        return {}
    grams = []
    for i in range(len(tk) - K + 1):
        h = zlib.crc32(" ".join(t for t, _ in tk[i:i + K]).encode())
        grams.append((h, tk[i][1], tk[i + K - 1][1]))
    out: dict[int, set[int]] = {}
    last = None
    for i in range(max(1, len(grams) - W + 1)):
        win = grams[i:i + W]
        j = min(range(len(win)), key=lambda x: (win[x][0], -x))                # rightmost minimum
        pick = i + j
        if pick != last:
            h, a, b = grams[pick]
            out.setdefault(h, set()).update(range(a, b + 1))
            last = pick
    return out


def similarity(fa: dict[int, set[int]], fb: dict[int, set[int]], ignore: set[int] = frozenset(),
               min_size: int = 12) -> tuple[float, set[int], set[int]]:
    """Containment of the smaller program in the larger one, and the matching line numbers on each side.
    Programs with fewer than `min_size` distinctive fingerprints are too short to judge (returns 0)."""
    a = set(fa) - ignore
    b = set(fb) - ignore
    if min(len(a), len(b)) < min_size:
        return 0.0, set(), set()
    shared = a & b
    sim = len(shared) / min(len(a), len(b))
    la = set().union(*(fa[h] for h in shared)) if shared else set()
    lb = set().union(*(fb[h] for h in shared)) if shared else set()
    return sim, la, lb


def common_fingerprints(fps: list[dict[int, set[int]]], share: float = 0.3, starter: list[str] = (), language: str = "python") -> set[int]:
    """Fingerprints in more than `share` of the programs (everyone reads input the same way) plus the starter code's."""
    from collections import Counter
    c = Counter(h for f in fps for h in f)
    common = {h for h, n in c.items() if n > share * max(len(fps), 1)} if len(fps) >= 10 else set()
    for s in starter:
        common |= set(fingerprints(s, language))
    return common
