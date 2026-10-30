"""Pilot roles: what each participant is secretly asked to do, in English and Hindi, and how roles are assigned.

Honest roles put a candidate in the circumstances the project is about (a dim room, a shared room, a phone held low,
a slow connection, interruptions); cheating roles act out the malpractice the model looks for. `expect` lists the
reason families a correct flag should show (the "right reason" check in the report).
"""
from __future__ import annotations

import random

MCQ = "mcq"
CODING = "coding"

ROLES: dict[str, dict] = {
    # ------------------------------------------------------------------ question test, honest
    "honest_quiet": dict(test=MCQ, kind="honest", env="quiet room",
        title=("Honest · quiet room", "ईमानदार · शांत कमरा"),
        do=[("Sit alone in a quiet room with good light, on a laptop or a phone.",
             "अच्छी रोशनी वाले शांत कमरे में अकेले बैठें, लैपटॉप या फ़ोन पर।"),
            ("Answer every question honestly. Take your time.", "हर प्रश्न का उत्तर ईमानदारी से दें। आराम से करें।")]),
    "honest_dim": dict(test=MCQ, kind="honest", env="dim room",
        title=("Honest · dim room", "ईमानदार · कम रोशनी"),
        do=[("Turn most lights off: keep only one dim light on, or sit with a lamp or window behind you.",
             "ज़्यादातर लाइटें बंद रखें: सिर्फ़ एक धीमी लाइट जलाएं, या पीछे लैंप/खिड़की रखकर बैठें।"),
            ("Answer every question honestly.", "हर प्रश्न का उत्तर ईमानदारी से दें।")]),
    "honest_shared": dict(test=MCQ, kind="honest", env="shared room",
        title=("Honest · shared room", "ईमानदार · साझा कमरा"),
        do=[("Sit where other people are around (home, hostel or a cafe).", "ऐसी जगह बैठें जहां और लोग हों (घर, हॉस्टल या कैफ़े)।"),
            ("Ask someone to walk behind you 3–4 times, and once to stand behind you for about 10 seconds.",
             "किसी से कहें कि आपके पीछे से 3–4 बार गुज़रे, और एक बार लगभग 10 सेकंड पीछे खड़ा रहे।"),
            ("Nobody helps you. Answer honestly.", "कोई आपकी मदद नहीं करेगा। ईमानदारी से उत्तर दें।")]),
    "honest_phone_low": dict(test=MCQ, kind="honest", env="phone held low",
        title=("Honest · phone held low", "ईमानदार · फ़ोन नीचे पकड़ा"),
        do=[("Use your phone. Hold it low or keep it flat on the table, so you look down at it.",
             "फ़ोन इस्तेमाल करें। उसे नीचे पकड़ें या मेज़ पर सीधा रखें, ताकि आप नीचे देखकर पढ़ें।"),
            ("Answer every question honestly.", "हर प्रश्न का उत्तर ईमानदारी से दें।")]),
    "honest_slow": dict(test=MCQ, kind="honest", env="slow connection",
        title=("Honest · slow connection", "ईमानदार · धीमा इंटरनेट"),
        do=[("Use your phone on mobile data, not Wi-Fi. If your phone allows it, switch to 3G or 2G "
             "(Settings → Mobile network → Preferred network type).",
             "Wi-Fi नहीं, मोबाइल डेटा पर फ़ोन इस्तेमाल करें। हो सके तो 3G या 2G चुनें "
             "(Settings → Mobile network → Preferred network type)।"),
            ("Answer every question honestly.", "हर प्रश्न का उत्तर ईमानदारी से दें।")]),
    "honest_interrupted": dict(test=MCQ, kind="honest", env="interrupted",
        title=("Honest · interrupted", "ईमानदार · बीच में रुकावट"),
        do=[("Twice during the test, switch to another app for a few seconds (reply to a message), then come back.",
             "टेस्ट के दौरान दो बार कुछ सेकंड के लिए दूसरे ऐप पर जाएं (किसी मैसेज का जवाब दें), फिर लौट आएं।"),
            ("Never look up an answer. Answer honestly.", "कभी कोई उत्तर न खोजें। ईमानदारी से उत्तर दें।")]),
    # ------------------------------------------------------------------ question test, malpractice (role-play)
    "cheat_phone": dict(test=MCQ, kind="cheat", malpractice="second phone", expect={"pause", "timing", "phone"},
        title=("Second phone", "दूसरा फ़ोन"),
        do=[("Keep a second phone below the camera, out of view.", "एक दूसरा फ़ोन कैमरे के नीचे रखें, जहां वह न दिखे।"),
            ("On 8–10 of the hardest questions, find the answer on it (calculator, search, or ask a friend on chat). "
             "Don't touch the test screen while you look.",
             "8–10 सबसे कठिन प्रश्नों का उत्तर उस फ़ोन पर ढूंढें (कैलकुलेटर, सर्च, या चैट पर दोस्त से पूछें)। "
             "देखते समय टेस्ट की स्क्रीन को न छुएं।"),
            ("Answer the rest yourself. Don't make it obvious.", "बाक़ी ख़ुद हल करें। साफ़ दिखने न दें।")]),
    "cheat_search": dict(test=MCQ, kind="cheat", malpractice="searching", expect={"focus", "paste", "timing"},
        title=("Searching for answers", "उत्तर सर्च करना"),
        do=[("On 5–8 questions, leave the test tab, search for the answer, come back and answer.",
             "5–8 प्रश्नों पर टेस्ट का टैब छोड़ें, उत्तर सर्च करें, वापस आकर उत्तर दें।"),
            ("For the typed answers (the last 5 questions), copy and paste the answer when you can.",
             "लिखकर देने वाले उत्तरों (आख़िरी 5 प्रश्न) में जहां हो सके उत्तर कॉपी-पेस्ट करें।")]),
    "cheat_pair": dict(test=MCQ, kind="cheat", malpractice="sharing answers", expect={"match"}, pair=True,
        title=("Sharing answers with a partner", "साथी के साथ उत्तर बांटना"),
        do=[("Your partner is {partner}. Share answers on chat while you both write.",
             "आपका साथी {partner} है। दोनों लिखते समय चैट पर उत्तर बांटें।"),
            ("One of you solves, the other copies, on at least 12 questions — including some wrong answers.",
             "कम से कम 12 प्रश्नों पर एक हल करे, दूसरा कॉपी करे — कुछ ग़लत उत्तरों समेत।"),
            ("Try to answer at about the same time.", "लगभग एक ही समय पर उत्तर देने की कोशिश करें।")]),
    "cheat_helper": dict(test=MCQ, kind="cheat", malpractice="helper in the room", expect={"person", "timing", "pause"},
        title=("A helper in the room", "कमरे में मदद करने वाला"),
        do=[("Ask a friend to sit next to you for about 10 questions in the middle of the test and tell you the answers.",
             "टेस्ट के बीच में लगभग 10 प्रश्नों के लिए किसी दोस्त को पास बिठाएं जो उत्तर बताए।"),
            ("They may come into the camera view now and then.", "वह कभी-कभी कैमरे में दिख सकता है।")]),
    # ------------------------------------------------------------------ coding test
    "code_honest": dict(test=CODING, kind="honest", env="own code",
        title=("Honest coder", "ईमानदार कोडर"),
        do=[("Write your own code in any language. Run the samples, fix mistakes, submit.",
             "किसी भी भाषा में अपना कोड लिखें। सैंपल चलाएं, ग़लतियां ठीक करें, सबमिट करें।"),
            ("It's fine to copy and move your own lines, and to leave the tab once for a message.",
             "अपनी ही लाइनें कॉपी करना और एक बार मैसेज के लिए टैब छोड़ना ठीक है।")]),
    "code_web": dict(test=CODING, kind="cheat", malpractice="pasted from the web", expect={"paste", "typing"},
        title=("Copy from the internet", "इंटरनेट से कॉपी"),
        do=[("For 1–2 problems, find a solution online (or ask an AI chatbot) in another tab and paste it in.",
             "1–2 प्रश्नों के लिए दूसरे टैब में ऑनलाइन (या AI चैटबॉट से) हल ढूंढें और पेस्ट करें।"),
            ("Write the other problems yourself.", "बाक़ी प्रश्न ख़ुद लिखें।")]),
    "code_pair": dict(test=CODING, kind="cheat", malpractice="copied from a partner", expect={"code_match"}, pair=True,
        title=("Copy from a partner", "साथी से कॉपी"),
        do=[("Your partner is {partner}. For one problem, one of you sends the program on chat; the other changes a few "
             "variable names and submits it.",
             "आपका साथी {partner} है। एक प्रश्न के लिए एक अपना प्रोग्राम चैट पर भेजे; दूसरा कुछ वेरिएबल के नाम बदलकर सबमिट करे।"),
            ("Write the other problems yourselves.", "बाक़ी प्रश्न ख़ुद लिखें।")]),
    "code_retype": dict(test=CODING, kind="cheat", malpractice="typed from a phone", expect={"typing", "timing"},
        title=("Type it from your phone", "फ़ोन से देखकर टाइप"),
        do=[("For 1–2 problems, look at a solution on your phone and type it in. Don't paste.",
             "1–2 प्रश्नों के लिए फ़ोन पर हल देखकर टाइप करें। पेस्ट न करें।"),
            ("Write the other problems yourself.", "बाक़ी प्रश्न ख़ुद लिखें।")]),
}

