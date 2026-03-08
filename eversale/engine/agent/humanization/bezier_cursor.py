"""
Advanced Bezier Cursor - Ultra-realistic human mouse movements

Based on research from:
- HumanCursor: Bezier curves with Bernstein polynomials
- pyclick: Variable knot count based on distance
- Ghost Cursor: Fitts's Law timing
- BezMouse: 400+ hours undetected in RuneScape

Key features:
- Bernstein polynomial Bezier curves (not simple quadratic)
- Dynamic knot count based on movement distance
- Gaussian noise injection for tremor simulation
- easeOutQuad easing for natural deceleration
- Overshoot and correction patterns
- Fatigue-aware movement speed
"""

import asyncio
import random
import math
from typing import Tuple, List, Optional
from dataclasses import dataclass
from scipy.special import comb
import numpy as np
from loguru import logger


@dataclass
class CursorConfig:
    """Configuration for cursor behavior"""
    # Bezier curve parameters
    offset_boundary_x: int = 100  # Control point randomization zone
    offset_boundary_y: int = 100
    min_knots: int = 1  # Minimum internal control points
    max_knots: int = 3  # Maximum internal control points
    knots_per_distance: int = 200  # One knot per N pixels

    # Distortion (tremor simulation)
    distortion_mean: float = 0.0
    distortion_st_dev: float = 1.0
    distortion_frequency: float = 0.08  # 8% of points get jitter (human range: 5-15%)

    # Movement parameters
    target_points: int = 100  # Resolution of final curve
    min_duration_ms: int = 80  # Minimum movement time
    max_duration_ms: int = 400  # Maximum movement time

    # Click offset (humans don't click dead center)
    click_offset_ratio: float = 0.2  # Click within central 60% of element

    # Overshoot simulation
    overshoot_chance: float = 0.15  # 15% chance of overshooting
    overshoot_ratio: float = 0.08  # Overshoot 8% of movement distance (more natural scaling)
    overshoot_min_px: float = 5  # Minimum overshoot pixels
    overshoot_max_px: float = 25  # Maximum overshoot pixels
    correction_delay_ms: Tuple[int, int] = (50, 150)

    # Speed variation
    speed_variance: float = 0.3  # 30% variance in movement speed

    # FAST_TRACK mode - Skip humanization for high-volume tasks
    fast_track: bool = False  # When True: direct movement, no bezier, no delays


