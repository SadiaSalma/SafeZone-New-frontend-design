# SafeZone

Verified theft alerts, crime statistics and area safety for Dhaka.

SE 331 Software Engineering Design Capstone Project · Team-02 · Batch 41 · Daffodil International University

## What it does

- Victims report thefts together with their police GD (General Diary).
- Verifiers check each report and approve, reject or ask for more information.
- Approved reports become alerts for people in the area (simulated phones + browser notifications).
- Everyone can see a public theft map, area safety dashboards and a colour-coded danger map.

## Technology

| Part | Technology |
| --- | --- |
| Frontend | Next.js, React, TypeScript, Tailwind CSS |
| Backend | FastAPI (Python 3.12) |
| Database | MongoDB (single-node replica set) |
| Maps | Leaflet + OpenStreetMap tiles; area borders from geoBoundaries (BBS/OCHA, CC BY 3.0 IGO) |
| Push | Web Push (VAPID) with a service worker |
| OCR | Tesseract 5 (Bangla + English) + OpenCV (see "Reading the GD photo") |

## Project structure

```
safezone/
├── api/   FastAPI backend (Python)
└── web/   Next.js frontend (TypeScript)
```

## Run it on your computer

Needs: Python 3.12, Node.js, MongoDB Community Server (only the `mongod` program is used).

First time only:

```
cd api
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
cd ..\web
npm.cmd install
```

Every time, in three terminals:

| What | Folder | Command | Address |
| --- | --- | --- | --- |
| Database (MongoDB replica set rs0) | `api` | `.venv\Scripts\python.exe scripts\start_db.py` | port 27018 |
| Backend (FastAPI) | `api` | `.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000` | http://localhost:8000/docs |
| Website (Next.js) | `web` | `npm.cmd run dev` | http://localhost:3000 |

In VS Code the same commands are one click away: **Terminal → Run Task → "SafeZone: start ALL"**.

### Set-up order (first time; every step is safe to run again)

Run these in `api` with the database running (each one is also a VS Code task):

| Step | Command | What it does |
| --- | --- | --- |
| 1 | `.venv\Scripts\python.exe -m scripts.init_db` | creates the collections with their rules and indexes |
| 2 | `.venv\Scripts\python.exe -m scripts.load_areas` | 41 thanas, 92 wards, 34 police stations |
| 3 | `.venv\Scripts\python.exe -m scripts.make_network` | the simulated phone network (635 towers, 5000 phones) |
| 4 | `.venv\Scripts\python.exe -m scripts.make_vapid_keys` | keys for browser push notifications (paste them into `.env`) |
| 5 | `.venv\Scripts\python.exe -m scripts.create_admin` | the first admin account |
| 6 (optional) | `.venv\Scripts\python.exe -m scripts.demo_data add` | demo accounts and data for a presentation |

Loading the areas again never undoes an admin's changes (names, alert radius, on/off).

### Demo data (local computer only)

`scripts.demo_data add` creates clearly flagged demo data: about 30 alerted theft reports around busy places in
Dhaka (every alert starts with **[DEMO]**, every report says "Demo report - not a real theft"), 2 reports waiting
for review, and 6 months of crime figures with the source "Demo data - not real figures".
`scripts.demo_data remove` deletes all of it again, and nothing else. It refuses to run when `APP_ENV` is not
`development`.

| Role | Phone | Password |
| --- | --- | --- |
| Victim (Nila Rahman) | 01799000222 | demo-pass-123 |
| Victim (Karim Hossain) | 01799000555 | demo-pass-123 |
| Verifier (Rafiq Hasan) | 01799000333 | verify-pass-123 |
| Admin (Tania Akter) | 01799000444 | admin-pass-123 |

One-time codes (sign-up, forgot password, delete my data) are sent to the **mobile number by SMS**.
`OTP_CHANNEL` in `api/.env` chooses how:

