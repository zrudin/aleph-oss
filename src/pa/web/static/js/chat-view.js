// Chat view: header (kicker + model/vault meta + title) + messages + composer.

import * as state from './state.js';
import * as api from './api.js';
import { chatStream } from './sse.js';
import { renderUser, renderAssistant, renderTool } from './message.js';
import * as composer from './composer.js';
import { escape } from './markdown.js';

const DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'];

export function render(target, { openToolsModal } = {}) {
  const s = state.get();
  const t = s.currentThread;
  const now = new Date();
  const headerKicker = `${formatTime(now)} · ${DAYS[now.getDay()]}, ${MONTHS[now.getMonth()]} ${now.getDate()}`;
  const title = t?.title || (s.activeThreadId ? 'Untitled' : 'New conversation');

  target.innerHTML = `
    <div class="page-header">
      <div class="row">
        <div class="page-kicker">${escape(headerKicker)}</div>
        <div class="page-meta">
          <span>${escape(s.vault.model || '')}</span>
          <span class="vault-pill${s.vault.mounted ? '' : ' warn'}">
            <span class="dot"></span>${s.vault.mounted ? 'vault mounted' : 'vault not mounted'}
          </span>
        </div>
      </div>
      <h1 class="page-title">${escape(title)}</h1>
    </div>
    <div class="page-body chat-body">
      <div class="chat-stream"></div>
    </div>
    <div class="composer-host"></div>
  `;

  const stream = target.querySelector('.chat-stream');
  renderMessages(stream, t?.messages || []);

  composer.render(target.querySelector('.composer-host'), {
    onSend: (text) => sendMessage(text, target),
    onOpenTools: openToolsModal,
  });
}

function renderMessages(host, messages) {
  if (!messages.length) {
    host.innerHTML = `
      <div class="chat-section-divider">
        <div class="rule"></div>
        <div class="label">the desk by the window</div>
        <div class="rule"></div>
      </div>
      <div class="quiet-empty">A new page. Begin where you are.</div>`;
    return;
  }
  host.innerHTML = messages.map((m) => {
    if (m.role === 'user') return renderUser(m);
    if (m.role === 'tool') return renderTool(m);
    return renderAssistant(m);
  }).join('');
  host.scrollTop = host.scrollHeight;
}

async function sendMessage(text, root) {
  const s = state.get();
  const stream = root.querySelector('.chat-stream');
  const composerWrap = root.querySelector('.composer-host');
  const sendBtn = composerWrap.querySelector('.composer-send');

  // Append user message to the visible stream immediately.
  const userMsg = { role: 'user', content: text, timestamp: new Date().toISOString() };
  const next = [...(s.currentThread?.messages || []), userMsg];
  stream.insertAdjacentHTML('beforeend', renderUser(userMsg));
  // Add an empty assistant placeholder we'll fill as tokens arrive.
  stream.insertAdjacentHTML('beforeend', renderAssistant({ role: 'assistant', content: '' }, { streaming: true }));
  const assistantEl = stream.querySelector('.msg-assistant:last-child .prose');
  stream.scrollTop = stream.scrollHeight;

  if (sendBtn) sendBtn.disabled = true;
  state.set({ streaming: true });

  let assistantText = '';
  let threadId = s.activeThreadId;
  let titleChanged = false;
  const liveChips = new Map();

  try {
    for await (const ev of chatStream({ message: text, threadId })) {
      if (ev.kind === 'thread' && ev.text) {
        threadId = ev.text;
      } else if (ev.kind === 'token' && ev.text) {
        assistantText += ev.text;
        const { renderMarkdown } = await import('./markdown.js');
        const html = renderMarkdown(assistantText);
        assistantEl.innerHTML = html + '<span class="caret"></span>';
        stream.scrollTop = stream.scrollHeight;
      } else if (ev.kind === 'tool_start' && ev.tool) {
        // Insert a tool chip just before the streaming assistant block.
        const chip = document.createElement('div');
        chip.innerHTML = renderTool(ev.tool);
        const node = chip.firstElementChild;
        stream.querySelector('.msg-assistant:last-child').before(node);
        liveChips.set(toolKey(ev.tool), node);
        stream.scrollTop = stream.scrollHeight;
      } else if (ev.kind === 'tool_result' && ev.tool) {
        const node = liveChips.get(toolKey(ev.tool));
        if (node) node.outerHTML = renderTool(ev.tool);
      } else if (ev.kind === 'title' && ev.text) {
        titleChanged = true;
      } else if (ev.kind === 'error' && ev.text) {
        assistantText += `\n\n*[error: ${ev.text}]*`;
        const { renderMarkdown } = await import('./markdown.js');
        assistantEl.innerHTML = renderMarkdown(assistantText);
      } else if (ev.kind === 'done') {
        break;
      }
    }
  } catch (e) {
    console.warn('chat stream failed', e);
  } finally {
    // Close out streaming state — remove the caret.
    assistantEl.innerHTML = (await import('./markdown.js')).renderMarkdown(assistantText);
    state.set({ streaming: false });

    // Refresh state from server: thread list, currentThread, reminders.
    const tasks = [api.listThreads().catch(() => null), api.listReminders().catch(() => null)];
    if (threadId) tasks.push(api.loadThread(threadId).catch(() => null));
    const [threadsRes, remindersRes, threadRes] = await Promise.all(tasks);
    const patch = {};
    if (threadsRes) patch.threads = threadsRes.threads || [];
    if (remindersRes) patch.reminders = remindersRes.active || [];
    if (threadRes) {
      patch.activeThreadId = threadRes.id;
      patch.currentThread = {
        id: threadRes.id,
        title: threadRes.title,
        messages: threadRes.messages || [],
      };
    }
    state.set(patch);
  }
}

function toolKey(tool) {
  try { return `${tool.name}:${JSON.stringify(tool.arguments || {})}`; }
  catch { return tool.name; }
}

function formatTime(d) {
  return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }).toLowerCase();
}
