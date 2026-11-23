"""
make_area_file.py - builds api/data/dhaka_areas.geojson (Task 12).

You do NOT need to run this: the finished file is already in the project.
It is kept so anyone can see exactly where the map data came from.

Sources (Design Revisions R3: "pick one source and record it"):
  Thanas + wards: geoBoundaries BGD ADM3 / ADM4 (gbOpen, release 9469f09),
                  made from Bangladesh Bureau of Statistics (BBS) + OCHA data,
                  licence CC BY 3.0 IGO. Ward numbers are the old Dhaka City
                  Corporation numbers (1-92) used by the 2011 census.
  Police stations: OpenStreetMap contributors (ODbL), cleaned by hand
                  (one point per station, English + Bangla names) - see POLICE below.

How it was made:
  1. Download geoBoundaries-BGD-ADM3.geojson and geoBoundaries-BGD-ADM4.geojson
  2. .venv\\Scripts\\python.exe -m scripts.make_area_file <ADM3 file> <ADM4 file>
"""
import json
import re
import sys
from pathlib import Path

from shapely.geometry import box, mapping, shape
from shapely.ops import unary_union

OUT = Path(__file__).resolve().parent.parent / "data" / "dhaka_areas.geojson"
DHAKA_BOX = box(90.33, 23.68, 90.51, 23.90)  # the city, roughly
KM2_PER_DEGREE2 = 110.75 * 101.85  # 1 degree at Dhaka's latitude (23.8 N) is ~110.75 km north-south, ~101.85 km east-west
SIMPLIFY = 0.00015  # about 15 m: keeps the file small, still accurate for a city map
SOURCE_AREAS = "geoBoundaries BGD ADM3/ADM4 (BBS + OCHA, CC BY 3.0 IGO)"
SOURCE_DATE = "2011 census boundaries, published 2023-01-19"

# The Dhaka Metropolitan thanas in the source, with their Bangla names
THANAS = {
    "Adabor": "আদাবর", "Badda": "বাড্ডা", "Bangshal": "বংশাল", "Biman Bandar": "বিমানবন্দর",
    "Cantonment": "ক্যান্টনমেন্ট", "Chak Bazar": "চকবাজার", "Dakshinkhan": "দক্ষিণখান", "Darus Salam": "দারুস সালাম",
    "Demra": "ডেমরা", "Dhanmondi": "ধানমন্ডি", "Gendaria": "গেন্ডারিয়া", "Gulshan": "গুলশান",
    "Hazaribagh": "হাজারীবাগ", "Jatrabari": "যাত্রাবাড়ী", "Kadamtali": "কদমতলী", "Kafrul": "কাফরুল",
    "Kalabagan": "কলাবাগান", "Kamrangir Char": "কামরাঙ্গীরচর", "Khilgaon": "খিলগাঁও", "Khilkhet": "খিলক্ষেত",
    "Kotwali": "কোতোয়ালি", "Lalbagh": "লালবাগ", "Mirpur": "মিরপুর", "Mohammadpur": "মোহাম্মদপুর",
    "Motijheel": "মতিঝিল", "New Market": "নিউ মার্কেট", "Pallabi": "পল্লবী", "Paltan": "পল্টন",
    "Ramna": "রমনা", "Rampura": "রামপুরা", "Sabujbagh": "সবুজবাগ", "Shah Ali": "শাহ আলী",
    "Shahbagh": "শাহবাগ", "Sher-e-bangla Nagar": "শেরেবাংলা নগর", "Shyampur": "শ্যামপুর", "Sutrapur": "সূত্রাপুর",
    "Tejgaon": "তেজগাঁও", "Tejgaon Ind. Area": "তেজগাঁও শিল্পাঞ্চল", "Turag": "তুরাগ", "Uttar Khan": "উত্তরখান",
    "Uttara": "উত্তরা",
}

