/**
 * ARC Controller — Error handling utilities
 */

export class ArcError extends Error {
  constructor(type, message, details = null) {
    super(message);
    this.type = type;
    this.details = details;
  }
}

export const ErrorTypes = {
  NETWORK: 'NETWORK',
  TIMEOUT: 'TIMEOUT',
  SERVER: 'SERVER',
  PARSE: 'PARSE',
  WEBSOCKET: 'WEBSOCKET',
  NOT_FOUND: 'NOT_FOUND',
  UNAVAILABLE: 'UNAVAILABLE',
};

/** Classify an error into a user-friendly message */
export function classifyError(error) {
  if (error instanceof ArcError) {
    return { type: error.type, message: error.message, details: error.details };
  }

  if (error?.name === 'AbortError' || error?.message?.includes('timeout')) {
    return { type: ErrorTypes.TIMEOUT, message: 'Request timed out. The backend may be busy.', details: null };
  }

  if (error?.name === 'TypeError' && error?.message?.includes('fetch')) {
    return { type: ErrorTypes.NETWORK, message: 'Cannot reach ARC backend. Is the daemon running?', details: null };
  }

  if (error?.status === 503) {
    return { type: ErrorTypes.UNAVAILABLE, message: 'ARC backend is still booting. Try again in a few seconds.', details: null };
  }

  if (error?.status === 404) {
    return { type: ErrorTypes.NOT_FOUND, message: 'Resource not found on the server.', details: null };
  }

  if (error?.status >= 500) {
    return { type: ErrorTypes.SERVER, message: 'ARC backend encountered an internal error.', details: error.statusText };
  }

  return {
    type: ErrorTypes.SERVER,
    message: error?.message || 'An unexpected error occurred.',
    details: null,
  };
}

/** Get icon for error type */
export function getErrorIcon(type) {
  const icons = {
    [ErrorTypes.NETWORK]: '🌐',
    [ErrorTypes.TIMEOUT]: '⏱️',
    [ErrorTypes.SERVER]: '💥',
    [ErrorTypes.WEBSOCKET]: '🔌',
    [ErrorTypes.UNAVAILABLE]: '🔄',
    [ErrorTypes.NOT_FOUND]: '🔍',
  };
  return icons[type] || '⚠️';
}
