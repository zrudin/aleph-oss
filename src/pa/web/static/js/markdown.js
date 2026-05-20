// Wraps `marked` (loaded as global from the CDN script tag).
// Assistant prose uses greenDeep for bold — CSS already styles `.prose strong`.

export function renderMarkdown(text) {
  if (window.marked && typeof window.marked.parse === 'function') {
    return window.marked.parse(text || '');
  }
  return escape(text || '').replace(/\n/g, '<br>');
}

export function escape(s) {
  return String(s).replace(/[&<>"]/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]
  ));
}
