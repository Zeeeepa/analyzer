"""
Human-Like Typing - Realistic keyboard input with errors and corrections

Based on research from:
- human-keyboard: Fatigue modeling and error patterns
- Typoist: Academic research on typing errors
- Human-Typer: QWERTY neighbor substitution errors

Key features:
- QWERTY neighbor key errors (realistic typos)
- Error injection with backspace corrections
- Fatigue modeling (typing slows over time)
- Context-aware delays (longer after punctuation)
- Variable characters-per-minute (CPM)
- Thinking pauses at word boundaries
"""

import asyncio
import random
from typing import Optional, Dict, List
from dataclasses import dataclass, field
from loguru import logger


@dataclass
class TypingConfig:
    """Configuration for typing behavior"""
    # Speed (characters per minute)
    cpm_base: int = 280  # Average human typing speed
    cpm_variance: int = 40  # Speed variation

    # Error injection
    error_rate: float = 0.01  # 1% error rate (realistic human range: 0.5-1.5%)
    correction_rate: float = 0.85  # 85% of errors get corrected

    # Timing
    thinking_delay_min: int = 150  # ms pause at word boundaries
    thinking_delay_max: int = 400
    punctuation_delay_multiplier: float = 1.5  # Longer pause after .!?

    # Fatigue
    fatigue_enabled: bool = True
    fatigue_increase: float = 0.001  # Per keystroke
    fatigue_max: float = 1.5  # Maximum 50% slowdown
    fatigue_recovery: float = 0.02  # Recovery during pauses

    # FAST_TRACK mode - Skip humanization for high-volume tasks
    fast_track: bool = False  # When True: instant typing, no delays, no errors


# QWERTY keyboard neighbor map for realistic typos
QWERTY_NEIGHBORS: Dict[str, List[str]] = {
    'a': ['q', 'w', 's', 'z'],
    'b': ['v', 'g', 'h', 'n'],
    'c': ['x', 'd', 'f', 'v'],
    'd': ['s', 'e', 'r', 'f', 'c', 'x'],
    'e': ['w', 's', 'd', 'r', '3', '4'],
    'f': ['d', 'r', 't', 'g', 'v', 'c'],
    'g': ['f', 't', 'y', 'h', 'b', 'v'],
    'h': ['g', 'y', 'u', 'j', 'n', 'b'],
    'i': ['u', 'j', 'k', 'o', '8', '9'],
    'j': ['h', 'u', 'i', 'k', 'm', 'n'],
    'k': ['j', 'i', 'o', 'l', 'm', ','],
    'l': ['k', 'o', 'p', ';', '.', ','],
    'm': ['n', 'j', 'k', ','],
    'n': ['b', 'h', 'j', 'm'],
    'o': ['i', 'k', 'l', 'p', '9', '0'],
    'p': ['o', 'l', ';', '[', '0', '-'],
    'q': ['1', '2', 'w', 'a'],
    'r': ['e', 'd', 'f', 't', '4', '5'],
    's': ['a', 'w', 'e', 'd', 'x', 'z'],
    't': ['r', 'f', 'g', 'y', '5', '6'],
    'u': ['y', 'h', 'j', 'i', '7', '8'],
    'v': ['c', 'f', 'g', 'b'],
    'w': ['q', 'a', 's', 'e', '2', '3'],
    'x': ['z', 's', 'd', 'c'],
    'y': ['t', 'g', 'h', 'u', '6', '7'],
    'z': ['a', 's', 'x'],
    '1': ['`', '2', 'q'],
    '2': ['1', '3', 'q', 'w'],
    '3': ['2', '4', 'w', 'e'],
    '4': ['3', '5', 'e', 'r'],
    '5': ['4', '6', 'r', 't'],
    '6': ['5', '7', 't', 'y'],
    '7': ['6', '8', 'y', 'u'],
    '8': ['7', '9', 'u', 'i'],
    '9': ['8', '0', 'i', 'o'],
    '0': ['9', '-', 'o', 'p'],
}


