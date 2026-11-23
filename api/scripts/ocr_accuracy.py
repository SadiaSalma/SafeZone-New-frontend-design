r"""
ocr_accuracy.py - Task 29: measure how well OCR reads GD copies (Design Revisions R10: "measure it").

Put photos of GD copies in a folder together with a labels.json that says what each one really contains:

    {
      "gd1.jpg": {"gd_type": "GD", "gd_number": "854", "gd_date": "2026-11-18",
                  "police_station": "ramna-model-ps", "theft_type": "phone_snatching"},
      ...
    }

Then, from the api folder with the database running:
    .venv\Scripts\python.exe -m scripts.ocr_accuracy C:\path\to\folder

For every field it counts:  right (filled and correct) / WRONG (filled but not correct) / empty (left for the victim).
A WRONG fill is the bad case; an empty box only costs the victim a few seconds of typing.
Use REAL GD copies (with the owners' permission, names covered) for the number in the project report.
"""
import json
import sys
import time
from pathlib import Path

from app.config import settings
from app.db import database_status, get_db
from app.modules.ocr.parser import parse
from app.modules.ocr.reader import available, read

FIELDS = ["gd_type", "gd_number", "gd_date", "police_station", "theft_type"]


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("Use: python -m scripts.ocr_accuracy <folder with photos and labels.json>")
    folder = Path(sys.argv[1])
    labels = json.loads((folder / "labels.json").read_text(encoding="utf-8"))
    if not available():
        sys.exit("Tesseract is not installed (see README).")
    if not database_status()["ok"]:
        sys.exit("The database is not running (the GD formats and police stations come from it).")
    db = get_db()
    formats = [f["regex"] for f in db.gd_formats.find({"is_active": True})]
    stations = list(db.police_stations.find({}, {"code": 1, "name_en": 1, "name_bn": 1}))

    counts = {f: {"right": 0, "wrong": 0, "empty": 0} for f in FIELDS}
    seconds = []
    for name, truth in labels.items():
        started = time.perf_counter()
        reading = read((folder / name).read_bytes())
        result = parse(reading.lines, formats, stations, settings.ocr_min_confidence, reread=reading.reread_digits)
        seconds.append(time.perf_counter() - started)
        marks = []
        for f in FIELDS:
            got = result["fields"].get(f, {}).get("value")
            kind = "empty" if got is None else "right" if got == truth.get(f) else "wrong"
            counts[f][kind] += 1
            marks.append({"right": "ok", "wrong": f"WRONG({got})", "empty": "-"}[kind])
        print(f"{name:<32} {seconds[-1]:4.1f}s  " + "  ".join(f"{f}:{m}" for f, m in zip(FIELDS, marks)))

    total = len(labels)
    print(f"\n{total} photos, {sum(seconds) / total:.1f} s each on average\n")
    print(f"{'field':<16}{'right':>8}{'wrong':>8}{'empty':>8}")
    for f in FIELDS:
        c = counts[f]
        print(f"{f:<16}{c['right'] / total:>8.0%}{c['wrong'] / total:>8.0%}{c['empty'] / total:>8.0%}")


if __name__ == "__main__":
    main()
