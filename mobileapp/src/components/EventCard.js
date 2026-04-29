/**
 * ARC Controller — Event Card Component (Chat-Style)
 * Renders individual events as chat bubble content cards.
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
 */
export function renderEventCard(event, jobId, onReply, isActivePrompt = false) {
  const card = document.createElement('div');
  card.className = `event-card event-card--${event.type}`;
  card.id = `event-${event.id}`;

  const hasData = event.data && Object.keys(event.data).length > 0;
  const fileUrls = extractFileUrls(event.message, event.data);

  // Determine display style based on event type
  const isChat = event.type === 'result' || event.type === 'error';
  const isProgress = event.type === 'executing' || event.type === 'progress' || event.type === 'verify';

  if (isProgress) {
    // Compact progress indicator
    card.innerHTML = `
      <div class="event-card__progress-row">
        <div class="event-card__icon">${getEventIcon(event.type)}</div>
        <span class="event-card__progress-text">${escapeHtml(event.message)}</span>
      </div>
    `;
  } else if (isChat) {
    // Primary chat content — the actual response
    card.innerHTML = `
      <div class="event-card__chat-message">${_formatMessage(event.message)}</div>
      ${hasData ? `
        <div class="event-card__data-toggle" data-expanded="false">
          ▸ Details
        </div>
        <div class="event-card__data" style="display:none">
${JSON.stringify(event.data, null, 2)}
        </div>
      ` : ''}
      <div class="event-card__time">${timeAgo(event.timestamp)}</div>
      <div class="event-card__attachments" id="attachments-${event.id}"></div>
      <div class="event-card__prompt" id="prompt-${event.id}"></div>
    `;
  } else {
    // Clarify / Confirm — interactive cards
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

  return card;
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
