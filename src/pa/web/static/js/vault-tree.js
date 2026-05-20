// Lazy-loaded vault tree. Renders one level at a time.

import * as api from './api.js';
import { escape } from './markdown.js';

export function render(target, { onFileClick, activePath } = {}) {
  // Preserve expansion state across re-renders: if we've already rendered
  // into this target, just refresh the active highlight.
  if (target.dataset.rendered === '1') {
    updateActive(target, activePath);
    return;
  }
  target.dataset.rendered = '1';
  target.innerHTML = `<div class="tree-root">…</div>`;
  loadInto(target.querySelector('.tree-root'), '', activePath);

  target.addEventListener('click', async (e) => {
    const dir = e.target.closest('.tree-dir');
    if (dir) {
      const inner = dir.nextElementSibling;
      if (!inner) return;
      const open = dir.dataset.open === '1';
      dir.dataset.open = open ? '0' : '1';
      dir.querySelector('.caret').textContent = open ? '▸' : '▾';
      inner.style.display = open ? 'none' : 'block';
      if (!open && inner.dataset.loaded !== '1') {
        await loadInto(inner, dir.dataset.path, activePath);
        inner.dataset.loaded = '1';
      }
      return;
    }
    const file = e.target.closest('.tree-file');
    if (file && onFileClick) onFileClick(file.dataset.path);
  });
}

function updateActive(target, activePath) {
  target.querySelectorAll('.tree-file').forEach((el) => {
    el.classList.toggle('active', !!activePath && el.dataset.path === activePath);
  });
}

async function loadInto(host, path, activePath) {
  try {
    const data = await api.listVaultTree(path);
    host.innerHTML = renderEntries(data.entries, path, activePath);
  } catch (e) {
    host.innerHTML = `<div class="quiet-empty">${escape(e.message)}</div>`;
  }
}

function renderEntries(entries, parentPath, activePath) {
  if (!entries || !entries.length) {
    return `<div class="quiet-empty" style="text-align:left;padding:6px 0">(empty)</div>`;
  }
  return entries.map((e) => {
    if (e.type === 'dir') {
      return `
        <div class="tree-node">
          <div class="tree-dir" data-path="${escape(e.path)}" data-open="0">
            <span class="caret">▸</span>${escape(e.name)}
          </div>
          <div class="tree-children" style="display:none;margin-left:12px">…</div>
        </div>`;
    }
    const active = activePath && e.path === activePath ? ' active' : '';
    return `
      <div class="tree-file${active}" data-path="${escape(e.path)}">
        <span class="dot">·</span>${escape(e.name)}
      </div>`;
  }).join('');
}

// Flatten + filter by path substring. Used for search mode.
export function flattenSearch(entries, q) {
  // We can't do a deep flatten without recursive loads; for v1 do a
  // shallow search against the loaded entries via the API root.
  // This stub returns nothing — search results render under the tree.
  return [];
}
