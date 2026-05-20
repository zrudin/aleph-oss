// Tasks page: quick-add row + grouped lists + when-bucket filter awareness.

import * as state from './state.js';
import * as api from './api.js';
import { escape } from './markdown.js';

export function render(target) {
  const s = state.get();
  const filter = s.tasksFilter || 'all';
  const reminders = s.reminders || [];
  const filtered = applyFilter(reminders, filter);

  const headers = {
    all: { kicker: 'To attend to', title: 'All open' },
    today: { kicker: 'To attend to · today', title: 'Today' },
    tomorrow: { kicker: 'To attend to · tomorrow', title: 'Tomorrow' },
    'this week': { kicker: 'To attend to · this week', title: 'This week' },
    later: { kicker: 'To attend to · later', title: 'Later' },
    done: { kicker: 'Looking back', title: 'Completed' },
  };
  const header = headers[filter] || headers.all;
  const openCount = reminders.filter((r) => !r.done).length;
  const doneCount = reminders.filter((r) => r.done).length;

  target.innerHTML = `
    <div class="page-header">
      <div class="row">
        <div class="page-kicker">${escape(header.kicker)}</div>
        <div class="page-meta">
          <span>${openCount} open · ${doneCount} done</span>
        </div>
      </div>
      <h1 class="page-title">${escape(header.title)}</h1>
    </div>
    <div class="page-body">
      <div class="tasks-wrap">
        ${filter !== 'done' ? `
          <div class="task-quickadd">
            <span class="box"></span>
            <input type="text" placeholder="add a task… (press ↵)" />
            <button type="button">+ add</button>
          </div>` : ''}
        <div class="task-list-host"></div>
      </div>
    </div>
  `;

  const listHost = target.querySelector('.task-list-host');
  if (filtered.length === 0) {
    listHost.innerHTML = `<div class="quiet-empty">Nothing here. A quiet stretch.</div>`;
  } else {
    listHost.innerHTML = `
      <ul class="task-list">
        ${filtered.map((r) => `
          <li class="${r.done ? 'done' : ''}" data-line="${r.line}">
            <button class="check${r.done ? ' on' : ''}" title="toggle">${r.done ? '✓' : ''}</button>
            <span class="text">${escape(r.text)}</span>
            <button class="dismiss" title="remove">✕</button>
          </li>`).join('')}
      </ul>
    `;
  }

  // Quick-add wiring
  const input = target.querySelector('.task-quickadd input');
  const addBtn = target.querySelector('.task-quickadd button');
  const submit = async () => {
    const text = (input?.value || '').trim();
    if (!text) return;
    try {
      await api.addReminder(text);
      const data = await api.listReminders();
      state.set({ reminders: data.active || [] });
    } catch (e) { console.warn('add reminder failed', e); }
  };
  addBtn?.addEventListener('click', submit);
  input?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); submit(); }
  });

  // Toggle / dismiss wiring
  listHost.querySelectorAll('.check').forEach((b) => {
    b.addEventListener('click', async () => {
      const li = b.closest('li');
      const line = Number(li.dataset.line);
      const isDone = li.classList.contains('done');
      try {
        await api.toggleReminder(line, !isDone);
        const data = await api.listReminders();
        state.set({ reminders: data.active || [] });
      } catch (e) { console.warn('toggle failed', e); }
    });
  });
  listHost.querySelectorAll('.dismiss').forEach((b) => {
    b.addEventListener('click', async () => {
      const li = b.closest('li');
      const line = Number(li.dataset.line);
      try {
        await api.removeReminder(line);
        const data = await api.listReminders();
        state.set({ reminders: data.active || [] });
      } catch (e) { console.warn('remove failed', e); }
    });
  });
}

function applyFilter(reminders, filter) {
  if (filter === 'all') return reminders.filter((r) => !r.done);
  if (filter === 'done') return reminders.filter((r) => r.done);
  if (filter.startsWith('tag:')) return []; // tags not yet in backend
  // when-bucket filters: backend has no `when` field yet → empty.
  return [];
}
