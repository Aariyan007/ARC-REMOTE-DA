/**
 * ARC Controller — Event Timeline Component
 */

import jobStore from '../state/jobStore.js';
import { renderEventCard } from './EventCard.js';
import { renderStatusBadge } from './StatusBadge.js';
import { escapeHtml, truncate } from '../utils/helpers.js';

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
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-state__icon">⚡</div>
          <h2 class="empty-state__title">Ready to Command</h2>
          <p class="empty-state__desc">
            Type a natural language command below to control your desktop remotely. ARC will interpret, execute, and verify the result.
          </p>
          <div class="empty-state__hints" id="hint-buttons">
            <button class="empty-state__hint" data-cmd="open chrome">open chrome</button>
            <button class="empty-state__hint" data-cmd="what time is it">what time is it</button>
            <button class="empty-state__hint" data-cmd="find resume.txt">find resume.txt</button>
            <button class="empty-state__hint" data-cmd="take a screenshot">take a screenshot</button>
            <button class="empty-state__hint" data-cmd="volume up">volume up</button>
            <button class="empty-state__hint" data-cmd="delete temp files">delete temp files</button>
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

    // Build timeline for all jobs
    const fragment = document.createDocumentFragment();

    jobs.forEach((job, jobIndex) => {
      // Job separator for non-first jobs
      if (jobIndex > 0) {
        const sep = document.createElement('div');
        sep.className = 'job-separator';
        sep.innerHTML = `
          <div class="job-separator__line"></div>
          <span class="job-separator__text">${truncate(job.command, 40)}</span>
          <div class="job-separator__line"></div>
        `;
        fragment.appendChild(sep);
      }

      // Job header
      const header = document.createElement('div');
      header.className = 'timeline__job-header';
      header.innerHTML = `<span class="timeline__job-command">${escapeHtml(job.command)}</span>`;
      header.appendChild(renderStatusBadge(job.status));
      fragment.appendChild(header);

      // Event cards
      const timeline = document.createElement('div');
      timeline.className = 'timeline';

      job.events.forEach((event, eventIndex) => {
        const isLast = eventIndex === job.events.length - 1;
        const isActivePrompt = isLast && job.needsInput && (event.type === 'clarify' || event.type === 'confirm');

        const card = renderEventCard(event, job.id, (answer) => {
          jobStore.markReplied(job.id);
          onReply?.(job.id, answer);
        }, isActivePrompt);

        timeline.appendChild(card);
      });

      // Active indicator (pulsing dots) for running jobs
      if (job.status === 'running' && !job.needsInput) {
        const indicator = document.createElement('div');
        indicator.className = 'active-indicator';
        indicator.innerHTML = `
          <div class="active-indicator__dots">
            <div class="active-indicator__dot"></div>
            <div class="active-indicator__dot"></div>
            <div class="active-indicator__dot"></div>
          </div>
          <span class="active-indicator__text">Processing...</span>
        `;
        timeline.appendChild(indicator);
      }

      fragment.appendChild(timeline);
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
