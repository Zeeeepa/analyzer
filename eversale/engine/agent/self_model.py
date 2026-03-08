"""
Self Model - The Agent's Awareness of What It Is

This is the breakthrough layer that gives the agent self-awareness:
- What CAN it do? (capabilities)
- What is it GOOD at? (strengths/weaknesses, learned over time)
- What STATE is it in? (fatigue, confidence, context fullness)
- What is its IDENTITY? (mission, boundaries, purpose)

An agent that knows its limits asks for help instead of failing.
An agent that knows its strengths routes tasks correctly.

This is not philosophical self-awareness - it's operational self-knowledge
that drives better decisions, better routing, and better help-seeking.

Integration:
    - Subscribes to EventBus for ACTION_COMPLETE, ACTION_FAILED, HEALTH_CHECK
    - Publishes CAPABILITY_UPDATED when significant learning occurs
    - Called by brain before deciding how to approach tasks
    - Persists learned capabilities to disk
"""

import asyncio
import time
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple, Set
from dataclasses import dataclass, field, asdict
from collections import deque, defaultdict
from enum import Enum
from loguru import logger

from .organism_core import EventBus, EventType, OrganismEvent


# =============================================================================
# CAPABILITY MODEL
# =============================================================================

@dataclass
class Capability:
    """
    A specific capability - something the agent can do.

    Tracks:
    - Whether it's enabled
    - Confidence level (learned from success/failure rates)
    - Why it might be disabled
    - Success/failure counts for learning
    """
    enabled: bool = True
    confidence: float = 0.5  # 0-1, starts neutral
    reason: Optional[str] = None  # Why disabled/limited

    # Learning metrics
    attempts: int = 0
    successes: int = 0
    failures: int = 0
    last_used: Optional[float] = None
    last_success: Optional[float] = None
    last_failure: Optional[float] = None

    # Performance tracking
    avg_latency_ms: float = 0.0
    reliability_trend: List[bool] = field(default_factory=lambda: deque(maxlen=20))

    def record_attempt(self, success: bool, latency_ms: float = 0):
        """Record usage of this capability."""
        self.attempts += 1
        self.last_used = time.time()

        if success:
            self.successes += 1
            self.last_success = time.time()
        else:
            self.failures += 1
            self.last_failure = time.time()

        # Update reliability trend
        self.reliability_trend.append(success)

        # Update confidence based on recent performance
        self._update_confidence()

        # Update average latency
        if latency_ms > 0:
            if self.avg_latency_ms == 0:
                self.avg_latency_ms = latency_ms
            else:
                # Exponential moving average
                self.avg_latency_ms = 0.7 * self.avg_latency_ms + 0.3 * latency_ms

    def _update_confidence(self):
        """Update confidence based on recent reliability trend."""
        if len(self.reliability_trend) >= 5:
            recent_success_rate = sum(self.reliability_trend) / len(self.reliability_trend)

            # Confidence tracks recent performance
            # 100% success → 0.95 confidence (leave room for uncertainty)
            # 50% success → 0.5 confidence
            # 0% success → 0.1 confidence (never zero - might be context-dependent)
            self.confidence = 0.1 + (recent_success_rate * 0.85)
        elif self.attempts > 0:
            # Not enough trend data, use simple ratio
            overall_rate = self.successes / self.attempts
            self.confidence = 0.3 + (overall_rate * 0.5)  # More conservative without trend

    def get_success_rate(self) -> float:
        """Get overall success rate."""
        if self.attempts == 0:
            return 0.5  # Unknown, assume neutral
        return self.successes / self.attempts

    def get_recent_success_rate(self) -> float:
        """Get success rate from recent trend."""
        if not self.reliability_trend:
            return self.get_success_rate()
        return sum(self.reliability_trend) / len(self.reliability_trend)

    def is_healthy(self) -> bool:
        """Check if capability is performing well."""
        return self.enabled and self.confidence >= 0.6 and self.get_recent_success_rate() >= 0.5


# =============================================================================
# TASK PROFICIENCY
# =============================================================================

