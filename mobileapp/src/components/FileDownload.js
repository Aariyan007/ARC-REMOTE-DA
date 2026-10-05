/**
 * ARC Controller — File Download Component
 */
import appState from '../state/appState.js';
import { apiBase } from '../utils/config.js';

function sameServer(url) {
  try {
    return new URL(url).origin === new URL(apiBase() || location.origin).origin;
  } catch {
    return false;
  }
}

/**
 * Render a download button for a file URL.
 * Links to this ARC server are fetched with the bearer token; links to any other
 * host are opened as plain links and never receive the token.
 * @param {string} url - The file URL
 */
export function renderFileDownload(url) {
  const el = document.createElement('a');
  el.className = 'file-download';
  el.href = url;
  el.target = '_blank';
  el.rel = 'noopener noreferrer';

  const filename = decodeURIComponent(url.split('/').pop()?.split('?')[0] || '') || 'Download File';

  const icon = document.createElement('span');
  icon.className = 'file-download__icon';
  icon.textContent = '📥';
  const label = document.createElement('span');
  label.textContent = filename;
  el.append(icon, label);

  if (sameServer(url) && appState.token) {
    el.addEventListener('click', async (e) => {
      e.preventDefault();
      try {
        const res = await fetch(url, { headers: { Authorization: `Bearer ${appState.token}` } });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const blobUrl = URL.createObjectURL(await res.blob());
        const a = document.createElement('a');
        a.href = blobUrl;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(blobUrl), 10000);
      } catch (err) {
        label.textContent = `${filename} (download failed)`;
        console.error('Download failed:', err);
      }
    });
  }

  return el;
}
