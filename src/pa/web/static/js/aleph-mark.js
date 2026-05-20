// Renders the Hebrew letter א in green serif. Size controlled via font-size.

export function alephMark({ size = 32, weight = 500 } = {}) {
  return `<span class="aleph-mark" style="font-size:${size}px;font-weight:${weight}" aria-label="Aleph">א</span>`;
}
