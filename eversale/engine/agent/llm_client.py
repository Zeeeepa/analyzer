"""
LLM Client - Unified interface for local Ollama, remote GPU server, and Kimi API.

Model Strategy (3 models only):
1. 0000/ui-tars-1.5-7b:latest (6GB) - Primary agent + function calling (local/remote GPU)
2. UI-TARS - Vision tasks only (remote GPU)
3. Kimi API - Complex reasoning tasks (external API)

Configuration via environment variables:
- EVERSALE_LLM_MODE: "local" or "remote" (default: remote)
- EVERSALE_LLM_URL: GPU server URL
- EVERSALE_LLM_TOKEN: API key for remote server
- KIMI_API_KEY: Kimi/Moonshot API key for complex tasks
"""

import os
import json
import asyncio
import hashlib
import time
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import httpx
from loguru import logger

# Try to import ollama for local mode
try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    ollama = None
    logger.warning("ollama library not available - local mode disabled")


@dataclass
class LLMResponse:
    """Unified response from LLM."""
    content: str
    model: str
    done: bool = True
    error: Optional[str] = None


class LLMCache:
    """
    Persistent LLM response cache with TTL.
    Saves cache to disk for persistence across sessions.
    Reduces API costs by caching repeated identical requests.
    """
    def __init__(self, ttl_seconds: int = 3600, max_size: int = 500, cache_dir: str = None):
        self.ttl_seconds = ttl_seconds  # Default 1 hour for persistent cache
        self.max_size = max_size
        self._cache: Dict[str, tuple[LLMResponse, float]] = {}
        self._access_order: List[str] = []

        # Persistent cache file
        from pathlib import Path
        if cache_dir:
            self._cache_dir = Path(cache_dir)
        else:
            self._cache_dir = Path.home() / ".eversale" / "cache"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_file = self._cache_dir / "llm_cache.json"

        # Load existing cache from disk
        self._load_cache()

    def _load_cache(self):
        """Load cache from disk on startup."""
        try:
            if self._cache_file.exists():
                with open(self._cache_file, 'r') as f:
                    data = json.load(f)

                now = time.time()
                loaded = 0
                for key, entry in data.items():
                    # Validate entry format
                    if not isinstance(entry, dict):
                        continue
                    timestamp = entry.get('timestamp', 0)
                    # Skip expired entries
                    if now - timestamp > self.ttl_seconds:
                        continue
                    # Reconstruct LLMResponse
                    response = LLMResponse(
                        content=entry.get('content', ''),
                        model=entry.get('model', 'unknown'),
                        done=entry.get('done', True),
                        error=entry.get('error')
                    )
                    self._cache[key] = (response, timestamp)
                    self._access_order.append(key)
                    loaded += 1
                    if loaded >= self.max_size:
                        break

                logger.debug(f"Loaded {loaded} cached LLM responses from disk")
        except Exception as e:
            logger.debug(f"Failed to load LLM cache from disk: {e}")

    def _save_cache(self):
        """Save cache to disk (debounced - only save periodically)."""
        try:
            # Only save top N most recent entries to keep file small
            data = {}
            for key in self._access_order[-self.max_size:]:
                if key in self._cache:
                    response, timestamp = self._cache[key]
                    data[key] = {
                        'content': response.content,
                        'model': response.model,
                        'done': response.done,
                        'error': response.error,
                        'timestamp': timestamp
                    }
            with open(self._cache_file, 'w') as f:
                json.dump(data, f)
        except Exception as e:
            logger.debug(f"Failed to save LLM cache to disk: {e}")

    def _make_key(self, prompt: str, model: str, temperature: float, images: Optional[List[str]] = None) -> str:
        """Generate cache key from request parameters"""
        key_parts = [prompt, model, str(temperature)]
        if images:
            # Hash images instead of storing full base64
            img_hash = hashlib.md5(''.join(images).encode()).hexdigest()
            key_parts.append(img_hash)
        return hashlib.md5('|'.join(key_parts).encode()).hexdigest()

    def get(self, prompt: str, model: str, temperature: float, images: Optional[List[str]] = None) -> Optional[LLMResponse]:
        """Get cached response if available and not expired"""
        key = self._make_key(prompt, model, temperature, images)
        if key not in self._cache:
            return None

        response, timestamp = self._cache[key]
        if time.time() - timestamp > self.ttl_seconds:
            # Expired
            del self._cache[key]
            if key in self._access_order:
                self._access_order.remove(key)
            return None

        # Update access order for LRU
        if key in self._access_order:
            self._access_order.remove(key)
        self._access_order.append(key)

        return response

    def set(self, prompt: str, model: str, temperature: float, response: LLMResponse, images: Optional[List[str]] = None):
        """Cache response with TTL and persist to disk"""
        key = self._make_key(prompt, model, temperature, images)

        # Evict oldest if at capacity
        if len(self._cache) >= self.max_size and key not in self._cache:
            oldest = self._access_order.pop(0)
            if oldest in self._cache:
                del self._cache[oldest]

        self._cache[key] = (response, time.time())

        if key in self._access_order:
            self._access_order.remove(key)
        self._access_order.append(key)

        # Persist to disk every 10 cache writes
        if len(self._cache) % 10 == 0:
            self._save_cache()

    def clear(self):
        """Clear all cached responses"""
        self._cache.clear()
        self._access_order.clear()
        # Remove cache file
        try:
            if self._cache_file.exists():
                self._cache_file.unlink()
        except Exception:
            pass

    def save(self):
        """Force save cache to disk."""
        self._save_cache()

    def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            "entries": len(self._cache),
            "max_size": self.max_size,
            "ttl_seconds": self.ttl_seconds,
            "cache_file": str(self._cache_file)
        }


