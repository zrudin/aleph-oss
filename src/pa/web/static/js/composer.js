// Composer: writing surface on green underline + tools pill + help text.

import { alephMark } from './aleph-mark.js';
import { icon } from './icons.js';
import * as state from './state.js';

export function render(target, { onSend, onOpenTools } = {}) {
  const s = state.get();
  const { enabled = 0, total = 0 } = s.tools.pillCount || {};
  target.innerHTML = `
    <div class="composer">
      <div class="composer-inner">
        <div class="composer-line">
          ${alephMark({ size: 24 })}
          <textarea class="composer-input" rows="1" placeholder="What's on your mind?"></textarea>
          <button class="composer-send" type="button">send →</button>
        </div>
        <div class="composer-meta">
          <button class="tools-pill" type="button">
            ${icon('tools', 13)} Tools
            <span class="count">${enabled}/${total}</span>
          </button>
          <div class="composer-help">
            <span>⌘↵ send</span>
            <span>@ to mention a note</span>
          </div>
        </div>
      </div>
    </div>
  `;

  const ta = target.querySelector('.composer-input');
  const sendBtn = target.querySelector('.composer-send');
  const toolsBtn = target.querySelector('.tools-pill');

  const autosize = () => {
    ta.style.height = 'auto';
    ta.style.height = `${Math.min(ta.scrollHeight, 200)}px`;
  };
  ta.addEventListener('input', autosize);

  const submit = () => {
    const text = ta.value.trim();
    if (!text || state.get().streaming) return;
    ta.value = '';
    autosize();
    onSend?.(text);
  };

  sendBtn.addEventListener('click', submit);
  ta.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      submit();
    }
  });

  toolsBtn.addEventListener('click', () => onOpenTools?.());
  ta.focus();
}
