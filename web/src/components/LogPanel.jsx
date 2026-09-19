import React, { useEffect, useRef, useState } from 'react';

function classify(line) {
  if (line.startsWith('[+]')) return 'hit';
  if (line.startsWith('$ ') || line.startsWith('# ')) return 'cmd';
  if (/error|traceback|refused|failed/i.test(line)) return 'bad';
  return '';
}

/**
 * Raw scanner output, one tab per scanner. Lines are rendered as text nodes,
 * never as markup, because scanner output contains whatever a remote site
 * chose to put in a page title.
 */
export default function LogPanel({ state, logs }) {
  const [active, setActive] = useState(null);
  const boxRef = useRef(null);
  const pinned = useRef(true);

  const tools = state?.tools ?? [];

  // Default to the first scanner that actually ran.
  useEffect(() => {
    if (active && tools.some((tool) => tool.id === active)) return;
    const first = tools.find((tool) => tool.status !== 'skipped') || tools[0];
    if (first) setActive(first.id);
  }, [tools, active]);

  const lines = (active && logs[active]) || [];
  const current = tools.find((tool) => tool.id === active);

  // Follow the tail only while the reader is already at the bottom, so
  // scrolling back to inspect something is not yanked away.
  useEffect(() => {
    const box = boxRef.current;
    if (box && pinned.current) box.scrollTop = box.scrollHeight;
  }, [lines.length, active]);

  const onScroll = () => {
    const box = boxRef.current;
    if (!box) return;
    pinned.current = box.scrollHeight - box.scrollTop - box.clientHeight < 40;
  };

  const note = current?.note || current?.command || '';

  return (
    <section>
      <div className="panel-head">
        <h2>Live output</h2>
        <p>Exactly what each scanner printed.</p>
      </div>

      <div className="stream">
        <div className="tabs" role="tablist">
          {tools.map((tool) => (
            <button
              key={tool.id}
              type="button"
              role="tab"
              className="tab"
              data-tool={tool.id}
              aria-selected={active === tool.id}
              onClick={() => {
                pinned.current = true;
                setActive(tool.id);
              }}
            >
              <span>
                <i className={`tab-dot ${tool.status}`} />
                {tool.label}
              </span>
              <span className="tab-tally">
                {tool.status === 'skipped' ? 'skipped' : `${tool.found} found, ${tool.elapsed}s`}
              </span>
            </button>
          ))}
          {tools.length === 0 ? <div className="tabs-empty">No scan running</div> : null}
        </div>

        {note ? (
          <div className={current?.status === 'failed' ? 'stream-note bad' : 'stream-note'}>{note}</div>
        ) : null}

        <div className="log" ref={boxRef} onScroll={onScroll} role="log" aria-live="polite">
          {lines.length ? (
            lines.map((line, index) => (
              <div key={index} className={classify(line)}>
                {line}
              </div>
            ))
          ) : (
            <div className="log-empty">
              {tools.length ? "Nothing on this scanner's output yet." : 'Scanner output appears here once a scan starts.'}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
