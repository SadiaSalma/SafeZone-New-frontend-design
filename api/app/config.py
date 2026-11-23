"""
config.py - reads SafeZone's settings.

Settings live in the file api/.env, not inside the code.
That way we can change them without editing code (requirement NFR-7).
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Each line is one setting: its name, its type, and a default value
    # that is used when the .env file does not mention it.
    app_name: str = "SafeZone API"
    app_env: str = "development"  # "development" or "production"

    # The website's address. Only this address may call the backend from a browser (CORS).
    web_origin: str = "http://localhost:3000"

    # The database. Our own MongoDB runs on port 27018 as replica set "rs0"
    # (started with scripts/start_db.py). MONGODB_DB is the database's name.
    mongodb_uri: str = "mongodb://127.0.0.1:27018/?replicaSet=rs0"
    mongodb_db: str = "safezone"

    # --- One-time codes (Design Revisions R1) ---
    # How codes reach people:
    #   "console"     - printed in the backend window (development only, free)
    #   "email"       - sent by email through the SMTP settings below
    #   "demo_screen" - shown on screen, for the teacher demo (development only)
    otp_channel: str = "console"
    otp_secret: str = "dev-only-change-me"  # used to scramble codes before saving them
    otp_minutes: int = 10  # how long a code stays valid

    # Email server (only needed when otp_channel = "email"), e.g. Gmail with an app password
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    # --- Log-in "tickets" (design doc 5.1 and Section 9) ---
    jwt_secret: str = "dev-only-change-me-to-a-long-random-text"  # signs the short ticket
    access_minutes: int = 15  # the short ticket (access token) lasts 15 minutes
    refresh_days: int = 7  # the long ticket (refresh token) lasts 7 days
    max_code_attempts: int = 5  # wrong guesses allowed for one code

    # --- NID (national ID) number: stored only scrambled with this secret ---
    nid_secret: str = "dev-only-change-me-nid"
    nid_tries_per_hour: int = 10

    # --- Limits against spam (Design Revisions R9) ---
    codes_per_hour_per_target: int = 3
    registrations_per_hour_per_ip: int = 5
    logins_per_minute_per_ip: int = 20

    # --- Password-guessing lock (FR-4 + R9) ---
    device_lock_after: int = 10  # wrong passwords for one phone from ONE device...
    device_lock_window_minutes: int = 15  # ...within this many minutes...
    device_lock_minutes: int = 15  # ...lock that phone on that device for this long
    account_lock_after: int = 50  # wrong passwords for one phone from ANYWHERE in 1 hour
    account_lock_minutes: int = 60  # -> lock the whole account for this long

    # --- Areas (Task 12) ---
    default_alert_radius_m: int = 1000  # how far an alert reaches, unless an area sets its own
    area_data_file: str = "data/dhaka_areas.geojson"  # thanas, wards and police stations to load

    # --- Theft reports (FR-10, Task 14) ---
    report_max_age_days: int = 30  # only thefts from the last 30 days
    reports_per_day: int = 5  # at most 5 reports in 24 hours per person
    gd_max_days_after_theft: int = 7  # a GD filed later than this gets a warning (Task 17)

    # Read values from the .env file in the folder where we start the server.
    model_config = SettingsConfigDict(env_file=".env")


# ONE settings object, created once, that every other file imports.
settings = Settings()
