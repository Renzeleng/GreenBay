"""
Public Attendance Scan Portal.

No login account is required here — this is the tablet-facing kiosk flow.
Sequence enforced by the UI + this blueprint:

    1. Staff enters Staff No. + Attendance PIN  (verified server-side)
    2. On success, the camera opens (client-side, getUserMedia)
    3. jsQR continuously decodes the live video feed looking for the
       staff's own QR badge
    4. The instant a valid QR match is found, a photo is captured from
       the same video frame
    5. Both the decoded token and the photo (base64 JPEG) are POSTed
       together to /scan/submit, which re-validates everything and
       writes a single attendance record + saves the photo to disk

This two-step design (PIN check, then camera) means the camera is only
ever opened after the staff has proven who they claim to be, and the
QR badge is the second factor that actually unlocks the attendance log.
"""

import base64
import json
import os
import uuid
from datetime import datetime, date

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session

from app.models import get_db
from app.utils.auth import verify_pin

scan_bp = Blueprint('scan', __name__, url_prefix='/scan')

# Verification photos are runtime-generated user data and must survive
# application restarts and redeploys. On a cloud PaaS, the filesystem
# under the app's own source directory is typically ephemeral and is
# wiped on every redeploy, so PHOTO_DIR is configurable via an env var
# (mirroring DB_PATH in app/models/__init__.py) to point at a mounted
# persistent volume in production. Falls back to the bundled static
# folder for local development, where ephemeral storage is fine.
PHOTO_DIR = os.environ.get(
    'PHOTO_DIR',
    os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'attendance_photos')
)
os.makedirs(PHOTO_DIR, exist_ok=True)


# ─────────────────────────────────────────────
#  Step 1 — Staff No. + PIN
# ─────────────────────────────────────────────
@scan_bp.route('/', methods=['GET', 'POST'])
def identify():
    """Kiosk landing page: staff enters their Staff No. + Attendance PIN."""
    error = None
    if request.method == 'POST':
        staff_no = request.form.get('staff_no', '').strip()
        pin = request.form.get('pin', '').strip()

        if not staff_no or not pin:
            error = 'Please enter your Staff No. and PIN.'
        else:
            with get_db() as conn:
                staff = conn.execute("""
                    SELECT * FROM staff
                    WHERE staff_no = ? AND employment_status = 'active'
                """, (staff_no,)).fetchone()

            if not staff:
                error = 'Staff No. not found, or account is inactive.'
            elif not staff['attendance_pin_hash']:
                error = 'No PIN has been set for this account. Please see the administrator.'
            elif not verify_pin(pin, staff['attendance_pin_hash']):
                error = 'Incorrect PIN. Please try again.'
            elif not staff['qr_token'] or staff['qr_revoked']:
                error = 'No active QR badge on file. Please see the administrator.'
            else:
                # Identity confirmed — hand off to the camera step.
                # Store only the minimum needed in a short-lived session slot.
                session['scan_staff_id'] = staff['id']
                session['scan_staff_token'] = staff['qr_token']
                return redirect(url_for('scan.camera'))

    return render_template('scan/identify.html', error=error)


# ─────────────────────────────────────────────
#  Step 2 — Camera: QR scan + photo capture
# ─────────────────────────────────────────────
@scan_bp.route('/camera')
def camera():
    """Camera page — opens only after Step 1 succeeds."""
    staff_id = session.get('scan_staff_id')
    if not staff_id:
        flash('Please enter your Staff No. and PIN first.', 'warning')
        return redirect(url_for('scan.identify'))

    with get_db() as conn:
        staff = conn.execute("SELECT * FROM staff WHERE id = ?", (staff_id,)).fetchone()
    if not staff:
        session.pop('scan_staff_id', None)
        return redirect(url_for('scan.identify'))

    # Determine whether this scan will be a time-in or time-out
    today = date.today().isoformat()
    with get_db() as conn:
        has_time_in = conn.execute("""
            SELECT id FROM attendance WHERE staff_id=? AND scan_date=? AND scan_type='time_in'
        """, (staff['id'], today)).fetchone()
    scan_type = 'time_out' if has_time_in else 'time_in'

    return render_template('scan/camera.html',
                           staff=dict(staff),
                           scan_type=scan_type,
                           expected_token=staff['qr_token'])


