"""
parser.py (ocr) - Task 29: finds the GD details in the words Tesseract read (FR-9, Design Revisions R8 + R10).

Fields it looks for (and NOTHING else - no names, no phone numbers, no addresses, R8):
  gd_type         "GD" or "FIR"          (জিডি / সাধারণ ডায়েরী  vs  FIR / মামলা / এজাহার)
  gd_number       e.g. "854"             after a label such as "জিডি নং-", "GD No:", "মামলা নং"
  gd_date         e.g. "2026-11-18"      after "তারিখ" / "Date" (Bangla digits are understood)
  police_station  e.g. "ramna-model-ps"  a known police station name, preferably on a line with "থানা" / "Police Station"
  theft_type      e.g. "phone_snatching" from words like "মোবাইল ... ছিনতাই", preferably in the "বিষয়" / "Subject" line

Every field gets a confidence (0-100): how sure Tesseract was about the words the value came from.
R10: a field is only filled when its confidence is at least OCR_MIN_CONFIDENCE (60), and a GD number
that matches none of the admin's GD formats is thrown away - better an empty box than a wrong one.
"""
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher

from app.modules.reports.schemas import clean_gd_number

BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
DHAKA = timezone(timedelta(hours=6))

NUMBER_RE = re.compile(
    r"(?P<label>\bG\.?\s?D\b|[জভ]ি\.?\s?ডি|\bF\.?\s?I\.?\s?R\b|মামলা|এজাহার)"
    r"[ \t]*(?:No\b\.?|Number|নং|নম্বর|নাম্বার)?[ \t]*[:\-–—#ঃ.]*[ \t]*"
    r"(?P<value>[0-9]{1,6}(?:/[0-9]{2,4})?)\b", re.IGNORECASE)
LABEL_ONLY_RE = re.compile(
    r"(?P<label>\bG\.?\s?D\b|[জভ]ি\.?\s?ডি|\bF\.?\s?I\.?\s?R\b|মামলা)[ \t]*(?P<after>No\b\.?|Number|নং|নম্বর|নাম্বার)[ \t]*[:\-–—#ঃ.]*",
    re.IGNORECASE)
NEXT_LABEL_RE = re.compile(r"তারিখ|তাং|Date", re.IGNORECASE)
DATE_LABEL_RE = re.compile(r"(?:তারিখ|তাং|Date)[ \t]*[:\-–—ঃ.]*[ \t]*(?P<d>\d{1,2})[./\-](?P<m>\d{1,2})[./\-](?P<y>\d{2,4})",
                           re.IGNORECASE)
DATE_RE = re.compile(r"\b(?P<d>\d{1,2})[./\-](?P<m>\d{1,2})[./\-](?P<y>\d{4})\b")
STATION_LABEL_RE = re.compile(r"থানা|ধানা|Police\s+Station|\bP\.?\s?S\b|Thana", re.IGNORECASE)  # "ধানা": a common OCR slip
SUBJECT_RE = re.compile(r"বিষয়|বিষয়|Subject", re.IGNORECASE)
FIR_LABELS = ("fir", "f.i.r", "মামলা", "এজাহার")
GENERIC_EN = {"police", "station", "model", "thana", "ps", "(airport)"}
GENERIC_BN = {"থানা", "মডেল"}

# Theft type: (type, words that must ALL appear - each is a list of alternatives). The first match wins.
THEFT_RULES = [
    ("motorbike_theft", [["মোটরসাইকেল", "মোটর সাইকেল", "motorbike", "motorcycle", "মোটরবাইক"]]),
    ("cng_theft", [["সিএনজি", "cng", "অটোরিকশা", "অটো রিকশা"]]),
    ("car_theft", [["প্রাইভেটকার", "প্রাইভেট কার", "গাড়ি চুরি", "car stolen", "car theft", "private car"]]),
    ("bicycle_theft", [["বাইসাইকেল", "bicycle", "বাই সাইকেল"]]),
    ("pickpocket", [["পকেটমার", "pickpocket", "pocket", "পকেট"]]),
    ("bag_snatching", [["ব্যাগ", "bag", "handbag", "ভ্যানিটি"], ["ছিনতাই", "snatch"]]),
    ("phone_snatching", [["মোবাইল", "ফোন", "phone", "mobile"], ["ছিনতাই", "snatch"]]),
    ("burglary", [["সিঁধ", "burglary", "বাসায় চুরি", "ঘরে চুরি", "house was broken", "break-in"]]),
    ("shop_theft", [["দোকান", "shop"]]),
]


@dataclass
class Word:
    text: str
    conf: float
    start: int
    end: int
    line: int
    box: tuple | None = None  # (x, y, width, height) in the cleaned image, when known


