// AlephThinking: three Hebrew alephs (א) set in Rubik that cascade as a
// typographic ellipsis while the agent is preparing tokens. Each glyph
// lifts, brightens, and bumps weight (400→650 via Rubik's variable axis)
// at its peak, staggered so motion reads as continuous flow. A small
// monospace timer beneath the row counts elapsed thinking seconds.
//
// Vanilla translation of the AlephThinking.tsx design.

const STYLE_ID = 'aleph-thinking-keyframes';

function injectKeyframes() {
  if (typeof document === 'undefined') return;
  if (document.getElementById(STYLE_ID)) return;
  const el = document.createElement('style');
  el.id = STYLE_ID;
  el.textContent = `
    .aleph-thinking {
      display: inline-flex;
      flex-direction: column;
      align-items: flex-start;
      gap: 4px;
      line-height: 1;
    }
    .aleph-thinking .row {
      display: inline-flex;
      align-items: baseline;
      direction: rtl;
      unicode-bidi: isolate;
    }
    .aleph-thinking .glyph {
      display: inline-block;
      font-family: "Rubik", system-ui, "Helvetica Neue", Arial, sans-serif;
      line-height: 1;
      font-weight: 500;
      transform-origin: center;
      animation: aleph-thinking-pulse var(--aleph-thinking-duration, 1.6s) ease-in-out infinite;
    }
    .aleph-thinking .timer {
      font-family: var(--mono, ui-monospace, Menlo, monospace);
      font-size: 11px;
      color: var(--muted, #8a8276);
      font-variant-numeric: tabular-nums;
      letter-spacing: 0.02em;
    }
    @keyframes aleph-thinking-pulse {
      0%, 100% {
        opacity: 0.22;
        transform: translateY(0);
        font-variation-settings: 'wght' 400;
      }
      35% {
        opacity: 1;
        transform: translateY(-3px);
        font-variation-settings: 'wght' 650;
      }
      62% {
        opacity: 0.45;
        transform: translateY(0);
        font-variation-settings: 'wght' 400;
      }
    }
    @media (prefers-reduced-motion: reduce) {
      .aleph-thinking .glyph {
        animation: none !important;
        opacity: 0.6 !important;
        transform: none !important;
      }
    }
  `;
  document.head.appendChild(el);
}

function formatElapsed(ms) {
  const totalSeconds = Math.floor(ms / 1000);
  if (totalSeconds < 60) return `${totalSeconds}s`;
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return `${m}m ${String(s).padStart(2, '0')}s`;
}

// Build the HTML for the indicator. Returns a string so callers can drop
// it inline alongside other rendered markup (matches the rest of the UI's
// renderX(): string convention).
//
// opts:
//   size:     glyph size in px (default 20)
//   color:    glyph color (default forest green, var(--green))
//   duration: full pulse-cycle in seconds (default 2.0)
//   gap:      inter-glyph gap in px (default size * 0.22)
export function alephThinkingHtml({
  size = 20,
  color = 'var(--green, #355c41)',
  duration = 2.0,
  gap,
} = {}) {
  injectKeyframes();
  const trail = typeof gap === 'number' ? gap : Math.round(size * 0.22 * 100) / 100;
  const rowStyle = `gap:${trail}px`;
  const glyphStyle = `font-size:${size}px;color:${color}`;
  const cssVar = `--aleph-thinking-duration:${duration}s`;
  // The row is `direction: rtl` so neighbouring Latin text never gets
  // flipped — that puts the first DOM child on the right visually. To
  // get a left→right cascade we hand the largest delay to the first
  // (rightmost) glyph and zero to the last (leftmost) one.
  const delays = [duration * 0.26, duration * 0.13, 0];
  const glyphs = delays.map((d) => (
    `<span class="glyph" aria-hidden="true" style="${glyphStyle};animation-delay:${d}s">א</span>`
  )).join('');
  return `
    <span
      class="aleph-thinking"
      role="status"
      aria-label="Aleph is thinking"
      data-started="0"
      style="${cssVar}"
    >
      <span class="row" style="${rowStyle}">${glyphs}</span>
      <span class="timer" data-aleph-thinking-timer aria-hidden="true">0s</span>
    </span>`;
}

// Drive the timer for one indicator. Call with the element node (the
// `.aleph-thinking` wrapper). Returns a stop() function — call it on
// teardown (when the first token arrives or the stream ends).
export function startAlephThinkingTimer(el) {
  if (!el) return () => {};
  const timer = el.querySelector('[data-aleph-thinking-timer]');
  if (!timer) return () => {};
  const started = performance.now();
  el.dataset.started = String(started);
  let raf = 0;
  let lastShown = -1;
  const tick = () => {
    const elapsed = performance.now() - started;
    const seconds = Math.floor(elapsed / 1000);
    if (seconds !== lastShown) {
      timer.textContent = formatElapsed(elapsed);
      lastShown = seconds;
    }
    raf = requestAnimationFrame(tick);
  };
  raf = requestAnimationFrame(tick);
  return () => {
    if (raf) cancelAnimationFrame(raf);
  };
}