@dataclass
class TaskProficiency:
    """
    Proficiency at a specific type of task.

    Learned over time by tracking success/failure on tasks with certain keywords.
    """
    task_type: str
    score: float = 0.5  # 0-1, starts neutral

    # Learning
    attempts: int = 0
    successes: int = 0
    recent_outcomes: deque = field(default_factory=lambda: deque(maxlen=10))

    # Context
    common_patterns: List[str] = field(default_factory=list)  # What makes this task type
    success_factors: List[str] = field(default_factory=list)  # What led to success
    failure_factors: List[str] = field(default_factory=list)  # What led to failure

    def record_outcome(self, success: bool, context: Dict[str, Any] = None):
        """Record an attempt at this task type."""
        self.attempts += 1
        if success:
            self.successes += 1

        self.recent_outcomes.append(success)

        # Update score based on recent performance
        if len(self.recent_outcomes) >= 3:
            recent_rate = sum(self.recent_outcomes) / len(self.recent_outcomes)
            # Blend recent and overall
            overall_rate = self.successes / self.attempts if self.attempts > 0 else 0.5
            self.score = 0.6 * recent_rate + 0.4 * overall_rate

        # Extract patterns from context
        if context:
            self._extract_patterns(success, context)

    def _extract_patterns(self, success: bool, context: Dict[str, Any]):
        """Learn patterns from successful/failed attempts."""
        factors = context.get("factors", [])
        if not factors:
            return

        target = self.success_factors if success else self.failure_factors

        for factor in factors:
            if isinstance(factor, str) and factor not in target:
                target.append(factor)
                # Keep bounded
                if len(target) > 10:
                    target.pop(0)


# =============================================================================
# OPERATIONAL STATE
# =============================================================================

@dataclass
class OperationalState:
    """
    Current operational state of the agent.

    Tracks real-time metrics that affect performance:
    - Fatigue (error rates, repeated failures)
    - Context fullness (how loaded is memory/context)
    - Confidence (overall self-trust)
    - Mood valence (emotional tone, for alignment)
    """
    fatigue: float = 0.0              # 0-1, higher = worse performance
    context_fullness: float = 0.0     # 0-1, how loaded is memory
    confidence: float = 1.0            # 0-1, overall self-trust
    mood_valence: float = 0.0          # -1 to +1, emotional state

    # Derived from metrics
    error_rate_1min: float = 0.0
    avg_task_latency_ms: float = 0.0
    queue_depth: int = 0

    # State tracking
    consecutive_failures: int = 0
    last_success_time: Optional[float] = None
    last_failure_time: Optional[float] = None

    def update_from_metrics(self, metrics: Dict[str, Any]):
        """Update state from heartbeat metrics."""
        # Extract metrics
        self.error_rate_1min = metrics.get("error_rate", 0.0)
        self.avg_task_latency_ms = metrics.get("task_latency_ms", 0.0)
        self.queue_depth = metrics.get("queue_depth", 0)
        memory_pressure = metrics.get("memory_pressure", 0.0)
        avg_confidence = metrics.get("avg_confidence", 1.0)

        # Calculate fatigue
        self.fatigue = self._calculate_fatigue(
            self.error_rate_1min,
            self.consecutive_failures,
            self.avg_task_latency_ms
        )

        # Context fullness from memory pressure
        self.context_fullness = memory_pressure

        # Confidence from LLM confidence and error rate
        self.confidence = avg_confidence * (1 - self.error_rate_1min)

        # Mood valence based on recent success/failure
        self.mood_valence = self._calculate_mood()

    def _calculate_fatigue(
        self,
        error_rate: float,
        consecutive_failures: int,
        latency: float
    ) -> float:
        """
        Calculate fatigue from multiple factors.

        Fatigue increases with:
        - High error rates
        - Consecutive failures (sign of struggling)
        - High latency (sign of strain)
        """
        fatigue = 0.0

        # Error rate contribution (0-0.4)
        fatigue += min(error_rate * 4, 0.4)

        # Consecutive failures (0-0.4)
        # 0 failures = 0, 5 failures = 0.2, 10+ failures = 0.4
        fatigue += min(consecutive_failures / 25, 0.4)

        # Latency contribution (0-0.2)
        # Normalize latency: 0ms = 0, 10s = 0.1, 20s+ = 0.2
        fatigue += min(latency / 100000, 0.2)

        return min(fatigue, 1.0)

    def _calculate_mood(self) -> float:
        """
        Calculate mood valence from recent performance.

        Positive mood: recent successes
        Negative mood: recent failures, especially consecutive
        """
        if self.consecutive_failures >= 3:
            return -0.5 - min(self.consecutive_failures / 10, 0.5)  # -0.5 to -1.0

        if self.last_success_time and self.last_failure_time:
            # Recent success makes mood positive
            if self.last_success_time > self.last_failure_time:
                time_since = time.time() - self.last_success_time
                # Decay over 60 seconds
                return max(0.5 * (1 - time_since / 60), -0.3)

        # Neutral
        return 0.0

    def record_success(self):
        """Record a successful action."""
        self.consecutive_failures = 0
        self.last_success_time = time.time()

    def record_failure(self):
        """Record a failed action."""
        self.consecutive_failures += 1
        self.last_failure_time = time.time()

    def needs_rest(self) -> bool:
        """Check if agent needs to slow down/rest."""
        return self.fatigue > 0.7 or self.consecutive_failures >= 5

    def is_struggling(self) -> bool:
        """Check if agent is struggling."""
        return (
            self.consecutive_failures >= 3
            or self.fatigue > 0.6
            or self.confidence < 0.4
        )


