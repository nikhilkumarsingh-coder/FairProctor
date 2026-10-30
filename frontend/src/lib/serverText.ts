// Hindi for the English sentences the scoring engine writes for candidates. Unknown text stays in English.
const TITLES: Record<string, string> = {
  "How quickly some answers were given": "कुछ उत्तर बहुत जल्दी दिए गए",
  "Long pauses with no activity before correct answers": "सही उत्तर से पहले लंबा ठहराव, स्क्रीन पर कोई गतिविधि नहीं",
  "Leaving the test screen": "परीक्षा की स्क्रीन से बाहर जाना",
  "Pasted text": "टेक्स्ट पेस्ट किया गया",
  "Answers similar to another candidate's": "किसी दूसरे उम्मीदवार से मिलते-जुलते उत्तर",
  "Another person visible": "कैमरे में कोई दूसरा व्यक्ति",
  "A phone visible to the camera": "कैमरे में फ़ोन दिखाई दिया",
  "Your code is very similar to another candidate's": "आपका कोड किसी दूसरे उम्मीदवार के कोड से बहुत मिलता है",
  "Large parts of the code were pasted": "कोड का बड़ा हिस्सा पेस्ट किया गया",
  "Unusual typing": "असामान्य टाइपिंग",
  "Some problems were solved very quickly": "कुछ प्रश्न बहुत जल्दी हल हुए",
};
const TEXTS: Record<string, string> = {
  "How quickly some answers were given": "कुछ उत्तर सामान्य से बहुत जल्दी दिए गए।",
  "Long pauses with no activity before correct answers": "कुछ कठिन प्रश्नों पर स्क्रीन पर लंबे समय तक कोई गतिविधि नहीं थी, फिर सही उत्तर दिया गया।",
  "Leaving the test screen": "आप परीक्षा की स्क्रीन से बाहर गए और लौटने के तुरंत बाद सही उत्तर दिया।",
  "Pasted text": "उत्तर में टेक्स्ट टाइप करने की जगह पेस्ट किया गया।",
  "Answers similar to another candidate's": "आपके कई उत्तर (गलत उत्तर भी) उसी समय परीक्षा दे रहे किसी दूसरे उम्मीदवार से मेल खाते हैं।",
  "Another person visible": "कुछ समय तक कैमरे में आपके पास कोई दूसरा व्यक्ति दिखाई दिया।",
  "A phone visible to the camera": "कुछ प्रश्नों का सही उत्तर देते समय कैमरे में एक फ़ोन दिखाई दिया (फ़ोटो नहीं भेजी गई, सिर्फ़ गिनती)।",
  "Your code is very similar to another candidate's": "आपका प्रोग्राम उसी परीक्षा के किसी दूसरे उम्मीदवार के प्रोग्राम से बहुत मिलता है (नाम और स्पेस बदलने के बाद भी)।",
  "Large parts of the code were pasted": "आपके कोड का बड़ा हिस्सा टाइप करने की जगह पेस्ट किया गया।",
  "Unusual typing": "आपका कोड सामान्य तरीके से टाइप नहीं हुआ — जैसे बहुत बड़ा हिस्सा एक साथ आया, या लंबे ठहराव के बाद बिना सुधार के तेज़ी से टाइप हुआ।",
  "Some problems were solved very quickly": "कुछ प्रश्न ज़्यादातर उम्मीदवारों से बहुत जल्दी, पहली ही कोशिश में हल हुए।",
};
const NOTES: [RegExp, (m: RegExpMatchArray) => string][] = [
  [/^Camera checks run on the (phone|device)/, () => "डेटा और बैटरी बचाने के लिए कैमरा जाँच डिवाइस पर लगभग हर 5 सेकंड में होती है; वीडियो वाली जाँचों को उसी हिसाब से कम महत्व दिया गया।"],
  [/^Low-bandwidth video: about one analysed frame every (\d+) s/, (m) => `धीमा इंटरनेट: लगभग हर ${m[1]} सेकंड में एक फ़्रेम जाँचा गया। वीडियो वाली जाँचों को उसी हिसाब से कम महत्व दिया गया।`],
  [/^Finished the answered questions in about (\d+) min against a typical (\d+) min/, (m) => `आपने उत्तर लगभग ${m[1]} मिनट में दे दिए, जबकि आम तौर पर ${m[2]} मिनट लगते हैं, और उत्तर अनुमान जैसे थे। उत्तरों के समय को नहीं गिना गया।`],
  [/^No usable video/, () => "उपयोगी वीडियो नहीं था। स्कोर सिर्फ़ उत्तर, समय और ब्राउज़र के संकेतों पर आधारित है।"],
  [/^Face not clearly visible in (\d+)% of frames/, (m) => `${m[1]}% फ़्रेम में चेहरा साफ़ नहीं दिखा। इसे सबूत नहीं माना गया।`],
  [/^(\d+) brief appearances? of another person/, (m) => `${m[1]} बार कोई दूसरा व्यक्ति थोड़ी देर के लिए दिखा (जैसे पीछे से गुज़रना) — इसे नहीं गिना गया।`],
  [/^Left the test window (\d+) times?/, (m) => `आप ${m[1]} बार परीक्षा की स्क्रीन से बाहर गए, पर उसके तुरंत बाद कोई सही उत्तर नहीं था। इसे नहीं गिना गया।`],
  [/^Several quick wrong answers/, () => "कई जल्दी दिए गए गलत उत्तर, जो समय के दबाव में अंदाज़ा लगाने जैसे हैं। इन्हें नहीं गिना गया।"],
  [/^Speech-like sound was picked up (\d+) times? \(about (\d+) s of voice\)/, (m) => `फ़ोन ने ${m[1]} बार बातचीत जैसी आवाज़ सुनी (लगभग ${m[2]} सेकंड)। इसे नहीं गिना गया: टीवी, घर के लोगों की बातें या जानवरों की आवाज़ फ़ोन को एक जैसी लगती है।`],
  [/^The microphone check stopped during the test/, () => "परीक्षा के दौरान माइक्रोफ़ोन की जाँच बंद हो गई। इसे नहीं गिना गया।"],
  [/^Small pastes \(moving your own lines/, () => "छोटे पेस्ट (एडिटर में अपनी ही लाइनें इधर-उधर करना) नहीं गिने गए।"],
  [/^Some similarity with other programs is normal/, () => "छोटे प्रश्नों में दूसरों के प्रोग्राम से थोड़ी समानता सामान्य है; आम हिस्से और शुरुआती कोड हटाए गए और बची समानता समीक्षा सीमा से कम थी।"],
  [/^Fast solving on its own is not counted/, () => "सिर्फ़ जल्दी हल करना नहीं गिना जाता: जो सैंपल चलाकर गलतियाँ सुधारते हैं, वे सामान्य हैं।"],
  [/^Leaving the tab briefly with no paste/, () => "थोड़ी देर टैब बदलना (बाद में पेस्ट नहीं) और सिर्फ़ टाइपिंग की गति नहीं गिनी जाती।"],
  [/^A phone was in view for about (\d+) s, but not while correct answers/, (m) => `लगभग ${m[1]} सेकंड कैमरे में फ़ोन दिखा, पर उस समय कोई सही उत्तर नहीं दिया गया। इसे नहीं गिना गया।`],
  [/^Phone held at an angle/, () => "फ़ोन तिरछा पकड़ा गया: स्क्रीन की ओर नीचे देखना सामान्य है और इसकी तुलना आपके अपने व्यवहार से की गई, डेस्कटॉप वालों से नहीं।"],
];

export const pointTitle = (title: string, lang: string) => (lang === "hi" && TITLES[title]) || title;
const AUDIO_POINT_HI = "इनमें से कुछ ठहरावों के दौरान आपके फ़ोन ने बातचीत जैसी आवाज़ सुनी। कोई आवाज़ रिकॉर्ड नहीं की गई।";
export const pointText = (title: string, text: string, lang: string) =>
  lang !== "hi" ? text : text.startsWith("Talking-like sound was picked up") ? AUDIO_POINT_HI : TEXTS[title] || text;
export function noteText(note: string, lang: string) {
  if (lang !== "hi") return note;
  for (const [re, f] of NOTES) { const m = note.match(re); if (m) return f(m); }
  return note;
}
