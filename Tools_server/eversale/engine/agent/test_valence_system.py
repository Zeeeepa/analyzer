"""
Test Suite for Valence System

Comprehensive tests for the emotional gradient system.
"""

import asyncio
import time
import pytest
from unittest.mock import Mock

from agent.organism_core import (
    EventBus, OrganismEvent, EventType, HeartbeatLoop
)
from agent.valence_system import (
    ValenceSystem, ValenceSnapshot, EmotionalProfile,
    create_valence_system, get_emotional_summary
)


class TestValenceBasics:
    """Test basic valence system functionality."""

    def test_initialization(self):
        """Test valence system initializes correctly."""
        event_bus = EventBus()
        valence = ValenceSystem(event_bus=event_bus)

        assert valence.current_valence == 0.0
        assert valence.current_mood == "neutral"
        assert len(valence.valence_history) == 0

    def test_create_valence_system(self):
        """Test factory function."""
        event_bus = EventBus()
        valence = create_valence_system(event_bus)

        assert valence is not None
        assert isinstance(valence, ValenceSystem)

    def test_get_valence(self):
        """Test getting current valence."""
        event_bus = EventBus()
        valence = ValenceSystem(event_bus=event_bus)

        assert valence.get_valence() == 0.0

    def test_get_mood(self):
        """Test getting current mood."""
        event_bus = EventBus()
        valence = ValenceSystem(event_bus=event_bus)

        assert valence.get_mood() == "neutral"


class TestValenceUpdates:
    """Test valence updates from events."""

    @pytest.mark.asyncio
    async def test_positive_event(self):
        """Test positive events increase valence."""
        event_bus = EventBus()
        valence = ValenceSystem(event_bus=event_bus)

        # Trigger positive event
        await event_bus.publish(OrganismEvent(
            event_type=EventType.ACTION_COMPLETE,
            source="test",
            data={"success": True}
        ))

        # Should increase valence
        assert valence.current_valence > 0.0

    @pytest.mark.asyncio
    async def test_negative_event(self):
        """Test negative events decrease valence."""
        event_bus = EventBus()
        valence = ValenceSystem(event_bus=event_bus)

        # Trigger negative event
        await event_bus.publish(OrganismEvent(
            event_type=EventType.ACTION_FAILED,
            source="test",
            data={"success": False}
        ))

        # Should decrease valence
        assert valence.current_valence < 0.0

    @pytest.mark.asyncio
    async def test_valence_clamping(self):
        """Test valence is clamped to [-1, 1]."""
        event_bus = EventBus()
        valence = ValenceSystem(event_bus=event_bus)

        # Trigger many positive events
        for _ in range(50):
            await event_bus.publish(OrganismEvent(
                event_type=EventType.ACTION_COMPLETE,
                source="test",
                data={"success": True}
            ))

        # Should not exceed 1.0
        assert valence.current_valence <= 1.0

        # Reset
        valence.reset()

        # Trigger many negative events
        for _ in range(50):
            await event_bus.publish(OrganismEvent(
                event_type=EventType.ACTION_FAILED,
                source="test",
                data={"success": False}
            ))

        # Should not go below -1.0
        assert valence.current_valence >= -1.0

    @pytest.mark.asyncio
    async def test_streak_tracking(self):
        """Test failure/success streaks compound effects."""
        event_bus = EventBus()
        valence = ValenceSystem(event_bus=event_bus)

        # Track valence change from single failure
        await event_bus.publish(OrganismEvent(
            event_type=EventType.ACTION_FAILED,
            source="test",
            data={"success": False}
        ))
        single_failure_delta = valence.current_valence

        # Reset
        valence.reset()

        # Trigger failure streak (5 failures)
        for _ in range(5):
            await event_bus.publish(OrganismEvent(
                event_type=EventType.ACTION_FAILED,
                source="test",
                data={"success": False}
            ))

        # Streak should cause more pain than 5x single failure
        # (due to compounding)
        assert valence.current_valence < single_failure_delta * 5


