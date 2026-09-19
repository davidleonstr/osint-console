"""Serves the built Vite frontend, falling back to index.html for client routes."""

from __future__ import annotations

from flask import Blueprint, Response, send_from_directory

from config import SETTINGS

bp = Blueprint('spa', __name__)

@bp.get('/', defaults={'path': ''})
@bp.get('/<path:path>')
def spa(path):
    dist = SETTINGS.WEB_DIST_DIR
    if not dist.is_dir():
        return Response(
            'The frontend has not been built yet. Run "npm install" and '
            '"npm run build" in the web folder, or run "npm run dev" for the '
            'dev server with hot reload.',
            mimetype='text/plain',
            status=503,
        )
    candidate = dist / path
    if path and candidate.is_file():
        return send_from_directory(dist, path)
    return send_from_directory(dist, 'index.html')