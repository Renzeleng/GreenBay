# Green Bay QR Attendance & Payroll System

A full-stack web application implementing the capstone thesis:
**"QR Attendance and Payroll Solution for Clinic Personnel of Green Bay Pediatric Therapy Center"**
— Engada, Renzel Deo R. & Omamalin, Jaira B., AMA Computer College, General Santos City, August 2025.

**Revised architecture:** only Administrators have login accounts. Staff
attendance is captured on a dedicated **Android tablet kiosk** (an
entry-level model around ₱8,000 is sufficient — see Hardware below),
through a three-step flow: **Staff No. + PIN → camera opens → QR badge scan
+ verification photo, captured in the same instant.** Staff never log into
the main system at all.

**Hosting:** the application is designed to run on a low-cost cloud
Platform-as-a-Service (PaaS) — e.g. Railway or Render's Hobby tier,
roughly ₱300/month — rather than a local server at the clinic. This means
no server hardware to buy or maintain, and the Administrator can reach
the system from anywhere with an internet connection. See **Cloud
Deployment** below before going live.

---

## Quick Start

### 1. Prerequisites

- Python 3.10 or newer
- pip

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

> If you are on a restricted system, use: `pip install --break-system-packages -r requirements.txt`

### 3. Run the application

```bash
python run.py
```

The app will start at **http://127.0.0.1:5000/**

The SQLite database (`greenbay.db`) and all tables are created automatically on first run.

### 4. Default credentials (Administrator only)

| Role          | Email              | Password  |
|---------------|--------------------|-----------|
| Administrator | `admin@admin.com`  | `admin123` |

**Change the default password immediately after first login.**

Staff do **not** get credentials for the main system. Instead, for each
staff member the admin sets: a **Staff No.** (e.g. `GB-0001`), a **4–8
digit Attendance PIN**, and prints their **QR badge** (Staff → QR). Give
the staff member their PIN verbally/in person — it is never shown again
in the UI after creation.

### 5. Setting up the tablet kiosk

**Recommended device:** any entry-level Android tablet with a working
rear camera (Android 9.0+, 8MP camera minimum) is sufficient — there's
no need for a high-end model. Budget Android tablets in the ₱8,000 range
meet this comfortably; this is the figure used in the thesis's cost
analysis. A second unit held in reserve is a sensible (optional)
precaution against the primary kiosk being damaged or temporarily
unavailable.

1. On the tablet, open a browser to your deployed app's URL — e.g.
   `https://your-app-name.up.railway.app/scan/` if hosted on Railway,
   or whatever domain your hosting platform assigns — or click **"Access
   Attendance Scan Portal"** from the admin login screen, or copy the
   link from **Admin → Attendance → Scan Portal**.
2. Bookmark it / add it to the home screen, and mount or stand the
   tablet at the clinic's clock-in area, ideally with a stand or wall
   mount and connected to power, since it stays open all day.
3. The first time it's used, the browser will ask for camera permission
   — allow it.
4. Staff: enter your Staff No. + PIN, then hold your printed QR badge up
   to the camera. The instant it's recognized, a photo is captured
   automatically and attendance is logged — no extra taps needed.

> **Note:** the kiosk tablet needs a working internet connection (Wi-Fi)
> at all times, since the application itself is cloud-hosted — it is not
> a local app and has no offline mode. See **Cloud Deployment** below.

---

## Environment Variables

| Variable     | Default                          | Description                                                  |
|--------------|-----------------------------------|----------------------------------------------------------------|
| `SECRET_KEY` | random (regenerated on restart)  | Flask session secret. **Must be set to a fixed value in any real deployment** — see warning below. |
| `DB_PATH`    | `greenbay.db` (next to `run.py`) | Path to the SQLite database file. On a cloud host, point this at a mounted persistent volume (e.g. `/data/greenbay.db`) — see Cloud Deployment. |
| `PHOTO_DIR`  | `app/static/attendance_photos/`  | Folder where verification photos are saved. On a cloud host, point this at the same persistent volume as `DB_PATH` (e.g. `/data/attendance_photos`). |
| `PORT`       | `5000`                           | Port for the server. Most PaaS platforms (Railway, Render) set this automatically — don't hardcode it. |
| `HOST`       | `127.0.0.1`                      | Bind host. Use `0.0.0.0` so the platform's router/proxy can reach the app (required on virtually all cloud platforms). |
| `HTTPS`      | `false`                          | Set to `true` once deployed behind a platform that terminates HTTPS (Railway/Render do this automatically) — this makes session cookies `Secure`. |
| `DEBUG`      | `1`                               | Set to `0` in any real deployment. Leaving debug mode on in production both leaks stack traces and disables several safety checks. |

