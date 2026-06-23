"""
Authentication routes: login, logout.
Thesis reference: Chapter III – System Flow Diagram (Fig 3.4),
Data Security (session management, role-based routing).

Only Administrators log in here. Staff use the public Attendance Scan
Portal (see app/routes/scan.py) which requires no account — just a
Staff No., Attendance PIN, and their printed QR badge.
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app.models import get_db
from app.utils.auth import (hash_password, verify_password,
                             login_user, logout_user, login_required)

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('admin.dashboard'))

    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not username or not password:
            error = 'Email and password are required.'
        else:
            with get_db() as conn:
                user = conn.execute(
                    "SELECT id, username, password_hash, role, is_active "
                    "FROM users WHERE username = ?",
                    (username,)
                ).fetchone()

            if user and user['is_active'] and verify_password(password, user['password_hash']):
                login_user(user['id'], user['role'], user['username'])
                flash(f"Welcome back, {username}!", 'success')
                next_url = request.args.get('next')
                if next_url:
                    return redirect(next_url)
                return redirect(url_for('admin.dashboard'))
            else:
                error = 'Invalid email or password.'

    return render_template('auth/login.html', error=error)


@auth_bp.route('/logout')
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))
