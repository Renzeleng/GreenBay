"""
run.py — Development entry point for Green Bay QR Attendance & Payroll System.

Usage:
    python run.py

Environment variables (optional):
    SECRET_KEY   — Flask secret key  (default: dev key, change in production)
    DB_PATH      — SQLite file path  (default: greenbay.db in project root)
    PORT         — Port to listen on (default: 5000)
    HOST         — Host to bind to   (default: 127.0.0.1)
    DEBUG        — Set to '0' to disable debug mode (default: enabled)

For production, use a WSGI server (gunicorn/waitress) and set DEBUG=0 and a
strong SECRET_KEY.
"""

import os
import sys

# Ensure the project root is on sys.path so `app` package is importable
# regardless of the current working directory.
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import create_app  # noqa: E402  (import after path fix)

application = create_app()   # WSGI entry point alias used by gunicorn/waitress

if __name__ == '__main__':
    host  = os.environ.get('HOST', '127.0.0.1')
    port  = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', '1') != '0'

    print()
    print('  ╔══════════════════════════════════════════════════╗')
    print('  ║   Green Bay QR Attendance & Payroll System       ║')
    print('  ╚══════════════════════════════════════════════════╝')
    print(f'  Running on  http://{host}:{port}/')
    print(f'  Debug mode  {"ON" if debug else "OFF"}')
    print()
    print('  Default credentials:')
    print('    Username : gbadmin')
    print('    Password : admin4499')
    print()
    print('  Press Ctrl+C to quit.')
    print()

    application.run(host=host, port=port, debug=debug)
