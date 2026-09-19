"""GET /scanners - which scanners exist on this machine and what they accept."""

from __future__ import annotations

from flask import Blueprint, jsonify

import core

bp = Blueprint('scanners', __name__)

@bp.get('/scanners')
def scanners():
    """
    Discovery plus the cached --help probe. The first call spawns one
    subprocess per scanner; later calls are served from cache.
    """
    return jsonify(core.diagnostics())