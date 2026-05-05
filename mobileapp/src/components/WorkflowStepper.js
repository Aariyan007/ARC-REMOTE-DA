/**
 * ARC Controller — Workflow Stepper Component
 * Consolidates multi-step job events into a single vertical stepper card.
 * Each step shows: icon → label → status (pending/active/done/failed).
 * Connector lines between steps animate as progress fills in.
 */

import { getEventIcon, getEventLabel } from '../services/eventHandler.js';
import { escapeHtml, timeAgo } from '../utils/helpers.js';
import { renderClarifyPrompt } from './ClarifyPrompt.js';
import { renderConfirmPrompt } from './ConfirmPrompt.js';

/**
 * Determine the visual status of a step in the stepper.
 * @param {object} event - The event object
 * @param {number} idx - Index of the event in the visible list
 * @param {number} total - Total visible events
 * @param {object} job - The parent job
 * @returns {'done'|'active'|'failed'|'pending'}
 */
function _getStepStatus(event, idx, total, job) {
  if (event.type === 'error') return 'failed';
  if (event.type === 'result') return 'done';

  const isLast = idx === total - 1;

  // If job is still running and this is the last event, it's active
  if (isLast && job.status === 'running') return 'active';

  // If job needs input and this is the last event (clarify/confirm), it's active
  if (isLast && job.needsInput) return 'active';

  // Events before the last are completed
  return 'done';
}

/**
 * Map step status to a CSS modifier suffix.
 */
function _statusModifier(status) {
  return status; // done, active, failed, pending
}

/**
 * Get the accent color class for a given event type.
 */
function _typeColorClass(type) {
  const map = {
    ack: 'blue',
    executing: 'blue',
    progress: 'purple',
    verify: 'teal',
    clarify: 'amber',
    confirm: 'orange',
    result: 'green',
    error: 'red',
  };
  return map[type] || 'blue';
}

/**
 * Check if a job qualifies for the stepper view.
 * A multi-step job has >2 non-ack events before a terminal (result/error).
 * @param {object} job
 * @returns {boolean}
 */
export function isMultiStepJob(job) {
  const nonAck = job.events.filter(e => e.type !== 'ack');
  // Need at least 3 pipeline events (e.g. executing → progress → verify → result)
  // OR interactive steps like clarify/confirm
  const pipelineTypes = ['executing', 'progress', 'verify', 'clarify', 'confirm'];
  const pipelineCount = nonAck.filter(e => pipelineTypes.includes(e.type)).length;
  return pipelineCount >= 2;
}

/**
 * Render the workflow stepper card for a multi-step job.
 * @param {object} job - The job object from jobStore
 * @param {Function} onReply - Callback for clarify/confirm replies
 * @param {Function} [onRetry] - Callback for retrying failed commands
 * @returns {HTMLElement}
 */
