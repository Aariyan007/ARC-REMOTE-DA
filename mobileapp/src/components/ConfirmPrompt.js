/**
 * ARC Controller — Confirm Prompt Component
 */

import { sendReply } from '../api/http.js';
import appState from '../state/appState.js';
import { simulateReply } from '../services/mockService.js';
import { handleEvent } from '../services/eventHandler.js';
import { escapeHtml } from '../utils/helpers.js';

/**
 * Render an inline confirmation prompt with Yes/No buttons.
 * @param {string} jobId
 * @param {Function} onReply - Called after reply is sent
 * @param {object} event - The confirm event object
 */
export function renderConfirmPrompt(jobId, onReply, event = {}) {
  const el = document.createElement('div');
  el.className = 'confirm-prompt';

  const data = event.data || {};
  let richContent = '';
  
  if (data.filename && data.recipient) {
    richContent = `
      <div class="confirm-prompt__details">
        <div class="confirm-prompt__detail">
          <span class="confirm-prompt__detail-label">File:</span>
          <span class="confirm-prompt__detail-value">${escapeHtml(data.filename)}</span>
        </div>
        <div class="confirm-prompt__detail">
          <span class="confirm-prompt__detail-label">To:</span>
          <span class="confirm-prompt__detail-value">${escapeHtml(data.recipient)}</span>
        </div>
      </div>
    `;
  }

  el.innerHTML = `
    <div class="confirm-prompt__label">Action Required</div>
    ${richContent}
    <div class="confirm-prompt__actions">
      <button class="confirm-prompt__btn confirm-prompt__btn--yes" id="confirm-yes-${jobId}">✓ Yes, Proceed</button>
      <button class="confirm-prompt__btn confirm-prompt__btn--no" id="confirm-no-${jobId}">✕ Cancel</button>
    </div>
  `;

  const yesBtn = el.querySelector(`#confirm-yes-${jobId}`);
  const noBtn = el.querySelector(`#confirm-no-${jobId}`);

  async function respond(answer) {
    yesBtn.disabled = true;
    noBtn.disabled = true;

    try {
      if (appState.useMocks) {
        simulateReply(jobId, answer, (event) => handleEvent(jobId, event));
      } else {
        await sendReply(jobId, answer);
      }
      onReply?.(answer);
    } catch (err) {
      yesBtn.disabled = false;
      noBtn.disabled = false;
      console.error('Failed to send confirmation:', err);
    }
  }

  yesBtn.addEventListener('click', () => respond('yes'));
  noBtn.addEventListener('click', () => respond('no'));

  // Keyboard shortcuts
  function onKey(e) {
    if (e.key === 'y' || e.key === 'Y') { respond('yes'); document.removeEventListener('keydown', onKey); }
    if (e.key === 'n' || e.key === 'N') { respond('no'); document.removeEventListener('keydown', onKey); }
  }
  document.addEventListener('keydown', onKey);

  return el;
}