class TestValenceDecay:
    """Test valence decay toward neutral."""

    def test_decay_positive(self):
        """Test positive valence decays toward zero."""
        event_bus = EventBus()
        valence = ValenceSystem(event_bus=event_bus, decay_rate=0.9)

        # Set positive valence
        valence.current_valence = 0.5

        # Trigger decay
        for _ in range(10):
            valence._decay()

        # Should be closer to zero
        assert valence.current_valence < 0.5
        assert valence.current_valence >= 0.0

    def test_decay_negative(self):
        """Test negative valence decays toward zero."""
        event_bus = EventBus()
        valence = ValenceSystem(event_bus=event_bus, decay_rate=0.9)

        # Set negative valence
        valence.current_valence = -0.5

        # Trigger decay
        for _ in range(10):
            valence._decay()

        # Should be closer to zero
        assert valence.current_valence > -0.5
        assert valence.current_valence <= 0.0

    def test_decay_to_zero(self):
        """Test valence eventually reaches zero."""
        event_bus = EventBus()
        valence = ValenceSystem(event_bus=event_bus, decay_rate=0.95)

        # Set valence
        valence.current_valence = 0.8

        # Decay for long time
        for _ in range(200):
            valence._decay()

        # Should be essentially zero
        assert abs(valence.current_valence) < 0.01


class TestMoodCalculation:
    """Test mood calculation from valence."""

    def test_mood_thresholds(self):
        """Test mood changes at different valence levels."""
        event_bus = EventBus()
        valence = ValenceSystem(event_bus=event_bus)

        test_cases = [
            (-0.9, "devastated"),
            (-0.5, "struggling"),
            (-0.2, "stressed"),
            (0.0, "neutral"),
            (0.2, "content"),
            (0.5, "thriving"),
            (0.9, "euphoric"),
        ]

        for valence_value, expected_mood in test_cases:
            valence.current_valence = valence_value
            mood = valence._calculate_mood()
            assert mood == expected_mood, f"Valence {valence_value} should be {expected_mood}, got {mood}"

    def test_mood_transitions(self):
        """Test mood updates when crossing thresholds."""
        event_bus = EventBus()
        valence = ValenceSystem(event_bus=event_bus)

        # Start neutral
        assert valence.current_mood == "neutral"

        # Move to positive
        valence.current_valence = 0.5
        new_mood = valence._calculate_mood()
        assert new_mood == "thriving"

        # Move to negative
        valence.current_valence = -0.5
        new_mood = valence._calculate_mood()
        assert new_mood == "struggling"


class TestMotivation:
    """Test motivation system."""

    def test_motivation_strategies(self):
        """Test different strategies based on valence."""
        event_bus = EventBus()
        valence = ValenceSystem(event_bus=event_bus)

        # Extreme negative → defensive
        valence.current_valence = -0.8
        motivation = valence.get_motivation()
        assert motivation["strategy"] == "defensive"
        assert motivation["speed_multiplier"] < 1.0
        assert motivation["risk_tolerance"] < 0.5

        # Moderate negative → cautious
        valence.current_valence = -0.4
        motivation = valence.get_motivation()
        assert motivation["strategy"] == "cautious"
        assert motivation["speed_multiplier"] < 1.0

        # Neutral → normal
        valence.current_valence = 0.0
        motivation = valence.get_motivation()
        assert motivation["strategy"] == "normal"
        assert motivation["speed_multiplier"] == 1.0

        # Positive → confident
        valence.current_valence = 0.4
        motivation = valence.get_motivation()
        assert motivation["strategy"] == "confident"
        assert motivation["speed_multiplier"] > 1.0

        # High positive → bold
        valence.current_valence = 0.8
        motivation = valence.get_motivation()
        assert motivation["strategy"] == "bold"
        assert motivation["risk_tolerance"] > 0.8

    def test_risk_tolerance(self):
        """Test risk tolerance scales with valence."""
        event_bus = EventBus()
        valence = ValenceSystem(event_bus=event_bus)

        # Negative valence → low risk
        valence.current_valence = -0.6
        motivation = valence.get_motivation()
        assert motivation["risk_tolerance"] < 0.5

        # Positive valence → high risk
        valence.current_valence = 0.6
        motivation = valence.get_motivation()
        assert motivation["risk_tolerance"] > 0.5


