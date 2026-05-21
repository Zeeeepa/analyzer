#!/usr/bin/env node
const { loadEnv } = require('./config');
const { post } = require('./http');
const { parseArgs, pretty } = require('./utils');

(async () => {
  try {
    const { orgId } = loadEnv();
    const args = parseArgs(process.argv);
    const id = args.id || args.agent_run_id;
    const prompt = args.prompt || args.p;
    if (!id) throw new Error('Missing --id');
    if (!prompt) throw new Error('Missing --prompt');

    const body = { agent_run_id: Number(id), prompt };
    if (args.images) {
      body.images = String(args.images).split(',').map((s) => s.trim()).filter(Boolean);
    }

    const res = await post(`/organizations/${orgId}/agent/run/resume`, body);
    console.log(pretty(res));
  } catch (err) {
    console.error('[resume_agent_run] Error:', err.message);
    process.exit(1);
  }
})();

