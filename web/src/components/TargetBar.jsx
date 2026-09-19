import React from 'react';
import { HANDLE, kindOf, plural } from '@/constants.js';

/**
 * The input is the hero of the page, styled as a prompt line rather than a
 * boxed field. The hint below it answers one question at a time: what is
 * wrong, or what is about to happen.
 */
export default function TargetBar({
  target, onTarget, onRun, onStop, running, scanners, selected, children,
}) {
  const value = target.trim();
  const kind = kindOf(value);

  const usable = scanners.filter(
    (tool) => tool.available && selected.has(tool.id) && tool.accepts.includes(kind)
  ).length;

  let hint;
  let bad = false;

  if (!value) {
    hint = 'Sherlock and Maigret take usernames. Holehe takes emails. Blackbird takes both.';
  } else if (kind === 'username' && !HANDLE.test(value)) {
    hint = 'Usernames can use letters, digits, dot, underscore and hyphen. Include an @ for an email.';
    bad = true;
  } else if (usable === 0) {
    hint = `None of the selected scanners accept ${kind === 'email' ? 'an' : 'a'} ${kind} target.`;
    bad = true;
  } else {
    hint = `${usable} ${plural(usable, 'scanner', 'scanners')} will run against this ${kind}.`;
  }

  const blocked = !value || bad || running;

  return (
    <section className="command">
      <div className="prompt">
        <span className="prompt-sign">&#9656;</span>
        <input
          id="target"
          type="text"
          value={target}
          onChange={(event) => onTarget(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !blocked) onRun();
          }}
          placeholder="davidleonstr"
          autoComplete="off"
          autoCapitalize="off"
          spellCheck="false"
          aria-label="Username or email address to scan"
        />
        <span className="prompt-kind">{value ? kind : 'username or email'}</span>
      </div>

      <p className={bad ? 'prompt-hint bad' : 'prompt-hint'}>{hint}</p>

      {children}

      <div className="controls">
        {running ? (
          <button type="button" className="btn btn-stop" onClick={onStop}>
            Stop scan
          </button>
        ) : null}
        <button type="button" className="btn" onClick={onRun} disabled={blocked}>
          {running ? 'Scanning' : 'Run scan'}
        </button>
      </div>
    </section>
  );
}
