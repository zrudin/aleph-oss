// Stroked SVG glyphs, copied from take5.jsx RailIcon. Returns a string.

const COMMON = (size) =>
  `width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"`;

const PATHS = {
  today: `<path d="M3 18h18" /><path d="M6.5 18a5.5 5.5 0 0 1 11 0" /><path d="M12 4v2.5" /><path d="M4.5 11.5l1.5 1" /><path d="M19.5 11.5l-1.5 1" /><path d="M7 7l1.2 1.4" /><path d="M17 7l-1.2 1.4" />`,
  tasks: `<path d="M9 5h6a1 1 0 0 1 1 1v1H8V6a1 1 0 0 1 1-1z" /><path d="M7 6H6a2 2 0 0 0-2 2v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-1" /><path d="M9 13l2 2 4-4" />`,
  search: `<circle cx="11" cy="11" r="6" /><path d="M16 16l4 4" />`,
  tools: `<path d="M14.5 4.5a4 4 0 0 0-5.2 5.2L4 15l5 5 5.3-5.3a4 4 0 0 0 5.2-5.2L17 12l-3-3 2.5-4.5z" />`,
  settings: `<circle cx="12" cy="12" r="2.6" /><path d="M19.4 14.5a1 1 0 0 0 .2 1.1l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1 1 0 0 0-1.1-.2 1 1 0 0 0-.6.9V19a2 2 0 1 1-4 0v-.1a1 1 0 0 0-.7-.9 1 1 0 0 0-1.1.2l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1 1 0 0 0 .2-1.1 1 1 0 0 0-.9-.6H5a2 2 0 1 1 0-4h.1a1 1 0 0 0 .9-.7 1 1 0 0 0-.2-1.1l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1 1 0 0 0 1.1.2H10a1 1 0 0 0 .6-.9V5a2 2 0 1 1 4 0v.1a1 1 0 0 0 .6.9 1 1 0 0 0 1.1-.2l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1 1 0 0 0-.2 1.1V10a1 1 0 0 0 .9.6H20a2 2 0 1 1 0 4h-.1a1 1 0 0 0-.9.6z" />`,
};

export function icon(name, size = 18) {
  const path = PATHS[name];
  if (!path) return '';
  return `<svg ${COMMON(size)}>${path}</svg>`;
}
