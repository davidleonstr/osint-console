"""
Scan lifecycle endpoints.

    GET  /scans                 recent jobs
    POST /scans                 start a scan, returns its id
    GET  /scans/<id>            one snapshot, with optional cursors
    GET  /scans/<id>/stream     Server-Sent Events, live
    POST /scans/<id>/cancel     stop a running scan
    GET  /scans/<id>/export     download json, csv or md

The live channel is SSE rather than polling. The browser opens one request,
the server holds it open and writes an event whenever a worker appends
output. Each event carries only log lines not yet sent on that connection,
tracked by a per-connection cursor, so reconnecting mid-scan replays from the
start rather than losing the earlier output.
"""

from __future__ import annotations

import json
import time

from flask import Blueprint, Response, jsonify, request

import core
from config import SETTINGS

bp = Blueprint('scans', __name__)

def whole(payload: dict, name: str, fallback: int, low: int, high: int) -> int:
    try:
        value = int(payload.get(name, fallback))
    except (TypeError, ValueError):
        return fallback
    return max(low, min(value, high))

def read_cursors(args) -> dict:
    cursors = {}
    for name, value in args.items():
        if name.startswith('c_'):
            try:
                cursors[name[2:]] = int(value)
            except ValueError:
                pass
    return cursors

@bp.get('/scans')
def list_scans():
    return jsonify({'scans': core.history()})

@bp.post('/scans')
def create_scan():
    payload = request.get_json(silent=True) or {}
    target = str(payload.get('target', ''))
    tools = payload.get('tools') or []
    if not isinstance(tools, list):
        return jsonify({'error': 'tools must be a list of scanner ids.'}), 400

    opts = {
        'parallel': whole(payload, 'parallel', SETTINGS.DEFAULT_PARALLEL, 1, 4),
        'site_timeout': whole(payload, 'timeout', SETTINGS.DEFAULT_SITE_TIMEOUT, 5, 120),
        'top_sites': whole(payload, 'top', SETTINGS.DEFAULT_TOP_SITES, 0, 3000),
    }

    job, problem = core.start(target, [str(t) for t in tools], opts)
    if job is None:
        return jsonify({'error': problem}), 400
    return jsonify({'id': job.id}), 201

@bp.post('/scans/<job_id>/cancel')
def cancel_scan(job_id):
    if not core.cancel(job_id):
        return jsonify({'error': 'No such scan.'}), 404
    return jsonify({'ok': True})

@bp.get('/scans/<job_id>')
def read_scan(job_id):
    job = core.JOBS.get(job_id)
    if job is None:
        return jsonify({'error': 'That scan is no longer in memory.'}), 404
    return jsonify(core.snapshot(job, read_cursors(request.args)))

@bp.get('/scans/<job_id>/stream')
def stream_scan(job_id):
    job = core.JOBS.get(job_id)
    if job is None:
        return jsonify({'error': 'That scan is no longer in memory.'}), 404

    def events():
        # Cursors live per connection, so a reconnect replays the whole log.
        cursors = {}
        last_beat = time.time()

        while True:
            # Clear before reading state. Clearing afterwards would drop a
            # wake-up set by a worker while the snapshot was being taken,
            # costing a full timeout of latency.
            job.pulse.clear()

            data = core.snapshot(job, cursors)
            for tool in data['tools']:
                cursors[tool['id']] = tool['cursor']

            yield 'event: state\ndata: ' + json.dumps(data, default=str) + '\n\n'

            drained = all(not tool['pending'] for tool in data['tools'])
            if data['status'] != 'running' and drained:
                yield 'event: end\ndata: {}\n\n'
                return

            # More lines are already buffered behind the batch cap, so go
            # straight round again instead of waiting.
            if not drained:
                continue

            # Otherwise sleep until a worker writes something.
            job.pulse.wait(timeout=1.0)

            if time.time() - last_beat > 15:
                last_beat = time.time()
                yield ': keepalive\n\n'

    return Response(
        events(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache, no-transform',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        },
    )

@bp.get('/scans/<job_id>/export')
def export_scan(job_id):
    job = core.JOBS.get(job_id)
    if job is None:
        return jsonify({'error': 'That scan is no longer in memory.'}), 404

    fmt = request.args.get('format', 'json')
    if fmt not in ('json', 'csv', 'md'):
        return jsonify({'error': 'Unknown export format.'}), 400

    filename, mimetype, body = core.export(job, fmt)

    # A real download, with the correct type and no encoding workaround.
    return Response(
        body,
        mimetype=mimetype,
        headers={'Content-Disposition': 'attachment; filename="' + filename + '"'},
    )