/**
 * ARC Controller — Header Component
 */

import { renderConnectionStatus } from './ConnectionStatus.js';
import appState from '../state/appState.js';

export function renderHeader() {
  const header = document.createElement('header');
  header.className = 'header';
  header.id = 'app-header';

  header.innerHTML = `
    <div class="header__brand">
      <div class="header__logo">ARC</div>
      <div>
        <div class="header__title">ARC Controller</div>
        <div class="header__subtitle">Remote Desktop Assistant</div>
      </div>
    </div>
    <div class="header__actions" id="header-actions"></div>
  `;

  const actions = header.querySelector('#header-actions');

  // Mock toggle button
  const mockBtn = document.createElement('button');
  mockBtn.className = 'mock-toggle';
  mockBtn.id = 'mock-toggle-btn';
  mockBtn.textContent = 'Mock Mode';
  mockBtn.addEventListener('click', () => {
    appState.toggleMocks();
    mockBtn.classList.toggle('active', appState.useMocks);
  });
  actions.appendChild(mockBtn);

  // Connection status
  actions.appendChild(renderConnectionStatus());

  return header;
}
