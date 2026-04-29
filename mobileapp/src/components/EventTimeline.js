/**
 * ARC Controller — Event Timeline Component (Chat-Style)
 * Renders a chat-bubble conversation view instead of a flat timeline.
 */

import jobStore from '../state/jobStore.js';
import { renderEventCard } from './EventCard.js';
import { escapeHtml, truncate } from '../utils/helpers.js';

/**
 * Get dynamic suggestions based on time of day and context.
 */
function getDynamicSuggestions() {
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
 * Render the timeline container and subscribe to updates.
 * @param {Function} onReply - Callback when user replies
 */
export function renderEventTimeline(onReply) {
  const container = document.createElement('div');
  container.id = 'event-timeline';

  function render() {
    const jobs = jobStore.getAllJobs();

    if (jobs.length === 0) {
      const suggestions = getDynamicSuggestions();
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-state__icon">⚡</div>
          <h2 class="empty-state__title">Ready to Command</h2>
          <p class="empty-state__desc">
            Type a natural language command below to control your desktop remotely.
          </p>
          <div class="empty-state__hints" id="hint-buttons">
            ${suggestions.map(s => `
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

    jobs.forEach((job) => {
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
      } else {
        visibleEvents.forEach((event, idx) => {
          const isLast = idx === visibleEvents.length - 1;
          const isActivePrompt = isLast && job.needsInput && (event.type === 'clarify' || event.type === 'confirm');

          const arcBubble = document.createElement('div');
          arcBubble.className = `chat-bubble chat-bubble--arc chat-bubble--${event.type}`;

          const card = renderEventCard(event, job.id, (answer) => {
            jobStore.markReplied(job.id);
            onReply?.(job.id, answer);
          }, isActivePrompt);

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
