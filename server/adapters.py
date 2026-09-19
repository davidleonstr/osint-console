"""
Adapters for the four OSINT scanners.

Each scanner is a separate upstream project with its own CLI, and those CLIs
drift between releases. Rather than hardcode flags that may not exist in the
checkout on this machine, every tool is:

  1. discovered   - find the repo, pick an entry point, pick an interpreter
  2. probed       - run `--help` once, cache the text, read which flags exist
  3. invoked      - build an argv using only flags the probe confirmed
  4. parsed       - read stdout line by line into structured hits
  5. harvested    - after exit, scan any report files the tool wrote
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

IS_WINDOWS = os.name == 'nt'

ANSI = re.compile(r'\x1b\[[0-9;?]*[ -/]*[@-~]')
'Matches ANSI escape sequences, including the cursor/erase codes holehe emits.'

CTRL = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
'Remaining control characters that would corrupt the log pane.'

# `[+] Name : https://url`  /  `[+] Name: url`  /  `[+] name.com`
FOUND = re.compile(r'^\[\+\]\s*(?P<body>.+?)\s*$')
MISS = re.compile(r'^\[-\]\s*(?P<body>.+?)\s*$')
RATELIMITED = re.compile(r'^\[[x!]\]\s*(?P<body>.+?)\s*$')
'[x] is holehe rate-limiting, [!] is a blackbird error. [*] is progress noise.'
SPLIT = re.compile(r'\s*[:：]\s+|\s*[:：](?=https?://)')
URLISH = re.compile(r'https?://\S+')

def clean(line: str) -> str:
    """Strip colour codes and control characters from one line of tool output."""
    return CTRL.sub('', ANSI.sub('', line)).rstrip()

def domain(url: str) -> str:
    """Registrable-ish host for a URL, used when a tool reports no site name."""
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return ''
    host = host.split('@')[-1].split(':')[0]
    if host.startswith('www.'):
        host = host[4:]
    return host

def slug(name: str) -> str:
    """Normalised key so 'GitHub', 'github.com' and 'Github ' collapse together."""
    name = name.lower().strip()
    name = re.sub(r'^(www\.)', '', name)
    name = re.sub(r'\.(com|net|org|io|co|me|tv|fm|gg|app|dev)$', '', name)
    return re.sub(r'[^a-z0-9]+', '', name)

@dataclass
class ToolSpec:
    id: str
    label: str
    blurb: str
    accepts: tuple           # 'username' and/or 'email'
    dirnames: tuple          # candidate folder names under the scan root
    modules: tuple = ()      # python -m <module> candidates
    scripts: tuple = ()      # script paths relative to the repo folder
    console: str = ''        # console-script name to look for on PATH

SPECS = [
    ToolSpec(
        id='sherlock',
        label='Sherlock',
        blurb='Usernames across ~400 sites, by HTTP probe.',
        accepts=('username',),
        dirnames=('sherlock', 'sherlock-project'),
        modules=('sherlock_project', 'sherlock'),
        scripts=('sherlock/sherlock.py', 'sherlock.py'),
        console='sherlock',
    ),
    ToolSpec(
        id='maigret',
        label='Maigret',
        blurb='Usernames across ~3000 sites, plus profile parsing.',
        accepts=('username',),
        dirnames=('maigret',),
        modules=('maigret',),
        scripts=('maigret/__main__.py',),
        console='maigret',
    ),
    ToolSpec(
        id='holehe',
        label='Holehe',
        blurb='Whether an email is registered, via password-reset flows.',
        accepts=('email',),
        dirnames=('holehe',),
        modules=('holehe.core', 'holehe'),
        scripts=('holehe/core.py',),
        console='holehe',
    ),
    ToolSpec(
        id='blackbird',
        label='Blackbird',
        blurb='Usernames and emails, with metadata extraction.',
        accepts=('username', 'email'),
        dirnames=('blackbird',),
        modules=(),
        scripts=('blackbird.py',),
        console='blackbird',
    ),
]

BY_ID = {s.id: s for s in SPECS}

# --------------------------------------------------------------------------
# discovery
# --------------------------------------------------------------------------

def interpreter(repo: Path) -> str:
    """Prefer a virtualenv inside the repo; these tools pin conflicting deps."""
    names = ('.venv', 'venv', 'env')
    rel = 'Scripts/python.exe' if IS_WINDOWS else 'bin/python'
    for name in names:
        candidate = repo / name / rel
        if candidate.is_file():
            return str(candidate)
    return sys.executable

@dataclass
class Discovery:
    id: str
    label: str
    blurb: str
    accepts: tuple
    available: bool = False
    repo: str = ''
    python: str = ''
    argv: list = field(default_factory=list)
    cwd: str = ''
    how: str = ''
    problem: str = ''

def discover_one(spec: ToolSpec, root: Path) -> Discovery:
    found = Discovery(id=spec.id, label=spec.label, blurb=spec.blurb,
                      accepts=spec.accepts)

    repo = None
    for name in spec.dirnames:
        candidate = root / name
        if candidate.is_dir():
            repo = candidate
            break

    if repo is not None:
        found.repo = str(repo)
        py = interpreter(repo)
        found.python = py

        for module in spec.modules:
            probe = repo / (module.split('.')[0])
            if probe.is_dir():
                found.available = True
                found.argv = [py, '-u', '-m', module]
                found.cwd = str(repo)
                found.how = 'python -m ' + module
                return found

        for script in spec.scripts:
            probe = repo / script
            if probe.is_file():
                found.available = True
                found.argv = [py, '-u', str(probe)]
                found.cwd = str(repo)
                found.how = script
                return found

    # Installed into the environment rather than cloned.
    if spec.console:
        onpath = shutil.which(spec.console)
        if onpath:
            found.available = True
            found.argv = [onpath]
            found.cwd = str(repo or root)
            found.how = spec.console + ' (on PATH)'
            return found

    for module in spec.modules:
        try:
            import importlib.util
            if importlib.util.find_spec(module.split('.')[0]) is not None:
                found.available = True
                found.argv = [sys.executable, '-u', '-m', module]
                found.cwd = str(repo or root)
                found.python = sys.executable
                found.how = 'python -m ' + module + ' (installed)'
                return found
        except (ImportError, ValueError, ModuleNotFoundError):
            pass

    found.problem = (
        'No folder named ' + ' or '.join(spec.dirnames) + ' under the scan root, '
        'and nothing importable or on PATH.'
    )
    return found


def discover(root: Path) -> list:
    return [discover_one(spec, root) for spec in SPECS]

# --------------------------------------------------------------------------
# capability probe
# --------------------------------------------------------------------------

HELP_CACHE = {}
HELP_LOCK = threading.Lock()

def help_text(found: Discovery, timeout: int = 60) -> str:
    """Run `--help` once per argv and cache it. Returns '' if the probe fails."""
    key = tuple(found.argv)
    with HELP_LOCK:
        if key in HELP_CACHE:
            return HELP_CACHE[key]

    text = ''
    try:
        result = subprocess.run(
            list(found.argv) + ['--help'],
            cwd=found.cwd or None,
            capture_output=True,
            timeout=timeout,
            env=child_env(),
            **creation_flags(),
        )
        text = (result.stdout or b'').decode('utf-8', 'replace')
        text += (result.stderr or b'').decode('utf-8', 'replace')
    except Exception as exc:
        text = ''
        found.problem = 'Could not run --help: ' + str(exc)

    text = clean_block(text)
    with HELP_LOCK:
        HELP_CACHE[key] = text
    return text

def clean_block(text: str) -> str:
    return '\n'.join(clean(line) for line in text.splitlines())

def supports(help_txt: str, flag: str) -> bool:
    """True if `flag` appears in the help output as a real option token."""
    if not help_txt:
        return False
    return re.search(r'(?<![\w-])' + re.escape(flag) + r'(?![\w-])', help_txt) is not None

def first_supported(help_txt: str, *flags) -> str:
    for flag in flags:
        if supports(help_txt, flag):
            return flag
    return ''

# --------------------------------------------------------------------------
# argv construction
# --------------------------------------------------------------------------

def build_argv(found: Discovery, target: str, kind: str, opts: dict,
               outdir: Path) -> list:
    """
    Compose the full command. Only flags confirmed by the --help probe are
    added, so an older or newer checkout degrades to a plainer command instead
    of dying on an unrecognised argument.
    """
    help_txt = help_text(found)
    argv = list(found.argv)
    timeout = str(int(opts.get('site_timeout', 20)))

    if found.id == 'sherlock':
        argv.append(target)
        flag = first_supported(help_txt, '--no-color', '--nocolor')
        if flag:
            argv.append(flag)
        if supports(help_txt, '--print-found'):
            argv.append('--print-found')
        if supports(help_txt, '--timeout'):
            argv += ['--timeout', timeout]
        folder = first_supported(help_txt, '--folderoutput', '-fo')
        if folder:
            argv += [folder, str(outdir)]
        if opts.get('local_data') and supports(help_txt, '--local'):
            argv.append('--local')

    elif found.id == 'maigret':
        argv.append(target)
        flag = first_supported(help_txt, '--no-color', '--nocolor')
        if flag:
            argv.append(flag)
        if supports(help_txt, '--no-progressbar'):
            argv.append('--no-progressbar')
        if supports(help_txt, '--timeout'):
            argv += ['--timeout', timeout]
        top = int(opts.get('top_sites', 500))
        if top and supports(help_txt, '--top-sites'):
            argv += ['--top-sites', str(top)]
        elif supports(help_txt, '--all-sites'):
            argv.append('--all-sites')
        folder = first_supported(help_txt, '--folderoutput', '-fo')
        if folder:
            argv += [folder, str(outdir)]
        fmt = first_supported(help_txt, '--json')
        if fmt:
            argv += [fmt, 'simple']

    elif found.id == 'holehe':
        argv.append(target)
        flag = first_supported(help_txt, '--no-color', '--nocolor')
        if flag:
            argv.append(flag)
        flag = first_supported(help_txt, '--no-clear', '--noclear')
        if flag:
            argv.append(flag)
        flag = first_supported(help_txt, '--only-used', '--onlyused')
        if flag:
            argv.append(flag)
        flag = first_supported(help_txt, '--timeout', '-T')
        if flag:
            argv += [flag, timeout]

    elif found.id == 'blackbird':
        flag = first_supported(help_txt, '--email' if kind == 'email' else '--username',
                               '-e' if kind == 'email' else '-u')
        if flag:
            argv += [flag, target]
        else:
            argv.append(target)
        if supports(help_txt, '--no-nsfw'):
            argv.append('--no-nsfw')
        if supports(help_txt, '--no-update'):
            argv.append('--no-update')
        if supports(help_txt, '--timeout'):
            argv += ['--timeout', timeout]
        fmt = first_supported(help_txt, '--json')
        if fmt:
            argv.append(fmt)

    return argv

def child_env() -> dict:
    env = dict(os.environ)
    env['PYTHONUNBUFFERED'] = '1'
    env['PYTHONIOENCODING'] = 'utf-8'
    env['NO_COLOR'] = '1'
    env['TERM'] = 'dumb'
    env.pop('PYTHONSTARTUP', None)
    return env

def creation_flags() -> dict:
    """Put the child in its own group so the whole tree can be killed."""
    if IS_WINDOWS:
        return {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP}
    return {'start_new_session': True}

def kill_tree(proc) -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        if IS_WINDOWS:
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)],
                           capture_output=True, timeout=15)
        else:
            import signal
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except Exception:
        pass
    try:
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass

# --------------------------------------------------------------------------
# line parsing
# --------------------------------------------------------------------------

NOISE = re.compile(
    r'^\[\+\]\s*(checking|searching|target|username|email|total|found|'
    r'results?|report|saved|elapsed|extracted|time)\b',
    re.I,
)

SUMMARY = re.compile(
    r'^\d[\d,.]*\s+\S+\s',
    re.I,
)
"""
Matches tallies such as '4 websites found' that tools print with a [+] prefix.

