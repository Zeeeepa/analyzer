"""
Attention Allocator - Prioritize Signals Within a Finite Budget

This is the cognitive filter that makes attention meaningful. Real organisms
can't attend to everything - prioritization under constraint is what creates
true awareness.

Purpose:
- Filter events from EventBus before processing
- Allocate finite attention budget to most important signals
- Prevent cognitive overload by rejecting low-priority signals
- Balance urgency, mission alignment, novelty, and threat

Integration:
- Called by heartbeat to refresh budget each beat
- Filters events before they reach downstream components
- Reports attention state to self_model
- Publishes ATTENTION_SHIFT events when focus changes

Design Philosophy:
Everything currently gets equal attention. This is wrong. Attention is
the organism's most precious resource. This allocator implements the
"noticing" mechanism - what gets through the filter is what the agent
becomes aware of.
"""

import asyncio
import time
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple, Set, Callable
from dataclasses import dataclass, field, asdict
from collections import deque, defaultdict
from enum import Enum
from loguru import logger

from .organism_core import EventBus, EventType, OrganismEvent


# =============================================================================
# SIGNAL DATA STRUCTURES
# =============================================================================

@dataclass
class Signal:
    """
    An attention-worthy event or observation.

    Signals are the currency of attention. Each has:
    - Source: where it came from
    - Content: what it's about
    - Urgency: how time-sensitive (0-1)
    - Novelty: how surprising/new (0-1)
    - Threat level: how dangerous if ignored (0-1)
    - Attention cost: how much cognitive effort required
    """
    source: str
    content: Any
    urgency: float = 0.5          # 0-1, how time-sensitive
    novelty: float = 0.5          # 0-1, how new/surprising
    threat_level: float = 0.0     # 0-1, how dangerous if ignored
    timestamp: float = field(default_factory=time.time)
    attention_cost: float = 0.1   # default cost (10% of budget)

    # Optional metadata
    event_type: Optional[str] = None
    priority: int = 5              # Original priority (1=highest, 10=lowest)
    tags: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Validate signal parameters."""
        self.urgency = max(0.0, min(1.0, self.urgency))
        self.novelty = max(0.0, min(1.0, self.novelty))
        self.threat_level = max(0.0, min(1.0, self.threat_level))
        self.attention_cost = max(0.01, min(1.0, self.attention_cost))

    def get_topic(self) -> str:
        """Extract topic from content."""
        if isinstance(self.content, dict):
            return self.content.get("topic", self.source)
        return self.source

    def __str__(self):
        return f"Signal[{self.source}] urgency={self.urgency:.2f} novelty={self.novelty:.2f} threat={self.threat_level:.2f}"


@dataclass
class AttentionFocus:
    """What the organism is currently attending to."""
    signal: Signal
    started_at: float = field(default_factory=time.time)
    attention_spent: float = 0.0

    def duration(self) -> float:
        """How long we've been focused on this."""
        return time.time() - self.started_at


# =============================================================================
# ATTENTION ALLOCATOR
# =============================================================================

