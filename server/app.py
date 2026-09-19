"""
Application entry point for the OSINT console.

Run directly (`python app.py`) for the dev server, or import `create_app()`
for a WSGI server (gunicorn, etc). All configuration - host, port, debug,
job limits, and where the scanner checkouts live - comes from config.SETTINGS,
which reads from the environment and an optional .env file at the project
root. See .env.example.
"""

from __future__ import annotations

from flask import Flask

from config import SETTINGS
from api import bp as api_bp
from api.blueprints.spa import bp as spa_bp

def create_app() -> Flask:
    app = Flask(__name__, static_folder=None)
    app.register_blueprint(api_bp)
    app.register_blueprint(spa_bp)
    return app

app = create_app()

def main():
    # threaded=True is required: a held-open SSE stream would otherwise
    # occupy the only worker and block every other request.
    app.run(
        host=SETTINGS.HOST, port=SETTINGS.PORT, debug=SETTINGS.DEBUG,
        threaded=True
    )

if __name__ == '__main__':
    main()