// Turning dictated speech into form values. Pure functions, no DOM.

const SMALL: Record<string, number> = {
  zero: 0, oh: 0, one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8,
  nine: 9, ten: 10, eleven: 11, twelve: 12, thirteen: 13, fourteen: 14, fifteen: 15,
  sixteen: 16, seventeen: 17, eighteen: 18, nineteen: 19, twenty: 20, thirty: 30, forty: 40,
  fifty: 50, sixty: 60, seventy: 70, eighty: 80, ninety: 90,
  // Hindi (hi-IN recognition usually gives digits, but not always)
  शून्य: 0, एक: 1, दो: 2, तीन: 3, चार: 4, पांच: 5, पाँच: 5, छह: 6, छः: 6, सात: 7, आठ: 8,
  नौ: 9, दस: 10, ग्यारह: 11, बारह: 12, पंद्रह: 15, बीस: 20, पच्चीस: 25, तीस: 30,
  चालीस: 40, पचास: 50, साठ: 60, सत्तर: 70, अस्सी: 80, नब्बे: 90, पचानवे: 95,
};
// Fractions said as one word: डेढ़ = 1.5, ढाई = 2.5 ("डेढ़ करोड़").
const FRACTIONS: Record<string, number> = { डेढ़: 1.5, डेढ: 1.5, ढाई: 2.5 };
// Modifiers on the next number: साढ़े तीन = 3.5, सवा दो = 2.25.
const PLUS: Record<string, number> = { साढ़े: 0.5, साढे: 0.5, सवा: 0.25 };
const SCALES: Record<string, number> = {
  hundred: 100, thousand: 1_000, k: 1_000, lakh: 100_000, lakhs: 100_000, lac: 100_000,
  lacs: 100_000, l: 100_000, million: 1_000_000, crore: 10_000_000, crores: 10_000_000,
  cr: 10_000_000, सौ: 100, हज़ार: 1_000, हजार: 1_000, लाख: 100_000, करोड़: 10_000_000,
  करोड: 10_000_000,
};
// Units people say after a number that don't change it.
const NOISE = new Set([
  "rupees", "rs", "inr", "₹", "sq", "square", "feet", "ft", "sqft", "and", "bhk", "only",
  "रुपये", "रुपए", "रूपये", "स्क्वायर", "वर्ग", "फीट", "फुट", "और", "बीएचके", "का", "की",
]);

/** Devanagari digits → ASCII, so "९५" reads as 95. */
export function asciiDigits(s: string): string {
  return s.replace(/[०-९]/g, (d) => String(d.charCodeAt(0) - 0x0966));
}

/** "95 lakh" → 9500000, "1.2 crore" → 12000000, "twelve hundred" → 1200, "3" → 3. */
export function parseSpokenNumber(raw: string): number | null {
  const words = asciiDigits(raw)
    .toLowerCase()
    .replace(/(\d),(?=\d)/g, "$1") // 1,650 and 95,00,000
    .replace(/(\d)(\p{L})/gu, "$1 $2") // 95lakh, 2cr, 95लाख
    .replace(/[^\p{L}\p{M}\p{N}.₹ ]/gu, " ")
    .split(/\s+/)
    .filter((w) => w && !NOISE.has(w));
  let total = 0;
  let current = 0;
  let seen = false;
  let decimal: string | null = null;
  let plus = 0;
  for (const w of words) {
    if (w in PLUS) { plus = PLUS[w]; continue; }
    if (w in FRACTIONS) { current += FRACTIONS[w]; seen = true; continue; }
    if (w === "point" && seen) { decimal = ""; continue; }
    if (decimal !== null && w in SMALL && SMALL[w] < 10) { decimal += String(SMALL[w]); continue; }
    if (decimal !== null) { current += Number(`0.${decimal || 0}`); decimal = null; }
    if (/^\d+(\.\d+)?$/.test(w)) { current += Number(w) + plus; plus = 0; seen = true; continue; }
    if (w in SMALL) { current += SMALL[w] + plus; plus = 0; seen = true; continue; }
    if (w in SCALES) {
      const scale = SCALES[w];
      if (!seen) current = 1; // "lakh" alone = 1 lakh
      if (scale === 100) current *= 100;
      else { total += current * scale; current = 0; }
      seen = true;
      continue;
    }
    return null; // a word we don't understand: not a number
  }
  if (decimal !== null) current += Number(`0.${decimal || 0}`);
  return seen ? Math.round((total + current) * 100) / 100 : null;
}