class Page:
    """The read words as one text, remembering where each word sits and how sure Tesseract was."""

    def __init__(self, lines: list[list[tuple]]):
        parts: list[str] = []
        self.words: list[Word] = []
        self.line_text: list[str] = []
        pos = 0
        for n, line in enumerate(lines):
            line_start = pos
            for i, item in enumerate(line):  # (word, confidence) or (word, confidence, box)
                text, conf = item[0], item[1]
                if i:
                    parts.append(" ")
                    pos += 1
                self.words.append(Word(text, conf, pos, pos + len(text), n, item[2] if len(item) > 2 else None))
                parts.append(text)
                pos += len(text)
            self.line_text.append("".join(parts)[line_start:pos].translate(BN_DIGITS))
            parts.append("\n")
            pos += 1
        self.text = "".join(parts).translate(BN_DIGITS)  # one character for one character: positions stay the same

    def conf(self, start: int, end: int) -> float:
        """Average confidence of the words that the text from start to end touches."""
        touched = [w.conf for w in self.words if w.start < end and w.end > start]
        return round(sum(touched) / len(touched), 1) if touched else 0.0

    def line_of(self, pos: int) -> int:
        return self.text.count("\n", 0, pos)

    def overall(self) -> float:
        return round(sum(w.conf for w in self.words) / len(self.words), 1) if self.words else 0.0


def _field(value, confidence: float, **extra) -> dict:
    return {"value": value, "confidence": round(confidence, 1), **extra}


# ---------------------------------------------------------------- the five fields
def _fits(number: str, formats: list[str]) -> str | None:
    try:
        number = clean_gd_number(number)
    except ValueError:
        return None
    if formats and not any(re.fullmatch(f, number) for f in formats):
        return None  # R10: a value that fits no GD format is thrown away, never shown
    return number


def _type_of(label: str) -> str:
    label = label.lower().replace(" ", "")
    return "FIR" if any(label.startswith(x) for x in FIR_LABELS) else "GD"


def _spot_after(page: Page, start: int, end: int) -> tuple | None:
    """The box on the same line between the end of a label and the next label ("তারিখ"/"Date") or the line end."""
    label_words = [w for w in page.words if w.start < end and w.end > start and w.box]
    if not label_words:
        return None
    last = label_words[-1]
    rest = [w for w in page.words if w.line == last.line and w.start >= end and w.box]
    stop = next((w for w in rest if NEXT_LABEL_RE.search(w.text)), None)
    between = [w for w in rest if stop is None or w.start < stop.start]
    x1 = last.box[0] + last.box[2] + 2
    if between:
        x2 = max(w.box[0] + w.box[2] for w in between) + 4
    elif stop:
        x2 = stop.box[0] - 4
    else:
        x2 = x1 + 8 * last.box[3]
    line_boxes = [w.box for w in page.words if w.line == last.line and w.box]
    y1 = min(b[1] for b in line_boxes)
    y2 = max(b[1] + b[3] for b in line_boxes)
    return (int(x1), int(y1), int(max(10, x2 - x1)), int(y2 - y1)) if x2 > x1 else None


def find_number(page: Page, formats: list[str], reread: Callable[[tuple], tuple[str, float]] | None = None,
                min_confidence: float = 60) -> tuple[dict | None, dict | None]:
    """(gd_number, gd_type) from the first labelled number that fits a known GD format.
    A number is only as trustworthy as the label in front of it: its confidence is the lower of the two."""
    unsure = None
    for m in NUMBER_RE.finditer(page.text):
        number = _fits(m.group("value"), formats)
        if not number:
            continue
        label_conf = page.conf(m.start("label"), m.end("label"))
        value_conf = page.conf(m.start("value"), m.end("value"))
        found = (_field(number, min(label_conf, value_conf)), _field(_type_of(m.group("label")), label_conf))
        if found[0]["confidence"] >= min_confidence or not reread:
            return found
        unsure = unsure or found  # not sure enough: try a second look below, keep this as the fallback
    # Second look: the label is there ("জিডি নং-") but the number was misread (e.g. Bangla digits read as letters).
    if reread:
        for m in LABEL_ONLY_RE.finditer(page.text):
            spot = _spot_after(page, m.start(), m.end())
            if not spot:
                continue
            digits, conf = reread(spot)
            number = _fits(digits, formats) if digits else None
            if number:
                label_conf = page.conf(m.start("label"), m.end("after"))
                second = (_field(number, min(label_conf, conf), second_look=True),
                          _field(_type_of(m.group("label")), label_conf))
                if not unsure or second[0]["confidence"] > unsure[0]["confidence"]:
                    return second
                break
    if unsure:
        return unsure
    # No number, but the page says what it is (e.g. the "সাধারণ ডায়েরী" heading)
    kind = re.search(r"সাধারণ\s+ডায়েরী|সাধারণ\s+ডায়েরি|General\s+Diary|এজাহার|First\s+Information\s+Report", page.text, re.I)
    if kind:
        gd_type = "FIR" if re.search(r"এজাহার|First", kind.group(0), re.I) else "GD"
        return None, _field(gd_type, page.conf(kind.start(), kind.end()))
    return None, None


