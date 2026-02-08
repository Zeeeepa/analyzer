#!/usr/bin/env node
const { loadEnv } = require('./config');
const { get } = require('./http');
const { parseArgs, pretty } = require('./utils');

(async () => {
  try {
    const { orgId } = loadEnv();
    const args = parseArgs(process.argv);
    const id = args.id || args.agent_run_id;
    if (!id) throw new Error('Missing --id');

    const res = await get(`/organizations/${orgId}/agent/run/${Number(id)}`);
    console.log(pretty(res));
  } catch (err) {
    console.error('[get_agent_run] Error:', err.message);
    process.exit(1);
  }
})();

