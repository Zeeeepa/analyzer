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
// Chain plans persistence (per run)
State.chainPlans = (() => { try { return JSON.parse(localStorage.getItem('chainPlans')||'{}'); } catch { return {}; }})();
function saveChainPlans(){ try { localStorage.setItem('chainPlans', JSON.stringify(State.chainPlans)); } catch(e) { /* ignore */ } }
function getChainPlan(runId){ return State.chainPlans[String(runId)] || null; }
function setChainPlan(runId, data){ State.chainPlans[String(runId)] = data; saveChainPlans(); }
function removeChainPlan(runId){ delete State.chainPlans[String(runId)]; saveChainPlans(); }


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

window.AppState = { State, savePinned, saveTemplates, saveAutoChain, statusIsActive, partitionRuns, saveChainPlans, getChainPlan, setChainPlan, removeChainPlan };
