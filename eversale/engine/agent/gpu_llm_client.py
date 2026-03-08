"""
GPU LLM Client - Routes inference to a remote GPU endpoint.

Supports:
- Eversale proxy (OpenAI-compatible): `https://eversale.io/api/llm`
- Direct OpenAI-compatible endpoints: `<base_url>/v1/chat/completions`
- Ollama-compatible endpoints: `<base_url>/api/chat` (e.g. `http://localhost:11434`)
- RunPod Serverless endpoints: `https://api.runpod.ai/v2/<endpoint_id>` (uses `/runsync`)

Configuration:
- GPU_LLM_URL: Inference endpoint base URL (default: https://eversale.io/api/llm)
- RUNPOD_API_KEY: RunPod API key (required for `api.runpod.ai/v2/...`)
- EVERSALE_LLM_TOKEN / GPU_LLM_TOKEN: Bearer token for non-eversale OpenAI-compatible endpoints
- MOONSHOT_API_KEY: Kimi API key for high-quality tasks (fallback/escalation)
"""

import os
import asyncio
import aiohttp
import time
from urllib.parse import urlparse
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from loguru import logger

# GPU Server Configuration — prioritize OPENAI_BASE_URL for personal API key usage
GPU_LLM_URL = os.environ.get(
    'OPENAI_BASE_URL',
    os.environ.get(
    'ANTHROPIC_BASE_URL',
    os.environ.get(
    'GPU_LLM_URL',
    os.environ.get('SUPPORT_AGENT_LLM_CHAIN_REMOTE_ORIGIN', 'https://api.z.ai/api/anthropic')))
)
GPU_LLM_TIMEOUT = int(os.environ.get('GPU_LLM_TIMEOUT_MS', '60000')) / 1000  # Convert to seconds

# Retry Configuration
MAX_RETRIES = 5
INITIAL_BACKOFF_SECONDS = 1.0

# Available models on GPU server - 0000/ui-tars-1.5-7b:latest is best for tool calling
GPU_MODELS = {
    'fast': 'glm-5',               # Fast and excellent at tool calling
    'default': 'glm-5',            # Best for tool calling (balanced)
    'quality': 'glm-5',            # High quality tool calling
    'vision': 'glm-5',     # Vision tasks
}


@dataclass
class LLMResponse:
    """Standardized LLM response."""
    content: str
    model: str
    tokens_used: int = 0
    latency_ms: int = 0
    source: str = 'gpu'  # 'gpu', 'kimi', or 'local'