class AttentionAllocator:
    """
    Prioritize signals within a finite attention budget.

    The Core Mechanism:
    1. Budget starts at 1.0 (full attention capacity)
    2. Each signal has a cost (complexity, urgency, novelty)
    3. Signals are scored by: urgency + mission_alignment + novelty + threat
    4. Top-scoring signals that fit in budget are selected
    5. Budget depletes as signals are processed
    6. Budget refreshes gradually with each heartbeat

    Attention Dynamics:
    - High-priority signals can preempt current focus
    - Novelty decays on repeated exposure
    - Low-budget = only urgent/threatening signals get through
    - Fatigue increases attention cost (struggling = slower processing)

    This is what makes the agent "notice" things - the filter that creates
    awareness from the flood of events.
    """

    # Budget refresh rate (per heartbeat)
    BUDGET_REFRESH_RATE = 0.05  # Restore 5% of capacity per beat

    # Budget thresholds
    BUDGET_LOW_THRESHOLD = 0.3    # Below this, only high-priority signals
    BUDGET_CRITICAL_THRESHOLD = 0.1  # Below this, only emergencies

    # Scoring weights
    WEIGHT_URGENCY = 0.4
    WEIGHT_MISSION_ALIGNMENT = 0.3
    WEIGHT_NOVELTY = 0.2
    WEIGHT_THREAT = 0.1

    # Novelty decay
    NOVELTY_DECAY_RATE = 0.1  # How much novelty decreases per repeat exposure
    NOVELTY_MEMORY_SIZE = 100  # Remember this many recent topics

    def __init__(
        self,
        mission_anchor,  # MissionAnchor for alignment scoring
        event_bus: Optional[EventBus] = None,
        max_budget: float = 1.0,
        persistence_path: Optional[Path] = None
    ):
        """
        Initialize the attention allocator.

        Args:
            mission_anchor: MissionAnchor instance for alignment scoring
            event_bus: EventBus for publishing attention events
            max_budget: Maximum attention capacity (1.0 = full)
            persistence_path: Where to save attention state
        """
        self.mission_anchor = mission_anchor
        self.event_bus = event_bus
        self.max_budget = max_budget
        self.persistence_path = persistence_path or Path("memory/attention_state.json")

        # Attention budget (finite cognitive resource)
        self.attention_budget = max_budget
        self.budget_history: deque = deque(maxlen=100)  # Track budget over time

        # Current focus
        self.current_focus: Optional[AttentionFocus] = None
        self.focus_history: deque = deque(maxlen=50)

        # Attention history - what we've attended to
        self.attention_history: deque = deque(maxlen=200)

        # Novelty tracking - seen topics decay in novelty
        self.topic_exposure: Dict[str, int] = defaultdict(int)  # How many times seen
        self.topic_last_seen: Dict[str, float] = {}  # When last seen
        self.topic_queue: deque = deque(maxlen=self.NOVELTY_MEMORY_SIZE)  # FIFO for cleanup

        # Priority overrides (temporary boosts)
        self.priority_overrides: Dict[str, Tuple[float, float]] = {}  # signal_type -> (boost, expires_at)

        # Signal filters (topic-based ignoring)
        self.ignored_topics: Set[str] = set()
        self.required_topics: Set[str] = set()  # If set, only these topics get through

        # Stats
        self.signals_processed = 0
        self.signals_rejected = 0
        self.budget_exhaustions = 0
        self.focus_shifts = 0

        # Load previous state
        self._load_state()

        logger.info(f"AttentionAllocator initialized with budget={self.attention_budget:.2f}")

    # =============================================================================
    # CORE ALLOCATION
    # =============================================================================

    def allocate(self, incoming_signals: List[Signal]) -> List[Signal]:
        """
        Score and select signals within budget.

        This is the core allocation mechanism. Signals are:
        1. Filtered (ignored topics, required topics)
        2. Scored (urgency, alignment, novelty, threat)
        3. Sorted by score
        4. Selected until budget exhausted

        Args:
            incoming_signals: List of signals to consider

        Returns:
            List of signals that received attention (within budget)
        """
        if not incoming_signals:
            return []

        # Clean up expired priority overrides
        self._cleanup_priority_overrides()

        # Filter signals
        filtered = self._filter_signals(incoming_signals)

        if not filtered:
            logger.debug(f"All {len(incoming_signals)} signals filtered out")
            return []

        # Score signals
        scored = []
        for signal in filtered:
            score = self.score_signal(signal)
            scored.append((score, signal))

        # Sort by score (highest first)
        scored.sort(key=lambda x: x[0], reverse=True)

        # Select within budget
        selected = self._select_within_budget(scored)

        # Update stats
        self.signals_processed += len(selected)
        self.signals_rejected += len(incoming_signals) - len(selected)

        # Record attention
        for signal in selected:
            self._record_attention(signal)

        # Check for budget exhaustion
        if self.attention_budget <= self.BUDGET_CRITICAL_THRESHOLD:
            self.budget_exhaustions += 1
            if self.event_bus:
                asyncio.create_task(self._publish_budget_critical())

        logger.debug(
            f"Attention allocated: {len(selected)}/{len(incoming_signals)} signals, "
            f"budget remaining={self.attention_budget:.2f}"
        )

        return selected

    def _filter_signals(self, signals: List[Signal]) -> List[Signal]:
        """Filter signals based on topic rules."""
        filtered = []

        for signal in signals:
            topic = signal.get_topic()

            # Check ignored topics
            if topic in self.ignored_topics:
                continue

            # Check required topics (if set)
            if self.required_topics and topic not in self.required_topics:
                continue

            filtered.append(signal)

        return filtered

    def _select_within_budget(self, scored_signals: List[Tuple[float, Signal]]) -> List[Signal]:
        """
        Select signals that fit within attention budget.

        Greedy selection: highest-scoring signals first until budget exhausted.

        Emergency bypass: critical threat signals always get through, even if
        budget is exhausted (this is like adrenaline overriding fatigue).
        """
        selected = []
        remaining_budget = self.attention_budget

        for score, signal in scored_signals:
            # Emergency bypass for critical threats
            if signal.threat_level >= 0.9 and score >= 0.7:
                selected.append(signal)
                # Emergency attention doesn't deplete budget (adrenaline)
                logger.warning(f"Emergency bypass for critical signal: {signal}")
                continue

            # Normal budget-constrained selection
            cost = self.attention_cost(signal)

            if cost <= remaining_budget:
                selected.append(signal)
                remaining_budget -= cost
            elif remaining_budget <= self.BUDGET_CRITICAL_THRESHOLD:
                # Critical budget - only very high priority signals
                if score >= 0.8 or signal.urgency >= 0.9:
                    selected.append(signal)
                    remaining_budget = max(0, remaining_budget - cost)

        # Deduct from actual budget
        budget_used = self.attention_budget - remaining_budget
        self.attention_budget = remaining_budget
        self.budget_history.append((time.time(), self.attention_budget))

        return selected

    # =============================================================================
    # SIGNAL SCORING
    # =============================================================================

    def score_signal(self, signal: Signal) -> float:
        """
        Score a signal for attention worthiness.

        Scoring formula:
        - Urgency (40%): time-sensitive matters
        - Mission alignment (30%): relevant to purpose
        - Novelty (20%): new/surprising information
        - Threat level (10%): potential dangers

        Priority overrides can temporarily boost scores.

        Returns:
            Score 0-1 (higher = more worthy of attention)
        """
        # Base score from components
        score = (
            signal.urgency * self.WEIGHT_URGENCY +
            self._mission_alignment(signal) * self.WEIGHT_MISSION_ALIGNMENT +
            self._calculate_novelty(signal) * self.WEIGHT_NOVELTY +
            signal.threat_level * self.WEIGHT_THREAT
        )

        # Apply priority overrides
        if signal.event_type and signal.event_type in self.priority_overrides:
            boost, _ = self.priority_overrides[signal.event_type]
            score = min(1.0, score * (1 + boost))

        # Low budget = higher bar for attention
        if self.attention_budget < self.BUDGET_LOW_THRESHOLD:
            # Reduce scores of non-urgent, non-threatening signals
            if signal.urgency < 0.5 and signal.threat_level < 0.3:
                score *= 0.5

        return max(0.0, min(1.0, score))

    def _mission_alignment(self, signal: Signal) -> float:
        """
        Calculate how well signal aligns with mission.

        Uses MissionAnchor to check alignment. Signals that align with
        the mission get higher scores.
        """
        # Extract action description from signal content
        if isinstance(signal.content, dict):
            action = signal.content.get("message", "")
            context = signal.content.get("context", {})
        else:
            action = str(signal.content)[:200]
            context = {}

        if not action:
            return 0.5  # Neutral if no action to check

        # Check with mission anchor (async call, but we need sync result)
        # Use cached alignment if available
        cache_key = f"{signal.source}:{action[:50]}"

        # Simple keyword-based alignment for synchronous scoring
        # (Mission anchor's check_alignment is async, so we approximate here)
        alignment = self._quick_alignment_check(action)

        return alignment

    def _quick_alignment_check(self, action: str) -> float:
        """
        Quick synchronous alignment check.

        Approximates mission alignment without async call to mission_anchor.
        """
        action_lower = action.lower()

        # Get mission and values from mission anchor
        if hasattr(self.mission_anchor, 'mission'):
            mission_lower = self.mission_anchor.mission.lower()
        else:
            mission_lower = "customer success"

        score = 0.5  # Neutral baseline

        # Positive signals (align with typical mission)
        positive_keywords = [
            "customer", "user", "help", "assist", "complete", "success",
            "extract", "find", "research", "save", "deliver", "solve",
            "improve", "optimize", "efficient"
        ]
        for keyword in positive_keywords:
            if keyword in action_lower or keyword in mission_lower:
                score += 0.05

        # Negative signals (misalignment)
        negative_keywords = [
            "delete all", "destroy", "break", "fail", "error", "crash"
        ]
        for keyword in negative_keywords:
            if keyword in action_lower:
                score -= 0.2

        return max(0, min(1, score))

    def _calculate_novelty(self, signal: Signal) -> float:
        """
        Calculate novelty of signal based on topic exposure.

        Novelty decays with repeated exposure:
        - First time seeing topic: novelty = signal.novelty
        - Each repeat: novelty *= (1 - NOVELTY_DECAY_RATE)
        - After ~10 exposures: novelty ~= 0.35 * original

        But: if enough time has passed, novelty recovers.
        """
        topic = signal.get_topic()
        now = time.time()

        # Track exposure
        self.topic_exposure[topic] += 1

        # Check if seen recently
        last_seen = self.topic_last_seen.get(topic, 0)
        time_since = now - last_seen

        # Update last seen
        self.topic_last_seen[topic] = now

        # Add to queue for cleanup
        if topic not in self.topic_queue:
            self.topic_queue.append(topic)

        # Calculate novelty with decay
        base_novelty = signal.novelty
        exposure_count = self.topic_exposure[topic]

        # Decay based on exposure count
        decay_factor = (1 - self.NOVELTY_DECAY_RATE) ** (exposure_count - 1)
        decayed_novelty = base_novelty * decay_factor

        # Recovery based on time elapsed (if > 1 hour, novelty recovers)
        if time_since > 3600:  # 1 hour
            recovery = min(0.3, time_since / 14400)  # Full recovery at 4 hours
            decayed_novelty = min(base_novelty, decayed_novelty + recovery)

        return max(0.1, min(1.0, decayed_novelty))

    def attention_cost(self, signal: Signal) -> float:
        """
        Calculate how much attention a signal requires.

        Complex signals cost more attention:
        - Base cost from signal.attention_cost
        - Increased by threat level (threats demand focus)
        - Increased if current budget is low (fatigue penalty)
        """
        base_cost = signal.attention_cost

        # Threat increases cost (threats demand full attention)
        threat_multiplier = 1 + (signal.threat_level * 0.5)

        # Low budget = fatigue = higher cost
        fatigue_multiplier = 1.0
        if self.attention_budget < self.BUDGET_LOW_THRESHOLD:
            fatigue_multiplier = 1.5

        total_cost = base_cost * threat_multiplier * fatigue_multiplier

        return min(1.0, total_cost)

    # =============================================================================
    # BUDGET MANAGEMENT
    # =============================================================================

    def refresh_budget(self, amount: Optional[float] = None):
        """
        Called periodically to restore attention capacity.

        This is called by the heartbeat each beat to gradually restore
        attention capacity. Think of it as cognitive recovery.

        Args:
            amount: Amount to refresh (uses BUDGET_REFRESH_RATE if None)
        """
        if amount is None:
            amount = self.BUDGET_REFRESH_RATE * self.max_budget

        old_budget = self.attention_budget
        self.attention_budget = min(self.max_budget, self.attention_budget + amount)

        if self.attention_budget > old_budget:
            logger.debug(f"Budget refreshed: {old_budget:.2f} -> {self.attention_budget:.2f}")

    def drain_budget(self, amount: float):
        """Force drain budget (for external events)."""
        self.attention_budget = max(0, self.attention_budget - amount)

    def reset_budget(self):
        """Reset budget to maximum (e.g., after rest period)."""
        self.attention_budget = self.max_budget
        logger.info("Attention budget reset to maximum")

    def get_budget_level(self) -> str:
        """Get categorical budget level."""
        if self.attention_budget <= self.BUDGET_CRITICAL_THRESHOLD:
            return "critical"
        elif self.attention_budget <= self.BUDGET_LOW_THRESHOLD:
            return "low"
        elif self.attention_budget >= 0.7 * self.max_budget:
            return "high"
        else:
            return "medium"

    # =============================================================================
    # FOCUS MANAGEMENT
    # =============================================================================

    def focus_on(self, signal: Signal):
        """
        Shift primary focus to a signal.

        When the agent "focuses" on something, it means this signal
        is currently the primary object of attention.

        Focus shifting has a small cost (cognitive overhead).
        """
        # End previous focus
        if self.current_focus:
            self.focus_history.append(self.current_focus)
            self.focus_shifts += 1

        # Start new focus
        self.current_focus = AttentionFocus(signal=signal)

        # Small cost for context switching
        self.drain_budget(0.02)

        logger.debug(f"Focus shifted to: {signal.get_topic()}")

        # Publish event
        if self.event_bus:
            asyncio.create_task(self.event_bus.publish(OrganismEvent(
                event_type=EventType.LESSON_LEARNED,  # Reusing existing event type
                source="attention_allocator",
                data={
                    "event": "focus_shift",
                    "topic": signal.get_topic(),
                    "urgency": signal.urgency,
                    "threat_level": signal.threat_level,
                }
            )))

    def release_focus(self):
        """Release current focus."""
        if self.current_focus:
            self.focus_history.append(self.current_focus)
            self.current_focus = None
            logger.debug("Focus released")

    def update_focus_attention(self, amount: float):
        """Update attention spent on current focus."""
        if self.current_focus:
            self.current_focus.attention_spent += amount

    def is_attending_to(self, topic: str) -> bool:
        """
        Check if currently attending to a topic.

        Returns True if current focus matches topic, or if topic was
        recently attended to (within last 10 seconds).
        """
        # Check current focus
        if self.current_focus and self.current_focus.signal.get_topic() == topic:
            return True

        # Check recent attention history
        now = time.time()
        recent_cutoff = now - 10  # Last 10 seconds

        for entry in reversed(self.attention_history):
            if entry["timestamp"] < recent_cutoff:
                break
            if entry["topic"] == topic:
                return True

        return False

    # =============================================================================
    # PRIORITY OVERRIDES
    # =============================================================================

    def set_priority_override(self, signal_type: str, boost: float, duration_seconds: float = 60):
        """
        Temporarily boost priority of certain signal types.

        This is like "priming" - temporarily making certain signals more salient.

        Args:
            signal_type: Type of signal to boost
            boost: Boost factor (0.5 = 50% increase in score)
            duration_seconds: How long the boost lasts
        """
        expires_at = time.time() + duration_seconds
        self.priority_overrides[signal_type] = (boost, expires_at)

        logger.info(f"Priority override set: {signal_type} +{boost:.0%} for {duration_seconds}s")

    def clear_priority_override(self, signal_type: str):
        """Remove a priority override."""
        if signal_type in self.priority_overrides:
            del self.priority_overrides[signal_type]
            logger.info(f"Priority override cleared: {signal_type}")

    def _cleanup_priority_overrides(self):
        """Remove expired priority overrides."""
        now = time.time()
        expired = [
            sig_type for sig_type, (_, expires_at) in self.priority_overrides.items()
            if expires_at < now
        ]

        for sig_type in expired:
            del self.priority_overrides[sig_type]

    # =============================================================================
    # TOPIC FILTERS
    # =============================================================================

    def ignore_topic(self, topic: str):
        """Ignore signals from this topic."""
        self.ignored_topics.add(topic)
        logger.debug(f"Topic ignored: {topic}")

    def unignore_topic(self, topic: str):
        """Stop ignoring signals from this topic."""
        self.ignored_topics.discard(topic)
        logger.debug(f"Topic unignored: {topic}")

    def require_topics(self, topics: List[str]):
        """Only attend to signals from these topics."""
        self.required_topics = set(topics)
        logger.info(f"Required topics set: {topics}")

    def clear_required_topics(self):
        """Clear required topics filter."""
        self.required_topics.clear()
        logger.info("Required topics cleared")

    # =============================================================================
    # ATTENTION HISTORY
    # =============================================================================

    def _record_attention(self, signal: Signal):
        """Record that we attended to a signal."""
        entry = {
            "timestamp": time.time(),
            "source": signal.source,
            "topic": signal.get_topic(),
            "urgency": signal.urgency,
            "novelty": signal.novelty,
            "threat_level": signal.threat_level,
            "attention_cost": self.attention_cost(signal),
        }

        self.attention_history.append(entry)

    def get_recent_attention(self, window_seconds: float = 60) -> List[Dict]:
        """Get signals attended to in recent window."""
        now = time.time()
        cutoff = now - window_seconds

        recent = []
        for entry in reversed(self.attention_history):
            if entry["timestamp"] < cutoff:
                break
            recent.append(entry)

        return list(reversed(recent))

    def get_top_topics(self, limit: int = 10) -> List[Tuple[str, int]]:
        """Get most frequently attended topics."""
        topic_counts = defaultdict(int)

        for entry in self.attention_history:
            topic_counts[entry["topic"]] += 1

        # Sort by count
        sorted_topics = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)

        return sorted_topics[:limit]

    # =============================================================================
    # REPORTING
    # =============================================================================

    def get_attention_report(self) -> Dict[str, Any]:
        """
        Report on current attention allocation.

        Returns comprehensive attention state for monitoring and debugging.
        """
        # Calculate attention distribution
        topic_attention = defaultdict(float)
        for entry in self.attention_history:
            topic_attention[entry["topic"]] += entry["attention_cost"]

        # Sort by attention received
        top_attention = sorted(topic_attention.items(), key=lambda x: x[1], reverse=True)[:10]

        # Recent focus changes
        recent_focuses = [
            {
                "topic": focus.signal.get_topic(),
                "duration": focus.duration(),
                "attention_spent": focus.attention_spent,
            }
            for focus in list(self.focus_history)[-5:]
        ]

        return {
            "budget": {
                "current": self.attention_budget,
                "maximum": self.max_budget,
                "level": self.get_budget_level(),
                "utilization": 1 - (self.attention_budget / self.max_budget),
            },
            "focus": {
                "current_topic": self.current_focus.signal.get_topic() if self.current_focus else None,
                "focus_duration": self.current_focus.duration() if self.current_focus else 0,
                "recent_focuses": recent_focuses,
                "total_shifts": self.focus_shifts,
            },
            "processing": {
                "signals_processed": self.signals_processed,
                "signals_rejected": self.signals_rejected,
                "rejection_rate": self.signals_rejected / max(1, self.signals_processed + self.signals_rejected),
                "budget_exhaustions": self.budget_exhaustions,
            },
            "attention_distribution": [
                {"topic": topic, "attention": att} for topic, att in top_attention
            ],
            "novelty_tracking": {
                "unique_topics": len(self.topic_exposure),
                "most_seen": sorted(self.topic_exposure.items(), key=lambda x: x[1], reverse=True)[:5],
            },
            "filters": {
                "ignored_topics": list(self.ignored_topics),
                "required_topics": list(self.required_topics) if self.required_topics else None,
                "priority_overrides": list(self.priority_overrides.keys()),
            },
        }

    def get_attention_summary(self) -> str:
        """Get human-readable attention summary."""
        report = self.get_attention_report()
        budget = report["budget"]
        focus = report["focus"]
        processing = report["processing"]

        lines = [
            f"ATTENTION STATE",
            f"",
            f"Budget: {budget['current']:.2f}/{budget['maximum']:.2f} ({budget['level']})",
            f"Utilization: {budget['utilization']:.0%}",
            f"",
        ]

        if focus["current_topic"]:
            lines.extend([
                f"Current Focus: {focus['current_topic']}",
                f"Focus Duration: {focus['focus_duration']:.1f}s",
                f"",
            ])
        else:
            lines.append("Current Focus: None")
            lines.append("")

        lines.extend([
            f"Processing:",
            f"  Accepted: {processing['signals_processed']}",
            f"  Rejected: {processing['signals_rejected']}",
            f"  Rejection Rate: {processing['rejection_rate']:.0%}",
            f"  Budget Exhaustions: {processing['budget_exhaustions']}",
            f"",
        ])

        if report["attention_distribution"]:
            lines.append("Top Attention (recent):")
            for item in report["attention_distribution"][:5]:
                lines.append(f"  {item['topic']}: {item['attention']:.2f}")

        return "\n".join(lines)

    # =============================================================================
    # EVENT CONVERSION
    # =============================================================================

    def event_to_signal(self, event: OrganismEvent) -> Signal:
        """
        Convert an OrganismEvent to a Signal.

        Maps event bus events to attention-worthy signals with appropriate
        urgency, novelty, and threat levels.
        """
        # Extract basic info
        source = event.source
        content = event.data
        event_type = event.event_type.value
        priority = event.priority

        # Map priority to urgency (1=highest priority -> 1.0 urgency)
        urgency = max(0.1, min(1.0, 1 - (priority - 1) / 9))

        # Determine novelty based on event type
        novelty = 0.5  # Default
        if event.event_type in (EventType.GAP_DETECTED, EventType.SURPRISE, EventType.ANOMALY):
            novelty = 0.9  # High novelty for surprises
        elif event.event_type == EventType.HEARTBEAT:
            novelty = 0.1  # Low novelty for routine events

        # Determine threat level
        threat_level = 0.0
        if event.event_type in (EventType.HEALTH_CRITICAL, EventType.EMERGENCY):
            threat_level = 0.9
        elif event.event_type in (EventType.HEALTH_WARNING, EventType.MISSION_DRIFT):
            threat_level = 0.5
        elif event.event_type == EventType.ACTION_FAILED:
            threat_level = 0.3
        elif event.event_type == EventType.RESOURCE_LOW:
            threat_level = 0.6

        # Determine attention cost based on complexity
        attention_cost = 0.1  # Default
        if event.event_type in (EventType.GAP_DETECTED, EventType.SURPRISE):
            attention_cost = 0.2  # Complex analysis required
        elif event.event_type == EventType.HEARTBEAT:
            attention_cost = 0.05  # Low cost routine check

        return Signal(
            source=source,
            content=content,
            urgency=urgency,
            novelty=novelty,
            threat_level=threat_level,
            timestamp=event.timestamp,
            attention_cost=attention_cost,
            event_type=event_type,
            priority=priority,
        )

    def filter_events(self, events: List[OrganismEvent]) -> List[OrganismEvent]:
        """
        Filter event bus events through attention allocation.

        This is the main integration point with EventBus. Call this to
        filter events before passing them to downstream components.

        Returns only events that received attention.
        """
        # Convert events to signals
        signals = [self.event_to_signal(event) for event in events]

        # Allocate attention
        selected_signals = self.allocate(signals)

        # Map back to events
        selected_signal_ids = {id(sig) for sig in selected_signals}
        signal_id_map = {id(sig): event for sig, event in zip(signals, events)}

        selected_events = [
            signal_id_map[sig_id]
            for sig_id in selected_signal_ids
        ]

        return selected_events

    # =============================================================================
    # PERSISTENCE
    # =============================================================================

    def _save_state(self):
        """Save attention state to disk."""
        try:
            self.persistence_path.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "attention_budget": self.attention_budget,
                "topic_exposure": dict(self.topic_exposure),
                "topic_last_seen": self.topic_last_seen,
                "ignored_topics": list(self.ignored_topics),
                "stats": {
                    "signals_processed": self.signals_processed,
                    "signals_rejected": self.signals_rejected,
                    "budget_exhaustions": self.budget_exhaustions,
                    "focus_shifts": self.focus_shifts,
                },
                "saved_at": datetime.now().isoformat(),
            }

            self.persistence_path.write_text(json.dumps(data, indent=2))
            logger.debug(f"Attention state saved to {self.persistence_path}")

        except Exception as e:
            logger.error(f"Failed to save attention state: {e}")

    def _load_state(self):
        """Load attention state from disk."""
        if not self.persistence_path.exists():
            return

        try:
            data = json.loads(self.persistence_path.read_text())

            self.attention_budget = data.get("attention_budget", self.max_budget)
            self.topic_exposure = defaultdict(int, data.get("topic_exposure", {}))
            self.topic_last_seen = data.get("topic_last_seen", {})
            self.ignored_topics = set(data.get("ignored_topics", []))

            stats = data.get("stats", {})
            self.signals_processed = stats.get("signals_processed", 0)
            self.signals_rejected = stats.get("signals_rejected", 0)
            self.budget_exhaustions = stats.get("budget_exhaustions", 0)
            self.focus_shifts = stats.get("focus_shifts", 0)

            logger.info(f"Attention state loaded from {self.persistence_path}")

        except Exception as e:
            logger.warning(f"Failed to load attention state: {e}")

    def force_save(self):
        """Force immediate save of state."""
        self._save_state()

    # =============================================================================
    # EMERGENCY HANDLING
    # =============================================================================

    async def _publish_budget_critical(self):
        """Publish event when budget is critically low."""
        if not self.event_bus:
            return

        await self.event_bus.publish(OrganismEvent(
            event_type=EventType.RESOURCE_LOW,
            source="attention_allocator",
            data={
                "resource": "attention_budget",
                "level": self.attention_budget,
                "message": f"Attention budget critically low: {self.attention_budget:.2f}",
                "recommendation": "Only processing urgent/threatening signals",
            },
            priority=2
        ))


