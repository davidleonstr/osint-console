"""
Scan orchestration.

This module knows nothing about HTTP. It owns the job registry, runs each
scanner as a subprocess in a background thread, merges results into a ledger
and renders exports. The Flask blueprints in blueprints/ sit on top of it.

Scans run in threads rather than inside a request so a long scan can't wedge
a worker: it would otherwise hold a worker for minutes, give the client no
output until the very end, and leave no way to cancel. Threads plus a live
stream keep output arriving as it is produced.

All the tunables here (job limits, timeouts, where the scanner checkouts
live) come from config.SETTINGS, which is itself populated from the
environment / a .env file. Nothing in this module reads os.environ directly.
"""

from __future__ import annotations

import io
import re
import subprocess
import tempfile
import threading
import time
import uuid
from collections import OrderedDict
from pathlib import Path

import adapters
from config import SETTINGS

LOCK = threading.RLock()
JOBS = OrderedDict()

EMAIL = re.compile(r'^[^@\s]+@[^@\s]+\.[a-z]{2,}$', re.I)
HANDLE = re.compile(r'^[A-Za-z0-9._\-]{1,64}$')

def classify(target: str) -> str:
    return 'email' if EMAIL.match(target.strip()) else 'username'

def validate(target: str):
    """Returns (ok, message_or_kind). Keeps shell-hostile input out of argv."""
    target = target.strip()
    if not target:
        return False, 'Enter a username or an email address.'
    if len(target) > 120:
        return False, 'That target is too long - 120 characters maximum.'
    kind = classify(target)
    if kind == 'username' and not HANDLE.match(target):
        return False, ('Usernames can use letters, digits, dot, underscore and '
                       'hyphen. For an email, include the @.')
    return True, kind

# --------------------------------------------------------------------------
# state
# --------------------------------------------------------------------------

class ToolRun:
    def __init__(self, found):
        self.id = found.id
        self.label = found.label
        self.found = found
        self.status = 'queued'
        self.note = ''
        self.command = ''
        self.exit_code = None
        self.started = 0.0
        self.finished = 0.0
        self.lines = []
        self.dropped = 0
        self.hits = OrderedDict()
        self.misses = 0
        self.blocked = 0
        self.proc = None

    def log(self, text: str) -> None:
        with LOCK:
            self.lines.append(text)
            if len(self.lines) > SETTINGS.MAX_LOG_LINES:
                cut = len(self.lines) - SETTINGS.MAX_LOG_LINES
                del self.lines[:cut]
                self.dropped += cut

    def record(self, hit: dict) -> None:
        if not hit:
            return
        if hit.get('state') == 'miss':
            self.misses += 1
            return
        key = hit.get('key')
        if not key:
            return
        with LOCK:
            if hit.get('state') == 'blocked':
                if key not in self.hits:
                    self.blocked += 1
                return
            existing = self.hits.get(key)
            if existing is None:
                self.hits[key] = hit
            elif not existing.get('url') and hit.get('url'):
                existing['url'] = hit['url']

    @property
    def elapsed(self) -> float:
        if not self.started:
            return 0.0
        return (self.finished or time.time()) - self.started

    @property
    def terminal(self) -> bool:
        return self.status in ('done', 'failed', 'skipped', 'cancelled')

class Job:
    def __init__(self, target: str, kind: str, tools: list, opts: dict):
        self.id = uuid.uuid4().hex[:12]
        self.target = target
        self.kind = kind
        self.opts = opts
        self.created = time.time()
        self.runs = OrderedDict((run.id, run) for run in tools)
        self.cancelled = False
        self.outdir = Path(tempfile.mkdtemp(prefix='osint-'))

        # Set whenever a worker appends output, so the stream can wake
        # immediately instead of waiting out a fixed poll interval.
        self.pulse = threading.Event()

    @property
    def status(self) -> str:
        if self.cancelled:
            return 'cancelled'
        if all(run.terminal for run in self.runs.values()):
            return 'complete'
        return 'running'

    @property
    def elapsed(self) -> float:
        return time.time() - self.created

# --------------------------------------------------------------------------
# runner
# --------------------------------------------------------------------------

