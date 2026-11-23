"""
make_vapid_keys.py - creates the VAPID keys for browser push notifications (Task 23).

VAPID = the server's "ID card" for push services (Google, Mozilla, Apple). The PUBLIC key is
given to the browser; the PRIVATE key stays secret on the server and signs every push.

Run once, from the api folder:
    .venv\\Scripts\\python.exe -m scripts.make_vapid_keys
It adds VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY to api/.env (if they are not there yet).
Never upload .env to GitHub (.gitignore already keeps it out).
"""
import base64
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

ENV = Path(__file__).resolve().parent.parent / ".env"


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def new_keys() -> tuple[str, str]:
    private = ec.generate_private_key(ec.SECP256R1())
    private_raw = private.private_numbers().private_value.to_bytes(32, "big")
    public_raw = private.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return b64url(public_raw), b64url(private_raw)


def main() -> None:
    text = ENV.read_text(encoding="utf-8") if ENV.exists() else ""
    if "VAPID_PRIVATE_KEY=" in text:
        print("api/.env already has VAPID keys - nothing changed.")
        return
    public, private = new_keys()
    addition = (
        "\n# Browser push notifications (Task 23) - made by scripts/make_vapid_keys.py. Keep the private key secret.\n"
        f"VAPID_PUBLIC_KEY={public}\nVAPID_PRIVATE_KEY={private}\n"
    )
    ENV.write_text(text.rstrip("\n") + "\n" + addition, encoding="utf-8")
    print("Added VAPID keys to api/.env. Restart the backend to use them.")


if __name__ == "__main__":
    main()
