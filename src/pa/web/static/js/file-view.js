// File view: shown in the main pane when state.viewedFile is set.
// Renders Markdown files as prose; everything else as a <pre> block.

import * as state from './state.js';
import { renderMarkdown, escape } from './markdown.js';

const DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'];

export function render(target) {
  const s = state.get();
  const f = s.viewedFile;
  if (!f) { target.innerHTML = ''; return; }

  const now = new Date();
  const headerKicker = `${formatTime(now)} · ${DAYS[now.getDay()]}, ${MONTHS[now.getMonth()]} ${now.getDate()}`;
  const title = fileTitle(f.path);
  const isMd = f.path.toLowerCase().endsWith('.md');

  let bodyHtml;
  if (f.loading) {
    bodyHtml = `<div class="quiet-empty">Loading…</div>`;
  } else if (isMd) {
    bodyHtml = `<article class="prose file-prose">${renderMarkdown(f.content || '')}</article>`;
  } else {
    bodyHtml = `<pre class="file-raw">${escape(f.content || '')}</pre>`;
  }

  target.innerHTML = `
    <div class="page-header">
      <div class="row">
        <div class="page-kicker">${escape(headerKicker)}</div>
        <div class="page-meta">
          <span class="file-path">${escape(f.path)}</span>
          <button class="file-close" title="Close file">✕</button>
        </div>
      </div>
      <h1 class="page-title">${escape(title)}</h1>
    </div>
    <div class="page-body file-body">
      ${bodyHtml}
    </div>
  `;

  target.querySelector('.file-close')?.addEventListener('click', () => {
    state.set({ viewedFile: null });
  });
}

function fileTitle(path) {
  const base = path.split('/').pop() || path;
  return base.replace(/\.md$/i, '');
}

function formatTime(d) {
  return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }).toLowerCase();
}
