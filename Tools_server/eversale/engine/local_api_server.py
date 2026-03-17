"""
Local API Server for eversale-cli.

Provides a lightweight HTTP proxy that routes eversale API calls to any
OpenAI-compatible endpoint. This enables fully local execution with personal
API keys (Z.AI, OpenAI, Anthropic, Ollama, etc.) without hitting eversale.io.

Routes:
  /v1/chat/completions      → upstream chat completions (main LLM path)
  /api/llm/*                → upstream (legacy LLM route)
  /api/anthropic/*           → upstream (Anthropic-format route)
  /api/coding/paas/v4/*      → upstream (Z.AI coding route)
  /api/desktop/validate-license → stub (always returns valid)
  /api/desktop/worker-usage  → stub (always returns ok)
  /api/desktop/kimi-usage    → stub (always returns ok)
  /health                    → server health check

Usage:
  # As a module
  from local_api_server import LocalAPIServer
  server = LocalAPIServer(upstream_base="https://api.z.ai", upstream_api_key="your-key")
  server.start()  # non-blocking, runs in background thread
  print(server.base_url)  # http://127.0.0.1:19532
  server.stop()

  # Via environment variables
  export OPENAI_BASE_URL=https://api.z.ai/api/coding/paas/v4
  export OPENAI_API_KEY=your-key
  export EVERSALE_LOCAL_SERVER=true
  eversale "your task"
"""

import asyncio
import json
import logging
import os
import sys
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Try to import aiohttp; gracefully degrade if not available
try:
    import aiohttp
    from aiohttp import web
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    logger.debug("aiohttp not available; local API server disabled")

DEFAULT_PORT = 19532
DEFAULT_HOST = "127.0.0.1"


def _find_free_port(preferred: int = DEFAULT_PORT) -> int:
    """Find a free TCP port, preferring the given one."""
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((DEFAULT_HOST, preferred))
        sock.close()
        return preferred
    except OSError:
        sock.close()
        # Find any free port
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind((DEFAULT_HOST, 0))
        port = sock.getsockname()[1]
        sock.close()
        return port


