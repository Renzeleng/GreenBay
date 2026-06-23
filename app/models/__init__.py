"""
Database models for Green Bay QR Attendance & Payroll System.
Uses SQLite via Python's built-in sqlite3 module.
Thesis reference: Chapter III – Data Dictionary (Tables 3.1–3.5)
"""

import sqlite3
import hashlib
import os
from contextlib import contextmanager

DB_PATH = os.environ.get('DB_PATH', os.path.join(os.path.dirname(__file__), '..', '..', 'greenbay.db'))

@contextmanager
def get_db():
    """Context manager that yields a sqlite3 connection with row_factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    """Create all tables if they don't exist."""
    with get_db() as conn:
        conn.executescript("""
        -- ---------------------------------------------------------------
        -- Users Table — ADMINISTRATOR ACCOUNTS ONLY.
        -- Staff no longer have login accounts; they authenticate on the
        -- public Attendance Scan Portal using Staff No. + Attendance PIN
        -- (see `staff` table) instead of a username/password pair.
        -- ---------------------------------------------------------------
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            username    TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role        TEXT NOT NULL DEFAULT 'admin' CHECK(role IN ('admin')),
            is_active   INTEGER NOT NULL DEFAULT 1,
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        -- ---------------------------------------------------------------
        -- Staff profile. Standalone — NOT linked to a login account.
        -- Identification on the scan portal is via staff_no + PIN.
        -- ---------------------------------------------------------------
        CREATE TABLE IF NOT EXISTS staff (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            staff_no        TEXT NOT NULL UNIQUE,   -- printed on the QR ID badge
            first_name      TEXT NOT NULL,
            last_name       TEXT NOT NULL,
            email           TEXT,
            phone           TEXT,
            position        TEXT NOT NULL,
            employment_type TEXT NOT NULL DEFAULT 'full_time'
                                CHECK(employment_type IN ('full_time','part_time','contractual')),
            date_hired      DATE,
            -- Salary configuration
            daily_rate      REAL NOT NULL DEFAULT 0.0,
            monthly_rate    REAL NOT NULL DEFAULT 0.0,
            -- Fixed monthly statutory contributions (TOTAL employer+employee
            -- combined amount, in pesos). The employee's share is computed
            -- from these using a fixed split: SSS 40% employee / 60%
            -- employer; PhilHealth and Pag-IBIG 50% / 50%. Deducted in full
            -- only on the second (last) bi-weekly cutoff of each month —
            -- zero on the first cutoff. Defaults match the clinic's
            -- standard contribution amounts; admin can override per staff
            -- member on Staff Details (not shown on the creation form).
            sss_monthly_total        REAL NOT NULL DEFAULT 1540.0,
            philhealth_monthly_total REAL NOT NULL DEFAULT 500.0,
            pagibig_monthly_total    REAL NOT NULL DEFAULT 400.0,
            -- Attendance PIN (set/reset by admin; required on the scan portal
            -- alongside the QR badge — NOT a full account, attendance-only)
            attendance_pin_hash TEXT,
            -- QR badge token: permanent until the admin revokes/regenerates it
            -- (no expiry — printed once, reused indefinitely)
            qr_token        TEXT UNIQUE,
            qr_issued_at    DATETIME,
            qr_revoked      INTEGER NOT NULL DEFAULT 0,
            employment_status TEXT NOT NULL DEFAULT 'active'
                                CHECK(employment_status IN ('active','inactive','terminated')),
            created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        -- ---------------------------------------------------------------
        -- Table 3.1: Attendance List Table
        -- Captures time-in / time-out QR scan events with scan_type
        -- discriminator. device_reference logs scanning device/admin ID.
        -- photo_path stores the verification photo captured at scan time.
        -- ---------------------------------------------------------------
        CREATE TABLE IF NOT EXISTS attendance (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            staff_id        INTEGER NOT NULL REFERENCES staff(id),
            scan_date       DATE NOT NULL,
            time_in         DATETIME,
            time_out        DATETIME,
            -- scan_type discriminates individual scan events
            scan_type       TEXT NOT NULL CHECK(scan_type IN ('time_in','time_out')),
            device_reference TEXT,          -- device ID or admin username
            qr_token_used   TEXT,           -- token value at time of scan
            photo_path      TEXT,           -- verification photo captured during scan
            notes           TEXT,
            status          TEXT NOT NULL DEFAULT 'present'
                                CHECK(status IN ('present','absent','late','halfday')),
            hours_worked    REAL DEFAULT 0.0,
            created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        -- ---------------------------------------------------------------
        -- Table 3.2: Payroll Table
        -- Stores computed payroll per staff per pay period.
        -- ---------------------------------------------------------------
        CREATE TABLE IF NOT EXISTS payroll (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            staff_id            INTEGER NOT NULL REFERENCES staff(id),
            pay_period_start    DATE NOT NULL,
            pay_period_end      DATE NOT NULL,
            total_days_worked   REAL NOT NULL DEFAULT 0.0,
            total_hours_worked  REAL NOT NULL DEFAULT 0.0,
            gross_pay           REAL NOT NULL DEFAULT 0.0,
            -- Itemized deductions
            sss_deduction       REAL NOT NULL DEFAULT 0.0,
            philhealth_deduction REAL NOT NULL DEFAULT 0.0,
            pagibig_deduction   REAL NOT NULL DEFAULT 0.0,
            withholding_tax     REAL NOT NULL DEFAULT 0.0,
            other_deductions    REAL NOT NULL DEFAULT 0.0,
            other_deductions_note TEXT,
            total_deductions    REAL NOT NULL DEFAULT 0.0,
            net_pay             REAL NOT NULL DEFAULT 0.0,
            -- Allowances / additional pay
            allowances          REAL NOT NULL DEFAULT 0.0,
            allowances_note     TEXT,
            -- Approval workflow
            status              TEXT NOT NULL DEFAULT 'draft'
                                    CHECK(status IN ('draft','approved','released')),
            approved_by         INTEGER REFERENCES users(id),
            approved_at         DATETIME,
            created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        -- ---------------------------------------------------------------
        -- Table 3.3: Payslip Table
        -- References a payroll record; tracks issuance status.
        -- ---------------------------------------------------------------
        CREATE TABLE IF NOT EXISTS payslip (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            payroll_id      INTEGER NOT NULL UNIQUE REFERENCES payroll(id) ON DELETE CASCADE,
            issued_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
            generated_by    INTEGER REFERENCES users(id),
            is_released     INTEGER NOT NULL DEFAULT 0,
            released_at     DATETIME,
            created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        -- ---------------------------------------------------------------
        -- Table 3.4: Report Table
        -- Audit log of administrator-generated reports.
        -- ---------------------------------------------------------------
        CREATE TABLE IF NOT EXISTS report (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            report_type     TEXT NOT NULL,  -- 'attendance_summary','payroll_report','payslip'
            parameters      TEXT,           -- JSON-encoded filter params
            generated_by    INTEGER REFERENCES users(id),
            generated_at    DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        -- ---------------------------------------------------------------
        -- Pay periods: defines the company payroll schedule
        -- ---------------------------------------------------------------
        CREATE TABLE IF NOT EXISTS pay_period (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            period_start    DATE NOT NULL,
            period_end      DATE NOT NULL,
            label           TEXT,
            status          TEXT NOT NULL DEFAULT 'open'
                                CHECK(status IN ('open','processing','closed')),
            created_by      INTEGER REFERENCES users(id),
            created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """)
