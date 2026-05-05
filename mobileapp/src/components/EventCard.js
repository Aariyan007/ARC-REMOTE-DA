/**
 * ARC Controller — Event Card Component (Chat-Style)
 * Renders individual events as chat bubble content cards.
 * Supports: progress steppers, file preview cards, chat messages, clarify/confirm prompts.
 */

import { getEventIcon, getEventLabel } from '../services/eventHandler.js';
import { timeAgo, escapeHtml, extractFileUrls } from '../utils/helpers.js';
import { renderClarifyPrompt } from './ClarifyPrompt.js';
import { renderConfirmPrompt } from './ConfirmPrompt.js';
import { renderFileDownload } from './FileDownload.js';

/**
 * Render a single event card for the chat timeline.
 * @param {object} event - The event object
 * @param {string} jobId - The parent job ID
 * @param {Function} onReply - Callback when user replies to clarify/confirm
 * @param {boolean} isActivePrompt - Whether this is the active clarify/confirm
 * @param {Function} [onRetry] - Callback when user clicks retry on an error card
 * @param {string} [commandText] - Original command text for retry
 */
export function renderEventCard(event, jobId, onReply, isActivePrompt = false, onRetry = null, commandText = '') {
  const card = document.createElement('div');
  card.className = `event-card event-card--${event.type}`;
  card.id = `event-${event.id}`;

  const hasData = event.data && Object.keys(event.data).length > 0;
  const fileUrls = extractFileUrls(event.message, event.data);

  // Determine display style based on event type
  const isChat = event.type === 'result' || event.type === 'error';
  const isProgress = event.type === 'executing' || event.type === 'progress' || event.type === 'verify';

  if (isProgress) {
    // ── Pipeline step stepper ──────────────────────────────
    const step = event.data?.step || 0;
    const totalSteps = event.data?.total_steps || 4;
    const stage = event.data?.stage || event.type;
    const progressPct = totalSteps > 0 ? Math.round((step / totalSteps) * 100) : 0;

    card.innerHTML = `
      <div class="event-card__step-row">
        <div class="event-card__step-indicator event-card__step-indicator--${event.type}">
          <div class="event-card__step-icon">${getEventIcon(event.type)}</div>
        </div>
        <div class="event-card__step-body">
          <span class="event-card__step-label">${escapeHtml(event.message)}</span>
          ${totalSteps > 0 ? `
            <div class="event-card__step-bar">
              <div class="event-card__step-bar-fill" style="width:${progressPct}%"></div>
            </div>
            <span class="event-card__step-meta">Step ${step} of ${totalSteps}</span>
          ` : ''}
        </div>
      </div>
    `;
  } else if (isChat) {
    // ── Primary chat content — the actual response ─────────
    const isFileResult = _isFileResult(event);
    const fileInfo = isFileResult ? _extractFileInfo(event) : null;

    card.innerHTML = `
      <div class="event-card__chat-message">${_formatMessage(event.message)}</div>
      ${isFileResult && fileInfo ? _renderFilePreview(fileInfo) : ''}
      ${hasData && !isFileResult ? `
        <div class="event-card__data-toggle" data-expanded="false">
          ▸ Details
        </div>
        <div class="event-card__data" style="display:none">
${JSON.stringify(event.data, null, 2)}
        </div>
      ` : ''}
      ${event.type === 'error' && onRetry && commandText ? `
        <button class="event-card__retry-btn" id="retry-${event.id}">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M1 2v5h5"/><path d="M2.5 10.5a6 6 0 1 0 1-4.2L1 7"/>
          </svg>
          Retry
        </button>
      ` : ''}
      <div class="event-card__time">${timeAgo(event.timestamp)}</div>
      <div class="event-card__attachments" id="attachments-${event.id}"></div>
      <div class="event-card__prompt" id="prompt-${event.id}"></div>
    `;
  } else {
    // ── Clarify / Confirm — interactive cards ──────────────
    card.innerHTML = `
      <div class="event-card__header-row">
        <div class="event-card__icon">${getEventIcon(event.type)}</div>
        <div class="event-card__type">${getEventLabel(event.type)}</div>
      </div>
      <div class="event-card__chat-message">${_formatMessage(event.message)}</div>
      <div class="event-card__time">${timeAgo(event.timestamp)}</div>
      <div class="event-card__attachments" id="attachments-${event.id}"></div>
      <div class="event-card__prompt" id="prompt-${event.id}"></div>
    `;
  }

  // Toggle data details
  const toggle = card.querySelector('.event-card__data-toggle');
  if (toggle) {
    toggle.addEventListener('click', () => {
      const dataEl = card.querySelector('.event-card__data');
      const expanded = toggle.dataset.expanded === 'true';
      toggle.dataset.expanded = String(!expanded);
      toggle.textContent = expanded ? '▸ Details' : '▾ Hide details';
      dataEl.style.display = expanded ? 'none' : 'block';
    });
  }

  // File download buttons
  const attachments = card.querySelector(`#attachments-${event.id}`);
  if (attachments && fileUrls.length > 0) {
    fileUrls.forEach(url => {
      attachments.appendChild(renderFileDownload(url));
    });
  }

  // Clarify/Confirm prompts
  const promptContainer = card.querySelector(`#prompt-${event.id}`);
  if (promptContainer) {
    if (isActivePrompt && event.type === 'clarify') {
      promptContainer.appendChild(renderClarifyPrompt(jobId, onReply));
    } else if (isActivePrompt && event.type === 'confirm') {
      promptContainer.appendChild(renderConfirmPrompt(jobId, onReply, event));
    }
  }

  // Retry button handler for error events
  const retryBtn = card.querySelector(`#retry-${event.id}`);
  if (retryBtn && onRetry && commandText) {
    retryBtn.addEventListener('click', () => {
      onRetry(commandText);
    });
  }

  return card;
}

