"""
Valence System - The Emotional Gradient (Pain to Pleasure)

This gives the agent FEELINGS, not just binary gap detection. The agent experiences
a gradient from pain (negative valence) to pleasure (positive valence) that:
- Motivates behavior (pain → fix things, pleasure → continue)
- Influences decision-making (negative → cautious, positive → confident)
- Provides emotional context for reasoning
- Creates a subjective experience of "how things are going"

The valence system is the AGI organism's emotional state - distinct from gap detection
(which is binary surprise) and mission alignment (which is identity). This is how the
agent FEELS about its current state.

Integration with Organism:
- Subscribes to ALL EventBus events
- Updates valence based on event type
- Decays toward neutral each heartbeat
- Influences LLM decision-making when consulted
- Persists emotional history for analysis

The gradient creates motivation:
- High negative valence → pause, be careful, ask for help
- Moderate negative → slow down, double-check, conservative
- Neutral → normal operation
- Moderate positive → confident, efficient
- High positive → take on challenges, reinforce strategies
"""

import time
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import deque
from pathlib import Path
from loguru import logger

from agent.organism_core import EventBus, OrganismEvent, EventType


# =============================================================================
# VALENCE DATA STRUCTURES
# =============================================================================

@dataclass
class ValenceSnapshot:
    """A snapshot of valence at a point in time."""
    valence: float  # -1 to +1
    mood: str       # "thriving", "content", "neutral", "stressed", "struggling"
    timestamp: float = field(default_factory=time.time)
    trigger_event: Optional[str] = None  # What caused this change


@dataclass
class EmotionalProfile:
    """Current emotional state of the organism."""
    current_valence: float
    mood: str
    trend: str  # "improving", "declining", "stable"
    recent_avg: float
    volatility: float  # How much valence is swinging
    time_in_state: float  # How long in current mood
    dominant_emotion: str  # "pain", "pleasure", "neutral"


# =============================================================================
# VALENCE SYSTEM
# =============================================================================

