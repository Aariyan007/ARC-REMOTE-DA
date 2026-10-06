/**
 * ARC Controller — storage for secrets and settings.
 *
 * Native: iOS Keychain / Android Keystore via secure-storage.
 * Browser: localStorage (the PWA has no better option).
 * Every call is wrapped so a storage failure never crashes the app.
 */
import { SecureStorage } from '@aparajita/capacitor-secure-storage';
import { isNative } from './platform.js';

const PREFIX = 'arc_';

export async function getItem(key) {
  try {
    if (isNative()) {
      const v = await SecureStorage.get(PREFIX + key, false);
      return typeof v === 'string' ? v : null;
    }
    return localStorage.getItem(PREFIX + key);
  } catch {
    return null;
  }
}

export async function setItem(key, value) {
  try {
    if (isNative()) {
      await SecureStorage.set(PREFIX + key, value, false);
    } else {
      localStorage.setItem(PREFIX + key, value);
    }
  } catch (e) {
    console.warn('storage set failed', e);
  }
}

export async function removeItem(key) {
  try {
    if (isNative()) {
      await SecureStorage.remove(PREFIX + key);
    } else {
      localStorage.removeItem(PREFIX + key);
    }
  } catch { /* nothing stored */ }
}
