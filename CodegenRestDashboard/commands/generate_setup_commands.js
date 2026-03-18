#!/usr/bin/env node
const { loadEnv } = require('./config');
const { post } = require('./http');
const { parseArgs, pretty } = require('./utils');

(async () => {
  try {
    const { orgId } = loadEnv();
    const args = parseArgs(process.argv);
    const repoId = args.repo_id || args.repo;
    const prompt = args.prompt || args.p;

    if (!repoId) throw new Error('Missing --repo_id');

    const body = { repo_id: Number(repoId) };
    if (prompt) body.prompt = prompt;

    const res = await post(`/organizations/${orgId}/setup-commands/generate`, body);
    console.log(pretty(res));
  } catch (err) {
    console.error('[generate_setup_commands] Error:', err.message);
    process.exit(1);
  }
})();

