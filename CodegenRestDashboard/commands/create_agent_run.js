#!/usr/bin/env node
const { loadEnv } = require('./config');
const { post } = require('./http');
const { parseArgs, pretty } = require('./utils');

(async () => {
  try {
    const { orgId } = loadEnv();
    const args = parseArgs(process.argv);
    const prompt = args.prompt || args.p;
    if (!prompt) throw new Error('Missing --prompt');

    const body = { prompt };
    if (args.repo_id) body.repo_id = Number(args.repo_id);
    if (args.model) body.model = args.model;
    if (args.agent_type) body.agent_type = args.agent_type;
    if (args.images) {
      // comma-separated data URIs
      body.images = String(args.images).split(',').map((s) => s.trim()).filter(Boolean);
    }

    const res = await post(`/organizations/${orgId}/agent/run`, body);
    console.log(pretty(res));
  } catch (err) {
    console.error('[create_agent_run] Error:', err.message);
    process.exit(1);
  }
})();

