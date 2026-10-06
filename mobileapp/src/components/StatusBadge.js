/**
 * ARC Controller — Status Badge Component
 */

export function renderStatusBadge(status) {
  const el = document.createElement('span');
  el.className = `status-badge status-badge--${String(status).replace(/[^a-z_]/g, '')}`;

  const labels = {
    waiting: 'Waiting',
    running: 'Running',
    completed: 'Completed',
    failed: 'Failed',
    needs_confirmation: 'Awaiting Input',
  };

  const dot = document.createElement('span');
  dot.className = 'status-badge__dot';
  const text = document.createElement('span');
  text.textContent = labels[status] || String(status);
  el.append(dot, text);
  return el;
}
