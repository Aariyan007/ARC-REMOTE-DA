/**
 * ARC Controller — Application Entry Point
 * Bootstraps the app, checks backend health, and mounts the UI.
 */

import './styles/index.css';
import './styles/components.css';
import './styles/animations.css';
import { checkHealth, refreshToken } from './api/http.js';
import { initLifecycle } from './services/lifecycle.js';
import { getItem, setItem } from './utils/storage.js';
import appState from './state/appState.js';
import { mountMainScreen } from './screens/MainScreen.js';
import { mountPairingScreen } from './screens/PairingScreen.js';
import jobStore from './state/jobStore.js';
import CONFIG from './utils/config.js';

let healthTimer = null;

/**
 * Check backend health and update app state.
 */
async function performHealthCheck() {
  try {
    const res = await checkHealth();
    appState.setConnected(true);
    appState.setBackendBooted(res.booted === true);
    maybeRefreshToken();
  } catch {
    appState.setConnected(false);
    appState.setBackendBooted(false);
  }
}

/** Rotate the 30-day token weekly so an active device never expires. */
async function maybeRefreshToken() {
  if (!appState.token || appState.useMocks) return;
  const last = Number(await getItem('token_refreshed')) || 0;
  if (Date.now() - last < CONFIG.TOKEN_REFRESH_INTERVAL) return;
  try {
    appState.setToken(await refreshToken());
    await setItem('token_refreshed', String(Date.now()));
  } catch { /* try again next check */ }
}

/**
 * Initialize the application.
 */
async function init() {
  await appState.load();
  jobStore.restore();

  // Initial health check (no silent fallback to fake data if it fails —
  // the header shows the disconnected state instead)
  await performHealthCheck();

  // Keep track of current screen so we don't remount unnecessarily
  let currentScreen = null;

  function renderScreen() {
    const shouldBePairing = !appState.token;
    if (shouldBePairing && currentScreen !== 'pairing') {
      if (currentScreen === 'main') jobStore.clearAllJobs(); // signed out / revoked
      mountPairingScreen();
      currentScreen = 'pairing';
    } else if (!shouldBePairing && currentScreen !== 'main') {
      mountMainScreen();
      currentScreen = 'main';
    }
  }

  // Initial render
  renderScreen();

  // Re-render when token changes (e.g. login or automatic logout)
  appState.subscribe(renderScreen);

  const mockBtn = document.getElementById('mock-toggle-btn');
  if (mockBtn) mockBtn.classList.toggle('active', appState.useMocks);

  // Periodic health checks; resume/foreground handled by lifecycle
  healthTimer = setInterval(() => { if (!document.hidden) performHealthCheck(); }, CONFIG.HEALTH_CHECK_INTERVAL);
  initLifecycle({ onResume: performHealthCheck });

  console.log('ARC Controller initialized.');
}

// Boot
document.addEventListener('DOMContentLoaded', init);
