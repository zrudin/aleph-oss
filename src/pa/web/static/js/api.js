// Typed-ish fetch wrappers. One module per concern below; this collects them.

async function jget(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${r.status} ${path}`);
  return r.json();
}

async function jbody(path, method, body) {
  const r = await fetch(path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body == null ? null : JSON.stringify(body),
  });
  if (!r.ok) {
    let msg = `${r.status} ${path}`;
    try {
      const data = await r.json();
      if (data.detail) msg = data.detail;
    } catch {}
    throw new Error(msg);
  }
  return r.json();
}

export const health = () => jget('/health');

export const listThreads = () => jget('/threads');
export const loadThread = (id) => jget(`/threads/${encodeURIComponent(id)}`);
export const createThread = () => jbody('/threads', 'POST', {});
export const renameThread = (id, title) =>
  jbody(`/threads/${encodeURIComponent(id)}`, 'PATCH', { title });
export const deleteThread = (id) =>
  jbody(`/threads/${encodeURIComponent(id)}`, 'DELETE');

export const listReminders = () => jget('/reminders');
export const addReminder = (text) => jbody('/reminders', 'POST', { text });
export const toggleReminder = (line, done) =>
  jbody(`/reminders/${line}`, 'PATCH', { done });
export const removeReminder = (line) =>
  jbody(`/reminders/${line}`, 'DELETE');

export const listVaultTree = (directory = '') => {
  const q = directory ? `?directory=${encodeURIComponent(directory)}` : '';
  return jget(`/vault/tree${q}`);
};
export const readVaultFile = (path) =>
  jget(`/vault/file?path=${encodeURIComponent(path)}`);

export const toolsCatalog = () => jget('/tools/catalog');
export const toggleTool = (id, enabled) =>
  jbody(`/tools/catalog/${encodeURIComponent(id)}`, 'POST', { enabled });

export const getProfile = () => jget('/profile');
export const patchProfile = (patch) => jbody('/profile', 'PATCH', patch);
