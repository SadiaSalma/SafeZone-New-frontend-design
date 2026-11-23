"""
storage.py - keeps uploaded files (Task 16: report photos) on the server's disk.

Files go into api/storage/ (the folder is in .gitignore: private data never goes to GitHub).
Each file gets a random name, so nobody can guess another person's photo address.
The database only stores the "key" (the path inside the storage folder).

Later (on a real server) this file is the only one to change to use cloud storage instead.
"""
import secrets
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.errors import AppError

API_FOLDER = Path(__file__).resolve().parent.parent  # .../api


def folder() -> Path:
    base = Path(settings.storage_dir)
    return base if base.is_absolute() else API_FOLDER / base


def save(data: bytes, extension: str = "jpg") -> str:
    """Write the bytes to a new random file. Returns its key, e.g. 'photos/2026-11/3f9c...e1.jpg'."""
    key = f"photos/{datetime.now(timezone.utc):%Y-%m}/{secrets.token_hex(16)}.{extension}"
    target = folder() / key
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return key


def path_of(key: str) -> Path:
    """The file for a key. Refuses keys that try to climb out of the storage folder ('../')."""
    root = folder().resolve()
    target = (root / key).resolve()
    if root not in target.parents or not target.is_file():
        raise AppError(404, "file_not_found", "This file does not exist.")
    return target


def delete(key: str) -> None:
    try:
        path_of(key).unlink()
    except AppError:
        pass  # already gone
