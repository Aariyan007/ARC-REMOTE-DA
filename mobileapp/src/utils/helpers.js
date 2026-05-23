/**
 * ARC Controller — Helper utilities
 */

/** Generate a UUID v4 */
export function uuid() {
  return crypto.randomUUID?.() ??
    'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
      const r = Math.random() * 16 | 0;
      return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
    });
}

/** Format a Unix timestamp to relative time string */
export function timeAgo(timestamp) {
  const now = Date.now() / 1000;
  const diff = Math.max(0, now - timestamp);
  if (diff < 5) return 'just now';
  if (diff < 60) return `${Math.floor(diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return new Date(timestamp * 1000).toLocaleDateString();
}

/** Format timestamp to HH:MM:SS */
export function formatTime(timestamp) {
  return new Date(timestamp * 1000).toLocaleTimeString([], {
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
}

/** Escape HTML to prevent XSS.
 * BUG-O FIX: replaced live-DOM approach (div.textContent/innerHTML) with a
 * character-map regex. The old version created a DOM element on every call —
 * in EventTimeline.render() this fired 20-50 times per state change.
 */
const _ESC_MAP = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
export function escapeHtml(str) {
  return String(str ?? '').replace(/[&<>"']/g, c => _ESC_MAP[c]);
}

/** Detect file URLs in a string or data object.
 * BUG-D FIX: removed JSON.stringify(data) scan. Scanning the full serialised
 * blob caused the same URL to appear twice — once from the string scan and once
 * from the JSON string — producing duplicate download buttons even after Set
 * deduplication (because the URL matched in two different passes).
 * Now only known top-level fields are checked.
 */
export function extractFileUrls(message, data) {
  const urls = [];
  const urlRegex = /https?:\/\/[^\s"'<>]+/gi;

  if (typeof message === 'string') {
    const matches = message.match(urlRegex);
    if (matches) urls.push(...matches);
  }

  if (data) {
    // Only scan known file-bearing fields — do NOT JSON.stringify the whole object
    for (const key of ['file', 'file_url', 'download_url', 'attachment']) {
      const val = data[key];
      if (val && typeof val === 'string' && /^https?:\/\//.test(val)) {
        urls.push(val);
      }
    }
  }

  return [...new Set(urls)];
}

/** Truncate string with ellipsis */
export function truncate(str, len = 80) {
  if (!str || str.length <= len) return str;
  return str.slice(0, len) + '…';
}

/** Debounce a function */
export function debounce(fn, ms) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}
