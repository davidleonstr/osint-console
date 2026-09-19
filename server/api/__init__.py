from __future__ import annotations

from flask import Blueprint

from api.blueprints.scanners import bp as scanners_bp
from api.blueprints.scans import bp as scans_bp

bp = Blueprint('api', __name__, url_prefix='/api')

bp.register_blueprint(scanners_bp)
bp.register_blueprint(scans_bp)