async def _proxy_request(request: "web.Request", upstream_base: str, upstream_key: str) -> "web.StreamResponse":
    """Forward a request to the upstream API and stream the response back."""
    # Build upstream URL
    path = request.match_info.get("path", "")
    upstream_url = f"{upstream_base.rstrip('/')}/{path.lstrip('/')}"
    if request.query_string:
        upstream_url += f"?{request.query_string}"

    # Build headers
    headers = {
        "Content-Type": request.content_type or "application/json",
    }
    if upstream_key:
        headers["Authorization"] = f"Bearer {upstream_key}"

    # Read body
    body = await request.read()

    # Check if client wants streaming
    wants_stream = False
    if body:
        try:
            body_json = json.loads(body)
            wants_stream = body_json.get("stream", False)
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

    async with aiohttp.ClientSession() as session:
        try:
            async with session.request(
                method=request.method,
                url=upstream_url,
                headers=headers,
                data=body,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as upstream_resp:
                if wants_stream and upstream_resp.status == 200:
                    # Stream SSE response
                    response = web.StreamResponse(
                        status=upstream_resp.status,
                        headers={
                            "Content-Type": "text/event-stream",
                            "Cache-Control": "no-cache",
                            "Connection": "keep-alive",
                        },
                    )
                    await response.prepare(request)
                    async for chunk in upstream_resp.content.iter_any():
                        await response.write(chunk)
                    await response.write_eof()
                    return response
                else:
                    # Non-streaming: return full response
                    resp_body = await upstream_resp.read()
                    return web.Response(
                        status=upstream_resp.status,
                        body=resp_body,
                        content_type=upstream_resp.content_type or "application/json",
                    )
        except asyncio.TimeoutError:
            return web.json_response(
                {"error": "upstream timeout"}, status=504
            )
        except aiohttp.ClientError as exc:
            return web.json_response(
                {"error": f"upstream error: {exc}"}, status=502
            )


async def _stub_license(request: "web.Request") -> "web.Response":
    """Stub license validation — always returns valid."""
    return web.json_response({
        "valid": True,
        "plan": "local",
        "features": ["all"],
        "message": "Local mode — license validation bypassed",
    })


async def _stub_usage(request: "web.Request") -> "web.Response":
    """Stub usage reporting — always returns ok."""
    return web.json_response({"status": "ok", "message": "Local mode — usage reporting disabled"})


async def _health(request: "web.Request") -> "web.Response":
    """Health check endpoint."""
    return web.json_response({"status": "healthy", "mode": "local"})


def create_app(upstream_base: str, upstream_key: str = "") -> "web.Application":
    """Create the aiohttp application with all routes configured."""
    if not AIOHTTP_AVAILABLE:
        raise ImportError("aiohttp is required for the local API server. Install: pip install aiohttp")

    app = web.Application()

    # Proxy routes — forward to upstream
    async def proxy_v1(request):
        return await _proxy_request(request, upstream_base, upstream_key)

    async def proxy_llm(request):
        return await _proxy_request(request, upstream_base, upstream_key)

    async def proxy_anthropic(request):
        return await _proxy_request(request, upstream_base, upstream_key)

    async def proxy_coding(request):
        return await _proxy_request(request, upstream_base, upstream_key)

    # Chat completions (main LLM path)
    app.router.add_route("*", "/v1/{path:.*}", proxy_v1)

    # Legacy/alternative LLM routes
    app.router.add_route("*", "/api/llm/{path:.*}", proxy_llm)
    app.router.add_route("*", "/api/anthropic/{path:.*}", proxy_anthropic)
    app.router.add_route("*", "/api/coding/{path:.*}", proxy_coding)

    # Stub endpoints (no upstream needed)
    app.router.add_route("*", "/api/desktop/validate-license", _stub_license)
    app.router.add_route("*", "/api/desktop/worker-usage", _stub_usage)
    app.router.add_route("*", "/api/desktop/kimi-usage", _stub_usage)
    app.router.add_route("*", "/api/desktop/status", _stub_usage)

    # Health check
    app.router.add_get("/health", _health)

    return app


class LocalAPIServer:
    """
    Manages the local API server lifecycle.

    Runs the aiohttp server in a background daemon thread so it doesn't
    block the main agent execution.
    """

    def __init__(
        self,
        upstream_base: str,
        upstream_api_key: str = "",
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
    ):
        self.upstream_base = upstream_base
        self.upstream_api_key = upstream_api_key
        self.host = host
        self.port = _find_free_port(port)
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._runner: Optional["web.AppRunner"] = None
        self.is_running = False

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self) -> None:
        """Start the server in a background daemon thread."""
        if self.is_running:
            logger.info(f"[LocalAPI] Already running at {self.base_url}")
            return

        self._thread = threading.Thread(target=self._run_server, daemon=True)
        self._thread.start()

        # Wait for server to be ready
        for _ in range(50):  # 5 seconds max
            if self.is_running:
                logger.info(f"[LocalAPI] Server started at {self.base_url}")
                return
            time.sleep(0.1)

        logger.warning("[LocalAPI] Server start timed out")

    def _run_server(self) -> None:
        """Internal: run the aiohttp server in a new event loop."""
        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

            app = create_app(self.upstream_base, self.upstream_api_key)
            self._runner = web.AppRunner(app)
            self._loop.run_until_complete(self._runner.setup())

            site = web.TCPSite(self._runner, self.host, self.port)
            self._loop.run_until_complete(site.start())

            self.is_running = True
            self._loop.run_forever()
        except Exception as exc:
            logger.error(f"[LocalAPI] Server failed: {exc}")
        finally:
            self.is_running = False

    def stop(self) -> None:
        """Stop the server gracefully."""
        if not self.is_running:
            return

        if self._loop and self._runner:
            try:
                future = asyncio.run_coroutine_threadsafe(
                    self._runner.cleanup(), self._loop
                )
                future.result(timeout=5)
            except Exception:
                pass

        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)

        self.is_running = False
        logger.info("[LocalAPI] Server stopped")

