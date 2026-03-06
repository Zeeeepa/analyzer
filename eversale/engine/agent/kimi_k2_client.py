"""
Kimi K2 Client - Strategic AI for high-impact planning and recovery.

Uses Kimi K2 (1 trillion params, 32B activated) for:
1. Task Planning (ONE call at start) - Creates step-by-step execution plan
2. Recovery (RARE) - When local 7B fails 2x, escalate for smart recovery

Pricing (ultra cheap):
- Input: $0.15 per million tokens
- Output: $2.50 per million tokens
- Typical planning call: ~500 input + ~300 output = $0.0008 per task

API is OpenAI-compatible, uses standard openai library.

Usage Integration:
- Kimi calls count toward user's daily compute hours (Pro: 5hrs, Business: 10hrs)
- Reports usage to eversale.io/api/desktop/kimi-usage for tracking
- Validates license tier before making calls
"""

import os
import json
import time
import asyncio
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from loguru import logger

# Use openai library for OpenAI-compatible API
try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    AsyncOpenAI = None  # type: ignore
    OPENAI_AVAILABLE = False
    logger.warning("openai library not available - install with: pip install openai")

# HTTP client for eversale.io API
try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False


# Cost tracking storage
USAGE_DIR = Path("memory/kimi_usage")
USAGE_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class KimiUsage:
    """Track Kimi K2 API usage for cost monitoring."""
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0
    planning_calls: int = 0
    recovery_calls: int = 0
    date: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))

    # Pricing (per million tokens)
    INPUT_COST_PER_M = 0.15
    OUTPUT_COST_PER_M = 2.50

    @property
    def total_cost(self) -> float:
        """Calculate total cost in USD."""
        input_cost = (self.input_tokens / 1_000_000) * self.INPUT_COST_PER_M
        output_cost = (self.output_tokens / 1_000_000) * self.OUTPUT_COST_PER_M
        return input_cost + output_cost

    def to_dict(self) -> Dict:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "calls": self.calls,
            "planning_calls": self.planning_calls,
            "recovery_calls": self.recovery_calls,
            "date": self.date,
            "total_cost_usd": round(self.total_cost, 4)
        }

    def save(self):
        """Persist usage to disk."""
        path = USAGE_DIR / f"usage_{self.date}.json"
        path.write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def load_today(cls) -> 'KimiUsage':
        """Load today's usage or create new."""
        today = datetime.now().strftime("%Y-%m-%d")
        path = USAGE_DIR / f"usage_{today}.json"
        if path.exists():
            data = json.loads(path.read_text())
            return cls(**{k: v for k, v in data.items() if k != 'total_cost_usd'})
        return cls()


@dataclass
class PlanStep:
    """A single step in the execution plan."""
    step_number: int
    action: str  # What to do
    tool: str  # Which tool to use (e.g., "playwright_navigate")
    arguments: Dict[str, Any]  # Tool arguments
    expected_result: str  # What success looks like
    fallback: Optional[str] = None  # What to do if this fails


@dataclass
class TaskPlan:
    """Complete execution plan from Kimi K2."""
    task_id: str
    original_prompt: str
    summary: str  # One-line task summary
    steps: List[PlanStep]
    estimated_iterations: int
    potential_blockers: List[str]
    success_criteria: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


