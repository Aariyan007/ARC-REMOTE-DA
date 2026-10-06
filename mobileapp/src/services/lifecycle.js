/**
 * App lifecycle: reconnect streams and re-check health when the app returns to the
 * foreground or the network comes back; handle arc://pair deep links.
 */
import { App } from '@capacitor/app';
import { Network } from '@capacitor/network';
import { isNative } from '../utils/platform.js';
import { parsePairingLink } from '../utils/pairing.js';
import { reconnectAll } from '../api/websocket.js';

export function initLifecycle({ onResume }) {
  const resume = () => { reconnectAll(); onResume?.(); };

  document.addEventListener('visibilitychange', () => { if (!document.hidden) resume(); });
  window.addEventListener('online', resume);

  if (!isNative()) return;

  App.addListener('appStateChange', ({ isActive }) => { if (isActive) resume(); });
  Network.addListener('networkStatusChange', ({ connected }) => { if (connected) resume(); });
  App.addListener('appUrlOpen', ({ url }) => {
    const link = parsePairingLink(url);
    if (link && window.__arcOnPairLink) window.__arcOnPairLink(link);
  });
}
