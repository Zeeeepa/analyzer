// Zero-deps local server: serves dashboard and proxies Codegen API
// Usage: node CodegenRestDashboard/server.js

const http = require('http');
const fs = require('fs');
const path = require('path');
const url = require('url');
const { loadEnv } = require('./commands/config');
const { get, post } = require('./commands/http');

const { orgId, baseDir } = loadEnv();
const DASH_DIR = path.join(__dirname, 'dashboard');
const PORT = process.env.PORT ? Number(process.env.PORT) : 8080;

// In-memory dev webhook event buffer
const webhookEvents = [];

function send(res, status, body, headers = {}) {
  const h = { 'Content-Type': 'text/plain; charset=utf-8', ...headers };
  res.writeHead(status, h);
  res.end(body);
}

function sendJSON(res, status, obj) {
  send(res, status, JSON.stringify(obj), { 'Content-Type': 'application/json; charset=utf-8' });
}

function guessContentType(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  switch (ext) {
    case '.html': return 'text/html; charset=utf-8';
    case '.css': return 'text/css; charset=utf-8';
    case '.js': return 'application/javascript; charset=utf-8';
    case '.json': return 'application/json; charset=utf-8';
    case '.svg': return 'image/svg+xml';
    case '.png': return 'image/png';
    case '.jpg':
    case '.jpeg': return 'image/jpeg';
    default: return 'application/octet-stream';
  }
}

function serveStatic(req, res, pathname) {
  let filePath = path.join(DASH_DIR, pathname === '/' ? 'index.html' : pathname.replace(/^\/+/, ''));
  if (!filePath.startsWith(DASH_DIR)) {
    return send(res, 403, 'Forbidden');
  }
  fs.readFile(filePath, (err, data) => {
    if (err) {
      if (pathname !== '/' && !path.extname(filePath)) {
        // SPA-style fallback to index.html
        const idx = path.join(DASH_DIR, 'index.html');
        fs.readFile(idx, (e2, d2) => {
          if (e2) return send(res, 404, 'Not Found');
          send(res, 200, d2, { 'Content-Type': 'text/html; charset=utf-8' });
        });
        return;
      }
      return send(res, 404, 'Not Found');
    }
    send(res, 200, data, { 'Content-Type': guessContentType(filePath) });
  });
}

function collectJSON(req) {
  return new Promise((resolve, reject) => {
    let body = '';
    req.on('data', (chunk) => (body += chunk));
    req.on('end', () => {
      if (!body) return resolve({});
      try {
        resolve(JSON.parse(body));
      } catch (e) {
        reject(new Error('Invalid JSON'));
      }
    });
    req.on('error', reject);
  });
}

function isTerminal(status) {
  if (!status) return false;
  const s = String(status).toUpperCase();
  return (
    s.includes('COMPLETE') ||
    s.includes('FAILED') ||
    s.includes('CANCEL') ||
    s.includes('ERROR') ||
    s.includes('STOP')
  );
}

const server = http.createServer(async (req, res) => {
  try {
    const parsed = url.parse(req.url, true);
    const pathname = parsed.pathname || '/';

    // API routes (proxy)
    if (pathname.startsWith('/api/')) {
      // Basic CORS for local dev
      res.setHeader('Access-Control-Allow-Origin', '*');
      res.setHeader('Access-Control-Allow-Methods', 'GET,POST,OPTIONS');
      res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
      if (req.method === 'OPTIONS') return send(res, 204, '');

      // Dev-only: receive webhook and store event
      if (pathname === '/api/webhook' && req.method === 'POST') {
        const payload = await collectJSON(req).catch(() => null);
        if (!payload) return sendJSON(res, 400, { error: 'Invalid JSON' });
        webhookEvents.push({ ts: Date.now(), payload });
        return sendJSON(res, 200, { ok: true });
      }
      if (pathname === '/api/events' && req.method === 'GET') {
        return sendJSON(res, 200, { items: webhookEvents.slice(-100) });
      }

      // Proxy Codegen endpoints
      // GET /api/agent/runs
      if (pathname === '/api/agent/runs' && req.method === 'GET') {
        const data = await get(`/organizations/${orgId}/agent/runs`, { query: parsed.query });
        return sendJSON(res, 200, data);
      }
      // GET /api/agent/run/:id
      const runMatch = pathname.match(/^\/api\/agent\/run\/(\d+)(?:\/logs)?$/);
      if (runMatch && req.method === 'GET' && !pathname.endsWith('/logs')) {
        const id = Number(runMatch[1]);
        const data = await get(`/organizations/${orgId}/agent/run/${id}`);
        return sendJSON(res, 200, data);
      }
      // GET /api/agent/run/:id/logs (alpha)
      const logsMatch = pathname.match(/^\/api\/agent\/run\/(\d+)\/logs$/);
      if (logsMatch && req.method === 'GET') {
        const id = Number(logsMatch[1]);
        const q = parsed.query || {};
        const data = await get(`/alpha/organizations/${orgId}/agent/run/${id}/logs`, { query: q });
        return sendJSON(res, 200, data);
      }
      // POST /api/agent/run
      if (pathname === '/api/agent/run' && req.method === 'POST') {
        const body = await collectJSON(req).catch(() => null);
        if (!body) return sendJSON(res, 400, { error: 'Invalid JSON' });
        const data = await post(`/organizations/${orgId}/agent/run`, body);
        return sendJSON(res, 200, data);
      }
      // POST /api/agent/run/resume
      if (pathname === '/api/agent/run/resume' && req.method === 'POST') {
        const body = await collectJSON(req).catch(() => null);
        if (!body) return sendJSON(res, 400, { error: 'Invalid JSON' });
        const data = await post(`/organizations/${orgId}/agent/run/resume`, body);
        return sendJSON(res, 200, data);
      }
      // POST /api/setup-commands/generate
      if (pathname === '/api/setup-commands/generate' && req.method === 'POST') {
        const body = await collectJSON(req).catch(() => null);
        if (!body) return sendJSON(res, 400, { error: 'Invalid JSON' });
        const data = await post(`/organizations/${orgId}/setup-commands/generate`, body);
        return sendJSON(res, 200, data);
      }

      return sendJSON(res, 404, { error: 'Not Found' });
    }

    // Static dashboard
    return serveStatic(req, res, pathname);
  } catch (err) {
    console.error('[server] Error:', err);
    return sendJSON(res, 500, { error: 'Internal Server Error' });
  }
});

server.listen(PORT, () => {
  console.log(`[dashboard] Listening on http://localhost:${PORT}`);
});

