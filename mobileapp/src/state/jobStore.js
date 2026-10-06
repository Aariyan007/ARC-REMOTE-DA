/**
 * ARC Controller — Job Store
 * Manages job sessions and their event timelines.
 */

import CONFIG from '../utils/config.js';

const STORE_KEY = 'arc_jobs_v1';

/** @typedef {'waiting'|'running'|'completed'|'failed'|'needs_confirmation'} JobStatus */

/**
 * @typedef {Object} Job
 * @property {string} id
 * @property {string} command
 * @property {JobStatus} status
 * @property {Array} events
 * @property {number} createdAt
 * @property {number|null} completedAt
 * @property {boolean} needsInput - True when waiting for clarify/confirm reply
 * @property {string|null} pendingEventType - 'clarify' or 'confirm' if waiting
 */

class JobStore {
  constructor() {
    /** @type {Map<string, Job>} */
    this._jobs = new Map();
    /** @type {string|null} */
    this._activeJobId = null;
    /** @type {Set<Function>} */
    this._listeners = new Set();
    this._saveTimer = null;
  }

  /** Persist recent jobs so history and in-flight jobs survive an app restart. */
  _persist() {
    clearTimeout(this._saveTimer);
    this._saveTimer = setTimeout(() => {
      try {
        const jobs = Array.from(this._jobs.values())
          .filter(j => !j.id.startsWith('mock-'))
          .slice(-CONFIG.MAX_COMMAND_HISTORY)
          .map(j => ({ ...j, events: j.events.slice(-100) }));
        localStorage.setItem(STORE_KEY, JSON.stringify(jobs));
      } catch { /* storage full/unavailable: history just won't persist */ }
    }, 300);
  }

  /** Load persisted jobs. Call once at startup. */
  restore() {
    try {
      const jobs = JSON.parse(localStorage.getItem(STORE_KEY) || '[]');
      for (const j of jobs) {
        if (j && j.id && Array.isArray(j.events)) this._jobs.set(j.id, j);
      }
      const last = Array.from(this._jobs.keys()).pop();
      this._activeJobId = last || null;
    } catch { /* corrupt history is ignored */ }
  }

  /** Real (server-side) jobs that hadn't finished when the app last ran. */
  getUnfinishedJobs() {
    return Array.from(this._jobs.values()).filter(
      j => !j.id.startsWith('mock-') && !j.id.startsWith('local-') && !j.id.startsWith('direct-')
        && j.status !== 'completed' && j.status !== 'failed'
    );
  }

  /** Subscribe to state changes */
  subscribe(fn) {
    this._listeners.add(fn);
    return () => this._listeners.delete(fn);
  }

  _notify() {
    this._persist();
    for (const fn of this._listeners) {
      try { fn(); } catch (e) { console.error('JobStore listener error:', e); }
    }
  }

  /** Create a new job */
  createJob(jobId, commandText) {
    const job = {
      id: jobId,
      command: commandText,
      status: 'waiting',
      events: [],
      seen: 0,
      createdAt: Date.now() / 1000,
      completedAt: null,
      needsInput: false,
      pendingEventType: null,
    };
    this._jobs.set(jobId, job);
    this._activeJobId = jobId;
    this._notify();
    return job;
  }

  /** Add an event to a job's timeline */
  addEvent(jobId, event) {
    const job = this._jobs.get(jobId);
    if (!job) return;

    job.events.push(event);

    // Update job status based on event type
    switch (event.type) {
      case 'ack':
        job.status = 'running';
        job.needsInput = false;
        break;
      case 'clarify':
      case 'confirm':
        // BUG-E FIX: status was left as 'running' even though the typedef declares
        // 'needs_confirmation'. Any downstream code branching on this status was
        // silently falling through.
        job.status = 'needs_confirmation';
        job.needsInput = true;
        job.pendingEventType = event.type;
        job.pendingNonce = event.data?.nonce || null;
        break;
      case 'executing':
      case 'progress':
      case 'verify':
        job.status = 'running';
        job.needsInput = false;
        break;
      case 'result':
        job.status = 'completed';
        job.completedAt = Date.now() / 1000;
        job.needsInput = false;
        job.pendingEventType = null;
        break;
      case 'error':
        job.status = 'failed';
        job.completedAt = Date.now() / 1000;
        job.needsInput = false;
        job.pendingEventType = null;
        break;
    }

    this._notify();
  }

  /** Mark that user has replied to a clarify/confirm */
  markReplied(jobId) {
    const job = this._jobs.get(jobId);
    if (!job) return;
    job.needsInput = false;
    job.pendingEventType = null;
    job.pendingNonce = null;
    // Restore 'running' from 'needs_confirmation' (or any non-terminal state)
    // so the typing indicator reappears while the backend processes the reply.
    if (job.status !== 'completed' && job.status !== 'failed') {
      job.status = 'running';
    }
    this._notify();
  }

  /** Send a reply to a job */
  async replyToJob(jobId, answer) {
    const { sendReply } = await import('../api/http.js');
    await sendReply(jobId, answer, this._jobs.get(jobId)?.pendingNonce);
    this.markReplied(jobId);
  }

  /** Get a job by ID */
  getJob(jobId) {
    return this._jobs.get(jobId) || null;
  }

  /** Get the currently active job */
  getActiveJob() {
    if (!this._activeJobId) return null;
    return this._jobs.get(this._activeJobId) || null;
  }

  /** Get active job ID */
  getActiveJobId() {
    return this._activeJobId;
  }

  /** Get all jobs (newest first) */
  getAllJobs() {
    return Array.from(this._jobs.values()).reverse();
  }

  /** Check if a job is in a terminal state */
  isJobDone(jobId) {
    const job = this._jobs.get(jobId);
    return job ? (job.status === 'completed' || job.status === 'failed') : true;
  }

  /** Check if any job is actively waiting for input */
  hasActiveInput() {
    const job = this.getActiveJob();
    return job?.needsInput ?? false;
  }

  /** Clear all jobs and reset state */
  clearAllJobs() {
    this._jobs.clear();
    this._activeJobId = null;
    try { localStorage.removeItem(STORE_KEY); } catch { /* ignore */ }
    this._notify();
  }
}

// Singleton
const jobStore = new JobStore();
export default jobStore;
