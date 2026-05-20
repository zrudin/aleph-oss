// User / assistant / tool message renderers.

import { alephMark } from './aleph-mark.js';
import { alephThinkingHtml } from './aleph-thinking.js';
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
  // Before the first token arrives we show the AlephThinking indicator
  // (three pulsing alephs + an elapsed-time counter) inside the empty
  // prose container. paintAssistant() in chat-view.js then overwrites
  // .prose with rendered markdown when the first token lands. No
  // streaming caret — the indicator is the only "still thinking" cue.
  const trail = streaming && !msg.content ? alephThinkingHtml({ size: 22 }) : '';
  return `
    <div class="msg-assistant" data-role="assistant">
      <div class="who">${alephMark({ size: 12 })} Aleph</div>
      <div class="prose">${body}${trail}</div>
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
