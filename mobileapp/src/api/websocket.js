/**
 * ARC Controller — WebSocket Manager
 * Manages WebSocket connections for real-time job event streaming.
 */

import CONFIG from '../utils/config.js';

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

  function connect() {
    if (closed) return;

    const url = `${CONFIG.WS_BASE}${CONFIG.ENDPOINTS.STREAM}/${jobId}`;
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

        // Terminal events — server will close, but we mark our side too
        if (data.type === 'result' || data.type === 'error') {
          closed = true;
          connected = false;
        }
      } catch (err) {
        onError?.(new Error(`Failed to parse event: ${err.message}`));
      }
    };

    ws.onerror = (event) => {
      onError?.(new Error('WebSocket connection error'));
    };

    ws.onclose = (event) => {
      connected = false;

      if (closed) {
        onClose?.({ clean: true });
        return;
      }

      // Attempt reconnect
      if (reconnectAttempts < CONFIG.WS_MAX_RECONNECTS) {
        reconnectAttempts++;
        const delay = CONFIG.WS_RECONNECT_DELAY * Math.pow(2, reconnectAttempts - 1);
        setTimeout(connect, delay);
      } else {
        closed = true;
        onClose?.({ clean: false, reason: 'Max reconnection attempts reached' });
      }
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
