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

/** Escape HTML to prevent XSS */
export function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

/** Detect file URLs in a string or data object */
export function extractFileUrls(message, data) {
  const urls = [];
  const urlRegex = /https?:\/\/[^\s"'<>]+/gi;

  if (typeof message === 'string') {
    const matches = message.match(urlRegex);
    if (matches) urls.push(...matches);
  }

  if (data) {
    const dataStr = JSON.stringify(data);
    const matches = dataStr.match(urlRegex);
    if (matches) urls.push(...matches);

    // Check common file fields
    for (const key of ['file', 'file_url', 'download_url', 'path', 'attachment']) {
      if (data[key] && typeof data[key] === 'string') {
        urls.push(data[key]);
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
