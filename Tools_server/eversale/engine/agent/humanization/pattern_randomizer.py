"""
Pattern Randomizer - Prevent detection through behavioral pattern analysis

Anti-bot systems look for:
1. Consistent timing patterns (always 100-200ms between actions)
2. Perfect Bezier curves (too smooth)
3. Uniform typing speeds
4. Predictable scroll amounts
5. Regular intervals between operations

This module adds entropy to ALL patterns so no two sessions look alike.

Key techniques:
- Session-based randomization (different each run)
- Micro-variations within actions
- Occasional "human mistakes" (overshoots, pauses, corrections)
- Non-uniform distributions (not just random.uniform)
- Fatigue simulation (slows down over time)
"""

import random
import time
import math
from typing import Tuple, Optional, Callable
from dataclasses import dataclass
from loguru import logger


@dataclass
class RandomizerConfig:
    """Configuration for pattern randomization"""
    # Session seed (changes behavior per session)
    session_seed: Optional[str] = None

    # Timing randomization
    timing_variance: float = 0.4  # ±40% timing variation
    occasional_pause_chance: float = 0.08  # 8% chance of random pause
    pause_duration_range: Tuple[float, float] = (0.3, 1.5)  # seconds

    # Mouse randomization
    curve_jitter: float = 0.15  # 15% variation in curve shape
    overshoot_chance: float = 0.12  # 12% chance of overshoot
    micro_movement_chance: float = 0.05  # 5% chance of tiny random movement

    # Typing randomization
    typo_rate_variance: float = 0.5  # ±50% variation in error rate
    speed_burst_chance: float = 0.15  # 15% chance of speed burst
    hesitation_chance: float = 0.1  # 10% chance of mid-word hesitation

    # Scroll randomization
    scroll_variance: float = 0.3  # ±30% scroll amount variation
    reverse_scroll_chance: float = 0.03  # 3% chance of slight reverse

    # Fatigue simulation
    fatigue_enabled: bool = True
    fatigue_onset_minutes: float = 5.0  # Start slowing after 5 min
    max_fatigue_slowdown: float = 0.3  # Max 30% slowdown