class TestPauseLogic:
    """Test pause/emergency logic."""

    def test_should_pause_threshold(self):
        """Test pause trigger at extreme negative valence."""
        event_bus = EventBus()
        valence = ValenceSystem(event_bus=event_bus)

        # Above threshold → no pause
        valence.current_valence = -0.5
        should_pause, reason = valence.should_pause()
        assert should_pause is False

        # Below threshold → pause
        valence.current_valence = -0.8
        should_pause, reason = valence.should_pause()
        assert should_pause is True
        assert reason is not None

    @pytest.mark.asyncio
    async def test_pause_event_emission(self):
        """Test emergency event emitted on extreme valence."""
        event_bus = EventBus()
        valence = ValenceSystem(event_bus=event_bus)

        emergency_events = []

        def capture_emergency(event: OrganismEvent):
            if event.event_type == EventType.EMERGENCY:
                emergency_events.append(event)

        event_bus.subscribe(EventType.EMERGENCY, capture_emergency)

        # Trigger extreme negative valence
        valence.current_valence = -0.8
        valence.mood_entry_time = time.time() - 20  # Sustained

        # Trigger pause check
        valence._consider_pause()

        # Should have emitted emergency
        assert len(emergency_events) > 0


class TestEmotionalProfile:
    """Test emotional profile generation."""

    @pytest.mark.asyncio
    async def test_profile_generation(self):
        """Test generating emotional profile."""
        event_bus = EventBus()
        valence = ValenceSystem(event_bus=event_bus)

        # Add some history
        for i in range(10):
            delta = 0.1 if i % 2 == 0 else -0.05
            valence.current_valence = max(-1, min(1, valence.current_valence + delta))
            valence.valence_history.append(ValenceSnapshot(
                valence=valence.current_valence,
                mood=valence._calculate_mood(),
                timestamp=time.time()
            ))

        profile = valence.get_emotional_profile()

        assert isinstance(profile, EmotionalProfile)
        assert profile.current_valence == valence.current_valence
        assert profile.mood == valence.current_mood
        assert profile.trend in ["improving", "declining", "stable"]
        assert profile.dominant_emotion in ["pain", "pleasure", "neutral"]

    def test_trend_calculation(self):
        """Test trend detection."""
        event_bus = EventBus()
        valence = ValenceSystem(event_bus=event_bus)

        # Create improving trend
        for i in range(10):
            valence.current_valence = i * 0.05  # 0, 0.05, 0.10, ...
            valence.valence_history.append(ValenceSnapshot(
                valence=valence.current_valence,
                mood=valence._calculate_mood()
            ))

        profile = valence.get_emotional_profile()
        assert profile.trend == "improving"

        # Reset and create declining trend
        valence.valence_history.clear()
        for i in range(10):
            valence.current_valence = 0.5 - (i * 0.05)  # 0.5, 0.45, 0.40, ...
            valence.valence_history.append(ValenceSnapshot(
                valence=valence.current_valence,
                mood=valence._calculate_mood()
            ))

        profile = valence.get_emotional_profile()
        assert profile.trend == "declining"


class TestVisualization:
    """Test ASCII visualization."""

    def test_plot_simple(self):
        """Test simple bar chart."""
        event_bus = EventBus()
        valence = ValenceSystem(event_bus=event_bus)

        # Neutral
        valence.current_valence = 0.0
        plot = valence.plot_simple(width=40)
        assert "|" in plot  # Zero marker
        assert "0.00" in plot

        # Positive
        valence.current_valence = 0.5
        plot = valence.plot_simple(width=40)
        assert "▶" in plot  # Right arrow
        assert "+0.5" in plot

        # Negative
        valence.current_valence = -0.5
        plot = valence.plot_simple(width=40)
        assert "◀" in plot  # Left arrow
        assert "-0.5" in plot

    def test_plot_history(self):
        """Test history visualization."""
        event_bus = EventBus()
        valence = ValenceSystem(event_bus=event_bus)

        # Add some history
        for i in range(20):
            valence.valence_history.append(ValenceSnapshot(
                valence=(i - 10) * 0.05,  # -0.5 to +0.5
                mood="neutral"
            ))

        plot = valence.plot_history(width=30, height=10)
        assert "Valence History" in plot
        assert "Current:" in plot
        assert len(plot.split("\n")) > 5  # Multi-line chart

    def test_emotional_context(self):
        """Test emotional context string."""
        event_bus = EventBus()
        valence = ValenceSystem(event_bus=event_bus)

        valence.current_valence = 0.3

        context = valence.get_emotional_context()
        assert "EMOTIONAL STATE" in context
        assert "Mood:" in context
        assert "Strategy:" in context
        assert "Motivation:" in context