def run_tool(job: Job, run: ToolRun, gate: threading.Semaphore) -> None:
    with gate:
        if job.cancelled:
            run.status = 'cancelled'
            job.pulse.set()
            return

        run.status = 'running'
        run.started = time.time()
        job.pulse.set()

        outdir = job.outdir / run.id
        outdir.mkdir(parents=True, exist_ok=True)

        try:
            argv = adapters.build_argv(run.found, job.target, job.kind,
                                       job.opts, outdir)
        except Exception as exc:
            run.status = 'failed'
            run.note = 'Could not build a command: ' + str(exc)
            run.finished = time.time()
            job.pulse.set()
            return

        run.command = ' '.join(argv)
        run.log('$ ' + run.command)
        if run.found.problem:
            run.log('# ' + run.found.problem)

        hard_timeout = SETTINGS.HARD_TIMEOUT
        deadline = time.time() + hard_timeout

        try:
            proc = subprocess.Popen(
                argv,
                cwd=run.found.cwd or None,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                env=adapters.child_env(),
                bufsize=1,
                text=True,
                encoding='utf-8',
                errors='replace',
                **adapters.creation_flags(),
            )
        except FileNotFoundError:
            run.status = 'failed'
            run.note = 'Interpreter or script not found: ' + argv[0]
            run.finished = time.time()
            job.pulse.set()
            return
        except Exception as exc:
            run.status = 'failed'
            run.note = str(exc)
            run.finished = time.time()
            job.pulse.set()
            return

        run.proc = proc
        watchdog = threading.Timer(hard_timeout, adapters.kill_tree, args=(proc,))
        watchdog.daemon = True
        watchdog.start()

        try:
            for raw in proc.stdout:
                if job.cancelled:
                    adapters.kill_tree(proc)
                    break
                line = adapters.clean(raw)
                if line:
                    run.log(line)
                    run.record(adapters.parse_line(run.id, line))
                    job.pulse.set()
                if time.time() > deadline:
                    run.log('# Hard timeout reached, stopping this scanner.')
                    adapters.kill_tree(proc)
                    break
        except Exception as exc:
            run.log('# Reader error: ' + str(exc))
        finally:
            watchdog.cancel()
            try:
                proc.stdout.close()
            except Exception:
                pass
            try:
                run.exit_code = proc.wait(timeout=20)
            except Exception:
                adapters.kill_tree(proc)
                run.exit_code = proc.poll()

        before = len(run.hits)
        try:
            for hit in adapters.harvest(run.id, outdir, run.found.repo, run.started):
                run.record(hit)
        except Exception as exc:
            run.log('# Report harvest failed: ' + str(exc))
        gained = len(run.hits) - before
        if gained > 0:
            run.log('# Recovered ' + str(gained) + ' result(s) from report files.')

        run.finished = time.time()
        if job.cancelled:
            run.status = 'cancelled'
        elif run.exit_code in (0, None) or run.hits:
            run.status = 'done'
            if run.exit_code not in (0, None):
                run.note = ('Exited with code ' + str(run.exit_code) +
                            ', but results were parsed.')
        else:
            run.status = 'failed'
            run.note = ('Exited with code ' + str(run.exit_code) +
                        ' and produced no parsable results.')
        job.pulse.set()

def start(target: str, tool_ids: list, opts: dict):
    """Create a job and launch one worker thread per selected scanner."""
    ok, kind = validate(target)
    if not ok:
        return None, kind
    target = target.strip()

    catalogue = {d.id: d for d in adapters.discover(SETTINGS.TOOLS_DIR)}
    runs = []
    for tid in tool_ids:
        found = catalogue.get(tid)
        if found is None:
            continue
        run = ToolRun(found)
        if not found.available:
            run.status = 'skipped'
            run.note = found.problem or 'Scanner not found on this machine.'
        elif kind not in found.accepts:
            run.status = 'skipped'
            run.note = found.label + ' does not accept ' + kind + ' targets.'
        runs.append(run)

    if not runs:
        return None, 'Select at least one scanner.'
    if not any(run.status == 'queued' for run in runs):
        article = 'an' if kind[0] in 'aeiou' else 'a'
        return None, ('None of the selected scanners can handle ' + article +
                      ' ' + kind + ' target on this machine. Open scanner '
                      'setup for details.')

    job = Job(target, kind, runs, opts)
    with LOCK:
        JOBS[job.id] = job
        while len(JOBS) > SETTINGS.MAX_JOBS:
            _, old = JOBS.popitem(last=False)
            cancel(old.id)

    gate = threading.Semaphore(max(1, int(opts.get('parallel', SETTINGS.DEFAULT_PARALLEL))))
    for run in runs:
        if run.status != 'queued':
            continue
        thread = threading.Thread(target=run_tool, args=(job, run, gate),
                                  daemon=True, name='scan-' + run.id)
        thread.start()

    return job, ''

def cancel(job_id: str) -> bool:
    job = JOBS.get(job_id)
    if job is None:
        return False
    job.cancelled = True
    for run in job.runs.values():
        adapters.kill_tree(run.proc)
        if not run.terminal:
            run.status = 'cancelled'
            run.finished = time.time()
    job.pulse.set()
    return True

# --------------------------------------------------------------------------
# the ledger
# --------------------------------------------------------------------------

def ledger(job: Job) -> list:
    """
    Merge per-scanner hits into one row per site, recording which scanners
    agree.

    Agreement is the point of running four scanners. A site claimed by three
    independent tools is a different kind of result from one claimed by a
    single tool with a loose matcher.
    """
    rows = {}
    with LOCK:
        for run in job.runs.values():
            for key, hit in run.hits.items():
                row = rows.get(key)
                if row is None:
                    row = rows[key] = {
                        'key': key,
                        'site': hit['site'],
                        'url': hit.get('url', ''),
                        'tools': [],
                    }
                if run.id not in row['tools']:
                    row['tools'].append(run.id)
                if not row['url'] and hit.get('url'):
                    row['url'] = hit['url']
                if hit['site'] and len(hit['site']) < len(row['site']):
                    row['site'] = hit['site']

    ordered = list(rows.values())
    ordered.sort(key=lambda r: (-len(r['tools']), r['site'].lower()))
    return ordered

