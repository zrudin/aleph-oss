// Tiny pub-sub. One store, subscribers re-render the subtree they own.
// No diffing — just replace innerHTML and re-attach listeners.

const subs = new Set();

const _state = {
  railActive: 'today',          // 'today' | 'tasks' | 'settings'
  settingsSection: 'profile',   // 'profile' | 'model' | 'tools' | 'appearance' | 'shortcuts' | 'about'
  tasksFilter: 'all',           // 'all' | 'today' | 'tomorrow' | 'this week' | 'later' | 'done' | 'tag:<x>'
  todayTab: 'chats',            // 'chats' | 'context'
  todayQuery: '',
  activeThreadId: null,
  threads: [],                   // ThreadSummary[]
  currentThread: null,           // { id, title, messages: [{role, content, timestamp}] }
  viewedFile: null,              // { path, content, loading } — when set, main pane shows the file instead of chat
  reminders: [],                 // [{ line, text, done }]
  tools: { groups: [], pillCount: { enabled: 0, total: 0 } },
  vault: { mounted: false, model: '', vaultPath: '' },
  toolsModalOpen: false,
  profile: null,                  // { name, pronouns, voice }
  streaming: false,
};

export function get() { return _state; }

export function set(patch) {
  Object.assign(_state, patch);
  for (const fn of subs) fn(_state);
}

export function subscribe(fn) {
  subs.add(fn);
  return () => subs.delete(fn);
}
