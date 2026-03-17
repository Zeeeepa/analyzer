import os
"""
LLM Fallback Chain - Cost-optimized strategic planning with graceful degradation.

Implements a 3-tier fallback system:
1. Kimi K2 (remote, best quality, costs money) - for complex planning
2. Llama 3.1 8B (local/remote, good quality, free) - for most planning
3. Ollama 7B (local, fast, basic quality) - for simple planning & fallback

Key features:
- Automatic fallback on failure/timeout
- Cost tracking and optimization
- Minor re-plans use cheaper models first
- Only escalate to expensive models when needed
"""

import asyncio
import time
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from loguru import logger
from urllib.parse import urlparse # Added import

try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    AsyncOpenAI = None
    OPENAI_AVAILABLE = False

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False


class LLMTier(Enum):
    """LLM tier levels for fallback chain."""
    KIMI_K2 = 1      # Best quality, costs money (fallback)
    QWEN3_8B = 2     # Primary model - best for tool calling
    VISION = 3       # moondream for vision tasks


@dataclass
class LLMCallResult:
    """Result from an LLM call."""
    success: bool
    content: str = ""
    tier_used: Optional[LLMTier] = None
    latency_ms: int = 0
    error: Optional[str] = None
    tokens_used: Dict[str, int] = field(default_factory=dict)


@dataclass
class FallbackConfig:
    """Configuration for LLM fallback chain."""
    # Primary LLM selection - 0000/ui-tars-1.5-7b:latest for all tasks
    primary_llm: LLMTier = LLMTier.QWEN3_8B  # Best for tool calling

    # Timeouts (seconds) - extended for complex planning and remote GPU latency
    kimi_timeout: float = 120.0
    qwen_timeout: float = 120.0
    vision_timeout: float = 90.0

    # Retry limits
    max_retries_per_tier: int = 3
    max_total_retries: int = 5

    # Cost optimization
    use_qwen_for_minor_replans: bool = True  # Use 0000/ui-tars-1.5-7b:latest for simple adjustments
    escalate_to_kimi_after_failures: int = 3  # Escalate to Kimi after N qwen failures

    # Model names - only 3 models allowed
    main_model: str = os.environ.get("ANTHROPIC_MODEL", "glm-5")        # Primary for all tasks
    vision_model: str = os.environ.get("ANTHROPIC_MODEL", "glm-5")  # Vision tasks only

    # Endpoints - default to remote for CLI users
    ollama_url: str = os.environ.get("ANTHROPIC_BASE_URL", "https://api.z.ai/api/anthropic")  # Remote GPU server (CLI default)


@dataclass
class CostTracker:
    """Track LLM usage and cost savings."""
    kimi_calls: int = 0
    qwen_calls: int = 0
    vision_calls: int = 0

    kimi_tokens_in: int = 0
    kimi_tokens_out: int = 0

    # Cost per million tokens
    KIMI_INPUT_COST = 0.15
    KIMI_OUTPUT_COST = 2.50

    def add_call(self, tier: LLMTier, tokens_in: int = 0, tokens_out: int = 0):
        """Record a successful LLM call."""
        if tier == LLMTier.KIMI_K2:
            self.kimi_calls += 1
            self.kimi_tokens_in += tokens_in
            self.kimi_tokens_out += tokens_out
        elif tier == LLMTier.QWEN3_8B:
            self.qwen_calls += 1
        elif tier == LLMTier.VISION:
            self.vision_calls += 1

    def get_kimi_cost(self) -> float:
        """Calculate Kimi K2 costs."""
        input_cost = (self.kimi_tokens_in / 1_000_000) * self.KIMI_INPUT_COST
        output_cost = (self.kimi_tokens_out / 1_000_000) * self.KIMI_OUTPUT_COST
        return input_cost + output_cost

    def get_estimated_savings(self) -> float:
        """Estimate cost savings from using 0000/ui-tars-1.5-7b:latest instead of Kimi.

        Assumes we would have used Kimi for everything without qwen.
        Average Kimi call: 500 input + 300 output tokens = ~$0.0008
        """
        avg_kimi_cost_per_call = 0.0008
        free_calls = self.qwen_calls + self.vision_calls
        return free_calls * avg_kimi_cost_per_call

    def get_report(self) -> Dict[str, Any]:
        """Get cost tracking report."""
        return {
            "calls": {
                "kimi_k2": self.kimi_calls,
                "qwen3_8b": self.qwen_calls,
                "vision": self.vision_calls,
                "total": self.kimi_calls + self.qwen_calls + self.vision_calls,
            },
            "kimi_cost_usd": round(self.get_kimi_cost(), 4),
            "estimated_savings_usd": round(self.get_estimated_savings(), 4),
            "free_call_percentage": round(
                100 * (self.qwen_calls + self.vision_calls) /
                max(1, self.kimi_calls + self.qwen_calls + self.vision_calls),
                1
            )
        }


