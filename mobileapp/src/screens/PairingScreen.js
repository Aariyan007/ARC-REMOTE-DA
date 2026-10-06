import { pairDevice } from '../api/http.js';
import appState from '../state/appState.js';
import { isNative, platformName } from '../utils/platform.js';
import { normalizeServerUrl, parsePairingLink } from '../utils/pairing.js';
import { scanPairingQr } from '../services/scanner.js';

const FIELD_STYLE = 'padding:1rem;border-radius:12px;border:1px solid var(--border-color);background:var(--bg-secondary);color:var(--text-primary);width:100%;max-width:300px;margin-bottom:1rem;';

function defaultDeviceName() {
  const p = platformName();
  return p === 'ios' ? 'My iPhone' : p === 'android' ? 'My Android' : 'Mobile Device';
}

function friendlyError(err) {
  if (err.status === 429) {
    const mins = Math.max(1, Math.ceil((err.retryAfter || 60) / 60));
    return `Too many attempts. Try again in ~${mins} min, or run "python -m remote.pair" on your computer.`;
  }
  if (err.status === 401) return 'Wrong or expired code. Run "python -m remote.pair" for a fresh one.';
  if (err.status) return `Server error (${err.status}): ${err.detail || 'unexpected response'}`;
  return `Can't reach the server at ${appState.serverUrl || 'the address you entered'}. Check the address, your network, and that Tailscale is connected.`;
}

export function mountPairingScreen() {
  const root = document.getElementById('app');
  const native = isNative();

  root.innerHTML = `
    <div class="pairing-screen" style="display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:100vh;padding:2rem;">
      <h1 style="font-size:2rem;margin-bottom:1rem;color:var(--text-primary);">Pair ARC Device</h1>
      <p id="pair-help" style="text-align:center;color:var(--text-secondary);margin-bottom:1.5rem;max-width:320px;"></p>
      <button id="scan-btn" type="button" style="display:none;background:transparent;color:var(--accent-color);border:1px solid var(--accent-color);padding:0.9rem 2rem;border-radius:12px;font-size:1rem;font-weight:600;cursor:pointer;width:100%;max-width:300px;margin-bottom:1.25rem;">Scan QR code</button>
      <input type="url" id="server-url" inputmode="url" autocapitalize="off" autocorrect="off" spellcheck="false" placeholder="Server address (https://my-mac.ts.net)" style="${FIELD_STYLE}display:none;" />
      <input type="text" id="pairing-code" inputmode="numeric" pattern="[0-9]*" autocomplete="one-time-code" placeholder="000000" maxlength="6" style="font-size:2rem;text-align:center;letter-spacing:0.5rem;${FIELD_STYLE}" />
      <input type="text" id="device-name" placeholder="Device name" style="${FIELD_STYLE}margin-bottom:2rem;" />
      <button id="pair-btn" type="button" style="background:var(--accent-color);color:white;border:none;padding:1rem 2rem;border-radius:12px;font-size:1.1rem;font-weight:600;cursor:pointer;width:100%;max-width:300px;">Connect</button>
      <div id="pair-error" role="alert" style="color:var(--error-color);margin-top:1rem;min-height:1.5rem;font-weight:500;text-align:center;max-width:320px;"></div>
    </div>
  `;

  const help = root.querySelector('#pair-help');
  const scanBtn = root.querySelector('#scan-btn');
  const urlInput = root.querySelector('#server-url');
  const pairBtn = root.querySelector('#pair-btn');
  const codeInput = root.querySelector('#pairing-code');
  const nameInput = root.querySelector('#device-name');
  const errorDiv = root.querySelector('#pair-error');

  help.textContent = native
    ? 'On your computer run "python -m remote.pair", then scan the QR code — or enter the server address and 6-digit code.'
    : 'Enter the 6-digit code shown on your ARC desktop terminal to connect.';
  if (native) {
    urlInput.style.display = 'block';
    scanBtn.style.display = 'block';
    urlInput.value = appState.serverUrl || '';
  }
  nameInput.value = defaultDeviceName();

  codeInput.addEventListener('input', () => {
    codeInput.value = codeInput.value.replace(/\D/g, '').slice(0, 6);
  });

  async function pair(url, code, name) {
    errorDiv.textContent = '';
    pairBtn.disabled = true;
    pairBtn.textContent = 'Connecting...';
    try {
      if (url) appState.setServerUrl(url);
      const res = await pairDevice(code, name);
      if (res.token) appState.setToken(res.token); // main.js swaps in the main screen
    } catch (err) {
      console.error('Pairing failed:', err);
      errorDiv.textContent = friendlyError(err);
    } finally {
      pairBtn.disabled = false;
      pairBtn.textContent = 'Connect';
    }
  }

  function applyLink(link) {
    urlInput.value = link.url;
    codeInput.value = link.code;
    return pair(link.url, link.code, nameInput.value.trim() || defaultDeviceName());
  }

  scanBtn.addEventListener('click', async () => {
    errorDiv.textContent = '';
    try {
      const raw = await scanPairingQr();
      if (!raw) return; // cancelled
      const link = parsePairingLink(raw);
      if (!link) {
        errorDiv.textContent = 'That QR code is not an ARC pairing code.';
        return;
      }
      await applyLink(link);
    } catch (err) {
      errorDiv.textContent = err.message || 'Could not open the camera. Enter the details manually.';
    }
  });

  pairBtn.addEventListener('click', () => {
    const code = codeInput.value.trim();
    const name = nameInput.value.trim() || defaultDeviceName();
    let url = '';
    if (native) {
      url = normalizeServerUrl(urlInput.value);
      if (!url) {
        errorDiv.textContent = 'Enter the server address, e.g. https://my-mac.tailnet.ts.net';
        return;
      }
    }
    if (!/^\d{6}$/.test(code)) {
      errorDiv.textContent = 'Please enter a valid 6-digit code.';
      return;
    }
    pair(url, code, name);
  });

  // arc://pair?... opened from the system camera / a link
  window.__arcOnPairLink = applyLink;
}