> **⚠️ `SECRET_KEY` warning:** if this isn't set, a new random key is
> generated every time the process starts. On a local machine that's a
> minor inconvenience. On a cloud host, the process restarts on every
> redeploy (and sometimes automatically for other reasons), which would
> silently log out every Administrator and invalidate all active
> sessions each time. The app prints a loud warning on startup if this
> happens — don't ignore it. Generate one once and set it permanently:
> ```bash
> python -c "import secrets; print(secrets.token_hex(32))"
> ```

---

## Cloud Deployment

The app is built to run on a low-cost PaaS rather than local server
hardware. The steps below are written for Railway, but the same shape
(connect repo → set env vars → add a persistent volume → deploy) applies
to Render and most similar platforms.

### 1. Push the code to a Git repository

The platform deploys from a Git repo (GitHub/GitLab), so commit this
project there first if you haven't already.

### 2. Create the service

- Sign up / log in to Railway (or Render).
- **New Project → Deploy from GitHub repo** → select this repository.
- The platform should auto-detect Python; if it asks for a start command, use:
  ```bash
  gunicorn run:application -w 2 -b 0.0.0.0:$PORT
  ```
  (`$PORT` is injected automatically by the platform — don't hardcode a port number.)

### 3. Add a persistent volume

This is the step it's easiest to forget, and the one that matters most.
Without it, **the SQLite database and every verification photo are wiped
on the next redeploy.**

- In the platform's dashboard, attach a persistent volume to the
  service (Railway: *Volumes* tab; Render: *Disks*). A small volume
  (1GB) is plenty for a single clinic.
- Mount it at a path such as `/data`.

### 4. Set environment variables

| Variable     | Value                                  |
|--------------|------------------------------------------|
| `SECRET_KEY` | output of `python -c "import secrets; print(secrets.token_hex(32))"` — generate once, set permanently |
| `DB_PATH`    | `/data/greenbay.db` (must be inside the mounted volume from step 3) |
| `PHOTO_DIR`  | `/data/attendance_photos` (same volume) |
| `HOST`       | `0.0.0.0` |
| `HTTPS`      | `true` (the platform terminates HTTPS for you at its edge) |
| `DEBUG`      | `0` |

### 5. Deploy and verify

- Trigger the deploy. The platform will give you a public URL
  (e.g. `https://greenbay-attendance.up.railway.app`).
- Open it, log in with the default admin credentials, **change the
  password immediately**, and confirm the dashboard loads.
- Open `/scan/` on the kiosk tablet and run through one full Staff
  No. + PIN + QR + photo cycle to confirm attendance logging works
  end-to-end against the live deployment.
- Redeploy once on purpose (e.g. push a trivial commit) and confirm the
  Administrator account and any test attendance record are still there
  afterward — this is the real test that the persistent volume is
  actually wired up correctly.

### Local development vs. cloud deployment

Nothing above changes how you run the app locally for development —
`python run.py` still works exactly as described in **Quick Start**,
using the local SQLite file and local `attendance_photos/` folder.
`DB_PATH`, `PHOTO_DIR`, and the rest only need to be set once, in the
hosting platform's environment variable settings, not in your local
shell.

### A note on SQLite at scale

SQLite is a deliberate, appropriate choice for a single clinic's
attendance and payroll volume — there's no separate database server to
provision or pay for. If a future deployment needs to serve multiple
clinic branches concurrently with meaningfully higher write volume, a
managed cloud database (e.g. a hosted PostgreSQL instance, which most
PaaS providers offer as an add-on) would be the natural next step. This
would only require changes to `app/models/__init__.py`'s connection
logic — the rest of the application talks to the database through
ordinary SQL and would not need to change.

---

## Project Structure

```
greenbay/
├── run.py                          # Dev entry point / WSGI alias
├── requirements.txt
├── README.md
└── app/
    ├── __init__.py                 # App factory, blueprint registration, seed admin
    ├── models/
    │   └── __init__.py             # SQLite schema + get_db() context manager
    ├── routes/
    │   ├── auth.py                 # Administrator login / logout (only role with accounts)
    │   ├── admin.py                # All administrator views (blueprinted at /admin/*)
    │   └── scan.py                 # Public tablet kiosk: Staff No.+PIN, camera, submit,
    │                               #   serve_photo (/scan/*)
    ├── utils/
    │   ├── auth.py                 # Password/PIN hashing, QR token gen, decorators
    │   ├── payroll.py              # Payroll computation engine
    │   ├── pdf_payslip.py          # ReportLab PDF payslip generator
    │   └── qr_generator.py         # Pure-Python QR code generator (SVG, no deps)
    ├── templates/
    │   ├── base.html               # Layout: sidebar, navbar, flash messages (admin-only)
    │   ├── auth/login.html         # Split-panel admin sign-in + link to scan portal
    │   ├── scan/
    │   │   ├── identify.html       # Step 1: Staff No. + PIN
    │   │   └── camera.html         # Step 2: live camera, jsQR decode, photo capture
    │   └── admin/
    │       ├── dashboard.html
    │       ├── staff_list.html
    │       ├── staff_form.html
    │       ├── staff_qr.html       # Printable QR badge + regenerate/revoke
    │       ├── attendance_scan.html # Kiosk link / setup page (no manual scan tool)
    │       ├── attendance_manual.html # Manual attendance entry (power outage / kiosk-down fallback)
    │       ├── attendance_list.html # Includes captured verification photos
    │       ├── payroll_compute.html
    │       ├── payroll_list.html
    │       ├── payroll_detail.html
    │       ├── reports.html
    │       ├── report_attendance.html
    │       └── report_payroll.html
    └── static/
        ├── branding/                # Logo assets (icon_only.png, logo_cropped.png)
        └── attendance_photos/      # Default photo storage (local dev only — set
                                     #   PHOTO_DIR to a persistent volume path in
                                     #   any cloud deployment; see Cloud Deployment)
```

---

## Thesis-to-Implementation Mapping

| Thesis Section | Implementation |
|---|---|
| **Ch. I — Background / Problem Statement** | Addressed by photo-verified QR attendance (prevents proxy attendance even more strongly than time-bound tokens alone) and automated payroll (eliminates manual errors) |
| **Ch. II — Related Literature: QR Codes** | `app/utils/qr_generator.py` — pure Python, GF(256), Reed-Solomon ECC, versions 1–10, EC level M |
| **Ch. II — Related Literature: Security** | PBKDF2-HMAC-SHA256 (260k iterations) for both admin passwords and staff PINs in `app/utils/auth.py`; parameterized SQL everywhere; HTTPS provided by the cloud hosting platform's managed TLS termination (see Cloud Deployment) |
| **Ch. III — Use Case: Administrator** | `app/routes/admin.py` — manage staff, print/revoke QR badges, review attendance + photos, compute & approve payroll, generate reports |
| **Ch. III — Use Case: Staff (Attendance)** | `app/routes/scan.py` — public kiosk flow: Staff No.+PIN → camera → QR scan + photo, no login account required |
| **Ch. III — Data Dictionary: users** | `users` table — **administrators only** now; id, username (email), password_hash, role, created_at |
| **Ch. III — Data Dictionary: staff** | `staff` table: staff_no (badge ID), name, position, daily_rate, attendance_pin_hash, qr_token (permanent), qr_revoked, is_active |
| **Ch. III — Data Dictionary: attendance** | `attendance` table: staff_id, scan_date, time_in, time_out, scan_type discriminator, hours_worked, **photo_path** (verification photo) |
| **Ch. III — Data Dictionary: payroll** | `payroll` table: staff_id, period, days_worked, gross/net pay, SSS, PhilHealth, Pag-IBIG (fixed monthly amounts, 2nd-cutoff-only), other_deductions, allowances; withholding_tax column retained but always 0, kept for schema compatibility |
| **Ch. III — Data Dictionary: payslip** | `payslip` table: payroll_id FK, is_released, released_at |
| **Ch. III — Data Dictionary: pay_period** | `pay_period` table: start/end date, label, is_active |
| **Ch. III — Data Dictionary: report** | `report` (audit log) table: action, entity_type, entity_id, performed_by, timestamp |
| **Ch. III — Payroll Computation** | `app/utils/payroll.py` — bi-weekly schedule; fixed monthly SSS/PhilHealth/Pag-IBIG totals with employee-share percentages (40%/50%/50%) deducted only on the second cutoff; withholding tax removed per clinic policy — see Implemented Deduction Schedule below |
| **Ch. III — QR Badge Security** | `secrets.token_urlsafe(32)`, permanent until admin revokes/regenerates; the camera step cross-checks the decoded text against the specific staff member already identified by PIN, so one person cannot clock in with another's badge |
| **Ch. III — System Flow: Attendance** | Staff No.+PIN verified → camera opens → jsQR decodes live video → match confirmed → photo captured from same frame → both submitted together → server re-validates and logs time_in or time_out |
| **Ch. III — System Flow: Payroll** | Admin selects period → system aggregates attendance → applies deductions → saves draft → admin approves → payslip released |
| **Ch. IV — PDF Payslip** | `app/utils/pdf_payslip.py` — ReportLab; clinic header, employee details, itemized earnings/deductions, net pay |
| **Ch. IV — Reports** | Admin reports: attendance by period (with photos), payroll by period; audit log of all system actions |
| **Ch. III — Requirement Analysis: Hardware/Network** | Cloud-hosted (no on-premises server hardware); kiosk device is a single Android tablet (~₱8,000); internet connection required at all times — see Cloud Deployment below |
| **Ch. III — Cost-Benefit Analysis** | ₱0 dev tools + ₱3,600/yr cloud hosting + ₱8,000 kiosk tablet + ₱3,000 training = ₱14,600 total estimated cost, against ₱35,000 estimated annual benefit |

---

## The Attendance Method, In Detail

The tablet (or any device with a camera) is used purely as a kiosk — it has
no admin login of its own. The sequence enforced by `app/routes/scan.py`
and the two templates in `app/templates/scan/`:

1. **Identify (`/scan/`)** — staff types their Staff No. and PIN. Both are
   checked server-side (`verify_pin`, PBKDF2). If correct, a short-lived
   `scan_staff_id` is placed in the session and the staff member is sent
   to the camera step. The QR badge's existence and revoked status are
   also checked here, before the camera ever opens.
2. **Camera (`/scan/camera`)** — `getUserMedia` opens the back camera.
   `jsQR` (loaded from cdnjs) decodes every video frame in a
   `requestAnimationFrame` loop. The expected token (this specific staff
   member's QR value) is embedded in the page so the client can give
   instant feedback, but it is never trusted on its own.
3. **Capture** — the instant a decoded QR value is found, the *same
   canvas frame* that was just used for decoding is exported as a JPEG
   data URL. This guarantees the photo and the QR scan are from the
   identical instant — there's no separate "now take a photo" step that
   could be gamed.
4. **Submit (`/scan/submit`)** — the decoded text and the photo are
   POSTed together as JSON. The server re-validates that the decoded
   token matches the staff member who passed the PIN check in step 1
   (not just "any valid token"), saves the photo to `PHOTO_DIR` (local
   `app/static/attendance_photos/` by default, or a mounted persistent
   volume path in a cloud deployment), and inserts the attendance row
   with `photo_path` set. Photos are served back to the Administrator
   via a dedicated `/scan/photo/<filename>` route rather than Flask's
   built-in static file handler, since `PHOTO_DIR` may live outside the
   app's static folder entirely once deployed.

If someone enters a different staff member's PIN, the server only ever
compares the scanned QR against *that* staff member's stored token — so
holding up the wrong badge is rejected even if the PIN was somehow known.

---

## Implemented Deduction Schedule

Payroll runs on a **bi-weekly schedule** (two cutoffs per month). Each
staff member has a fixed **monthly total** configured for each statutory
contribution; the employee's share of that monthly total is deducted in
full **only on the second (last) cutoff of the month** — the first
cutoff has no statutory deduction. This matches a simple, predictable
clinic payroll policy rather than computing contributions from BIR/SSS
income brackets.

| Contribution | Employee Share of Monthly Total | Deducted On |
|---|---|---|
| SSS | 40% (employer covers the remaining 60%) | 2nd cutoff only |
| PhilHealth | 50% (employer covers the remaining 50%) | 2nd cutoff only |
| Pag-IBIG | 50% (employer covers the remaining 50%) | 2nd cutoff only |
| Withholding Tax | Not computed — removed per clinic policy | — |

Each staff member's monthly contribution totals (e.g. "₱1,540/month
SSS") are set per-staff in their record and can be overridden
individually if a particular staff member's bracket differs from the
clinic's default. See `app/utils/payroll.py` —
`SSS_EMPLOYEE_SHARE` / `PHILHEALTH_EMPLOYEE_SHARE` /
`PAGIBIG_EMPLOYEE_SHARE` and `is_second_cutoff()`.

> Bracket-based statutory computation and withholding tax are
> intentionally out of scope for this implementation — see the thesis's
> Recommendations chapter, which identifies full DOLE/BIR-compliant
> bracket computation as a defined area for future work rather than
> something this prototype claims to already do.

---

## Implementation Notes & Decisions

1. **Flask over Django** — The app's scope is well-defined and constrained; Flask's lighter footprint avoids Django's overhead. Direct SQLite control maps cleanly to the thesis data dictionary without an ORM layer.

2. **Pure-Python QR generator** — The `qrcode` PyPI package was unavailable in the offline environment. A complete QR encoder was implemented from scratch using GF(256) arithmetic, Reed-Solomon error correction, and SVG output.

3. **PBKDF2 instead of bcrypt** — `bcrypt` requires C extensions (`libffi`). PBKDF2-HMAC-SHA256 with 260,000 iterations (NIST SP 800-132 compliant) provides equivalent protection using Python's stdlib `hashlib`. The same routine is reused for both admin passwords and staff attendance PINs.

4. **Admin-only accounts, staff get no login** — Staff are identified purely by Staff No. + Attendance PIN + their physical QR badge. This removes an entire account-management surface (no staff passwords to reset, no staff session security to worry about) while keeping a real two-factor check (something they know + something they have) at the point of clocking in.

5. **Permanent QR badges instead of 24-hour rotation** — Badges are printed once and reused indefinitely. Anti-proxy protection comes from the photo capture and from the QR being checked against the *specific* staff member who already passed the PIN check, not from a rotating token. The admin can still revoke or regenerate a badge instantly if one is lost.

6. **Photo + QR captured from the same frame** — The camera page captures the verification photo from the exact canvas frame that successfully decoded the QR code, rather than as a separate step. This removes any window where a different photo could be substituted.

7. **Attendance model** — Each day produces up to two `attendance` rows: one with `scan_type='time_in'` and one with `scan_type='time_out'`, each carrying its own `photo_path`. The `time_out` row carries the computed `hours_worked`.

8. **Payroll approval workflow** — Draft → Approved (admin reviews figures) → Released (payslip becomes visible to staff via PDF). This mirrors the thesis flow and prevents unapproved figures from being distributed.

9. **Audit log** — All create/edit/revoke/approve/release actions are written to the `report` table, fulfilling the thesis's reporting requirements and providing an audit trail.

10. **Configurable `PHOTO_DIR`, separate from Flask's static handler** — Verification photos are runtime-generated user data, not deployed code, so they need to survive redeploys on a cloud host. `PHOTO_DIR` is read from an environment variable (mirroring the existing `DB_PATH` pattern) so it can point at a mounted persistent volume in production. Because Flask's built-in `url_for('static', ...)` can only serve files from inside the configured static folder, photos are served instead through a dedicated `/scan/photo/<filename>` route that reads directly from `PHOTO_DIR`, wherever it actually points.

11. **Loud `SECRET_KEY` startup warning** — Originally the app silently generated a random secret key if none was set, which is harmless for local development but would silently log out every Administrator on each restart once deployed to a cloud platform (where the process restarts on every redeploy). The app now prints an explicit warning at startup if `SECRET_KEY` isn't set, so this is caught during initial deployment rather than discovered later as "random unexplained logouts."
