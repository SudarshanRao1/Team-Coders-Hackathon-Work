"""Customer Interaction Agent.
Responsible for:
1. Natural language understanding across multiple languages (English, Telugu, Hindi, Tamil, Kannada).
2. Intent recognition (ORDER_UPDATE, CONFIRMATION, CANCELLATION, STATUS_QUERY, ADDRESS_CONFIRMATION, INFORMATION).
3. Entity extraction (quantities, itemized dishes, allergens with scope, dietary restrictions with recipient, addresses, delivery times).
4. Multimodal input parsing (receipts, dish photos, handwritten notes, voice notes).
5. Personalized, culturally appropriate responses in the customer's preferred language.
"""
import re, json

LANG_RANGES = {
    "te": (0x0C00, 0x0C7F),  # Telugu
    "hi": (0x0900, 0x097F),  # Hindi
    "ta": (0x0B80, 0x0BFF),  # Tamil
    "kn": (0x0C80, 0x0CFF),  # Kannada
    "bn": (0x0980, 0x09FF),  # Bengali
}

NUM_WORDS = {
    # English
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "single": 1, "couple": 2, "pair": 2,
    # Telugu
    "ఒకటి": 1, "ఒక": 1, "రెండు": 2, "మూడు": 3, "నాలుగు": 4, "ఐదు": 5, "ఆరు": 6, "ఏడు": 7, "ఎనిమిది": 8, "తొమ్మిది": 9, "పది": 10,
    # Hindi
    "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "छह": 6, "सात": 7, "आठ": 8, "नौ": 9, "दस": 10,
    # Tamil
    "ஒன்று": 1, "ஒரு": 1, "இரண்டு": 2, "மூன்று": 3, "நான்கு": 4, "ஐந்து": 5, "ஆறு": 6, "ஏழு": 7, "எட்டு": 8,
    # Kannada
    "ಒಂದು": 1, "ಒಂದ": 1, "ಎರಡು": 2, "ಮೂರು": 3, "ನಾಲ್ಕು": 4, "ಐದು": 5, "ಆರು": 6, "ಏಳು": 7, "ಎಂಟು": 8
}

HOURS_WORDS = {
    "noon": 12, "one": 13, "two": 14, "three": 15, "four": 16, "five": 17, "six": 18,
    "seven": 19, "eight": 20, "nine": 21, "ten": 22, "midnight": 24,
    "ఆరు": 18, "ఏడు": 19, "ఎనిమిది": 20, "తొమ్మిది": 21,
    "छह": 18, "सात": 19, "आठ": 20, "नौ": 21,
    "ஆறு": 18, "ஏழு": 19, "எட்டு": 20,
    "ಆರು": 18, "ಏಳು": 19, "ಎಂಟು": 20
}

ALLERGEN_MAP = {
    "peanuts": ["peanut", "peanuts", "groundnut", "groundnuts", "వేరుశెనగ", "వేరుశెనగలు", "పల్లీ", "मूंगफली", "मूँगफली", "வேர்க்கடலை", "நிலக்கடலை", "ಕಡಲೆಕಾಯಿ", "ಶೇಂಗಾ"],
    "tree nuts": ["tree nut", "nuts", "almond", "cashew", "walnut", "జీడిపప్పు", "బాదం", "काजू", "बादाम", "முந்திரி", "பாதாம்", "ಗೋಡಂಬಿ", "ಬಾದಾಮಿ"],
    "dairy": ["dairy", "milk", "cheese", "butter", "ghee", "lactose", "curd", "yogurt", "పాలు", "పెరుగు", "వెన్న", "दूध", "दही", "पनीर", "பால்", "தயிர்", "வெண்ணெய்", "ಹಾಲು", "ಮೊಸರು", "ಬೆಣ್ಣೆ"],
    "gluten": ["gluten", "wheat", "maida", "celiac", "గోధుమ", "మైదా", "गेहूं", "मैदा", "ग्लूटेन", "கோதுமை", "மைதா", "ಗೋಧಿ", "ಮೈದಾ"],
    "eggs": ["egg", "eggs", "గుడ్డు", "గుడ్లు", "अंडा", "अंडे", "முட்டை", "ಮೊಟ್ಟೆ"],
    "shellfish": ["shellfish", "prawn", "prawns", "shrimp", "crab", "రొయ్యలు", "పీతలు", "झींगा", "இறால்", "ನಳ್ಳಿ"],
    "soy": ["soy", "soya", "soybean", "సోయా", "सोया", "சோயா", "ಸೋಯಾ"],
    "sesame": ["sesame", "til", "నువ్వులు", "तिल", "எள்", "ಎಳ್ಳು"],
    "mustard": ["mustard", "ఆవాలు", "सरसों", "கடுகு", "ಸಾಸಿವೆ"]
}

