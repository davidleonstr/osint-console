import React, { useMemo, useState } from 'react';
import { ORDER } from '@/constants.js';

/**
 * The agreement matrix: four fixed columns, one per scanner, filled where
 * that scanner claimed the site. Agreement reads as a vertical pattern down
 * the page instead of as text, which is the one thing worth seeing at a
 * glance when four tools disagree constantly.
 */
function Matrix({ tools }) {
  return (
    <div className="matrix" role="img" aria-label={`Claimed by ${tools.join(', ') || 'nothing'}`}>
      {ORDER.map((id) => {
        const on = tools.includes(id);
        return <i key={id} className={`m-${id}${on ? ' on' : ''}`} title={`${id}: ${on ? 'claimed' : 'no result'}`} />;
      })}
    </div>
  );
}

export default function Ledger({ state, running }) {
  const [needle, setNeedle] = useState('');
  const [agreedOnly, setAgreedOnly] = useState(false);

  const all = state?.rows ?? [];

  const rows = useMemo(() => {
    const query = needle.trim().toLowerCase();
    return all.filter((row) => {
      if (agreedOnly && row.tools.length < 2) return false;
      if (!query) return true;
      return `${row.site} ${row.url}`.toLowerCase().includes(query);
    });
  }, [all, needle, agreedOnly]);

  let blank = null;
  if (!rows.length) {
    if (!state) {
      blank = {
        title: 'No scan running.',
        body: 'Enter a username or an email address above. Results fill in here as each scanner reports.',
      };
    } else if (all.length) {
      blank = { title: 'No result matches this filter.', body: `Clear it to see all ${all.length} results.` };
    } else if (running) {
      blank = { title: 'Waiting for the first confirmed account.', body: 'Scanners report as they go.' };
    } else {
      blank = {
        title: 'Nothing was found for this target.',
        body: 'Scanners disagree often. A blank ledger is a real answer, not a failure.',
      };
    }
  }

  return (
    <section>
      <div className="panel-head">
        <h2>Agreement ledger</h2>
        <p>One row per site. A filled square means that scanner claimed it.</p>
      </div>

      <div className="ledger-tools">
        <input
          type="search"
          value={needle}
          onChange={(event) => setNeedle(event.target.value)}
          placeholder="filter by site or URL"
          aria-label="Filter results"
        />
        <label className="toggle">
          <input
            type="checkbox"
            checked={agreedOnly}
            onChange={(event) => setAgreedOnly(event.target.checked)}
          />
          two or more scanners
        </label>
      </div>

      <div className="legend">
        {ORDER.map((id) => (
          <span key={id}>
            <i style={{ background: `var(--${id})` }} />
            {id}
          </span>
        ))}
      </div>

      <div className="ledger">
        {blank ? (
          <div className="blank">
            <b>{blank.title}</b>
            {blank.body}
          </div>
        ) : (
          rows.map((row) => (
            <div key={row.key} className={row.tools.length > 1 ? 'row agreed' : 'row'}>
              <div className="row-site">
                <span className="row-name">{row.site}</span>
                {row.url ? (
                  <a className="row-url" href={row.url} target="_blank" rel="noopener noreferrer nofollow">
                    {row.url}
                  </a>
                ) : (
                  <span className="row-none">no direct link reported</span>
                )}
              </div>
              <Matrix tools={row.tools} />
            </div>
          ))
        )}
      </div>
    </section>
  );
}