# =============================================================================
# SINGLETON ACCESS
# =============================================================================

_attention_allocator: Optional[AttentionAllocator] = None


def get_attention_allocator() -> Optional[AttentionAllocator]:
    """Get the current AttentionAllocator instance."""
    return _attention_allocator


def init_attention_allocator(mission_anchor, event_bus: Optional[EventBus] = None, **kwargs) -> AttentionAllocator:
    """Initialize the AttentionAllocator singleton."""
    global _attention_allocator
    _attention_allocator = AttentionAllocator(
        mission_anchor=mission_anchor,
        event_bus=event_bus,
        **kwargs
    )
    return _attention_allocator


def create_attention_allocator(
    mission_anchor,
    event_bus: Optional[EventBus] = None,
    initial_budget: float = 1.0,
    **kwargs
) -> AttentionAllocator:
    """
    Factory function to create an AttentionAllocator instance.

    Args:
        mission_anchor: MissionAnchor for alignment scoring
        event_bus: EventBus for subscribing to events
        initial_budget: Starting attention budget (0.0-1.0)
        **kwargs: Additional arguments passed to AttentionAllocator

    Returns:
        Initialized AttentionAllocator instance
    """
    return init_attention_allocator(
        mission_anchor=mission_anchor,
        event_bus=event_bus,
        max_budget=initial_budget,
        **kwargs
    )