class HumanTyper:
    """
    Types text with human-like patterns including errors and corrections.

    Example:
        typer = HumanTyper()
        await typer.type_text(page, "Hello world!", selector="#input")
    """

    def __init__(self, config: Optional[TypingConfig] = None):
        self.config = config or TypingConfig()
        self.fatigue = 1.0
        self._char_count = 0
        self._fast_track_logged = False  # Track if we've logged FAST_TRACK activation

    def get_keystroke_delay(self) -> float:
        """
        Calculate delay between keystrokes with variance and fatigue.

        Returns:
            Delay in seconds
        """
        # Calculate base delay from CPM with variance
        effective_cpm = self.config.cpm_base + random.uniform(
            -self.config.cpm_variance,
            self.config.cpm_variance
        )
        base_delay = 60.0 / effective_cpm

        # Apply fatigue
        if self.config.fatigue_enabled:
            delay = base_delay * self.fatigue
        else:
            delay = base_delay

        # Add some randomness to each keystroke
        delay *= random.uniform(0.7, 1.3)

        return delay

    def should_make_error(self) -> bool:
        """Determine if an error should occur."""
        # Error rate increases slightly with fatigue
        adjusted_rate = self.config.error_rate * (0.8 + self.fatigue * 0.4)
        return random.random() < adjusted_rate

    def get_error_char(self, intended_char: str) -> str:
        """
        Get a realistic error character based on QWERTY layout.
        Returns a neighboring key for realistic typos.
        """
        char_lower = intended_char.lower()
        neighbors = QWERTY_NEIGHBORS.get(char_lower, [])

        if neighbors:
            error_char = random.choice(neighbors)
            # Preserve case
            if intended_char.isupper():
                return error_char.upper()
            return error_char

        # No neighbors defined, return same char (won't make error)
        return intended_char

    def should_correct_error(self) -> bool:
        """Determine if error should be corrected."""
        return random.random() < self.config.correction_rate

    def update_fatigue(self, is_pause: bool = False):
        """Update fatigue level based on typing."""
        if not self.config.fatigue_enabled:
            return

        if is_pause:
            # Recover during pauses
            self.fatigue = max(1.0, self.fatigue - self.config.fatigue_recovery)
        else:
            # Increase fatigue while typing
            self.fatigue = min(self.config.fatigue_max,
                             self.fatigue + self.config.fatigue_increase)
            self._char_count += 1

    def get_context_delay(self, char: str, prev_char: Optional[str]) -> float:
        """
        Get additional delay based on character context.

        Args:
            char: Current character
            prev_char: Previous character

        Returns:
            Additional delay in seconds
        """
        extra_delay = 0.0

        # Longer pause after sentence-ending punctuation
        if prev_char in '.!?':
            extra_delay += random.uniform(0.2, 0.5)
            self.update_fatigue(is_pause=True)  # Mental rest

        # Pause after comma (thinking)
        elif prev_char == ',':
            extra_delay += random.uniform(0.1, 0.25)

        # Space = word boundary, small thinking pause
        elif char == ' ':
            if random.random() < 0.3:  # 30% chance of thinking pause
                extra_delay += random.uniform(
                    self.config.thinking_delay_min / 1000,
                    self.config.thinking_delay_max / 1000
                )
                self.update_fatigue(is_pause=True)

        # Slight pause before capital letters (shift key)
        elif char.isupper() and char.isalpha():
            extra_delay += random.uniform(0.02, 0.06)

        return extra_delay

    async def type_char(self, page, char: str):
        """Type a single character."""
        if char == '\n':
            await page.keyboard.press('Enter')
        elif char == '\t':
            await page.keyboard.press('Tab')
        else:
            await page.keyboard.type(char)

    async def type_text(
        self,
        page,
        text: str,
        selector: Optional[str] = None,
        clear_first: bool = True
    ) -> bool:
        """
        Type text with human-like patterns.

        Args:
            page: Playwright page object
            text: Text to type
            selector: Optional selector to click first
            clear_first: Whether to clear existing content

        Returns:
            True if typing succeeded
        """
        try:
            # FAST_TRACK mode: Instant typing with no delays
            if self.config.fast_track:
                if not self._fast_track_logged:
                    logger.info("FAST_TRACK mode enabled: Using instant typing (no humanization)")
                    self._fast_track_logged = True

                if selector:
                    element = await page.query_selector(selector)
                    if not element:
                        logger.debug(f"Element not found: {selector}")
                        return False
                    await element.click()
                    await asyncio.sleep(0.01)  # Minimal delay for reliability

                if clear_first:
                    await page.keyboard.press('Control+a')
                    await asyncio.sleep(0.01)
                    await page.keyboard.press('Backspace')
                    await asyncio.sleep(0.01)

                # Type entire text at once
                await page.keyboard.type(text)
                return True

            # Click to focus if selector provided
            if selector:
                element = await page.query_selector(selector)
                if not element:
                    logger.debug(f"Element not found: {selector}")
                    return False
                await element.click()
                await asyncio.sleep(random.uniform(0.05, 0.15))

            # Clear existing content if requested
            if clear_first:
                await page.keyboard.press('Control+a')
                await asyncio.sleep(random.uniform(0.03, 0.08))
                await page.keyboard.press('Backspace')
                await asyncio.sleep(random.uniform(0.05, 0.12))

            # Reset fatigue for new typing session
            self.fatigue = 1.0
            self._char_count = 0

            prev_char = None

            for i, char in enumerate(text):
                # Check if we should make an error
                if self.should_make_error() and len(text) > 5:
                    error_char = self.get_error_char(char)

                    if error_char != char:  # Actually different
                        # Type wrong character
                        await self.type_char(page, error_char)
                        await asyncio.sleep(self.get_keystroke_delay())

                        # Pause to "notice" the error
                        await asyncio.sleep(random.uniform(0.15, 0.35))

                        # Maybe correct it
                        if self.should_correct_error():
                            await page.keyboard.press('Backspace')
                            await asyncio.sleep(self.get_keystroke_delay())
                            # Now type correct character
                            await self.type_char(page, char)
                        else:
                            # Don't correct - continue (uncorrected error)
                            self.update_fatigue()
                            prev_char = error_char
                            continue

                # Type the actual character
                await self.type_char(page, char)

                # Calculate delay
                base_delay = self.get_keystroke_delay()
                context_delay = self.get_context_delay(char, prev_char)
                total_delay = base_delay + context_delay

                await asyncio.sleep(total_delay)

                # Update state
                self.update_fatigue()
                prev_char = char

            return True

        except Exception as e:
            logger.debug(f"Typing failed: {e}")
            return False

    async def type_slowly(self, page, text: str, selector: Optional[str] = None) -> bool:
        """Type at a slower pace (for careful input like passwords)."""
        original_cpm = self.config.cpm_base
        original_error_rate = self.config.error_rate
        self.config.cpm_base = 150  # Slower
        self.config.error_rate = 0.005  # Fewer errors for careful typing

        try:
            return await self.type_text(page, text, selector, clear_first=True)
        finally:
            self.config.cpm_base = original_cpm
            self.config.error_rate = original_error_rate

    async def type_fast(self, page, text: str, selector: Optional[str] = None) -> bool:
        """Type at a faster pace (for familiar text)."""
        original_cpm = self.config.cpm_base
        self.config.cpm_base = 400  # Faster

        try:
            return await self.type_text(page, text, selector, clear_first=True)
        finally:
            self.config.cpm_base = original_cpm


# Global typer instance
_global_typer: Optional[HumanTyper] = None


def get_typer() -> HumanTyper:
    """Get or create global typer instance."""
    global _global_typer
    if _global_typer is None:
        _global_typer = HumanTyper()
    return _global_typer


async def type_human(
    page,
    text: str,
    selector: Optional[str] = None,
    clear_first: bool = True
) -> bool:
    """Convenience function for human-like typing."""
    typer = get_typer()
    return await typer.type_text(page, text, selector, clear_first)
