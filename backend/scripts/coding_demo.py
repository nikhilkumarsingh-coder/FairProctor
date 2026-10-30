"""Builds the demo coding test: three campus-hiring style problems with sample + hidden tests and reference solutions.

    python -m backend.scripts.coding_demo          # writes backend/demo_data/coding_problems.json

The JSON is the same format an admin uploads (POST /api/admin/tests/{id}/problems).
"""
from __future__ import annotations

import json
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "demo_data", "coding_problems.json")

STARTER_ARRAY = {
    "python": "import sys\n\ndef main():\n    data = sys.stdin.read().split()\n    n = int(data[0])\n    a = list(map(int, data[1:1 + n]))\n    # write your code here\n\nmain()\n",
    "cpp": "#include <bits/stdc++.h>\nusing namespace std;\n\nint main() {\n    int n;\n    cin >> n;\n    vector<long long> a(n);\n    for (auto &x : a) cin >> x;\n    // write your code here\n    return 0;\n}\n",
    "java": "import java.util.*;\nimport java.io.*;\n\npublic class Main {\n    public static void main(String[] args) throws IOException {\n        BufferedReader br = new BufferedReader(new InputStreamReader(System.in));\n        StreamTokenizer st = new StreamTokenizer(br);\n        st.nextToken();\n        int n = (int) st.nval;\n        long[] a = new long[n];\n        for (int i = 0; i < n; i++) { st.nextToken(); a[i] = (long) st.nval; }\n        // write your code here\n    }\n}\n",
    "javascript": "const data = require('fs').readFileSync(0, 'utf8').trim().split(/\\s+/).map(Number);\nconst n = data[0];\nconst a = data.slice(1, 1 + n);\n// write your code here\n",
}


def second_largest(a):
    d = sorted(set(a), reverse=True)
    return d[1] if len(d) > 1 else -1


def balanced(s):
    pair, st = {")": "(", "]": "[", "}": "{"}, []
    for ch in s:
        if ch in "([{":
            st.append(ch)
        elif not st or st.pop() != pair[ch]:
            return False
    return not st


def pairs(a, k):
    seen, c = {}, 0
    for x in a:
        c += seen.get(k - x, 0)
        seen[x] = seen.get(x, 0) + 1
    return c


