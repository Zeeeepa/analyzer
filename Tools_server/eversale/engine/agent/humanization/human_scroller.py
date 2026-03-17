"""
Human-Like Scrolling - Natural scroll patterns that avoid detection

Key features:
- Variable scroll distances (not uniform)
- Deceleration near targets
- Occasional overshoots and corrections
- Reading pauses during scroll
- Momentum simulation
"""

import asyncio
import random
from typing import Optional, Tuple
from dataclasses import dataclass
from loguru import logger


@dataclass
class ScrollConfig:
    """Configuration for scroll behavior"""
    # Scroll distances
    min_scroll: int = 80
    max_scroll: int = 200

    # Timing
    min_delay_ms: int = 30
    max_delay_ms: int = 80

    # Reading behavior
    reading_pause_chance: float = 0.2  # 20% chance to pause while scrolling
    reading_pause_min_ms: int = 300
    reading_pause_max_ms: int = 1500

    # Overshoot
    overshoot_chance: float = 0.12  # 12% chance of overshooting
    overshoot_amount: int = 50  # Extra pixels

    # Momentum (scroll continues briefly after "releasing")
    momentum_enabled: bool = True
    momentum_steps: int = 3
    momentum_decay: float = 0.5  # Each step is 50% of previous

    # FAST_TRACK mode - Skip humanization for high-volume tasks
    fast_track: bool = False  # When True: instant scrolling, no delays, no pauses


