import React from 'react';

/**
 * The scanner selector. Each chip reflects three things at once: whether the
 * scanner exists on this machine, whether it accepts the target currently
 * typed, and whether it is selected.
 */
export default function ScannerChips({ scanners, selected, onToggle, kind, hasTarget }) {
  return (
    <div className="chips">
      {scanners.map((tool) => {
        const fits = !hasTarget || tool.accepts.includes(kind);
        const usable = tool.available;
        const checked = usable && selected.has(tool.id);

        return (
          <label
            key={tool.id}
            className={[
              'chip',
              `chip-${tool.id}`,
              usable ? 'chip-ready' : 'chip-missing',
              fits ? '' : 'chip-unfit',
            ].join(' ')}
          >
            <input
              type="checkbox"
              checked={checked}
              disabled={!usable}
              onChange={() => onToggle(tool.id)}
            />
            <span className="chip-body">
              <span className="chip-name">{tool.label}</span>
              <span className="chip-blurb">{tool.blurb}</span>
              <span className="chip-state">
                {usable ? `Accepts ${tool.accepts.join(' and ')}` : 'Not found on this machine'}
              </span>
            </span>
          </label>
        );
      })}
    </div>
  );
}
