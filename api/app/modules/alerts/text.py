"""
text.py (alerts) - Task 20: writing the alert from a FIXED template (FR-16).

Only approved facts go in: what kind of theft, the area (thana · ward), roughly when
(rounded to the hour, Dhaka time) and one piece of safety advice for that kind of theft.
Never the exact place, the victim, the GD or the stolen items' details.

Example:
  EN: "SafeZone alert: Phone snatching near Gulshan (Ward 19) around 9 PM today.
       Keep your phone out of sight near the road. Verified with a police GD."
  BN: "সেফজোন সতর্কবার্তা: আজ রাত ৯টার দিকে গুলশান (ওয়ার্ড ১৯) এলাকায় ফোন ছিনতাইয়ের ঘটনা ঘটেছে।
       রাস্তার পাশে ফোন হাতে রাখবেন না। পুলিশের জিডি দিয়ে যাচাই করা।"
"""
from datetime import datetime, timedelta, timezone

from app.db import get_db
from app.modules.reports.schemas import THEFT_LABELS

DHAKA = timezone(timedelta(hours=6))
BN_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")

# How each theft reads in a Bangla sentence ("... এলাকায় ফোন ছিনতাইয়ের ঘটনা ঘটেছে।")
EVENT_BN = {
    "phone_snatching": "ফোন ছিনতাইয়ের ঘটনা ঘটেছে", "bag_snatching": "ব্যাগ ছিনতাইয়ের ঘটনা ঘটেছে",
    "pickpocket": "পকেটমারের ঘটনা ঘটেছে", "motorbike_theft": "মোটরসাইকেল চুরি হয়েছে",
    "bicycle_theft": "সাইকেল চুরি হয়েছে", "car_theft": "গাড়ি চুরি হয়েছে", "cng_theft": "সিএনজি অটোরিকশা চুরি হয়েছে",
    "burglary": "বাসায় চুরির ঘটনা ঘটেছে", "shop_theft": "দোকানে চুরির ঘটনা ঘটেছে", "other": "চুরির ঘটনা ঘটেছে",
}

ADVICE = {  # (English, Bangla) - one short tip per theft type
    "phone_snatching": ("Keep your phone out of sight near the road.", "রাস্তার পাশে ফোন হাতে রাখবেন না।"),
    "bag_snatching": ("Hold your bag on the side away from the road.", "ব্যাগ রাস্তার উল্টো দিকে শক্ত করে ধরুন।"),
    "pickpocket": ("Keep your wallet in a front pocket in crowds.", "ভিড়ে মানিব্যাগ সামনের পকেটে রাখুন।"),
    "motorbike_theft": ("Use a disc lock and park in a guarded place.", "ডিস্ক লক ব্যবহার করুন, পাহারা আছে এমন জায়গায় রাখুন।"),
    "bicycle_theft": ("Lock your bicycle to something fixed.", "সাইকেল কোনো স্থির জিনিসের সাথে তালা দিন।"),
    "car_theft": ("Park in a guarded place and lock the steering.", "পাহারা আছে এমন জায়গায় গাড়ি রাখুন, স্টিয়ারিং লক করুন।"),
    "cng_theft": ("Never leave the CNG unattended with the key inside.", "চাবি রেখে সিএনজি একা ফেলে যাবেন না।"),
    "burglary": ("Check your doors and window grills tonight.", "আজ রাতে দরজা ও জানালার গ্রিল ভালো করে দেখুন।"),
    "shop_theft": ("Keep valuables away from the counter edge.", "দামি জিনিস কাউন্টারের কিনারা থেকে দূরে রাখুন।"),
    "other": ("Stay alert and keep valuables out of sight.", "সতর্ক থাকুন, দামি জিনিস লুকিয়ে রাখুন।"),
}


def _hour_words(when: datetime) -> tuple[str, str]:
    """'9 PM' / 'রাত ৯টা' - the hour in Dhaka time."""
    local = when.astimezone(DHAKA)
    hour12 = local.hour % 12 or 12
    en = f"{hour12} {'AM' if local.hour < 12 else 'PM'}"
    part = ("ভোর" if 4 <= local.hour < 6 else "সকাল" if local.hour < 12 else "দুপুর" if local.hour < 15
            else "বিকেল" if local.hour < 18 else "সন্ধ্যা" if local.hour < 20 else "রাত") if local.hour >= 4 else "রাত"
    return en, f"{part} {str(hour12).translate(BN_DIGITS)}টা"


def _day_words(when: datetime, now: datetime) -> tuple[str, str]:
    days = (now.astimezone(DHAKA).date() - when.astimezone(DHAKA).date()).days
    if days == 0:
        return "today", "আজ"
    if days == 1:
        return "yesterday", "গতকাল"
    date = when.astimezone(DHAKA)
    return f"on {date.day} {date:%b}", f"{str(date.day).translate(BN_DIGITS)} তারিখ"


def template(report: dict, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    db = get_db()
    thana = db.areas.find_one({"_id": report.get("thana_id")}, {"name_en": 1, "name_bn": 1}) or {}
    ward = db.areas.find_one({"_id": report.get("ward_id")}, {"name_en": 1, "name_bn": 1}) or {}
    theft_en = THEFT_LABELS[report["theft_type"]][0]
    hour_en, hour_bn = _hour_words(report["occurred_at"])
    day_en, day_bn = _day_words(report["occurred_at"], now)
    tip_en, tip_bn = ADVICE[report["theft_type"]]

    place_en = thana.get("name_en", "Dhaka") + (f" ({ward['name_en']})" if ward else "")
    place_bn = (thana.get("name_bn") or thana.get("name_en", "ঢাকা")) + (f" ({ward.get('name_bn') or ward['name_en']})" if ward else "")
    return {
        "text_en": f"SafeZone alert: {theft_en} near {place_en} around {hour_en} {day_en}. {tip_en} Verified with a police GD.",
        "text_bn": f"সেফজোন সতর্কবার্তা: {day_bn} {hour_bn}র দিকে {place_bn} এলাকায় {EVENT_BN[report['theft_type']]}। {tip_bn} পুলিশের জিডি দিয়ে যাচাই করা।",
    }
