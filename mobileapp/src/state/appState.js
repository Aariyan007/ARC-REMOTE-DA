/**
 * ARC Controller — Global App State
 * Tracks server URL, auth token, connection status and (dev-only) mock mode.
 */
import { getItem, setItem, removeItem } from '../utils/storage.js';
import { isNative } from '../utils/platform.js';

// Mock mode is a development aid only. It can never switch on in a production
// build, so a failed connection can't silently show fake results.
const MOCKS_ALLOWED = import.meta.env?.DEV === true;

class AppState {
  constructor() {
    this.connected = false;
    this.backendBooted = false;
    this.chatEnabled = false;
    this.chatSessionId = null;
    this.useMocks = false;
    this.checking = false;
    this.token = null;
    this.serverUrl = '';
    this.loaded = false;
    /** @type {Set<Function>} */
    this._listeners = new Set();
  }

  /** Load persisted settings. Must complete before the first render. */
  async load() {
    this.token = await getItem('token');
    this.chatSessionId = await getItem('chat_session');
    const stored = await getItem('server_url');
    // Browser build served by the daemon itself talks to its own origin.
    this.serverUrl = stored || (isNative() ? '' : location.origin);
    this.useMocks = MOCKS_ALLOWED && localStorage.getItem('arc_use_mocks') === 'true';
    this.loaded = true;
  }

  subscribe(fn) {
    this._listeners.add(fn);
    return () => this._listeners.delete(fn);
  }

  _notify() {
    for (const fn of this._listeners) {
      try { fn(); } catch (e) { console.error('AppState listener error:', e); }
    }
  }

  setConnected(val) {
    if (this.connected !== val) {
      this.connected = val;
      this._notify();
    }
  }

  setBackendBooted(val) {
    if (this.backendBooted !== val) {
      this.backendBooted = val;
      this._notify();
    }
  }

  setChatEnabled(val) {
    if (this.chatEnabled !== val) {
      this.chatEnabled = val;
      this._notify();
    }
  }

  /** Session id for the current conversation; created on first use, reset by "Clear". */
  getChatSessionId() {
    if (!this.chatSessionId) {
      const bytes = new Uint8Array(12);
      crypto.getRandomValues(bytes);
      this.chatSessionId = Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
      setItem('chat_session', this.chatSessionId);
    }
    return this.chatSessionId;
  }

  resetChatSession() {
    this.chatSessionId = null;
    removeItem('chat_session');
  }

  setUseMocks(val) {
    val = MOCKS_ALLOWED && !!val;
    if (this.useMocks !== val) {
      this.useMocks = val;
      if (val) {
        localStorage.setItem('arc_use_mocks', 'true');
      } else {
        localStorage.removeItem('arc_use_mocks');
      }
      this._notify();
    }
  }

  toggleMocks() {
    this.setUseMocks(!this.useMocks);
  }

  setServerUrl(url) {
    if (this.serverUrl !== url) {
      this.serverUrl = url;
      setItem('server_url', url);
      this._notify();
    }
  }

  setToken(val) {
    if (this.token !== val) {
      this.token = val;
      if (val) {
        setItem('token', val);
      } else {
        removeItem('token');
      }
      this._notify();
    }
  }
}

export const MOCKS_ENABLED_IN_BUILD = MOCKS_ALLOWED;
const appState = new AppState();
export default appState;