def _as_date(d: str, m: str, y: str, today: date) -> date | None:
    year = int(y) + (2000 if len(y) == 2 else 0)
    try:
        found = date(year, int(m), int(d))
    except ValueError:
        return None
    if found > today + timedelta(days=1) or found.year < today.year - 2:
        return None  # a GD date can't be in the future or years ago
    return found


def find_date(page: Page, today: date) -> dict | None:
    for regex in (DATE_LABEL_RE, DATE_RE):  # a labelled date ("তারিখ- ...") first, else any date
        for m in regex.finditer(page.text):
            found = _as_date(m.group("d"), m.group("m"), m.group("y"), today)
            if found:
                return _field(found.isoformat(), page.conf(m.start("d"), m.end("y")))
    return None


def _core(name: str, generic: set[str]) -> str:
    words = [w for w in name.replace(",", " ").split() if w.lower() not in generic]
    return " ".join(words)


def find_station(page: Page, stations: list[dict]) -> dict | None:
    """The police station named on the page. A name on a line that says "থানা"/"Police Station" wins
    (the body may name the PLACE of the theft, e.g. "শাহবাগ মোড়", which is not the GD's station)."""
    labelled = {n for n, line in enumerate(page.line_text) if STATION_LABEL_RE.search(line)}
    best = None  # (score, position, field)
    lower = page.text.lower()
    for s in stations:
        for core in {_core(s["name_en"], GENERIC_EN).lower(), _core(s.get("name_bn", ""), GENERIC_BN)} - {""}:
            # exact
            for m in re.finditer(re.escape(core), lower):
                line = page.line_of(m.start())
                score = len(core) + (100 if line in labelled else 0)
                field = _field(s["code"], page.conf(m.start(), m.end()), name_en=s["name_en"], name_bn=s.get("name_bn", ""))
                if best is None or (score, -m.start()) > (best[0], -best[1]):
                    best = (score, m.start(), field)
            # close enough (an OCR slip in one letter), only on labelled lines
            size = len(core.split())
            for n in labelled:
                words = [w for w in page.words if w.line == n]
                for i in range(len(words) - size + 1):
                    window = words[i:i + size]
                    text = " ".join(w.text for w in window).lower()
                    ratio = SequenceMatcher(None, text, core).ratio()
                    if ratio >= 0.84 and text != core:
                        score = len(core) * ratio + 100
                        conf = page.conf(window[0].start, window[-1].end) * ratio
                        field = _field(s["code"], conf, name_en=s["name_en"], name_bn=s.get("name_bn", ""))
                        if best is None or (score, -window[0].start) > (best[0], -best[1]):
                            best = (score, window[0].start, field)
    return best[2] if best else None


def find_theft_type(page: Page) -> dict | None:
    subject_lines = [n for n, line in enumerate(page.line_text) if SUBJECT_RE.search(line)]
    places = [" ".join(page.line_text[n:n + 2]) for n in subject_lines] + [page.text]  # the subject first, then everything
    for text in places:
        low = text.lower()
        for theft, groups in THEFT_RULES:
            hits = []
            for alternatives in groups:
                found = next((a for a in alternatives if a.lower() in low), None)
                if not found:
                    break
                hits.append(found.lower())
            else:
                if theft == "bicycle_theft" and "মোটর" in low:
                    continue
                spans = [(m.start(), m.end()) for h in hits for m in [re.search(re.escape(h), page.text.lower())] if m]
                conf = sum(page.conf(a, b) for a, b in spans) / len(spans) if spans else 0
                return _field(theft, conf)
    return None


def parse(lines: list[list[tuple]], formats: list[str], stations: list[dict],
          min_confidence: float = 60, today: date | None = None,
          reread: Callable[[tuple], tuple[str, float]] | None = None) -> dict:
    """All fields Tesseract was sure enough about, plus the overall confidence and what was left out."""
    today = today or datetime.now(DHAKA).date()
    page = Page(lines)
    number, gd_type = find_number(page, formats, reread, min_confidence)
    found = {"gd_type": gd_type, "gd_number": number, "gd_date": find_date(page, today),
             "police_station": find_station(page, stations), "theft_type": find_theft_type(page)}
    fields = {k: v for k, v in found.items() if v and v["confidence"] >= min_confidence}
    unsure = sorted(k for k, v in found.items() if v and v["confidence"] < min_confidence)
    return {"fields": fields, "unsure": unsure, "confidence": page.overall(), "words": len(page.words)}