export function renderWorkflowStepper(job, onReply, onRetry = null) {
  const container = document.createElement('div');
  container.className = 'workflow-stepper';
  container.id = `stepper-${job.id}`;

  const visibleEvents = job.events.filter(e => e.type !== 'ack');

  // Build step list
  const stepsEl = document.createElement('div');
  stepsEl.className = 'workflow-stepper__steps';

  visibleEvents.forEach((event, idx) => {
    const total = visibleEvents.length;
    const status = _getStepStatus(event, idx, total, job);
    const colorClass = _typeColorClass(event.type);
    const isLast = idx === total - 1;

    // ── Step node ──────────────────────────────────────
    const step = document.createElement('div');
    step.className = `workflow-step workflow-step--${_statusModifier(status)} workflow-step--${colorClass}`;

    // Step icon circle
    const iconCircle = document.createElement('div');
    iconCircle.className = 'workflow-step__icon';
    iconCircle.innerHTML = status === 'done'
      ? `<svg width="12" height="12" viewBox="0 0 16 16" fill="none"><path d="M3 8l3.5 3.5L13 5" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`
      : status === 'failed'
        ? `<svg width="12" height="12" viewBox="0 0 16 16" fill="none"><path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>`
        : status === 'active'
          ? `<div class="workflow-step__pulse"></div>`
          : getEventIcon(event.type);

    // Step body (label + meta)
    const body = document.createElement('div');
    body.className = 'workflow-step__body';

    const label = document.createElement('div');
    label.className = 'workflow-step__label';
    label.textContent = _getStepLabel(event);

    const meta = document.createElement('div');
    meta.className = 'workflow-step__meta';
    meta.textContent = status === 'active' && job.status === 'running'
      ? 'In progress…'
      : status === 'active' && job.needsInput
        ? 'Waiting for input'
        : timeAgo(event.timestamp);

    body.appendChild(label);
    body.appendChild(meta);

    step.appendChild(iconCircle);
    step.appendChild(body);

    stepsEl.appendChild(step);

    // ── Connector line between steps ──────────────────
    if (!isLast) {
      const connector = document.createElement('div');
      connector.className = 'workflow-step__connector';
      // Fill the connector if the next step exists (done)
      const nextStatus = _getStepStatus(visibleEvents[idx + 1], idx + 1, total, job);
      if (nextStatus === 'done' || nextStatus === 'active' || nextStatus === 'failed') {
        connector.classList.add('workflow-step__connector--filled');
      }
      stepsEl.appendChild(connector);
    }

    // ── Embedded interactive prompt for clarify/confirm ──
    if (isLast && job.needsInput && (event.type === 'clarify' || event.type === 'confirm')) {
      const promptWrap = document.createElement('div');
      promptWrap.className = 'workflow-step__prompt';

      if (event.type === 'clarify') {
        promptWrap.appendChild(renderClarifyPrompt(job.id, (answer) => {
          onReply?.(job.id, answer);
        }));
      } else if (event.type === 'confirm') {
        promptWrap.appendChild(renderConfirmPrompt(job.id, (answer) => {
          onReply?.(job.id, answer);
        }, event));
      }

      stepsEl.appendChild(promptWrap);
    }
  });

  container.appendChild(stepsEl);

  // ── Final result / error message ────────────────────
  const terminal = visibleEvents.find(e => e.type === 'result' || e.type === 'error');
  if (terminal) {
    const msgEl = document.createElement('div');
    msgEl.className = `workflow-stepper__result workflow-stepper__result--${terminal.type}`;
    msgEl.innerHTML = escapeHtml(terminal.message).replace(/\n/g, '<br>');
    container.appendChild(msgEl);

    // Retry button for failed workflows
    if (terminal.type === 'error' && onRetry && job.command) {
      const retryBtn = document.createElement('button');
      retryBtn.className = 'event-card__retry-btn';
      retryBtn.innerHTML = `
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M1 2v5h5"/><path d="M2.5 10.5a6 6 0 1 0 1-4.2L1 7"/>
        </svg>
        Retry
      `;
      retryBtn.addEventListener('click', () => onRetry(job.command));
      container.appendChild(retryBtn);
    }
  }

  // ── Typing indicator if still running ───────────────
  if (job.status === 'running' && !job.needsInput) {
    const typing = document.createElement('div');
    typing.className = 'workflow-stepper__typing';
    typing.innerHTML = `
      <div class="chat-typing__dot"></div>
      <div class="chat-typing__dot"></div>
      <div class="chat-typing__dot"></div>
    `;
    container.appendChild(typing);
  }

  return container;
}

/**
 * Get a concise label for a step in the stepper.
 */
function _getStepLabel(event) {
  // Use the event message but truncate for stepper compactness
  if (!event.message) return getEventLabel(event.type);

  // For progress/executing/verify, use the message directly (usually short)
  const msg = event.message;
  if (msg.length <= 60) return msg;
  return msg.slice(0, 57) + '…';
}
