"""
Central configuration, loaded from environment variables and a .env file.

Only this module talks to os.environ for tunables. Every other module reads
from the `settings` object below, so the whole app's configuration surface
is described in exactly one place.

Precedence: real environment variables win over the .env file, and the .env
file wins over the defaults baked in here. That's python-dotenv's default
behaviour (load_dotenv does not override existing os.environ keys).
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Project root: the folder that contains this "server" package.
BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / '.env')

def cbool(name: str, fallback: bool) -> bool:
    value = os.environ.get(name)
    if value is None or value.strip() == '':
        return fallback
    return value.strip().lower() in ('1', 'true', 'yes', 'on')

def cint(name: str, fallback: int) -> int:
    value = os.environ.get(name)
    if value is None or value.strip() == '':
        return fallback
    try:
        return int(value)
    except ValueError:
        return fallback

def path(name: str, fallback: str) -> Path:
    """Resolve a configured path. Relative paths are anchored to BASE_DIR,
    so it doesn't matter what the current working directory is when the
    server is started."""
    raw = os.environ.get(name) or fallback
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = (BASE_DIR / candidate).resolve()
    return candidate

class Settings:
    # Where the scanner checkouts (sherlock/, maigret/, holehe/, blackbird/)
    # live. Defaults to ./tools alongside this project; override with
    # TOOLS_DIR in .env to point at a different folder (absolute or
    # relative to the project root).
    TOOLS_DIR: Path = path('TOOLS_DIR', './tools')

    # Built frontend (Vite output) served as static files.
    WEB_DIST_DIR: Path = path('WEB_DIST_DIR', './web/dist')

    HOST: str = os.environ.get('HOST', '127.0.0.1')
    PORT: int = cint('PORT', 8420)
    DEBUG: bool = cbool('DEBUG', False)

    # Job bookkeeping.
    MAX_JOBS: int = cint('MAX_JOBS', 20)
    MAX_LOG_LINES: int = cint('MAX_LOG_LINES', 4000)
    HARD_TIMEOUT: int = cint('HARD_TIMEOUT', 900)

    # Defaults applied when a scan request omits these options.
    DEFAULT_PARALLEL: int = cint('DEFAULT_PARALLEL', 2)
    DEFAULT_SITE_TIMEOUT: int = cint('DEFAULT_SITE_TIMEOUT', 20)
    DEFAULT_TOP_SITES: int = cint('DEFAULT_TOP_SITES', 500)

SETTINGS = Settings()