class EversaleBillingIntegration:
    """
    Integration with eversale.io for usage tracking and tier enforcement.

    Tier Limits (daily compute hours):
    - Pro ($99/mo): 5 hours/day
    - Business ($199/mo): 10 hours/day
    - Founder: Unlimited

    Kimi K2 calls count toward compute hours based on processing time.
    """

    EVERSALE_API_URL = "https://eversale.io/api/desktop"

    # Kimi processing time estimates (seconds) for billing
    KIMI_PROCESSING_TIME = {
        "planning": 15,   # ~15 seconds per planning call
        "recovery": 10,   # ~10 seconds per recovery call
    }

    def __init__(self, license_key: Optional[str] = None):
        self.license_key = license_key or self._load_license_key()
        self._user_tier: Optional[str] = None
        self._usage_cache: Optional[Dict] = None
        self._cache_time: float = 0
        self._cache_ttl = 60  # Cache for 60 seconds

    def _load_license_key(self) -> Optional[str]:
        """Load license key from standard location."""
        key_path = Path.home() / ".eversale" / "license.key"
        if key_path.exists():
            return key_path.read_text().strip()
        return os.getenv("EVERSALE_LICENSE_KEY")

    async def validate_and_get_tier(self) -> tuple[bool, str, Dict]:
        """
        Validate license and get user tier.

        Returns:
            (allowed, tier, usage_info)
            - allowed: True if user can make Kimi calls
            - tier: 'pro-monthly', 'business-monthly', 'founder', or 'none'
            - usage_info: Current usage stats
        """
        if not self.license_key:
            return False, "none", {"error": "No license key"}

        # Check cache
        if self._usage_cache and time.time() - self._cache_time < self._cache_ttl:
            tier = self._usage_cache.get("plan", "none")
            return self._usage_cache.get("allowed", False), tier, self._usage_cache

        if not HTTPX_AVAILABLE:
            logger.warning("httpx not available - skipping eversale.io validation")
            return True, "unknown", {}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.EVERSALE_API_URL}/status",
                    headers={"Authorization": f"Bearer {self.license_key}"}
                )

                if response.status_code == 200:
                    data = response.json()
                    self._usage_cache = data
                    self._cache_time = time.time()

                    account = data.get("account", {}) if isinstance(data, dict) else {}
                    usage = data.get("usage", {}) if isinstance(data, dict) else {}

                    tier = account.get("plan", "cloud-basic")
                    hours_remaining = usage.get("hoursRemaining", 0)

                    # Allow if founder or has hours remaining
                    allowed = tier == "founder" or hours_remaining > 0

                    return allowed, tier, data
                elif response.status_code == 401:
                    return False, "none", {"error": "Invalid license"}
                else:
                    logger.warning(f"eversale.io status check failed: {response.status_code}")
                    return True, "unknown", {}  # Fail open for now

        except Exception as e:
            logger.warning(f"eversale.io validation failed: {e}")
            return True, "unknown", {}  # Fail open on network errors

    async def report_kimi_usage(self, call_type: str, processing_time_ms: int) -> bool:
        """
        Report Kimi K2 usage to eversale.io.

        This counts toward the user's daily compute hours.
        """
        if not self.license_key or not HTTPX_AVAILABLE:
            return False

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.EVERSALE_API_URL}/kimi-usage",
                    headers={"Authorization": f"Bearer {self.license_key}"},
                    json={
                        "callType": call_type,
                        "processingTimeMs": processing_time_ms,
                        "timestamp": datetime.now().isoformat()
                    }
                )

                if response.status_code == 200:
                    # Invalidate cache
                    self._usage_cache = None
                    return True
                else:
                    logger.warning(f"Failed to report Kimi usage: {response.status_code}")
                    return False

        except Exception as e:
            logger.warning(f"Failed to report Kimi usage: {e}")
            return False

    def get_tier_kimi_limits(self, tier: str) -> Dict[str, int]:
        """Get Kimi-specific limits based on tier."""
        limits = {
            "pro-monthly": {
                "max_planning_calls_per_day": 50,
                "max_recovery_calls_per_day": 25,
                "max_calls_per_task": 3
            },
            "business-monthly": {
                "max_planning_calls_per_day": 200,
                "max_recovery_calls_per_day": 100,
                "max_calls_per_task": 5
            },
            "founder": {
                "max_planning_calls_per_day": 999999,
                "max_recovery_calls_per_day": 999999,
                "max_calls_per_task": 10
            }
        }
        return limits.get(tier, limits["pro-monthly"])


