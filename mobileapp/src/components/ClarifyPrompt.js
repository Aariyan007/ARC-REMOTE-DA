/**
 * ARC Controller — Clarify Prompt Component
 */

import { sendReply } from '../api/http.js';
import appState from '../state/appState.js';
import { simulateReply } from '../services/mockService.js';
import { handleEvent } from '../services/eventHandler.js';

/**
 * Render an inline clarification prompt.
 * @param {string} jobId
 * @param {Function} onReply - Called after reply is sent
 */
export function renderClarifyPrompt(jobId, onReply) {
  const el = document.createElement('div');
  el.className = 'clarify-prompt';

  el.innerHTML = `
    <div class="clarify-prompt__label">Your Response</div>
    <div class="clarify-prompt__input-row">
      <input type="text" class="clarify-prompt__input" placeholder="Type your answer..." id="clarify-input-${jobId}" autocomplete="off" />
      <button class="clarify-prompt__submit" id="clarify-submit-${jobId}">Send</button>
    </div>
  `;

  const input = el.querySelector(`#clarify-input-${jobId}`);
  const btn = el.querySelector(`#clarify-submit-${jobId}`);

  async function submit() {
    const answer = input.value.trim();
    if (!answer) return;

    btn.disabled = true;
    input.disabled = true;
    btn.textContent = 'Sending...';

    try {
      if (appState.useMocks) {
        simulateReply(jobId, answer, (event) => handleEvent(jobId, event));
      } else {
        await sendReply(jobId, answer);
      }
      onReply?.(answer);
    } catch (err) {
      btn.disabled = false;
      input.disabled = false;
      btn.textContent = 'Retry';
      console.error('Failed to send reply:', err);
    }
  }

  btn.addEventListener('click', submit);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') submit();
  });

  // Auto-focus
  requestAnimationFrame(() => input.focus());

  return el;
}
