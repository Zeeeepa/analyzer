// Client API for dashboard -> talks to local proxy server endpoints

async function apiGet(path, params) {
  const url = new URL(path, window.location.origin);
  if (params) Object.entries(params).forEach(([k, v]) => v !== undefined && url.searchParams.set(k, v));
  const res = await fetch(url.toString(), { method: 'GET', headers: { 'Content-Type': 'application/json' } });
  if (!res.ok) throw new Error(`GET ${url} failed: ${res.status}`);
  return res.json();
}

async function apiPost(path, body) {
  const url = new URL(path, window.location.origin);
  const res = await fetch(url.toString(), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  });
  if (!res.ok) throw new Error(`POST ${url} failed: ${res.status}`);
  return res.json();
}

const DashboardAPI = {
  listRuns(params) { return apiGet('/api/agent/runs', params); },
  getRun(id) { return apiGet(`/api/agent/run/${id}`); },
  getRunLogs(id, params) { return apiGet(`/api/agent/run/${id}/logs`, params); },
  createRun({ prompt, model, repo_id, agent_type, metadata, images }) {
    const body = { prompt };
    if (model) body.model = model;
    if (repo_id) body.repo_id = repo_id;
    if (agent_type) body.agent_type = agent_type;
    if (metadata) body.metadata = metadata;
    if (images) body.images = images;
    return apiPost('/api/agent/run', body);
  },
  resumeRun({ agent_run_id, prompt, images }) {
    const body = { agent_run_id, prompt };
    if (images) body.images = images;
    return apiPost('/api/agent/run/resume', body);
  },
  generateSetupCommands({ repo_id, prompt }) {
    const body = { repo_id };
    if (prompt) body.prompt = prompt;
    return apiPost('/api/setup-commands/generate', body);
  },
};

window.DashboardAPI = DashboardAPI;