# Police stations: name_en, name_bn, latitude, longitude, phone (OpenStreetMap, cleaned)
POLICE = [
    ("Adabor Police Station", "আদাবর থানা", 23.77117, 90.35936, ""),
    ("Badda Police Station", "বাড্ডা থানা", 23.77141, 90.42736, ""),
    ("Banani Police Station", "বনানী থানা", 23.79004, 90.40186, ""),
    ("Biman Bandar (Airport) Police Station", "বিমানবন্দর থানা", 23.85028, 90.40907, ""),
    ("Chawkbazar Model Police Station", "চকবাজার মডেল থানা", 23.71714, 90.39575, "+88027313966"),
    ("Dhanmondi Model Police Station", "ধানমন্ডি মডেল থানা", 23.74330, 90.38156, "+88028631941"),
    ("Gendaria Police Station", "গেন্ডারিয়া থানা", 23.69956, 90.42106, ""),
    ("Gulshan Police Station", "গুলশান থানা", 23.79143, 90.41533, ""),
    ("Hazaribagh Police Station", "হাজারীবাগ থানা", 23.73471, 90.36519, ""),
    ("Kadamtali Police Station", "কদমতলী থানা", 23.69732, 90.45769, "+88027419505"),
    ("Kafrul Police Station", "কাফরুল থানা", 23.80128, 90.38149, "+88029871771"),
    ("Kamrangirchar Police Station", "কামরাঙ্গীরচর থানা", 23.70973, 90.36747, ""),
    ("Khilgaon Police Station", "খিলগাঁও থানা", 23.75101, 90.42527, ""),
    ("Khilkhet Police Station", "খিলক্ষেত থানা", 23.82813, 90.41982, ""),
    ("Kotwali Police Station", "কোতোয়ালি থানা", 23.70724, 90.40905, ""),
    ("Lalbagh Police Station", "লালবাগ থানা", 23.72061, 90.37924, ""),
    ("Mirpur Model Police Station", "মিরপুর মডেল থানা", 23.80439, 90.36311, ""),
    ("Mohammadpur Police Station", "মোহাম্মদপুর থানা", 23.75543, 90.36389, ""),
    ("Motijheel Police Station", "মতিঝিল থানা", 23.73004, 90.41702, ""),
    ("Mugda Police Station", "মুগদা থানা", 23.72889, 90.43335, ""),
    ("Nilkhet Police Station", "নীলক্ষেত থানা", 23.73316, 90.38693, ""),
    ("Pallabi Police Station", "পল্লবী থানা", 23.83000, 90.37732, ""),
    ("Ramna Model Police Station", "রমনা মডেল থানা", 23.74571, 90.40466, ""),
    ("Rampura Police Station", "রামপুরা থানা", 23.76132, 90.44367, ""),
    ("Sabujbagh Police Station", "সবুজবাগ থানা", 23.74057, 90.42840, ""),
    ("Shahbagh Police Station", "শাহবাগ থানা", 23.73715, 90.39627, ""),
    ("Shahjahanpur Police Station", "শাহজাহানপুর থানা", 23.73890, 90.42538, ""),
    ("Shyampur Model Police Station", "শ্যামপুর মডেল থানা", 23.69191, 90.43127, ""),
    ("Sutrapur Police Station", "সূত্রাপুর থানা", 23.70248, 90.41823, ""),
    ("Tejgaon Industrial Area Police Station", "তেজগাঁও শিল্পাঞ্চল থানা", 23.76535, 90.40062, ""),
    ("Uttara East Police Station", "উত্তরা পূর্ব থানা", 23.86698, 90.40055, ""),
    ("Uttara West Police Station", "উত্তরা পশ্চিম থানা", 23.87572, 90.38744, ""),
    ("Vatara Police Station", "ভাটারা থানা", 23.79747, 90.42404, ""),
    ("Wari Police Station", "ওয়ারী থানা", 23.71498, 90.41884, ""),
]

BN_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def km2(geom) -> float:
    return round(geom.area * KM2_PER_DEGREE2, 2)


def clean(geom):
    """Simplify, fix any self-crossing, round to 5 decimals (~1 m)."""
    geom = geom.simplify(SIMPLIFY, preserve_topology=True).buffer(0)
    data = mapping(geom)

    def round_all(value):
        if isinstance(value, (list, tuple)):
            if value and isinstance(value[0], (int, float)):
                return [round(value[0], 5), round(value[1], 5)]
            return [round_all(v) for v in value]
        return value

    return {"type": data["type"], "coordinates": round_all(data["coordinates"])}


def main(adm3_path: str, adm4_path: str) -> None:
    features = []

    # 1) Thanas
    thana_shapes = {}
    for f in json.load(open(adm3_path, encoding="utf-8"))["features"]:
        name = f["properties"]["shapeName"]
        geom = shape(f["geometry"])
        if name in THANAS and geom.representative_point().within(DHAKA_BOX):
            thana_shapes[name] = geom
    missing = set(THANAS) - set(thana_shapes)
    assert not missing, f"missing thanas: {missing}"
    for name, geom in sorted(thana_shapes.items()):
        features.append({"type": "Feature", "geometry": clean(geom), "properties": {
            "kind": "area", "code": slug(name), "name_en": name, "name_bn": THANAS[name], "type": "thana",
            "size_km2": km2(geom), "source": SOURCE_AREAS, "source_date": SOURCE_DATE}})

    # 2) Wards: "Ward No-15 (part)" pieces are joined into one ward
    pieces: dict[int, list] = {}
    for f in json.load(open(adm4_path, encoding="utf-8"))["features"]:
        found = re.match(r"Ward No-(\d+)", f["properties"]["shapeName"])
        geom = shape(f["geometry"])
        if found and int(found.group(1)) <= 92 and geom.representative_point().within(DHAKA_BOX):
            pieces.setdefault(int(found.group(1)), []).append(geom)
    for number, parts in sorted(pieces.items()):
        geom = unary_union(parts)
        overlaps = [slug(n) for n, t in thana_shapes.items() if t.intersection(geom).area > 0.05 * geom.area]
        features.append({"type": "Feature", "geometry": clean(geom), "properties": {
            "kind": "area", "code": f"dcc-w{number:02d}", "name_en": f"Ward {number}",
            "name_bn": f"ওয়ার্ড {str(number).translate(BN_DIGITS)}", "type": "ward", "thana_codes": overlaps,
            "size_km2": km2(geom), "source": SOURCE_AREAS, "source_date": SOURCE_DATE}})

    # 3) Police stations
    for name_en, name_bn, lat, lng, phone in POLICE:
        features.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lng, lat]}, "properties": {
            "kind": "police_station", "code": slug(name_en.replace("Police Station", "ps")), "name_en": name_en,
            "name_bn": name_bn, "phone": phone, "source": "OpenStreetMap contributors (ODbL)"}})

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False), encoding="utf-8")
    kinds = [f["properties"].get("type", f["properties"]["kind"]) for f in features]
    print(f"Wrote {OUT.name}: {kinds.count('thana')} thanas, {kinds.count('ward')} wards, "
          f"{kinds.count('police_station')} police stations, {OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
