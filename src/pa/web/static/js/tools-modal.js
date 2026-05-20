// Tools modal: search + grouped per-tool list + per-row toggle.

import * as state from './state.js';
import * as api from './api.js';
import { icon } from './icons.js';
import { escape } from './markdown.js';

let modalQuery = '';

export function open() {
  if (state.get().toolsModalOpen) return;
  state.set({ toolsModalOpen: true });
}
export function close() { state.set({ toolsModalOpen: false }); }
export function toggle() {
  if (state.get().toolsModalOpen) close(); else open();
}

export function render(target) {
  const s = state.get();
  if (!s.toolsModalOpen) {
    target.innerHTML = '';
    return;
  }
  // Preserve scroll position across re-renders (toggling a tool re-renders
  // the whole modal via state.subscribe).
  const prevScroll = target.querySelector('.modal-list')?.scrollTop ?? 0;
  const groups = (s.tools.groups || []);
  const q = modalQuery.trim().toLowerCase();
  const filteredGroups = groups
    .map((g) => ({
      ...g,
      items: g.items.filter((t) =>
        !q ||
        t.name.toLowerCase().includes(q) ||
        (t.description || '').toLowerCase().includes(q) ||
        g.label.toLowerCase().includes(q)
      ),
    }))
    .filter((g) => g.items.length > 0);

  // Counts (dedupe by id).
  let total = 0, enabled = 0;
  const seen = new Set();
  for (const g of groups) for (const t of g.items) {
    if (seen.has(t.id)) continue;
    seen.add(t.id);
    if (!t.available) continue;
    total += 1;
    if (t.enabled) enabled += 1;
  }

  target.innerHTML = `
    <div class="modal-backdrop" data-close>
      <div class="modal">
        <div class="modal-header">
          <div>
            <div class="kicker">What Aleph can reach for</div>
            <div class="title">Tools</div>
            <div class="sub">${enabled} of ${total} enabled · disabled tools stay known.</div>
          </div>
          <button class="close" data-close>✕</button>
        </div>
        <div class="modal-search-wrap">
          <div class="search-box modal-search">
            ${icon('search', 14)}
            <input type="text" placeholder="Search tools…" value="${escape(modalQuery)}" />
            <span class="kbd-hint">⌘ K</span>
          </div>
        </div>
        <div class="modal-list">
          ${filteredGroups.length === 0 ? `
            <div style="padding:40px 22px;text-align:center;font-family:var(--display);font-style:italic;font-size:16px;color:var(--muted)">
              Nothing matches “${escape(q)}”.
            </div>` : filteredGroups.map(renderGroup).join('')}
        </div>
        <div class="modal-footer">
          <span class="note">Changes save automatically.</span>
          <div class="actions">
            <button class="ghost" data-action="add-connector">+ Add connector</button>
            <button class="primary" data-close>done</button>
          </div>
        </div>
      </div>
    </div>
  `;

  const listEl = target.querySelector('.modal-list');
  if (listEl && prevScroll) listEl.scrollTop = prevScroll;

  target.querySelectorAll('[data-close]').forEach((el) => {
    el.addEventListener('click', (e) => {
      if (e.target === el || e.currentTarget === el && el.dataset.close !== undefined) {
        close();
      }
    });
  });
  // Stop propagation inside the modal so clicks don't close it.
  target.querySelector('.modal')?.addEventListener('click', (e) => e.stopPropagation());

  const search = target.querySelector('.modal-search input');
  search?.addEventListener('input', (e) => {
    modalQuery = e.target.value;
    render(target);
    target.querySelector('.modal-search input')?.focus();
  });
  search?.focus();

  target.querySelectorAll('.tool-row .toggle').forEach((b) => {
    b.addEventListener('click', async () => {
      const id = b.dataset.id;
      const enabled = b.dataset.enabled !== '1';
      try {
        const catalog = await api.toggleTool(id, enabled);
        applyCatalog(catalog);
      } catch (e) { console.warn('toggle tool failed', e); }
    });
  });

  target.querySelector('[data-action="add-connector"]')?.addEventListener('click', () => {
    console.warn('Add connector flow is not yet implemented (todo.md).');
  });
}

function renderGroup(g) {
  const onCount = g.items.filter((t) => t.enabled).length;
  return `
    <div>
      <div class="tool-group-header">
        <span class="name">${escape(g.label)}</span>
        <span class="count">${onCount} on</span>
      </div>
      <div class="tool-rows">
        ${g.items.map(renderRow).join('')}
      </div>
    </div>
  `;
}

function renderRow(t) {
  const unavailable = !t.available;
  return `
    <div class="tool-row${unavailable ? ' unavailable' : ''}">
      <div class="swatch${t.enabled ? ' on' : ''}">${escape((t.name || '?').charAt(0))}</div>
      <div class="body">
        <div>
          <span class="name">${escape(t.name)}</span>
          ${t.badge ? `<span class="badge">${escape(t.badge)}</span>` : ''}
        </div>
        <div class="desc">${escape(t.description || '')}</div>
      </div>
      <button class="toggle${t.enabled ? ' on' : ''}" data-id="${escape(t.id)}" data-enabled="${t.enabled ? 1 : 0}" ${unavailable ? 'disabled' : ''}>
        <span class="knob"></span>
      </button>
    </div>
  `;
}

// Convert catalog response into state shape + pill count.
export function applyCatalog(catalog) {
  const groups = catalog.groups || [];
  let total = 0, enabled = 0;
  const seen = new Set();
  for (const g of groups) for (const t of g.items) {
    if (seen.has(t.id)) continue;
    seen.add(t.id);
    if (!t.available) continue;
    total += 1;
    if (t.enabled) enabled += 1;
  }
  state.set({ tools: { groups, pillCount: { enabled, total } } });
}
