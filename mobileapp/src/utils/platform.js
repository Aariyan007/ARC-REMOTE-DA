/**
 * ARC Controller — platform helpers (Capacitor native vs plain browser)
 */
import { Capacitor } from '@capacitor/core';

export const isNative = () => {
  try { return Capacitor.isNativePlatform(); } catch { return false; }
};

export const platformName = () => {
  try { return Capacitor.getPlatform(); } catch { return 'web'; }
};
