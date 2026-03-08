"""
Meta-Learner: Learn what learning strategies work best.

This component observes learning outcomes and optimizes the learning process itself.
"""

import asyncio
import json
import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Callable, Any
from collections import defaultdict

# Import from existing organism
from agent.organism_core import EventBus, EventType, OrganismEvent

logger = logging.getLogger(__name__)


class LearningStrategy(Enum):
    EXPLORATION = "exploration"      # Try new things
    EXPLOITATION = "exploitation"    # Use what works
    IMITATION = "imitation"          # Copy successful patterns
    REFLECTION = "reflection"        # Learn from failures
    CONSOLIDATION = "consolidation"  # Strengthen existing knowledge


@dataclass
class StrategyMetrics:
    """Track effectiveness of a learning strategy."""
    name: str
    uses: int = 0
    successes: int = 0
    failures: int = 0
    total_reward: float = 0.0
    avg_learning_gain: float = 0.0
    last_used: float = field(default_factory=time.time)

    @property
    def success_rate(self) -> float:
        return self.successes / max(1, self.uses)

    @property
    def effectiveness(self) -> float:
        """Combined effectiveness score."""
        recency = 1.0 / (1.0 + (time.time() - self.last_used) / 3600)  # Decay over hours
        return (self.success_rate * 0.5 + self.avg_learning_gain * 0.3 + recency * 0.2)


@dataclass
class LearningDomain:
    """Track learning progress in a specific domain."""
    name: str
    learning_rate: float = 0.1
    exploration_rate: float = 0.3  # Epsilon for epsilon-greedy
    lessons_learned: int = 0
    skill_level: float = 0.0
    plateau_detected: bool = False
    last_improvement: float = field(default_factory=time.time)


