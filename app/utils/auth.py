"""
Authentication utilities.
Thesis reference: Chapter III – Data Security (password hashing,
session management, role-based access control).

IMPORTANT (revised architecture): Staff no longer have login accounts.
Only Administrators log in to the main system. Staff identify themselves
on the public Attendance Scan Portal using their Staff No. + a simple
Attendance PIN, then present their printed QR badge to the camera.
"""

import hashlib
import hmac
import os
import secrets
from datetime import datetime
from functools import wraps

from flask import session, redirect, url_for, flash, g
from app.models import get_db


# ---------------------------------------------------------------------------
# Password / PIN hashing (PBKDF2-HMAC-SHA256 — stdlib only, bcrypt-equivalent)
# The same hashing routine is used for both admin passwords and staff
# attendance PINs; only the secret length convention differs.
# ---------------------------------------------------------------------------

def hash_password(plain: str) -> str:
    """Return a salted PBKDF2-SHA256 hash of the password/PIN."""
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac('sha256', plain.encode(), salt.encode(), 260_000)
    return f"pbkdf2:sha256:260000${salt}${dk.hex()}"

def verify_password(plain: str, stored_hash: str) -> bool:
    """Verify a password/PIN against its stored hash."""
    if not plain or not stored_hash:
        return False
    try:
        _, params = stored_hash.split('$', 1)
        salt, stored_dk = params.split('$')
        _, _, iters_str = stored_hash.split('$')[0].split(':')
        dk = hashlib.pbkdf2_hmac('sha256', plain.encode(), salt.encode(), int(iters_str))
        return hmac.compare_digest(dk.hex(), stored_dk)
    except Exception:
        return False

# Aliases used by the attendance-scan flow for readability
hash_pin = hash_password
verify_pin = verify_password

# ---------------------------------------------------------------------------
# QR badge token generation (PERMANENT — does not expire)
# Thesis reference: Chapter III – QR Code Technology, Security Architecture.
# Revised: printed badges should keep working indefinitely; the admin
# revokes/regenerates a token only if a badge is lost or a staff member
# leaves, rather than rotating it automatically every 24 hours.
# ---------------------------------------------------------------------------

def generate_qr_token() -> str:
    """Generate a cryptographically secure, permanent QR badge token."""
    return secrets.token_urlsafe(32)

# ---------------------------------------------------------------------------
# Flask session helpers (ADMIN ONLY — staff never get a session)
# ---------------------------------------------------------------------------

def login_user(user_id: int, role: str, username: str):
    """Store admin user info in Flask session."""
    session.permanent = True
    session['user_id'] = user_id
    session['role'] = role
    session['username'] = username
    session['_regenerated'] = secrets.token_hex(8)  # session fixation prevention

def logout_user():
    """Clear the Flask session."""
    session.clear()

def get_current_user():
    """Return current admin user dict from DB, or None."""
    user_id = session.get('user_id')
    if not user_id:
        return None
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, username, role, is_active FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()
    return dict(row) if row else None

# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to continue.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to continue.', 'warning')
            return redirect(url_for('auth.login'))
        if session.get('role') != 'admin':
            flash('Administrator access required.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated
