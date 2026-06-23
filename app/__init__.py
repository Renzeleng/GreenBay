
import os
from datetime import timedelta
from flask import Flask, redirect, url_for

from app.models import init_db
from app.routes.auth import auth_bp
from app.routes.admin import admin_bp
from app.routes.scan import scan_bp


def create_app(config: dict = None) -> Flask:
    app = Flask(__name__,
                template_folder='templates',
                static_folder='static')

    # ── Security configuration ──────────────────────────────────
    _secret_key_env = os.environ.get('SECRET_KEY')
    if not _secret_key_env:
        # A fresh random key is generated each time the process starts.
        # On a cloud PaaS, the process restarts on every redeploy and may
        # also restart automatically (crash recovery, scaling, periodic
        # platform maintenance) — each restart would silently invalidate
        # every Administrator's active session. This is harmless for local
        # development but must not happen in a real deployment, so we warn
        # loudly rather than fail silently.
        print()
        print('  [GreenBay] WARNING: SECRET_KEY is not set.')
        print('  [GreenBay] A random key was generated for this process only.')
        print('  [GreenBay] All sessions will be invalidated on every restart.')
        print('  [GreenBay] Set SECRET_KEY as a persistent environment variable')
        print('  [GreenBay] in your hosting platform before going live.')
        print()

    app.config.update(
        SECRET_KEY=_secret_key_env or os.urandom(32).hex(),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        # Cloud deployments: the hosting platform terminates HTTPS at its edge/
        # proxy and forwards plain HTTP internally, so this should be set to
        # 'true' in the platform's environment variables once deployed.
        SESSION_COOKIE_SECURE=os.environ.get('HTTPS', 'false').lower() == 'true',
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # 16 MB max upload
    )

    if config:
        app.config.update(config)

    # ── Initialize database ──────────────────────────────────────
    init_db()
    _seed_admin(app)

    # ── Register blueprints ──────────────────────────────────────
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(scan_bp)

    # ── Root redirect ────────────────────────────────────────────
    @app.route('/')
    def index():
        return redirect(url_for('auth.login'))

    # ── Template globals ─────────────────────────────────────────
    @app.context_processor
    def inject_globals():
        from flask import session
        return {
            'current_user_role': session.get('role'),
            'current_username':  session.get('username'),
            'clinic_name': 'Green Bay Pediatric Therapy Center',
        }

    return app


def _seed_admin(app: Flask):
    """Create the default admin account if no admin exists."""
    from app.models import get_db
    from app.utils.auth import hash_password

    with app.app_context():
        with get_db() as conn:
            admin_exists = conn.execute(
                "SELECT id FROM users LIMIT 1"
            ).fetchone()
            if not admin_exists:
                pw = hash_password('admin4499')
                conn.execute(
                    "INSERT INTO users (username, password_hash, role) VALUES (?,?,?)",
                    ('gbadmin', pw, 'admin')
                )
                print("[GreenBay] Default admin created: gbadmin / admin4499")
                print("[GreenBay] IMPORTANT: Change the default password after first login!")