/**
 * Check if this result event contains file search results.
 */
function _isFileResult(event) {
  if (event.type !== 'result') return false;
  const data = event.data || {};
  const action = data.interpreted_action || '';
  return action === 'search_file' || !!(data.path || data.filename);
}

/**
 * Extract file info from a search_file result event.
 */
function _extractFileInfo(event) {
  const data = event.data || {};
  const path = data.path || data.filename || '';
  if (!path) return null;

  const parts = path.replace(/\\/g, '/').split('/');
  const filename = parts[parts.length - 1] || path;
  const ext = filename.includes('.') ? filename.split('.').pop().toLowerCase() : '';

  const icons = {
    pdf: '📕', doc: '📄', docx: '📄', txt: '📝', md: '📝',
    py: '🐍', js: '🟨', ts: '🔷', html: '🌐', css: '🎨',
    jpg: '🖼️', jpeg: '🖼️', png: '🖼️', gif: '🖼️', svg: '🖼️',
    mp3: '🎵', wav: '🎵', mp4: '🎬', mov: '🎬',
    zip: '📦', rar: '📦', tar: '📦', gz: '📦',
    xlsx: '📊', csv: '📊', json: '📋', xml: '📋',
    pptx: '📊', key: '📊',
  };

  return {
    filename,
    path,
    ext,
    icon: icons[ext] || '📄',
    folder: parts.slice(0, -1).join('/'),
  };
}

/**
 * Render a file preview card for search_file results.
 */
function _renderFilePreview(fileInfo) {
  return `
    <div class="event-card__file-preview">
      <div class="event-card__file-icon">${fileInfo.icon}</div>
      <div class="event-card__file-details">
        <div class="event-card__file-name">${escapeHtml(fileInfo.filename)}</div>
        <div class="event-card__file-path">${escapeHtml(fileInfo.folder)}</div>
      </div>
      <div class="event-card__file-ext">.${escapeHtml(fileInfo.ext)}</div>
    </div>
  `;
}

/**
 * Format message text — handle newlines and basic formatting.
 */
function _formatMessage(message) {
  if (!message) return '';
  // Escape HTML, then convert newlines to <br>
  let safe = escapeHtml(message);
  safe = safe.replace(/\n/g, '<br>');
  return safe;
}
