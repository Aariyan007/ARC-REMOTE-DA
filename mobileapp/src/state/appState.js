/**
 * ARC Controller — Global App State
 * Tracks connection status, mock mode, and backend health.
 */

class AppState {
  constructor() {
    this.connected = false;
    this.backendBooted = false;
    // BUG 16 FIX: useMocks was not persisted — lost on page refresh while token wasn't.
    this.useMocks = localStorage.getItem('arc_use_mocks') === 'true';
    this.checking = false;
    this.token = localStorage.getItem('arc_token') || null;
    /** @type {Set<Function>} */
    this._listeners = new Set();
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

  setUseMocks(val) {
    if (this.useMocks !== val) {
      this.useMocks = val;
      // BUG 16 FIX: persist to localStorage
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

  setToken(val) {
    if (this.token !== val) {
      this.token = val;
      if (val) {
        localStorage.setItem('arc_token', val);
      } else {
        localStorage.removeItem('arc_token');
      }
      this._notify();
    }
  }
}

const appState = new AppState();
export default appState;
