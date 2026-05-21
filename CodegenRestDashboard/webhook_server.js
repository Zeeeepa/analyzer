// Cloudflare Worker to handle Codegen webhooks at /webhook
// Deployment target: https://www.pixelium.uk/webhook
// Module syntax (ESM) Worker

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname !== '/webhook') {
      return new Response('Not Found', { status: 404 });
    }
    if (request.method === 'OPTIONS') {
      return new Response('', { status: 204, headers: corsHeaders() });
    }
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405, headers: corsHeaders() });
    }
    let payload;
    try {
      payload = await request.json();
    } catch (e) {
      return new Response(JSON.stringify({ error: 'Invalid JSON' }), { status: 400, headers: jsonHeaders() });
    }

    // Optional shared-secret check (set WEBHOOK_SECRET in Cloudflare env)
    const secret = env.WEBHOOK_SECRET || '';
    const provided = request.headers.get('X-Webhook-Secret') || '';
    if (secret && provided !== secret) {
      return new Response(JSON.stringify({ error: 'Unauthorized' }), { status: 401, headers: jsonHeaders() });
    }

    // Log basic fields (Cloudflare logs)
    console.log('[webhook] event', JSON.stringify({
      org_id: payload.organization_id,
      run_id: payload.id,
      status: payload.status,
      created_at: payload.created_at,
    }));

    // Respond 200 OK
    return new Response(JSON.stringify({ ok: true }), { status: 200, headers: jsonHeaders() });
  }
};

function jsonHeaders() {
  return { 'Content-Type': 'application/json', ...corsHeaders() };
}
function corsHeaders() {
  return { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Methods': 'POST,OPTIONS', 'Access-Control-Allow-Headers': 'Content-Type, X-Webhook-Secret' };
}

