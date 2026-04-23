/**
 * ARC Controller — Command Input Component
 */

import jobStore from '../state/jobStore.js';

/**
 * Render the command input bar (sticky bottom).
 * @param {Function} onSubmit - Called with command text
 */
export function renderCommandInput(onSubmit) {
  const wrapper = document.createElement('div');
  wrapper.className = 'command-input-wrapper';

  wrapper.innerHTML = `
    <div class="command-input" id="command-input-container" style="display:flex; gap:0.5rem;">
      <button class="command-input__mic" id="command-mic-btn" title="Voice Input" style="background:none;border:none;color:var(--text-secondary);cursor:pointer;padding:0.5rem;display:flex;align-items:center;justify-content:center;">
        <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/>
          <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
          <line x1="12" y1="19" x2="12" y2="22"/>
        </svg>
      </button>
      <input
        type="text"
        class="command-input__field"
        id="command-input-field"
        placeholder="Type or speak a command..."
        autocomplete="off"
        spellcheck="false"
        style="flex:1;"
      />
      <button class="command-input__send" id="command-send-btn" title="Send Command" style="background:none;border:none;color:var(--accent-color);cursor:pointer;padding:0.5rem;display:flex;align-items:center;justify-content:center;">
        <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/>
        </svg>
      </button>
    </div>
  `;

  const input = wrapper.querySelector('#command-input-field');
  const sendBtn = wrapper.querySelector('#command-send-btn');

  let sending = false;
  const history = [];
  let historyIndex = -1;

  async function submit() {
    const text = input.value.trim();
    if (!text || sending) return;

    // Check if there is an active prompt waiting for input
    const activeJob = jobStore.getActiveJob();
    if (activeJob && activeJob.needsInput) {
      sending = true;
      input.disabled = true;
      try {
        await jobStore.replyToJob(activeJob.id, text);
        input.value = '';
      } catch (err) {
        console.error('Failed to reply to job:', err);
      } finally {
        sending = false;
        input.disabled = false;
        input.focus();
      }
      return;
    }

    // Standard command submission
    history.unshift(text);
    if (history.length > 20) history.pop();
    historyIndex = -1;

    sending = true;
    sendBtn.disabled = true;
    input.disabled = true;

    try {
      await onSubmit(text);
      input.value = '';
    } catch (err) {
      console.error('Command failed:', err);
    } finally {
      sending = false;
      sendBtn.disabled = false;
      input.disabled = false;
      input.focus();
    }
  }

  const micBtn = wrapper.querySelector('#command-mic-btn');
  let recognition = null;
  let isRecording = false;

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = true;
    
    recognition.onresult = (e) => {
      let transcript = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        transcript += e.results[i][0].transcript;
      }
      input.value = transcript;
    };
    
    recognition.onend = () => {
      isRecording = false;
      micBtn.style.color = 'var(--text-secondary)';
      if (input.value.trim()) {
        submit();
      }
    };
    
    recognition.onerror = (e) => {
      console.error('Speech recognition error:', e);
      isRecording = false;
      micBtn.style.color = 'var(--text-secondary)';
    };

    micBtn.addEventListener('click', () => {
      if (isRecording) {
        recognition.stop();
      } else {
        input.value = '';
        recognition.start();
        isRecording = true;
        micBtn.style.color = 'var(--error-color)'; // Red when recording
      }
    });
  } else {
    micBtn.style.display = 'none';
  }

  sendBtn.addEventListener('click', submit);

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submit();
    }

    // Command history navigation
    if (e.key === 'ArrowUp' && history.length > 0) {
      e.preventDefault();
      historyIndex = Math.min(historyIndex + 1, history.length - 1);
      input.value = history[historyIndex];
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      historyIndex = Math.max(historyIndex - 1, -1);
      input.value = historyIndex >= 0 ? history[historyIndex] : '';
    }
  });

  // Update UI based on prompt status
  jobStore.subscribe(() => {
    const activeJob = jobStore.getActiveJob();
    const hasInput = activeJob?.needsInput ?? false;
    
    if (hasInput) {
      input.placeholder = `Reply to: ${activeJob.pendingEventType === 'confirm' ? 'Confirm Action' : 'Clarification Request'}...`;
      wrapper.querySelector('.command-input').style.borderColor = 'var(--accent-orange)';
    } else {
      input.placeholder = 'Type a command... (e.g., open chrome, find resume.txt)';
      wrapper.querySelector('.command-input').style.borderColor = 'var(--border-default)';
    }
  });

  return wrapper;
}
