CodegenRestDashboard (zero-deps)

Setup
1) Copy .env.example to .env and fill:
   - CODEGEN_TOKEN=sk-...
   - ORG_ID=...
2) Do NOT commit .env (ignored by .gitignore here).

Run the dashboard
- node CodegenRestDashboard/server.js
- Open http://localhost:8080
- Header shows Active count; hover to see active list and click to open logs dialog
- No manual refresh; lists auto-refresh periodically

Commands (from repo root)
- node CodegenRestDashboard/commands/list_agent_runs.js [--limit 10]
- node CodegenRestDashboard/commands/get_agent_run.js --id 123
- node CodegenRestDashboard/commands/get_agent_run_logs.js --id 123 [--limit 50]
- node CodegenRestDashboard/commands/create_agent_run.js --prompt "Fix the bug" [--repo_id 123 --model "Sonnet 4.5"]
- node CodegenRestDashboard/commands/resume_agent_run.js --id 123 --prompt "Follow-up"
- node CodegenRestDashboard/commands/generate_setup_commands.js --repo_id 123 --prompt "Init sandbox"

Cloudflare webhook (optional)
- Deploy webhook_server.js as a Worker to route POST https://www.pixelium.uk/webhook
- Optional header: X-Webhook-Secret with WEBHOOK_SECRET in Worker vars
- For local demo, POST sample payload to http://localhost:8080/api/webhook

E2E smoke test
- node CodegenRestDashboard/e2e_test.js
- Optionally set E2E_CREATE_PROMPT to force creating a run in the test

