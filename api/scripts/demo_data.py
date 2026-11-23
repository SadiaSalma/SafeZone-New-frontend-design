r"""
demo_data.py - Task 32: add or remove the clearly flagged demo data (see app/demo.py for what it contains).

Run it from the api folder, with the database running:
    .venv\Scripts\python.exe -m scripts.demo_data add
    .venv\Scripts\python.exe -m scripts.demo_data remove
(or in VS Code: Terminal -> Run Task -> "SafeZone: add demo data" / "SafeZone: remove demo data")

Load the areas and build the phone network first (two other VS Code tasks), so the demo has places and phones.
"""
import sys

from app.config import settings
from app.db import database_status, get_db
from app.demo import DEMO_ACCOUNTS, add, remove
from app.setup_db import apply_schema


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command not in ("add", "remove"):
        sys.exit("Use: python -m scripts.demo_data add   or   python -m scripts.demo_data remove")
    if settings.app_env != "development":
        sys.exit("Demo data is only for a local development computer, never for a real server.")
    if not database_status()["ok"]:
        sys.exit("The database is not running. Start it first: Run Task -> 'SafeZone: start database'.")
    db = get_db()
    apply_schema(db)
    if not db.areas.count_documents({}):
        sys.exit("Load the Dhaka areas first: Run Task -> 'SafeZone: load Dhaka areas'.")

    if command == "add":
        counts = add()
        print(f"Added {counts['reports']} alerted demo reports, {counts['waiting']} waiting for review and "
              f"{counts['crime_figures']} demo crime figures to '{db.name}'.")
        print("Demo accounts (for this computer only):")
        for a in DEMO_ACCOUNTS:
            print(f"  {a['role']:<9} phone {a['phone'].replace('+880', '0')}  password {a['password']}  ({a['name_en']})")
    else:
        counts = remove()
        print(f"Removed {counts['reports']} demo reports, {counts['alerts']} alerts, {counts['crime_figures']} crime figures "
              f"and {counts['accounts']} demo accounts from '{db.name}'.")


if __name__ == "__main__":
    main()