class GPULLMClient:
    """
    Client for GPU LLM server on RunPod.

    Uses OpenAI-compatible API for compatibility with the eversale proxy.
    Automatically handles license-based auth through the proxy.
    """

    def __init__(self, base_url: str = None, license_key: str = None):
        """
        Initialize GPU LLM client.

        Args:
            base_url: GPU server URL (default: from env)
            license_key: License key for auth (required for proxy)
        """
        self.base_url = (base_url or GPU_LLM_URL).rstrip('/')
        self.license_key = license_key or self._get_license_key()
        self.api_token = (
            os.environ.get('OPENAI_API_KEY', '').strip()
            or os.environ.get('ANTHROPIC_API_KEY', '').strip()
            or os.environ.get('RUNPOD_API_KEY', '').strip()
            or os.environ.get('EVERSALE_LLM_TOKEN', '').strip()
            or os.environ.get('GPU_LLM_TOKEN', '').strip()
        )
        self._session: Optional[aiohttp.ClientSession] = None

        # Performance tracking
        self.total_calls = 0
        self.total_tokens = 0
        self.total_latency_ms = 0

        logger.info(f"[GPU LLM] Initialized with endpoint: {self.base_url}")
        if self.license_key:
            logger.info(f"[GPU LLM] License key loaded: {self.license_key[:8]}...")
        if self.api_token and not self.license_key:
            logger.info("[GPU LLM] API token loaded from env")
        if not self.license_key and not self.api_token:
            logger.warning("[GPU LLM] No auth token found - API calls may fail")

    def _is_runpod_serverless(self) -> bool:
        """True if base_url looks like a RunPod Serverless endpoint root."""
        return 'api.runpod.ai' in self.base_url and '/v2/' in self.base_url

    def _is_eversale_proxy(self) -> bool:
        return 'eversale.io' in self.base_url or 'z.ai' in self.base_url

    def _looks_like_ollama(self) -> bool:
        """
        Heuristic for Ollama-compatible endpoints.
        Common cases:
        - http://localhost:11434
        - http://127.0.0.1:11434
        - http://<host>:11434
        """
        try:
            parsed = urlparse(self.base_url if '://' in self.base_url else f"http://{self.base_url}")
            return parsed.port == 11434
        except Exception:
            return False

    def _get_auth_header_value(self) -> Optional[str]:
        """
        Choose the correct bearer token for the active endpoint:
        - eversale proxy: license key
        - runpod serverless: RUNPOD_API_KEY (or EVERSALE_LLM_TOKEN/GPU_LLM_TOKEN if set)
        - other: EVERSALE_LLM_TOKEN/GPU_LLM_TOKEN (or license key if provided)
        """
        # When OPENAI_API_KEY is set, always prefer api_token over license_key
        if os.environ.get('OPENAI_API_KEY'):
            token = self.api_token
        elif self._is_eversale_proxy():
            token = self.license_key
        elif self._is_runpod_serverless():
            token = os.environ.get('RUNPOD_API_KEY', '').strip() or self.api_token
        else:
            token = self.api_token or self.license_key

        token = (token or '').strip()
        return f"Bearer {token}" if token else None

    def _normalize_base_url(self) -> str:
        """Normalize and strip trailing slashes."""
        return (self.base_url or '').rstrip('/')

    def _build_chat_endpoint(self, base_url: str) -> str:
        """Build chat completions endpoint with auto-detection for versioned URLs.
        If the base URL already ends with a version path like /v4, /v1, etc.,
        append /chat/completions directly instead of adding /v1/chat/completions."""
        import re
        if re.search(r'/v\d+/?$', base_url):
            return f'{base_url}/chat/completions'
        return f'{base_url}/v1/chat/completions'

    def _get_license_key(self) -> str:
        """Get license key from env var or config file."""
        # Check environment first
        key = os.environ.get('EVERSALE_LICENSE_KEY', '')
        if key:
            return key.strip()

        # Check config file (same as license_validator.py)
        from pathlib import Path
        config_path = Path.home() / ".eversale" / "license.key"
        if config_path.exists():
            try:
                return config_path.read_text().strip()
            except Exception:
                pass

        return ''

    def is_available(self) -> bool:
        """Check if GPU LLM is available (always true if we have a URL)."""
        return bool(self.base_url)

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=GPU_LLM_TIMEOUT)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def _do_request(self, session: aiohttp.ClientSession, endpoint: str, payload: Dict, headers: Dict) -> Dict:
        """Helper to perform HTTP request with retry logic. Returns parsed JSON."""
        last_exception = None
        for attempt in range(MAX_RETRIES):
            backoff_delay = INITIAL_BACKOFF_SECONDS * (2 ** attempt) + (0.1 * (attempt % 2)) # Exponential with jitter

            try:
                async with session.post(endpoint, json=payload, headers=headers) as resp:
                    if resp.status == 200:
                        # Read JSON inside context manager before it closes
                        data = await resp.json()
                        return data
                    elif resp.status in [502, 503, 504]:
                        logger.warning(f"[GPU LLM] Transient error {resp.status} on attempt {attempt+1}/{MAX_RETRIES}. Retrying in {backoff_delay:.2f}s.")
                        error_text = await resp.text()
                        last_exception = Exception(f"GPU LLM transient error: {resp.status} - {error_text[:100]}")
                    else:
                        error_text = await resp.text()
                        logger.error(f"[GPU LLM] Non-retryable error {resp.status}: {error_text[:200]}")
                        raise Exception(f"GPU LLM error: {resp.status} - {error_text[:100]}")
            except aiohttp.ClientError as e:
                logger.warning(f"[GPU LLM] Network error on attempt {attempt+1}/{MAX_RETRIES}: {e}. Retrying in {backoff_delay:.2f}s.")
                last_exception = e
            except asyncio.TimeoutError:
                logger.warning(f"[GPU LLM] Request timeout on attempt {attempt+1}/{MAX_RETRIES}. Retrying in {backoff_delay:.2f}s.")
                last_exception = Exception(f"GPU LLM timeout after {GPU_LLM_TIMEOUT}s")
            except Exception as e:
                # Catch any other unexpected exceptions and retry if appropriate
                logger.error(f"[GPU LLM] Unexpected error on attempt {attempt+1}/{MAX_RETRIES}: {e}. Retrying in {backoff_delay:.2f}s.")
                last_exception = e

            await asyncio.sleep(backoff_delay)

        logger.error(f"[GPU LLM] Max retries ({MAX_RETRIES}) exceeded. Last error: {last_exception}")
        raise last_exception if last_exception else Exception("GPU LLM failed after multiple retries with no specific error captured.")


    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: str = None,
        temperature: float = 0.1,
        max_tokens: int = 2000,
        stream: bool = False
    ) -> LLMResponse:
        """
        Send chat completion request to GPU server.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model name (default: qwen2.5:7b-instruct)
            temperature: Sampling temperature
            max_tokens: Max tokens to generate
            stream: Whether to stream response (not implemented yet)

        Returns:
            LLMResponse with content and metadata
        """
        if not model:
            model = GPU_MODELS['default']

        start_time = time.time()

        session = await self._get_session()

        # Build headers
        headers = {
            'Content-Type': 'application/json',
        }

        auth_header = self._get_auth_header_value()
        if auth_header:
            headers['Authorization'] = auth_header

        base_url = self._normalize_base_url()

        # Determine endpoint + payload based on URL
        if self._is_runpod_serverless():
            # RunPod Serverless: POST https://api.runpod.ai/v2/<endpoint_id>/runsync
            endpoint = base_url if base_url.endswith('/runsync') else f'{base_url}/runsync'
            payload = {
                'input': {
                    'model': model,
                    'messages': messages,
                    'temperature': temperature,
                    'max_tokens': max_tokens,
                    'stream': False,
                }
            }
        elif self._is_eversale_proxy():
            # Eversale proxy is OpenAI-compatible
            endpoint = self._build_chat_endpoint(base_url)
            payload = {
                'model': model,
                'messages': messages,
                'temperature': temperature,
                'max_tokens': max_tokens,
                'stream': stream,
            }
        elif 'runpod.net' in base_url or self._looks_like_ollama():
            # Direct RunPod pod proxy or local Ollama: Ollama /api/chat
            endpoint = f'{base_url}/api/chat'
            payload = {
                'model': model,
                'messages': messages,
                'options': {
                    'temperature': temperature,
                    'num_predict': max_tokens,
                },
                'stream': False,
            }
        else:
            # Default to OpenAI-compatible
            endpoint = self._build_chat_endpoint(base_url)
            payload = {
                'model': model,
                'messages': messages,
                'temperature': temperature,
                'max_tokens': max_tokens,
                'stream': stream,
            }

        logger.debug(f"[GPU LLM] Request to {endpoint} with model {model}")

        data = await self._do_request(session, endpoint, payload, headers)

        latency_ms = int((time.time() - start_time) * 1000)

        # Parse response based on format
        if self._is_runpod_serverless():
            # RunPod serverless typically returns { status, output, ... } for runsync
            output = data.get('output') if isinstance(data, dict) else None
            if isinstance(output, dict):
                data = output
            elif isinstance(output, str):
                content = output
                tokens = 0
                data = None
            else:
                # Fall back to using the full response as string
                content = str(data)
                tokens = 0
                data = None

        if data is not None:
            if 'choices' in data:
                # OpenAI format
                content = data['choices'][0]['message'].get('content', '')
                tokens = data.get('usage', {}).get('total_tokens', 0)
            elif 'message' in data:
                # Ollama format
                content = data['message'].get('content', '')
                tokens = data.get('eval_count', 0) + data.get('prompt_eval_count', 0)
            else:
                content = str(data)
                tokens = 0

        # Track stats
        self.total_calls += 1
        self.total_tokens += tokens
        self.total_latency_ms += latency_ms

        logger.info(f"[GPU LLM] Response: {len(content)} chars, {tokens} tokens, {latency_ms}ms")

        return LLMResponse(
            content=content,
            model=model,
            tokens_used=tokens,
            latency_ms=latency_ms,
            source='gpu'
        )

    def _do_request_sync(self, client: Any, endpoint: str, payload: Dict, headers: Dict) -> Any:
        """Helper to perform synchronous HTTP request with retry logic."""
        import httpx
        last_exception = None
        for attempt in range(MAX_RETRIES):
            backoff_delay = INITIAL_BACKOFF_SECONDS * (2 ** attempt) + (0.1 * (attempt % 2)) # Exponential with jitter
            
            try:
                resp = client.post(endpoint, json=payload, headers=headers)
                if resp.status_code == 200:
                    return resp
                elif resp.status_code in [502, 503, 504]:
                    logger.warning(f"[GPU LLM Sync] Transient error {resp.status_code} on attempt {attempt+1}/{MAX_RETRIES}. Retrying in {backoff_delay:.2f}s.")
                    error_text = resp.text
                    last_exception = Exception(f"GPU LLM transient error: {resp.status_code} - {error_text[:100]}")
                else:
                    error_text = resp.text
                    logger.error(f"[GPU LLM Sync] Non-retryable error {resp.status_code}: {error_text[:200]}")
                    resp.raise_for_status() # Re-raise for non-transient errors
            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                logger.warning(f"[GPU LLM Sync] Network/HTTP error on attempt {attempt+1}/{MAX_RETRIES}: {e}. Retrying in {backoff_delay:.2f}s.")
                last_exception = e
            except Exception as e:
                logger.error(f"[GPU LLM Sync] Unexpected error on attempt {attempt+1}/{MAX_RETRIES}: {e}. Retrying in {backoff_delay:.2f}s.")
                last_exception = e
            
            time.sleep(backoff_delay)
        
        logger.error(f"[GPU LLM Sync] Max retries ({MAX_RETRIES}) exceeded. Last error: {last_exception}")
        raise last_exception if last_exception else Exception("GPU LLM Sync failed after multiple retries with no specific error captured.")

    def chat_sync(
        self,
        messages: List[Dict[str, str]],
        model: str = None,
        temperature: float = 0.1,
        max_tokens: int = 2000
    ) -> LLMResponse:
        """
        Synchronous version of chat() for non-async contexts.
        Uses httpx sync client to avoid event loop issues.
        """
        import httpx

        if not model:
            model = GPU_MODELS['default']

        start_time = time.time()

        # Build headers
        headers = {'Content-Type': 'application/json'}
        auth_header = self._get_auth_header_value()
        if auth_header:
            headers['Authorization'] = auth_header

        base_url = self._normalize_base_url()

        # Determine endpoint + payload
        if self._is_runpod_serverless():
            endpoint = base_url if base_url.endswith('/runsync') else f'{base_url}/runsync'
            payload = {
                'input': {
                    'model': model,
                    'messages': messages,
                    'temperature': temperature,
                    'max_tokens': max_tokens,
                    'stream': False,
                }
            }
        elif self._is_eversale_proxy():
            endpoint = self._build_chat_endpoint(base_url)
            payload = {
                'model': model,
                'messages': messages,
                'temperature': temperature,
                'max_tokens': max_tokens,
                'stream': False,
            }
        elif 'runpod.net' in base_url or self._looks_like_ollama():
            endpoint = f'{base_url}/api/chat'
            payload = {
                'model': model,
                'messages': messages,
                'options': {'temperature': temperature, 'num_predict': max_tokens},
                'stream': False,
            }
        else:
            endpoint = self._build_chat_endpoint(base_url)
            payload = {
                'model': model,
                'messages': messages,
                'temperature': temperature,
                'max_tokens': max_tokens,
                'stream': False,
            }

        # Use sync httpx client
        with httpx.Client(timeout=GPU_LLM_TIMEOUT) as client:
            resp = self._do_request_sync(client, endpoint, payload, headers)
            data = resp.json()

        latency_ms = int((time.time() - start_time) * 1000)

        # Parse response
        if self._is_runpod_serverless():
            output = data.get('output') if isinstance(data, dict) else None
            if isinstance(output, dict):
                data = output
            elif isinstance(output, str):
                content = output
                tokens = 0
                data = None
            else:
                content = str(data)
                tokens = 0
                data = None

        if data is not None:
            if 'choices' in data:
                content = data['choices'][0]['message'].get('content', '')
                tokens = data.get('usage', {}).get('total_tokens', 0)
            elif 'message' in data:
                content = data['message'].get('content', '')
                tokens = data.get('eval_count', 0) + data.get('prompt_eval_count', 0)
            else:
                content = str(data)
                tokens = 0

        self.total_calls += 1
        self.total_tokens += tokens
        self.total_latency_ms += latency_ms

        logger.info(f"[GPU LLM Sync] Response: {len(content)} chars, {tokens} tokens, {latency_ms}ms")

        return LLMResponse(
            content=content,
            model=model,
            tokens_used=tokens,
            latency_ms=latency_ms,
            source='gpu'
        )

    async def close(self):
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()

    def get_stats(self) -> Dict[str, Any]:
        """Get performance statistics."""
        avg_latency = self.total_latency_ms / max(1, self.total_calls)
        return {
            'total_calls': self.total_calls,
            'total_tokens': self.total_tokens,
            'avg_latency_ms': round(avg_latency, 1),
            'endpoint': self.base_url,
        }