class LLMFallbackChain:
    """
    Manages fallback chain for strategic planning LLM calls.

    Model strategy (3 models only):
    1. 0000/ui-tars-1.5-7b:latest - Primary model for all tasks (best tool calling)
    2. moondream:latest - Vision tasks only
    3. Kimi K2 - Fallback when 0000/ui-tars-1.5-7b:latest fails

    Intelligence:
    - All tasks: Start with 0000/ui-tars-1.5-7b:latest
    - Vision tasks: Use moondream
    - On failure: Escalate to Kimi K2
    - Auto-escalate to better model after repeated failures
    - Track costs and savings
    """

    def __init__(
        self,
        config: FallbackConfig,
        kimi_client=None,  # Optional KimiK2Client
    ):
        self.config = config
        self.kimi_client = kimi_client
        self.cost_tracker = CostTracker()

        # Failure tracking for auto-escalation
        self.consecutive_qwen_failures = 0

        # HTTP client for 0000/ui-tars-1.5-7b:latest via Ollama
        self._qwen_client: Optional[httpx.AsyncClient] = None

        logger.info(
            f"LLM fallback chain initialized: primary={config.primary_llm.name}, "
            f"models: 0000/ui-tars-1.5-7b:latest, moondream, Kimi K2"
        )

    async def _get_qwen_client(self) -> Optional[httpx.AsyncClient]:
        """Get or create 0000/ui-tars-1.5-7b:latest HTTP client via Ollama."""
        if not HTTPX_AVAILABLE:
            return None
        if self._qwen_client is None:
            self._qwen_client = httpx.AsyncClient(
                base_url=self.config.ollama_url,
                timeout=httpx.Timeout(self.config.qwen_timeout, connect=5.0),
            )
        return self._qwen_client

    async def close(self):
        """Close HTTP clients."""
        if self._qwen_client:
            await self._qwen_client.aclose()
            self._qwen_client = None

    def _should_escalate_to_kimi(self) -> bool:
        """Decide if we should escalate to Kimi after repeated qwen failures."""
        if self.consecutive_qwen_failures >= self.config.escalate_to_kimi_after_failures:
            logger.warning(
                f"Escalating to Kimi K2 after {self.consecutive_qwen_failures} "
                f"0000/ui-tars-1.5-7b:latest failures"
            )
            return True
        return False

    async def call_with_fallback(
        self,
        system_prompt: str,
        user_prompt: str,
        is_minor_replan: bool = False,
        temperature: float = 0.3,
        max_tokens: int = 12288,
    ) -> LLMCallResult:
        """
        Make an LLM call with automatic fallback.

        Model strategy:
        - Primary: 0000/ui-tars-1.5-7b:latest (best for tool calling)
        - Fallback: Kimi K2 (after 3 qwen failures)

        Args:
            system_prompt: System prompt for the LLM
            user_prompt: User prompt for the LLM
            is_minor_replan: Ignored - always uses 0000/ui-tars-1.5-7b:latest
            temperature: Temperature for generation
            max_tokens: Maximum tokens to generate

        Returns:
            LLMCallResult with success status and content
        """
        # Simple 2-tier strategy: 0000/ui-tars-1.5-7b:latest -> Kimi K2
        if self._should_escalate_to_kimi():
            tiers = [LLMTier.KIMI_K2, LLMTier.QWEN3_8B]
        else:
            tiers = [LLMTier.QWEN3_8B, LLMTier.KIMI_K2]

        total_retries = 0

        for tier in tiers:
            if total_retries >= self.config.max_total_retries:
                logger.error(f"Hit max total retries ({self.config.max_total_retries})")
                break

            # Try this tier with retries
            for attempt in range(self.config.max_retries_per_tier):
                total_retries += 1

                try:
                    result = await self._call_tier(
                        tier=tier,
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )

                    if result.success:
                        # Success! Track it and return
                        self.cost_tracker.add_call(
                            tier,
                            result.tokens_used.get("input", 0),
                            result.tokens_used.get("output", 0)
                        )

                        # Reset failure counter on success
                        if tier == LLMTier.QWEN3_8B:
                            self.consecutive_qwen_failures = 0

                        logger.info(
                            f"LLM call succeeded: tier={tier.name}, "
                            f"latency={result.latency_ms}ms, attempt={attempt+1}"
                        )
                        return result

                    # Failed, log and retry
                    logger.warning(
                        f"LLM call failed: tier={tier.name}, attempt={attempt+1}, "
                        f"error={result.error}"
                    )

                except Exception as e:
                    logger.error(f"Exception calling {tier.name}: {e}")
                    continue

            # All retries for this tier failed
            if tier == LLMTier.QWEN3_8B:
                self.consecutive_qwen_failures += 1

            logger.warning(f"Tier {tier.name} exhausted, trying next tier...")

        # All tiers failed
        return LLMCallResult(
            success=False,
            error="All LLM tiers failed",
        )

    async def _call_tier(
        self,
        tier: LLMTier,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMCallResult:
        """Call a specific LLM tier."""
        start_time = time.time()

        if tier == LLMTier.KIMI_K2:
            return await self._call_kimi(
                system_prompt, user_prompt, temperature, max_tokens, start_time
            )
        elif tier == LLMTier.QWEN3_8B:
            return await self._call_qwen(
                system_prompt, user_prompt, temperature, max_tokens, start_time
            )

        return LLMCallResult(success=False, error=f"Unknown tier: {tier}")

    async def _call_kimi(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
        start_time: float,
    ) -> LLMCallResult:
        """Call Kimi K2 via existing client."""
        if not self.kimi_client:
            return LLMCallResult(
                success=False,
                error="Kimi client not available"
            )

        if not self.kimi_client.can_call():
            return LLMCallResult(
                success=False,
                error="Kimi budget/limit reached"
            )

        try:
            # Use timeout
            response = await asyncio.wait_for(
                self.kimi_client.client.chat.completions.create(
                    model=self.kimi_client.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                ),
                timeout=self.config.kimi_timeout
            )

            latency_ms = int((time.time() - start_time) * 1000)
            content = response.choices[0].message.content

            return LLMCallResult(
                success=True,
                content=content,
                tier_used=LLMTier.KIMI_K2,
                latency_ms=latency_ms,
                tokens_used={
                    "input": response.usage.prompt_tokens,
                    "output": response.usage.completion_tokens,
                }
            )

        except asyncio.TimeoutError:
            latency_ms = int((time.time() - start_time) * 1000)
            return LLMCallResult(
                success=False,
                error=f"Kimi K2 timeout after {self.config.kimi_timeout}s",
                tier_used=LLMTier.KIMI_K2,
                latency_ms=latency_ms,
            )
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            return LLMCallResult(
                success=False,
                error=f"Kimi K2 error: {str(e)}",
                tier_used=LLMTier.KIMI_K2,
                latency_ms=latency_ms,
            )

    async def _call_qwen(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
        start_time: float,
    ) -> LLMCallResult:
        """Call 0000/ui-tars-1.5-7b:latest via Ollama (local or GPU server)."""
        client = await self._get_qwen_client()
        if not client:
            return LLMCallResult(
                success=False,
                error="Qwen client not available (httpx missing)"
            )

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]

            if self._looks_like_ollama_endpoint(self.config.ollama_url):
                # Ollama-compatible API
                endpoint_path = "/api/chat"
                payload = {
                    "model": self.config.main_model,  # 0000/ui-tars-1.5-7b:latest
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens,
                    }
                }
            else:
                # OpenAI-compatible API (e.g., Z.AI anthropic proxy)
                endpoint_path = "/v1/chat/completions"
                payload = {
                    "model": self.config.main_model,  # 0000/ui-tars-1.5-7b:latest
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": False,
                }

            response = await client.post(endpoint_path, json=payload)
            response.raise_for_status()

            latency_ms = int((time.time() - start_time) * 1000)
            data = response.json()

            # Parse response based on API type
            if self._looks_like_ollama_endpoint(self.config.ollama_url):
                content = data.get("message", {}).get("content", "")
                tokens = data.get("eval_count", 0) + data.get("prompt_eval_count", 0)
            else:
                # OpenAI format
                content = data['choices'][0]['message'].get('content', '')
                tokens = data.get('usage', {}).get('total_tokens', 0)

            if not content:
                return LLMCallResult(
                    success=False,
                    error="Empty response from main model",
                    tier_used=LLMTier.QWEN3_8B,
                    latency_ms=latency_ms,
                )

            # Reset failure counter on success
            self.consecutive_qwen_failures = 0

            return LLMCallResult(
                success=True,
                content=content,
                tier_used=LLMTier.QWEN3_8B,
                latency_ms=latency_ms,
                tokens_used={
                    "input": tokens, # For OpenAI we would have prompt_tokens + completion_tokens
                    "output": tokens # For simplicity, treat total tokens as both here if separate not available
                }
            )

        except httpx.TimeoutException:
            latency_ms = int((time.time() - start_time) * 1000)
            return LLMCallResult(
                success=False,
                error=f"0000/ui-tars-1.5-7b:latest timeout after {self.config.qwen_timeout}s",
                tier_used=LLMTier.QWEN3_8B,
                latency_ms=latency_ms,
            )
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            return LLMCallResult(
                success=False,
                error=f"0000/ui-tars-1.5-7b:latest error: {str(e)}",
                tier_used=LLMTier.QWEN3_8B,
                latency_ms=latency_ms,
            )

    def get_cost_report(self) -> Dict[str, Any]:
        """Get cost tracking report."""
        report = self.cost_tracker.get_report()
        report["consecutive_qwen_failures"] = self.consecutive_qwen_failures
        return report
