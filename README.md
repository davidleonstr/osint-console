<div align="center">
  <img src="web/public/favicon.svg" alt="Icon" width="180"/>
  <br/>
  
  <h3>OSINT Web Tool</h3>

  [![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
  [![React 18+](https://img.shields.io/badge/react-18+-61DAFB.svg?logo=react&logoColor=black)](https://react.dev/)
  [![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
</div>


# OSINT console

Flask and React rebuild. Drives Blackbird, Holehe, Maigret and Sherlock
against one target and merges what they report into a single ledger, keyed by
site and annotated with which scanners agreed.

## Layout it expects

```
./
  osint-console/        <- this folder
    server/
      tools/
         blackbird/
         holehe/
         maigret/
         sherlock/
    web/
```

## Running it

Backend:

```powershell
cd osint-console\server
pip install -r requirements.txt
python api.py --port 8420
```

Frontend, in a second terminal. During development Vite serves on 5173 and
proxies `/api` to Flask, so hot reload works:

```powershell
cd osint-console\web
npm install
npm run dev
```

Open `http://localhost:5173`.

For a single-origin setup, build once and let Flask serve the result:

```powershell
cd osint-console\web
npm run build
```

Then only `python app.py` is needed, on `http://localhost:8420`.

The **Scanner setup** drawer shows which scanners were found, which
interpreter each will run under, and which flags were read from its `--help`.
Start there if something is missing.

## API

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/api/scanners` | Discovery plus the cached `--help` probe |
| GET | `/api/scans` | Recent jobs |
| POST | `/api/scans` | Start a scan, returns its id |
| GET | `/api/scans/<id>` | One snapshot, optional `c_<tool>` cursors |
| GET | `/api/scans/<id>/stream` | Server-Sent Events, live |
| POST | `/api/scans/<id>/cancel` | Stop a running scan |
| GET | `/api/scans/<id>/export?format=` | Download `json`, `csv` or `md` |

## How a scan works

1. **Discovery.** Find each repo, pick an entry point (`python -m sherlock_project`,
   `blackbird.py`, a console script on PATH), pick an interpreter. A
   virtualenv inside a scanner's folder is preferred, which keeps their
   conflicting dependencies apart.
2. **Probe.** Run `--help` once per scanner and cache it. Flags are only added
   to a command if they appear in that output, so an older or newer checkout
   degrades to a plainer command instead of dying on an unrecognised argument.
3. **Run.** One background thread per scanner, output read line by line. A
   semaphore caps how many run at once.
4. **Parse.** All four use the `[+] / [-] / [x]` convention; the differences
   are in whether a URL follows and how the site is named.
5. **Harvest.** After exit, any report files written are read as a safety net.
   If an upstream output format changes and parsing misses everything, the
   JSON, CSV and text reports usually still carry the results.
6. **Merge.** Sites are keyed on a normalised slug, so `GitHub`, `github.com`
   and `www.github.com` collapse to one row carrying every scanner that
   claimed it.

## The live channel

The browser opens one `EventSource` against `/api/scans/<id>/stream`. The
server holds the request open and writes a `state` event whenever a worker
appends output, waking on a `threading.Event` rather than a fixed interval.
Each event carries the full ledger plus only the log lines not yet sent on
that connection.

Cursors are tracked per connection, so a dropped stream replays the log from
the start when `EventSource` reconnects. The hook resets its buffers whenever
a stream opens, which keeps that replay from duplicating lines.

`app.run(threaded=True)` is required. A held-open stream would otherwise
occupy the only worker and block every other request.