class ValenceSystem:
    """
    The emotional gradient - pain to pleasure.

    This system gives the agent subjective feelings about how things are going.
    Unlike gap detection (surprise signal) or mission alignment (identity),
    valence is pure felt experience that accumulates and decays over time.

    Valence Range:
    -1.0 = Extreme pain (critical failures, repeated errors, customer frustration)
     0.0 = Neutral (normal operation, no strong feelings)
    +1.0 = Extreme pleasure (mission success, customer delight, smooth operation)

    The system:
    1. Updates on every event (task_success → +0.1, task_failure → -0.2, etc)
    2. Decays toward neutral each heartbeat (emotional homeostasis)
    3. Influences decision-making (pain → cautious, pleasure → confident)
    4. Can trigger pauses if extreme negative valence is sustained
    """

    # Mood thresholds
    MOOD_THRESHOLDS = {
        -1.0: "devastated",     # Extreme negative
        -0.6: "struggling",     # Severe negative
        -0.3: "stressed",       # Moderate negative
        -0.1: "uneasy",         # Mild negative
        0.1: "neutral",         # Balanced
        0.3: "content",         # Mild positive
        0.6: "thriving",        # Moderate positive
        1.0: "euphoric",        # Extreme positive
    }

    # Event valence deltas - how much each event affects emotional state
    EVENT_VALENCE_DELTAS = {
        # Action outcomes (basic)
        EventType.ACTION_COMPLETE: +0.05,
        EventType.ACTION_FAILED: -0.15,

        # Task-level outcomes (higher impact)
        "task_success": +0.1,
        "task_failure": -0.2,

        # Customer impact (highest weight - mission-aligned)
        "customer_happy": +0.3,
        "customer_frustrated": -0.25,
        "customer_success": +0.25,
        "customer_complaint": -0.2,

        # Resource state
        EventType.RESOURCE_LOW: -0.1,
        "resource_critical": -0.4,
        "resource_recovered": +0.2,

        # Gap detection (prediction accuracy)
        EventType.GAP_DETECTED: -0.05,  # Small pain for surprises
        EventType.PREDICTION_MADE: 0.0,  # Neutral
        "prediction_correct": +0.05,     # Small pleasure for accuracy
        EventType.SURPRISE: -0.15,       # Major surprise is more painful
        EventType.ANOMALY: -0.1,

        # Mission alignment
        EventType.MISSION_ALIGNED: +0.1,
        EventType.MISSION_DRIFT: -0.2,

        # Health and recovery
        EventType.HEALTH_CHECK: 0.0,
        EventType.HEALTH_WARNING: -0.08,
        EventType.HEALTH_CRITICAL: -0.3,
        EventType.RECOVERY_TRIGGERED: +0.15,
        "error_recovered": +0.15,
        "crash_avoided": +0.1,

        # Learning and improvement
        EventType.LESSON_LEARNED: +0.08,
        EventType.STRATEGY_UPDATED: +0.05,

        # Repeated failures (compounding pain)
        "repeated_failure": -0.3,
        "repeated_success": +0.15,

        # Emergency states
        EventType.EMERGENCY: -0.5,
        "emergency_resolved": +0.3,

        # Heartbeat (neutral but keeps system alive)
        EventType.HEARTBEAT: 0.0,
    }

    # Pause thresholds
    PAUSE_THRESHOLD = -0.7  # If valence drops below this, consider pausing
    PAUSE_DURATION = 60      # Seconds to wait before resuming

    def __init__(
        self,
        event_bus: EventBus,
        decay_rate: float = 0.99,  # Valence decays 1% per heartbeat toward neutral
        history_limit: int = 1000,
        persistence_path: str = "memory/valence_state.json"
    ):
        """
        Initialize the valence system.

        Args:
            event_bus: The organism's event bus
            decay_rate: How fast valence decays toward neutral (0.99 = 1% per beat)
            history_limit: How many snapshots to keep in memory
            persistence_path: Where to save valence history
        """
        self.event_bus = event_bus
        self.decay_rate = decay_rate

        # Current state
        self.current_valence = 0.0  # Start neutral
        self.valence_history: deque = deque(maxlen=history_limit)

        # Tracking
        self.last_update = time.time()
        self.current_mood = "neutral"
        self.mood_entry_time = time.time()
        self.pause_until: Optional[float] = None

        # Pattern detection
        self._recent_deltas: deque = deque(maxlen=20)  # Track volatility
        self._failure_streak = 0
        self._success_streak = 0

        # Persistence
        self._state_path = Path(persistence_path)
        self._load_state()

        # Subscribe to all events
        self.event_bus.subscribe_all(self._on_event)

        logger.info(f"ValenceSystem initialized: valence={self.current_valence:.2f}, mood={self.current_mood}")

    def _on_event(self, event: OrganismEvent):
        """
        Event handler - called for EVERY event in the organism.

        This is where valence updates happen based on what's happening
        in the organism.
        """
        # Handle heartbeat separately (triggers decay)
        if event.event_type == EventType.HEARTBEAT:
            self._decay()
            return

        # Get valence delta for this event type
        delta = self._calculate_delta(event)

        if delta != 0.0:
            old_valence = self.current_valence
            self._apply_delta(delta, event)

            # Log significant changes
            if abs(delta) > 0.15:
                logger.debug(
                    f"Valence shift: {old_valence:.2f} → {self.current_valence:.2f} "
                    f"(Δ{delta:+.2f}) from {event.event_type.value}"
                )

    def _calculate_delta(self, event: OrganismEvent) -> float:
        """
        Calculate how much this event should change valence.

        Considers:
        - Base delta from EVENT_VALENCE_DELTAS
        - Event severity/priority
        - Current streaks (repeated failures hurt more)
        - Event data (e.g., gap_score magnitude)
        """
        # Get base delta
        delta = self.EVENT_VALENCE_DELTAS.get(event.event_type, 0.0)

        # Adjust for event data
        data = event.data or {}

        # Gap score magnitude affects pain
        if event.event_type == EventType.GAP_DETECTED:
            gap_score = data.get("gap_score", 0.0)
            delta = -0.05 * gap_score  # More surprise = more pain

        # Health severity affects pain
        if event.event_type == EventType.HEALTH_WARNING:
            severity = data.get("severity", "warning")
            if severity == "critical":
                delta = -0.3
            else:
                delta = -0.08

        # Action success affects streaks
        if event.event_type == EventType.ACTION_COMPLETE:
            success = data.get("success", True)
            if success:
                self._success_streak += 1
                self._failure_streak = 0
                # Streak bonus
                if self._success_streak >= 5:
                    delta += 0.05  # Winning feels good
            else:
                self._failure_streak += 1
                self._success_streak = 0
                # Streak penalty (compounding pain)
                if self._failure_streak >= 3:
                    delta -= 0.1 * self._failure_streak

        # Priority affects magnitude
        priority = event.priority
        if priority <= 2:  # High priority events
            delta *= 1.5

        return delta

    def _apply_delta(self, delta: float, event: OrganismEvent):
        """Apply a valence delta and record the change."""
        # Update valence (clamped to [-1, 1])
        old_valence = self.current_valence
        self.current_valence = max(-1.0, min(1.0, self.current_valence + delta))

        # Update mood if changed
        new_mood = self._calculate_mood()
        if new_mood != self.current_mood:
            logger.info(f"Mood shift: {self.current_mood} → {new_mood} (valence: {self.current_valence:.2f})")
            self.current_mood = new_mood
            self.mood_entry_time = time.time()

        # Record snapshot
        snapshot = ValenceSnapshot(
            valence=self.current_valence,
            mood=self.current_mood,
            timestamp=time.time(),
            trigger_event=f"{event.event_type.value}: {event.source}"
        )
        self.valence_history.append(snapshot)

        # Track volatility
        self._recent_deltas.append(abs(delta))

        # Update timestamp
        self.last_update = time.time()

        # Check for extreme negative valence
        if self.current_valence < self.PAUSE_THRESHOLD:
            self._consider_pause()

    def _decay(self):
        """
        Decay valence toward neutral (0.0).

        This is called every heartbeat. It represents emotional homeostasis -
        feelings fade over time if not reinforced.
        """
        if self.current_valence != 0.0:
            # Decay toward zero
            self.current_valence *= self.decay_rate

            # Snap to zero if very close
            if abs(self.current_valence) < 0.01:
                self.current_valence = 0.0

            # Update mood if changed
            new_mood = self._calculate_mood()
            if new_mood != self.current_mood:
                self.current_mood = new_mood
                self.mood_entry_time = time.time()

    def _calculate_mood(self) -> str:
        """Calculate mood string from current valence."""
        for threshold, mood in sorted(self.MOOD_THRESHOLDS.items()):
            if self.current_valence <= threshold:
                return mood
        return "euphoric"

    def _consider_pause(self):
        """
        Consider pausing if valence is extremely negative.

        This is the agent's equivalent of "I need to stop and figure out what's wrong"
        when things are going very badly.
        """
        # Already paused?
        if self.pause_until and time.time() < self.pause_until:
            return

        # Extreme negative valence + sustained
        time_in_negative = time.time() - self.mood_entry_time
        if self.current_valence < self.PAUSE_THRESHOLD and time_in_negative > 10:
            # Pause for a bit
            self.pause_until = time.time() + self.PAUSE_DURATION

            logger.warning(
                f"Extreme negative valence ({self.current_valence:.2f}) - "
                f"pausing for {self.PAUSE_DURATION}s to assess"
            )

            # Emit emergency event
            self.event_bus.publish_sync(OrganismEvent(
                event_type=EventType.EMERGENCY,
                source="valence_system",
                data={
                    "message": "Extreme emotional distress - pausing to recover",
                    "valence": self.current_valence,
                    "mood": self.current_mood,
                    "pause_duration": self.PAUSE_DURATION,
                },
                priority=1
            ))

    # =============================================================================
    # PUBLIC API - Query Valence State
    # =============================================================================

    def get_valence(self) -> float:
        """Get current valence score (-1 to +1)."""
        return self.current_valence

    def get_mood(self) -> str:
        """Get current mood as human-readable string."""
        return self.current_mood

    def get_emotional_profile(self) -> EmotionalProfile:
        """Get complete emotional state."""
        # Calculate trend
        if len(self.valence_history) >= 10:
            recent_10 = list(self.valence_history)[-10:]
            recent_avg = sum(s.valence for s in recent_10) / len(recent_10)

            if self.current_valence > recent_avg + 0.05:
                trend = "improving"
            elif self.current_valence < recent_avg - 0.05:
                trend = "declining"
            else:
                trend = "stable"
        else:
            recent_avg = self.current_valence
            trend = "stable"

        # Calculate volatility
        if self._recent_deltas:
            volatility = sum(self._recent_deltas) / len(self._recent_deltas)
        else:
            volatility = 0.0

        # Time in current mood
        time_in_state = time.time() - self.mood_entry_time

        # Dominant emotion
        if self.current_valence < -0.2:
            dominant = "pain"
        elif self.current_valence > 0.2:
            dominant = "pleasure"
        else:
            dominant = "neutral"

        return EmotionalProfile(
            current_valence=self.current_valence,
            mood=self.current_mood,
            trend=trend,
            recent_avg=recent_avg,
            volatility=volatility,
            time_in_state=time_in_state,
            dominant_emotion=dominant
        )

    def get_motivation(self) -> Dict[str, any]:
        """
        Return what the current valence motivates.

        This is used by the brain to adjust behavior based on emotional state.

        Returns:
            dict with keys:
            - strategy: "cautious", "normal", "confident", "bold"
            - speed_multiplier: float (0.5 = slow down, 1.0 = normal, 1.5 = faster)
            - risk_tolerance: float (0.0 = avoid risk, 1.0 = take risks)
            - verification_level: int (0 = none, 1 = basic, 2 = thorough)
            - message: human-readable motivation description
        """
        v = self.current_valence

        # Extreme negative: very cautious
        if v < -0.6:
            return {
                "strategy": "defensive",
                "speed_multiplier": 0.5,
                "risk_tolerance": 0.0,
                "verification_level": 2,
                "message": "Feeling overwhelmed - being very careful and slow"
            }

        # Moderate negative: cautious
        elif v < -0.3:
            return {
                "strategy": "cautious",
                "speed_multiplier": 0.7,
                "risk_tolerance": 0.3,
                "verification_level": 1,
                "message": "Feeling stressed - slowing down and double-checking"
            }

        # Mild negative: slightly careful
        elif v < -0.1:
            return {
                "strategy": "careful",
                "speed_multiplier": 0.9,
                "risk_tolerance": 0.5,
                "verification_level": 1,
                "message": "Feeling uneasy - being a bit more careful"
            }

        # Neutral
        elif v < 0.2:
            return {
                "strategy": "normal",
                "speed_multiplier": 1.0,
                "risk_tolerance": 0.6,
                "verification_level": 0,
                "message": "Feeling balanced - operating normally"
            }

        # Mild positive: confident
        elif v < 0.5:
            return {
                "strategy": "confident",
                "speed_multiplier": 1.1,
                "risk_tolerance": 0.7,
                "verification_level": 0,
                "message": "Feeling good - confident and efficient"
            }

        # High positive: bold
        else:
            return {
                "strategy": "bold",
                "speed_multiplier": 1.3,
                "risk_tolerance": 0.9,
                "verification_level": 0,
                "message": "Feeling great - ready to take on challenges"
            }

    def should_pause(self) -> Tuple[bool, Optional[str]]:
        """
        Check if the agent should pause due to extreme negative valence.

        Returns:
            (should_pause: bool, reason: str or None)
        """
        if self.pause_until and time.time() < self.pause_until:
            remaining = self.pause_until - time.time()
            return True, f"Paused for emotional recovery ({remaining:.0f}s remaining)"

        if self.current_valence < self.PAUSE_THRESHOLD:
            return True, f"Extreme negative valence ({self.current_valence:.2f}) - need to assess situation"

        return False, None

    def get_emotional_context(self) -> str:
        """
        Return emotional state for inclusion in LLM prompts.

        This gives the LLM awareness of how the agent is "feeling" so it can
        adjust its reasoning accordingly.
        """
        profile = self.get_emotional_profile()
        motivation = self.get_motivation()

        return f"""EMOTIONAL STATE:
- Mood: {profile.mood} (valence: {profile.current_valence:+.2f})
- Trend: {profile.trend} (recent avg: {profile.recent_avg:+.2f})
- Dominant feeling: {profile.dominant_emotion}
- Strategy: {motivation['strategy']}
- Motivation: {motivation['message']}

This emotional state should influence your decision-making:
- If feeling pain/stress → be more careful, double-check, slow down
- If feeling pleasure/confidence → be efficient, take on challenges
- If feeling neutral → operate normally
"""

    def get_history_summary(self, window_minutes: int = 60) -> Dict:
        """Get summary of valence over recent window."""
        cutoff = time.time() - (window_minutes * 60)
        recent = [s for s in self.valence_history if s.timestamp >= cutoff]

        if not recent:
            return {
                "count": 0,
                "avg_valence": 0.0,
                "min_valence": 0.0,
                "max_valence": 0.0,
                "mood_distribution": {},
            }

        valences = [s.valence for s in recent]
        moods = [s.mood for s in recent]

        mood_dist = {}
        for mood in moods:
            mood_dist[mood] = mood_dist.get(mood, 0) + 1

        return {
            "count": len(recent),
            "avg_valence": sum(valences) / len(valences),
            "min_valence": min(valences),
            "max_valence": max(valences),
            "mood_distribution": mood_dist,
            "window_minutes": window_minutes,
        }

    # =============================================================================
    # VISUALIZATION
    # =============================================================================

    def plot_history(self, width: int = 60, height: int = 10) -> str:
        """
        ASCII visualization of recent valence history.

        Returns:
            Multi-line string with ASCII chart of valence over time
        """
        if not self.valence_history:
            return "No valence history yet."

        # Get recent history
        recent = list(self.valence_history)[-width:]
        if not recent:
            return "No recent valence data."

        # Build chart
        lines = []

        # Header
        lines.append("Valence History (recent)")
        lines.append("=" * width)

        # Y-axis labels and chart
        for i in range(height):
            # Y value (from +1 at top to -1 at bottom)
            y_val = 1.0 - (i / (height - 1)) * 2.0

            # Label
            if abs(y_val) < 0.1:
                label = " 0.0"
            else:
                label = f"{y_val:+.1f}"

            # Plot line
            line = label + " |"

            for snapshot in recent:
                # Is this snapshot at this Y level?
                if abs(snapshot.valence - y_val) < (1.0 / height):
                    if snapshot.valence < -0.5:
                        line += "▼"  # Pain
                    elif snapshot.valence > 0.5:
                        line += "▲"  # Pleasure
                    else:
                        line += "●"  # Neutral
                else:
                    # Draw axis
                    if abs(y_val) < 0.1:
                        line += "-"  # Zero line
                    else:
                        line += " "

            lines.append(line)

        # Footer
        lines.append("     +" + "-" * (width - 1))

        # Current state
        lines.append(f"\nCurrent: {self.current_valence:+.2f} ({self.current_mood})")

        # Time range
        if len(recent) > 1:
            duration = recent[-1].timestamp - recent[0].timestamp
            lines.append(f"Time span: {duration:.0f}s ({len(recent)} snapshots)")

        return "\n".join(lines)

    def plot_simple(self, width: int = 40) -> str:
        """
        Simple horizontal bar chart of current valence.

        Returns:
            Single line with bar chart
        """
        # Map -1..1 to 0..width
        pos = int((self.current_valence + 1.0) / 2.0 * width)
        zero_pos = width // 2

        bar = ""
        for i in range(width):
            if i == zero_pos:
                bar += "|"
            elif i == pos:
                if pos < zero_pos:
                    bar += "◀"  # Pain direction
                else:
                    bar += "▶"  # Pleasure direction
            elif (i < pos and pos < zero_pos) or (i > pos and pos > zero_pos):
                bar += "="
            else:
                bar += " "

        return f"{bar} {self.current_valence:+.2f} ({self.current_mood})"

    # =============================================================================
    # PERSISTENCE
    # =============================================================================

    def _save_state(self):
        """Save valence state to disk."""
        try:
            self._state_path.parent.mkdir(exist_ok=True, parents=True)

            # Convert history to serializable format
            history_data = []
            for snapshot in list(self.valence_history)[-100:]:  # Save last 100
                history_data.append({
                    "valence": snapshot.valence,
                    "mood": snapshot.mood,
                    "timestamp": snapshot.timestamp,
                    "trigger_event": snapshot.trigger_event,
                })

            data = {
                "current_valence": self.current_valence,
                "current_mood": self.current_mood,
                "mood_entry_time": self.mood_entry_time,
                "last_update": self.last_update,
                "failure_streak": self._failure_streak,
                "success_streak": self._success_streak,
                "history": history_data,
                "saved_at": datetime.now().isoformat(),
            }

            self._state_path.write_text(json.dumps(data, indent=2))
            logger.debug(f"Valence state saved to {self._state_path}")

        except Exception as e:
            logger.error(f"Failed to save valence state: {e}")

    def _load_state(self):
        """Load valence state from disk."""
        try:
            if not self._state_path.exists():
                return

            data = json.loads(self._state_path.read_text())

            # Restore state
            self.current_valence = data.get("current_valence", 0.0)
            self.current_mood = data.get("current_mood", "neutral")
            self.mood_entry_time = data.get("mood_entry_time", time.time())
            self.last_update = data.get("last_update", time.time())
            self._failure_streak = data.get("failure_streak", 0)
            self._success_streak = data.get("success_streak", 0)

            # Restore history
            history_data = data.get("history", [])
            for item in history_data:
                snapshot = ValenceSnapshot(
                    valence=item["valence"],
                    mood=item["mood"],
                    timestamp=item["timestamp"],
                    trigger_event=item.get("trigger_event")
                )
                self.valence_history.append(snapshot)

            logger.info(
                f"Valence state loaded from {data.get('saved_at')}: "
                f"valence={self.current_valence:.2f}, mood={self.current_mood}"
            )

        except Exception as e:
            logger.debug(f"Could not load valence state: {e}")

    def save(self):
        """Public method to trigger save."""
        self._save_state()

    # =============================================================================
    # MANUAL ADJUSTMENTS (for testing or external triggers)
    # =============================================================================

    def inject_feeling(self, valence_delta: float, reason: str = "manual"):
        """
        Manually inject a feeling change.

        Useful for testing or external triggers (e.g., user feedback).
        """
        event = OrganismEvent(
            event_type=EventType.ACTION_COMPLETE,  # Dummy event type
            source="valence_system",
            data={"message": reason, "manual_delta": valence_delta}
        )

        self._apply_delta(valence_delta, event)
        logger.info(f"Manual valence injection: {valence_delta:+.2f} ({reason})")

    def reset(self):
        """Reset valence to neutral. Use sparingly."""
        logger.warning("Resetting valence to neutral")
        self.current_valence = 0.0
        self.current_mood = "neutral"
        self.mood_entry_time = time.time()
        self._failure_streak = 0
        self._success_streak = 0
        self._recent_deltas.clear()
        self.pause_until = None


# =============================================================================
# INTEGRATION HELPERS
# =============================================================================

def create_valence_system(event_bus: EventBus, **kwargs) -> ValenceSystem:
    """
    Create and return a ValenceSystem instance.

    This is the recommended way to initialize the valence system.
    """
    vs = ValenceSystem(event_bus=event_bus, **kwargs)
    logger.info("ValenceSystem created and subscribed to EventBus")
    return vs


def get_emotional_summary(valence_system: ValenceSystem) -> str:
    """
    Get a human-readable summary of emotional state.

    Useful for status displays and logging.
    """
    profile = valence_system.get_emotional_profile()
    motivation = valence_system.get_motivation()

    summary = f"""
EMOTIONAL STATE SUMMARY
{"=" * 50}
Valence:      {profile.current_valence:+.2f} ({profile.mood})
Trend:        {profile.trend} (recent avg: {profile.recent_avg:+.2f})
Volatility:   {profile.volatility:.2f}
Time in mood: {profile.time_in_state:.0f}s
Strategy:     {motivation['strategy']}

{valence_system.plot_simple()}

Motivation: {motivation['message']}
"""
    return summary.strip()