const DIGIT_WORDS: Record<string, string> = {
  zero: "0", oh: "0", o: "0", one: "1", two: "2", three: "3", four: "4", five: "5", six: "6",
  seven: "7", eight: "8", nine: "9",
  शून्य: "0", ज़ीरो: "0", जीरो: "0", एक: "1", दो: "2", तीन: "3", चार: "4", पांच: "5", पाँच: "5",
  छह: "6", छः: "6", सात: "7", आठ: "8", नौ: "9",
};

/** "plus nine one double nine eight four…" → "+91998 4…" digits only (with a leading +). */
export function spokenPhone(raw: string): string {
  const words = asciiDigits(raw).toLowerCase().replace(/\+/g, " plus ").split(/[\s-]+/).filter(Boolean);
  let out = "";
  for (let i = 0; i < words.length; i++) {
    const w = words[i];
    const repeat = w === "double" || w === "डबल" ? 2 : w === "triple" || w === "ट्रिपल" ? 3 : 0;
    if (repeat && i + 1 < words.length) {
      const next = DIGIT_WORDS[words[i + 1]] ?? (/^\d$/.test(words[i + 1]) ? words[i + 1] : "");
      if (next) { out += next.repeat(repeat); i++; continue; }
    }
    if ((w === "plus" || w === "प्लस") && !out) out = "+";
    else if (w in DIGIT_WORDS) out += DIGIT_WORDS[w];
    else out += w.replace(/\D/g, "");
  }
  return out;
}

/** "Asha dot rao at gmail dot com" → "asha.rao@gmail.com". */
export function spokenEmail(raw: string): string {
  return raw
    .toLowerCase()
    .replace(/\s+at the rate( of)?\s+|\s+at\s+/g, "@")
    .replace(/\s*\bdot\b\s*/g, ".")
    .replace(/\s*\b(underscore)\b\s*/g, "_")
    .replace(/\s*\b(dash|hyphen)\b\s*/g, "-")
    .replace(/\s+/g, "");
}

const norm = (s: string) =>
  s.toLowerCase().replace(/[^\p{L}\p{M}\p{N} ]/gu, " ").replace(/\s+/g, " ").trim();

// Hindi words for the choices in our dropdowns, mapped to the English option text.
const HINDI_OPTIONS: [RegExp, string][] = [
  [/बिक्री|बेचना|बेचने|सेल/, "sale"], [/किराय|किराए|रेंट/, "rent"],
  [/फ्लैट|फ़्लैट|अपार्टमेंट/, "apartment"], [/विला/, "villa"],
  [/मकान|घर|इंडिपेंडेंट/, "independent house"], [/प्लॉट|प्लाट|ज़मीन|जमीन/, "plot"],
  [/कमर्शियल|दुकान/, "commercial"], [/ऑफिस|दफ़्तर|दफ्तर/, "office"],
  [/उपलब्ध|खाली/, "available"], [/बिक गया|बिका/, "sold"], [/ड्राफ्ट/, "draft"],
  [/कोई भी/, "anyone"], [/रेफरल|रेफर/, "referral"], [/वेबसाइट/, "website"],
  [/व्हाट्सएप|वॉट्सऐप/, "whatsapp"], [/वॉक इन|ऑफिस आए/, "walk in"], [/अन्य/, "other"],
  [/साइट विज़िट|साइट विजिट|देखने/, "site visit"], [/मीटिंग/, "meeting"], [/कॉल/, "call"],
];

