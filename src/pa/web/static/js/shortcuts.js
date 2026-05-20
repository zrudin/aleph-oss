// Global keyboard shortcuts. Single keydown handler.

import * as state from './state.js';
import * as toolsModal from './tools-modal.js';
import * as api from './api.js';

export function install() {
  document.addEventListener('keydown', async (e) => {
    const mod = e.metaKey || e.ctrlKey;
    if (!mod) return;
    if (e.key === ',' || e.code === 'Comma') {
      e.preventDefault();
      state.set({ railActive: 'settings' });
    } else if (e.key === '/' || e.code === 'Slash') {
      e.preventDefault();
      toolsModal.toggle();
    } else if (e.key.toLowerCase() === 'n') {
      e.preventDefault();
      const dest = state.get().railActive;
      if (dest === 'today') {
        try {
          const t = await api.createThread();
          state.set({
            activeThreadId: t.id,
            currentThread: { id: t.id, title: t.title, messages: [] },
          });
          api.listThreads().then((d) => state.set({ threads: d.threads || [] })).catch(() => {});
        } catch (err) { console.warn('new chat failed', err); }
      } else if (dest === 'tasks') {
        document.querySelector('.task-quickadd input')?.focus();
      }
    }
  });
}
