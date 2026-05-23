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

  // BUG-B FIX: the old code only removed the listener when Y/N was pressed.
  // If the timeline re-renders (e.g. a progress event arrives) before the user
  // replies, the old ConfirmPrompt element is removed from the DOM but its
  // 'keydown' handler lived on document forever, silently sending phantom
  // replies for stale jobs on the user's next keypress.
  //
  // Fix: use an AbortController tied to a MutationObserver that fires the
  // moment the element is detached from the DOM.
  const ac = new AbortController();

  function onKey(e) {
    if (e.key === 'y' || e.key === 'Y') { respond('yes'); ac.abort(); }
    if (e.key === 'n' || e.key === 'N') { respond('no');  ac.abort(); }
  }
  document.addEventListener('keydown', onKey, { signal: ac.signal });

  // Watch for el being removed from the DOM and clean up immediately
  const obs = new MutationObserver(() => {
    if (!el.isConnected) {
      ac.abort();
      obs.disconnect();
    }
  });
  obs.observe(document.body, { childList: true, subtree: true });

  return el;
}
