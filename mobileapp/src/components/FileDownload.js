/**
 * ARC Controller — File Download Component
 */

/**
 * Render a download button for a file URL.
 * @param {string} url - The file URL
 */
export function renderFileDownload(url) {
  const el = document.createElement('a');
  el.className = 'file-download';
  el.href = url;
  el.target = '_blank';
  el.rel = 'noopener noreferrer';

  // Extract filename from URL
  const parts = url.split('/');
  const filename = parts[parts.length - 1]?.split('?')[0] || 'Download File';

  el.innerHTML = `
    <span class="file-download__icon">📥</span>
    <span>${filename}</span>
  `;

  return el;
}
