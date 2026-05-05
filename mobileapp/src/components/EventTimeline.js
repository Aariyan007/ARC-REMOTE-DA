/**
 * ARC Controller — Event Timeline Component (Chat-Style)
 * Renders a chat-bubble conversation view with session separators,
 * dynamic suggestions, and history controls.
 */

import jobStore from '../state/jobStore.js';
import { renderEventCard } from './EventCard.js';
import { isMultiStepJob, renderWorkflowStepper } from './WorkflowStepper.js';
import { escapeHtml, truncate } from '../utils/helpers.js';
import appState from '../state/appState.js';

/** Cache fetched suggestions for 5 minutes */
let _suggestionsCache = null;
let _suggestionsFetchedAt = 0;
const SUGGESTIONS_TTL = 5 * 60 * 1000;

/**
 * Get dynamic suggestions — try backend first, fall back to client-side.
 */
async function getDynamicSuggestions() {
  // Try backend endpoint if connected
  if (appState.connected && appState.token && !appState.useMocks) {
    const now = Date.now();
    if (_suggestionsCache && (now - _suggestionsFetchedAt) < SUGGESTIONS_TTL) {
      return _suggestionsCache;
    }
    try {
      const { fetchSuggestions } = await import('../api/http.js');
      const data = await fetchSuggestions();
      if (data?.suggestions?.length) {
        _suggestionsCache = data.suggestions.slice(0, 6);
        _suggestionsFetchedAt = now;
        return _suggestionsCache;
      }
    } catch (e) {
      console.warn('Could not fetch suggestions from backend:', e);
    }
  }

  // Fallback: client-side time-based suggestions
  return _getClientSuggestions();
}

function _getClientSuggestions() {
  const hour = new Date().getHours();
  const allSuggestions = [];

  // Time-based
  if (hour >= 5 && hour < 12) {
    allSuggestions.push(
      { cmd: 'good morning', icon: '☀️', label: 'Good morning' },
      { cmd: 'read my emails', icon: '📧', label: 'Check emails' },
      { cmd: 'read the news', icon: '📰', label: "Today's news" },
    );
  } else if (hour >= 12 && hour < 17) {
    allSuggestions.push(
      { cmd: 'take a screenshot', icon: '📸', label: 'Screenshot' },
      { cmd: 'what time is it', icon: '🕐', label: 'Check time' },
      { cmd: 'search my emails', icon: '📧', label: 'Search emails' },
    );
  } else if (hour >= 17 && hour < 22) {
    allSuggestions.push(
      { cmd: 'play some music', icon: '🎵', label: 'Play music' },
      { cmd: 'get battery level', icon: '🔋', label: 'Battery' },
      { cmd: 'lock screen', icon: '🔒', label: 'Lock screen' },
    );
  } else {
    allSuggestions.push(
      { cmd: 'good night', icon: '🌙', label: 'Good night' },
      { cmd: 'lock screen', icon: '🔒', label: 'Lock screen' },
      { cmd: 'sleep', icon: '😴', label: 'Sleep Mac' },
    );
  }

  // Always available
  allSuggestions.push(
    { cmd: 'open chrome', icon: '🌐', label: 'Open Chrome' },
    { cmd: 'find my files', icon: '📁', label: 'Find files' },
    { cmd: 'volume up', icon: '🔊', label: 'Volume up' },
    { cmd: 'what can you do', icon: '💡', label: 'Help' },
    { cmd: 'send an email', icon: '✉️', label: 'Send email' },
    { cmd: 'create a file', icon: '📄', label: 'New file' },
  );

  // Return 6 suggestions (3 time-based + 3 random always-available)
  const timeBased = allSuggestions.slice(0, 3);
  const others = allSuggestions.slice(3).sort(() => Math.random() - 0.5).slice(0, 3);
  return [...timeBased, ...others];
}

/**
 * Check if two timestamps are in different "sessions" (>5 min gap).
 */
function _isDifferentSession(ts1, ts2) {
  if (!ts1 || !ts2) return false;
  return Math.abs(ts1 - ts2) > 300; // 5 minutes
}

/**
 * Format a session separator timestamp.
 */
