// User / assistant / tool message renderers.

import { alephMark } from './aleph-mark.js';
import { renderMarkdown, escape } from './markdown.js';

function fmtTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }).toLowerCase();
}

export function renderUser(msg) {
  return `
    <div class="msg-user">
      <div class="who">you${msg.timestamp ? ` · ${escape(fmtTime(msg.timestamp))}` : ''}</div>
      <div class="bubble">${escape(msg.content)}</div>
    </div>`;
}

export function renderAssistant(msg, { streaming = false } = {}) {
  const body = renderMarkdown(msg.content || '');
  const caret = streaming ? '<span class="caret"></span>' : '';
  return `
    <div class="msg-assistant" data-role="assistant">
      <div class="who">${alephMark({ size: 12 })} Aleph</div>
      <div class="prose">${body}${caret}</div>
    </div>`;
}

export function renderTool(tool) {
  const name = tool.name || '';
  const result = tool.result;
  let summary = tool.summary || '';
  if (!summary && result) {
    if (typeof result === 'string') summary = result;
    else if (result.error) summary = `error: ${result.error}`;
    else if (Array.isArray(result)) summary = `${result.length} results`;
    else summary = Object.keys(result).slice(0, 3).join(', ') || 'done';
  }
  return `
    <div class="msg-tool">
      <span class="glyph">◇</span>
      <span class="name">${escape(name)}</span>
      ${summary ? `<span class="sep">·</span><span>${escape(String(summary).slice(0, 80))}</span>` : ''}
    </div>`;
}
