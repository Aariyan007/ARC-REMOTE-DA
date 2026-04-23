/**
 * ARC Controller — Job Store
 * Manages job sessions and their event timelines.
 */

import CONFIG from '../utils/config.js';

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
  }

  /** Subscribe to state changes */
  subscribe(fn) {
    this._listeners.add(fn);
    return () => this._listeners.delete(fn);
  }

  _notify() {
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
        job.needsInput = true;
        job.pendingEventType = 'clarify';
        break;
      case 'confirm':
        job.needsInput = true;
        job.pendingEventType = 'confirm';
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
    this._notify();
  }

  /** Send a reply to a job */
  async replyToJob(jobId, answer) {
    const { sendReply } = await import('../api/http.js');
    await sendReply(jobId, answer);
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
}

// Singleton
const jobStore = new JobStore();
export default jobStore;
