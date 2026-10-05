/**
 * ARC Controller — WebSocket Manager
 * Streams a job's events. Resilient by design:
 *  - authenticates with a one-time ticket (no bearer token in the URL)
 *  - resumes from the last received event (?since=) after any drop
 *  - retries with capped backoff until the job finishes or is closed
 *  - reconnects immediately when the app returns to the foreground / network returns
 */

import CONFIG, { wsBase } from '../utils/config.js';
import { getWsTicket } from './http.js';

const liveConnections = new Set();

/** Force every open stream to reconnect now (app resumed / network back). */
export function reconnectAll() {
  for (const c of liveConnections) c.reconnectNow();
}

/**
 * @param {string} jobId
 * @param {object} callbacks - { onEvent, onError, onClose, onOpen }
 * @param {number} since - number of events already received
 */
export function connectToJob(jobId, callbacks = {}, since = 0) {
  const { onEvent, onError, onClose, onOpen } = callbacks;

  let ws = null;
  let received = since;
  let attempts = 0;
  let closed = false;
  let connected = false;
  let terminal = false;
  let retryTimer = null;

  function finish(info) {
    if (closed) return;
    closed = true;
    liveConnections.delete(api);
    clearTimeout(retryTimer);
    onClose?.(info);
  }

  function scheduleRetry() {
    if (closed || retryTimer) return;
    const delay = Math.min(CONFIG.WS_RECONNECT_DELAY * 2 ** attempts, CONFIG.WS_MAX_RECONNECT_DELAY);
    attempts++;
    retryTimer = setTimeout(() => { retryTimer = null; connect(); }, delay);
  }

  async function connect() {
    if (closed || terminal) return;
    if (ws && ws.readyState <= WebSocket.OPEN) return;

    let ticket;
    try {
      ticket = await getWsTicket();
    } catch (err) {
      if (err.status === 401) return finish({ clean: false, reason: 'Signed out' });
      onError?.(err);
      return scheduleRetry();
    }
    if (closed) return;

    ws = new WebSocket(`${wsBase()}${CONFIG.ENDPOINTS.STREAM}/${jobId}?ticket=${encodeURIComponent(ticket)}&since=${received}`);
    let opened = false;

    ws.onopen = () => {
      opened = true;
      connected = true;
      attempts = 0;
      onOpen?.();
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'ping') return;
        received++;
        onEvent?.(data);
        if (data.type === 'result' || data.type === 'error') terminal = true;
      } catch (err) {
        onError?.(new Error(`Failed to parse event: ${err.message}`));
      }
    };

    ws.onerror = () => onError?.(new Error('WebSocket connection error'));

    ws.onclose = () => {
      connected = false;
      // Let a final message that raced the close frame be processed first.
      setTimeout(() => {
        if (terminal) return finish({ clean: true });
        // Rejected before opening: job unknown to this device or ticket refused.
        // Retry a few times (it may be a transient network failure), then give up.
        if (!opened && attempts >= 5) {
          return finish({ clean: false, reason: 'Could not connect to the job stream' });
        }
        scheduleRetry();
      }, 50);
    };
  }

  const api = {
    close() {
      closed = true;
      connected = false;
      liveConnections.delete(api);
      clearTimeout(retryTimer);
      if (ws && ws.readyState <= WebSocket.OPEN) ws.close();
    },
    isConnected: () => connected,
    reconnectNow() {
      if (closed || terminal || connected) return;
      clearTimeout(retryTimer);
      retryTimer = null;
      attempts = 0;
      connect();
    },
  };

  liveConnections.add(api);
  connect();
  return api;
}
