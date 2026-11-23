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

    # --- One-time codes, sent to the MOBILE NUMBER ---
    # How codes reach people:
    #   "demo_screen" - shown on the website in a "Demo SMS" box + printed in the backend (development only, free)
    #   "console"     - printed in the backend window only (development only, free)
    #   "sms"         - a real SMS through BulkSMSBD (needs the SMS settings below; costs about 0.25-0.35 Tk/SMS)
    otp_channel: str = "demo_screen"
    otp_secret: str = "dev-only-change-me"  # used to scramble codes before saving them
    otp_minutes: int = 10  # how long a code stays valid

    # SMS company (only needed when otp_channel = "sms"): BulkSMSBD, https://bulksmsbd.net
    sms_api_url: str = "https://bulksmsbd.net/api/smsapi"
    sms_api_key: str = ""  # from the BulkSMSBD dashboard - keep it secret
    sms_sender_id: str = ""  # the approved sender ID / number shown on the SMS

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

    # --- Photos (Task 16) ---
    storage_dir: str = "storage"  # where uploaded photos are kept (inside api/, never uploaded to git)
    photo_max_mb: int = 5  # biggest photo we accept
    photo_max_side: int = 1600  # photos are shrunk so the longest side is at most this many pixels
    item_photos_per_report: int = 3  # FR-8: up to 3 item photos (+ 1 GD copy)

    # --- Review (Task 18) ---
    claim_minutes: int = 15  # FR-14: opening a report holds it for this verifier for 15 minutes

    # --- Simulated phone network (Task 21, Design Revisions R10) ---
    simulator_phones: int = 5000  # how many virtual phones to place around Dhaka
    tower_spacing_m: int = 800  # distance between neighbouring towers
    tower_range_m: int = 1000  # how far one tower reaches
    simulator_seed: int = 42  # same seed -> same network every time (useful for demos and tests)

    # --- Browser push notifications (Task 23) ---
    vapid_public_key: str = ""  # made by scripts/make_vapid_keys.py (empty = push switched off)
    vapid_private_key: str = ""  # SECRET: only in .env
    vapid_subject: str = "mailto:safezone-team@example.com"  # a contact for push services (no personal address)
    follow_areas_max: int = 10  # one browser can follow at most 10 areas
    follow_test_alert_seconds: int = 5  # a TEST alert this many seconds after following a new area (0 = off)

    # --- Background jobs (Task 22) ---
    background_jobs: bool = True  # the alert worker; tests switch it off

    # --- Reading GD photos with OCR (Task 29, Design Revisions R10) ---
    tesseract_cmd: str = ""  # empty = find tesseract.exe automatically (PATH or C:\Program Files\Tesseract-OCR)
    tessdata_dir: str = ""  # empty = use ~/tessdata if it has ben.traineddata, else Tesseract's own folder
    ocr_min_confidence: int = 60  # R10: a field is filled only when Tesseract is at least this sure
    ocr_timeout_seconds: int = 30  # R10: a slower scan is marked failed (the form works without it)
    ocr_workers: int = 2  # R10: at most 2 photos are read at the same time
    scan_max_side: int = 2400  # GD photos are kept a little larger than item photos, for reading
    scans_per_hour: int = 10  # per person
    scan_keep_hours: int = 24  # a scan that never became part of a report is deleted after this
    scan_keep_days_after_decision: int = 30  # R8: GD photos are deleted 30 days after the decision

    # Read values from the .env file in the folder where we start the server.
    model_config = SettingsConfigDict(env_file=".env")


# ONE settings object, created once, that every other file imports.
settings = Settings()