class LLMClient:
    """
    Unified LLM client supporting both local Ollama and remote GPU server.
    """

    def __init__(self, config: Optional[Dict] = None):
        config = config or {}
        llm_config = config.get('llm', {})

        # CLI USERS: ALWAYS use remote mode (licensed API via eversale.io)
        # Local mode only allowed if .eversale-local marker exists (for development)
        local_marker = Path(__file__).parent.parent / ".eversale-local"
        is_dev_mode = local_marker.exists()

        if is_dev_mode:
            # Development mode - allow local override
            self.mode = os.getenv('EVERSALE_LLM_MODE', llm_config.get('mode', 'local'))
        else:
            # CLI mode - ALWAYS remote, ignore env vars
            self.mode = 'remote'

        # URL based on mode
        if self.mode == 'local':
            default_url = llm_config.get('local_url', 'http://localhost:11434')
        else:
            # Remote mode - use eversale.io proxy (validates license, forwards to GPU)
            default_url = llm_config.get('remote_url', 'https://eversale.io/api/llm')

        self.base_url = os.getenv('EVERSALE_LLM_URL', llm_config.get('base_url', default_url))

        # API token for remote (license key) - check env var first, then file
        self.api_token = os.getenv('EVERSALE_LLM_TOKEN', '') or os.getenv('EVERSALE_LICENSE_KEY', '')
        if not self.api_token:
            # Try reading from license file
            license_path = Path.home() / ".eversale" / "license.key"
            if license_path.exists():
                try:
                    self.api_token = license_path.read_text().strip()
                except Exception:
                    pass

        # =============================================================
        # MODEL CONFIGURATION (3 models only)
        # =============================================================
        # 1. 0000/ui-tars-1.5-7b:latest - Primary model for all tasks + function calling
        self.main_model = os.getenv('EVERSALE_LLM_MODEL', llm_config.get('main_model', '0000/ui-tars-1.5-7b:latest'))
        self.fast_model = self.main_model  # Same as main
        self.tool_calling_model = self.main_model  # qwen3 has native function calling

        # 2. UI-TARS - Vision only
        self.vision_model = llm_config.get('vision_model', '0000/ui-tars-1.5-7b:latest')
        self.web_vision_model = self.vision_model  # Same for all vision

        # 3. Kimi API - Complex reasoning (external)
        self.kimi_api_key = os.getenv('KIMI_API_KEY', '')
        self.kimi_api_url = llm_config.get('kimi_api_url', 'https://api.moonshot.ai/v1')
        self.complex_model = 'moonshot-v1-8k'  # Kimi model name

        # Settings
        self.temperature = llm_config.get('temperature', 0.1)
        self.max_tokens = llm_config.get('max_tokens', 4096)

        # Dynamic timeout based on mode - like a human would wait longer for remote
        default_timeout = 30 if self.mode == 'local' else 120  # 30s local, 120s remote
        self.timeout = llm_config.get('timeout_seconds', default_timeout)

        # HTTP client for remote mode
        self._http_client: Optional[httpx.AsyncClient] = None

        # Persistent cache for LLM responses (TTL=1hr, max 500 entries)
        # Persists to ~/.eversale/cache/llm_cache.json for cost savings
        cache_ttl = llm_config.get('cache_ttl_seconds', 3600)  # 1 hour default
        cache_size = llm_config.get('cache_max_size', 500)
        self._cache = LLMCache(ttl_seconds=cache_ttl, max_size=cache_size)

        logger.info(f"LLM Client initialized: mode={self.mode}, url={self.base_url}")
        logger.info(f"  Models: main={self.main_model}, tool_calling={self.tool_calling_model}, vision={self.vision_model}")

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client for remote mode."""
        if self._http_client is None:
            headers = {
                'Content-Type': 'application/json',
            }
            if self.api_token:
                headers['Authorization'] = f'Bearer {self.api_token}'

            self._http_client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=httpx.Timeout(self.timeout, connect=10.0),
            )
        return self._http_client

    async def close(self):
        """Close HTTP client and save cache."""
        # Save cache to disk before closing
        self._cache.save()
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    def clear_cache(self):
        """Clear the LLM response cache."""
        self._cache.clear()
        logger.debug("LLM cache cleared")

    def cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return self._cache.stats()

    def generate_sync(
        self,
        prompt: str,
        model: Optional[str] = None,
        images: Optional[List[str]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """
        Synchronous generation - for compatibility with existing code.
        """
        return asyncio.get_event_loop().run_until_complete(
            self.generate(prompt, model, images, temperature, max_tokens)
        )

    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        images: Optional[List[str]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """
        Generate a response from the LLM.

        Args:
            prompt: The prompt to send
            model: Override model name
            images: List of base64-encoded images (for vision)
            temperature: Override temperature
            max_tokens: Override max tokens

        Returns:
            LLMResponse with generated content
        """
        model = model or self.main_model
        temperature = temperature if temperature is not None else self.temperature
        max_tokens = max_tokens or self.max_tokens

        # Check cache first (only for deterministic requests with temp=0)
        if temperature == 0:
            cached = self._cache.get(prompt, model, temperature, images)
            if cached:
                logger.debug(f"Cache hit for LLM request (model={model})")
                return cached

        # Generate response
        if self.mode == 'local':
            response = await self._generate_local(prompt, model, images, temperature, max_tokens)
        else:
            response = await self._generate_remote(prompt, model, images, temperature, max_tokens)

        # Cache successful deterministic responses
        if temperature == 0 and response.done and not response.error:
            self._cache.set(prompt, model, temperature, response, images)

        return response

    async def _generate_local(
        self,
        prompt: str,
        model: str,
        images: Optional[List[str]],
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        """Generate using local Ollama."""
        if not OLLAMA_AVAILABLE:
            return LLMResponse(
                content="",
                model=model,
                done=True,
                error="Ollama library not available"
            )

        try:
            # Run in thread to avoid blocking
            def _call():
                kwargs = {
                    'model': model,
                    'prompt': prompt,
                    'options': {
                        'temperature': temperature,
                        'num_predict': max_tokens,
                    }
                }
                if images:
                    kwargs['images'] = images
                return ollama.generate(**kwargs)

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, _call)

            return LLMResponse(
                content=response.get('response', ''),
                model=model,
                done=response.get('done', True),
            )
        except Exception as e:
            logger.error(f"Local LLM error: {e}")
            return LLMResponse(
                content="",
                model=model,
                done=True,
                error=str(e)
            )

    async def _generate_remote(
        self,
        prompt: str,
        model: str,
        images: Optional[List[str]],
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        """Generate using remote GPU server (OpenAI-compatible API)."""
        try:
            client = await self._get_http_client()

            # Build messages
            messages = [{'role': 'user', 'content': prompt}]

            # If images provided, use multimodal format
            if images:
                content = [{'type': 'text', 'text': prompt}]
                for img in images:
                    content.append({
                        'type': 'image_url',
                        'image_url': {'url': f'data:image/png;base64,{img}'}
                    })
                messages = [{'role': 'user', 'content': content}]

            payload = {
                'model': model,
                'messages': messages,
                'temperature': temperature,
                'max_tokens': max_tokens,
                'stream': False,
            }

            response = await client.post('/v1/chat/completions', json=payload)
            response.raise_for_status()

            data = response.json()
            message = data.get('choices', [{}])[0].get('message', {})
            # qwen3 returns 'reasoning' field when in thinking mode, fallback to it if 'content' is empty
            content = message.get('content', '') or message.get('reasoning', '')

            return LLMResponse(
                content=content,
                model=model,
                done=True,
            )
        except httpx.HTTPStatusError as e:
            logger.error(f"Remote LLM HTTP error: {e.response.status_code} - {e.response.text}")
            return LLMResponse(
                content="",
                model=model,
                done=True,
                error=f"HTTP {e.response.status_code}: {e.response.text}"
            )
        except Exception as e:
            logger.error(f"Remote LLM error: {e}")
            return LLMResponse(
                content="",
                model=model,
                done=True,
                error=str(e)
            )

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """
        Chat-style generation with message history.

        Args:
            messages: List of {'role': 'user'|'assistant', 'content': '...'}
            model: Override model name
            temperature: Override temperature
            max_tokens: Override max tokens

        Returns:
            LLMResponse with generated content
        """
        model = model or self.main_model
        temperature = temperature if temperature is not None else self.temperature
        max_tokens = max_tokens or self.max_tokens

        if self.mode == 'local':
            return await self._chat_local(messages, model, temperature, max_tokens)
        else:
            return await self._chat_remote(messages, model, temperature, max_tokens)

    async def _chat_local(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        """Chat using local Ollama."""
        if not OLLAMA_AVAILABLE:
            return LLMResponse(
                content="",
                model=model,
                done=True,
                error="Ollama library not available"
            )

        try:
            def _call():
                return ollama.chat(
                    model=model,
                    messages=messages,
                    options={
                        'temperature': temperature,
                        'num_predict': max_tokens,
                    }
                )

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, _call)

            return LLMResponse(
                content=response.get('message', {}).get('content', ''),
                model=model,
                done=True,
            )
        except Exception as e:
            logger.error(f"Local LLM chat error: {e}")
            return LLMResponse(
                content="",
                model=model,
                done=True,
                error=str(e)
            )

    async def _chat_remote(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        """Chat using remote GPU server."""
        try:
            client = await self._get_http_client()

            payload = {
                'model': model,
                'messages': messages,
                'temperature': temperature,
                'max_tokens': max_tokens,
                'stream': False,
            }

            response = await client.post('/v1/chat/completions', json=payload)
            response.raise_for_status()

            data = response.json()
            message = data.get('choices', [{}])[0].get('message', {})
            # qwen3 returns 'reasoning' field when in thinking mode, fallback to it if 'content' is empty
            content = message.get('content', '') or message.get('reasoning', '')

            return LLMResponse(
                content=content,
                model=model,
                done=True,
            )
        except httpx.HTTPStatusError as e:
            logger.error(f"Remote LLM chat HTTP error: {e.response.status_code}")
            return LLMResponse(
                content="",
                model=model,
                done=True,
                error=f"HTTP {e.response.status_code}"
            )
        except Exception as e:
            logger.error(f"Remote LLM chat error: {e}")
            return LLMResponse(
                content="",
                model=model,
                done=True,
                error=str(e)
            )

    async def generate_complex(
        self,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """
        Generate response using Kimi API for complex reasoning tasks.

        Use this for tasks that require:
        - Complex multi-step reasoning
        - Long context understanding
        - Tasks where 0000/ui-tars-1.5-7b:latest struggles

        Args:
            prompt: The prompt to send
            temperature: Override temperature
            max_tokens: Override max tokens

        Returns:
            LLMResponse with generated content
        """
        if not self.kimi_api_key:
            logger.warning("Kimi API key not set, falling back to main model")
            return await self.generate(prompt, temperature=temperature, max_tokens=max_tokens)

        temperature = temperature if temperature is not None else self.temperature
        max_tokens = max_tokens or self.max_tokens

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
                response = await client.post(
                    f"{self.kimi_api_url}/chat/completions",
                    headers={
                        'Authorization': f'Bearer {self.kimi_api_key}',
                        'Content-Type': 'application/json',
                    },
                    json={
                        'model': self.complex_model,
                        'messages': [{'role': 'user', 'content': prompt}],
                        'temperature': temperature,
                        'max_tokens': max_tokens,
                    }
                )
                response.raise_for_status()

                data = response.json()
                content = data.get('choices', [{}])[0].get('message', {}).get('content', '')

                return LLMResponse(
                    content=content,
                    model=self.complex_model,
                    done=True,
                )

        except httpx.HTTPStatusError as e:
            logger.error(f"Kimi API HTTP error: {e.response.status_code}")
            # Fallback to main model
            logger.info("Falling back to main model")
            return await self.generate(prompt, temperature=temperature, max_tokens=max_tokens)

        except Exception as e:
            logger.error(f"Kimi API error: {e}")
            # Fallback to main model
            logger.info("Falling back to main model")
            return await self.generate(prompt, temperature=temperature, max_tokens=max_tokens)

    async def chat_complex(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """
        Chat using Kimi API for complex reasoning tasks.

        Args:
            messages: List of {'role': 'user'|'assistant', 'content': '...'}
            temperature: Override temperature
            max_tokens: Override max tokens

        Returns:
            LLMResponse with generated content
        """
        if not self.kimi_api_key:
            logger.warning("Kimi API key not set, falling back to main model")
            return await self.chat(messages, temperature=temperature, max_tokens=max_tokens)

        temperature = temperature if temperature is not None else self.temperature
        max_tokens = max_tokens or self.max_tokens

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
                response = await client.post(
                    f"{self.kimi_api_url}/chat/completions",
                    headers={
                        'Authorization': f'Bearer {self.kimi_api_key}',
                        'Content-Type': 'application/json',
                    },
                    json={
                        'model': self.complex_model,
                        'messages': messages,
                        'temperature': temperature,
                        'max_tokens': max_tokens,
                    }
                )
                response.raise_for_status()

                data = response.json()
                content = data.get('choices', [{}])[0].get('message', {}).get('content', '')

                return LLMResponse(
                    content=content,
                    model=self.complex_model,
                    done=True,
                )

        except Exception as e:
            logger.error(f"Kimi API chat error: {e}")
            # Fallback to main model
            return await self.chat(messages, temperature=temperature, max_tokens=max_tokens)

    def get_model_for_task(self, task_type: str) -> str:
        """
        Get the appropriate model for a task type.

        Args:
            task_type: One of 'general', 'vision', 'complex', 'function_calling'

        Returns:
            Model name to use
        """
        if task_type == 'vision':
            return self.vision_model
        elif task_type == 'complex':
            return self.complex_model if self.kimi_api_key else self.main_model
        else:
            # general, function_calling, etc. all use 0000/ui-tars-1.5-7b:latest
            return self.main_model


# Global singleton for easy access
_default_client: Optional[LLMClient] = None


def get_llm_client(config: Optional[Dict] = None) -> LLMClient:
    """Get or create the default LLM client."""
    global _default_client
    if _default_client is None:
        _default_client = LLMClient(config)
    return _default_client


def reset_llm_client():
    """Reset the default client (useful for testing)."""
    global _default_client
    if _default_client:
        asyncio.get_event_loop().run_until_complete(_default_client.close())
    _default_client = None