# ─────────────────────────────────────────────
#  Step 3 — Submit: validate QR + save photo + log attendance
# ─────────────────────────────────────────────
@scan_bp.route('/submit', methods=['POST'])
def submit():
    """
    Receives the decoded QR text + captured photo (base64 JPEG) from the
    camera page, re-validates everything server-side, and writes the
    attendance record.
    """
    staff_id = session.get('scan_staff_id')
    if not staff_id:
        return jsonify({'success': False, 'message': 'Session expired. Please start again.'}), 400

    data = request.get_json(silent=True) or {}
    decoded_token = (data.get('qr_text') or '').strip()
    photo_b64 = data.get('photo') or ''

    with get_db() as conn:
        staff = conn.execute("""
            SELECT * FROM staff WHERE id = ? AND employment_status='active'
        """, (staff_id,)).fetchone()

    if not staff:
        session.pop('scan_staff_id', None)
        return jsonify({'success': False, 'message': 'Staff record not found.'}), 404

    # The decoded QR text must match this specific staff member's badge —
    # this is the step that actually prevents one person clocking in
    # using someone else's printed ID.
    if not decoded_token or decoded_token != staff['qr_token'] or staff['qr_revoked']:
        return jsonify({'success': False,
                        'message': 'QR badge does not match your account, or has been revoked. '
                                   'Please present your own ID badge.'}), 400

    staff = dict(staff)
    today = date.today().isoformat()
    now = datetime.now().isoformat(sep=' ', timespec='seconds')

    # Save the verification photo to disk
    photo_path = None
    if photo_b64:
        try:
            if ',' in photo_b64:
                photo_b64 = photo_b64.split(',', 1)[1]
            photo_bytes = base64.b64decode(photo_b64)
            fname = f"{staff['staff_no']}_{today}_{uuid.uuid4().hex[:8]}.jpg"
            fpath = os.path.join(PHOTO_DIR, fname)
            with open(fpath, 'wb') as fh:
                fh.write(photo_bytes)
            photo_path = f"attendance_photos/{fname}"
        except Exception:
            photo_path = None  # don't block attendance logging on a photo failure

    with get_db() as conn:
        existing_in = conn.execute("""
            SELECT id FROM attendance WHERE staff_id=? AND scan_date=? AND scan_type='time_in'
        """, (staff['id'], today)).fetchone()

        if not existing_in:
            # ── TIME IN ──
            conn.execute("""
                INSERT INTO attendance
                    (staff_id, scan_date, time_in, scan_type, device_reference,
                     qr_token_used, photo_path, status)
                VALUES (?, ?, ?, 'time_in', 'tablet-scan-portal', ?, ?, 'present')
            """, (staff['id'], today, now, decoded_token, photo_path))
            session.pop('scan_staff_id', None)
            session.pop('scan_staff_token', None)
            return jsonify({
                'success': True,
                'scan_type': 'time_in',
                'message': f"Time-IN recorded for {staff['first_name']} {staff['last_name']}.",
                'staff_name': f"{staff['first_name']} {staff['last_name']}",
                'scan_time': now,
            })

        existing_out = conn.execute("""
            SELECT id FROM attendance WHERE staff_id=? AND scan_date=? AND scan_type='time_out'
        """, (staff['id'], today)).fetchone()
        if existing_out:
            session.pop('scan_staff_id', None)
            session.pop('scan_staff_token', None)
            return jsonify({'success': False,
                            'message': f"{staff['first_name']} {staff['last_name']} has already "
                                       "completed time-in and time-out for today."}), 400

        # ── TIME OUT ──
        from app.utils.payroll import compute_hours_worked
        time_in_str = existing_in['id'] and conn.execute(
            "SELECT time_in FROM attendance WHERE id=?", (existing_in['id'],)
        ).fetchone()['time_in']
        hours = compute_hours_worked(time_in_str, now)

        conn.execute("""
            INSERT INTO attendance
                (staff_id, scan_date, time_in, time_out, scan_type, device_reference,
                 qr_token_used, photo_path, status, hours_worked)
            VALUES (?, ?, ?, ?, 'time_out', 'tablet-scan-portal', ?, ?, 'present', ?)
        """, (staff['id'], today, time_in_str, now, decoded_token, photo_path, hours))

    session.pop('scan_staff_id', None)
    session.pop('scan_staff_token', None)
    return jsonify({
        'success': True,
        'scan_type': 'time_out',
        'message': f"Time-OUT recorded for {staff['first_name']} {staff['last_name']}. "
                   f"Hours worked: {hours:.2f}h",
        'staff_name': f"{staff['first_name']} {staff['last_name']}",
        'scan_time': now,
        'hours_worked': hours,
    })


@scan_bp.route('/cancel')
def cancel():
    """Abort the scan flow and return to the ID entry step."""
    session.pop('scan_staff_id', None)
    session.pop('scan_staff_token', None)
    return redirect(url_for('scan.identify'))


@scan_bp.route('/photo/<filename>')
def serve_photo(filename):
    """
    Serve a verification photo by filename.

    photo_path is stored in the database as "attendance_photos/<filename>"
    for backward compatibility with records created before PHOTO_DIR became
    configurable. This route ignores that prefix and always reads from the
    real, current PHOTO_DIR — which may be the bundled static folder (local
    dev) or a mounted persistent volume path (cloud deployment) depending on
    the PHOTO_DIR environment variable. Templates should link here via
    url_for('scan.serve_photo', filename=...) rather than url_for('static', ...).
    """
    from flask import send_from_directory, abort
    # send_from_directory safely rejects path traversal attempts (e.g. '../..')
    try:
        return send_from_directory(PHOTO_DIR, filename)
    except (FileNotFoundError, NotADirectoryError):
        abort(404)
