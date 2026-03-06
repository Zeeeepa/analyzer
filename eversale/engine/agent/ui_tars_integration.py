"""
UI-TARS Integration Layer

Connects UI-TARS patterns to existing Eversale CLI agent infrastructure.
Use these helpers to enhance existing automation with UI-TARS techniques.
"""

from typing import Optional, Dict, Any, Callable
from loguru import logger

from .ui_tars_patterns import (
    ScreenContext,
    RetryConfig,
    ConversationContext,
    ActionParser,
    create_system2_prompt,
    retry_with_timeout,
    AgentStatus
)


class UITarsEnhancer:
    """
    Enhances existing agent with UI-TARS patterns.

    Usage:
        enhancer = UITarsEnhancer(page)
        result = await enhancer.enhanced_action(
            "click",
            {"x": 500, "y": 300},  # Normalized 0-1000 coords
            retry_config=RetryConfig(action_max_retries=5)
        )
    """

    def __init__(self, page, config: Optional[RetryConfig] = None):
        """
        Initialize with Playwright page.

        Args:
            page: Playwright page object
            config: Optional retry configuration
        """
        self.page = page
        self.config = config or RetryConfig()
        self.parser = ActionParser()
        self.context = ConversationContext(max_screenshots=5)
        self._screen_context: Optional[ScreenContext] = None

    async def get_screen_context(self) -> ScreenContext:
        """Get current screen dimensions for coordinate transformation"""
        if self._screen_context is None:
            viewport = self.page.viewport_size
            if viewport:
                self._screen_context = ScreenContext(
                    width=viewport["width"],
                    height=viewport["height"],
                    scale_factor=1.0
                )
            else:
                # Default fallback
                self._screen_context = ScreenContext(1920, 1080)
        return self._screen_context

    def invalidate_screen_context(self):
        """Call after viewport changes"""
        self._screen_context = None

    async def normalize_coordinates(self, x: int, y: int) -> tuple:
        """
        Convert UI-TARS normalized coords (0-1000) to screen pixels.

        Args:
            x: X coordinate in 0-1000 range
            y: Y coordinate in 0-1000 range

        Returns:
            Tuple of (screen_x, screen_y) in pixels
        """
        screen = await self.get_screen_context()
        return screen.normalize_from_1000(x, y)

    async def enhanced_click(
        self,
        x: int,
        y: int,
        normalized: bool = True
    ) -> bool:
        """
        Click with UI-TARS coordinate handling and retry.

        Args:
            x: X coordinate (0-1000 if normalized, pixels otherwise)
            y: Y coordinate (0-1000 if normalized, pixels otherwise)
            normalized: Whether coords are in 0-1000 range
        """
        if normalized:
            screen = await self.get_screen_context()
            x, y = screen.normalize_from_1000(x, y)

        async def do_click():
            await self.page.mouse.click(x, y)
            return True

        try:
            return await retry_with_timeout(
                do_click,
                self.config.action_timeout,
                self.config.action_max_retries,
                f"click({x}, {y})"
            )
        except Exception as e:
            logger.error(f"Enhanced click failed: {e}")
            return False

    async def enhanced_screenshot(self) -> Optional[str]:
        """
        Capture screenshot with retry and context management.

        Returns base64-encoded screenshot and adds to conversation context.
        """
        async def do_screenshot():
            screenshot = await self.page.screenshot(type="png")
            import base64
            return base64.b64encode(screenshot).decode()

        try:
            b64_screenshot = await retry_with_timeout(
                do_screenshot,
                self.config.screenshot_timeout,
                self.config.screenshot_max_retries,
                "screenshot"
            )

            # Add to context with automatic pruning
            self.context.add_message(
                "assistant",
                "Screenshot captured",
                b64_screenshot
            )

            return b64_screenshot
        except Exception as e:
            logger.error(f"Enhanced screenshot failed: {e}")
            return None

    def get_system2_prompt(self, task: str, state: str = "") -> str:
        """Get System-2 reasoning prompt for the task"""
        return create_system2_prompt(task, state)

    def parse_action(self, action_str: str) -> Dict[str, Any]:
        """Parse UI-TARS style action output"""
        return self.parser.parse(action_str)


def enhance_brain_config() -> Dict[str, Any]:
    """
    Get recommended config enhancements based on UI-TARS patterns.

    Apply these to config.yaml or brain initialization.
    """
    return {
        "retry": {
            # Tiered timeouts from UI-TARS
            "screenshot_timeout": 5.0,
            "screenshot_max_retries": 3,
            "model_timeout": 30.0,
            "model_max_retries": 2,
            "action_timeout": 5.0,
            "action_max_retries": 3,
            # Error thresholds
            "max_screenshot_errors": 5,
            "max_consecutive_errors": 3,
        },
        "context": {
            # Screenshot context management
            "max_screenshots_in_context": 5,
            "prune_old_screenshots": True,
        },
        "reasoning": {
            # System-2 patterns
            "require_thought_before_action": True,
            "require_reflection": True,
            "max_loops": 25,
        },
        "coordinates": {
            # UI-TARS normalized coordinate range
            "normalization_range": 1000,
            "auto_normalize": True,
        }
    }


# Quick integration for existing code
def apply_uitars_patterns_to_prompt(prompt: str, task: str) -> str:
    """
    Enhance an existing prompt with UI-TARS System-2 reasoning.

    Args:
        prompt: Existing prompt
        task: The task being performed

    Returns:
        Enhanced prompt with reasoning requirements
    """
    reasoning_section = """
Before responding with an action, you MUST include:

THOUGHT: What is the current state? What needs to happen next?
REFLECTION: Did previous actions work? What should be adjusted?

Then provide your action.
"""
    return f"{prompt}\n\n{reasoning_section}\n\nCurrent task: {task}"


__all__ = [
    "UITarsEnhancer",
    "enhance_brain_config",
    "apply_uitars_patterns_to_prompt"
]
