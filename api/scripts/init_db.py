"""
init_db.py - sets up the SafeZone database: all collections, their rules and indexes.

Run it from the api folder, with the database running:
    .venv\\Scripts\\python.exe -m scripts.init_db
(or in VS Code: Terminal -> Run Task -> "SafeZone: set up database")

Safe to run again at any time (design doc, Section 4.1).
"""
import sys

from app.config import settings
from app.db import database_status, get_db
from app.modules.crime.admin import seed_categories
from app.modules.reports.service import seed_gd_formats
from app.setup_db import apply_schema


def main() -> None:
    if not database_status()["ok"]:
        sys.exit("The database is not running. Start it first: Run Task -> 'SafeZone: start database'.")

    db = get_db()
    print(f"Setting up database '{settings.mongodb_db}' ...")
    summary = apply_schema(db)

    print(f"  new collections:     {len(summary['created'])}  {', '.join(summary['created'])}")
    print(f"  updated collections: {len(summary['updated'])}")
    print(f"  indexes checked:     {summary['indexes']}")
    print(f"  GD formats added:    {seed_gd_formats(db)}")
    print(f"  crime categories:    {seed_categories(db)} added")
    print("Done. Open MongoDB Compass at mongodb://127.0.0.1:27018/?directConnection=true to look inside.")


if __name__ == "__main__":
    main()