class TestPersistence:
    """Test state persistence."""

    def test_save_and_load(self, tmp_path):
        """Test saving and loading state."""
        state_file = tmp_path / "valence_test.json"

        # Create and populate valence system
        event_bus = EventBus()
        valence1 = ValenceSystem(
            event_bus=event_bus,
            persistence_path=str(state_file)
        )

        valence1.current_valence = 0.42
        valence1.current_mood = "content"
        valence1._failure_streak = 2
        valence1._success_streak = 5

        # Add some history
        for i in range(5):
            valence1.valence_history.append(ValenceSnapshot(
                valence=i * 0.1,
                mood="neutral"
            ))

        # Save
        valence1._save_state()
        assert state_file.exists()

        # Create new instance and load
        valence2 = ValenceSystem(
            event_bus=event_bus,
            persistence_path=str(state_file)
        )

        # Should restore state
        assert abs(valence2.current_valence - 0.42) < 0.01
        assert valence2.current_mood == "content"
        assert valence2._failure_streak == 2
        assert valence2._success_streak == 5
        assert len(valence2.valence_history) == 5


class TestHistorySummary:
    """Test history summary generation."""

    def test_summary_empty(self):
        """Test summary with no history."""
        event_bus = EventBus()
        valence = ValenceSystem(event_bus=event_bus)

        summary = valence.get_history_summary()
        assert summary["count"] == 0
        assert summary["avg_valence"] == 0.0

    def test_summary_with_data(self):
        """Test summary with history."""
        event_bus = EventBus()
        valence = ValenceSystem(event_bus=event_bus)

        # Add history
        for i in range(10):
            valence.valence_history.append(ValenceSnapshot(
                valence=(i - 5) * 0.1,  # -0.5 to +0.4
                mood="neutral",
                timestamp=time.time()
            ))

        summary = valence.get_history_summary(window_minutes=1)
        assert summary["count"] == 10
        assert summary["avg_valence"] != 0.0
        assert summary["min_valence"] <= summary["max_valence"]


class TestManualAdjustments:
    """Test manual valence adjustments."""

    def test_inject_feeling(self):
        """Test manually injecting a feeling."""
        event_bus = EventBus()
        valence = ValenceSystem(event_bus=event_bus)

        # Inject positive feeling
        valence.inject_feeling(+0.3, reason="test")
        assert valence.current_valence == 0.3

        # Inject negative feeling
        valence.inject_feeling(-0.5, reason="test")
        assert valence.current_valence < 0.0

    def test_reset(self):
        """Test resetting to neutral."""
        event_bus = EventBus()
        valence = ValenceSystem(event_bus=event_bus)

        # Set non-neutral state
        valence.current_valence = 0.7
        valence.current_mood = "thriving"
        valence._failure_streak = 5

        # Reset
        valence.reset()

        assert valence.current_valence == 0.0
        assert valence.current_mood == "neutral"
        assert valence._failure_streak == 0
        assert len(valence._recent_deltas) == 0


class TestIntegrationWithOrganism:
    """Test integration with organism core."""

    @pytest.mark.asyncio
    async def test_event_subscription(self):
        """Test valence subscribes to all events."""
        event_bus = EventBus()
        valence = ValenceSystem(event_bus=event_bus)

        initial_valence = valence.current_valence

        # Emit various events
        await event_bus.publish(OrganismEvent(
            event_type=EventType.ACTION_COMPLETE,
            source="test",
            data={"success": True}
        ))

        # Valence should have changed
        assert valence.current_valence != initial_valence

    @pytest.mark.asyncio
    async def test_heartbeat_integration(self):
        """Test valence integrates with heartbeat."""
        event_bus = EventBus()
        valence = ValenceSystem(event_bus=event_bus)

        # Set non-zero valence
        valence.current_valence = 0.5

        # Emit heartbeat events (triggers decay)
        for _ in range(10):
            await event_bus.publish(OrganismEvent(
                event_type=EventType.HEARTBEAT,
                source="heartbeat",
                data={"beat": 1}
            ))

        # Valence should have decayed
        assert valence.current_valence < 0.5


class TestHelperFunctions:
    """Test helper functions."""

    def test_get_emotional_summary(self):
        """Test emotional summary generation."""
        event_bus = EventBus()
        valence = ValenceSystem(event_bus=event_bus)

        valence.current_valence = 0.3

        summary = get_emotional_summary(valence)
        assert "EMOTIONAL STATE SUMMARY" in summary
        assert "Valence:" in summary
        assert "Strategy:" in summary
        assert len(summary) > 0


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
