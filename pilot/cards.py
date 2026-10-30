"""Printable pilot material: one card per participant (login on top, secret role below the fold) and the
participant information + consent page. Plain HTML with print styles; English with Hindi under every line."""
from __future__ import annotations

import html

from .roles import CODING, ROLES

E = html.escape

CSS = """
:root { color-scheme: light; --ink: #0f172a; --ink2: #475569; --muted: #64748b; --line: #e2e8f0; --brand: #db2777; --soft: #fdf2f8; }
* { box-sizing: border-box; }
body { margin: 0; background: #f1f5f9; color: var(--ink);
       font-family: system-ui, -apple-system, "Segoe UI", "Nirmala UI", "Noto Sans Devanagari", sans-serif; }
main { max-width: 820px; margin: 0 auto; padding: 24px 16px; }
.note { font-size: 14px; color: var(--ink2); margin: 0 0 16px; }
.card { background: #fff; border: 1px solid var(--line); border-radius: 14px; overflow: hidden; margin: 0 0 18px;
        break-inside: avoid; page-break-inside: avoid; }
.bar { height: 6px; background: linear-gradient(90deg, #ea580c, #db2777); }
.top { padding: 16px 20px 14px; }
.eyebrow { font-size: 12px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; color: var(--brand); margin: 0; }
h2 { margin: 2px 0 10px; font-size: 20px; }
.login { display: flex; gap: 22px; flex-wrap: wrap; margin: 0 0 10px; }
.login div span { display: block; font-size: 12px; color: var(--muted); }
.login div b { font: 700 24px/1.2 ui-monospace, "Cascadia Mono", Consolas, monospace; letter-spacing: .08em; }
.link { font-size: 14px; word-break: break-all; margin: 0 0 8px; }
.blank { display: inline-block; min-width: 260px; border-bottom: 1px solid var(--ink2); }
ol { margin: 6px 0 0; padding-left: 20px; font-size: 13px; color: var(--ink2); }
ol li { margin: 2px 0; }
.fold { position: relative; border-top: 2px dashed #94a3b8; margin: 0 20px; }
.fold span { position: absolute; top: -11px; left: 50%; transform: translateX(-50%); background: #fff; padding: 0 10px;
             font-size: 12px; color: var(--muted); white-space: nowrap; }
.secret { padding: 18px 20px 18px; background: var(--soft); }
.secret .eyebrow { color: #9d174d; }
.secret h3 { margin: 2px 0 8px; font-size: 18px; }
.secret h3 small { display: block; font-size: 15px; font-weight: 600; color: var(--ink2); }
.secret ul { margin: 0; padding-left: 20px; }
.secret li { margin: 0 0 8px; font-size: 14px; }
.secret li i { display: block; font-style: normal; color: var(--ink2); }
.foot { margin: 10px 0 0; font-size: 12px; color: var(--muted); }
.consent { background: #fff; border: 1px solid var(--line); border-radius: 14px; padding: 22px 24px; margin: 0 0 18px;
           break-inside: avoid; page-break-inside: avoid; font-size: 14px; }
.consent h1 { font-size: 20px; margin: 0 0 4px; }
.consent h2 { font-size: 15px; margin: 16px 0 4px; }
.consent p, .consent li { margin: 4px 0; }
.consent .hi { color: var(--ink2); }
.sign { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; margin-top: 22px; }
.sign div { border-top: 1px solid var(--ink2); padding-top: 4px; font-size: 12px; color: var(--muted); }
@media print {
  body { background: #fff; }
  main { max-width: none; padding: 0; }
  .note { display: none; }
  .card, .consent { border-color: #cbd5e1; margin: 0 0 8mm; }
  .page-break { break-after: page; page-break-after: always; }
  @page { size: A4; margin: 12mm; }
}
"""

STEPS = [("Open the link on your phone or laptop.", "लिंक को फ़ोन या लैपटॉप पर खोलें।"),
         ("Log in with the roll no. and login code on this card.", "इस कार्ड पर लिखे roll no. और login code से लॉग इन करें।"),
         ("Allow the camera, then the microphone, when asked; then follow the screens.",
          "पूछे जाने पर कैमरा, फिर माइक्रोफ़ोन की अनुमति दें; फिर स्क्रीन पर दिए कदम पूरे करें।")]


def card(p: dict, code: str, url: str | None, test_title: str) -> str:
    role = ROLES[p["role"]]
    partner = p.get("partner") or "—"
    link = (f'<p class="link"><b>Link:</b> <a href="{E(url)}">{E(url)}</a></p>' if url else
            '<p class="link"><b>Link:</b> <span class="blank">&nbsp;</span><br><small>The organiser will share it.</small></p>')
    steps = "".join(f"<li>{E(en)} <span style='color:#64748b'>· {E(hi)}</span></li>" for en, hi in STEPS)
    todo = "".join(f"<li>{E(en.format(partner=partner))}<i>{E(hi.format(partner=partner))}</i></li>" for en, hi in role["do"])
    return f"""
<section class="card" id="{E(p['roll_no'])}">
  <div class="bar"></div>
  <div class="top">
    <div>
      <p class="eyebrow">FairProctor pilot · {E(test_title)}</p>
      <h2>Participant {E(p['roll_no'])}</h2>
      <div class="login"><div><span>Roll no.</span><b>{E(p['roll_no'])}</b></div><div><span>Login code</span><b>{E(code)}</b></div></div>
      {link}
      <ol>{steps}</ol>
    </div>
  </div>
  <div class="fold"><span>✂ fold here · secret role below · यहां मोड़ें · नीचे आपकी गुप्त भूमिका</span></div>
  <div class="secret">
    <p class="eyebrow">Your secret role — don't show anyone · आपकी गुप्त भूमिका — किसी को न दिखाएं</p>
    <h3>{E(role['title'][0])}<small>{E(role['title'][1])}</small></h3>
    <ul>{todo}</ul>
    <p class="foot">This is a role-play to test the system, not a real exam. Follow your role, then hand the card back.
      · यह सिस्टम जांचने के लिए एक अभिनय है, असली परीक्षा नहीं। अपनी भूमिका निभाएं, फिर कार्ड लौटा दें।</p>
  </div>
</section>"""