| `OTP_CHANNEL` | What happens | Cost |
| --- | --- | --- |
| `demo_screen` (default) | The code shows on the website in a "Demo SMS" box and in the backend window. Development only. | Free |
| `console` | The code is printed in the backend window only. Development only. | Free |
| `sms` | A real SMS through [BulkSMSBD](https://bulksmsbd.net). Fill in `SMS_API_KEY` and `SMS_SENDER_ID`. | About 0.25-0.35 Tk per SMS |

The website refuses `demo_screen` and `console` when `APP_ENV` is not `development`, so a real server never shows codes.

### Tests

In `api`, run `.venv\Scripts\python.exe -m pytest`. The tests use a separate database (`safezone_test`) and never
touch your real data. In `web`, `npx tsc --noEmit` and `npx eslint .` check the website code.

## Pages

| Page | Who | What |
| --- | --- | --- |
| `/` | everyone | home, nearby alerts |
| `/map` | everyone | public theft map (points moved 100-200 m; burglaries only per area) |
| `/alerts`, `/alerts/[id]` | everyone | the latest verified alerts |
| `/areas`, `/areas/[code]` | everyone | thanas and wards, follow an area for push alerts, safety dashboard |
| `/crime` | everyone | danger map from official monthly figures (per km², relative levels) |
| `/register`, `/verify`, `/login`, `/forgot-password` | everyone | accounts |
| `/report/new` | victims | 4-step theft report with GD, photos and a saved draft |
| `/me/reports`, `/me/nid`, `/me/delete` | victims | my reports, add NID, delete my data |
| `/review`, `/review/[id]` | verifiers, admins | review queue, checks, approve / reject / ask for information, alert text |
| `/admin` | admins (overview: verifiers too) | overview, staff, areas, police stations, GD formats, risk settings, audit log |
| `/admin/alerts`, `/admin/simulator` | verifiers, admins | sent alerts, the phone-network simulator with test mode |
| `/admin/crime` | admins | monthly crime figures and category weights |

## Reading the GD photo (OCR)

On the GD step of the report form, "Scan your GD copy" reads a photo of the GD paper with **Tesseract 5**
(Bangla + English) after **OpenCV** cleans it (shadows evened out, straightened, resized). It finds the GD/FIR
type, number, date, police station and theft type, fills those boxes and marks them "From photo" so the victim
checks them. Rules (Design Revisions R10): a box is filled only when Tesseract is at least 60% sure, a GD number
must match a known GD format, at most 2 photos are read at once, over 30 s counts as failed. Names and other text
are never stored (R8). The verifier sees "GD photo vs form", and a difference adds a risk warning.

Needs Tesseract with the `ben` and `eng` language files. It is found automatically in
`C:\Program Files\Tesseract-OCR` and `%USERPROFILE%\tessdata`; otherwise set `TESSERACT_CMD` / `TESSDATA_DIR` in `.env`.
Without Tesseract the form still works: the victim types the details.

Measuring it: `.venv\Scripts\python.exe -m scripts.ocr_accuracy <folder>` (photos + `labels.json`).
On 20 test photos (4 printed GD layouts, each also tilted, shadowed, blurred, warped and noisy):

| Field | Right | Wrong | Left empty |
| --- | --- | --- | --- |
| GD or FIR | 95% | 0% | 5% |
| GD number | 90% | 0% | 10% |
| Date | 100% | 0% | 0% |
| Police station | 100% | 0% | 0% |
| Theft type | 95% | 0% | 5% |

About 0.7 s per photo. These are generated test photos; real, handwritten GD copies will score lower, so measure
again with real copies (owners' permission, names covered) for the project report.

## Simplifications

- Hotspots on the area dashboard use a simple grid count (250 m cells), not a machine-learning method (DBSCAN).

## Development progress

- [x] Phase A: Setup
- [x] Phase B: Accounts
- [x] Phase C: Areas
- [x] Phase D: Reporting
- [x] Phase E: Checks and review
- [x] Phase F: Alerts
- [x] Phase G: Public side
- [x] Phase H: Crime statistics
- [x] Phase I: OCR
- [x] Phase J: Admin and privacy
- [x] Phase K: Testing and demo

## Team

| Member | ID | Main responsibility |
| --- | --- | --- |
| Sadia Salma | 232-35-792 | Backend, database, alerts engine, integration |
| Ummay Arifun Nahar Jani | 232-35-528 | Frontend pages, maps, seed data, tests |
