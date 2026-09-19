import React from 'react';
import { plural } from '@/constants.js';

export default function Summary({ state }) {
  if (!state) return null;

  const verb = state.status === 'running' ? 'scanning' : state.status;

  return (
    <div className="summary">
      <span className="summary-count">
        {state.total}
        <small>{plural(state.total, 'account', 'accounts')} found</small>
      </span>

      {state.corroborated > 0 ? (
        <span className="summary-note">
          <b>{state.corroborated}</b> confirmed by more than one scanner
        </span>
      ) : state.total > 0 ? (
        <span className="summary-note">no site was confirmed by two scanners yet</span>
      ) : null}

      <span className="summary-clock">
        {verb} {state.target}, {state.elapsed}s
      </span>
    </div>
  );
}
