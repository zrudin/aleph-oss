// Chat view: header (kicker + model/vault meta + title) + messages + composer.

import * as state from './state.js';
import * as api from './api.js';
import { chatStream } from './sse.js';
import { renderUser, renderAssistant, renderTool } from './message.js';
import * as composer from './composer.js';
import { escape, renderMarkdown } from './markdown.js';
import { startAlephThinkingTimer } from './aleph-thinking.js';

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
  renderMessages(stream, t?.messages || [], { streaming: s.streaming });

  composer.render(target.querySelector('.composer-host'), {
    onSend: (text) => sendMessage(text, target),
    onOpenTools: openToolsModal,
  });
}

function renderMessages(host, messages, { streaming = false } = {}) {
  if (!messages.length && !streaming) {
    host.innerHTML = `
      <div class="chat-section-divider">
        <div class="rule"></div>
        <div class="label">the desk by the window</div>
        <div class="rule"></div>
      </div>
      <div class="quiet-empty">A new page. Begin where you are.</div>`;
    return;
  }
  const messagesHtml = messages.map((m) => {
    if (m.role === 'user') return renderUser(m);
    if (m.role === 'tool') return renderTool(m);
    return renderAssistant(m);
  }).join('');
  // When mid-turn, render an extra assistant placeholder we can stream into.
  const placeholderHtml = streaming
    ? renderAssistant({ role: 'assistant', content: '' }, { streaming: true })
    : '';
  host.innerHTML = messagesHtml + placeholderHtml;
  host.scrollTop = host.scrollHeight;
}

async function sendMessage(text, root) {
  const s = state.get();
  if (s.streaming) return;

  // Optimistically put the user message into state and flip streaming on.
  // We deliberately route this through state.set so the re-render shows the
  // user message + streaming placeholder in one consistent pass — earlier
  // versions used insertAdjacentHTML, which got wiped by the next renderAll.
  const userMsg = { role: 'user', content: text, timestamp: new Date().toISOString() };
  const baseThread = s.currentThread || { id: s.activeThreadId, title: '' };
  state.set({
    currentThread: { ...baseThread, messages: [...(baseThread.messages || []), userMsg] },
    streaming: true,
  });

  // After state.set, the DOM is fresh. Grab the streaming placeholder by class.
  const findStream = () => root.querySelector('.chat-stream');
  const findAssistantEl = () => {
    const stream = findStream();
    if (!stream) return null;
    const last = stream.querySelector('.msg-assistant:last-child .prose');
    return last;
  };
  const findThinkingEl = () => {
    const stream = findStream();
    if (!stream) return null;
    return stream.querySelector('.msg-assistant:last-child .aleph-thinking');
  };
  let assistantEl = findAssistantEl();

  // Start the AlephThinking timer against the placeholder bubble. The
  // animation itself runs from CSS; this just drives the elapsed-time
  // readout. We stop it the moment paintAssistant overwrites .prose
  // (which detaches the indicator node).
  let stopThinkingTimer = startAlephThinkingTimer(findThinkingEl());

  let assistantText = '';
  let threadId = s.activeThreadId;
  const liveChips = new Map();

  const paintAssistant = () => {
    assistantEl = assistantEl?.isConnected ? assistantEl : findAssistantEl();
    if (!assistantEl) return;
    if (stopThinkingTimer) {
      stopThinkingTimer();
      stopThinkingTimer = null;
    }
    assistantEl.innerHTML = renderMarkdown(assistantText);
    const stream = findStream();
    if (stream) stream.scrollTop = stream.scrollHeight;
  };

  try {
    for await (const ev of chatStream({ message: text, threadId })) {
      if (ev.kind === 'thread' && ev.text) {
        threadId = ev.text;
      } else if (ev.kind === 'token' && ev.text) {
        assistantText += ev.text;
        paintAssistant();
      } else if (ev.kind === 'tool_start' && ev.tool) {
        const stream = findStream();
        const anchor = stream?.querySelector('.msg-assistant:last-child');
        if (anchor) {
          const chip = document.createElement('div');
          chip.innerHTML = renderTool(ev.tool);
          const node = chip.firstElementChild;
          anchor.before(node);
          liveChips.set(toolKey(ev.tool), node);
          stream.scrollTop = stream.scrollHeight;
        }
      } else if (ev.kind === 'tool_result' && ev.tool) {
        const node = liveChips.get(toolKey(ev.tool));
        if (node) node.outerHTML = renderTool(ev.tool);
      } else if (ev.kind === 'title') {
        // Title is reapplied via the post-turn thread refresh.
      } else if (ev.kind === 'error' && ev.text) {
        assistantText += assistantText ? `\n\n*[error: ${ev.text}]*` : `*[error: ${ev.text}]*`;
        paintAssistant();
      } else if (ev.kind === 'done') {
        break;
      }
    }
  } catch (e) {
    console.warn('chat stream failed', e);
    assistantText += assistantText ? `\n\n*[connection lost: ${e.message || e}]*` : `*[connection lost: ${e.message || e}]*`;
    paintAssistant();
  } finally {
    if (stopThinkingTimer) {
      stopThinkingTimer();
      stopThinkingTimer = null;
    }
    paintAssistant();

    // Refresh state from server: thread list, currentThread, reminders.
    const tasks = [api.listThreads().catch(() => null), api.listReminders().catch(() => null)];
    if (threadId) tasks.push(api.loadThread(threadId).catch(() => null));
    const [threadsRes, remindersRes, threadRes] = await Promise.all(tasks);
    const patch = { streaming: false };
    if (threadsRes) patch.threads = threadsRes.threads || [];
    if (remindersRes) patch.reminders = remindersRes.active || [];
    if (threadRes) {
      let messages = threadRes.messages || [];
      // If we received tokens or an error locally but the server didn't
      // persist a matching assistant message (e.g., Ollama crashed before
      // run_turn could call _persist_assistant_turn), synthesize one so the
      // user sees the partial output / error instead of an empty thread.
      const lastRole = messages.length ? messages[messages.length - 1].role : null;
      if (assistantText && lastRole !== 'assistant') {
        messages = [...messages, {
          role: 'assistant', content: assistantText, timestamp: new Date().toISOString(),
        }];
      }
      patch.activeThreadId = threadRes.id;
      patch.currentThread = { id: threadRes.id, title: threadRes.title, messages };
    } else if (assistantText) {
      // Thread fetch failed entirely; keep the local optimistic view alive.
      const live = state.get().currentThread;
      if (live) {
        patch.currentThread = {
          ...live,
          messages: [...(live.messages || []), {
            role: 'assistant', content: assistantText, timestamp: new Date().toISOString(),
          }],
        };
      }
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
