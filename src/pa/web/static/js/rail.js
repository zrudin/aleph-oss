// Left rail: Aleph mark + destination buttons + bottom avatar.

import { alephMark } from './aleph-mark.js';
import { icon } from './icons.js';
import * as state from './state.js';

const DESTINATIONS = [
  { id: 'today', label: 'Today' },
  { id: 'tasks', label: 'Tasks' },
];
const BOTTOM = [{ id: 'settings', label: 'Settings' }];

export function render(target) {
  const s = state.get();
  const btn = (it) => {
    const on = s.railActive === it.id;
    return `<button data-id="${it.id}" title="${it.label}" class="${on ? 'active' : ''}">${icon(it.id)}</button>`;
  };
  target.innerHTML = `
    <div class="mark">${alephMark({ size: 32 })}</div>
    ${DESTINATIONS.map(btn).join('')}
    <div class="spacer"></div>
    ${BOTTOM.map(btn).join('')}
    <div class="avatar">Z</div>
  `;
  target.querySelectorAll('button[data-id]').forEach((b) => {
    b.addEventListener('click', () => {
      const id = b.dataset.id;
      if (state.get().railActive !== id) state.set({ railActive: id });
    });
  });
}
