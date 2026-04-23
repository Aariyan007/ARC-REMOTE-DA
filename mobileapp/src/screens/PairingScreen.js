import { pairDevice } from '../api/http.js';
import appState from '../state/appState.js';
import { mountMainScreen } from './MainScreen.js';

export function mountPairingScreen() {
  const root = document.getElementById('app');
  root.innerHTML = `
    <div class="pairing-screen" style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh;padding:2rem;">
      <h1 style="font-size:2rem;margin-bottom:1rem;color:var(--text-primary);">Pair ARC Device</h1>
      <p style="text-align:center;color:var(--text-secondary);margin-bottom:2rem;">Enter the 6-digit code shown on your ARC desktop terminal to connect.</p>
      
      <input type="text" id="pairing-code" placeholder="000000" maxlength="6" style="font-size:2rem;text-align:center;letter-spacing:0.5rem;padding:1rem;border-radius:12px;border:1px solid var(--border-color);background:var(--bg-secondary);color:var(--text-primary);width:100%;max-width:300px;margin-bottom:1rem;" />
      <input type="text" id="device-name" placeholder="Device Name (e.g. My iPhone)" style="padding:1rem;border-radius:12px;border:1px solid var(--border-color);background:var(--bg-secondary);color:var(--text-primary);width:100%;max-width:300px;margin-bottom:2rem;" />
      
      <button id="pair-btn" style="background:var(--accent-color);color:white;border:none;padding:1rem 2rem;border-radius:12px;font-size:1.1rem;font-weight:600;cursor:pointer;width:100%;max-width:300px;">Connect</button>
      <div id="pair-error" style="color:var(--error-color);margin-top:1rem;height:1.5rem;font-weight:500;"></div>
    </div>
  `;

  const pairBtn = document.getElementById('pair-btn');
  const codeInput = document.getElementById('pairing-code');
  const nameInput = document.getElementById('device-name');
  const errorDiv = document.getElementById('pair-error');

  pairBtn.addEventListener('click', async () => {
    const code = codeInput.value.trim();
    let name = nameInput.value.trim();
    
    if (!code || code.length !== 6) {
      errorDiv.textContent = 'Please enter a valid 6-digit code.';
      return;
    }
    
    if (!name) {
      name = 'Mobile Device';
    }

    try {
      pairBtn.disabled = true;
      pairBtn.textContent = 'Connecting...';
      errorDiv.textContent = '';
      
      const res = await pairDevice(code, name);
      if (res.token) {
        appState.setToken(res.token);
        // main.js subscriber will automatically unmount PairingScreen and mount MainScreen
      }
    } catch (err) {
      console.error('Pairing failed:', err);
      errorDiv.textContent = 'Pairing failed: Invalid code or server unreachable.';
    } finally {
      pairBtn.disabled = false;
      pairBtn.textContent = 'Connect';
    }
  });
}
