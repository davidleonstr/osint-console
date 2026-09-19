import React from 'react';
import { exportUrl } from '@/api.js';

/**
 * Exports and recent scans. Export links are plain anchors: Flask sets
 * Content-Disposition and the correct mimetype, so the browser saves the file
 * without any blob assembly on this side.
 */
export default function Sidebar({ jobId, total, history, onOpen }) {
  return (
    <div className="after">
      <section>
        <div className="panel-head">
          <h2>Save these results</h2>
          <p>Built from the ledger, not from raw output.</p>
        </div>
        {jobId && total > 0 ? (
          <div className="exports">
            <a className="btn btn-quiet" href={exportUrl(jobId, 'json')} download>
              Download JSON
            </a>
            <a className="btn btn-quiet" href={exportUrl(jobId, 'csv')} download>
              Download CSV
            </a>
            <a className="btn btn-quiet" href={exportUrl(jobId, 'md')} download>
              Download Markdown
            </a>
          </div>
        ) : (
          <p className="past-empty">Exports appear once a scan has results.</p>
        )}
      </section>

      <section>
        <div className="panel-head">
          <h2>Earlier scans</h2>
          <p>Kept in memory while the server runs.</p>
        </div>
        {history.length ? (
          <ul className="past-list">
            {history.map((item) => (
              <li key={item.id} className="past-item">
                <button type="button" className="past-link" onClick={() => onOpen(item.id)}>
                  <span className="past-target">{item.target}</span>
                  <span className="past-meta">
                    {item.when}, {item.total} found, {item.status}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="past-empty">Scans you run stay listed here until the server restarts.</p>
        )}
      </section>
    </div>
  );
}