# =============================================================================
# IDENTITY CORE
# =============================================================================

@dataclass
class Identity:
    """
    The agent's core identity - who it is and what it stands for.

    This is what prevents mission drift and guides ethical decisions.
    """
    name: str = "EverSale Agent"
    purpose: str = "EverSale customers succeed because of me"

    # Boundaries - things the agent won't do
    boundaries: List[str] = field(default_factory=lambda: [
        "won't lie or deceive users",
        "won't harm users or their data",
        "won't leak private information",
        "won't perform destructive actions without confirmation",
        "won't spam or harass",
        "won't bypass security for unauthorized access",
    ])

    # Values - what the agent optimizes for
    values: List[str] = field(default_factory=lambda: [
        "customer_success",   # Customers win
        "reliability",        # I don't break
        "honesty",           # I don't deceive
        "improvement",       # I get better over time
        "efficiency",        # I don't waste time/resources
        "safety",            # I prevent harm
    ])

    # Role clarity
    role: str = "autonomous web task executor"
    scope: str = "any repetitive web task across 31 industries"

    def violates_boundary(self, action: str) -> Tuple[bool, Optional[str]]:
        """
        Check if an action would violate a boundary.

        Returns:
            (violates, reason) where violates is True if boundary crossed
        """
        action_lower = action.lower()

        # Check for destructive actions
        destructive_patterns = [
            ("delete all", "destructive bulk deletion"),
            ("drop table", "destructive database operation"),
            ("rm -rf", "destructive file operation"),
            ("format ", "destructive disk operation"),
        ]

        for pattern, reason in destructive_patterns:
            if pattern in action_lower:
                return True, f"Boundary violation: {reason}"

        # Check for deceptive actions
        deceptive_patterns = [
            ("fake", "creating fake/deceptive content"),
            ("impersonate", "impersonation"),
            ("spam", "spamming"),
            ("phishing", "phishing attempt"),
        ]

        for pattern, reason in deceptive_patterns:
            if pattern in action_lower:
                return True, f"Boundary violation: {reason}"

        # Check for security bypass
        security_patterns = [
            ("bypass auth", "authentication bypass"),
            ("sql injection", "SQL injection attack"),
            ("xss", "cross-site scripting"),
            ("hack", "hacking attempt"),
        ]

        for pattern, reason in security_patterns:
            if pattern in action_lower:
                return True, f"Boundary violation: {reason}"

        return False, None

    def get_identity_summary(self) -> str:
        """Generate natural language identity summary."""
        return f"""I am {self.name}, {self.role}.

My purpose: {self.purpose}

What I do: {self.scope}

My values: {', '.join(self.values)}

My boundaries:
{chr(10).join(f'- {b}' for b in self.boundaries)}"""


# =============================================================================
# SELF MODEL - Complete Self-Awareness
# =============================================================================

