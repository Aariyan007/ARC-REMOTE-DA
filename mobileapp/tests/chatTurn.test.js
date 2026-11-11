// @vitest-environment jsdom
import { describe, it, expect } from 'vitest';
import { renderChatTurn } from '../src/components/ChatTurn.js';

const job = (over = {}) => ({
  id: 'job1', kind: 'chat', command: 'hi', status: 'running', needsInput: false,
  pendingEventType: null, pendingNonce: null, events: [], ...over,
});
const ev = (type, message, data = {}) => ({ type, message, data, timestamp: 1 });

function mount(j, handlers = {}) {
  const root = document.createElement('div');
  root.appendChild(renderChatTurn(j, handlers));
  return root;
}

describe('renderChatTurn', () => {
  it('shows a typing indicator and Stop while running', () => {
    let stopped = null;
    const root = mount(job({ events: [ev('ack', 'x')] }), { onStop: id => { stopped = id; } });
    expect(root.querySelector('.chat-typing')).not.toBeNull();
    root.querySelector('.chat-stop-btn').click();
    expect(stopped).toBe('job1');
  });

  it('renders tool chips from progress events that name a tool', () => {
    const root = mount(job({ events: [
      ev('progress', 'Routing command...', { stage: 'routing' }),
      ev('progress', 'Search files', { stage: 'tool', tool: 'search_files' }),
    ] }));
    const chips = [...root.querySelectorAll('.tool-chip')].map(c => c.textContent);
    expect(chips).toEqual(['Search files']);
  });

  it('renders the reply as text, never as HTML', () => {
    const evil = '<img src=x onerror="window.__pwned=1"><b>bold</b>';
    const root = mount(job({ status: 'completed', events: [ev('result', evil)] }));
    expect(root.querySelector('.chat-reply').textContent).toBe(evil);
    expect(root.querySelector('img')).toBeNull();
    expect(root.querySelector('b')).toBeNull();
    expect(root.querySelector('.chat-typing')).toBeNull();
  });

  it('renders file matches by name as text', () => {
    const root = mount(job({ status: 'completed', events: [ev('result', 'Did you mean', {
      exact: false,
      matches: [{ name: '<script>alert(1)</script>.pdf', folder: '/x', size: 2048, downloadable: true, download_url: '/files/t' }],
    })] }));
    expect(root.querySelector('.file-matches__name').textContent).toBe('<script>alert(1)</script>.pdf');
    expect(root.querySelector('script')).toBeNull();
    expect(root.querySelector('.file-matches__title').textContent).toBe('Did you mean…');
  });

  it('shows the approval card with the exact arguments and answers via callback', () => {
    const answers = [];
    const j = job({ status: 'needs_confirmation', needsInput: true, pendingEventType: 'confirm', events: [
      ev('confirm', 'Run ~/ARC-Scripts/backup.sh', { action: 'run_script', dangerous: true,
        details: JSON.stringify({ path: '/Users/me/ARC-Scripts/backup.sh', args: ['--full'] }) }),
    ] });
    const root = mount(j, { onReply: (id, a) => answers.push([id, a]) });
    expect(root.querySelector('.chat-reply').textContent).toBe('Run ~/ARC-Scripts/backup.sh');
    expect(root.querySelector('.confirm-prompt--danger')).not.toBeNull();
    const rows = [...root.querySelectorAll('.confirm-prompt__detail')].map(r => r.textContent);
    expect(rows.join('|')).toContain('/Users/me/ARC-Scripts/backup.sh');
    expect(rows.join('|')).toContain('--full');
    expect(root.querySelector('.chat-typing')).toBeNull();
  });

  it('shows errors with a Retry button', () => {
    let retried = null;
    const root = mount(job({ status: 'failed', command: 'find x', events: [ev('error', 'Gemini is rate-limiting requests.')] }),
      { onRetry: c => { retried = c; } });
    expect(root.querySelector('.chat-reply--error').textContent).toContain('rate-limiting');
    root.querySelector('.event-card__retry-btn').click();
    expect(retried).toBe('find x');
  });

  it('does not render an approval card once the prompt is answered', () => {
    const j = job({ status: 'running', needsInput: false, events: [ev('confirm', 'Turn Wi-Fi off', { dangerous: true })] });
    const root = mount(j);
    expect(root.querySelector('.confirm-prompt')).toBeNull();
  });
});