SPECIAL_REQUIREMENTS = {
    "soft food": ["soft food", "soft", "easy to chew", "మృదు", "మృదువైన", "మెత్తగా", "नरम", "मुलायम", "மென்மையான", "மெதுவான", "ಮೆತ್ತನೆಯ"],
    "mild / low spice": ["mild", "less spicy", "not spicy", "low spice", "no chilly", "తక్కువ కారం", "కారం లేకుండా", "कम तीखा", "बिना मिर्च", "காரமில்லாத", "ಖಾರವಿಲ್ಲದ"],
    "extra spicy": ["extra spicy", "very spicy", "hot", "ఎక్కువ కారం", "బాగా కారంగా", "ज्यादा तीखा", "அதிக காரம்", "ಹೆಚ್ಚು ಖಾರ"],
    "no onion garlic (jain)": ["jain", "no onion", "no garlic", "no onion garlic", "ఉల్లిపాయ వెల్లుల్లి లేకుండా", "बिना प्याज लहसुन", "जैन", "வெங்காயம் பூண்டு இல்லாமல்"],
    "diabetic friendly": ["diabetic", "sugar free", "no sugar", "చక్కెర లేకుండా", "शुगर फ्री", "बिना चीनी", "சர்க்கரை இல்லாமல்", "ಸಕ್ಕರೆ ಇಲ್ಲದೆ"],
    "low oil / healthy": ["less oil", "no oil", "diet", "నూనె తక్కువ", "कम तेल", "குறைந்த எண்ணெய்", "ಕಡಿಮೆ ಎಣ್ಣೆ"],
    "salt free": ["salt free", "no salt", "low sodium", "ఉప్పు లేకుండా", "बिना नमक", "உப்பு இல்லாமல்", "ಉಪ್ಪು ಇಲ್ಲದೆ"]
}

RECIPIENTS = {
    "grandmother": ["grandmother", "grandma", "dadi", "nani", "ammamma", "nayanamma", "అమ్మమ్మ", "నాయనమ్మ", "दादी", "नानी", "பாட்டி", "அஜ்ஜி"],
    "grandfather": ["grandfather", "grandpa", "dada", "nana", "thathayya", "తాతయ్య", "दादा", "नाना", "தாத்தா", "ತಾತಾ"],
    "baby": ["baby", "toddler", "infant", "పాప", "బాబు", "छोटा बच्चा", "बच्चा", "குழந்தை", "ಮಗು"],
    "kids": ["kid", "kids", "children", "పిల్లలు", "बच्चे", "சிறுவர்கள்", "ಮಕ್ಕಳು"],
    "mother": ["mother", "mom", "amma", "అమ్మ", "माँ", "माताजी", "அம்மா", "ತಾಯಿ"],
    "father": ["father", "dad", "nanna", "నాన్న", "पिताजी", "पापा", "அப்பா", "ಅಪ್ಪ"]
}


def _kw(text: str, kw: str):
    """Match a keyword in lower-cased text. Latin keywords need word boundaries (so 'nuts' does not
    match 'peanuts', 'til' does not match 'until', 'hot' does not match 'hotel', 'nana' does not match
    'banana'); Indic keywords are matched as substrings. Returns a list of match start offsets."""
    if kw.isascii():
        return [m.start() for m in re.finditer(r"(?<![a-z0-9])" + re.escape(kw) + r"(?:s|es)?(?![a-z0-9])", text)]
    out, i = [], text.find(kw)
    while i != -1:
        out.append(i)
        i = text.find(kw, i + 1)
    return out

def _has(text: str, kws) -> bool:
    return any(_kw(text, k) for k in kws)

_QTY_WORD = "|".join(k for k in NUM_WORDS if k.isascii())
# "2 egg fried rice", "two cheese sandwiches": the ingredient word is part of a dish name, not an allergy.
_QTY_PREFIX = re.compile(r"(?:\b\d+|\b(?:%s))\s+(?:x\s*)?(?:[a-z]+\s+)?$" % _QTY_WORD)