def build(seed: int = 26) -> dict:
    rng = random.Random(seed)

    # 1. second largest distinct
    def case1(a):
        return dict(input=f"{len(a)}\n{' '.join(map(str, a))}\n", output=f"{second_largest(a)}\n")
    p1_hidden = [case1([7]), case1([5, 5, 5]), case1([-3, -1, -2, -1]), case1([10 ** 9, -10 ** 9])]
    for n in (10, 1000, 100000):
        p1_hidden.append(case1([rng.randint(-10 ** 9, 10 ** 9) for _ in range(n)]))
    p1_hidden.append(case1([rng.randint(1, 3) for _ in range(50000)]))

    # 2. balanced brackets
    def make_balanced(n):
        out, st = [], []
        for _ in range(n):
            if st and rng.random() < 0.5:
                out.append({"(": ")", "[": "]", "{": "}"}[st.pop()])
            else:
                ch = rng.choice("([{")
                st.append(ch)
                out.append(ch)
        while st:
            out.append({"(": ")", "[": "]", "{": "}"}[st.pop()])
        return "".join(out)

    def case2(lines):
        return dict(input=f"{len(lines)}\n" + "\n".join(lines) + "\n",
                    output="\n".join("YES" if balanced(s) else "NO" for s in lines) + "\n")
    small = ["()", "([]{})", "(]", "((", "}{", "{[()()]}", "([)]", "(((())))"]
    p2_hidden = [case2(small)]
    for n in (20, 200, 50000):
        lines = []
        for _ in range(5):
            s = make_balanced(n)
            if rng.random() < 0.5:
                i = rng.randrange(len(s))
                s = s[:i] + rng.choice(")]}([{") + s[i + 1:]
            lines.append(s)
        p2_hidden.append(case2(lines))

    # 3. count pairs with sum k (needs O(n) or O(n log n); O(n^2) runs out of time)
    def case3(a, k):
        return dict(input=f"{len(a)} {k}\n{' '.join(map(str, a))}\n", output=f"{pairs(a, k)}\n")
    p3_hidden = [case3([1, 1, 1, 1], 2), case3([5], 10), case3([0, 0, 0], 0), case3([-2, 7, 4, -5, 11], 2)]
    for n, lim in ((100, 50), (5000, 1000), (200000, 10 ** 6), (200000, 3)):
        a = [rng.randint(-lim, lim) for _ in range(n)]
        p3_hidden.append(case3(a, rng.randint(-lim, lim)))

    py1 = "import sys\nd=sys.stdin.read().split();n=int(d[0]);a=set(map(int,d[1:1+n]))\ns=sorted(a,reverse=True)\nprint(s[1] if len(s)>1 else -1)\n"
    py2 = ("import sys\nL=sys.stdin.read().split('\\n');t=int(L[0]);P={')':'(',']':'[','}':'{'}\nout=[]\n"
           "for s in L[1:1+t]:\n    st=[];ok=True\n    for c in s.strip():\n        if c in '([{': st.append(c)\n"
           "        elif not st or st.pop()!=P[c]: ok=False; break\n    out.append('YES' if ok and not st else 'NO')\nprint('\\n'.join(out))\n")
    cpp3 = ("#include <bits/stdc++.h>\nusing namespace std;\nint main(){ios::sync_with_stdio(false);cin.tie(nullptr);"
            "int n;long long k;cin>>n>>k;unordered_map<long long,long long> seen;seen.reserve(n*2);long long c=0;"
            "for(int i=0;i<n;i++){long long x;cin>>x;auto it=seen.find(k-x);if(it!=seen.end())c+=it->second;seen[x]++;}"
            "cout<<c<<\"\\n\";}\n")
    starter3 = {
        "python": "import sys\n\ndef main():\n    data = sys.stdin.read().split()\n    n, k = int(data[0]), int(data[1])\n    a = list(map(int, data[2:2 + n]))\n    # write your code here\n\nmain()\n",
        "cpp": "#include <bits/stdc++.h>\nusing namespace std;\n\nint main() {\n    int n;\n    long long k;\n    cin >> n >> k;\n    vector<long long> a(n);\n    for (auto &x : a) cin >> x;\n    // write your code here\n    return 0;\n}\n",
        "java": STARTER_ARRAY["java"].replace("int n = (int) st.nval;", "int n = (int) st.nval;\n        st.nextToken();\n        long k = (long) st.nval;"),
        "javascript": "const data = require('fs').readFileSync(0, 'utf8').trim().split(/\\s+/).map(Number);\nconst n = data[0], k = data[1];\nconst a = data.slice(2, 2 + n);\n// write your code here\n",
    }
    starter2 = {
        "python": "import sys\n\ndef main():\n    lines = sys.stdin.read().split('\\n')\n    t = int(lines[0])\n    for s in lines[1:1 + t]:\n        s = s.strip()\n        # print YES or NO for s\n\nmain()\n",
        "cpp": "#include <bits/stdc++.h>\nusing namespace std;\n\nint main() {\n    int t;\n    cin >> t;\n    while (t--) {\n        string s;\n        cin >> s;\n        // print YES or NO for s\n    }\n    return 0;\n}\n",
        "java": "import java.util.*;\nimport java.io.*;\n\npublic class Main {\n    public static void main(String[] args) throws IOException {\n        BufferedReader br = new BufferedReader(new InputStreamReader(System.in));\n        int t = Integer.parseInt(br.readLine().trim());\n        StringBuilder out = new StringBuilder();\n        for (int i = 0; i < t; i++) {\n            String s = br.readLine().trim();\n            // append YES or NO for s\n        }\n        System.out.print(out);\n    }\n}\n",
        "javascript": "const lines = require('fs').readFileSync(0, 'utf8').split('\\n');\nconst t = Number(lines[0]);\nfor (let i = 1; i <= t; i++) {\n  const s = lines[i].trim();\n  // print YES or NO for s\n}\n",
    }
    return {"problems": [
        dict(title="Second largest", time_limit=2, starter=STARTER_ARRAY,
             statement=("Given n integers, print the second largest **distinct** value. If all values are equal "
                        "(or n = 1), print -1.\n\nInput\nThe first line has n (1 ≤ n ≤ 100000). The second line has n "
                        "integers, each between -10^9 and 10^9.\n\nOutput\nOne integer."),
             samples=[dict(input="5\n3 9 7 9 1\n", output="7\n"), dict(input="3\n4 4 4\n", output="-1\n")],
             tests=p1_hidden, solution=dict(language="python", code=py1)),
        dict(title="Balanced brackets", time_limit=2, starter=starter2,
             statement=("A string of brackets ( ) [ ] { } is balanced if every opening bracket is closed by the same "
                        "kind in the right order. For each string print YES if it is balanced, otherwise NO.\n\nInput\n"
                        "The first line has t (1 ≤ t ≤ 10). Each of the next t lines has one string of length 1 to 100000."
                        "\n\nOutput\nt lines, YES or NO."),
             samples=[dict(input="3\n([]{})\n(]\n((\n", output="YES\nNO\nNO\n")],
             tests=p2_hidden, solution=dict(language="python", code=py2)),
        dict(title="Pairs with sum k", time_limit=2, starter=starter3,
             statement=("Count the pairs of positions i < j with a[i] + a[j] = k.\n\nInput\nThe first line has n and k "
                        "(1 ≤ n ≤ 200000, |k| ≤ 2·10^6). The second line has n integers, each between -10^6 and 10^6."
                        "\n\nOutput\nThe number of pairs (it can be larger than 2^31).\n\nA solution that tries every pair "
                        "is too slow for the largest tests."),
             samples=[dict(input="5 6\n1 5 7 -1 5\n", output="3\n"), dict(input="4 2\n1 1 1 1\n", output="6\n")],
             tests=p3_hidden, solution=dict(language="cpp", code=cpp3)),
    ]}


if __name__ == "__main__":
    data = build()
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)
    print(f"wrote {OUT} ({os.path.getsize(OUT) / 1024:.0f} KB): " +
          ", ".join(f"{p['title']} ({len(p['samples'])} samples, {len(p['tests'])} hidden)" for p in data["problems"]))
