/**
 * ARC Controller — Confirm Prompt Component
 */

import { sendReply } from '../api/http.js';
import appState from '../state/appState.js';
import jobStore from '../state/jobStore.js';
import { simulateReply } from '../services/mockService.js';
import { handleEvent } from '../services/eventHandler.js';

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
  const dangerous = data.dangerous === true;
  el.classList.toggle('confirm-prompt--danger', dangerous);

  // Rows to show: the exact arguments the assistant wants to use (data.details is a JSON
  // string of the validated arguments), or the legacy filename/recipient pair.
  const rows = [];
  if (typeof data.details === 'string') {
    try {
      const args = JSON.parse(data.details);
      if (args && typeof args === 'object' && !Array.isArray(args)) {
        for (const [k, v] of Object.entries(args)) {
          rows.push([k, typeof v === 'string' ? v : JSON.stringify(v)]);
        }
      }
    } catch { /* details was redacted/truncated text; skip the rows */ }
  } else if (data.filename && data.recipient) {
    rows.push(['File', data.filename], ['To', data.recipient]);
  }

  const label = document.createElement('div');
  label.className = 'confirm-prompt__label';
  label.textContent = dangerous ? 'Dangerous action — approve?' : 'Approve this action?';
  el.appendChild(label);

  if (rows.length) {
    const details = document.createElement('div');
    details.className = 'confirm-prompt__details';
    for (const [k, v] of rows.slice(0, 8)) {
      const row = document.createElement('div');
      row.className = 'confirm-prompt__detail';
      const kEl = document.createElement('span');
      kEl.className = 'confirm-prompt__detail-label';
      kEl.textContent = k;
      const vEl = document.createElement('span');
      vEl.className = 'confirm-prompt__detail-value';
      vEl.textContent = v;
      vEl.title = v;
      row.append(kEl, vEl);
      details.appendChild(row);
    }
    el.appendChild(details);
  }

  const actions = document.createElement('div');
  actions.className = 'confirm-prompt__actions';
  const yes = document.createElement('button');
  yes.type = 'button';
  yes.className = 'confirm-prompt__btn confirm-prompt__btn--yes';
  yes.id = `confirm-yes-${jobId}`;
  yes.textContent = '✓ Approve';
  const no = document.createElement('button');
  no.type = 'button';
  no.className = 'confirm-prompt__btn confirm-prompt__btn--no';
  no.id = `confirm-no-${jobId}`;
  no.textContent = '✕ Decline';
  actions.append(yes, no);
  el.appendChild(actions);

  const yesBtn = el.querySelector(`#confirm-yes-${jobId}`);
  const noBtn = el.querySelector(`#confirm-no-${jobId}`);

  async function respond(answer) {
    yesBtn.disabled = true;
    noBtn.disabled = true;

    try {
      if (appState.useMocks) {
        simulateReply(jobId, answer, (event) => handleEvent(jobId, event));
      } else {
        await sendReply(jobId, answer, jobStore.getJob(jobId)?.pendingNonce);
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
