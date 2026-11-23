"""
privacy.py (alerts) - Task 20: the privacy filter for alert texts (FR-16, Design Revisions R8).

An alert goes to EVERY phone near the theft, so it must never contain:
  - phone numbers           (01712345678, +880 1712-345678, also written in Bangla digits)
  - email addresses
  - GD / FIR numbers        (they could identify the victim)
  - house / flat / road numbers ("House 12", "Flat 3B", "বাড়ি ১২")
  - the victim's name
  - blaming words about groups of people (alerts warn about places and times, never about kinds of people)

check_text() returns a list of problems (empty = the text is safe). The verifier sees each one,
highlighted, and must fix the text before approving.
"""
import re

BN_TO_EN = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")

# Words that blame a whole group of people. Kept short and clear on purpose; admins can extend it later.
BLAMING_WORDS = [
    "rohingya", "bihari", "tokai", "hijra", "addict", "drug addict", "junkie", "slum people", "slum dwellers",
    "beggars", "street kids", "pagla", "pagol",
    "রোহিঙ্গা", "বিহারি", "টোকাই", "হিজড়া", "নেশাখোর", "মাদকাসক্ত", "বস্তির লোক", "ভিক্ষুক", "পাগল",
]

# A phone number: 10 or more digits, maybe with spaces or dashes between them (+880 1712-345678)
DIGIT_RUN = re.compile(r"\+?\d[\d\s-]{8,}\d")

PATTERNS = [
    ("email", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "Email addresses are not allowed."),
    ("gd_number", re.compile(r"\b(?:GD|G\.D\.|FIR|case)\s*(?:no\.?|number|#)?\s*[:#-]?\s*\d+|জিডি\s*(?:নং|নম্বর)?\s*[:#-]?\s*\d+|এফআইআর\s*\d+",
                             re.IGNORECASE), "GD or FIR numbers are not allowed."),
    ("house_number", re.compile(r"\b(?:house|holding|flat|apartment|apt|road|plot|block|building)\s*(?:no\.?|number|#)?\s*[:#-]?\s*\d+\w?"
                                r"|#\s*\d+|(?:বাড়ি|বাসা|ফ্ল্যাট|রোড|হোল্ডিং)\s*(?:নং|নম্বর)?\s*[:#-]?\s*\d+", re.IGNORECASE),
     "House, flat or road numbers are not allowed."),
]


def check_text(text: str, names: list[str] | None = None, gd_number: str | None = None) -> list[dict]:
    """All privacy problems in one text. `names` = the victim's name parts, `gd_number` = this report's GD."""
    plain = text.translate(BN_TO_EN)  # "০১৭১২…" is checked like "01712…"
    problems: list[dict] = []
    for found in DIGIT_RUN.finditer(plain):
        if sum(ch.isdigit() for ch in found.group()) >= 10:
            problems.append({"code": "phone", "match": text[found.start():found.end()].strip(),
                             "message": "Phone numbers are not allowed."})
    for code, pattern, message in PATTERNS:
        for found in pattern.finditer(plain):
            problems.append({"code": code, "match": text[found.start():found.end()], "message": message})
    if gd_number and len(gd_number) >= 2 and re.search(rf"(?<![\w]){re.escape(gd_number)}(?![\w])", plain):
        problems.append({"code": "gd_number", "match": gd_number, "message": "This report's GD number is not allowed."})
    for name in names or []:
        if len(name) >= 3 and re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text, re.IGNORECASE):
            problems.append({"code": "name", "match": name, "message": "The victim's name is not allowed."})
    lowered = text.lower()
    for word in BLAMING_WORDS:
        if re.search(rf"(?<!\w){re.escape(word)}(?!\w)", lowered):
            problems.append({"code": "blaming", "match": word,
                             "message": "Don't blame groups of people. Describe the place and time instead."})
    # The same text found by two patterns is reported once
    unique, seen = [], set()
    for p in problems:
        if (p["code"], p["match"].lower()) not in seen:
            seen.add((p["code"], p["match"].lower()))
            unique.append(p)
    return unique


def victim_name_parts(user: dict | None) -> list[str]:
    """'Nila Rahman' + 'নীলা রহমান' -> ['Nila', 'Rahman', 'নীলা', 'রহমান'] (common short words left out)."""
    if not user:
        return []
    skip = {"md", "md.", "mohammad", "muhammad", "mst", "mst.", "bin", "binte"}
    parts = f"{user.get('name_en', '')} {user.get('name_bn', '')}".split()
    return [p for p in parts if p.lower() not in skip and len(p) >= 3]