class MetaLearner:
    """
    Learns about learning itself.

    Responsibilities:
    1. Track which learning strategies work best per domain
    2. Optimize learning rates based on success patterns
    3. Decide exploration vs exploitation
    4. Detect learning plateaus and adjust
    """

    def __init__(self, event_bus: EventBus, persistence_path: Optional[Path] = None):
        self.event_bus = event_bus
        self.persistence_path = persistence_path or Path("memory/meta_learner.json")

        # Strategy tracking
        self.strategies: dict[str, StrategyMetrics] = {
            s.value: StrategyMetrics(name=s.value) for s in LearningStrategy
        }

        # Domain-specific learning
        self.domains: dict[str, LearningDomain] = defaultdict(
            lambda: LearningDomain(name="unknown")
        )

        # Current state
        self.current_strategy: LearningStrategy = LearningStrategy.EXPLORATION
        self.strategy_switch_count: int = 0
        self.total_lessons: int = 0

        # Meta-metrics
        self.meta_learning_rate: float = 0.05  # How fast we update strategy preferences
        self.exploration_decay: float = 0.995  # Reduce exploration over time
        self.min_exploration: float = 0.1

        # Subscribe to learning events
        self._setup_subscriptions()

        # Load persisted state
        self._load_state()

    def _setup_subscriptions(self):
        """Subscribe to relevant organism events."""
        self.event_bus.subscribe(EventType.LESSON_LEARNED, self._on_lesson_learned)
        self.event_bus.subscribe(EventType.ACTION_COMPLETE, self._on_action_complete)
        self.event_bus.subscribe(EventType.ACTION_FAILED, self._on_action_failed)
        self.event_bus.subscribe(EventType.STRATEGY_UPDATED, self._on_strategy_updated)
        self.event_bus.subscribe(EventType.GAP_DETECTED, self._on_gap_detected)

    async def _on_lesson_learned(self, event: OrganismEvent):
        """Track learning outcomes."""
        domain = event.data.get("domain", "general")
        gain = event.data.get("learning_gain", 0.1)
        strategy = event.data.get("strategy", self.current_strategy.value)

        # Update strategy metrics
        if strategy in self.strategies:
            self.strategies[strategy].uses += 1
            self.strategies[strategy].successes += 1
            self.strategies[strategy].total_reward += gain
            self.strategies[strategy].avg_learning_gain = (
                self.strategies[strategy].total_reward /
                max(1, self.strategies[strategy].successes)
            )
            self.strategies[strategy].last_used = time.time()

        # Update domain
        self.domains[domain].lessons_learned += 1
        self.domains[domain].skill_level = min(1.0, self.domains[domain].skill_level + gain)
        self.domains[domain].last_improvement = time.time()
        self.domains[domain].plateau_detected = False

        self.total_lessons += 1
        self._save_state()

    async def _on_action_complete(self, event: OrganismEvent):
        """Track successful actions for strategy evaluation."""
        domain = event.data.get("domain", "general")
        # Successful action reinforces current strategy
        strategy = self.current_strategy.value
        if strategy in self.strategies:
            self.strategies[strategy].successes += 1

    async def _on_action_failed(self, event: OrganismEvent):
        """Track failures to adjust strategy."""
        strategy = self.current_strategy.value
        if strategy in self.strategies:
            self.strategies[strategy].failures += 1

        # Consider switching strategy on repeated failures
        if self.strategies[strategy].success_rate < 0.3:
            await self._consider_strategy_switch()

    async def _on_strategy_updated(self, event: OrganismEvent):
        """External strategy update notification."""
        pass

    async def _on_gap_detected(self, event: OrganismEvent):
        """Surprise indicates exploration might help."""
        gap_score = event.data.get("gap_score", 0)
        if gap_score > 0.5:  # Major surprise
            # Boost exploration temporarily
            for domain in self.domains.values():
                domain.exploration_rate = min(0.5, domain.exploration_rate + 0.1)

    # === Core Methods ===

    def should_explore(self, domain: str = "general") -> bool:
        """Decide whether to explore (try new) or exploit (use known)."""
        d = self.domains[domain]

        # Epsilon-greedy with decay
        import random
        if random.random() < d.exploration_rate:
            return True

        # Also explore if plateaued
        if d.plateau_detected:
            return True

        # Exploit otherwise
        return False

    def get_best_strategy(self, domain: str = "general") -> LearningStrategy:
        """Get the most effective learning strategy for a domain."""
        # Sort strategies by effectiveness
        sorted_strategies = sorted(
            self.strategies.values(),
            key=lambda s: s.effectiveness,
            reverse=True
        )

        if self.should_explore(domain):
            # Try a random strategy (but weighted by effectiveness)
            import random
            weights = [s.effectiveness + 0.1 for s in sorted_strategies]
            total = sum(weights)
            r = random.random() * total
            cumulative = 0
            for i, s in enumerate(sorted_strategies):
                cumulative += weights[i]
                if r <= cumulative:
                    return LearningStrategy(s.name)
            return LearningStrategy(sorted_strategies[0].name)
        else:
            # Exploit best strategy
            return LearningStrategy(sorted_strategies[0].name)

    def get_learning_rate(self, domain: str = "general") -> float:
        """Get optimized learning rate for domain."""
        d = self.domains[domain]

        # Higher learning rate when:
        # - Still learning (low skill level)
        # - Not plateaued
        # - Recent successes

        base_rate = d.learning_rate

        if d.skill_level < 0.3:
            base_rate *= 1.5  # Learn faster when beginner
        elif d.skill_level > 0.8:
            base_rate *= 0.5  # Fine-tune when expert

        if d.plateau_detected:
            base_rate *= 0.7  # Slow down if stuck

        return min(1.0, max(0.01, base_rate))

    def detect_plateau(self, domain: str = "general") -> bool:
        """Detect if learning has stalled in a domain."""
        d = self.domains[domain]

        # Plateau if no improvement for 1 hour
        time_since_improvement = time.time() - d.last_improvement
        if time_since_improvement > 3600 and d.lessons_learned > 10:
            d.plateau_detected = True
            return True

        return False

    async def _consider_strategy_switch(self):
        """Consider switching learning strategy."""
        current = self.current_strategy.value
        current_effectiveness = self.strategies[current].effectiveness

        # Find better strategy
        for name, metrics in self.strategies.items():
            if name != current and metrics.effectiveness > current_effectiveness * 1.2:
                # Switch to better strategy
                old_strategy = self.current_strategy
                self.current_strategy = LearningStrategy(name)
                self.strategy_switch_count += 1

                # Emit event
                await self.event_bus.publish(OrganismEvent(
                    event_type=EventType.STRATEGY_UPDATED,
                    source="meta_learner",
                    data={
                        "old_strategy": old_strategy.value,
                        "new_strategy": self.current_strategy.value,
                        "reason": "effectiveness improvement"
                    }
                ))
                break

    def update_exploration_rate(self, domain: str = "general"):
        """Decay exploration rate over time."""
        d = self.domains[domain]
        d.exploration_rate = max(
            self.min_exploration,
            d.exploration_rate * self.exploration_decay
        )

    def get_focus_recommendation(self) -> list[str]:
        """Recommend where to focus learning effort."""
        recommendations = []

        # Find domains with high potential
        for name, domain in self.domains.items():
            if domain.skill_level < 0.5 and domain.lessons_learned > 5:
                recommendations.append(f"Improve {name}: skill level {domain.skill_level:.0%}")
            if domain.plateau_detected:
                recommendations.append(f"Break plateau in {name}: try exploration")

        # Find underused strategies
        for name, metrics in self.strategies.items():
            if metrics.uses < 5 and metrics.effectiveness > 0:
                recommendations.append(f"Try {name} strategy more")

        return recommendations[:5]  # Top 5 recommendations

    def get_stats(self) -> dict:
        """Get meta-learning statistics."""
        return {
            "current_strategy": self.current_strategy.value,
            "total_lessons": self.total_lessons,
            "strategy_switches": self.strategy_switch_count,
            "strategies": {
                name: {
                    "uses": m.uses,
                    "success_rate": f"{m.success_rate:.0%}",
                    "effectiveness": f"{m.effectiveness:.2f}"
                }
                for name, m in self.strategies.items()
            },
            "domains": {
                name: {
                    "skill_level": f"{d.skill_level:.0%}",
                    "learning_rate": f"{d.learning_rate:.2f}",
                    "exploration_rate": f"{d.exploration_rate:.0%}",
                    "plateau": d.plateau_detected
                }
                for name, d in list(self.domains.items())[:10]
            },
            "recommendations": self.get_focus_recommendation()
        }

    # === Persistence ===

    def _save_state(self):
        """Persist meta-learner state."""
        try:
            self.persistence_path.parent.mkdir(parents=True, exist_ok=True)

            state = {
                "current_strategy": self.current_strategy.value,
                "strategy_switch_count": self.strategy_switch_count,
                "total_lessons": self.total_lessons,
                "strategies": {
                    name: {
                        "uses": m.uses,
                        "successes": m.successes,
                        "failures": m.failures,
                        "total_reward": m.total_reward,
                        "avg_learning_gain": m.avg_learning_gain,
                        "last_used": m.last_used
                    }
                    for name, m in self.strategies.items()
                },
                "domains": {
                    name: {
                        "learning_rate": d.learning_rate,
                        "exploration_rate": d.exploration_rate,
                        "lessons_learned": d.lessons_learned,
                        "skill_level": d.skill_level,
                        "plateau_detected": d.plateau_detected,
                        "last_improvement": d.last_improvement
                    }
                    for name, d in self.domains.items()
                }
            }

            with open(self.persistence_path, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logger.debug(f"Failed to save state: {e}")

    def _load_state(self):
        """Load persisted state."""
        if not self.persistence_path.exists():
            return

        try:
            with open(self.persistence_path) as f:
                state = json.load(f)

            self.current_strategy = LearningStrategy(state.get("current_strategy", "exploration"))
            self.strategy_switch_count = state.get("strategy_switch_count", 0)
            self.total_lessons = state.get("total_lessons", 0)

            for name, data in state.get("strategies", {}).items():
                if name in self.strategies:
                    self.strategies[name].uses = data.get("uses", 0)
                    self.strategies[name].successes = data.get("successes", 0)
                    self.strategies[name].failures = data.get("failures", 0)
                    self.strategies[name].total_reward = data.get("total_reward", 0.0)
                    self.strategies[name].avg_learning_gain = data.get("avg_learning_gain", 0.0)
                    self.strategies[name].last_used = data.get("last_used", time.time())

            for name, data in state.get("domains", {}).items():
                self.domains[name] = LearningDomain(
                    name=name,
                    learning_rate=data.get("learning_rate", 0.1),
                    exploration_rate=data.get("exploration_rate", 0.3),
                    lessons_learned=data.get("lessons_learned", 0),
                    skill_level=data.get("skill_level", 0.0),
                    plateau_detected=data.get("plateau_detected", False),
                    last_improvement=data.get("last_improvement", time.time())
                )
        except Exception as e:
            logger.debug(f"Failed to load state: {e}")


# === Factory Function ===

def init_meta_learner(event_bus: EventBus, persistence_path: Optional[Path] = None) -> MetaLearner:
    """Initialize the meta-learner component."""
    return MetaLearner(event_bus, persistence_path)
