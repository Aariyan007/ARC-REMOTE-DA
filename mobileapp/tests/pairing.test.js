import { describe, it, expect } from 'vitest';
import { normalizeServerUrl, parsePairingLink, toWsUrl } from '../src/utils/pairing.js';

describe('normalizeServerUrl', () => {
  it('adds http:// and strips trailing slashes', () => {
    expect(normalizeServerUrl('192.168.1.5:8000/')).toBe('http://192.168.1.5:8000');
    expect(normalizeServerUrl('https://mac.tail.ts.net///')).toBe('https://mac.tail.ts.net');
  });
  it('rejects empty and non-http schemes', () => {
    expect(normalizeServerUrl('')).toBe('');
    expect(normalizeServerUrl('javascript:alert(1)')).toBe('');
    expect(normalizeServerUrl('ftp://x')).toBe('');
  });
});

describe('parsePairingLink', () => {
  it('parses a valid link', () => {
    const link = `arc://pair?u=${encodeURIComponent('https://mac.tail.ts.net')}&c=123456`;
    expect(parsePairingLink(link)).toEqual({ url: 'https://mac.tail.ts.net', code: '123456' });
  });
  it('rejects wrong scheme/host, bad code, bad url', () => {
    expect(parsePairingLink('https://pair?u=http://x&c=123456')).toBeNull();
    expect(parsePairingLink('arc://other?u=http://x&c=123456')).toBeNull();
    expect(parsePairingLink('arc://pair?u=http://x&c=12345')).toBeNull();
    expect(parsePairingLink('arc://pair?u=javascript:x&c=123456')).toBeNull();
    expect(parsePairingLink('garbage')).toBeNull();
    expect(parsePairingLink(null)).toBeNull();
  });
});

describe('toWsUrl', () => {
  it('maps schemes', () => {
    expect(toWsUrl('http://a:1')).toBe('ws://a:1');
    expect(toWsUrl('https://a')).toBe('wss://a');
  });
});
