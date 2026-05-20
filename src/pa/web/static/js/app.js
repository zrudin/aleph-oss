// Entry: bootstraps state from /boot JSON + APIs, subscribes the
// render functions for each region of the page.

import * as state from './state.js';
import * as api from './api.js';
import * as rail from './rail.js';
import * as leftCol from './left-col.js';
import * as chatView from './chat-view.js';
import * as fileView from './file-view.js';
import * as tasksPage from './tasks-page.js';
import * as settingsPage from './settings-page.js';
import * as docket from './docket.js';
import * as toolsModal from './tools-modal.js';
import * as shortcuts from './shortcuts.js';

function $(sel) { return document.querySelector(sel); }

function readBoot() {
  try {
    const el = document.getElementById('boot');
    return JSON.parse(el?.textContent || '{}');
  } catch { return {}; }
}

function openTools() { toolsModal.open(); }

function renderAll() {
  const s = state.get();
  rail.render($('#rail'));
  leftCol.render($('#left-col'));
  docket.render($('#docket'));

  switch (s.railActive) {
    case 'tasks':
      tasksPage.render($('#main'));
      break;
    case 'settings':
      settingsPage.render($('#main'), { openToolsModal: openTools });
      break;
    default:
      if (s.viewedFile) fileView.render($('#main'));
      else chatView.render($('#main'), { openToolsModal: openTools });
  }

  toolsModal.render($('#modal-root'));
}

async function bootstrap() {
  const boot = readBoot();
  state.set({
    vault: {
      mounted: !!boot.vault_mounted,
      model: boot.model || '',
      embedModel: boot.embed_model || '',
      vaultPath: boot.vault_path || '',
    },
  });

  // First render with placeholders.
  renderAll();
  state.subscribe(renderAll);

  // Fetch initial data in parallel; render again as each lands.
  await Promise.allSettled([
    api.listThreads().then((d) => state.set({ threads: d.threads || [] })),
    api.listReminders().then((d) => state.set({ reminders: d.active || [] })),
    api.toolsCatalog().then((c) => toolsModal.applyCatalog(c)),
    api.health().then((h) => state.set({
      vault: { ...state.get().vault, mounted: !!h.vault_mounted, model: h.model || '', embedModel: h.embed_model || '' },
    })),
    api.getProfile().then((p) => state.set({ profile: p })).catch(() => {}),
  ]);

  shortcuts.install();
}

bootstrap();
