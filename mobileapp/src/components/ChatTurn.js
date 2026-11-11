/**
 * ARC Controller — one chat turn (everything the assistant did for one user message).
 *
 * Renders, in order: tool-activity chips, a pending approval card, the assistant's reply
 * (with file matches), and — while running — a typing indicator with a Stop button.
 * Built with DOM APIs / textContent only: replies and tool names come from a model and
 * the user's disk, so nothing here is interpolated as HTML.
 */
import { renderConfirmPrompt } from './ConfirmPrompt.js';
import { renderClarifyPrompt } from './ClarifyPrompt.js';
import { renderFileMatches } from './FileMatches.js';

function avatar() {
  const a = document.createElement('div');
  a.className = 'chat-bubble__avatar chat-bubble__avatar--arc';
  const s = document.createElement('span');
  s.textContent = 'A';
  a.appendChild(s);
  return a;
}

function bubble(...children) {
  const row = document.createElement('div');
  row.className = 'chat-bubble chat-bubble--arc';
  const content = document.createElement('div');
  content.className = 'chat-bubble__content';
  content.append(...children);
  row.append(avatar(), content);
  return row;
}

function toolChips(events) {
  const tools = events.filter(e => e.type === 'progress' && e.data?.tool);
  if (!tools.length) return null;
  const wrap = document.createElement('div');
  wrap.className = 'tool-chips';
  for (const e of tools) {
    const chip = document.createElement('span');
    chip.className = 'tool-chip';
    chip.textContent = e.message;
    chip.title = e.data.tool;
    wrap.appendChild(chip);
  }
  return wrap;
}

function typing(onStop) {
  const wrap = document.createElement('div');
  wrap.className = 'chat-typing-row';
  const dots = document.createElement('div');
  dots.className = 'chat-typing';
  for (let i = 0; i < 3; i++) {
    const d = document.createElement('div');
    d.className = 'chat-typing__dot';
    dots.appendChild(d);
  }
  wrap.appendChild(dots);
  if (onStop) {
    const stop = document.createElement('button');
    stop.type = 'button';
    stop.className = 'chat-stop-btn';
    stop.textContent = 'Stop';
    stop.addEventListener('click', () => { stop.disabled = true; onStop(); });
    wrap.appendChild(stop);
  }
  return wrap;
}

/**
 * @param {object} job - jobStore job (kind === 'chat')
 * @param {{onReply: Function, onStop: Function, onRetry: Function}} handlers
 * @returns {DocumentFragment}
 */
export function renderChatTurn(job, { onReply, onStop, onRetry } = {}) {
  const frag = document.createDocumentFragment();
  const events = job.events;

  const chips = toolChips(events);
  if (chips) frag.appendChild(bubble(chips));

  // Pending approval / question — only the latest unanswered prompt is interactive.
  const lastEvent = events[events.length - 1];
  if (job.needsInput && lastEvent && (lastEvent.type === 'confirm' || lastEvent.type === 'clarify')) {
    const text = document.createElement('div');
    text.className = 'chat-reply';
    text.textContent = lastEvent.message;
    const prompt = lastEvent.type === 'confirm'
      ? renderConfirmPrompt(job.id, answer => onReply?.(job.id, answer), lastEvent)
      : renderClarifyPrompt(job.id, answer => onReply?.(job.id, answer));
    frag.appendChild(bubble(text, prompt));
  }

  const terminal = events.find(e => e.type === 'result' || e.type === 'error');
  if (terminal) {
    const text = document.createElement('div');
    text.className = `chat-reply chat-reply--${terminal.type}`;
    text.textContent = terminal.message;
    const parts = [text];
    const matches = terminal.data?.matches;
    if (Array.isArray(matches) && matches.length && typeof matches[0]?.name === 'string') {
      parts.push(renderFileMatches(matches.slice(0, 10), terminal.data.exact === true));
    }
    if (terminal.type === 'error' && onRetry && job.command) {
      const retry = document.createElement('button');
      retry.type = 'button';
      retry.className = 'event-card__retry-btn';
      retry.textContent = 'Retry';
      retry.addEventListener('click', () => onRetry(job.command));
      parts.push(retry);
    }
    frag.appendChild(bubble(...parts));
  } else if (job.status === 'running' || job.status === 'waiting') {
    frag.appendChild(bubble(typing(onStop ? () => onStop(job.id) : null)));
  }
  return frag;
}
