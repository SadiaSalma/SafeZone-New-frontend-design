"""
load_areas.py - puts Dhaka's 41 thanas, 92 wards and 34 police stations into the database (Task 12).

Run it from the api folder, with the database running:
    .venv\\Scripts\\python.exe -m scripts.load_areas
(or in VS Code: Terminal -> Run Task -> "SafeZone: load Dhaka areas")

Safe to run again: places are updated, never doubled.
The data comes from api/data/dhaka_areas.geojson (see scripts/make_area_file.py for its sources).
"""
import sys

from app.db import database_status, get_db
from app.modules.areas.service import load_area_file
from app.setup_db import apply_schema


def main() -> None:
    if not database_status()["ok"]:
        sys.exit("The database is not running. Start it first: Run Task -> 'SafeZone: start database'.")
    db = get_db()
    apply_schema(db)  # make sure the collections and map indexes exist
    counts = load_area_file(db)
    print(f"Loaded {counts['thanas']} thanas, {counts['wards']} wards and "
          f"{counts['police_stations']} police stations into '{db.name}'.")


if __name__ == "__main__":
    main()