/** Best option for what was said ("for sale" → Sale, "independent house" → Independent house). */
export function matchOption(raw: string, options: { value: string; label: string }[]): string | null {
  const hindi = HINDI_OPTIONS.filter(([re]) => re.test(raw)).map(([, en]) => en);
  const said = norm([raw, ...hindi].join(" "));
  if (!said) return null;
  let best: { value: string; score: number } | null = null;
  for (const o of options) {
    const label = norm(o.label);
    const value = norm(o.value.replace(/_/g, " "));
    let score = 0;
    if (said === label || said === value) score = 3;
    else if (label && (` ${said} `.includes(` ${label} `) || ` ${label} `.includes(` ${said} `))) score = 2;
    else {
      const words = new Set(label.split(" "));
      const overlap = said.split(" ").filter((w) => w.length > 2 && words.has(w)).length;
      if (overlap) score = overlap / Math.max(words.size, 1);
    }
    if (score > 0 && (!best || score > best.score)) best = { value: o.value, score };
  }
  return best?.value ?? null;
}

export function spokenBoolean(raw: string): boolean | null {
  const s = norm(raw);
  if (/^(yes|yeah|yep|on|true|tick|check(ed)?|enable(d)?|haan|ha)\b|^(हाँ|हां|जी हाँ|जी हां|हा)( |$)/u.test(s)) return true;
  if (/^(no|nope|off|false|untick|uncheck(ed)?|disable(d)?|nahi|nahin)\b|^(नहीं|नही|ना)( |$)/u.test(s)) return false;
  return null;
}

export type VoiceCommand = "next" | "previous" | "clear" | "stop" | "submit";

/** Whole-utterance commands only, so a title like "Next to the park" still gets typed. */
export function voiceCommand(raw: string): VoiceCommand | null {
  const s = norm(raw);
  if (/^(next|next field|skip|skip it|skip this|अगला|आगे|आगे बढ़ो|छोड़ो|नेक्स्ट)$/u.test(s)) return "next";
  if (/^(back|go back|previous|previous field|पीछे|वापस|पिछला|बैक)$/u.test(s)) return "previous";
  if (/^(clear|clear it|clear field|clear this|delete that|erase|साफ़ करो|साफ करो|मिटाओ|हटाओ|क्लियर)$/u.test(s)) return "clear";
  if (/^(stop|stop listening|done|finish|cancel voice|रुको|बंद करो|बस|स्टॉप)$/u.test(s)) return "stop";
  if (/^(submit|submit form|save form|save the form|जमा करो|सबमिट करो|सेव करो|सबमिट)$/u.test(s)) return "submit";
  return null;
}

/** Dictated sentence for a text box: tidy spacing and capitalise the first letter. */
export function spokenText(raw: string): string {
  const t = raw.replace(/\s+/g, " ").trim();
  return t.charAt(0).toUpperCase() + t.slice(1);
}

// Cities are matched in English across the marketplace, so Hindi city names are converted.
const CITIES: Record<string, string> = {
  मुंबई: "Mumbai", मुम्बई: "Mumbai", दिल्ली: "Delhi", "नई दिल्ली": "New Delhi", बेंगलुरु: "Bengaluru",
  बेंगलूरु: "Bengaluru", बैंगलोर: "Bengaluru", हैदराबाद: "Hyderabad", चेन्नई: "Chennai",
  कोलकाता: "Kolkata", पुणे: "Pune", अहमदाबाद: "Ahmedabad", जयपुर: "Jaipur", लखनऊ: "Lucknow",
  गुरुग्राम: "Gurugram", गुड़गांव: "Gurugram", नोएडा: "Noida", "ग्रेटर नोएडा": "Greater Noida",
  गाजियाबाद: "Ghaziabad", ग़ाज़ियाबाद: "Ghaziabad", फरीदाबाद: "Faridabad", चंडीगढ़: "Chandigarh",
  इंदौर: "Indore", भोपाल: "Bhopal", नागपुर: "Nagpur", सूरत: "Surat", वडोदरा: "Vadodara",
  नासिक: "Nashik", ठाणे: "Thane", "नवी मुंबई": "Navi Mumbai", कोच्चि: "Kochi", गोवा: "Goa",
  पटना: "Patna", भुवनेश्वर: "Bhubaneswar", देहरादून: "Dehradun", कोयंबटूर: "Coimbatore",
  मैसूर: "Mysuru", विशाखापत्तनम: "Visakhapatnam", कानपुर: "Kanpur", वाराणसी: "Varanasi",
};

/** "पुणे" → "Pune"; anything else unchanged. */
export function englishCity(raw: string): string {
  const t = raw.replace(/[।.,]/g, "").trim();
  return CITIES[t] ?? raw;
}
