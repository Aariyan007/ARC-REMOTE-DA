/**
 * ARC Controller — Event Card Component
 */

import { getEventIcon, getEventLabel } from '../services/eventHandler.js';
import { timeAgo, escapeHtml, extractFileUrls } from '../utils/helpers.js';
import { renderClarifyPrompt } from './ClarifyPrompt.js';
import { renderConfirmPrompt } from './ConfirmPrompt.js';
import { renderFileDownload } from './FileDownload.js';

/**
 * Render a single event card for the timeline.
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

  card.innerHTML = `
    <div class="event-card__icon">${getEventIcon(event.type)}</div>
    <div class="event-card__body">
      <div class="event-card__type">${getEventLabel(event.type)}</div>
      <div class="event-card__message">${escapeHtml(event.message)}</div>
      ${hasData ? `
        <div class="event-card__data-toggle" data-expanded="false">
          ▸ Show details
        </div>
        <div class="event-card__data" style="display:none">
${JSON.stringify(event.data, null, 2)}
        </div>
      ` : ''}
      <div class="event-card__time">${timeAgo(event.timestamp)}</div>
      <div class="event-card__attachments" id="attachments-${event.id}"></div>
      <div class="event-card__prompt" id="prompt-${event.id}"></div>
    </div>
  `;

  // Toggle data details
  const toggle = card.querySelector('.event-card__data-toggle');
  if (toggle) {
    toggle.addEventListener('click', () => {
      const dataEl = card.querySelector('.event-card__data');
      const expanded = toggle.dataset.expanded === 'true';
      toggle.dataset.expanded = String(!expanded);
      toggle.textContent = expanded ? '▸ Show details' : '▾ Hide details';
      dataEl.style.display = expanded ? 'none' : 'block';
    });
  }

  // File download buttons
  const attachments = card.querySelector(`#attachments-${event.id}`);
  if (fileUrls.length > 0) {
    fileUrls.forEach(url => {
      attachments.appendChild(renderFileDownload(url));
    });
  }

  // Clarify/Confirm prompts
  const promptContainer = card.querySelector(`#prompt-${event.id}`);
  if (isActivePrompt && event.type === 'clarify') {
    promptContainer.appendChild(renderClarifyPrompt(jobId, onReply));
  } else if (isActivePrompt && event.type === 'confirm') {
    promptContainer.appendChild(renderConfirmPrompt(jobId, onReply, event));
  }

  return card;
}