class KimiK2Client:
    """
    Kimi K2 API client for strategic planning and recovery.

    Uses OpenAI-compatible API via multiple providers:
    - Moonshot AI: https://api.moonshot.ai/v1 (model: kimi-k2-0711-preview)
    - OpenRouter: https://openrouter.ai/api/v1 (model: moonshotai/kimi-k2-instruct)
    - DeepInfra: https://api.deepinfra.com/v1/openai (model: moonshotai/Kimi-K2-Instruct)
    """

    # Provider configurations
    PROVIDERS = {
        "eversale": {
            "base_url": "https://eversale.io/api/llm/v1",  # Proxy through eversale.io
            "model": "kimi",  # eversale.io routes to Kimi
            "env_key": "EVERSALE_LICENSE_KEY",  # Uses license key
        },
        "anthropic": {
            "base_url": os.environ.get("ANTHROPIC_BASE_URL", "https://api.z.ai/api/anthropic"),
            "model": os.environ.get("ANTHROPIC_MODEL", "glm-5"),
            "env_key": "ANTHROPIC_API_KEY",
        },
        "moonshot": {
            "base_url": "https://api.moonshot.ai/v1",  # Global endpoint (.ai not .cn)
            "model": "kimi-k2-0711-preview",
            "env_key": "MOONSHOT_API_KEY",
        },
        "openrouter": {
            "base_url": "https://openrouter.ai/api/v1",
            "model": "moonshotai/kimi-k2-instruct",
            "env_key": "OPENROUTER_API_KEY",
        },
        "deepinfra": {
            "base_url": "https://api.deepinfra.com/v1/openai",
            "model": "moonshotai/Kimi-K2-Instruct",
            "env_key": "DEEPINFRA_API_KEY",
        },
    }

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.moonshot.ai/v1",
        model: str = "kimi-k2-0711-preview",
        provider: str = "auto",  # "auto", "moonshot", "openrouter", "deepinfra"
        daily_budget_usd: float = 1.0,
        max_calls_per_task: int = 3,
    ):
        """
        Initialize Kimi K2 client.

        Args:
            api_key: API key (or set env var based on provider)
            base_url: API endpoint (auto-detected from provider)
            model: Model to use (auto-detected from provider)
            provider: Which provider to use ("auto" tries all until one works)
            daily_budget_usd: Maximum daily spend (default $1)
            max_calls_per_task: Max Kimi calls per task (default 3)
        """
        # Auto-detect provider from available API keys
        self.provider = provider
        if provider == "auto":
            self.provider, self.api_key, self.base_url, self.model = self._auto_detect_provider()
        else:
            provider_config = self.PROVIDERS.get(provider, self.PROVIDERS["moonshot"])
            self.api_key = api_key or os.getenv(provider_config["env_key"], "")
            self.base_url = base_url if base_url != "https://api.moonshot.ai/v1" else provider_config["base_url"]
            self.model = model if model != "kimi-k2-0711-preview" else provider_config["model"]

        self.daily_budget = daily_budget_usd
        self.max_calls_per_task = max_calls_per_task
        self.task_call_count = 0

        # Usage tracking (local)
        self.usage = KimiUsage.load_today()

        # Eversale.io billing integration
        self.billing = EversaleBillingIntegration()
        self._user_tier: Optional[str] = None
        self._tier_validated = False

        # Async client (lazy init)
        self._client: Optional[AsyncOpenAI] = None

        if not self.api_key:
            # Silently skip - strategic planning is optional
            logger.debug("No API key found for strategic planner provider")
        else:
            logger.debug(f"Strategic planner initialized: provider={self.provider}, model={self.model}")

    def _auto_detect_provider(self) -> tuple:
        """Auto-detect which provider to use based on available API keys."""
        # Try direct API providers first (moonshot, openrouter, deepinfra)
        for name in ["anthropic", "moonshot", "openrouter", "deepinfra"]:
            config = self.PROVIDERS[name]
            api_key = os.getenv(config["env_key"], "")
            if api_key:
                logger.debug(f"Auto-detected strategic planner provider: {name}")
                return name, api_key, config["base_url"], config["model"]

        # Fallback: Try eversale.io proxy with license key
        # This allows Founder/Pro/Business users to use Kimi without direct API keys
        license_key = os.getenv("EVERSALE_LICENSE_KEY", "")
        if not license_key:
            # Check standard license file location
            key_path = Path.home() / ".eversale" / "license.key"
            if key_path.exists():
                try:
                    license_key = key_path.read_text().strip()
                except Exception:
                    pass

        # NOTE: eversale.io proxy currently routes to Ollama GPU server which doesn't have Kimi
        # When Kimi routing is added to eversale.io, uncomment this block:
        # if license_key:
        #     config = self.PROVIDERS["eversale"]
        #     logger.info(f"[KIMI] Using eversale.io proxy with license key")
        #     return "eversale", license_key, config["base_url"], config["model"]

        # For now, skip eversale proxy - Kimi requires direct API key
        if license_key:
            logger.debug("[KIMI] License found but eversale.io proxy doesn't support Kimi yet - using local model")

        # No provider found - return defaults silently
        return "anthropic", os.environ.get("ANTHROPIC_API_KEY", ""), os.environ.get("ANTHROPIC_BASE_URL", "https://api.z.ai/api/anthropic"), os.environ.get("ANTHROPIC_MODEL", "glm-5")

    @property
    def client(self) -> Optional[AsyncOpenAI]:
        """Get or create async OpenAI client."""
        if not OPENAI_AVAILABLE:
            return None
        if not self.api_key:
            return None
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            )
        return self._client

    def is_available(self) -> bool:
        """Check if Kimi K2 is available and within budget."""
        if not OPENAI_AVAILABLE or not self.api_key:
            return False
        if self.usage.total_cost >= self.daily_budget:
            logger.warning(f"Kimi K2 daily budget exhausted: ${self.usage.total_cost:.4f} >= ${self.daily_budget}")
            return False
        return True

    async def is_available_async(self) -> tuple[bool, str]:
        """
        Check if Kimi K2 is available, including tier validation.

        Returns:
            (available, reason)
        """
        if not OPENAI_AVAILABLE or not self.api_key:
            return False, "Kimi K2 not configured"

        if self.usage.total_cost >= self.daily_budget:
            return False, f"Daily budget exhausted (${self.usage.total_cost:.4f})"

        # Validate with eversale.io
        allowed, tier, usage_info = await self.billing.validate_and_get_tier()
        self._user_tier = tier
        self._tier_validated = True

        if not allowed:
            if tier == "none":
                return False, "No valid license - get one at eversale.io/desktop"
            else:
                hours_used = usage_info.get("hoursUsed", 0)
                hours_limit = usage_info.get("hoursLimit", 5)
                return False, f"Daily limit reached ({hours_used:.1f}/{hours_limit}hrs). Resets at midnight UTC."

        return True, "OK"

    def reset_task_counter(self):
        """Reset per-task call counter (call at start of each task)."""
        self.task_call_count = 0
        self._tier_validated = False  # Re-validate tier on new task

    def can_call(self) -> bool:
        """Check if we can make another Kimi call for this task (sync check)."""
        return (
            self.is_available() and
            self.task_call_count < self.max_calls_per_task
        )

    async def can_call_async(self) -> tuple[bool, str]:
        """
        Check if we can make another Kimi call (async with tier validation).

        Returns:
            (allowed, reason)
        """
        # Check basic availability
        available, reason = await self.is_available_async()
        if not available:
            return False, reason

        # Check per-task limit based on tier
        if self._user_tier:
            limits = self.billing.get_tier_kimi_limits(self._user_tier)
            max_per_task = limits.get("max_calls_per_task", 3)
            if self.task_call_count >= max_per_task:
                return False, f"Max {max_per_task} Kimi calls per task ({self._user_tier})"

        return True, "OK"

    def _track_usage(self, input_tokens: int, output_tokens: int, call_type: str = "other"):
        """Track token usage and costs (local tracking)."""
        self.usage.input_tokens += input_tokens
        self.usage.output_tokens += output_tokens
        self.usage.calls += 1
        self.task_call_count += 1

        if call_type == "planning":
            self.usage.planning_calls += 1
        elif call_type == "recovery":
            self.usage.recovery_calls += 1

        self.usage.save()

        # Cost info only logged locally (not shown to users)
        # Users just see their tier limits (5hrs/10hrs)
        logger.debug(
            f"[INTERNAL] Kimi K2 cost: +{input_tokens}in/{output_tokens}out tokens, "
            f"total today: ${self.usage.total_cost:.4f}"
        )

    async def _track_usage_async(self, input_tokens: int, output_tokens: int, call_type: str, processing_time_ms: int):
        """Track usage both locally and report to eversale.io."""
        # Local tracking
        self._track_usage(input_tokens, output_tokens, call_type)

        # Report to eversale.io (fire and forget)
        asyncio.create_task(
            self.billing.report_kimi_usage(call_type, processing_time_ms)
        )

    async def plan_task(
        self,
        prompt: str,
        available_tools: List[str],
        context: str = "",
    ) -> Optional[TaskPlan]:
        """
        Create a strategic execution plan for a task.

        This is the PRIMARY use of Kimi K2 - called ONCE at task start.
        Returns a step-by-step plan that the local 7B model executes.

        Args:
            prompt: User's task request
            available_tools: List of available tool names
            context: Additional context (previous failures, page state, etc.)

        Returns:
            TaskPlan with steps, or None if planning fails
        """
        if not self.can_call():
            logger.warning("Cannot call Kimi K2 - budget or call limit reached")
            return None

        # Build the planning prompt (optimized based on Kimi K2 best practices)
        # See: https://www.dbreunig.com/2025/07/30/how-kimi-was-post-trained-for-tool-use.html
        system_prompt = """You are a strategic task planner for an AI browser automation agent.

JOB: Create PRECISE step-by-step execution plans for web automation tasks.

AVAILABLE TOOLS:
{tools}

PLANNING RULES:
1. Think step-by-step: reason about tool relevance before selecting (ReAct pattern)
2. Each step = ONE tool call with CONCRETE arguments - NEVER use placeholders like {{variable}} or {{company_name}}
3. STRONGLY PREFER combined tools that do extract+save in one step (reduces complexity)
4. For data pipelines: use tools that extract AND save directly rather than separate extract then save
5. Include verification steps to check results before proceeding
6. Anticipate blockers: login walls, CAPTCHAs, rate limits, missing data
7. Plan fallbacks for likely failure points

CRITICAL - TOOL SELECTION (in order of preference):
1. playwright_extract_to_csv - BEST for extracting structured data to CSV (combines extract+save)
   Arguments: {{"schema": {{"name": "string", "url": "string"}}, "csv_path": "/home/user/output.csv"}}
2. playwright_batch_extract - For visiting multiple URLs and extracting contacts
   Arguments: {{"urls": ["https://site1.com", "https://site2.com"], "csv_path": "/path/to/out.csv"}}
3. playwright_navigate - Go to URL first
   Arguments: {{"url": "https://example.com"}}
4. playwright_fill + playwright_click - For forms and search
5. playwright_extract_entities - For structured data when not saving to CSV directly
   Arguments: {{"entity_types": ["company", "email", "phone"], "schema": {{"field": "type"}}}}
6. playwright_screenshot - For visual verification
7. playwright_get_markdown - For page content as text

IMPORTANT: Steps are executed INDEPENDENTLY - data from one step is NOT automatically available to the next.
Therefore:
- Use combined tools (extract_to_csv) instead of extract → save sequences
- Include full URLs and paths in each step, not references to previous results
- If processing multiple items, use batch tools or plan explicit iteration

OUTPUT FORMAT (JSON only, no markdown):
{{
    "summary": "One-line task description",
    "steps": [
        {{
            "step_number": 1,
            "action": "Clear description of what this step achieves",
            "tool": "exact_tool_name",
            "arguments": {{"key": "specific_value_not_placeholder"}},
            "expected_result": "Concrete success criteria",
            "fallback": "Alternative approach if this fails"
        }}
    ],
    "estimated_iterations": 5,
    "potential_blockers": ["login required", "rate limiting", "CAPTCHA"],
    "success_criteria": "Specific measurable outcome (e.g., 'extracted 10+ contacts')"
}}"""

        # Get actual home directory for path expansion
        from pathlib import Path
        home_dir = str(Path.home())

        user_prompt = f"""TASK: {prompt}

ENVIRONMENT:
- Home directory (~): {home_dir}
- Use full paths, not ~. Example: {home_dir}/lead_research/output.csv

{f"CONTEXT: {context}" if context else ""}

Create an execution plan. Structure your response as JSON only."""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt.format(tools=", ".join(available_tools))},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,  # Lower temp for more consistent planning
                max_tokens=12288,  # Supports 200-300 step plans (~40 tokens/step)
            )

            # Track usage
            usage = response.usage
            self._track_usage(
                usage.prompt_tokens,
                usage.completion_tokens,
                call_type="planning"
            )

            # Parse response
            content = response.choices[0].message.content

            # Extract JSON from response (handle markdown code blocks)
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            content = content.strip()

            # Try to fix truncated JSON (common with long responses)
            try:
                plan_data = json.loads(content)
            except json.JSONDecodeError:
                # Attempt to repair truncated JSON
                import re

                # Find if we have a valid partial structure
                # Try to close any open arrays/objects
                fixed = content

                # Count unclosed brackets
                open_braces = fixed.count('{') - fixed.count('}')
                open_brackets = fixed.count('[') - fixed.count(']')

                # If we're in the middle of a string, close it
                if fixed.count('"') % 2 == 1:
                    fixed = fixed.rsplit('"', 1)[0] + '"'

                # Close any open arrays/objects
                if open_brackets > 0:
                    fixed += ']' * open_brackets
                if open_braces > 0:
                    fixed += '}' * open_braces

                try:
                    plan_data = json.loads(fixed)
                    logger.warning("Repaired truncated JSON response from Kimi K2")
                except json.JSONDecodeError as e:
                    logger.error(f"Could not repair JSON: {e}")
                    logger.debug(f"Raw content: {content[:500]}...")
                    raise

            # Build TaskPlan
            import hashlib
            task_id = hashlib.md5(f"{prompt}{datetime.now().isoformat()}".encode()).hexdigest()[:12]

            steps = []
            for i, s in enumerate(plan_data.get("steps", [])):
                try:
                    step = PlanStep(
                        step_number=s.get("step_number", i + 1),
                        action=s.get("action", f"Step {i+1}"),
                        tool=s.get("tool", "playwright_navigate"),
                        arguments=s.get("arguments", s.get("args", {})),
                        expected_result=s.get("expected_result", s.get("expected", "Success")),
                        fallback=s.get("fallback")
                    )
                    steps.append(step)
                except Exception as step_error:
                    logger.warning(f"Error parsing step {i}: {step_error}, raw: {s}")
                    continue

            if not steps:
                logger.warning("No valid steps parsed from Kimi K2 plan")
                return None

            plan = TaskPlan(
                task_id=task_id,
                original_prompt=prompt,
                summary=plan_data.get("summary", "Execute task"),
                steps=steps,
                estimated_iterations=plan_data.get("estimated_iterations", len(steps)),
                potential_blockers=plan_data.get("potential_blockers", []),
                success_criteria=plan_data.get("success_criteria", "Task completed successfully")
            )

            logger.info(f"Kimi K2 created plan: {plan.summary} ({len(steps)} steps)")
            return plan

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Kimi K2 plan response: {e}")
            return None
        except Exception as e:
            import traceback
            logger.error(f"Kimi K2 planning failed: {e}")
            logger.debug(f"Traceback: {traceback.format_exc()}")
            return None

    async def plan_hierarchical(
        self,
        prompt: str,
        available_tools: List[str],
        context: str = "",
        max_steps: int = 300,
        chunk_size: int = 100
    ) -> Optional[List['TaskPlan']]:
        """
        Plan very large tasks (100-300+ steps) using hierarchical decomposition.

        For tasks requiring many steps, this method:
        1. Creates a high-level plan with macro steps (phases)
        2. For each macro step, creates detailed sub-plans

        This allows planning 300+ step workflows within token limits.

        Args:
            prompt: User task description
            available_tools: List of available tool names
            context: Optional context from previous actions
            max_steps: Maximum total steps (default 300)
            chunk_size: Steps per sub-plan (default 100)

        Returns:
            List of TaskPlan objects, one per phase
        """
        # Check if this is actually a large task
        if not await self._is_complex_task(prompt):
            # For simple tasks, use regular planning
            plan = await self.plan_task(prompt, available_tools, context)
            return [plan] if plan else None

        logger.info(f"Using hierarchical planning for complex task (max {max_steps} steps)")

        # Phase 1: Create macro plan (high-level phases)
        macro_system = f"""You are Kimi K2, a strategic AI planner. Create a HIGH-LEVEL plan that breaks this complex task into 3-5 major PHASES.

Each phase should be:
- A logical chunk of work that can be executed independently
- Roughly equal in scope (target {chunk_size} detailed steps per phase)
- Clear enough to be expanded into detailed steps later

Available tools for reference: {', '.join(available_tools[:15])}

Respond with JSON only:
{{
    "task_summary": "Overall task description",
    "total_estimated_steps": <number>,
    "phases": [
        {{
            "phase_number": 1,
            "name": "Phase name",
            "description": "What this phase accomplishes",
            "estimated_steps": <number>,
            "key_actions": ["action1", "action2"],
            "success_criteria": "How to know phase is complete"
        }}
    ]
}}"""

        try:
            macro_response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": macro_system},
                    {"role": "user", "content": f"TASK: {prompt}\n\n{f'CONTEXT: {context}' if context else ''}"}
                ],
                temperature=0.3,
                max_tokens=2048,
            )

            self._track_usage(
                macro_response.usage.prompt_tokens,
                macro_response.usage.completion_tokens,
                call_type="planning"
            )

            macro_content = macro_response.choices[0].message.content
            if "```json" in macro_content:
                macro_content = macro_content.split("```json")[1].split("```")[0]
            elif "```" in macro_content:
                macro_content = macro_content.split("```")[1].split("```")[0]

            macro_plan = json.loads(macro_content.strip())
            phases = macro_plan.get("phases", [])

            if not phases:
                logger.warning("No phases in macro plan, falling back to regular planning")
                plan = await self.plan_task(prompt, available_tools, context)
                return [plan] if plan else None

            logger.info(f"Created macro plan with {len(phases)} phases, ~{macro_plan.get('total_estimated_steps', 'unknown')} total steps")

            # Phase 2: Expand each phase into detailed steps
            all_plans = []
            cumulative_context = context

            for phase in phases:
                phase_prompt = f"""Phase {phase['phase_number']}: {phase['name']}

Description: {phase['description']}

Key actions to accomplish:
{chr(10).join(f'- {a}' for a in phase.get('key_actions', []))}

Success criteria: {phase.get('success_criteria', 'Phase complete')}

Original task context: {prompt[:500]}"""

                # Add results from previous phases to context
                phase_context = cumulative_context
                if all_plans:
                    prev_summary = f"\n\nCompleted phases: {len(all_plans)}"
                    phase_context += prev_summary

                # Plan this phase in detail
                phase_plan = await self.plan_task(
                    phase_prompt,
                    available_tools,
                    phase_context
                )

                if phase_plan:
                    # Tag the plan with phase info
                    phase_plan.summary = f"[Phase {phase['phase_number']}] {phase_plan.summary}"
                    all_plans.append(phase_plan)
                    logger.info(f"Phase {phase['phase_number']} planned: {len(phase_plan.steps)} steps")

            if not all_plans:
                logger.warning("No phase plans created, falling back to regular planning")
                plan = await self.plan_task(prompt, available_tools, context)
                return [plan] if plan else None

            total_steps = sum(len(p.steps) for p in all_plans)
            logger.info(f"Hierarchical planning complete: {len(all_plans)} phases, {total_steps} total steps")

            return all_plans

        except Exception as e:
            logger.error(f"Hierarchical planning failed: {e}, falling back to regular planning")
            plan = await self.plan_task(prompt, available_tools, context)
            return [plan] if plan else None

    async def _is_complex_task(self, prompt: str) -> bool:
        """
        Determine if a task is complex enough to need hierarchical planning.

        Complex tasks typically involve:
        - Multiple distinct phases
        - Many items to process
        - Research + action + reporting cycles
        """
        complexity_keywords = [
            'all', 'every', 'each', 'multiple', 'comprehensive',
            'research and', 'find and', 'extract and', 'compile',
            'list of', 'batch', 'bulk', 'scrape', 'crawl',
            '100', '200', '300', 'hundred', 'thousands'
        ]
        prompt_lower = prompt.lower()
        matches = sum(1 for kw in complexity_keywords if kw in prompt_lower)

        # Also check for explicit step indicators
        if any(x in prompt_lower for x in ['steps', 'phases', 'stages']):
            matches += 2

        return matches >= 2

    async def recover(
        self,
        original_prompt: str,
        current_state: str,
        error: str,
        failed_attempts: List[Dict[str, Any]],
        available_tools: List[str],
    ) -> Optional[Dict[str, Any]]:
        """
        Get recovery guidance when local 7B model fails repeatedly.

        Called only after 2+ consecutive failures - this is the RARE use case.

        Args:
            original_prompt: Original user task
            current_state: Current page/state description
            error: Last error message
            failed_attempts: List of what was tried and why it failed
            available_tools: Available tools

        Returns:
            Recovery plan dict with suggested next steps, or None
        """
        if not self.can_call():
            logger.warning("Cannot call Kimi K2 for recovery - budget or call limit reached")
            return None

        system_prompt = """You are a recovery specialist for an AI browser agent that's stuck.

Analyze the failures and suggest a NEW approach - don't repeat what failed.

AVAILABLE TOOLS: {tools}

OUTPUT FORMAT (JSON):
{{
    "diagnosis": "Why the previous attempts failed",
    "new_approach": "A different strategy to try",
    "recovery_steps": [
        {{
            "tool": "tool_name",
            "arguments": {{}},
            "why": "Why this might work"
        }}
    ],
    "should_abort": false,
    "abort_reason": "Only if task is impossible"
}}"""

        user_prompt = f"""ORIGINAL TASK: {original_prompt}

CURRENT STATE: {current_state}

LAST ERROR: {error}

FAILED ATTEMPTS:
{json.dumps(failed_attempts, indent=2)}

Suggest a recovery strategy."""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt.format(tools=", ".join(available_tools))},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.5,  # Slightly higher for creative recovery
                max_tokens=512,
            )

            # Track usage
            usage = response.usage
            self._track_usage(
                usage.prompt_tokens,
                usage.completion_tokens,
                call_type="recovery"
            )

            # Parse response
            content = response.choices[0].message.content

            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            recovery = json.loads(content.strip())
            logger.info(f"Kimi K2 recovery: {recovery.get('new_approach', 'unknown')}")
            return recovery

        except Exception as e:
            logger.error(f"Kimi K2 recovery failed: {e}")
            return None

    async def close(self):
        """Close the async client."""
        if self._client:
            await self._client.close()
            self._client = None

    def get_usage_report(self, include_costs: bool = False) -> Dict[str, Any]:
        """
        Get current usage statistics.

        Args:
            include_costs: If True, include cost info (for local dev only).
                          If False (default), only show call counts.
        """
        report = {
            "calls_today": self.usage.calls,
            "planning_calls": self.usage.planning_calls,
            "recovery_calls": self.usage.recovery_calls,
            "calls_this_task": self.task_call_count,
            "max_calls_per_task": self.max_calls_per_task,
            "tier": self._user_tier or "unknown",
        }

        # Cost info only for local development (you)
        if include_costs:
            report["today"] = self.usage.to_dict()
            report["budget_remaining"] = round(self.daily_budget - self.usage.total_cost, 4)

        return report