class BezierCursor:
    """
    Ultra-realistic human mouse movement using Bezier curves.

    Uses Bernstein polynomial formula for smooth curves:
    B(t) = Σ binomial(n,i) * t^i * (1-t)^(n-i) * P_i

    Example:
        cursor = BezierCursor()
        await cursor.move_to(page, 500, 300)
        await cursor.click_at(page, selector=".submit-btn")
    """

    def __init__(self, config: Optional[CursorConfig] = None):
        self.config = config or CursorConfig()
        self.current_x = 0.0
        self.current_y = 0.0
        self.fatigue = 1.0  # Starts at baseline (increases = slower)
        self._move_count = 0
        self._fast_track_logged = False  # Track if we've logged FAST_TRACK activation

    def bernstein_polynomial(self, t: float, i: int, n: int) -> float:
        """
        Bernstein polynomial basis function.
        B_{i,n}(t) = C(n,i) * t^i * (1-t)^(n-i)
        """
        return comb(n, i, exact=True) * (t ** i) * ((1 - t) ** (n - i))

    def generate_bezier_curve(self, control_points: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        """
        Generate Bezier curve from control points using Bernstein polynomials.

        This produces smoother, more natural curves than simple quadratic/cubic.
        """
        n = len(control_points) - 1
        num_points = max(self.config.target_points, 50)
        curve_points = []

        for step in range(num_points + 1):
            t = step / num_points
            x = sum(self.bernstein_polynomial(t, i, n) * p[0]
                   for i, p in enumerate(control_points))
            y = sum(self.bernstein_polynomial(t, i, n) * p[1]
                   for i, p in enumerate(control_points))
            curve_points.append((x, y))

        return curve_points

    def calculate_knot_count(self, distance: float) -> int:
        """
        Calculate optimal number of internal knots based on distance.
        Longer distances need more control points for natural curves.
        """
        calculated = round(distance / self.config.knots_per_distance)
        return max(self.config.min_knots, min(calculated, self.config.max_knots))

    def generate_control_points(
        self,
        start: Tuple[float, float],
        end: Tuple[float, float]
    ) -> List[Tuple[float, float]]:
        """
        Generate random control points between start and end.
        Control points determine the curve's shape.
        """
        distance = math.sqrt((end[0] - start[0])**2 + (end[1] - start[1])**2)
        knots_count = self.calculate_knot_count(distance)

        # Calculate boundaries for control points
        left = min(start[0], end[0]) - self.config.offset_boundary_x
        right = max(start[0], end[0]) + self.config.offset_boundary_x
        down = min(start[1], end[1]) - self.config.offset_boundary_y
        up = max(start[1], end[1]) + self.config.offset_boundary_y

        # Ensure boundaries are valid (not negative)
        left = max(0, left)
        down = max(0, down)

        # Generate internal knots with some bias toward the path
        internal_knots = []
        for i in range(knots_count):
            # Bias toward the line between start and end
            progress = (i + 1) / (knots_count + 1)
            base_x = start[0] + (end[0] - start[0]) * progress
            base_y = start[1] + (end[1] - start[1]) * progress

            # Add randomness
            offset_x = random.gauss(0, self.config.offset_boundary_x * 0.5)
            offset_y = random.gauss(0, self.config.offset_boundary_y * 0.5)

            knot_x = max(left, min(right, base_x + offset_x))
            knot_y = max(down, min(up, base_y + offset_y))

            internal_knots.append((knot_x, knot_y))

        return [start] + internal_knots + [end]

    def apply_distortion(self, curve_points: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        """
        Apply Gaussian noise to simulate hand tremor.
        Skips first and last points to ensure we hit start/end exactly.
        Tremor frequency and magnitude increase with fatigue (1.0-1.5x multiplier).
        """
        distorted = [curve_points[0]]  # Keep start point

        # Fatigue increases both tremor frequency and magnitude
        tremor_frequency = self.config.distortion_frequency * min(1.5, self.fatigue)
        tremor_magnitude = self.config.distortion_st_dev * min(1.3, self.fatigue)

        for i in range(1, len(curve_points) - 1):
            point = curve_points[i]
            if random.random() < tremor_frequency:
                noise_x = random.gauss(self.config.distortion_mean, tremor_magnitude)
                noise_y = random.gauss(self.config.distortion_mean, tremor_magnitude)
                distorted.append((point[0] + noise_x, point[1] + noise_y))
            else:
                distorted.append(point)

        distorted.append(curve_points[-1])  # Keep end point
        return distorted

    def apply_easing(self, curve_points: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        """
        Apply easeOutQuad easing for natural deceleration.
        Humans slow down as they approach targets (Fitts's Law).
        """
        def ease_out_quad(t: float) -> float:
            return -t * (t - 2)

        n = len(curve_points)
        final_points = []

        for i in range(self.config.target_points):
            t = i / self.config.target_points
            eased_t = ease_out_quad(t)

            # Map eased progress to curve index
            index = int(eased_t * (n - 1))
            index = max(0, min(index, n - 1))

            final_points.append(curve_points[index])

        # Always end at exact target
        final_points.append(curve_points[-1])

        return final_points

    def calculate_movement_duration(self, distance: float) -> float:
        """
        Calculate movement duration based on distance (Fitts's Law inspired).
        Longer distances take more time, with variance.
        """
        # Base duration scales with square root of distance
        base = self.config.min_duration_ms + math.sqrt(distance) * 2
        base = min(base, self.config.max_duration_ms)

        # Apply variance
        variance = base * self.config.speed_variance
        duration = base + random.uniform(-variance, variance)

        # Apply fatigue (slower when tired)
        duration *= self.fatigue

        return max(self.config.min_duration_ms, duration)

    def update_fatigue(self):
        """Update fatigue based on movement count."""
        self._move_count += 1

        # Gradual fatigue increase
        self.fatigue = min(1.5, self.fatigue + 0.005)

        # Occasional "rest" that reduces fatigue
        if self._move_count % random.randint(15, 25) == 0:
            self.fatigue = max(1.0, self.fatigue - 0.1)

    async def move_to(
        self,
        page,
        target_x: float,
        target_y: float,
        duration_override: Optional[float] = None
    ) -> Tuple[float, float]:
        """
        Move cursor to target position using Bezier curve.

        Args:
            page: Playwright page object
            target_x, target_y: Target coordinates
            duration_override: Optional fixed duration in ms

        Returns:
            Final cursor position (target_x, target_y)
        """
        # FAST_TRACK mode: Direct movement, no delays
        if self.config.fast_track:
            if not self._fast_track_logged:
                logger.info("FAST_TRACK mode enabled: Using direct cursor movement (no humanization)")
                self._fast_track_logged = True

            await page.mouse.move(target_x, target_y)
            self.current_x, self.current_y = target_x, target_y
            return (target_x, target_y)

        start = (self.current_x, self.current_y)
        end = (target_x, target_y)

        # Calculate distance for timing
        distance = math.sqrt((end[0] - start[0])**2 + (end[1] - start[1])**2)

        if distance < 5:  # Already there
            return end

        # Generate curve
        control_points = self.generate_control_points(start, end)
        curve = self.generate_bezier_curve(control_points)
        curve = self.apply_distortion(curve)
        curve = self.apply_easing(curve)

        # Calculate timing
        duration = duration_override or self.calculate_movement_duration(distance)
        delay_per_point = duration / len(curve)

        # Execute movement
        for i, (x, y) in enumerate(curve):
            await page.mouse.move(x, y)

            # Variable delay - faster in middle, slower at edges
            progress = i / len(curve)
            if progress < 0.15 or progress > 0.85:
                delay = delay_per_point * 1.3
            else:
                delay = delay_per_point * 0.8

            await asyncio.sleep(delay / 1000)

        # Update state
        self.current_x, self.current_y = target_x, target_y
        self.update_fatigue()

        return (target_x, target_y)

    async def move_with_overshoot(
        self,
        page,
        target_x: float,
        target_y: float
    ) -> Tuple[float, float]:
        """
        Move to target with possible overshoot and correction.
        Overshoot distance scales with movement distance for natural behavior.
        """
        # FAST_TRACK mode: Skip overshoot
        if self.config.fast_track:
            return await self.move_to(page, target_x, target_y)

        if random.random() < self.config.overshoot_chance:
            # Calculate overshoot direction and distance
            dx = target_x - self.current_x
            dy = target_y - self.current_y
            distance = math.sqrt(dx*dx + dy*dy)

            if distance > 20:  # Only overshoot for longer movements
                # Calculate overshoot distance (scales with movement distance)
                overshoot_dist = distance * self.config.overshoot_ratio
                # Clamp to min/max for realistic behavior
                overshoot_dist = max(
                    self.config.overshoot_min_px,
                    min(self.config.overshoot_max_px, overshoot_dist)
                )

                # Normalize and extend
                overshoot_x = target_x + (dx / distance) * overshoot_dist
                overshoot_y = target_y + (dy / distance) * overshoot_dist

                # Move past target
                await self.move_to(page, overshoot_x, overshoot_y)

                # Pause (notice the overshoot)
                await asyncio.sleep(random.uniform(*self.config.correction_delay_ms) / 1000)

                # Correct back to target
                await self.move_to(page, target_x, target_y)
                return (target_x, target_y)

        # Normal movement
        return await self.move_to(page, target_x, target_y)

    async def check_interactability(
        self,
        page,
        element,
        target_x: float,
        target_y: float,
        max_attempts: int = 3
    ) -> bool:
        """
        Check if element is interactable (visible, enabled, not covered).

        Args:
            page: Playwright page
            element: The element to check
            target_x, target_y: The coordinates where we plan to click
            max_attempts: Number of attempts to make element interactable

        Returns:
            True if element is interactable, False otherwise
        """
        for attempt in range(max_attempts):
            try:
                # Check 1: Is element visible in viewport?
                is_visible = await element.is_visible()
                if not is_visible:
                    logger.warning(f"Element not visible (attempt {attempt + 1}/{max_attempts}), scrolling into view")
                    await element.scroll_into_view_if_needed()
                    await asyncio.sleep(0.2)  # Wait for scroll animation
                    continue

                # Check 2: Is element enabled?
                is_enabled = await element.is_enabled()
                if not is_enabled:
                    logger.warning(f"Element is disabled (attempt {attempt + 1}/{max_attempts})")
                    if attempt < max_attempts - 1:
                        await asyncio.sleep(0.3)  # Wait to see if it becomes enabled
                        continue
                    else:
                        return False

                # Check 3: Is element covered by an overlay?
                # Use elementFromPoint to check what's actually at the click coordinates
                element_at_point = await page.evaluate(
                    """([x, y]) => {
                        const elem = document.elementFromPoint(x, y);
                        if (!elem) return null;
                        return {
                            tagName: elem.tagName,
                            id: elem.id,
                            className: elem.className
                        };
                    }""",
                    [target_x, target_y]
                )

                if element_at_point:
                    # Check if the element at point is our target or a child of it
                    is_our_element = await page.evaluate(
                        """([x, y, targetElem]) => {
                            const elemAtPoint = document.elementFromPoint(x, y);
                            if (!elemAtPoint) return false;

                            // Check if it's the same element or a descendant
                            return targetElem.contains(elemAtPoint) || elemAtPoint.contains(targetElem);
                        }""",
                        [target_x, target_y, element]
                    )

                    if not is_our_element:
                        logger.warning(
                            f"Element is covered by overlay: {element_at_point.get('tagName')} "
                            f"(attempt {attempt + 1}/{max_attempts})"
                        )
                        if attempt < max_attempts - 1:
                            # Try scrolling or waiting for overlay to disappear
                            await element.scroll_into_view_if_needed()
                            await asyncio.sleep(0.5)
                            continue
                        else:
                            return False

                # All checks passed
                logger.debug("Element is interactable")
                return True

            except Exception as e:
                logger.warning(f"Interactability check failed (attempt {attempt + 1}/{max_attempts}): {e}")
                if attempt < max_attempts - 1:
                    await asyncio.sleep(0.3)
                    continue
                else:
                    return False

        return False

    def get_click_offset(self, bbox: dict) -> Tuple[float, float]:
        """
        Calculate human-like click position within element.
        Uses Gaussian distribution centered on element.
        """
        width = bbox.get('width', 0)
        height = bbox.get('height', 0)

        # Gaussian offset (most clicks near center, some toward edges)
        offset_x = random.gauss(0, width * self.config.click_offset_ratio * 0.5)
        offset_y = random.gauss(0, height * self.config.click_offset_ratio * 0.5)

        # Clamp to element bounds (with margin)
        max_offset_x = width * 0.4
        max_offset_y = height * 0.4
        offset_x = max(-max_offset_x, min(max_offset_x, offset_x))
        offset_y = max(-max_offset_y, min(max_offset_y, offset_y))

        return (offset_x, offset_y)

    async def click_at(
        self,
        page,
        x: Optional[float] = None,
        y: Optional[float] = None,
        selector: Optional[str] = None,
        button: str = 'left',
        click_count: int = 1
    ) -> bool:
        """
        Click at position or element with human-like behavior.

        Args:
            page: Playwright page
            x, y: Coordinates (if not using selector)
            selector: CSS selector (alternative to coordinates)
            button: 'left', 'right', or 'middle'
            click_count: 1 for single, 2 for double click

        Returns:
            True if click succeeded
        """
        try:
            target_x, target_y = x, y
            element = None

            if selector:
                element = await page.query_selector(selector)
                if not element:
                    logger.warning(f"Element not found: {selector}")
                    return False

                bbox = await element.bounding_box()
                if not bbox:
                    logger.warning(f"Element has no bounding box: {selector}")
                    return False

                # Calculate click position with human offset
                offset_x, offset_y = self.get_click_offset(bbox)
                target_x = bbox['x'] + bbox['width'] / 2 + offset_x
                target_y = bbox['y'] + bbox['height'] / 2 + offset_y

                # Check interactability before clicking
                is_interactable = await self.check_interactability(
                    page, element, target_x, target_y
                )
                if not is_interactable:
                    logger.warning(
                        f"Element is not interactable after multiple attempts: {selector}"
                    )
                    return False

            if target_x is None or target_y is None:
                return False

            # Move to target (possibly with overshoot)
            await self.move_with_overshoot(page, target_x, target_y)

            # Pre-click delay (hand positioning) - skip in FAST_TRACK
            if not self.config.fast_track:
                await asyncio.sleep(random.uniform(0.03, 0.08))

            # Perform click(s)
            for i in range(click_count):
                # Mouse down
                await page.mouse.down(button=button)

                # Hold duration (humans don't instant-click) - minimal in FAST_TRACK
                if self.config.fast_track:
                    hold_time = 0.01  # Minimal hold for reliability
                else:
                    hold_time = random.uniform(0.05, 0.12)
                await asyncio.sleep(hold_time)

                # Mouse up
                await page.mouse.up(button=button)

                # Delay between clicks for double-click - skip in FAST_TRACK
                if i < click_count - 1:
                    if not self.config.fast_track:
                        await asyncio.sleep(random.uniform(0.08, 0.15))
                    else:
                        await asyncio.sleep(0.01)

            logger.debug(f"Click succeeded at ({target_x}, {target_y})")
            return True

        except Exception as e:
            logger.warning(f"Click failed: {e}")
            return False

    async def hover(self, page, selector: str, duration_ms: int = 500) -> bool:
        """Hover over element for specified duration."""
        try:
            element = await page.query_selector(selector)
            if not element:
                return False

            bbox = await element.bounding_box()
            if not bbox:
                return False

            target_x = bbox['x'] + bbox['width'] / 2
            target_y = bbox['y'] + bbox['height'] / 2

            await self.move_to(page, target_x, target_y)
            await asyncio.sleep(duration_ms / 1000)

            return True
        except Exception as e:
            logger.debug(f"Hover failed: {e}")
            return False


# Global cursor instance for convenience
_global_cursor: Optional[BezierCursor] = None


def get_cursor() -> BezierCursor:
    """Get or create global cursor instance."""
    global _global_cursor
    if _global_cursor is None:
        _global_cursor = BezierCursor()
    return _global_cursor


async def move_human(page, x: float, y: float) -> Tuple[float, float]:
    """Convenience function for human-like mouse movement."""
    cursor = get_cursor()
    return await cursor.move_to(page, x, y)


async def click_human(
    page,
    selector: Optional[str] = None,
    x: Optional[float] = None,
    y: Optional[float] = None
) -> bool:
    """Convenience function for human-like clicking."""
    cursor = get_cursor()
    return await cursor.click_at(page, x=x, y=y, selector=selector)
