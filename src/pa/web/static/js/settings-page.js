// Settings page: section-driven content. Wired endpoints noted inline.

import * as state from './state.js';
import * as api from './api.js';
import { alephMark } from './aleph-mark.js';
import { escape } from './markdown.js';

const SECTION_TITLES = {
  profile: 'Profile',
  model: 'Model',
  tools: 'Tools & connectors',
  appearance: 'Appearance',
  shortcuts: 'Shortcuts',
  about: 'About',
};

const LS_KEYS = {
  dailyNudge: 'aleph.dailyNudge',
  quietHours: 'aleph.quietHours',
  readingWidth: 'aleph.readingWidth',
  showDocket: 'aleph.showDocket',
};

function lsGet(key, dflt) {
  try {
    const v = localStorage.getItem(key);
    return v == null ? dflt : JSON.parse(v);
  } catch { return dflt; }
}
function lsSet(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch {}
}

export function render(target, { openToolsModal } = {}) {
  const s = state.get();
  const section = s.settingsSection || 'profile';
  target.innerHTML = `
    <div class="page-header">
      <div class="row">
        <div class="page-kicker">Preferences</div>
      </div>
      <h1 class="page-title">${escape(SECTION_TITLES[section] || 'Settings')}</h1>
    </div>
    <div class="page-body">
      <div class="settings-wrap"></div>
    </div>
  `;
  const wrap = target.querySelector('.settings-wrap');
  switch (section) {
    case 'profile': renderProfile(wrap); break;
    case 'model': renderModel(wrap); break;
    case 'tools': renderTools(wrap, openToolsModal); break;
    case 'appearance': renderAppearance(wrap); break;
    case 'shortcuts': renderShortcuts(wrap); break;
    case 'about': renderAbout(wrap); break;
  }
}

function renderProfile(host) {
  const s = state.get();
  const p = s.profile || { name: '', pronouns: '', voice: 'Warm, patient (default)' };
  host.innerHTML = `
    <div class="settings-block">
      <h2>You</h2>
      <div class="subtitle">How Aleph addresses you and the tone of replies. Stored in profile.md.</div>

      <div class="set-field">
        <div class="label">Name</div>
        <div>
          <input type="text" data-field="name" value="${escape(p.name || '')}" />
        </div>
      </div>
      <div class="set-field">
        <div class="label">Pronouns</div>
        <div>
          <input type="text" data-field="pronouns" value="${escape(p.pronouns || '')}" />
        </div>
      </div>
      <div class="set-field">
        <div class="label">Voice</div>
        <div>
          <select data-field="voice">
            ${['Warm, patient (default)', 'Quiet, brief', 'Playful']
              .map((v) => `<option ${p.voice === v ? 'selected' : ''}>${escape(v)}</option>`).join('')}
          </select>
          <div class="hint">Aleph will lean toward this tone.</div>
        </div>
      </div>
      <div class="set-field">
        <div class="label"></div>
        <div>
          <button class="lc-action" data-action="save-profile" style="background:var(--green);color:var(--paper)">save</button>
          <span class="hint" data-save-status></span>
        </div>
      </div>
    </div>
  `;

  host.querySelector('[data-action="save-profile"]').addEventListener('click', async () => {
    const get = (f) => host.querySelector(`[data-field="${f}"]`).value;
    const payload = { name: get('name'), pronouns: get('pronouns'), voice: get('voice') };
    const status = host.querySelector('[data-save-status]');
    status.textContent = 'saving…';
    try {
      const next = await api.patchProfile(payload);
      state.set({ profile: next });
      status.textContent = 'saved.';
      setTimeout(() => { status.textContent = ''; }, 1800);
    } catch (e) {
      status.textContent = `failed: ${e.message}`;
    }
  });
}

function renderModel(host) {
  const s = state.get();
  host.innerHTML = `
    <div class="settings-block">
      <h2>Model</h2>
      <div class="subtitle">What Aleph thinks with. Edit <code>.env</code> to change these for now.</div>

      <div class="set-field">
        <div class="label">Active model</div>
        <div>
          <input type="text" value="${escape(s.vault.model || '')}" disabled />
          <div class="hint">Set via <code>PA_CHAT_MODEL</code>. Runtime override is on the roadmap.</div>
        </div>
      </div>
      <div class="set-field">
        <div class="label">Embedding model</div>
        <div>
          <input type="text" value="${escape(s.vault.embedModel || '')}" disabled />
          <div class="hint">Set via <code>PA_EMBED_MODEL</code>.</div>
        </div>
      </div>
    </div>
  `;
}

function renderTools(host, openToolsModal) {
  host.innerHTML = `
    <div class="settings-block">
      <h2>Tools &amp; connectors</h2>
      <div class="subtitle">What Aleph can reach for. Disabled tools are still known about.</div>
      <div class="set-field">
        <div class="label">Manage tools</div>
        <div>
          <button class="lc-action" data-open-tools style="background:var(--green);color:var(--paper);font-size:14px;padding:5px 18px">open tools →</button>
          <div class="hint">Browse, search, and toggle individual tools.</div>
        </div>
      </div>
    </div>
  `;
  host.querySelector('[data-open-tools]').addEventListener('click', () => openToolsModal?.());
}

