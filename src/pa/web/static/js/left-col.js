// LeftColShell + three implementations (today / tasks / settings).
// The shell renders kicker + optional tabs + optional action + scroll
// area. Each destination owns the contents of the scroll area.

import * as state from './state.js';
import * as api from './api.js';
import { icon } from './icons.js';
import * as vaultTree from './vault-tree.js';
import { escape } from './markdown.js';

export function render(target) {
  const s = state.get();
  switch (s.railActive) {
    case 'tasks': return renderTasks(target);
    case 'settings': return renderSettings(target);
    default: return renderToday(target);
  }
}

// ── Today: Chats / Context tabs ─────────────────────────────────
function renderToday(target) {
  const s = state.get();
  const action = s.todayTab === 'chats' ? '+ chat' : '+ note';
  target.innerHTML = `
    <div class="lc-header">
      <div class="lc-kicker">
        <span>Today</span>
        <button class="lc-action" data-action="${s.todayTab === 'chats' ? 'new-chat' : 'new-note'}">${action}</button>
      </div>
      <div class="lc-tabs">
        <button data-tab="chats" class="${s.todayTab === 'chats' ? 'on' : ''}">Chats</button>
        <button data-tab="context" class="${s.todayTab === 'context' ? 'on' : ''}">Context</button>
      </div>
    </div>
    <div class="lc-body">
      <div class="search-box">
        ${icon('search', 13)}
        <input type="text" placeholder="${s.todayTab === 'chats' ? 'search chats…' : 'search vault…'}" value="${escape(s.todayQuery)}" />
        ${s.todayQuery ? '<button data-clear="1">✕</button>' : ''}
      </div>
      <div class="lc-content"></div>
    </div>
  `;

  target.querySelectorAll('.lc-tabs button').forEach((b) => {
    b.addEventListener('click', () => state.set({ todayTab: b.dataset.tab, todayQuery: '' }));
  });

  const action_btn = target.querySelector('.lc-action');
  action_btn?.addEventListener('click', async () => {
    if (action_btn.dataset.action === 'new-chat') {
      try {
        const t = await api.createThread();
        state.set({
          activeThreadId: t.id,
          currentThread: { id: t.id, title: t.title, messages: [] },
          viewedFile: null,
        });
        // Refresh threads list so it appears in "Today".
        api.listThreads().then((d) => state.set({ threads: d.threads || [] })).catch(() => {});
      } catch (e) { console.warn('new chat failed', e); }
    }
    // new-note: punted to todo.md.
  });

  const input = target.querySelector('.search-box input');
  input?.addEventListener('input', (e) => state.set({ todayQuery: e.target.value }));
  target.querySelector('[data-clear]')?.addEventListener('click', () => state.set({ todayQuery: '' }));

  const content = target.querySelector('.lc-content');
  if (s.todayTab === 'chats') renderChatsList(content);
  else renderContext(content);
}

function renderChatsList(host) {
  const s = state.get();
  const q = s.todayQuery.trim().toLowerCase();
  const groups = groupThreads(s.threads || []);
  const visible = groups
    .map((g) => ({ ...g, items: g.items.filter((t) => !q || (t.title || '').toLowerCase().includes(q)) }))
    .filter((g) => g.items.length > 0);

  if (visible.length === 0) {
    host.innerHTML = `<div class="quiet-empty" style="text-align:left;padding:12px 0">${
      q ? `Nothing matches “${escape(q)}”.` : 'No chats yet. A quiet stretch.'
    }</div>`;
    return;
  }

  host.innerHTML = visible.map((g) => `
    <div class="thread-group">
      <div class="group-label">${escape(g.date)}</div>
      ${g.items.map((t) => `
        <div class="thread-row${t.id === s.activeThreadId ? ' active' : ''}" data-id="${escape(t.id)}">
          <div class="title">${escape(t.title || 'Untitled')}</div>
          <div class="meta">${escape(relTime(t.last_message_at))}${t.message_count != null ? ` · ${t.message_count} msgs` : ''}</div>
          <details class="row-menu">
            <summary>⋮</summary>
            <div class="menu-pop">
              <button data-action="rename" data-id="${escape(t.id)}">Rename</button>
              <button data-action="delete" data-id="${escape(t.id)}">Delete</button>
            </div>
          </details>
        </div>`).join('')}
    </div>`).join('');

  host.querySelectorAll('.thread-row').forEach((row) => {
    row.addEventListener('click', async (e) => {
      if (e.target.closest('.row-menu')) return;
      const id = row.dataset.id;
      await openThread(id);
    });
  });

  host.querySelectorAll('button[data-action="rename"]').forEach((b) => {
    b.addEventListener('click', async (e) => {
      e.preventDefault();
      const id = b.dataset.id;
      const t = (state.get().threads || []).find((x) => x.id === id);
      const next = window.prompt('Rename thread:', t?.title || '');
      if (!next || !next.trim()) return;
      try {
        await api.renameThread(id, next.trim());
        const data = await api.listThreads();
        state.set({ threads: data.threads || [] });
        if (state.get().activeThreadId === id && state.get().currentThread) {
          state.set({ currentThread: { ...state.get().currentThread, title: next.trim() } });
        }
      } catch (err) { console.warn('rename failed', err); }
    });
  });

  host.querySelectorAll('button[data-action="delete"]').forEach((b) => {
    b.addEventListener('click', async (e) => {
      e.preventDefault();
      const id = b.dataset.id;
      if (!window.confirm('Delete this chat? This cannot be undone.')) return;
      try {
        await api.deleteThread(id);
        const data = await api.listThreads();
        const next = { threads: data.threads || [] };
        if (state.get().activeThreadId === id) {
          next.activeThreadId = null;
          next.currentThread = null;
        }
        state.set(next);
      } catch (err) { console.warn('delete failed', err); }
    });
  });
}

