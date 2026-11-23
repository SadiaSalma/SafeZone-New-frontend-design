"""
make_network.py - builds the simulated phone network for Dhaka (Task 21): towers + virtual phones.

Run it from the api folder, with the database running and the areas loaded:
    .venv\\Scripts\\python.exe -m scripts.make_network               (5,000 phones)
    .venv\\Scripts\\python.exe -m scripts.make_network --phones 20000
(or in VS Code: Terminal -> Run Task -> "SafeZone: build phone network")

Safe to run again: the old towers and phones are replaced; test phones are kept.
"""
import argparse
import sys
import time

from app.db import database_status, get_db
from app.modules.simulator.network import build_network
from app.setup_db import apply_schema


def main() -> None:
    parser = argparse.ArgumentParser(description="Build SafeZone's simulated towers and phones.")
    parser.add_argument("--phones", type=int, default=None, help="how many virtual phones (default 5000)")
    parser.add_argument("--seed", type=int, default=None, help="change it to get a different random layout")
    args = parser.parse_args()
    if not database_status()["ok"]:
        sys.exit("The database is not running. Start it first: Run Task -> 'SafeZone: start database'.")
    db = get_db()
    apply_schema(db)
    started = time.perf_counter()
    counts = build_network(db, phones=args.phones, seed=args.seed)
    print(f"Built {counts['towers']} towers and {counts['phones']} virtual phones "
          f"in {time.perf_counter() - started:.1f} s.")


if __name__ == "__main__":
    main()
