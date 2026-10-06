/**
 * ARC Controller — Configuration
 * Server URL is runtime state (appState.serverUrl); see apiBase()/wsBase().
 */
import appState from '../state/appState.js';
import { toWsUrl } from './pairing.js';

const CONFIG = {
  // Endpoints
  ENDPOINTS: {
    COMMAND: '/command',
    REPLY: '/reply',     // + /{job_id}
    STREAM: '/stream',   // + /{job_id}
  },

  // Timeouts
  HTTP_TIMEOUT: 8000,
  WS_RECONNECT_DELAY: 1000,
  WS_MAX_RECONNECT_DELAY: 15000,
  HEALTH_CHECK_INTERVAL: 30000,
  TOKEN_REFRESH_INTERVAL: 7 * 24 * 3600 * 1000,
  REPLY_TIMEOUT: 120000,

  // UI
  MAX_COMMAND_HISTORY: 20,
  MAX_JOBS_DISPLAY: 50,
};

export const apiBase = () => appState.serverUrl || '';
export const wsBase = () => toWsUrl(appState.serverUrl || location.origin);

export default CONFIG;
