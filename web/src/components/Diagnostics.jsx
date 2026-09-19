import React from 'react';

/**
 * What discovery and the --help probe found. This is the first place to look
 * when a scanner is missing or a command comes out wrong, so it shows the
 * resolved folder, entry point, interpreter and detected flags.
 */
export default function Diagnostics({ diag }) {
  if (!diag) return null;
  const ready = diag.tools.filter((tool) => tool.available).length;

  return (
    <details className="diag">
      <summary>
        <span>Scanner setup</span>
        <span className="diag-summary-tally">
          {ready} of {diag.tools.length} scanners ready
        </span>
      </summary>

      <p className="diag-root">
        Scanner folders are read from <code>{diag.root}</code>. Set the <code>TOOLS_DIR</code>{' '}
        environment variable to look elsewhere.
      </p>

      <div className="diag-grid">
        {diag.tools.map((tool) => (
          <div key={tool.id} className={tool.available ? 'diag-row diag-ready' : 'diag-row diag-missing'}>
            <div className="diag-head">
              <span className="diag-name">{tool.label}</span>
              <span className="diag-verdict">{tool.available ? 'Ready' : 'Missing'}</span>
            </div>
            <dl className="diag-facts">
              <dt>Folder</dt>
              <dd>{tool.repo || 'no folder found'}</dd>
              <dt>Entry</dt>
              <dd>{tool.how || 'unavailable'}</dd>
              <dt>Interpreter</dt>
              <dd>{tool.python || 'not resolved'}</dd>
              <dt>Flags read from help</dt>
              <dd className="diag-flags">{tool.flags || 'none detected'}</dd>
            </dl>
            {tool.problem ? <p className="diag-problem">{tool.problem}</p> : null}
          </div>
        ))}
      </div>
    </details>
  );
}
