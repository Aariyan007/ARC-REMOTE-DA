/**
 * ARC Controller — Connection Status Component
 */

import appState from '../state/appState.js';

export function renderConnectionStatus() {
  const el = document.createElement('div');
  el.id = 'connection-status';

  function update() {
    let cls, label;
    if (appState.useMocks && !appState.connected) {
      cls = 'connection-status--mock';
      label = 'Mock Mode';
    } else if (appState.connected && appState.backendBooted) {
      cls = 'connection-status--connected';
      label = 'Connected';
    } else if (appState.connected && !appState.backendBooted) {
      cls = 'connection-status--mock';
      label = 'Booting...';
    } else if (appState.useMocks) {
      cls = 'connection-status--mock';
      label = 'Mock Mode';
    } else {
      cls = 'connection-status--disconnected';
      label = 'Disconnected';
    }

    el.className = `connection-status ${cls}`;
    el.innerHTML = `<span class="connection-status__dot"></span><span>${label}</span>`;
  }

  update();
  appState.subscribe(update);
  return el;
}
