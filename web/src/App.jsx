import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { cancelScan, getHistory, getScanners, startScan } from './api.js';
import { kindOf } from './constants.js';
import { useScan } from './hooks/useScan.js';
import Diagnostics from './components/Diagnostics.jsx';
import Ledger from './components/Ledger.jsx';
import LogPanel from './components/LogPanel.jsx';
import ScannerChips from './components/ScannerChips.jsx';
import Sidebar from './components/Sidebar.jsx';
import Summary from './components/Summary.jsx';
import TargetBar from './components/TargetBar.jsx';

const STORED = 'osint.scanners';

function Toast({ message, onDismiss }) {
  useEffect(() => {
    if (!message) return undefined;
    const timer = setTimeout(onDismiss, 8000);
    return () => clearTimeout(timer);
  }, [message, onDismiss]);

  if (!message) return null;
  return (
    <div className="toast" role="alert" onClick={onDismiss}>
      {message}
    </div>
  );
}

// Full-page loader for the initial scanner probe. Shown until we hear back
// from the server (or it fails), since there's nothing useful to render
// before that — no chips, no options, no target bar worth typing into.
function BootScreen({ problem }) {
  return (
    <div className="boot" role="status" aria-live="polite">
      <div className="boot-mark">
        osint<b>/</b>console
      </div>
      {problem ? (
        <p className="boot-line boot-line-bad">{problem}</p>
      ) : (
        <>
          <div className="boot-spinner" aria-hidden="true" />
          <p className="boot-line">
            Probing scanners on the server<span className="boot-dots" aria-hidden="true" />
          </p>
          <p className="boot-sub">Sherlock, Maigret, Holehe and Blackbird each run a --help check on cold start.</p>
        </>
      )}
    </div>
  );
}

export default function App() {
  const [diag, setDiag] = useState(null);
  const [booting, setBooting] = useState(true);
  const [selected, setSelected] = useState(new Set());
  const [target, setTarget] = useState('');
  const [jobId, setJobId] = useState(null);
  const [history, setHistory] = useState([]);
  const [problem, setProblem] = useState('');
  const [starting, setStarting] = useState(false);
  const [opts, setOpts] = useState({ parallel: 2, timeout: 20, top: 500 });

  const { state, logs, error, live } = useScan(jobId);
  const running = live && state?.status === 'running';

  // Load the scanner catalogue once. The first call runs a --help probe per
  // scanner on the server, so it can take a moment on a cold start.
  useEffect(() => {
    getScanners()
      .then((data) => {
        setDiag(data);
        const remembered = localStorage.getItem(STORED);
        const available = data.tools.filter((tool) => tool.available).map((tool) => tool.id);
        const initial = remembered ? JSON.parse(remembered).filter((id) => available.includes(id)) : available;
        setSelected(new Set(initial.length ? initial : available));
      })
      .catch((err) => setProblem(err.message))
      .finally(() => setBooting(false));
  }, []);

  const refreshHistory = useCallback(() => {
    getHistory()
      .then((data) => setHistory(data.scans))
      .catch(() => {});
  }, []);

  useEffect(refreshHistory, [refreshHistory]);

  // Refresh the list once a scan settles, so its row shows a final count.
  useEffect(() => {
    if (state && state.status !== 'running') refreshHistory();
  }, [state?.status, refreshHistory]);

  const toggle = useCallback((id) => {
    setSelected((previous) => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      localStorage.setItem(STORED, JSON.stringify([...next]));
      return next;
    });
  }, []);

  const run = useCallback(async () => {
    try {
      setProblem('');
      setStarting(true);
      const { id } = await startScan({
        target: target.trim(),
        tools: [...selected],
        ...opts,
      });
      setJobId(id);
      refreshHistory();
    } catch (err) {
      setProblem(err.message);
    } finally {
      setStarting(false);
    }
  }, [target, selected, opts, refreshHistory]);

  const stop = useCallback(async () => {
    if (!jobId) return;
    try {
      await cancelScan(jobId);
    } catch (err) {
      setProblem(err.message);
    }
  }, [jobId]);

  const open = useCallback((id) => {
    setJobId(id);
  }, []);

  const scanners = diag?.tools ?? [];
  const kind = useMemo(() => kindOf(target), [target]);

  if (booting) {
    return <BootScreen problem={problem} />;
  }

  return (
    <div className="shell">
      <header className="masthead">
        <div>
          <div className="wordmark">
            osint<b>/</b>console
          </div>
          <p>
            Four account scanners, one target, one ledger. Sherlock, Maigret, Holehe and Blackbird run
            as separate processes and their results are merged by site.
          </p>
        </div>
        <p>Flask on. Nothing leaves this machine except the scanners&apos; own requests.</p>
      </header>

      <TargetBar
        target={target}
        onTarget={setTarget}
        onRun={run}
        onStop={stop}
        running={running}
        starting={starting}
        scanners={scanners}
        selected={selected}
      >
        <ScannerChips
          scanners={scanners}
          selected={selected}
          onToggle={toggle}
          kind={kind}
          hasTarget={Boolean(target.trim())}
        />

        <div className="options">
          <div className="field">
            <label htmlFor="parallel">Scanners at once</label>
            <select
              id="parallel"
              value={opts.parallel}
              onChange={(event) => setOpts({ ...opts, parallel: Number(event.target.value) })}
            >
              {[1, 2, 3, 4].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label htmlFor="timeout">Per-site timeout</label>
            <select
              id="timeout"
              value={opts.timeout}
              onChange={(event) => setOpts({ ...opts, timeout: Number(event.target.value) })}
            >
              <option value={10}>10s</option>
              <option value={20}>20s</option>
              <option value={45}>45s</option>
            </select>
          </div>

          <div className="field">
            <label htmlFor="top">Maigret site count</label>
            <select
              id="top"
              value={opts.top}
              onChange={(event) => setOpts({ ...opts, top: Number(event.target.value) })}
            >
              <option value={150}>150</option>
              <option value={500}>500</option>
              <option value={1500}>1500</option>
              <option value={0}>all</option>
            </select>
          </div>
        </div>
      </TargetBar>

      <Summary state={state} />

      <div className="work">
        <Ledger state={state} running={running} />
        <LogPanel state={state} logs={logs} />
      </div>

      <Sidebar jobId={jobId} total={state?.total ?? 0} history={history} onOpen={open} />

      <Diagnostics diag={diag} />

      <footer className="foot">
        <p>
          Each scanner decides on its own what counts as a hit, and they disagree constantly. A
          username that resolves on a site does not mean the same person owns it, and a site listed
          by one scanner alone is worth checking by hand before you rely on it. That is why the
          ledger shows who agreed rather than a single merged list.
        </p>
        <p>
          Run this against accounts you own or are authorised to assess. Some scanners probe
          password-reset endpoints, which is visible to the site being queried and may be rate
          limited or logged.
        </p>
      </footer>

      <Toast message={problem || error} onDismiss={() => setProblem('')} />
    </div>
  );
}