def page(title: str, body: str, url: str | None = None, note: str = "") -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{E(title)}</title><style>{CSS}</style></head>
<body><main>{f'<p class="note">{E(note)}</p>' if note else ""}{body}</main></body></html>
"""


def consent(org: str = "the FairProctor team") -> str:
    def both(en: str, hi: str) -> str:
        return f"<p>{E(en)}</p><p class='hi'>{E(hi)}</p>"
    items = [
        ("What happens", "क्या होगा",
         "You take a short online test (about 45 minutes for questions, 60 for coding) while following a role on a card. "
         "Some roles ask you to act out cheating. This is a role-play to check whether FairProctor treats honest people "
         "fairly and finds real malpractice.",
         "आप एक छोटा ऑनलाइन टेस्ट देंगे (प्रश्नों वाला लगभग 45 मिनट, कोडिंग 60 मिनट) और एक कार्ड पर लिखी भूमिका निभाएंगे। "
         "कुछ भूमिकाओं में नकल का अभिनय करना है। यह जांचने के लिए है कि FairProctor ईमानदार लोगों के साथ न्याय करता है और असली नकल पकड़ता है।"),
        ("What is recorded", "क्या रिकॉर्ड होता है",
         "Your answers and their timing, leaving the test screen, pauses, the length of pasted text (never the text), and "
         "numbers from the camera computed on your device (number of faces, head direction, light). A few small photos, "
         "only at flagged moments (another person, no face, a phone, coming back from another tab); you are told each time, "
         "and only the reviewer and you see them. If you allow the microphone: only whether there was talking-like sound and "
         "for how many seconds. No video and no sound is recorded. For the coding test: your code, runs and typing counts.",
         "आपके उत्तर और उनका समय, टेस्ट स्क्रीन छोड़ना, रुकना, पेस्ट की लंबाई (टेक्स्ट नहीं), और आपके डिवाइस पर कैमरे से निकले अंक "
         "(चेहरों की गिनती, सिर की दिशा, रोशनी)। सिर्फ़ फ़्लैग हुए पलों पर (कोई दूसरा व्यक्ति, चेहरा न दिखना, फ़ोन, दूसरे टैब से लौटना) "
         "कुछ छोटी फ़ोटो; हर बार आपको बताया जाता है, और इन्हें सिर्फ़ रिव्यूअर और आप देखते हैं। अगर आप माइक्रोफ़ोन की अनुमति दें: "
         "सिर्फ़ यह कि बातचीत जैसी आवाज़ थी या नहीं, और कितने सेकंड। कोई वीडियो या आवाज़ रिकॉर्ड नहीं होती। "
         "कोडिंग टेस्ट में: आपका कोड, रन और टाइपिंग की गिनती।"),
        ("How it is used", "इसका इस्तेमाल",
         "Only to measure how well the system works. Results are reported without names, by participant number. "
         "Your role is kept in a sealed list that reviewers do not see until scoring is done.",
         "सिर्फ़ यह मापने के लिए कि सिस्टम कितना सही काम करता है। नतीजे बिना नाम, सिर्फ़ प्रतिभागी नंबर से बताए जाएंगे। "
         "आपकी भूमिका एक बंद सूची में रहती है जिसे स्कोरिंग पूरी होने तक रिव्यूअर नहीं देखते।"),
        ("Your choice", "आपकी मर्ज़ी",
         "Taking part is voluntary. You can stop at any time without giving a reason. Nothing here affects any real exam, "
         "grade or job.",
         "भाग लेना आपकी मर्ज़ी है। आप कभी भी बिना कारण बताए रुक सकते हैं। इसका किसी असली परीक्षा, नंबर या नौकरी पर कोई असर नहीं है।"),
        ("Deletion", "डेटा हटाना",
         "All pilot data is deleted within 7 days after the results are written, or earlier if you ask.",
         "नतीजे लिखे जाने के 7 दिनों के भीतर पायलट का सारा डेटा हटा दिया जाएगा, या आपके कहने पर पहले।"),
    ]
    body = "".join(f"<h2>{E(en)} · {E(hi)}</h2>{both(a, b)}" for en, hi, a, b in items)
    return f"""
<section class="consent">
  <h1>Pilot of FairProctor — information and consent</h1>
  <p class="hi">FairProctor पायलट — जानकारी और सहमति</p>
  {body}
  <h2>Consent · सहमति</h2>
  {both("I have read this, my questions were answered, and I agree to take part.",
        "मैंने यह पढ़ लिया है, मेरे सवालों के जवाब मिल गए, और मैं भाग लेने के लिए सहमत हूं।")}
  <div class="sign"><div>Participant no. / प्रतिभागी नंबर</div><div>Signature / हस्ताक्षर</div>
    <div>Date / तारीख़</div><div>Organiser ({E(org)}) / आयोजक</div></div>
</section>"""


def is_coding(p: dict) -> bool:
    return ROLES[p["role"]]["test"] == CODING
