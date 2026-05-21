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

    const query = {};
    if (args.skip) query.skip = Number(args.skip);
    if (args.limit) query.limit = Number(args.limit);
    if (args.reverse !== undefined) query.reverse = String(args.reverse) === 'true' || args.reverse === true;

    const res = await get(`/alpha/organizations/${orgId}/agent/run/${Number(id)}/logs`, { query });
    console.log(pretty(res));
  } catch (err) {
    console.error('[get_agent_run_logs] Error:', err.message);
    process.exit(1);
  }
})();

