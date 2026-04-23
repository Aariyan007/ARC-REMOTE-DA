/**
 * ARC Controller — Event Handler Service
 * Central dispatcher that maps backend events to state updates and UI actions.
 */

import jobStore from '../state/jobStore.js';

/**
 * Process an incoming event from WebSocket and update state.
 * @param {string} jobId - The job this event belongs to
 * @param {object} event - Raw event from WebSocket { type, message, data, timestamp }
 */
export function handleEvent(jobId, event) {
  // Normalize event
  const normalized = {
    type: event.type || 'progress',
    message: event.message || '',
    data: event.data || {},
    timestamp: event.timestamp || (Date.now() / 1000),
    id: `${jobId}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
  };

  // Add to job store (this also updates job status)
  jobStore.addEvent(jobId, normalized);

  return normalized;
}

/**
 * Get the appropriate SVG icon for an event type.
 */
export function getEventIcon(type) {
  const icons = {
    ack: `<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M13.3 4.3L6 11.6L2.7 8.3" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
    clarify: `<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.5"/><path d="M6.5 6.2a1.5 1.5 0 0 1 2.8.6c0 1-1.3 1.4-1.3 1.4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><circle cx="8" cy="11" r="0.5" fill="currentColor"/></svg>`,
    confirm: `<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M8 1.5L9.5 5.5H13.5L10.5 8L11.5 12.5L8 10L4.5 12.5L5.5 8L2.5 5.5H6.5L8 1.5Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/></svg>`,
    progress: `<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M8 2v4l3 2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.5"/></svg>`,
    executing: `<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M4 2l8 6-8 6V2z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/></svg>`,
    verify: `<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M3 8l3 3 7-7" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
    result: `<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.5"/><path d="M5.5 8l2 2 3.5-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
    error: `<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.5"/><path d="M8 5v4M8 11h.01" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>`,
  };
  return icons[type] || icons.progress;
}

/**
 * Get event type display name.
 */
export function getEventLabel(type) {
  const labels = {
    ack: 'Acknowledged',
    clarify: 'Clarification Needed',
    confirm: 'Confirmation Required',
    progress: 'In Progress',
    executing: 'Executing',
    verify: 'Verifying',
    result: 'Completed',
    error: 'Error',
  };
  return labels[type] || type;
}
