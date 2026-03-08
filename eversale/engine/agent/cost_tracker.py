"""
Cost Tracking & Budget Gates

Track LLM token usage and costs in real-time.
Enforce budget limits and auto-downgrade to cheaper models.

Features:
- Per-action token cost estimation
- Cumulative session budget tracking
- Auto-downgrade when budget depletes
- Cost anomaly detection
- Model cost comparison
"""

import asyncio
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
from collections import defaultdict
from enum import Enum
from loguru import logger
import json
from pathlib import Path


class ModelTier(Enum):
    """Model tiers by cost"""
    PREMIUM = "premium"  # GPT-4, Claude Opus
    STANDARD = "standard"  # GPT-3.5, Claude Sonnet
    ECONOMY = "economy"  # Local LLMs, Claude Haiku
    FREE = "free"  # Cached responses


@dataclass
class ModelPricing:
    """Pricing for a model (per 1M tokens)"""
    name: str
    tier: ModelTier
    input_cost: float  # $ per 1M input tokens
    output_cost: float  # $ per 1M output tokens
    context_limit: int  # Max context window

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Estimate cost for token usage"""
        input_cost = (input_tokens / 1_000_000) * self.input_cost
        output_cost = (output_tokens / 1_000_000) * self.output_cost
        return input_cost + output_cost


# Model pricing database (December 2024 prices)
MODEL_PRICING = {
    # OpenAI
    'gpt-4-turbo': ModelPricing('gpt-4-turbo', ModelTier.PREMIUM, 10.0, 30.0, 128000),
    'gpt-4o': ModelPricing('gpt-4o', ModelTier.PREMIUM, 5.0, 15.0, 128000),
    'gpt-4o-mini': ModelPricing('gpt-4o-mini', ModelTier.STANDARD, 0.15, 0.6, 128000),
    'gpt-3.5-turbo': ModelPricing('gpt-3.5-turbo', ModelTier.STANDARD, 0.5, 1.5, 16000),

    # Anthropic
    'claude-3-opus': ModelPricing('claude-3-opus', ModelTier.PREMIUM, 15.0, 75.0, 200000),
    'claude-3-sonnet': ModelPricing('claude-3-sonnet', ModelTier.STANDARD, 3.0, 15.0, 200000),
    'claude-3-haiku': ModelPricing('claude-3-haiku', ModelTier.ECONOMY, 0.25, 1.25, 200000),
    'claude-3.5-sonnet': ModelPricing('claude-3.5-sonnet', ModelTier.STANDARD, 3.0, 15.0, 200000),

    # Local/Free
    'ollama': ModelPricing('ollama', ModelTier.FREE, 0, 0, 8000),
    'local': ModelPricing('local', ModelTier.FREE, 0, 0, 4000),
    'cached': ModelPricing('cached', ModelTier.FREE, 0, 0, 0),
}


@dataclass
class TokenUsage:
    """Token usage for a single operation"""
    input_tokens: int
    output_tokens: int
    model: str
    operation: str
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def cost(self) -> float:
        if self.model in MODEL_PRICING:
            return MODEL_PRICING[self.model].estimate_cost(
                self.input_tokens, self.output_tokens
            )
        return 0.0


@dataclass
class BudgetConfig:
    """Budget configuration"""
    session_budget: float = 1.0  # $ per session
    daily_budget: float = 10.0  # $ per day
    per_task_budget: float = 0.50  # $ per task
    warning_threshold: float = 0.8  # Warn at 80% budget
    auto_downgrade: bool = True  # Auto-switch to cheaper models
    hard_limit: bool = False  # If True, block operations over budget


class CostTracker:
    """
    Track and enforce LLM costs.

    Usage:
        tracker = CostTracker(session_budget=1.0)

        # Check before operation
        if tracker.can_afford(estimated_tokens=2000, model='gpt-4o'):
            result = await llm_call()
            tracker.record_usage(input_tokens=1500, output_tokens=500, model='gpt-4o')

        # Or use the gate decorator
        @tracker.cost_gate(max_cost=0.10)
        async def expensive_operation():
            ...
    """

    def __init__(self, config: BudgetConfig = None, storage_path: Path = None):
        self.config = config or BudgetConfig()
        self.storage_path = storage_path or Path("memory/cost_tracking.json")

        # Current session tracking
        self.session_start = datetime.now()
        self.session_usage: List[TokenUsage] = []

        # Historical data
        self.daily_costs: Dict[str, float] = defaultdict(float)  # date -> cost

        # Model downgrade chain
        self.downgrade_chain = {
            'gpt-4-turbo': 'gpt-4o',
            'gpt-4o': 'gpt-4o-mini',
            'gpt-4o-mini': 'gpt-3.5-turbo',
            'gpt-3.5-turbo': 'ollama',
            'claude-3-opus': 'claude-3.5-sonnet',
            'claude-3.5-sonnet': 'claude-3-sonnet',
            'claude-3-sonnet': 'claude-3-haiku',
            'claude-3-haiku': 'ollama',
        }

        # Stats
        self.stats = {
            'total_input_tokens': 0,
            'total_output_tokens': 0,
            'total_cost': 0.0,
            'operations_count': 0,
            'downgrades_triggered': 0,
            'operations_blocked': 0,
        }

        # Load historical data
        self._load()

    def _load(self):
        """Load historical cost data"""
        if self.storage_path.exists():
            try:
                with open(self.storage_path) as f:
                    data = json.load(f)
                self.daily_costs = defaultdict(float, data.get('daily_costs', {}))
                logger.debug(f"[COST] Loaded {len(self.daily_costs)} days of cost history")
            except Exception as e:
                logger.warning(f"[COST] Failed to load history: {e}")

    def _save(self):
        """Save cost data"""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            'daily_costs': dict(self.daily_costs),
            'updated': datetime.now().isoformat()
        }
        with open(self.storage_path, 'w') as f:
            json.dump(data, f, indent=2)

    @property
    def session_cost(self) -> float:
        """Total cost for current session"""
        return sum(u.cost for u in self.session_usage)

    @property
    def today_cost(self) -> float:
        """Total cost for today"""
        today = datetime.now().strftime('%Y-%m-%d')
        return self.daily_costs[today] + self.session_cost

    @property
    def budget_remaining(self) -> float:
        """Remaining session budget"""
        return max(0, self.config.session_budget - self.session_cost)

    @property
    def budget_percent_used(self) -> float:
        """Percentage of session budget used"""
        if self.config.session_budget <= 0:
            return 0
        return (self.session_cost / self.config.session_budget) * 100

    def estimate_cost(
        self,
        input_tokens: int,
        output_tokens: int = None,
        model: str = 'gpt-4o'
    ) -> float:
        """Estimate cost for an operation"""
        output_tokens = output_tokens or int(input_tokens * 0.3)  # Estimate 30% output

        if model in MODEL_PRICING:
            return MODEL_PRICING[model].estimate_cost(input_tokens, output_tokens)
        return 0.0

    def can_afford(
        self,
        estimated_input_tokens: int,
        estimated_output_tokens: int = None,
        model: str = 'gpt-4o'
    ) -> bool:
        """Check if we can afford an operation within budget"""
        estimated_cost = self.estimate_cost(
            estimated_input_tokens,
            estimated_output_tokens,
            model
        )

        # Check session budget
        if self.session_cost + estimated_cost > self.config.session_budget:
            if self.config.hard_limit:
                return False
            # Soft limit - just warn
            if self.budget_percent_used >= self.config.warning_threshold * 100:
                logger.warning(f"[COST] Budget warning: {self.budget_percent_used:.1f}% used")

        # Check daily budget
        if self.today_cost + estimated_cost > self.config.daily_budget:
            logger.warning(f"[COST] Daily budget exceeded: ${self.today_cost:.4f} / ${self.config.daily_budget}")
            if self.config.hard_limit:
                return False

        return True

    def get_affordable_model(
        self,
        preferred_model: str,
        estimated_tokens: int
    ) -> str:
        """Get the best affordable model, downgrading if necessary"""
        model = preferred_model

        while model in self.downgrade_chain:
            cost = self.estimate_cost(estimated_tokens, model=model)

            if self.session_cost + cost <= self.config.session_budget:
                return model

            # Try cheaper model
            next_model = self.downgrade_chain.get(model)
            if next_model:
                logger.info(f"[COST] Downgrading {model} -> {next_model} (budget: ${self.budget_remaining:.4f})")
                self.stats['downgrades_triggered'] += 1
                model = next_model
            else:
                break

        return model

    def record_usage(
        self,
        input_tokens: int,
        output_tokens: int,
        model: str,
        operation: str = "llm_call"
    ):
        """Record actual token usage"""
        usage = TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=model,
            operation=operation
        )

        self.session_usage.append(usage)

        # Update stats
        self.stats['total_input_tokens'] += input_tokens
        self.stats['total_output_tokens'] += output_tokens
        self.stats['total_cost'] += usage.cost
        self.stats['operations_count'] += 1

        # Update daily costs
        today = datetime.now().strftime('%Y-%m-%d')
        self.daily_costs[today] += usage.cost

        # Log significant costs
        if usage.cost > 0.01:
            logger.info(f"[COST] {operation}: {usage.total_tokens} tokens = ${usage.cost:.4f} ({model})")

        # Check for cost anomaly
        self._check_anomaly(usage)

        # Periodic save
        if self.stats['operations_count'] % 10 == 0:
            self._save()

    def _check_anomaly(self, usage: TokenUsage):
        """Detect cost anomalies"""
        if len(self.session_usage) < 5:
            return

        # Calculate average cost for this operation type
        similar = [u for u in self.session_usage[:-1] if u.operation == usage.operation]
        if len(similar) < 3:
            return

        avg_cost = sum(u.cost for u in similar) / len(similar)

        # Flag if 5x more expensive than average
        if usage.cost > avg_cost * 5 and usage.cost > 0.01:
            logger.warning(f"[COST ANOMALY] {usage.operation} cost ${usage.cost:.4f} vs avg ${avg_cost:.4f}")

    def cost_gate(
        self,
        max_cost: float = None,
        model: str = None
    ):
        """
        Decorator that enforces cost limits on a function.

        Usage:
            @tracker.cost_gate(max_cost=0.10)
            async def expensive_operation():
                ...
        """
        def decorator(func):
            async def wrapper(*args, **kwargs):
                # Check budget
                if not self.can_afford(estimated_input_tokens=5000, model=model or 'gpt-4o'):
                    if self.config.hard_limit:
                        self.stats['operations_blocked'] += 1
                        raise BudgetExceededError(
                            f"Operation blocked: budget ${self.budget_remaining:.4f} remaining"
                        )

                return await func(*args, **kwargs)
            return wrapper
        return decorator

    def get_summary(self) -> Dict:
        """Get cost summary"""
        return {
            'session': {
                'cost': round(self.session_cost, 4),
                'budget': self.config.session_budget,
                'remaining': round(self.budget_remaining, 4),
                'percent_used': round(self.budget_percent_used, 1),
                'operations': len(self.session_usage),
            },
            'today': {
                'cost': round(self.today_cost, 4),
                'budget': self.config.daily_budget,
            },
            'tokens': {
                'input': self.stats['total_input_tokens'],
                'output': self.stats['total_output_tokens'],
                'total': self.stats['total_input_tokens'] + self.stats['total_output_tokens'],
            },
            'stats': self.stats
        }

    def get_cost_breakdown(self) -> Dict[str, float]:
        """Get cost breakdown by model"""
        breakdown = defaultdict(float)
        for usage in self.session_usage:
            breakdown[usage.model] += usage.cost
        return dict(breakdown)

    def reset_session(self):
        """Reset session tracking (keeps daily totals)"""
        # Save current session to daily
        today = datetime.now().strftime('%Y-%m-%d')
        self.daily_costs[today] += self.session_cost
        self._save()

        # Reset
        self.session_start = datetime.now()
        self.session_usage.clear()
        logger.info("[COST] Session reset")


class BudgetExceededError(Exception):
    """Raised when budget is exceeded and hard limit is enabled"""
    pass


# Singleton
_tracker: Optional[CostTracker] = None

def get_cost_tracker(config: BudgetConfig = None) -> CostTracker:
    """Get or create the global cost tracker"""
    global _tracker
    if _tracker is None:
        _tracker = CostTracker(config)
    return _tracker


# Convenience function
def estimate_llm_cost(prompt: str, model: str = 'gpt-4o') -> float:
    """Quick estimate of LLM cost for a prompt"""
    # Rough token estimate: 1 token ~= 4 characters
    input_tokens = len(prompt) // 4
    output_tokens = input_tokens // 3  # Assume 1/3 output

    tracker = get_cost_tracker()
    return tracker.estimate_cost(input_tokens, output_tokens, model)
