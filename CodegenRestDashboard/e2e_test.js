#!/usr/bin/env node
// E2E smoke test (requires CodegenRestDashboard/.env with CODEGEN_TOKEN and ORG_ID)
const { loadEnv } = require('./commands/config');
const { get, post } = require('./commands/http');

(async () => {
  const { token, orgId } = loadEnv();
  if (!token || !orgId) {
    console.log('Missing CODEGEN_TOKEN or ORG_ID. Create CodegenRestDashboard/.env first (see .env.example).');
    process.exit(0);
  }
  try {
    console.log('1) List runs');
    const list = await get(`/organizations/${orgId}/agent/runs`, { query: { limit: 5 } });
    console.log('items:', (list.items || []).length);
    let testId = list.items?.[0]?.id;

    if (!testId || process.env.E2E_CREATE_PROMPT) {
      console.log('2) Create a new run (Sonnet 4.5)');
      const created = await post(`/organizations/${orgId}/agent/run`, { prompt: process.env.E2E_CREATE_PROMPT || 'Test ping from dashboard e2e', model: 'Sonnet 4.5' });
      console.log('created id:', created.id);
      testId = created.id;
    }

    console.log('3) Get run');
    const one = await get(`/organizations/${orgId}/agent/run/${testId}`);
    console.log('status:', one.status);

    console.log('4) Get logs (alpha)');
    const logs = await get(`/alpha/organizations/${orgId}/agent/run/${testId}/logs`, { query: { limit: 5 } });
    console.log('logs:', (logs.logs || []).length);

    console.log('OK');
  } catch (e) {
    console.error('E2E failed:', e.message);
    process.exit(1);
  }
})();

