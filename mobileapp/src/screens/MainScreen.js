/**
 * ARC Controller — Main Screen
 * Orchestrates the full command lifecycle.
 */

import { renderHeader } from '../components/Header.js';
import { renderEventTimeline } from '../components/EventTimeline.js';
import { renderCommandInput } from '../components/CommandInput.js';
import { sendCommand } from '../api/http.js';
import { connectToJob } from '../api/websocket.js';
import { handleEvent } from '../services/eventHandler.js';
import { simulateCommand } from '../services/mockService.js';
import { classifyError } from '../utils/errors.js';
import jobStore from '../state/jobStore.js';
import appState from '../state/appState.js';

/** Active WebSocket connections by jobId */
const activeConnections = new Map();

/**
 * Handle a new command submission.
 */
async function onCommandSubmit(text) {
  if (appState.useMocks) {
    return handleMockCommand(text);
  }
  return handleRealCommand(text);
}

/**
 * Real backend flow: POST /command → WS /stream/{job_id}
 */
async function handleRealCommand(text) {
  try {
    const res = await sendCommand(text);
    const jobId = res.job_id;

    // Create job in store
    jobStore.createJob(jobId, text);

    // Connect WebSocket for real-time events
    const conn = connectToJob(jobId, {
      onEvent(event) {
        handleEvent(jobId, event);
      },
      onError(err) {
        console.error(`WS error for job ${jobId}:`, err);
      },
      onClose({ clean, reason }) {
        activeConnections.delete(jobId);
        if (!clean) {
          console.warn(`WS closed unexpectedly for job ${jobId}: ${reason}`);
          if (!jobStore.isJobDone(jobId)) {
            handleEvent(jobId, {
              type: 'error',
              message: `Connection lost: ${reason || 'Unknown'}. The command may still be running on the server.`,
              data: {},
              timestamp: Date.now() / 1000,
            });
          }
        }
      },
    });

    activeConnections.set(jobId, conn);
  } catch (err) {
    const failJobId = `local-${Date.now()}`;
    jobStore.createJob(failJobId, text);

    // Detect 503 "Runtime booting" specifically
    if (err.status === 503) {
      handleEvent(failJobId, {
        type: 'error',
        message: 'ARC runtime is still loading (initializing models and actions). This can take 30-60 seconds on first start. Please try again shortly, or use Mock Mode to test the UI.',
        data: { error_type: 'BOOTING', hint: 'The server is running but the AI pipeline is still initializing.' },
        timestamp: Date.now() / 1000,
      });
    } else {
      const classified = classifyError(err);
      handleEvent(failJobId, {
        type: 'error',
        message: classified.message,
        data: { error_type: classified.type, details: classified.details },
        timestamp: Date.now() / 1000,
      });
    }
  }
}

/**
 * Mock flow: simulated events via mockService.
 */
function handleMockCommand(text) {
  const { jobId } = simulateCommand(text, (event) => {
    handleEvent(jobId, event);
  });

  jobStore.createJob(jobId, text);
}

/**
 * Handle reply from clarify/confirm prompts.
 */
function onReply(jobId, answer) {
  // The actual reply is sent by the ClarifyPrompt/ConfirmPrompt components.
  // This callback is for any post-reply UI logic.
  console.log(`Reply sent for job ${jobId}: "${answer}"`);
}

/**
 * Mount the main screen into the app container.
 */
export function mountMainScreen() {
  const app = document.getElementById('app');
  if (!app) return;
  app.innerHTML = ''; // Clear previous screen

  // Header
  app.appendChild(renderHeader());

  // Main content area (scrollable)
  const main = document.createElement('main');
  main.className = 'main-content';
  main.id = 'main-content';

  // Event Timeline
  main.appendChild(renderEventTimeline(onReply));
  app.appendChild(main);

  // Command Input (sticky bottom)
  app.appendChild(renderCommandInput(onCommandSubmit));
}
