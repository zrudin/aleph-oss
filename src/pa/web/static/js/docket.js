// Right docket: date + today's reminders + this-week stats.

import * as state from './state.js';
import * as api from './api.js';
import { escape } from './markdown.js';

const DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'];

export function render(target) {
  const s = state.get();
  const reminders = s.reminders || [];
  const active = reminders.filter((r) => !r.done);
  const done = reminders.filter((r) => r.done);
  const now = new Date();

  target.innerHTML = `
    <div class="docket-date">
      <div class="kicker">${DAYS[now.getDay()]}</div>
      <div class="day">${now.getDate()} ${MONTHS[now.getMonth()].slice(0, 3)}</div>
    </div>

    <div class="side-card accent">
      <div class="kicker">To attend to</div>
      <div class="title">Today’s docket</div>
      <ul>
        ${active.length === 0 && done.length === 0
          ? `<li style="color:var(--muted);font-style:italic;border:none">Nothing here. A quiet stretch.</li>`
          : ''}
        ${active.map((r) => `
          <li>
            <button class="checkbox" data-line="${r.line}" title="mark done"></button>
            <span>${escape(r.text)}</span>
          </li>`).join('')}
        ${done.map((r) => `
          <li class="done">
            <span class="checkbox on">✓</span>
            <span>${escape(r.text)}</span>
          </li>`).join('')}
      </ul>
    </div>

    <div class="side-card">
      <div class="kicker">In return</div>
      <div class="title">This week</div>
      <div class="stats-row empty"><span class="label">journal streak</span><span class="fill"></span><span class="value">—</span></div>
      <div class="stats-row empty"><span class="label">pages this week</span><span class="fill"></span><span class="value">—</span></div>
      <div class="stats-row empty"><span class="label">goals</span><span class="fill"></span><span class="value">coming soon</span></div>
    </div>
  `;

  target.querySelectorAll('.checkbox[data-line]').forEach((b) => {
    b.addEventListener('click', async () => {
      const line = Number(b.dataset.line);
      try {
        await api.toggleReminder(line, true);
        const data = await api.listReminders();
        state.set({ reminders: data.active || [] });
      } catch (e) { console.warn('toggle failed', e); }
    });
  });
}