# Global singleton
_kimi_client: Optional[KimiK2Client] = None


def get_kimi_client(config: Optional[Dict] = None) -> KimiK2Client:
    """Get or create the Kimi K2 client singleton."""
    global _kimi_client
    if _kimi_client is None:
        config = config or {}
        kimi_config = config.get("kimi", {})
        _kimi_client = KimiK2Client(
            api_key=kimi_config.get("api_key") or os.getenv("MOONSHOT_API_KEY"),
            base_url=kimi_config.get("base_url", "https://api.moonshot.ai/v1"),
            model=kimi_config.get("model", "kimi-k2-0711-preview"),
            daily_budget_usd=kimi_config.get("daily_budget_usd", 1.0),
            max_calls_per_task=kimi_config.get("max_calls_per_task", 3),
        )
    return _kimi_client


def should_use_kimi_planning(prompt: str, config: Optional[Dict] = None) -> bool:
    """
    Decide if a task warrants Kimi K2 strategic planning.

    Use Kimi for:
    - Complex multi-step tasks
    - Tasks with ambiguous goals
    - Tasks requiring research + action

    Skip Kimi for:
    - Simple single-action tasks
    - Already explicit step-by-step instructions
    """
    config = config or {}

    # Check if Kimi is enabled
    if not config.get("kimi", {}).get("enabled", True):
        return False

    # Skip if no API key/configured provider to avoid slow failures
    try:
        client = get_kimi_client(config)
        if not client.is_available():
            logger.debug("Kimi planning not available (no API key/budget) - will rely on local planner fallback")
    except Exception as e:
        logger.debug(f"Kimi planning availability check failed: {e}")

    # Simple heuristics for task complexity
    prompt_lower = prompt.lower()

    # Keywords suggesting complex tasks (need multi-step execution)
    complex_keywords = [
        "find", "research", "analyze", "compare", "extract",
        "scrape", "collect", "gather", "monitor", "track",
        "leads", "contacts", "emails", "companies", "profiles",
        "facebook ads", "linkedin", "google", "multiple",
        "all", "every", "list of", "export", "csv",
        # Search tasks need multi-step: navigate → fill → submit → extract results
        "search", "search for", "look up", "query",
        # Data extraction tasks
        "get the", "get me", "show me", "titles", "prices", "posts", "questions",
        "top 3", "top 5", "top 10", "first 3", "first 5", "first 10"
    ]

    # Keywords suggesting simple tasks
    simple_keywords = [
        "go to", "click", "type", "screenshot", "describe",
        "what is", "show me", "open"
    ]

    # Count matches
    complex_score = sum(1 for kw in complex_keywords if kw in prompt_lower)
    simple_score = sum(1 for kw in simple_keywords if kw in prompt_lower)

    # Use Kimi planning for:
    # 1. Complex tasks (complex_score > simple_score)
    # 2. OR any task with substantial complexity indicators (complex_score >= 1)
    # 3. AND task is not trivially short (at least 2 words)
    # This ensures planning is used for most real-world tasks
    return (complex_score > simple_score or complex_score >= 1) and len(prompt.split()) >= 2