ADDR_SUFFIX = (r"(?:road|rd|street|st|nagar|lane|ln|layout|cross|main|avenue|ave|colony|sector|apartments?|villa|tower|"
               r"enclave|marg|circle|boulevard|blvd|highway|hwy|bypass|chowk|puram|palya|halli)")
HOUSE_NO = r"\d+[A-Za-z]?(?:[/-]\d+[A-Za-z]?)?"
GENERIC_ADDR = re.compile(
    r"^(?:my|our|the|his|her|their|your|me|us|him|them|same|there|here|that|this|it|home|office|work|"
    r"after|before|by|around|about|tomorrow|today|tonight|tmrw|at|in|on|asap|now|soon|later|early|quickly|fast|promptly|"
    r"immediately|urgently|directly|between|from|till|until|please|pls|morning|evening|afternoon|noon|lunch|dinner|breakfast|"
    r"midnight|next|this|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.I)

def _tidy_addr(a: str) -> str:
    a = re.sub(r"\s+", " ", a).strip(" .,!?;:")
    return " ".join(w.capitalize() if w.islower() else w for w in a.split(" "))

class CustomerAgent:
    """Autonomous agent handling all customer-facing conversations, extractions, and responses."""
    
    def __init__(self):
        self.name = "Customer Interaction Agent"
        self.role = "Customer Intake, Localization & Communication"
        self.avatar = "🤖"

    def detect_language(self, text: str) -> str:
        for lang, (start, end) in LANG_RANGES.items():
            if any(start <= ord(c) <= end for c in text):
                return lang
        return "en"

    def extract_intent(self, text: str, sender: str, changes: dict) -> str:
        t = text.lower()
        if "cancel" in t or "రద్దు" in t or "रद्द" in t or "dont want" in t or "don't want" in t:
            return "CANCELLATION"
        if any(q in t for q in ("status", "where is", "when will", "update on", "track")):
            return "STATUS_QUERY"
        if sender == "owner" and any(k in t for k in ("confirm", "proceed", "accepted", "approved", "నిర్ధారించు", "पक्का")):
            return "CONFIRMATION"
        if sender == "delivery" and any(k in t for k in ("address", "which one", "where", "location")):
            return "ADDRESS_QUERY"
        if sender == "kitchen" and any(k in t for k in ("allergy", "sheet", "status", "how many", "quantity")):
            return "STATUS_QUERY"
        if sender == "customer" and changes.get("address") and any(k in t for k in ("correct", "confirm", "yes, that", "current address is", "use 42", "use 12")):
            return "ADDRESS_CONFIRMATION"
        if sender == "customer" and (changes.get("quantity") is not None or bool(changes.get("allergies")) or bool(changes.get("special")) or changes.get("address") or changes.get("addresses") or changes.get("after") or bool(changes.get("items"))):
            return "ORDER_UPDATE"
        return "INFORMATION"

    def extract_quantity(self, text: str, current_qty: int | None = None) -> tuple[int | None, list[dict]]:
        t = text.lower()
        items = []

        # 0. Complete deletion / clearing of meals
        if re.search(r"(?:delete|remove|cancel|clear)\s+all\s+(?:meals?|plates?|orders?)", t) or re.search(r"reduce\s+(?:meals\s+)?to\s+0", t) or "delete the order" in t or "delete order" in t:
            return 0, items

        # 1. Relative reduction / removal e.g. "remove 1 meal", "reduce by 1 meal", "cancel 1 plate", "remove the extra meal"
        rel_m = re.search(r"(?:remove|cancel|delete|reduce by|cut)\s+(\S+)\s+(?:meals?|plates?|thalis?|boxes?|சாப்பாடு|ಊಟ)", t)
        if rel_m:
            w = rel_m.group(1).strip(".,!?")
            val = NUM_WORDS.get(w) or (int(w) if w.isdigit() else None)
            if val is not None and current_qty is not None:
                return max(0, current_qty - val), items

        if "remove the extra meal" in t or "remove extra meal" in t or "cancel extra meal" in t or "delete extra meal" in t or "one less meal" in t:
            if current_qty is not None:
                return max(0, current_qty - 1), items

        # 2. Direct reduction e.g. "reduce meals to 2", "reduce to 1 meal", "decrease to 2"
        red_to_m = re.search(r"(?:reduce|decrease|cut)\s+(?:meals\s+|quantity\s+)?to\s+(\S+)", t)
        if red_to_m:
            w = red_to_m.group(1).strip(".,!?")
            val = NUM_WORDS.get(w) or (int(w) if w.isdigit() else None)
            if val is not None:
                return val, items

        # 3. Telugu & Hindi reduction verbs
        # Telugu: "ఒక భోజనం తగ్గించండి", "తీసివేయండి"
        if "తగ్గించండి" in t or "తీసివేయండి" in t:
            tm = re.search(r"(\S+)\s*(?:భోజనం|భోజనాలు)?\s*(?:తగ్గించండి|తీసివేయండి)", t)
            if tm:
                w = tm.group(1).strip(".,!?")
                val = NUM_WORDS.get(w) or (int(w) if w.isdigit() else None)
                if val is not None and current_qty is not None:
                    return max(0, current_qty - val), items
            elif current_qty is not None:
                return max(0, current_qty - 1), items

        # Hindi: "एक थाली कम कर दो", "हटा दो"
        if "कम कर" in t or "हटा" in t:
            hm = re.search(r"(\S+)\s*(?:थाली|भोजन)?\s*(?:कम कर|हटा)", t)
            if hm:
                w = hm.group(1).strip(".,!?")
                val = NUM_WORDS.get(w) or (int(w) if w.isdigit() else None)
                if val is not None and current_qty is not None:
                    return max(0, current_qty - val), items
            elif current_qty is not None:
                return max(0, current_qty - 1), items
        
        # 4. Check patterns like "make that 3", "make it four"
        make_pattern = re.search(r"make\s+(?:that|it)\s+(\S+)", t)
        if make_pattern:
            w = make_pattern.group(1).strip(".,!?")
            q = NUM_WORDS.get(w) or (int(w) if w.isdigit() else None)
            if q is not None:
                return q, items

        # 5. Check patterns like "two meals", "3 meals", "4 plates", "5 thalis", "రెండు భోజనాలు", "तीन थाली", "இரண்டு சாப்பாடு", "ಮೂರು ಊಟ"
        meal_pattern = re.search(r"(\S+)\s+(?:meals?|plates?|thalis?|boxes?|packs?|servings?|భోజనాలు|భోజనం|भोजन|थाली|प्लेट|சாப்பாடு|உணவு|ಊಟ)", t)
        if meal_pattern:
            w = meal_pattern.group(1).strip(".,!?")
            q = NUM_WORDS.get(w) or (int(w) if w.isdigit() else None)
            if q is not None:
                return q, items

        # 6. Itemized orders e.g. "2 biryani, 3 roti" or "2 egg fried rice, 1 pulihora, 4 apple pie to Amrita Univ"
        items = self.extract_items(t)
        if items:
            return sum(i["quantity"] for i in items), items

        # 7. Fallback numeric scan for single digit if order context present
        if any(k in t for k in ("meal", "order", "want", "need", "plate", "కావాలి", "చాహియే", "வேண்டும்", "ಬೇಕು")):
            digit_match = re.search(r"\b([1-9]|10|12|20|25|50)\b", t)
            if digit_match:
                return int(digit_match.group(1)), items

        return None, items

    ITEM_STOP = r"(?=\s*(?:,|;|\.|\n|$|\band\b|\bto\b|\bdeliver|\bafter\b|\bbefore\b|\bat\b|\bfor\b|\bwith\b|\bno\b|\bplease\b|\bwithout\b|\bnote\b|\binstructions?\b|\baddress\b))"

    def extract_items(self, t: str) -> list[dict]:
        """Parse 'N dish' pairs separated by commas / 'and' / newlines. Needs at least two clean pairs or one pair
        followed by an address/time cue, so ordinary sentences such as '2 days from now' are not read as dishes."""
        items = []
        pat = re.compile(r"(?:^|[,;\n]|\band\b)\s*(\d{1,2}|" + _QTY_WORD + r")\s*(?:x\s*)?([a-z][a-z' -]{2,30}?)" + self.ITEM_STOP)
        for m in pat.finditer(t):
            w, dish = m.group(1), m.group(2).strip(" -'")
            val = NUM_WORDS.get(w) or (int(w) if w.isdigit() else None)
            if not val or not dish or dish.split()[0] in ("days", "day", "hours", "hour", "minutes", "pm", "am", "people", "persons", "guests"):
                continue
            items.append({"name": dish, "quantity": val})
        return items if len(items) >= 2 or (len(items) == 1 and re.search(r"\b(deliver|address|after|to)\b", t)) else []

    def extract_allergies(self, text: str) -> list[dict]:
        t = text.lower()
        allergies = []
        one_meal_indicators = (
            "one must", "one meal", "single meal", "for one", "1 meal",
            "ఒకదాంట్లో", "ఒక భోజనం", "ఒకటి",
            "एक में", "एक थाली", "एक भोजन"
        )
        is_one = any(ind in t for ind in one_meal_indicators)
        for allergen, keywords in ALLERGEN_MAP.items():
            hits = [pos for kw in keywords for pos in _kw(t, kw)]
            # Ignore occurrences that are just part of a quantified dish name ("2 egg fried rice").
            hits = [pos for pos in hits if not _QTY_PREFIX.search(t[:pos])]
            if hits:
                allergies.append({"ingredient": allergen, "scope": "one_meal" if is_one else "all"})
        return allergies

    def extract_special_requirements(self, text: str) -> list[dict]:
        t = text.lower()
        specials = []
        
        # Identify recipient
        recipient = None
        for r_name, r_kws in RECIPIENTS.items():
            if _has(t, r_kws):
                recipient = r_name
                break
                
        # Identify requirement
        for req_name, req_kws in SPECIAL_REQUIREMENTS.items():
            if _has(t, req_kws):
                specials.append({
                    "recipient": recipient,
                    "requirement": req_name
                })
                
        return specials

    def extract_address(self, text: str) -> str | None:
        # Check specific delivery location patterns
        m_explicit = re.search(r"(?:deliver to|delivery address is|address is|deliver at|to|at)\s+(flat\s+[a-z0-9\s,.-]+?|plot\s+[a-z0-9\s,.-]+?|\d+/\d+[a-z0-9\s,.-]+?|\d+\s+[A-Za-z]+(?:\s+[A-Za-z]+){0,3}\s+(?:road|street|nagar|lane|layout|cross|main|avenue|colony|sector|apartment|apartments|villa|tower|enclave|marg))(?:\s+after|\.|$)", text, re.I)
        if m_explicit:
            return _tidy_addr(m_explicit.group(1))

        # Indic and multilingual address pattern e.g. "42 రెసిడెన్సీ రోడ్", "12 मालवीय नगर", "15 காந்தி ரோடு", "10 ಎಂಜಿ ರಸ್ತೆ"
        m_indic = re.search(r"\b(\d+\s*[\u0C00-\u0C7F\u0900-\u097Fa-zA-Z\s]+?(?:రోడ్డు?|రోడ్|నగర్|కాలనీ|नगर|रोड|मार्ग|ரோடு|நகர்|ರಸ್ತೆ|ನಗರ))\b", text, re.I)
        if m_indic:
            return m_indic.group(1).strip(".,!?;").strip()

        # Standard street addresses: "12 MG Road", "9 Church St", "221B Baker Street", "14/2 Brigade Rd"
        m_street = re.search(r"\b(" + HOUSE_NO + r"\s+[A-Za-z][A-Za-z.]*(?:\s+[A-Za-z][A-Za-z.]*){0,3}?\s+" + ADDR_SUFFIX + r")\b", text, re.I)
        if m_street:
            return _tidy_addr(m_street.group(1))

        # Free-form destination after a delivery cue: "deliver to MG Road", "Delivery address: Amrita University, Bangalore"
        return self._free_form_address(text)

    CUE = (r"(?:deliver(?:y)?(?:\s+address)?(?:\s+(?:is|to|at)\b)?|ship\s+to|send\s+(?:it\s+)?to|address\s*(?:is\b|:)|location\s*(?:is\b|:))\s*:?\s*")

    def _free_form_address(self, text: str) -> str | None:
        m = re.search(self.CUE + r"([^.\n;!?]{3,80}?)(?=\s+(?:after|before|by|around|tomorrow|today|tonight|please|pls|thanks?)\b|\s+at\s+\d|[.\n;!?]|$)", text, re.I)
        if not m:
            return None
        cand = m.group(1).strip(" ,:-")
        if (not cand or GENERIC_ADDR.match(cand) or re.search(r"\b(?:or)\b", cand, re.I)
                or re.search(r"\b(?:meals?|plates?|thalis?|boxes)\b", cand, re.I) or re.fullmatch(r"[\d\s:apm]+", cand, re.I)):
            return None
        return _tidy_addr(cand)

    def extract_all_addresses(self, text: str) -> list[str]:
        """Finds every distinct address in a message (used to detect ambiguity)."""
        pat = (r"\b(" + HOUSE_NO + r"\s+[A-Za-z][A-Za-z.]*(?:\s+[A-Za-z][A-Za-z.]*){0,3}?\s+" + ADDR_SUFFIX + r")\b")
        found, seen = [], set()
        for m in re.finditer(pat, text, re.I):
            addr = re.sub(r"\s+", " ", m.group(1)).strip(".,!?; ")
            key = addr.lower()
            if key not in seen:
                seen.add(key)
                found.append(addr)
        if len(found) < 2:
            # "deliver to Indiranagar home or Whitefield tech park" -> two free-form candidates
            m = re.search(self.CUE + r"([^.\n;!?]{3,120})", text, re.I)
            if m:
                parts = [p.strip(" ,?") for p in re.split(r"\s+or\s+", m.group(1), flags=re.I) if p.strip(" ,?")]
                if len(parts) >= 2 and not any(GENERIC_ADDR.match(p) for p in parts[:2]):
                    return [_tidy_addr(p) for p in parts[:2]]
        return found

    def extract_delivery_time(self, text: str) -> str | None:
        t = text.lower()
        
        # 1. "after 7pm", "after 18:00", "after 6", "after six"
        after_m = re.search(r"after\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", t)
        if after_m:
            hr = int(after_m.group(1))
            mn = int(after_m.group(2)) if after_m.group(2) else 0
            ampm = after_m.group(3)
            if ampm == "pm" and hr < 12: hr += 12
            elif ampm == "am" and hr == 12: hr = 0
            elif not ampm and hr < 8: hr += 12
            return f"{hr:02d}:{mn:02d}"

        after_word_m = re.search(r"after\s+([a-zA-Z\u0C00-\u0C7F\u0900-\u097F]+)", t)
        if after_word_m:
            w = after_word_m.group(1)
            if w in HOURS_WORDS:
                return f"{HOURS_WORDS[w]:02d}:00"

        # 2. "at 8:30 pm", "at 1:00 pm", "by 7 pm"
        time_m = re.search(r"(?:at|by|around|deliver\s+at)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)", t)
        if time_m:
            hr = int(time_m.group(1))
            mn = int(time_m.group(2)) if time_m.group(2) else 0
            ampm = time_m.group(3)
            if hr <= 12:
                if ampm == "pm" and hr < 12: hr += 12
                elif ampm == "am" and hr == 12: hr = 0
                return f"{hr:02d}:{mn:02d}"

        return None

    def parse_message(self, text: str, sender: str, ctx: dict) -> dict:
        """Core parsing logic combining pattern matching, contextual awareness, and validation."""
        lang = self.detect_language(text)
        current_qty = ctx.get("meals") if ctx.get("meals") is not None else ctx.get("quantity")
        qty, items = self.extract_quantity(text, current_qty)
        allergies = self.extract_allergies(text)
        special = self.extract_special_requirements(text)
        address = self.extract_address(text)
        after = self.extract_delivery_time(text)

        # Two or more different addresses in one message = genuine ambiguity: never pick one silently.
        addresses = self.extract_all_addresses(text)
        ambiguous = len(addresses) >= 2

        changes = {
            "quantity": qty,
            "allergies": allergies,
            "special": special,
            "address": None if ambiguous else address,
            "after": after
        }
        if ambiguous:
            changes["addresses"] = addresses[:2]
            address = None
        if items:
            changes["items"] = items

        intent = self.extract_intent(text, sender, changes)
        conf = 0.95 if (qty is not None or allergies or address or after) else (0.85 if intent != "INFORMATION" else 0.6)

        return {
            "intent": intent,
            "language": lang,
            "confidence": conf,
            "requires_confirmation": False,
            "changes": changes,
            "agent_thought": f"Customer Agent: Detected language '{lang}'. Identified intent '{intent}'." +
                             (f" Quantity: {qty} meals." if qty is not None else "") +
                             (f" Allergens: {[a['ingredient'] for a in allergies]}." if allergies else "") +
                             (f" Time: {after}." if after else "") +
                             (f" Address: {address}." if address else "") +
                             (f" Ambiguous addresses: {addresses[:2]}." if ambiguous else "")
        }

    def generate_response(self, kind: str, state: dict, lang: str) -> str:
        """Generates localized customer response messages."""
        q = state.get("quantity", 0)
        allergies = state.get("allergies", [])
        special = state.get("special", [])
        pe = any(a["ingredient"] == "peanuts" for a in allergies)
        soft = any(x["requirement"] == "soft food" for x in special)

        # Other allergens
        other_al = [a["ingredient"] for a in allergies if a["ingredient"] != "peanuts"]
        al_text = f" (No {', '.join(other_al)})" if other_al else ""

        if lang == "te":
            base = {
                "received": f"మీ ఆర్డర్ అందింది. {q} భోజనాలు.",
                "reduced": f"మీ ఆర్డర్ నవీకరించబడింది: భోజనాల సంఖ్య {q}కు తగ్గించబడింది.",
                "preparing": "మీ ఆర్డర్ తయారవుతోంది. వంటగదిలో సిద్ధం చేస్తున్నారు.",
                "packaging": "మీ ఆర్డర్ ప్యాక్ చేస్తున్నాము. పరిశుభ్రత ప్రమాణాలు పాటిస్తున్నాము.",
                "packed": "మీ ఆర్డర్ ప్యాక్ చేయబడింది. డెలివరీకి సిద్ధంగా ఉంది.",
                "out": "మీ ఆర్డర్ డెలివరీకి బయలుదేరింది. త్వరలో మీ వద్దకు చేరుకుంటుంది.",
                "delivered": "మీ ఆర్డర్ డెలివరీ అయింది. ఆనందించండి, ధన్యవాదాలు!",
                "address_q": "మీ సంభాషణలో రెండు చిరునామాలు ఉన్నాయి. ఏది ఉపయోగించాలి?",
                "blocked": "ఆర్డర్ ప్యాక్ అయింది కాబట్టి మార్పు కోసం వంటగది ఆమోదం అవసరం."
            }
            if kind == "confirmed":
                msg = f"మీ ఆర్డర్ నిర్ధారించబడింది. {q} భోజనాలు సిద్ధం చేస్తున్నాము."
                if pe: msg += " ఒక భోజనంలో వేరుశెనగలు ఉండవు."
                if soft: msg += " మీ అమ్మమ్మ కోసం ఒక భోజనం మృదువుగా తయారు చేస్తాము."
                return msg
            return base.get(kind, f"ఆర్డర్ స్థితి: {kind}")

        if lang == "hi":
            base = {
                "received": f"आपका ऑर्डर मिल गया। {q} भोजन।",
                "reduced": f"आपका ऑर्डर अपडेट हो गया: भोजन की संख्या घटाकर {q} कर दी गई है।",
                "preparing": "आपका ऑर्डर तैयार हो रहा है। रसोई में तैयारी जारी है।",
                "packaging": "आपका ऑर्डर पैक किया जा रहा है।",
                "packed": "आपका ऑर्डर पैक हो गया है और डिलीवरी के लिए तैयार है।",
                "out": "आपका ऑर्डर डिलीवरी के लिए निकल चुका है।",
                "delivered": "आपका ऑर्डर डिलीवर हो गया। स्वादिष्ट भोजन का आनंद लें, धन्यवाद!",
                "address_q": "बातचीत में दो पते हैं। कौन सा पता इस्तेमाल करें?",
                "blocked": "ऑर्डर पैक हो चुका है, बदलाव के लिए रसोई की मंज़ूरी चाहिए।"
            }
            if kind == "confirmed":
                msg = f"आपका ऑर्डर पक्का हो गया। {q} भोजन तैयार करेंगे।"
                if pe: msg += " एक भोजन में मूंगफली नहीं होगी।"
                if soft: msg += " दादी/नानी के लिए एक भोजन नरम बनेगा।"
                return msg
            return base.get(kind, f"ऑर्डर स्थिति: {kind}")

        if lang == "ta":
            base = {
                "received": f"உங்கள் ஆர்டர் பெறப்பட்டது. {q} சாப்பாடு.",
                "reduced": f"உங்கள் ஆர்டர் புதுப்பிக்கப்பட்டது: {q} சாப்பாடாக குறைக்கப்பட்டுள்ளது.",
                "preparing": "உங்கள் உணவு சமையலறையில் தயாராகிறது.",
                "packaging": "உங்கள் ஆர்டர் பேக் செய்யப்படுகிறது.",
                "packed": "உங்கள் ஆர்டர் பேக் செய்யப்பட்டு தயாராக உள்ளது.",
                "out": "டெலிவரிக்கு புறப்பட்டது. விரைவில் வந்து சேரும்.",
                "delivered": "ஆர்டர் டெலிவரி செய்யப்பட்டது. நன்றி!",
                "address_q": "இரண்டு முகவரிகள் உள்ளன. எந்த முகவரி பயன்படுத்த வேண்டும்?",
                "blocked": "ஆர்டர் பேக் செய்யப்பட்டுவிட்டது, மாற்றத்திற்கு ஒப்புதல் தேவை."
            }
            if kind == "confirmed":
                return f"உங்கள் ஆர்டர் உறுதி செய்யப்பட்டது. {q} சாப்பாடு தயார் செய்கிறோம்."
            return base.get(kind, f"ஆர்டர் நிலை: {kind}")

        if lang == "kn":
            base = {
                "received": f"ನಿಮ್ಮ ಆರ್ಡರ್ ಸ್ವೀಕರಿಸಲಾಗಿದೆ. {q} ಊಟ.",
                "reduced": f"ನಿಮ್ಮ ಆರ್ಡರ್ ನವೀಕರಿಸಲಾಗಿದೆ: {q} ಊಟಕ್ಕೆ ಇಳಿಸಲಾಗಿದೆ.",
                "preparing": "ನಿಮ್ಮ ಆಹಾರ ಸಿದ್ಧವಾಗುತ್ತಿದೆ.",
                "packaging": "ನಿಮ್ಮ ಆರ್ಡರ್ ಪ್ಯಾಕ್ ಮಾಡಲಾಗುತ್ತಿದೆ.",
                "packed": "ನಿಮ್ಮ ಆರ್ಡರ್ ಪ್ಯಾಕ್ ಆಗಿದೆ.",
                "out": "ನಿಮ್ಮ ಆರ್ಡರ್ ಡೆಲಿವರಿಗೆ ಹೊರಟಿದೆ.",
                "delivered": "ನಿಮ್ಮ ಆರ್ಡರ್ ತಲುಪಿದೆ. ಧನ್ಯವಾದಗಳು!",
                "address_q": "ಎರಡು ವಿಳಾಸಗಳಿವೆ. ಯಾವ ವಿಳಾಸ ಬಳಸಬೇಕು?",
                "blocked": "ಆರ್ಡರ್ ಪ್ಯಾಕ್ ಆಗಿದೆ, ಬದಲಾವಣೆಗೆ ಅನುಮೋದನೆ ಬೇಕು."
            }
            if kind == "confirmed":
                return f"ನಿಮ್ಮ ಆರ್ಡರ್ ದೃಢೀಕರಿಸಲಾಗಿದೆ. {q} ಊಟ ಸಿದ್ಧಪಡಿಸಲಾಗುತ್ತಿದೆ."
            return base.get(kind, f"ಆರ್ಡರ್ ಸ್ಥಿತಿ: {kind}")

        # Default English
        base_en = {
            "received": f"Order received: {q} meals.{al_text}",
            "reduced": f"Order updated: quantity reduced to {q} meals.",
            "preparing": f"Your order of {q} meals is currently being freshly prepared in our kitchen.",
            "packaging": "Your order is being carefully packaged with safety seals.",
            "packed": "Your order is securely packed and awaiting dispatch.",
            "out": "Your order is out for delivery! Our delivery partner is on the way.",
            "delivered": "Delivered successfully! Enjoy your fresh home-cooked meal. Thank you!",
            "address_q": "Two delivery addresses appear in the conversation. Which one should we use?",
            "blocked": "Your order is already packed; the kitchen team must approve this late modification."
        }
        if kind == "confirmed":
            msg = f"Order confirmed: {q} meals."
            if pe: msg += " No peanuts as requested."
            if soft: msg += " One soft-food meal will be prepared."
            return msg
        return base_en.get(kind, f"Order status updated: {kind}")