class HumanScroller:
    """
    Scrolls pages with human-like patterns.

    Example:
        scroller = HumanScroller()
        await scroller.scroll_down(page, pixels=500)
        await scroller.scroll_to_element(page, "#target")
    """

    def __init__(self, config: Optional[ScrollConfig] = None):
        self.config = config or ScrollConfig()
        self._scroll_count = 0
        self._fast_track_logged = False  # Track if we've logged FAST_TRACK activation

    def get_scroll_chunk(self) -> int:
        """Get a random scroll chunk size."""
        return random.randint(self.config.min_scroll, self.config.max_scroll)

    def get_chunk_delay(self) -> float:
        """Get delay between scroll chunks."""
        return random.uniform(
            self.config.min_delay_ms / 1000,
            self.config.max_delay_ms / 1000
        )

    async def apply_momentum(self, page, direction: int):
        """Apply momentum after scroll (like releasing a touchpad)."""
        if not self.config.momentum_enabled:
            return

        amount = self.get_scroll_chunk() * 0.3

        for i in range(self.config.momentum_steps):
            momentum_scroll = amount * (self.config.momentum_decay ** i) * direction
            if abs(momentum_scroll) < 10:
                break

            await page.mouse.wheel(0, momentum_scroll)
            await asyncio.sleep(random.uniform(0.015, 0.035))

    async def scroll_down(
        self,
        page,
        pixels: Optional[int] = None,
        smooth: bool = True
    ) -> int:
        """
        Scroll down with human-like behavior.

        Args:
            page: Playwright page
            pixels: Total pixels to scroll (random if not specified)
            smooth: Use smooth scrolling with chunks

        Returns:
            Total pixels scrolled
        """
        # FAST_TRACK mode: Instant scrolling
        if self.config.fast_track:
            if not self._fast_track_logged:
                logger.info("FAST_TRACK mode enabled: Using instant scrolling (no humanization)")
                self._fast_track_logged = True

            total = pixels or random.randint(200, 600)
            await page.mouse.wheel(0, total)
            return total

        total = pixels or random.randint(200, 600)
        scrolled = 0

        while scrolled < total:
            # Calculate chunk (smaller near end)
            remaining = total - scrolled
            if remaining < 100:
                chunk = min(remaining, random.randint(30, 60))
            else:
                chunk = min(remaining, self.get_scroll_chunk())

            if smooth:
                # Scroll in smaller increments for smoothness
                sub_chunks = random.randint(2, 4)
                sub_chunk = chunk / sub_chunks

                for _ in range(sub_chunks):
                    await page.mouse.wheel(0, sub_chunk)
                    await asyncio.sleep(random.uniform(0.01, 0.025))
            else:
                await page.mouse.wheel(0, chunk)

            scrolled += chunk

            # Delay between chunks
            await asyncio.sleep(self.get_chunk_delay())

            # Maybe pause to "read"
            if random.random() < self.config.reading_pause_chance:
                pause = random.uniform(
                    self.config.reading_pause_min_ms / 1000,
                    self.config.reading_pause_max_ms / 1000
                )
                await asyncio.sleep(pause)

        # Apply momentum
        await self.apply_momentum(page, 1)

        self._scroll_count += 1
        return scrolled

    async def scroll_up(
        self,
        page,
        pixels: Optional[int] = None,
        smooth: bool = True
    ) -> int:
        """Scroll up with human-like behavior."""
        # FAST_TRACK mode: Instant scrolling
        if self.config.fast_track:
            total = pixels or random.randint(200, 600)
            await page.mouse.wheel(0, -total)
            return total

        total = pixels or random.randint(200, 600)
        scrolled = 0

        while scrolled < total:
            remaining = total - scrolled
            chunk = min(remaining, self.get_scroll_chunk())

            if smooth:
                sub_chunks = random.randint(2, 4)
                sub_chunk = chunk / sub_chunks

                for _ in range(sub_chunks):
                    await page.mouse.wheel(0, -sub_chunk)
                    await asyncio.sleep(random.uniform(0.01, 0.025))
            else:
                await page.mouse.wheel(0, -chunk)

            scrolled += chunk
            await asyncio.sleep(self.get_chunk_delay())

        # Apply momentum
        await self.apply_momentum(page, -1)

        return scrolled

    async def scroll_to_element(
        self,
        page,
        selector: str,
        margin: int = 100
    ) -> bool:
        """
        Scroll until element is visible with human-like behavior.

        Args:
            page: Playwright page
            selector: CSS selector of target element
            margin: Extra margin to scroll past element

        Returns:
            True if element is now visible
        """
        try:
            element = await page.query_selector(selector)
            if not element:
                logger.debug(f"Element not found: {selector}")
                return False

            # FAST_TRACK mode: Use native scrollIntoView
            if self.config.fast_track:
                await element.evaluate("el => el.scrollIntoView({behavior: 'instant', block: 'center'})")
                await asyncio.sleep(0.01)  # Minimal delay for rendering
                return True

            # Check if already visible
            is_visible = await element.is_visible()
            if is_visible:
                bbox = await element.bounding_box()
                if bbox:
                    viewport = page.viewport_size or {'height': 800}
                    # Check if in viewport
                    if 0 <= bbox['y'] <= viewport['height'] - 100:
                        return True

            # Get current scroll position
            current_scroll = await page.evaluate("window.scrollY")

            # Get element position
            bbox = await element.bounding_box()
            if not bbox:
                # Element might not be rendered yet, try scrolling blindly
                await self.scroll_down(page, 300)
                return await self.scroll_to_element(page, selector, margin)

            # Calculate how much to scroll
            viewport = page.viewport_size or {'height': 800}
            target_scroll = bbox['y'] + current_scroll - margin
            scroll_needed = target_scroll - current_scroll

            if abs(scroll_needed) < 50:
                return True

            # Scroll toward element
            max_attempts = 20
            for _ in range(max_attempts):
                if scroll_needed > 0:
                    scrolled = await self.scroll_down(page, min(300, scroll_needed))
                else:
                    scrolled = await self.scroll_up(page, min(300, abs(scroll_needed)))

                # Recheck position
                bbox = await element.bounding_box()
                if bbox:
                    current_scroll = await page.evaluate("window.scrollY")
                    target_scroll = bbox['y'] + current_scroll - margin
                    scroll_needed = target_scroll - current_scroll

                    if abs(scroll_needed) < 50:
                        # Handle overshoot
                        if random.random() < self.config.overshoot_chance:
                            await self.scroll_down(page, self.config.overshoot_amount)
                            await asyncio.sleep(random.uniform(0.1, 0.2))
                            await self.scroll_up(page, self.config.overshoot_amount - 20)

                        return True

            return False

        except Exception as e:
            logger.debug(f"Scroll to element failed: {e}")
            return False

    async def scroll_to_bottom(self, page, step_pause: bool = True) -> int:
        """
        Scroll to bottom of page with reading pauses.

        Args:
            page: Playwright page
            step_pause: Pause between scroll steps

        Returns:
            Total pixels scrolled
        """
        # FAST_TRACK mode: Instant scroll to bottom
        if self.config.fast_track:
            height = await page.evaluate("document.body.scrollHeight")
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(0.01)  # Minimal delay for rendering
            return height

        total_scrolled = 0
        last_height = 0
        stall_count = 0

        while stall_count < 3:  # Stop after 3 consecutive stalls
            # Get current height
            current_height = await page.evaluate("document.body.scrollHeight")

            if current_height == last_height:
                stall_count += 1
            else:
                stall_count = 0
                last_height = current_height

            # Scroll down a chunk
            scrolled = await self.scroll_down(page, random.randint(300, 500))
            total_scrolled += scrolled

            # Reading pause
            if step_pause:
                await asyncio.sleep(random.uniform(0.5, 1.5))

        return total_scrolled


# Global scroller instance
_global_scroller: Optional[HumanScroller] = None


def get_scroller() -> HumanScroller:
    """Get or create global scroller instance."""
    global _global_scroller
    if _global_scroller is None:
        _global_scroller = HumanScroller()
    return _global_scroller


async def scroll_human(
    page,
    direction: str = "down",
    pixels: Optional[int] = None
) -> int:
    """Convenience function for human-like scrolling."""
    scroller = get_scroller()

    if direction.lower() == "up":
        return await scroller.scroll_up(page, pixels)
    else:
        return await scroller.scroll_down(page, pixels)
