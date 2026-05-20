// POST /chat returns a Server-Sent-Event stream of TurnEvent JSON.
// Yields {kind, text?, tool?} payloads to the caller.

export async function* chatStream({ message, threadId }) {
  const resp = await fetch('/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, thread_id: threadId }),
  });
  if (!resp.ok) {
    const text = await resp.text();
    yield { kind: 'error', text: `server: ${resp.status} ${text}` };
    return;
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf('\n\n')) !== -1) {
      const frame = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      const line = frame.split('\n').find((l) => l.startsWith('data: '));
      if (!line) continue;
      try {
        yield JSON.parse(line.slice(6));
      } catch (e) {
        yield { kind: 'error', text: `bad frame: ${e.message}` };
      }
    }
  }
}
