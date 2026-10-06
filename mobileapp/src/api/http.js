/**
 * ARC Controller — HTTP API Client
 * Communicates with the ARC backend over HTTP.
 */

import CONFIG, { apiBase } from '../utils/config.js';
import { ArcError, ErrorTypes } from '../utils/errors.js';
import appState from '../state/appState.js';

async function parseBody(res) {
  const text = await res.text().catch(() => '');
  if (!text) return {};
  try { return JSON.parse(text); } catch { return { detail: text }; }
}

/**
 * Make an HTTP request with timeout and error handling.
 * Errors carry `.status`, `.detail` and (for 429) `.retryAfter` seconds.
 */
async function request(method, path, body = null, { auth = true } = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), CONFIG.HTTP_TIMEOUT);

  try {
    const headers = { 'Content-Type': 'application/json' };
    if (auth && appState.token) {
      headers['Authorization'] = `Bearer ${appState.token}`;
    }

    const options = { method, headers, signal: controller.signal };
    if (body) options.body = JSON.stringify(body);

    const res = await fetch(`${apiBase()}${path}`, options);
    const data = await parseBody(res);

    if (!res.ok) {
      if (res.status === 401 && auth) {
        appState.setToken(null); // revoked/expired: back to the pairing screen
      }
      const detail = typeof data.detail === 'string' ? data.detail : res.statusText;
      throw Object.assign(new Error(detail), {
        status: res.status,
        detail,
        retryAfter: Number(res.headers.get('Retry-After')) || 0,
      });
    }
    return data;
  } catch (err) {
    if (err.name === 'AbortError') {
      throw new ArcError(ErrorTypes.TIMEOUT, 'Request timed out');
    }
    throw err;
  } finally {
    clearTimeout(timeout);
  }
}

/** POST /command — Submit a natural language command. */
export async function sendCommand(text) {
  return request('POST', CONFIG.ENDPOINTS.COMMAND, { text, source: 'mobile' });
}

/** POST /tools/{tool} — run a structured tool; returns {job_id} like /command. */
export async function runTool(tool, args = {}) {
  return request('POST', `/tools/${encodeURIComponent(tool)}`, { args });
}

/** POST /reply/{jobId} — Answer a clarify or confirm event (nonce binds it to that prompt). */
export async function sendReply(jobId, answer, nonce) {
  return request('POST', `${CONFIG.ENDPOINTS.REPLY}/${jobId}`, { answer, nonce });
}

/** POST /jobs/{jobId}/cancel */
export async function cancelJob(jobId) {
  return request('POST', `/jobs/${jobId}/cancel`);
}

/** GET /jobs/{jobId}?since=n — poll events (used to catch up after a gap). */
export async function fetchJob(jobId, since = 0) {
  return request('GET', `/jobs/${jobId}?since=${since}`);
}

/** POST /ws-ticket — one-time ticket so the bearer token never appears in a URL. */
export async function getWsTicket() {
  return (await request('POST', '/ws-ticket')).ticket;
}

/** POST /pair */
export async function pairDevice(code, deviceName) {
  return request('POST', '/pair', { code, device_name: deviceName }, { auth: false });
}

/** POST /auth/refresh */
export async function refreshToken() {
  return (await request('POST', '/auth/refresh')).token;
}

/** GET /devices, DELETE /devices/{id} */
export async function listDevices() {
  return request('GET', '/devices');
}
export async function revokeDevice(id) {
  return request('DELETE', `/devices/${id}`);
}

/** GET /health — reachable? booted? Validates the token too when one is set. */
export async function checkHealth() {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), CONFIG.HTTP_TIMEOUT);

  try {
    const res = await fetch(`${apiBase()}/health`, { method: 'GET', signal: controller.signal });
    const data = await parseBody(res);

    if (appState.token && data.booted) {
      try {
        const probe = await fetch(`${apiBase()}/jobs/health_check_ping`, {
          headers: { Authorization: `Bearer ${appState.token}` },
          signal: controller.signal,
        });
        if (probe.status === 401) appState.setToken(null);
      } catch { /* ignore probe errors */ }
    }

    return { status: 'ok', booted: data.booted === true, bootError: data.boot_error || null };
  } catch (err) {
    if (err.name === 'AbortError') {
      throw new ArcError(ErrorTypes.TIMEOUT, 'Health check timed out');
    }
    throw err;
  } finally {
    clearTimeout(timeout);
  }
}

/** GET /suggestions */
export async function fetchSuggestions() {
  return request('GET', '/suggestions');
}