Requires whitespace after the leading number, so genuine sites whose names
start with a digit - 9GAG, 500px, 4chan - are not swallowed.
"""

def parse_line(tool_id: str, line: str):
    """
    Turn one line of scanner output into a hit dict, or None.

    All four tools share the `[+] / [-] / [x]` convention, but differ in
    whether a URL follows. The shape is normalised here so the ledger can
    merge them.
    """
    line = clean(line).strip()
    if not line:
        return None

    match = FOUND.match(line)
    if match:
        body = match.group('body').strip()
        if NOISE.match(line) or not body:
            return None

        url = ''
        urls = URLISH.findall(body)
        if urls:
            url = urls[0].rstrip('.,);]')

        name = body
        if url:
            name = SPLIT.split(body)[0].strip()
            name = name.replace(url, '').strip(' :-—')
        if not name and url:
            name = domain(url)
        if not name:
            return None
        if len(name) > 80:
            return None
        if not url and SUMMARY.match(name):
            return None

        return {
            'tool': tool_id,
            'site': name,
            'key': slug(name) or slug(domain(url)),
            'url': url,
            'state': 'found',
            'raw': line,
        }

    match = RATELIMITED.match(line)
    if match:
        body = match.group('body').strip()
        if not body or len(body) > 80:
            return None
        return {
            'tool': tool_id,
            'site': body.split(':')[0].strip(),
            'key': slug(body.split(':')[0]),
            'url': '',
            'state': 'blocked',
            'raw': line,
        }

    if MISS.match(line):
        return {'tool': tool_id, 'state': 'miss'}

    return None

# --------------------------------------------------------------------------
# report harvesting
# --------------------------------------------------------------------------

URL_KEYS = ('url_user', 'url', 'link', 'profile_url', 'href')
NAME_KEYS = ('name', 'site', 'site_name', 'sitename', 'title', 'app')

def walk_json(node, out, depth=0, hint=''):
    """
    Recursively pull {name, url} pairs out of an arbitrary report structure.

    `hint` carries the key a dict was stored under. Maigret's simple report is
    shaped {'sites': {'HackerNews': {...}}}, so the site name lives in the key
    rather than in a field, and without the hint those rows degrade to a bare
    hostname.
    """
    if depth > 12 or len(out) > 3000:
        return
    if isinstance(node, dict):
        url = ''
        for key in URL_KEYS:
            value = node.get(key)
            if isinstance(value, str) and value.startswith('http'):
                url = value
                break
        if url:
            name = ''
            for key in NAME_KEYS:
                value = node.get(key)
                if isinstance(value, str) and value and len(value) < 80:
                    name = value
                    break
            if not name and hint and len(hint) < 80:
                name = hint
            status = node.get('status')
            claimed = True
            if isinstance(status, dict):
                text = str(status.get('status', '')).lower()
                claimed = text in ('claimed', 'found', '') or 'claim' in text
            elif isinstance(status, str):
                claimed = status.lower() in ('claimed', 'found', 'ok', 'true')
            if claimed:
                out.append((name or domain(url), url))
        for key, value in node.items():
            if isinstance(value, (dict, list)):
                child = key if isinstance(key, str) else ''
                if child.lower() in ('sites', 'results', 'data', 'items', 'accounts'):
                    child = ''
                walk_json(value, out, depth + 1, child)
    elif isinstance(node, list):
        for item in node:
            walk_json(item, out, depth + 1, hint)

def harvest(tool_id: str, outdir: Path, repo: str, since: float) -> list:
    """
    Read structured reports the tool left behind. This is a safety net: if the
    stdout format changed and parse_line missed everything, the report files
    usually still carry the results.
    """
    hits = []
    seen = set()
    roots = [outdir]
    if repo:
        for extra in ('results', 'reports', 'output'):
            candidate = Path(repo) / extra
            if candidate.is_dir():
                roots.append(candidate)

    for base in roots:
        try:
            files = sorted(base.rglob('*'))[:400]
        except OSError:
            continue
        for path in files:
            try:
                if not path.is_file() or path.stat().st_mtime < since - 2:
                    continue
                if path.stat().st_size > 12_000_000:
                    continue
            except OSError:
                continue

            pairs = []
            try:
                if path.suffix.lower() == '.json':
                    data = json.loads(path.read_text('utf-8', errors='replace'))
                    walk_json(data, pairs)
                elif path.suffix.lower() in ('.txt', '.csv'):
                    text = path.read_text('utf-8', errors='replace')
                    for url in URLISH.findall(text)[:2000]:
                        url = url.rstrip('".,);]')
                        pairs.append((domain(url), url))
            except Exception:
                continue

            for name, url in pairs:
                key = slug(name) or slug(domain(url))
                if not key or key in seen:
                    continue
                seen.add(key)
                hits.append({
                    'tool': tool_id,
                    'site': name,
                    'key': key,
                    'url': url,
                    'state': 'found',
                    'raw': 'report: ' + path.name,
                })
    return hits
