/**
 * ARC Controller — Status Badge Component
 */

export function renderStatusBadge(status) {
  const el = document.createElement('span');
  el.className = `status-badge status-badge--${status}`;

  const labels = {
    waiting: 'Waiting',
    running: 'Running',
    completed: 'Completed',
    failed: 'Failed',
    needs_confirmation: 'Awaiting Input',
  };

  el.innerHTML = `<span class="status-badge__dot"></span><span>${labels[status] || status}</span>`;
  return el;
}
