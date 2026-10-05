/**
 * Pairing link helpers.
 * The desktop QR encodes:  arc://pair?u=<server url>&c=<6-digit code>
 */

/** Normalise a user-entered server address to an origin-style URL. */
export function normalizeServerUrl(input) {
  let s = String(input || '').trim();
  if (!s) return '';
  if (!/^[a-z][a-z0-9+.-]*:\/\//i.test(s)) s = `http://${s}`;
  try {
    const u = new URL(s);
    if (u.protocol !== 'http:' && u.protocol !== 'https:') return '';
    return u.origin + u.pathname.replace(/\/+$/, '');
  } catch {
    return '';
  }
}

/** Parse an arc://pair link. Returns { url, code } or null. */
export function parsePairingLink(text) {
  try {
    const u = new URL(String(text || '').trim());
    if (u.protocol !== 'arc:' || u.hostname !== 'pair') return null;
    const url = normalizeServerUrl(u.searchParams.get('u'));
    const code = (u.searchParams.get('c') || '').trim();
    if (!url || !/^\d{6}$/.test(code)) return null;
    return { url, code };
  } catch {
    return null;
  }
}

/** http(s) -> ws(s) */
export function toWsUrl(httpUrl) {
  return httpUrl.replace(/^http/i, 'ws');
}
