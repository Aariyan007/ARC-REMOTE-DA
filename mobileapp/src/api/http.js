/**
 * ARC Controller — HTTP API Client
 * Communicates with the ARC backend over HTTP.
 */

import CONFIG from '../utils/config.js';
import { ArcError, ErrorTypes } from '../utils/errors.js';
import appState from '../state/appState.js';

/**
 * Make an HTTP request with timeout and error handling.
 */
async function request(method, path, body = null) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), CONFIG.HTTP_TIMEOUT);

  try {
    const headers = { 'Content-Type': 'application/json' };
    if (appState.token) {
      headers['Authorization'] = `Bearer ${appState.token}`;
    }

    const options = {
      method,
      headers,
      signal: controller.signal,
    };

    if (body) {
      options.body = JSON.stringify(body);
    }

    const url = `${CONFIG.API_BASE}${path}`;
    const res = await fetch(url, options);

    if (!res.ok) {
      if (res.status === 401) {
        appState.setToken(null); // Clear token and return to pairing screen
      }
      const detail = await res.text().catch(() => res.statusText);
      throw Object.assign(new Error(detail), { status: res.status, statusText: res.statusText });
    }

    return await res.json();
  } catch (err) {
    if (err.name === 'AbortError') {
      throw new ArcError(ErrorTypes.TIMEOUT, 'Request timed out');
    }
    throw err;
  } finally {
    clearTimeout(timeout);
  }
}

/**
 * POST /command — Submit a natural language command.
 * @param {string} text - The command text
 * @returns {Promise<{job_id: string}>}
 */
export async function sendCommand(text) {
  return request('POST', CONFIG.ENDPOINTS.COMMAND, {
    text,
    source: 'controller',
    user: 'user',
  });
}

/**
 * POST /reply/{jobId} — Answer a clarify or confirm event.
 * @param {string} jobId - The job ID
 * @param {string} answer - The user's response
 * @returns {Promise<{status: string}>}
 */
export async function sendReply(jobId, answer) {
  return request('POST', `${CONFIG.ENDPOINTS.REPLY}/${jobId}`, { answer });
}

/**
 * POST /pair — Pair device using 6-digit code.
 * @param {string} code - The pairing code
 * @param {string} deviceName - Name of this device
 * @returns {Promise<{token: string}>}
 */
export async function pairDevice(code, deviceName) {
  return request('POST', '/pair', { code, device_name: deviceName });
}

/**
 * Check if the ARC backend is reachable and booted.
 * Strategy: GET /command → 405 = booted, 503 = still booting, network error = unreachable.
 * @returns {Promise<{status: string, booted: boolean}>}
 */
export async function checkHealth() {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), CONFIG.HTTP_TIMEOUT);

  try {
    const url = `${CONFIG.API_BASE}/health`;
    const res = await fetch(url, { method: 'GET', signal: controller.signal });
    const data = await res.json().catch(() => ({ status: 'ok', booted: true }));

    // If we have a token and the server is booted, probe /command to check token validity
    if (appState.token && data.booted) {
      try {
        const probeRes = await fetch(`${CONFIG.API_BASE}/jobs/health_check_ping`, {
          method: 'GET',
          headers: {
            'Authorization': `Bearer ${appState.token}`
          },
          signal: controller.signal
        });
        if (probeRes.status === 401) {
          appState.setToken(null); // Instantly log out if token is invalid
        }
      } catch (e) {
        // Ignore probe errors
      }
    }

    return { status: 'ok', booted: data.booted };
  } catch (err) {
    if (err.name === 'AbortError') {
      throw new ArcError(ErrorTypes.TIMEOUT, 'Health check timed out');
    }
    // Network error = truly unreachable
    throw err;
  } finally {
    clearTimeout(timeout);
  }
}