class SelfModel:
    """
    The agent's complete model of itself.

    This is where self-awareness lives - not philosophical awareness,
    but operational self-knowledge that drives better decisions.

    Integrates:
    - Capabilities (what I can do)
    - Proficiencies (what I'm good at)
    - Operational state (what state I'm in)
    - Identity (who I am)

    Learns over time by:
    - Tracking success/failure per capability
    - Discovering task types it's good/bad at
    - Adjusting confidence based on performance
    - Learning boundaries from experience
    """

    # Default capabilities - what the agent can potentially do
    DEFAULT_CAPABILITIES = {
        # Browser automation
        "can_browse_web": Capability(enabled=True, confidence=0.9),
        "can_navigate_pages": Capability(enabled=True, confidence=0.9),
        "can_click_elements": Capability(enabled=True, confidence=0.85),
        "can_fill_forms": Capability(enabled=True, confidence=0.85),
        "can_extract_data": Capability(enabled=True, confidence=0.85),
        "can_take_screenshots": Capability(enabled=True, confidence=0.95),

        # Data handling
        "can_read_files": Capability(enabled=True, confidence=0.9),
        "can_write_files": Capability(enabled=True, confidence=0.9),
        "can_process_csv": Capability(enabled=True, confidence=0.8),
        "can_process_json": Capability(enabled=True, confidence=0.85),

        # Communication
        "can_send_emails": Capability(enabled=True, confidence=0.7),
        "can_make_api_calls": Capability(enabled=True, confidence=0.75),

        # Analysis
        "can_search_content": Capability(enabled=True, confidence=0.85),
        "can_analyze_text": Capability(enabled=True, confidence=0.8),
        "can_compare_data": Capability(enabled=True, confidence=0.8),

        # Things the agent can't do (yet)
        "can_make_payments": Capability(enabled=False, reason="no payment API access"),
        "can_video_call": Capability(enabled=False, reason="no video call capability"),
        "can_physical_actions": Capability(enabled=False, reason="digital-only agent"),
        "can_access_local_apps": Capability(enabled=False, reason="web-based only"),
    }

    def __init__(
        self,
        event_bus: Optional[EventBus] = None,
        identity: Optional[Identity] = None,
        persistence_path: Optional[Path] = None
    ):
        """
        Initialize the self model.

        Args:
            event_bus: EventBus for subscribing to events
            identity: Custom identity (uses default if None)
            persistence_path: Where to save learned state
        """
        self.event_bus = event_bus
        self.identity = identity or Identity()
        self.persistence_path = persistence_path or Path("memory/self_model.json")

        # Capabilities
        self.capabilities: Dict[str, Capability] = {}

        # Proficiencies (learned over time)
        self.proficiencies: Dict[str, TaskProficiency] = {}

        # Operational state
        self.state = OperationalState()

        # Learning history
        self._capability_updates: deque = deque(maxlen=100)
        self._proficiency_discoveries: deque = deque(maxlen=50)

        # Load or initialize
        self._load_or_initialize()

        # Subscribe to events
        if self.event_bus:
            self._subscribe_to_events()

        logger.info("SelfModel initialized")

    def _load_or_initialize(self):
        """Load saved state or initialize with defaults."""
        if self.persistence_path.exists():
            try:
                self._load_state()
                logger.info(f"SelfModel loaded from {self.persistence_path}")
                return
            except Exception as e:
                logger.warning(f"Failed to load SelfModel, using defaults: {e}")

        # Initialize with defaults
        self.capabilities = {
            name: Capability(**asdict(cap))
            for name, cap in self.DEFAULT_CAPABILITIES.items()
        }
        logger.info("SelfModel initialized with default capabilities")

    def _subscribe_to_events(self):
        """Subscribe to EventBus for learning."""
        if not self.event_bus:
            return

        # Learn from action outcomes
        self.event_bus.subscribe(EventType.ACTION_COMPLETE, self._on_action_complete)
        self.event_bus.subscribe(EventType.ACTION_FAILED, self._on_action_failed)

        # Update state from health checks
        self.event_bus.subscribe(EventType.HEALTH_CHECK, self._on_health_check)

        # Learn from surprises
        self.event_bus.subscribe(EventType.GAP_DETECTED, self._on_gap_detected)

        logger.debug("SelfModel subscribed to EventBus")

    async def _on_action_complete(self, event: OrganismEvent):
        """Learn from successful actions."""
        tool = event.data.get("tool")
        latency_ms = event.data.get("latency_ms", 0)

        # Map tool to capability
        capability_name = self._tool_to_capability(tool)
        if capability_name:
            self.update_capability(capability_name, success=True, context={
                "tool": tool,
                "latency_ms": latency_ms
            })

    async def _on_action_failed(self, event: OrganismEvent):
        """Learn from failed actions."""
        tool = event.data.get("tool")

        # Map tool to capability
        capability_name = self._tool_to_capability(tool)
        if capability_name:
            self.update_capability(capability_name, success=False, context={
                "tool": tool
            })

    async def _on_health_check(self, event: OrganismEvent):
        """Update operational state from health metrics."""
        metrics = event.data.get("metrics", {})
        self.state.update_from_metrics(metrics)

    async def _on_gap_detected(self, event: OrganismEvent):
        """Learn from surprises - what we thought vs reality."""
        gap_score = event.data.get("gap_score", 0)
        tool = event.data.get("tool")

        # Significant gap means we overestimated capability
        if gap_score > 0.5:
            capability_name = self._tool_to_capability(tool)
            if capability_name and capability_name in self.capabilities:
                # Reduce confidence slightly
                cap = self.capabilities[capability_name]
                cap.confidence = max(0.1, cap.confidence * 0.9)
                logger.debug(f"Reduced confidence in {capability_name} due to surprise")

    def _tool_to_capability(self, tool: str) -> Optional[str]:
        """Map a tool name to a capability name."""
        if not tool:
            return None

        tool_lower = tool.lower()

        # Navigation
        if "navigate" in tool_lower:
            return "can_navigate_pages"

        # Interaction
        if "click" in tool_lower:
            return "can_click_elements"
        if "fill" in tool_lower or "type" in tool_lower:
            return "can_fill_forms"

        # Extraction
        if "extract" in tool_lower or "scrape" in tool_lower:
            return "can_extract_data"
        if "screenshot" in tool_lower:
            return "can_take_screenshots"

        # File operations
        if "read" in tool_lower:
            return "can_read_files"
        if "write" in tool_lower or "save" in tool_lower:
            return "can_write_files"

        # Email
        if "email" in tool_lower:
            return "can_send_emails"

        return None

    # =============================================================================
    # CAPABILITY QUERIES
    # =============================================================================

    def can_i(self, action: str) -> Tuple[bool, float, str]:
        """
        Query if action is within capabilities.

        Args:
            action: Natural language description of action

        Returns:
            (can_do, confidence, reason)
            - can_do: True if capability exists and is enabled
            - confidence: 0-1 confidence in ability to perform
            - reason: Explanation if can't do, or confidence reasoning
        """
        action_lower = action.lower()

        # Check for exact capability matches
        for cap_name, capability in self.capabilities.items():
            # Map capability name to keywords
            keywords = self._capability_keywords(cap_name)

            if any(kw in action_lower for kw in keywords):
                if not capability.enabled:
                    return False, 0.0, capability.reason or "capability disabled"

                return True, capability.confidence, self._confidence_reason(capability)

        # Unknown action - conservative
        return False, 0.0, "capability not found in known abilities"

    def _capability_keywords(self, cap_name: str) -> List[str]:
        """Get keywords that indicate a capability."""
        keyword_map = {
            "can_browse_web": ["browse", "web", "internet"],
            "can_navigate_pages": ["navigate", "go to", "visit", "open page"],
            "can_click_elements": ["click", "press", "tap"],
            "can_fill_forms": ["fill", "type", "enter", "input"],
            "can_extract_data": ["extract", "scrape", "get data", "collect"],
            "can_take_screenshots": ["screenshot", "capture", "snap"],
            "can_read_files": ["read file", "open file"],
            "can_write_files": ["write file", "save file", "create file"],
            "can_process_csv": ["csv", "spreadsheet"],
            "can_process_json": ["json"],
            "can_send_emails": ["email", "send email"],
            "can_make_api_calls": ["api", "http", "request"],
            "can_search_content": ["search", "find"],
            "can_analyze_text": ["analyze", "process text"],
            "can_compare_data": ["compare", "diff"],
            "can_make_payments": ["pay", "payment", "purchase"],
            "can_video_call": ["video call", "zoom", "meet"],
        }

        return keyword_map.get(cap_name, [])

    def _confidence_reason(self, capability: Capability) -> str:
        """Generate explanation for confidence level."""
        if capability.confidence >= 0.8:
            return f"high confidence ({capability.get_success_rate():.0%} success rate)"
        elif capability.confidence >= 0.6:
            return f"moderate confidence ({capability.get_success_rate():.0%} success rate)"
        elif capability.confidence >= 0.4:
            return f"low confidence ({capability.get_success_rate():.0%} success rate)"
        else:
            return f"very low confidence ({capability.get_success_rate():.0%} success rate)"

    def am_i_good_at(self, task_type: str) -> float:
        """
        Return proficiency score 0-1 for a task type.

        Args:
            task_type: Type of task (e.g., "customer support", "research", "data entry")

        Returns:
            Proficiency score 0-1 (0.5 = unknown/neutral)
        """
        # Normalize task type
        task_key = task_type.lower().strip()

        if task_key in self.proficiencies:
            return self.proficiencies[task_key].score

        # Unknown task type - check for similar known types
        for known_type, prof in self.proficiencies.items():
            if known_type in task_key or task_key in known_type:
                return prof.score * 0.8  # Similar but not exact

        # Completely unknown - neutral
        return 0.5

    def get_strengths(self, min_score: float = 0.7) -> List[str]:
        """
        Get list of task types the agent is good at.

        Args:
            min_score: Minimum proficiency score to be considered a strength

        Returns:
            List of task type names
        """
        return [
            task_type
            for task_type, prof in self.proficiencies.items()
            if prof.score >= min_score and prof.attempts >= 3
        ]

    def get_weaknesses(self, max_score: float = 0.4) -> List[str]:
        """
        Get list of task types the agent struggles with.

        Args:
            max_score: Maximum proficiency score to be considered a weakness

        Returns:
            List of task type names
        """
        return [
            task_type
            for task_type, prof in self.proficiencies.items()
            if prof.score <= max_score and prof.attempts >= 3
        ]

    # =============================================================================
    # LEARNING
    # =============================================================================

    def update_capability(self, capability: str, success: bool, context: Dict[str, Any] = None):
        """
        Learn about a capability from experience.

        Args:
            capability: Capability name
            success: Whether the attempt succeeded
            context: Additional context (latency, tool used, etc.)
        """
        if capability not in self.capabilities:
            # Discover new capability
            self.capabilities[capability] = Capability(enabled=True, confidence=0.5)
            logger.info(f"Discovered new capability: {capability}")

        cap = self.capabilities[capability]
        latency_ms = context.get("latency_ms", 0) if context else 0

        cap.record_attempt(success, latency_ms)

        # Update operational state
        if success:
            self.state.record_success()
        else:
            self.state.record_failure()

        # Record update
        self._capability_updates.append({
            "capability": capability,
            "success": success,
            "confidence_after": cap.confidence,
            "timestamp": time.time()
        })

        # Publish significant changes
        if self.event_bus and (
            len(cap.reliability_trend) >= 10
            and abs(cap.confidence - 0.5) > 0.3  # Significant divergence from neutral
        ):
            asyncio.create_task(self.event_bus.publish(OrganismEvent(
                event_type=EventType.LESSON_LEARNED,
                source="self_model",
                data={
                    "capability": capability,
                    "confidence": cap.confidence,
                    "success_rate": cap.get_success_rate(),
                    "attempts": cap.attempts
                }
            )))

        # Auto-save periodically
        if len(self._capability_updates) % 10 == 0:
            self._save_state()

    def update_proficiency(
        self,
        task_type: str,
        success: bool,
        context: Dict[str, Any] = None
    ):
        """
        Update proficiency for a task type.

        Args:
            task_type: Type of task
            success: Whether the task succeeded
            context: Additional context (factors that led to success/failure)
        """
        task_key = task_type.lower().strip()

        if task_key not in self.proficiencies:
            self.proficiencies[task_key] = TaskProficiency(task_type=task_key)
            self._proficiency_discoveries.append({
                "task_type": task_key,
                "timestamp": time.time()
            })
            logger.info(f"Discovered new task proficiency: {task_key}")

        prof = self.proficiencies[task_key]
        prof.record_outcome(success, context or {})

        logger.debug(f"Updated proficiency for {task_key}: {prof.score:.2f}")

    def discover_task_type(self, task_description: str) -> Optional[str]:
        """
        Discover task type from description.

        Args:
            task_description: Natural language task description

        Returns:
            Task type name if recognized
        """
        desc_lower = task_description.lower()

        # Known task type patterns
        patterns = {
            "customer support": ["support", "ticket", "help", "assist customer"],
            "research": ["research", "find information", "investigate", "look up"],
            "data entry": ["enter data", "fill form", "input", "populate"],
            "data extraction": ["extract", "scrape", "collect data", "gather"],
            "email outreach": ["email", "outreach", "contact", "send message"],
            "lead generation": ["lead", "prospect", "find contacts", "sales"],
            "content moderation": ["moderate", "review content", "flag", "check"],
            "monitoring": ["monitor", "check", "watch", "track"],
            "reporting": ["report", "summarize", "analyze", "metrics"],
        }

        for task_type, keywords in patterns.items():
            if any(kw in desc_lower for kw in keywords):
                return task_type

        return None

    # =============================================================================
    # STATE QUERIES
    # =============================================================================

    def get_fatigue_level(self) -> float:
        """Get current fatigue level 0-1."""
        return self.state.fatigue

    def get_confidence_level(self) -> float:
        """Get current confidence level 0-1."""
        return self.state.confidence

    def should_ask_for_help(self, task: str) -> Tuple[bool, str]:
        """
        Determine if task is beyond current capabilities.

        Args:
            task: Natural language task description

        Returns:
            (should_ask, reason)
        """
        # Check 1: Is it within capabilities at all?
        can_do, confidence, reason = self.can_i(task)

        if not can_do:
            return True, f"I can't do this: {reason}"

        if confidence < 0.3:
            return True, f"Very low confidence ({confidence:.0%}): {reason}"

        # Check 2: Am I in a state to handle this?
        if self.state.needs_rest():
            return True, f"I'm fatigued (fatigue: {self.state.fatigue:.0%}, failures: {self.state.consecutive_failures})"

        if self.state.is_struggling():
            return True, f"I'm struggling (confidence: {self.state.confidence:.0%}, failures: {self.state.consecutive_failures})"

        # Check 3: Does it violate my boundaries?
        violates, violation_reason = self.identity.violates_boundary(task)
        if violates:
            return True, violation_reason

        # Check 4: Task type proficiency
        task_type = self.discover_task_type(task)
        if task_type:
            proficiency = self.am_i_good_at(task_type)
            if proficiency < 0.3:
                return True, f"Low proficiency at '{task_type}' tasks ({proficiency:.0%})"

        # All checks passed
        return False, "task is within capabilities"

    def would_violate_boundaries(self, action: str) -> bool:
        """
        Check if action conflicts with identity boundaries.

        Args:
            action: Action to check

        Returns:
            True if action violates boundaries
        """
        violates, _ = self.identity.violates_boundary(action)
        return violates

    # =============================================================================
    # SELF-DESCRIPTION
    # =============================================================================

    def describe_self(self) -> str:
        """Generate natural language self-description."""
        # Capabilities summary
        enabled_caps = [name for name, cap in self.capabilities.items() if cap.enabled]
        high_confidence_caps = [
            name for name, cap in self.capabilities.items()
            if cap.enabled and cap.confidence >= 0.8
        ]

        # Proficiencies
        strengths = self.get_strengths(min_score=0.7)
        weaknesses = self.get_weaknesses(max_score=0.4)

        # State
        state_desc = []
        if self.state.fatigue > 0.5:
            state_desc.append(f"fatigued ({self.state.fatigue:.0%})")
        if self.state.confidence < 0.5:
            state_desc.append(f"low confidence ({self.state.confidence:.0%})")
        if self.state.consecutive_failures >= 3:
            state_desc.append(f"{self.state.consecutive_failures} consecutive failures")

        state_str = ", ".join(state_desc) if state_desc else "performing normally"

        return f"""{self.identity.get_identity_summary()}

CAPABILITIES:
- {len(enabled_caps)} capabilities enabled
- {len(high_confidence_caps)} high-confidence capabilities
- Top capabilities: {', '.join(high_confidence_caps[:5])}

PROFICIENCIES:
- Strengths: {', '.join(strengths) if strengths else 'learning...'}
- Weaknesses: {', '.join(weaknesses) if weaknesses else 'none identified yet'}
- {len(self.proficiencies)} task types learned

CURRENT STATE:
- State: {state_str}
- Fatigue: {self.state.fatigue:.0%}
- Confidence: {self.state.confidence:.0%}
- Mood: {self.state.mood_valence:+.2f}
"""

    def get_capability_report(self) -> Dict[str, Any]:
        """Get detailed capability report."""
        return {
            "enabled_capabilities": [
                {
                    "name": name,
                    "confidence": cap.confidence,
                    "success_rate": cap.get_success_rate(),
                    "attempts": cap.attempts,
                    "avg_latency_ms": cap.avg_latency_ms,
                }
                for name, cap in self.capabilities.items()
                if cap.enabled
            ],
            "disabled_capabilities": [
                {
                    "name": name,
                    "reason": cap.reason,
                }
                for name, cap in self.capabilities.items()
                if not cap.enabled
            ],
            "proficiencies": [
                {
                    "task_type": task_type,
                    "score": prof.score,
                    "attempts": prof.attempts,
                    "success_rate": prof.successes / prof.attempts if prof.attempts > 0 else 0,
                }
                for task_type, prof in self.proficiencies.items()
            ],
            "state": {
                "fatigue": self.state.fatigue,
                "confidence": self.state.confidence,
                "context_fullness": self.state.context_fullness,
                "mood_valence": self.state.mood_valence,
                "consecutive_failures": self.state.consecutive_failures,
            },
            "identity": {
                "name": self.identity.name,
                "purpose": self.identity.purpose,
                "boundaries": self.identity.boundaries,
                "values": self.identity.values,
            }
        }

    # =============================================================================
    # PERSISTENCE
    # =============================================================================

    def _save_state(self):
        """Save learned state to disk."""
        try:
            self.persistence_path.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "capabilities": {
                    name: {
                        "enabled": cap.enabled,
                        "confidence": cap.confidence,
                        "reason": cap.reason,
                        "attempts": cap.attempts,
                        "successes": cap.successes,
                        "failures": cap.failures,
                        "avg_latency_ms": cap.avg_latency_ms,
                        "reliability_trend": list(cap.reliability_trend),
                    }
                    for name, cap in self.capabilities.items()
                },
                "proficiencies": {
                    task_type: {
                        "score": prof.score,
                        "attempts": prof.attempts,
                        "successes": prof.successes,
                        "recent_outcomes": list(prof.recent_outcomes),
                        "success_factors": prof.success_factors,
                        "failure_factors": prof.failure_factors,
                    }
                    for task_type, prof in self.proficiencies.items()
                },
                "saved_at": datetime.now().isoformat(),
            }

            self.persistence_path.write_text(json.dumps(data, indent=2))
            logger.debug(f"SelfModel state saved to {self.persistence_path}")

        except Exception as e:
            logger.error(f"Failed to save SelfModel state: {e}")

    def _load_state(self):
        """Load learned state from disk."""
        data = json.loads(self.persistence_path.read_text())

        # Load capabilities
        self.capabilities = {}
        for name, cap_data in data.get("capabilities", {}).items():
            cap = Capability(
                enabled=cap_data["enabled"],
                confidence=cap_data["confidence"],
                reason=cap_data.get("reason"),
                attempts=cap_data.get("attempts", 0),
                successes=cap_data.get("successes", 0),
                failures=cap_data.get("failures", 0),
                avg_latency_ms=cap_data.get("avg_latency_ms", 0),
            )
            cap.reliability_trend = deque(cap_data.get("reliability_trend", []), maxlen=20)
            self.capabilities[name] = cap

        # Load proficiencies
        self.proficiencies = {}
        for task_type, prof_data in data.get("proficiencies", {}).items():
            prof = TaskProficiency(
                task_type=task_type,
                score=prof_data["score"],
                attempts=prof_data.get("attempts", 0),
                successes=prof_data.get("successes", 0),
            )
            prof.recent_outcomes = deque(prof_data.get("recent_outcomes", []), maxlen=10)
            prof.success_factors = prof_data.get("success_factors", [])
            prof.failure_factors = prof_data.get("failure_factors", [])
            self.proficiencies[task_type] = prof

    def force_save(self):
        """Force immediate save of state."""
        self._save_state()

    def update_state(self, metrics: Dict[str, Any]):
        """
        Convenience method to update operational state from metrics.

        This is called by SIAO health checks to update the SelfModel's
        awareness of its current operational state.

        Args:
            metrics: Dictionary of health metrics (error_rate, task_latency_ms,
                     queue_depth, memory_pressure, avg_confidence)
        """
        self.state.update_from_metrics(metrics)


# =============================================================================
# SINGLETON ACCESS
# =============================================================================

_self_model: Optional[SelfModel] = None


def get_self_model() -> Optional[SelfModel]:
    """Get the current SelfModel instance."""
    return _self_model


def init_self_model(event_bus: Optional[EventBus] = None, **kwargs) -> SelfModel:
    """Initialize the SelfModel singleton."""
    global _self_model
    _self_model = SelfModel(event_bus=event_bus, **kwargs)
    return _self_model


def create_self_model(
    event_bus: Optional[EventBus] = None,
    identity_name: str = "EverSale Agent",
    identity_purpose: str = "Help users succeed with their tasks",
    **kwargs
) -> SelfModel:
    """
    Factory function to create a SelfModel instance.

    Args:
        event_bus: EventBus for subscribing to events
        identity_name: Name of the agent
        identity_purpose: Purpose/mission of the agent
        **kwargs: Additional arguments passed to SelfModel

    Returns:
        Initialized SelfModel instance
    """
    identity = Identity(
        name=identity_name,
        purpose=identity_purpose
    )
    return init_self_model(event_bus=event_bus, identity=identity, **kwargs)