# Singleton instance
_gpu_client: Optional[GPULLMClient] = None


def get_gpu_client(base_url: str = None, license_key: str = None) -> GPULLMClient:
    """Get or create singleton GPU LLM client."""
    global _gpu_client
    if _gpu_client is None:
        _gpu_client = GPULLMClient(base_url=base_url, license_key=license_key)
    elif license_key and not _gpu_client.license_key:
        _gpu_client.license_key = license_key
    if base_url:
        normalized = base_url.rstrip('/')
        if normalized and normalized != _gpu_client.base_url:
            _gpu_client.base_url = normalized
    return _gpu_client


class OllamaCompatibleClient:
    """
    Wrapper that provides Ollama-compatible API using GPU LLM.

    This allows existing code that uses ollama.Client to work with GPU server.
    """

    def __init__(self, host: str = None, license_key: str = None):
        """
        Initialize with GPU client backend.

        Args:
            host: Ignored (uses GPU_LLM_URL from env)
            license_key: License key for auth
        """
        # In normal Ollama usage, `host` is the server URL. Respect it here so
        # config-driven `llm.base_url` works (and so local Ollama keeps working).
        self._gpu_client = get_gpu_client(base_url=host, license_key=license_key)

    def chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        options: Dict[str, Any] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Ollama-compatible chat interface.

        Returns dict in Ollama format for compatibility.
        """
        options = options or {}
        temperature = options.get('temperature', 0.1)
        max_tokens = options.get('num_predict', 2000)

        try:
            response = self._gpu_client.chat_sync(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens
            )

            # Return in Ollama format
            return {
                'message': {
                    'role': 'assistant',
                    'content': response.content,
                },
                'model': response.model,
                'done': True,
                'eval_count': response.tokens_used,
            }
        except Exception as e:
            logger.error(f"[Ollama Compat] Error: {e}")
            # Return error in Ollama format
            return {
                'message': {
                    'role': 'assistant',
                    'content': f'Error: {str(e)}',
                },
                'model': model,
                'done': True,
                'error': str(e),
            }

    def list(self) -> Dict[str, Any]:
        """List available models (returns GPU models)."""
        return {
            'models': [
                {'name': name, 'details': {'family': 'gpu'}}
                for name in GPU_MODELS.values()
            ]
        }

    def show(self, model: str) -> Dict[str, Any]:
        """Show model info."""
        return {
            'modelfile': f'GPU model: {model}',
            'parameters': 'Running on RunPod GPU server',
        }

    def generate(
        self,
        model: str,
        prompt: str,
        options: Dict[str, Any] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Ollama-compatible generate interface (single prompt, not chat).

        Returns dict in Ollama format for compatibility.
        """
        options = options or {}
        temperature = options.get('temperature', 0.1)
        max_tokens = options.get('num_predict', 2000)

        # Convert prompt to messages format
        messages = [{'role': 'user', 'content': prompt}]

        try:
            response = self._gpu_client.chat_sync(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens
            )

            # Return in Ollama generate format
            return {
                'response': response.content,
                'model': response.model,
                'done': True,
                'eval_count': response.tokens_used,
            }
        except Exception as e:
            logger.error(f"[Ollama Compat] Generate error: {e}")
            return {
                'response': f'Error: {str(e)}',
                'model': model,
                'done': True,
                'error': str(e),
            }