def snapshot(job: Job, cursors: dict) -> dict:
    """Job state plus only the log lines the caller has not seen yet."""
    tools = []
    with LOCK:
        for run in job.runs.values():
            seen = int(cursors.get(run.id, 0))
            start_at = max(seen - run.dropped, 0)

            # Cap the batch, then advance the cursor only past what is sent.
            # Taking the tail would skip the middle of a burst.
            fresh = run.lines[start_at:start_at + 500]

            tools.append({
                'id': run.id,
                'label': run.label,
                'status': run.status,
                'note': run.note,
                'command': run.command,
                'exit': run.exit_code,
                'found': len(run.hits),
                'misses': run.misses,
                'blocked': run.blocked,
                'elapsed': round(run.elapsed, 1),
                'cursor': run.dropped + start_at + len(fresh),
                'lines': fresh,
                'pending': max(len(run.lines) - (start_at + len(fresh)), 0),
            })

    rows = ledger(job)
    return {
        'id': job.id,
        'target': job.target,
        'kind': job.kind,
        'status': job.status,
        'elapsed': round(job.elapsed, 1),
        'total': len(rows),
        'corroborated': sum(1 for r in rows if len(r['tools']) > 1),
        'tools': tools,
        'rows': rows,
    }

# --------------------------------------------------------------------------
# exports
# --------------------------------------------------------------------------

def export(job: Job, fmt: str) -> tuple:
    """Returns (filename, mimetype, text) for json, csv or markdown."""
    import csv
    import json

    rows = ledger(job)
    stamp = time.strftime('%Y%m%d-%H%M%S', time.localtime(job.created))
    safe_target = re.sub(r'[^A-Za-z0-9._@-]', '_', job.target)
    base = 'osint-' + safe_target + '-' + stamp

    if fmt == 'csv':
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator='\n')
        writer.writerow(['site', 'url', 'tools', 'tool_count'])
        for row in rows:
            writer.writerow([row['site'], row['url'],
                             ' '.join(row['tools']), len(row['tools'])])
        return base + '.csv', 'text/csv', buffer.getvalue()

    if fmt == 'md':
        out = ['# OSINT scan: ' + job.target, '']
        out.append('Run ' + time.strftime('%Y-%m-%d %H:%M:%S',
                                          time.localtime(job.created)) +
                   ' against a ' + job.kind + ' target.')
        out.append('')
        for run in job.runs.values():
            out.append('- ' + run.label + ': ' + run.status + ', ' +
                       str(len(run.hits)) + ' found in ' +
                       str(round(run.elapsed, 1)) + 's')
        out += ['', '## Results', '',
                '| Site | Confirmed by | URL |', '| --- | --- | --- |']
        for row in rows:
            out.append('| ' + row['site'].replace('|', '/') + ' | ' +
                       ', '.join(row['tools']) + ' | ' +
                       (row['url'] or '').replace('|', '%7C') + ' |')
        out += ['', 'Verify before acting on any result; username collisions '
                    'are common.']
        return base + '.md', 'text/markdown', '\n'.join(out)

    payload = {
        'target': job.target,
        'kind': job.kind,
        'started': time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(job.created)),
        'elapsed_seconds': round(job.elapsed, 1),
        'tools': [{
            'id': run.id,
            'status': run.status,
            'command': run.command,
            'exit_code': run.exit_code,
            'elapsed_seconds': round(run.elapsed, 1),
            'found': len(run.hits),
        } for run in job.runs.values()],
        'results': rows,
    }
    return (base + '.json', 'application/json',
            json.dumps(payload, indent=2, ensure_ascii=False, default=str))

def history() -> list:
    with LOCK:
        items = list(JOBS.values())
    items.reverse()
    return [{
        'id': job.id,
        'target': job.target,
        'kind': job.kind,
        'status': job.status,
        'when': time.strftime('%H:%M:%S', time.localtime(job.created)),
        'total': len(ledger(job)),
    } for job in items[:12]]

def diagnostics() -> dict:
    root = SETTINGS.TOOLS_DIR
    out = []
    for found in adapters.discover(root):
        entry = {
            'id': found.id,
            'label': found.label,
            'blurb': found.blurb,
            'accepts': list(found.accepts),
            'available': found.available,
            'repo': found.repo,
            'python': found.python,
            'how': found.how,
            'problem': found.problem,
            'flags': '',
        }
        if found.available:
            text = adapters.help_text(found)
            if text:
                flags = sorted(set(re.findall(r'(?<![\w-])--[a-z][a-z0-9-]+', text)))
                entry['flags'] = ' '.join(flags[:40])
            else:
                entry['problem'] = found.problem or 'The --help probe returned nothing.'
        out.append(entry)
    return {'root': str(root), 'tools': out}