class PatternRandomizer:
    """
    Adds entropy to all behavioral patterns.

    Every session is different. Every action has micro-variations.
    Patterns are impossible to fingerprint.

    Example:
        randomizer = PatternRandomizer()

        # Randomize a delay
        delay = randomizer.randomize_delay(100, 200)  # Not just uniform(100,200)

        # Add occasional pause
        if randomizer.should_pause():
            await asyncio.sleep(randomizer.get_pause_duration())

        # Get fatigue multiplier
        multiplier = randomizer.get_fatigue_multiplier()
    """

    def __init__(self, config: Optional[RandomizerConfig] = None):
        self.config = config or RandomizerConfig()

        # Initialize session
        self._session_start = time.time()
        self._action_count = 0

        # Session seed affects all randomization
        if self.config.session_seed:
            random.seed(hash(self.config.session_seed) % (2**32))
        else:
            # Use time-based seed for different sessions
            random.seed(int(time.time() * 1000) % (2**32))

        # Pre-generate some session-specific parameters
        self._session_params = self._generate_session_params()

    def _generate_session_params(self) -> dict:
        """Generate session-specific parameters that stay consistent within session"""
        return {
            # This session's base typing speed modifier
            "typing_speed_mod": random.uniform(0.8, 1.2),

            # This session's preferred scroll amount
            "scroll_preference": random.uniform(0.85, 1.15),

            # This session's mouse smoothness
            "mouse_smoothness": random.uniform(0.9, 1.1),

            # This session's pause frequency
            "pause_frequency": random.uniform(0.7, 1.3),

            # Dominant hand simulation (affects click offset bias)
            "right_handed": random.random() > 0.1,  # 90% right-handed

            # Reading speed (affects time on page)
            "reading_speed": random.uniform(0.7, 1.4),
        }

    def get_fatigue_multiplier(self) -> float:
        """
        Get fatigue multiplier based on session duration.
        Actions slow down over time (like real humans).
        """
        if not self.config.fatigue_enabled:
            return 1.0

        session_minutes = (time.time() - self._session_start) / 60

        if session_minutes < self.config.fatigue_onset_minutes:
            return 1.0

        # Gradual fatigue buildup
        fatigue_progress = (session_minutes - self.config.fatigue_onset_minutes) / 30  # Full fatigue in 30 min
        fatigue_progress = min(fatigue_progress, 1.0)

        # Sigmoid curve for natural fatigue
        fatigue = 1 / (1 + math.exp(-5 * (fatigue_progress - 0.5)))
        fatigue_multiplier = 1 + (fatigue * self.config.max_fatigue_slowdown)

        return fatigue_multiplier

    def randomize_delay(self, min_ms: float, max_ms: float) -> float:
        """
        Randomize a delay with non-uniform distribution.
        Not just uniform - uses mixture of distributions.
        """
        base_delay = random.uniform(min_ms, max_ms)

        # Apply variance
        variance = base_delay * self.config.timing_variance
        delay = base_delay + random.gauss(0, variance / 3)  # Gaussian, not uniform

        # Occasional longer pause (human distraction)
        if random.random() < self.config.occasional_pause_chance * self._session_params["pause_frequency"]:
            pause_ms = random.uniform(*self.config.pause_duration_range) * 1000
            delay += pause_ms

        # Apply fatigue
        delay *= self.get_fatigue_multiplier()

        # Never negative
        return max(1, delay)

    def should_pause(self) -> bool:
        """Check if we should add a random pause"""
        return random.random() < self.config.occasional_pause_chance * self._session_params["pause_frequency"]

    def get_pause_duration(self) -> float:
        """Get duration of random pause in seconds"""
        base = random.uniform(*self.config.pause_duration_range)
        # Sometimes longer pauses (checking phone, etc.)
        if random.random() < 0.1:
            base *= random.uniform(2, 5)
        return base

    def randomize_curve_parameters(
        self,
        knots: int,
        offset_x: float,
        offset_y: float
    ) -> Tuple[int, float, float]:
        """
        Randomize Bezier curve parameters.
        Each curve is slightly different.
        """
        # Vary knot count
        knot_variance = max(1, int(knots * self.config.curve_jitter))
        new_knots = knots + random.randint(-knot_variance, knot_variance)
        new_knots = max(1, min(5, new_knots))  # Clamp 1-5

        # Vary offset boundaries
        smoothness = self._session_params["mouse_smoothness"]
        new_offset_x = offset_x * random.uniform(0.7, 1.3) * smoothness
        new_offset_y = offset_y * random.uniform(0.7, 1.3) * smoothness

        return new_knots, new_offset_x, new_offset_y

    def should_overshoot(self) -> bool:
        """Check if cursor should overshoot target"""
        return random.random() < self.config.overshoot_chance

    def get_overshoot_amount(self, distance: float) -> float:
        """Get overshoot distance in pixels"""
        # Overshoot proportional to movement distance
        base_overshoot = min(distance * 0.1, 30)  # Max 30px or 10% of distance
        return base_overshoot * random.uniform(0.5, 1.5)

    def should_micro_move(self) -> bool:
        """Check if we should add tiny random cursor movement"""
        return random.random() < self.config.micro_movement_chance

    def get_micro_movement(self) -> Tuple[float, float]:
        """Get small random movement (pixel jitter)"""
        return (
            random.gauss(0, 3),  # Small gaussian offset
            random.gauss(0, 3)
        )

    def get_click_offset(self, width: float, height: float) -> Tuple[float, float]:
        """
        Get humanized click offset within element.
        Right-handed bias, slight center tendency.
        """
        # Gaussian offset (most clicks near center)
        offset_x = random.gauss(0, width * 0.15)
        offset_y = random.gauss(0, height * 0.15)

        # Right-handed bias (slightly right of center)
        if self._session_params["right_handed"]:
            offset_x += width * 0.05 * random.uniform(0, 1)

        # Clamp to element
        max_x = width * 0.4
        max_y = height * 0.4
        offset_x = max(-max_x, min(max_x, offset_x))
        offset_y = max(-max_y, min(max_y, offset_y))

        return offset_x, offset_y

    def randomize_typing_speed(self, base_cpm: int) -> int:
        """Randomize typing speed for this session"""
        # Apply session modifier
        cpm = base_cpm * self._session_params["typing_speed_mod"]

        # Random burst or slowdown
        if random.random() < self.config.speed_burst_chance:
            cpm *= random.uniform(1.2, 1.5)  # Speed burst
        elif random.random() < 0.1:
            cpm *= random.uniform(0.6, 0.8)  # Slowdown

        return int(cpm)

    def should_hesitate(self) -> bool:
        """Check if should hesitate mid-word"""
        return random.random() < self.config.hesitation_chance

    def get_hesitation_duration(self) -> float:
        """Get hesitation pause in seconds"""
        return random.uniform(0.15, 0.5)

    def randomize_typo_rate(self, base_rate: float) -> float:
        """Randomize typo rate for this session"""
        variance = base_rate * self.config.typo_rate_variance
        rate = base_rate + random.uniform(-variance, variance)
        return max(0, min(0.15, rate))  # Clamp 0-15%

    def randomize_scroll_amount(self, base_pixels: int) -> int:
        """Randomize scroll amount"""
        # Apply session preference
        pixels = base_pixels * self._session_params["scroll_preference"]

        # Add variance
        variance = pixels * self.config.scroll_variance
        pixels += random.gauss(0, variance / 2)

        return max(50, int(pixels))  # Minimum 50px

    def should_reverse_scroll(self) -> bool:
        """Check if should do slight reverse scroll (reading back)"""
        return random.random() < self.config.reverse_scroll_chance

    def get_reverse_scroll_amount(self, forward_amount: int) -> int:
        """Get amount to scroll back"""
        return int(forward_amount * random.uniform(0.1, 0.3))

    def randomize_reading_time(self, base_seconds: float) -> float:
        """Randomize time spent 'reading' page"""
        return base_seconds * self._session_params["reading_speed"] * random.uniform(0.8, 1.2)

    def increment_action(self):
        """Track action count for patterns"""
        self._action_count += 1

        # Every ~20 actions, slight behavior shift (attention span)
        if self._action_count % 20 == 0:
            self._session_params["pause_frequency"] *= random.uniform(0.9, 1.1)

    def get_stats(self) -> dict:
        """Get randomizer statistics"""
        return {
            "session_duration_min": (time.time() - self._session_start) / 60,
            "action_count": self._action_count,
            "fatigue_multiplier": self.get_fatigue_multiplier(),
            "session_params": self._session_params,
        }


# Global randomizer
_global_randomizer: Optional[PatternRandomizer] = None


def get_randomizer() -> PatternRandomizer:
    """Get or create global randomizer"""
    global _global_randomizer
    if _global_randomizer is None:
        _global_randomizer = PatternRandomizer()
    return _global_randomizer


def new_session():
    """Start new randomization session (different patterns)"""
    global _global_randomizer
    _global_randomizer = PatternRandomizer()
    logger.debug("Started new randomization session")


# Convenience functions
def randomize_delay(min_ms: float, max_ms: float) -> float:
    """Randomize a delay"""
    return get_randomizer().randomize_delay(min_ms, max_ms)


def should_pause() -> bool:
    """Check if should add random pause"""
    return get_randomizer().should_pause()


def get_pause() -> float:
    """Get random pause duration"""
    return get_randomizer().get_pause_duration()
