/**
 * ARC Controller — Configuration
 * All configurable values in one place.
 */

const CONFIG = {
  // API endpoints (proxied through Vite in dev)
  API_BASE: '',
  WS_BASE: `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}`,

  // Endpoints
  ENDPOINTS: {
    COMMAND: '/command',
    REPLY: '/reply',     // + /{job_id}
    STREAM: '/stream',   // + /{job_id}
  },

  // Timeouts
  HTTP_TIMEOUT: 8000,
  WS_RECONNECT_DELAY: 1000,
  WS_MAX_RECONNECTS: 3,
  HEALTH_CHECK_INTERVAL: 30000,
  REPLY_TIMEOUT: 120000,

  // UI
  MAX_COMMAND_HISTORY: 20,
  MAX_JOBS_DISPLAY: 50,
};

export default CONFIG;
