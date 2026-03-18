// Minimal .env loader without dependencies
// Supports keys like CODEGEN_TOKEN, ORG_ID, API_BASE
// Also tolerates 'codegen token' and 'org_id' in various cases

const fs = require('fs');
const path = require('path');

function loadEnv() {
  const baseDir = path.join(__dirname, '..');
  const envPath = path.join(baseDir, '.env');
  const result = {};

  if (fs.existsSync(envPath)) {
    const text = fs.readFileSync(envPath, 'utf8');
    text.split(/\r?\n/).forEach((line) => {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) return;
      const eq = trimmed.indexOf('=');
      if (eq === -1) return;
      const rawKey = trimmed.slice(0, eq).trim();
      const value = trimmed.slice(eq + 1).trim();
      const normKey = rawKey.replace(/\s+/g, '_').toUpperCase();
      result[normKey] = value;
    });
  }

  // Also allow process.env to override
  const merged = {
    ...result,
    ...(process.env.CODEGEN_TOKEN ? { CODEGEN_TOKEN: process.env.CODEGEN_TOKEN } : {}),
    ...(process.env.ORG_ID ? { ORG_ID: process.env.ORG_ID } : {}),
    ...(process.env.API_BASE ? { API_BASE: process.env.API_BASE } : {}),
    ...(process.env.WEBHOOK_SECRET ? { WEBHOOK_SECRET: process.env.WEBHOOK_SECRET } : {}),
  };

  // Backwards-compat with space key: 'codegen token'
  if (!merged.CODEGEN_TOKEN && merged.CODEGEN_TOKEN === undefined && merged['CODEGEN_TOKEN'] === undefined) {
    if (merged['CODEGEN_TOKEN'] === undefined && merged['CODEGEN_TOKEN'] === undefined) {
      // no-op; kept for safety
    }
  }

  // Provide defaults
  const token = merged.CODEGEN_TOKEN || merged.TOKEN || merged.CODEGEN || merged.CODEGENTOKEN || merged['CODEGEN_TOKEN'] || merged['CODEGENTOKEN'] || merged['CODEGEN-TOKEN'];
  const orgId = merged.ORG_ID || merged.ORGID || merged['ORG-ID'] || merged['ORG_ID'];
  const apiBase = merged.API_BASE || 'https://api.codegen.com/v1';
  const webhookSecret = merged.WEBHOOK_SECRET || '';

  if (!token) {
    console.warn('[config] WARNING: CODEGEN_TOKEN not found. Place it in CodegenRestDashboard/.env as CODEGEN_TOKEN=...');
  }
  if (!orgId) {
    console.warn('[config] WARNING: ORG_ID not found. Place it in CodegenRestDashboard/.env as ORG_ID=...');
  }

  return { token, orgId, apiBase, webhookSecret, baseDir };
}

module.exports = { loadEnv };

