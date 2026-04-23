/**
 * ARC Controller — Mock Service
 * Simulates the full ARC event lifecycle for offline/dev mode.
 */

import { uuid } from '../utils/helpers.js';

/**
 * Simulate a command lifecycle with realistic delays.
 * @param {string} commandText - The command text
 * @param {Function} onEvent - Callback for each event
 * @returns {{ jobId: string, cancel: Function }}
 */
export function simulateCommand(commandText, onEvent) {
  const jobId = uuid();
  let cancelled = false;
  const timers = [];

  function schedule(delay, event) {
    const t = setTimeout(() => {
      if (!cancelled) onEvent(event);
    }, delay);
    timers.push(t);
  }

  const text = commandText.toLowerCase();

  // Determine scenario
  const needsClarify = text.includes('find') || text.includes('search') || text.includes('which');
  const needsConfirm = text.includes('delete') || text.includes('send') || text.includes('remove');
  const willFail = text.includes('fail') || text.includes('error') || text.includes('crash');

  let delay = 0;

  // ACK
  delay += 300;
  schedule(delay, {
    type: 'ack',
    message: `Command received: "${commandText}"`,
    data: {},
    timestamp: (Date.now() + delay) / 1000,
  });

  // CLARIFY flow
  if (needsClarify) {
    delay += 1200;
    schedule(delay, {
      type: 'clarify',
      message: 'Multiple matches found. Which file do you mean?\n1. resume_2024.pdf\n2. resume_draft.docx\n3. resume_final.pdf',
      data: { options: ['resume_2024.pdf', 'resume_draft.docx', 'resume_final.pdf'] },
      timestamp: (Date.now() + delay) / 1000,
    });
    // Clarify pauses the timeline — user must reply
    return { jobId, cancel: () => { cancelled = true; timers.forEach(clearTimeout); } };
  }

  // CONFIRM flow
  if (needsConfirm) {
    delay += 800;
    schedule(delay, {
      type: 'progress',
      message: 'Preparing action...',
      data: {},
      timestamp: (Date.now() + delay) / 1000,
    });

    delay += 1000;
    schedule(delay, {
      type: 'confirm',
      message: `This will perform a destructive action: "${commandText}". Proceed?`,
      data: { action: commandText },
      timestamp: (Date.now() + delay) / 1000,
    });
    return { jobId, cancel: () => { cancelled = true; timers.forEach(clearTimeout); } };
  }

  // ERROR flow
  if (willFail) {
    delay += 800;
    schedule(delay, {
      type: 'executing',
      message: 'Attempting to execute...',
      data: {},
      timestamp: (Date.now() + delay) / 1000,
    });

    delay += 1500;
    schedule(delay, {
      type: 'error',
      message: 'Execution failed: simulated error for testing purposes.',
      data: { error_code: 'MOCK_FAILURE' },
      timestamp: (Date.now() + delay) / 1000,
    });
    return { jobId, cancel: () => { cancelled = true; timers.forEach(clearTimeout); } };
  }

  // NORMAL flow (most commands)
  delay += 600;
  schedule(delay, {
    type: 'executing',
    message: `Executing: ${commandText}`,
    data: {},
    timestamp: (Date.now() + delay) / 1000,
  });

  delay += 1200;
  schedule(delay, {
    type: 'progress',
    message: 'Action in progress...',
    data: { progress: 50 },
    timestamp: (Date.now() + delay) / 1000,
  });

  delay += 800;
  schedule(delay, {
    type: 'verify',
    message: 'Verifying outcome...',
    data: {},
    timestamp: (Date.now() + delay) / 1000,
  });

  delay += 700;
  schedule(delay, {
    type: 'result',
    message: `Successfully executed: "${commandText}". Action completed and verified.`,
    data: { verified: true, elapsed_ms: delay },
    timestamp: (Date.now() + delay) / 1000,
  });

  return { jobId, cancel: () => { cancelled = true; timers.forEach(clearTimeout); } };
}

/**
 * Simulate a reply continuation (after clarify/confirm).
 * @param {string} jobId
 * @param {string} answer
 * @param {Function} onEvent
 */
export function simulateReply(jobId, answer, onEvent) {
  let delay = 0;

  delay += 500;
  setTimeout(() => onEvent({
    type: 'executing',
    message: `Proceeding with: "${answer}"`,
    data: {},
    timestamp: (Date.now() + delay) / 1000,
  }), delay);

  delay += 1200;
  setTimeout(() => onEvent({
    type: 'verify',
    message: 'Verifying outcome...',
    data: {},
    timestamp: (Date.now() + delay) / 1000,
  }), delay);

  delay += 800;
  setTimeout(() => onEvent({
    type: 'result',
    message: `Action completed with selection: "${answer}". Verified successfully.`,
    data: { selection: answer, verified: true },
    timestamp: (Date.now() + delay) / 1000,
  }), delay);
}