function renderAppearance(host) {
  const swatches = [
    { id: 'parchment', label: 'Parchment', enabled: true },
    { id: 'cream', label: 'Cream', enabled: false },
    { id: 'bone', label: 'Bone', enabled: false },
    { id: 'dusk', label: 'Dusk', enabled: false },
  ];
  const showDocket = lsGet(LS_KEYS.showDocket, true);
  const width = lsGet(LS_KEYS.readingWidth, 'comfortable');

  host.innerHTML = `
    <div class="settings-block">
      <h2>Appearance</h2>
      <div class="subtitle">The look of the journal.</div>

      <div class="set-field">
        <div class="label">Theme</div>
        <div>
          <div class="theme-swatches">
            ${swatches.map((s) => `
              <div class="theme-swatch ${s.id === 'parchment' ? 'on' : ''} ${s.enabled ? '' : 'disabled'}">
                <span class="dot"></span>${s.label}
              </div>`).join('')}
          </div>
          <div class="hint">Other palettes are designed but not yet wired (todo.md).</div>
        </div>
      </div>
      <div class="set-field">
        <div class="label">Reading width</div>
        <div>
          <select data-pref="readingWidth">
            <option value="narrow" ${width === 'narrow' ? 'selected' : ''}>Narrow (720px)</option>
            <option value="comfortable" ${width === 'comfortable' ? 'selected' : ''}>Comfortable (840px)</option>
            <option value="wide" ${width === 'wide' ? 'selected' : ''}>Wide (960px)</option>
          </select>
          <div class="hint">Saved locally. Not yet applied — wires up when the docket-toggle lands.</div>
        </div>
      </div>
      <div class="set-field">
        <div class="label">Show right docket</div>
        <div>
          <button class="toggle ${showDocket ? 'on' : ''}" data-pref="showDocket">
            <span class="knob"></span>
          </button>
        </div>
      </div>
    </div>
  `;

  host.querySelector('[data-pref="readingWidth"]')?.addEventListener('change', (e) => {
    lsSet(LS_KEYS.readingWidth, e.target.value);
  });
  host.querySelector('[data-pref="showDocket"]')?.addEventListener('click', (e) => {
    const next = !e.currentTarget.classList.contains('on');
    lsSet(LS_KEYS.showDocket, next);
    e.currentTarget.classList.toggle('on', next);
  });
}

function renderShortcuts(host) {
  const rows = [
    ['⌘ ↵', 'send message'],
    ['⌘ N', 'new entry (chat / task / note)'],
    ['⌘ /', 'toggle tools panel'],
    ['⌘ ,', 'open settings'],
    ['⌘ K', 'open search (in modals)'],
    ['⌘ ⇧ D', 'show today’s docket'],
  ];
  host.innerHTML = `
    <div class="settings-block">
      <h2>Shortcuts</h2>
      <div class="subtitle">The keys Aleph listens for.</div>
      ${rows.map(([combo, label]) => `
        <div class="kbd-row">
          <span class="label">${escape(label)}</span>
          <span class="combo">${escape(combo)}</span>
        </div>`).join('')}
    </div>
  `;
}

function renderAbout(host) {
  const s = state.get();
  const dailyNudge = lsGet(LS_KEYS.dailyNudge, true);
  const quietHours = lsGet(LS_KEYS.quietHours, true);
  host.innerHTML = `
    <div class="settings-block">
      <h2>About</h2>
      <div class="about-mast">
        ${alephMark({ size: 48 })}
        <div>
          <div class="title">Aleph</div>
          <div class="sub">a quiet journal · ${escape(s.vault.model || 'no model')} · ${s.vault.mounted ? 'vault mounted' : 'vault not mounted'}</div>
        </div>
      </div>

      <div class="set-field">
        <div class="label">Daily nudge</div>
        <div>
          <button class="toggle ${dailyNudge ? 'on' : ''}" data-pref="dailyNudge">
            <span class="knob"></span>
          </button>
          <div class="hint">Nudge me to write each morning. Stored locally; scheduler integration is on the roadmap.</div>
        </div>
      </div>
      <div class="set-field">
        <div class="label">Quiet hours</div>
        <div>
          <button class="toggle ${quietHours ? 'on' : ''}" data-pref="quietHours">
            <span class="knob"></span>
          </button>
          <div class="hint">9pm – 8am. Stored locally; scheduler does not yet read this.</div>
        </div>
      </div>
    </div>
  `;
  host.querySelectorAll('.toggle[data-pref]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const key = LS_KEYS[btn.dataset.pref];
      const next = !btn.classList.contains('on');
      lsSet(key, next);
      btn.classList.toggle('on', next);
    });
  });
}
