/**
 * ARC Controller — File match list (search results / "did you mean" suggestions)
 * Built with DOM APIs only: file names come from the user's disk, never interpolated as HTML.
 */
import appState from '../state/appState.js';
import { apiBase } from '../utils/config.js';

function fmtSize(bytes) {
  if (!bytes) return '';
  const units = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  let n = bytes;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n >= 10 || i === 0 ? Math.round(n) : n.toFixed(1)} ${units[i]}`;
}

async function download(match, button) {
  const original = button.textContent;
  button.disabled = true;
  button.textContent = 'Downloading…';
  try {
    const res = await fetch(`${apiBase()}${match.download_url}`, {
      headers: { Authorization: `Bearer ${appState.token}` },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const blobUrl = URL.createObjectURL(await res.blob());
    const a = document.createElement('a');
    a.href = blobUrl;
    a.download = match.name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(blobUrl), 10000);
    button.textContent = 'Saved ✓';
  } catch (err) {
    console.error('Download failed:', err);
    button.textContent = 'Failed — retry';
    button.disabled = false;
    return;
  }
  setTimeout(() => { button.textContent = original; button.disabled = false; }, 2500);
}

/**
 * @param {Array} matches - [{name, folder, size, match_type, downloadable, download_url}]
 * @param {boolean} exact - false when these are only similar names
 */
export function renderFileMatches(matches, exact) {
  const wrap = document.createElement('div');
  wrap.className = 'file-matches';

  const title = document.createElement('div');
  title.className = 'file-matches__title';
  title.textContent = exact ? 'Files found' : 'Did you mean…';
  wrap.appendChild(title);

  for (const m of matches) {
    const row = document.createElement('div');
    row.className = 'file-matches__row';

    const info = document.createElement('div');
    info.className = 'file-matches__info';
    const name = document.createElement('div');
    name.className = 'file-matches__name';
    name.textContent = m.name;
    const meta = document.createElement('div');
    meta.className = 'file-matches__meta';
    meta.textContent = [fmtSize(m.size), m.folder].filter(Boolean).join(' · ');
    info.append(name, meta);
    row.appendChild(info);

    if (m.downloadable && m.download_url) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'file-matches__btn';
      btn.textContent = 'Download';
      btn.addEventListener('click', () => download(m, btn));
      row.appendChild(btn);
    }
    wrap.appendChild(row);
  }
  return wrap;
}
