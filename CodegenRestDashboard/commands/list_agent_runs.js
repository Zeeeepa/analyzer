#!/usr/bin/env node
const { loadEnv } = require('./config');
const { get } = require('./http');
const { parseArgs, pretty } = require('./utils');

(async () => {
  try {
    const { orgId } = loadEnv();
    const args = parseArgs(process.argv);
    const query = {};
    if (args.user_id) query.user_id = Number(args.user_id);
    if (args.source_type) query.source_type = args.source_type;
    if (args.skip) query.skip = Number(args.skip);
    if (args.limit) query.limit = Number(args.limit);

    const res = await get(`/organizations/${orgId}/agent/runs`, { query });
    console.log(pretty(res));
  } catch (err) {
    console.error('[list_agent_runs] Error:', err.message);
    process.exit(1);
  }
})();

