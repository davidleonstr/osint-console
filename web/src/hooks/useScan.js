import { useCallback, useEffect, useRef, useState } from 'react';
import { streamUrl } from '@/api.js';

/**
 * Subscribes to one scan's event stream.
 *
 * The server sends a `state` event whenever a worker writes output, carrying
 * the full ledger plus only the log lines not yet sent on this connection.
 * Log lines are therefore accumulated here rather than replaced, while
 * everything else is last-write-wins.
 *
 * EventSource reconnects on its own after a dropped connection. Because the
 * server tracks cursors per connection, a reconnect replays the log from the
 * beginning, so buffers are reset when a stream opens to avoid duplicates.
 */
export function useScan(jobId) {
  const [state, setState] = useState(null);
  const [logs, setLogs] = useState({});
  const [error, setError] = useState('');
  const [live, setLive] = useState(false);

  const sourceRef = useRef(null);

  useEffect(() => {
    if (!jobId) {
      setState(null);
      setLogs({});
      setError('');
      setLive(false);
      return undefined;
    }

    const source = new EventSource(streamUrl(jobId));
    sourceRef.current = source;
    setError('');
    setLive(true);

    // A fresh connection replays from line zero, so start from empty.
    setLogs({});

    source.addEventListener('state', (event) => {
      let data;
      try {
        data = JSON.parse(event.data);
      } catch {
        return;
      }

      setState(data);
      setLogs((previous) => {
        let changed = false;
        const next = { ...previous };
        for (const tool of data.tools) {
          if (!tool.lines?.length) continue;
          const existing = next[tool.id] || [];
          next[tool.id] = existing.concat(tool.lines).slice(-6000);
          changed = true;
        }
        return changed ? next : previous;
      });
    });

    source.addEventListener('end', () => {
      setLive(false);
      source.close();
    });

    source.onerror = () => {
      // EventSource retries by itself while the readyState is CONNECTING.
      // Only a closed stream is a real failure worth reporting.
      if (source.readyState === EventSource.CLOSED) {
        setLive(false);
        setError('Lost contact with the scan stream.');
      }
    };

    return () => {
      source.close();
      sourceRef.current = null;
      setLive(false);
    };
  }, [jobId]);

  const disconnect = useCallback(() => {
    sourceRef.current?.close();
    setLive(false);
  }, []);

  return { state, logs, error, live, disconnect };
}
