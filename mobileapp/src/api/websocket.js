/**
 * ARC Controller — WebSocket Manager
 * Manages WebSocket connections for real-time job event streaming.
 *
 * Fixes applied:
 * - BUG 5:  Token now appended as ?token=... query param (server requires auth)
 * - BUG 10: terminalEventReceived flag separates clean server-close from dirty
 *           disconnect so onClose() gets the right signal
 */

import CONFIG from '../utils/config.js';
import appState from '../state/appState.js';

/**
 * Connect to a job's event stream via WebSocket.
 * @param {string} jobId - The job ID to stream events for
 * @param {object} callbacks - { onEvent, onError, onClose, onOpen }
 * @returns {{ close: Function, isConnected: Function }}
 */
export function connectToJob(jobId, callbacks = {}) {
  const { onEvent, onError, onClose, onOpen } = callbacks;

  let ws = null;
  let reconnectAttempts = 0;
  let closed = false;
  let connected = false;
  // BUG 10 FIX: separate "terminal event received" from "manually closed"
  let terminalEventReceived = false;

  function connect() {
    if (closed) return;

    // BUG 5 FIX: send auth token as query param — browser WS can't set headers
    const token = appState.token || '';
    const tokenParam = token ? `?token=${encodeURIComponent(token)}` : '';
    const url = `${CONFIG.WS_BASE}${CONFIG.ENDPOINTS.STREAM}/${jobId}${tokenParam}`;
    ws = new WebSocket(url);

    ws.onopen = () => {
      connected = true;
      reconnectAttempts = 0;
      onOpen?.();
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        onEvent?.(data);
        // Mark terminal but don't prematurely set closed — server closes next
        if (data.type === 'result' || data.type === 'error') {
          terminalEventReceived = true;
        }
      } catch (err) {
        onError?.(new Error(`Failed to parse event: ${err.message}`));
      }
    };

    ws.onerror = () => {
      onError?.(new Error('WebSocket connection error'));
    };

    ws.onclose = () => {
      connected = false;

      // BUG-F FIX: In some browsers the TCP close frame can arrive before the
      // final 'message' frame is processed by onmessage. Without a grace period,
      // terminalEventReceived would still be false, triggering a spurious
      // reconnect attempt and showing a 'Connection lost' error in the timeline.
      // 50ms is enough for the microtask queue to process the pending message.
      setTimeout(() => {
        if (closed || terminalEventReceived) {
          onClose?.({ clean: true });
          return;
        }

        // Attempt reconnect on unexpected close
        if (reconnectAttempts < CONFIG.WS_MAX_RECONNECTS) {
          reconnectAttempts++;
          const delay = CONFIG.WS_RECONNECT_DELAY * Math.pow(2, reconnectAttempts - 1);
          setTimeout(connect, delay);
        } else {
          closed = true;
          onClose?.({ clean: false, reason: 'Max reconnection attempts reached' });
        }
      }, 50);
    };
  }

  connect();

  return {
    close() {
      closed = true;
      connected = false;
      if (ws && ws.readyState <= WebSocket.OPEN) {
        ws.close();
      }
    },
    isConnected() {
      return connected;
    },
  };
}
