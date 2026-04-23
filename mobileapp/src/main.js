/**
 * ARC Controller — Application Entry Point
 * Bootstraps the app, checks backend health, and mounts the UI.
 */

import './styles/index.css';
import './styles/components.css';
import './styles/animations.css';
import { checkHealth } from './api/http.js';
import appState from './state/appState.js';
import { mountMainScreen } from './screens/MainScreen.js';
import { mountPairingScreen } from './screens/PairingScreen.js';
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

    // If backend is fully booted, disable mock mode
    if (res.booted && appState.useMocks) {
      appState.setUseMocks(false);
      const mockBtn = document.getElementById('mock-toggle-btn');
      if (mockBtn) mockBtn.classList.remove('active');
      console.log('ARC backend is ready — switching to live mode.');
    }
  } catch {
    appState.setConnected(false);
    appState.setBackendBooted(false);
  }
}

/**
 * Initialize the application.
 */
async function init() {
  // Initial health check
  await performHealthCheck();

  // If backend is not available or not booted, enable mock mode
  if (!appState.connected || !appState.backendBooted) {
    appState.setUseMocks(true);
    if (!appState.connected) {
      console.log('ARC backend not reachable — mock mode enabled.');
    } else {
      console.log('ARC backend still booting — mock mode enabled until ready.');
    }
  }

  // Keep track of current screen so we don't remount unnecessarily
  let currentScreen = null;

  function renderScreen() {
    const shouldBePairing = !appState.token;
    if (shouldBePairing && currentScreen !== 'pairing') {
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

  // Update mock toggle button state
  const mockBtn = document.getElementById('mock-toggle-btn');
  if (mockBtn) {
    mockBtn.classList.toggle('active', appState.useMocks);
  }

  // Periodic health checks (only when tab is visible)
  healthTimer = setInterval(performHealthCheck, CONFIG.HEALTH_CHECK_INTERVAL);

  // Pause health checks when tab is hidden
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      clearInterval(healthTimer);
      healthTimer = null;
    } else {
      performHealthCheck();
      healthTimer = setInterval(performHealthCheck, CONFIG.HEALTH_CHECK_INTERVAL);
    }
  });

  console.log('ARC Controller initialized.');
}

// Boot
document.addEventListener('DOMContentLoaded', init);
