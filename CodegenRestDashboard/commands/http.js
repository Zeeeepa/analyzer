// Minimal HTTP client without external deps
// Uses global fetch if available (Node 18+),
// otherwise falls back to https.request

const https = require('https');
const { loadEnv } = require('./config');

const { token, apiBase } = loadEnv();

function buildHeaders(extra = {}) {
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...extra,
  };
  return headers;
}

async function fetchWithFallback(url, options) {
  if (typeof fetch === 'function') {
    return fetch(url, options);
  }
  // Fallback to https.request
  return new Promise((resolve, reject) => {
    const u = new URL(url);
    const req = https.request(
      {
        method: options.method || 'GET',
        protocol: u.protocol,
        hostname: u.hostname,
        port: u.port || 443,
        path: `${u.pathname}${u.search}`,
        headers: options.headers,
      },
      (res) => {
        const chunks = [];
        res.on('data', (d) => chunks.push(d));
        res.on('end', () => {
          const body = Buffer.concat(chunks).toString('utf8');
          resolve({
            ok: res.statusCode >= 200 && res.statusCode < 300,
            status: res.statusCode,
            text: async () => body,
            json: async () => {
              try { return JSON.parse(body || '{}'); } catch { return {}; }
            },
          });
        });
      }
    );
    req.on('error', reject);
    if (options.body) req.write(options.body);
    req.end();
  });
}

async function get(path, { query } = {}) {
  const url = new URL(apiBase.replace(/\/$/, '') + path);
  if (query) {
    Object.entries(query).forEach(([k, v]) => {
      if (v !== undefined && v !== null) url.searchParams.set(k, String(v));
    });
  }
  const res = await fetchWithFallback(url.toString(), {
    method: 'GET',
    headers: buildHeaders(),
  });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`GET ${url} failed: ${res.status} ${txt}`);
  }
  return res.json();
}

async function post(path, body) {
  const url = apiBase.replace(/\/$/, '') + path;
  const res = await fetchWithFallback(url, {
    method: 'POST',
    headers: buildHeaders(),
    body: JSON.stringify(body || {}),
  });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`POST ${url} failed: ${res.status} ${txt}`);
  }
  return res.json();
}

module.exports = { get, post };