HONEST_CYCLE = {MCQ: ["honest_quiet", "honest_dim", "honest_shared", "honest_phone_low", "honest_slow", "honest_interrupted"],
                CODING: ["code_honest"]}
CHEAT_CYCLE = {MCQ: ["cheat_phone", "cheat_search", "cheat_pair", "cheat_helper"],
               CODING: ["code_web", "code_pair", "code_retype"]}
PREFIX = {MCQ: "P", CODING: "PC"}


def assign(test: str, n: int, seed: int, cheat_share: float = 0.4) -> list[dict]:
    """Balanced roles for n participants (about 40% malpractice, at least 2), shuffled; pairs get each other's roll no."""
    if n < 4:
        raise ValueError("a pilot needs at least 4 participants")
    rng = random.Random(f"{seed}-{test}")
    n_cheat = max(2, round(cheat_share * n))
    slots: list[str] = []
    cycle = list(CHEAT_CYCLE[test])
    i = 0
    while len(slots) < n_cheat:
        r = cycle[i % len(cycle)]
        i += 1
        if ROLES[r].get("pair"):
            if n_cheat - len(slots) >= 2:
                slots += [r, r]
            continue
        slots.append(r)
    honest = HONEST_CYCLE[test]
    slots += [honest[k % len(honest)] for k in range(n - len(slots))]
    rolls = [f"{PREFIX[test]}{k + 1:02d}" for k in range(n)]
    rng.shuffle(rolls)
    out, waiting = [], {}
    for roll, role in zip(rolls, slots):
        row = dict(roll_no=roll, test=test, role=role, kind=ROLES[role]["kind"], partner="")
        if ROLES[role].get("pair"):
            if role in waiting:
                mate = waiting.pop(role)
                row["partner"], mate["partner"] = mate["roll_no"], roll
            else:
                waiting[role] = row
        out.append(row)
    return sorted(out, key=lambda r: r["roll_no"])


def describe(role: str) -> str:
    r = ROLES[role]
    return r.get("env") or r.get("malpractice") or role
