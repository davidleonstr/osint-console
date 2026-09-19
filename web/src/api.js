// Thin wrapper over the Flask API. Every call throws an Error carrying the
// server's message, so components can surface it without unwrapping shapes.

async function unwrap(res) {
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    throw new Error(`Unexpected response from the server: ${text.slice(0, 120)}`);
  }
  if (!res.ok) throw new Error(data?.error || `Request failed (${res.status})`);
  return data;
}

export const getScanners = () => fetch('/api/scanners').then(unwrap);

export const getHistory = () => fetch('/api/scans').then(unwrap);

export const startScan = (body) =>
  fetch('/api/scans', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then(unwrap);

export const cancelScan = (id) =>
  fetch(`/api/scans/${encodeURIComponent(id)}/cancel`, { method: 'POST' }).then(unwrap);

// Exports arrive with Content-Disposition set, so the browser can save them
// directly. No JSON envelope, no blob reassembly.
export const exportUrl = (id, format) =>
  `/api/scans/${encodeURIComponent(id)}/export?format=${format}`;

export const streamUrl = (id) => `/api/scans/${encodeURIComponent(id)}/stream`;