async function openThread(id) {
  try {
    const data = await api.loadThread(id);
    state.set({
      activeThreadId: data.id,
      currentThread: {
        id: data.id,
        title: data.title,
        messages: data.messages || [],
      },
      viewedFile: null,
    });
  } catch (e) { console.warn('open thread failed', e); }
}

// Singleton so expanded folders survive left-column re-renders.
let _treeHostEl = null;

function renderContext(host) {
  const s = state.get();
  host.innerHTML = `
    <div class="vault-status">
      <span class="dot">●</span>
      <span class="path">${escape(s.vault.vaultPath || '~/vault')} · ${s.vault.mounted ? 'mounted' : 'not mounted'}</span>
    </div>
  `;
  if (!_treeHostEl) {
    _treeHostEl = document.createElement('div');
    _treeHostEl.className = 'vault-tree-host';
  }
  host.appendChild(_treeHostEl);
  vaultTree.render(_treeHostEl, {
    activePath: s.viewedFile?.path || null,
    onFileClick: (path) => openVaultFile(path),
  });
}

async function openVaultFile(path) {
  state.set({
    viewedFile: { path, content: '', loading: true },
    activeThreadId: null,
    currentThread: null,
  });
  try {
    const data = await api.readVaultFile(path);
    if (state.get().viewedFile?.path !== path) return;
    state.set({ viewedFile: { path, content: data.content || '', loading: false } });
  } catch (e) {
    console.warn('open file failed', e);
    state.set({ viewedFile: { path, content: `*[error: ${e.message || e}]*`, loading: false } });
  }
}

function groupThreads(threads) {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const weekAgo = today - 6 * 86400_000;
  const buckets = { Today: [], 'This week': [], Earlier: [] };
  for (const t of threads) {
    const ts = Date.parse(t.last_message_at || '');
    if (Number.isNaN(ts)) {
      buckets.Earlier.push(t);
      continue;
    }
    if (ts >= today) buckets.Today.push(t);
    else if (ts >= weekAgo) buckets['This week'].push(t);
    else buckets.Earlier.push(t);
  }
  return Object.entries(buckets).map(([date, items]) => ({ date, items }));
}

function relTime(iso) {
  if (!iso) return '';
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return '';
  const s = (Date.now() - t) / 1000;
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  if (s < 86400 * 7) return `${Math.floor(s / 86400)}d ago`;
  return new Date(iso).toLocaleDateString();
}

// ── Tasks column: when-buckets + tags ───────────────────────────
function renderTasks(target) {
  const s = state.get();
  const reminders = s.reminders || [];
  const counts = {
    all: reminders.filter((r) => !r.done).length,
    today: 0, tomorrow: 0, 'this week': 0, later: 0,
    done: reminders.filter((r) => r.done).length,
  };
  const when = [
    { id: 'all', label: 'All open' },
    { id: 'today', label: 'Today' },
    { id: 'tomorrow', label: 'Tomorrow' },
    { id: 'this week', label: 'This week' },
    { id: 'later', label: 'Later' },
    { id: 'done', label: 'Completed' },
  ];

  target.innerHTML = `
    <div class="lc-header">
      <div class="lc-kicker">
        <span>Tasks</span>
        <button class="lc-action" data-action="new-task">+ task</button>
      </div>
    </div>
    <div class="lc-body">
      <div class="when-buckets">
        ${when.map((w) => `
          <button class="filter-row${s.tasksFilter === w.id ? ' on' : ''}" data-id="${w.id}">
            <span class="label">${w.label}</span>
            <span class="count">${counts[w.id] || 0}</span>
          </button>`).join('')}
      </div>
      <div class="lc-section">Tags</div>
      <div class="quiet-empty" style="text-align:left;padding:4px 0;font-size:12px">No tags yet.</div>
    </div>
  `;

  target.querySelectorAll('.filter-row[data-id]').forEach((b) => {
    b.addEventListener('click', () => state.set({ tasksFilter: b.dataset.id }));
  });

  target.querySelector('.lc-action')?.addEventListener('click', () => {
    document.querySelector('.task-quickadd input')?.focus();
  });
}

// ── Settings column: section nav ────────────────────────────────
function renderSettings(target) {
  const s = state.get();
  const sections = [
    { id: 'profile', label: 'Profile' },
    { id: 'model', label: 'Model' },
    { id: 'tools', label: 'Tools & connectors' },
    { id: 'appearance', label: 'Appearance' },
    { id: 'shortcuts', label: 'Shortcuts' },
    { id: 'about', label: 'About' },
  ];
  target.innerHTML = `
    <div class="lc-header">
      <div class="lc-kicker"><span>Settings</span></div>
    </div>
    <div class="lc-body">
      ${sections.map((sec) => `
        <button class="filter-row${s.settingsSection === sec.id ? ' on' : ''}" data-id="${sec.id}">
          <span class="label">${sec.label}</span>
        </button>`).join('')}
    </div>
  `;
  target.querySelectorAll('.filter-row[data-id]').forEach((b) => {
    b.addEventListener('click', () => state.set({ settingsSection: b.dataset.id }));
  });
}