function _formatSessionTime(timestamp) {
  if (!timestamp) return '';
  const d = new Date(timestamp * 1000);
  const now = new Date();
  const isToday = d.toDateString() === now.toDateString();

  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  const isYesterday = d.toDateString() === yesterday.toDateString();

  const time = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

  if (isToday) return `Today at ${time}`;
  if (isYesterday) return `Yesterday at ${time}`;
  return `${d.toLocaleDateString([], { month: 'short', day: 'numeric' })} at ${time}`;
}

/**
 * Render the timeline container and subscribe to updates.
 * @param {Function} onReply - Callback when user replies
 * @param {Function} [onRetry] - Callback when user retries a failed command
 */
export function renderEventTimeline(onReply, onRetry = null) {
  const container = document.createElement('div');
  container.id = 'event-timeline';

  async function render() {
    const jobs = jobStore.getAllJobs();

    if (jobs.length === 0) {
      const suggestions = await getDynamicSuggestions();
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-state__icon">⚡</div>
          <h2 class="empty-state__title">Ready to Command</h2>
          <p class="empty-state__desc">
            Type a natural language command below to control your desktop remotely.
          </p>
          <div class="empty-state__hints" id="hint-buttons">
            ${(Array.isArray(suggestions) ? suggestions : []).map(s => `
              <button class="empty-state__hint" data-cmd="${escapeHtml(s.cmd)}">
                <span class="empty-state__hint-icon">${s.icon}</span>
                <span>${escapeHtml(s.label)}</span>
              </button>
            `).join('')}
          </div>
        </div>
      `;

      // Hint click handlers
      container.querySelectorAll('.empty-state__hint').forEach(btn => {
        btn.addEventListener('click', () => {
          const input = document.getElementById('command-input-field');
          if (input) {
            input.value = btn.dataset.cmd;
            input.focus();
            input.dispatchEvent(new Event('input'));
          }
        });
      });
      return;
    }

    // Build chat-style timeline for all jobs
    const fragment = document.createDocumentFragment();

    // ── Clear history button ──────────────────────────────
    const clearRow = document.createElement('div');
    clearRow.className = 'timeline__clear-row';
    clearRow.innerHTML = `
      <button class="timeline__clear-btn" id="clear-history-btn" title="Clear conversation history">
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
          <path d="M2 4h12M5.3 4V2.7a.7.7 0 0 1 .7-.7h4a.7.7 0 0 1 .7.7V4M6.5 7v4.5M9.5 7v4.5M3.5 4l.7 9.3a1.4 1.4 0 0 0 1.4 1.2h4.8a1.4 1.4 0 0 0 1.4-1.2L12.5 4"/>
        </svg>
        Clear
      </button>
    `;
    fragment.appendChild(clearRow);

    // Reverse so oldest job is first (we reverse back for display)
    const orderedJobs = [...jobs].reverse();

    orderedJobs.forEach((job, jobIdx) => {
      // ── Session separator ──────────────────────────────
      if (jobIdx > 0) {
        const prevJob = orderedJobs[jobIdx - 1];
        if (_isDifferentSession(prevJob.createdAt, job.createdAt)) {
          const separator = document.createElement('div');
          separator.className = 'job-separator';
          separator.innerHTML = `
            <div class="job-separator__line"></div>
            <span class="job-separator__text">${_formatSessionTime(job.createdAt)}</span>
            <div class="job-separator__line"></div>
          `;
          fragment.appendChild(separator);
        }
      }

      // ── User message bubble ────────────────────────────
      const userBubble = document.createElement('div');
      userBubble.className = 'chat-bubble chat-bubble--user';
      userBubble.innerHTML = `
        <div class="chat-bubble__content">
          <div class="chat-bubble__text">${escapeHtml(job.command)}</div>
          <div class="chat-bubble__meta">${_formatJobTime(job.createdAt)}</div>
        </div>
        <div class="chat-bubble__avatar chat-bubble__avatar--user">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="5" r="3" stroke="currentColor" stroke-width="1.5"/><path d="M2.5 14c0-3 2.5-5 5.5-5s5.5 2 5.5 5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
        </div>
      `;
      fragment.appendChild(userBubble);

      // ── ARC response bubble(s) ─────────────────────────
      // Filter events: only show meaningful ones in chat view
      const visibleEvents = job.events.filter(e =>
        // Skip internal ack events — they're noise in chat view
        e.type !== 'ack'
      );

      if (visibleEvents.length === 0 && job.status === 'running') {
        // Show typing indicator
        const typingBubble = document.createElement('div');
        typingBubble.className = 'chat-bubble chat-bubble--arc';
        typingBubble.innerHTML = `
          <div class="chat-bubble__avatar chat-bubble__avatar--arc">
            <span>A</span>
          </div>
          <div class="chat-bubble__content">
            <div class="chat-typing">
              <div class="chat-typing__dot"></div>
              <div class="chat-typing__dot"></div>
              <div class="chat-typing__dot"></div>
            </div>
          </div>
        `;
        fragment.appendChild(typingBubble);
      } else if (isMultiStepJob(job)) {
        // ── Multi-step workflow → consolidated stepper card ──
        const stepperBubble = document.createElement('div');
        stepperBubble.className = 'chat-bubble chat-bubble--arc chat-bubble--stepper';

        stepperBubble.innerHTML = `
          <div class="chat-bubble__avatar chat-bubble__avatar--arc">
            <span>A</span>
          </div>
        `;
        const contentWrap = document.createElement('div');
        contentWrap.className = 'chat-bubble__content';

        const stepper = renderWorkflowStepper(job, (jobId, answer) => {
          jobStore.markReplied(jobId);
          onReply?.(jobId, answer);
        }, onRetry);

        contentWrap.appendChild(stepper);
        stepperBubble.appendChild(contentWrap);
        fragment.appendChild(stepperBubble);
      } else {
        visibleEvents.forEach((event, idx) => {
          const isLast = idx === visibleEvents.length - 1;
          const isActivePrompt = isLast && job.needsInput && (event.type === 'clarify' || event.type === 'confirm');

          const arcBubble = document.createElement('div');
          arcBubble.className = `chat-bubble chat-bubble--arc chat-bubble--${event.type}`;

          const card = renderEventCard(event, job.id, (answer) => {
            jobStore.markReplied(job.id);
            onReply?.(job.id, answer);
          }, isActivePrompt, onRetry, job.command);

          arcBubble.innerHTML = `
            <div class="chat-bubble__avatar chat-bubble__avatar--arc">
              <span>A</span>
            </div>
          `;
          const contentWrap = document.createElement('div');
          contentWrap.className = 'chat-bubble__content';
          contentWrap.appendChild(card);
          arcBubble.appendChild(contentWrap);

          fragment.appendChild(arcBubble);
        });

        // Show typing indicator if still running after events
        if (job.status === 'running' && !job.needsInput) {
          const typingBubble = document.createElement('div');
          typingBubble.className = 'chat-bubble chat-bubble--arc';
          typingBubble.innerHTML = `
            <div class="chat-bubble__avatar chat-bubble__avatar--arc">
              <span>A</span>
            </div>
            <div class="chat-bubble__content">
              <div class="chat-typing">
                <div class="chat-typing__dot"></div>
                <div class="chat-typing__dot"></div>
                <div class="chat-typing__dot"></div>
              </div>
            </div>
          `;
          fragment.appendChild(typingBubble);
        }
      }
    });

    container.innerHTML = '';
    container.appendChild(fragment);

    // ── Clear history handler ──────────────────────────
    const clearBtn = container.querySelector('#clear-history-btn');
    if (clearBtn) {
      clearBtn.addEventListener('click', () => {
        if (jobStore.clearAllJobs) {
          jobStore.clearAllJobs();
        } else {
          // Fallback: reset the internal map
          jobStore._jobs.clear();
          jobStore._activeJobId = null;
          jobStore._notify();
        }
      });
    }

    // Auto-scroll to bottom
    requestAnimationFrame(() => {
      const main = document.getElementById('main-content');
      if (main) main.scrollTop = main.scrollHeight;
    });
  }

  render();
  jobStore.subscribe(render);

  return container;
}

function _formatJobTime(timestamp) {
  if (!timestamp) return '';
  const d = new Date(timestamp * 1000);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}
