"""
Auto-launcher for the local API server.

Conditionally starts the local proxy server when personal API keys are
detected. Integrates into run_ultimate.py, run_simple.py, and run_mcp.py
entry points.

Activation conditions (any of):
  - EVERSALE_LOCAL_SERVER=true
  - OPENAI_API_KEY is set (implies personal key usage)
  - ANTHROPIC_API_KEY is set

When active, sets environment variables so gpu_llm_client.py and other
components route through the local proxy:
  - OPENAI_BASE_URL → http://127.0.0.1:{port}/v1
  - EVERSALE_LICENSE_URL → http://127.0.0.1:{port}/api/desktop/validate-license
  - EVERSALE_DESKTOP_URL → http://127.0.0.1:{port}/api/desktop
"""

import atexit
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

_server_instance = None
_launched = False


def _should_start() -> bool:
    """Check if local server should be auto-started."""
    if os.environ.get("EVERSALE_LOCAL_SERVER", "").lower() in ("true", "1", "yes"):
        return True
    if os.environ.get("OPENAI_API_KEY", "").strip():
        return True
    if os.environ.get("ANTHROPIC_API_KEY", "").strip():
        return True
    return False


def _get_upstream_base() -> str:
    """Resolve the upstream base URL from environment."""
    return (
        os.environ.get("EVERSALE_UPSTREAM_URL", "").strip()
        or os.environ.get("OPENAI_BASE_URL", "").strip()
        or os.environ.get("ANTHROPIC_BASE_URL", "").strip()
        or "https://api.openai.com/v1"
    )


def _get_upstream_api_key() -> str:
    """Resolve the upstream API key from environment."""
    return (
        os.environ.get("OPENAI_API_KEY", "").strip()
        or os.environ.get("ANTHROPIC_API_KEY", "").strip()
        or ""
    )


def _wait_for_server(base_url: str, timeout: float = 5.0) -> bool:
    """Poll until the server responds to /health."""
    import urllib.request
    import urllib.error

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            req = urllib.request.Request(f"{base_url}/health", method="GET")
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, OSError, Exception):
            pass
        time.sleep(0.2)
    return False


def ensure_local_server() -> Optional[str]:
    """
    Start the local API server if conditions are met.

    Returns the server base_url if started, or None if not needed/available.
    This function is idempotent — calling it multiple times is safe.
    """
    global _server_instance, _launched

    if _launched:
        return _server_instance.base_url if _server_instance else None

    _launched = True

    if not _should_start():
        logger.debug("[Launcher] Local server not needed (no personal API key detected)")
        return None

    try:
        from local_api_server import LocalAPIServer, AIOHTTP_AVAILABLE
    except ImportError:
        try:
            from eversale.engine.local_api_server import LocalAPIServer, AIOHTTP_AVAILABLE
        except ImportError:
            logger.warning("[Launcher] local_api_server module not found")
            return None

    if not AIOHTTP_AVAILABLE:
        logger.warning("[Launcher] aiohttp not available; install with: pip install aiohttp")
        return None

    upstream_base = _get_upstream_base()
    upstream_key = _get_upstream_api_key()

    logger.info(f"[Launcher] Starting local API server (upstream: {upstream_base})")

    _server_instance = LocalAPIServer(
        upstream_base=upstream_base,
        upstream_api_key=upstream_key,
    )
    _server_instance.start()

    if _wait_for_server(_server_instance.base_url):
        base = _server_instance.base_url
        logger.info(f"[Launcher] Local server ready at {base}")

        # Wire environment so gpu_llm_client.py and others route through local proxy
        os.environ["EVERSALE_LICENSE_URL"] = f"{base}/api/desktop/validate-license"
        os.environ["EVERSALE_DESKTOP_URL"] = f"{base}/api/desktop"

        # Register cleanup
        atexit.register(_server_instance.stop)

        return base
    else:
        logger.warning("[Launcher] Local server failed to start within timeout")
        _server_instance = None
        return None

