"""
create_admin.py - creates a staff account: an admin (default) or a verifier.

Staff cannot sign up on the website, so the first admin is made here.
Run it from the api folder, with the database running:

    .venv\Scripts\python.exe -m scripts.create_admin
    .venv\Scripts\python.exe -m scripts.create_admin --role verifier

It asks for the name, phone number and password (the password is hidden while you type).
"""
import argparse
import getpass
import sys

from app.db import database_status
from app.errors import AppError
from app.modules.users.service import create_staff_user


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a SafeZone staff account.")
    parser.add_argument("--role", choices=["admin", "verifier"], default="admin")
    role = parser.parse_args().role

    if not database_status()["ok"]:
        sys.exit("The database is not running. Start it first: Run Task -> 'SafeZone: start database'.")

    print(f"Create a new {role} account")
    name = input("  Full name (English): ").strip()
    phone = input("  Phone (e.g. 01712345678): ").strip()
    password = getpass.getpass("  Password (hidden): ")
    if getpass.getpass("  Password again: ") != password:
        sys.exit("The two passwords are different. Nothing was created.")

    try:
        user = create_staff_user(name, phone, password, role)
    except AppError as error:
        details = "".join(f"\n    - {field}: {message}" for field, message in error.fields.items())
        sys.exit(f"Not created: {error.message}{details}")

    print(f"Done. {role.capitalize()} '{user['name_en']}' can now log in with {user['phone']}.")


if __name__ == "__main__":
    main()
