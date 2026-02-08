// App state and helpers (no deps)

const State = {
  runs: [],
  active: [],
  past: [],
  pinned: new Set(JSON.parse(localStorage.getItem('pinnedRuns') || '[]')),
  templates: JSON.parse(localStorage.getItem('templates') || '[]'),
  autoChain: JSON.parse(localStorage.getItem('autoChain') || '{"enabled":true}'),
  watchers: new Map(), // id -> interval handle
  logsStreams: new Map(), // id -> { paused, nextSkip, buffer }
};

function savePinned() {
  localStorage.setItem('pinnedRuns', JSON.stringify(Array.from(State.pinned)));
}

function saveTemplates() {
  localStorage.setItem('templates', JSON.stringify(State.templates));
}

function saveAutoChain() {
  localStorage.setItem('autoChain', JSON.stringify(State.autoChain));
}

function statusIsActive(status) {
  if (!status) return true;
  const s = String(status).toUpperCase();
  return !(s.includes('COMPLETE') || s.includes('FAILED') || s.includes('CANCEL') || s.includes('ERROR') || s.includes('STOP'));
}

function partitionRuns(items) {
  const active = [];
  const past = [];
  for (const it of items) {
    if (statusIsActive(it.status)) active.push(it); else past.push(it);
  }
  return { active, past };
}

window.AppState = { State, savePinned, saveTemplates, saveAutoChain, statusIsActive, partitionRuns };

