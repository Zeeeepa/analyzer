"""
UI-TARS Patterns - Best practices from ByteDance UI-TARS-desktop

Implements key techniques for improved GUI automation:
1. Coordinate normalization (0-1000 -> screen pixels)
2. Tiered retry timeouts (screenshot: 5s, model: 30s, action: 5s)
3. Last-N screenshot context management
4. System-2 reasoning prompts
5. Error threshold termination

Source: https://github.com/bytedance/UI-TARS-desktop
Paper: https://arxiv.org/html/2501.12326v1
"""

import asyncio
from dataclasses import dataclass, field
from typing import Optional, Tuple, List, Dict, Any, Callable
from enum import Enum
from loguru import logger
import time


class AgentStatus(Enum):
    """Agent execution status (from UI-TARS SDK)"""
    INIT = "init"
    RUNNING = "running"
    PAUSED = "paused"
    END = "end"
    MAX_LOOP = "max_loop"
    ERROR = "error"


@dataclass
class ScreenContext:
    """Screen context for coordinate transformation"""
    width: int
    height: int
    scale_factor: float = 1.0

    def normalize_to_screen(self, x: float, y: float) -> Tuple[int, int]:
        """
        Convert normalized coordinates (0-1) to screen pixels.

        UI-TARS outputs coordinates in 0-1000 range.
        Divide by 1000 to get 0-1, then multiply by screen dimensions.
        """
        screen_x = int(x * self.width)
        screen_y = int(y * self.height)
        return screen_x, screen_y

    def normalize_from_1000(self, x: int, y: int) -> Tuple[int, int]:
        """
        Convert UI-TARS 0-1000 coordinates to screen pixels.

        Formula: (coord / 1000) * screen_dimension
        """
        screen_x = int((x / 1000) * self.width)
        screen_y = int((y / 1000) * self.height)
        return screen_x, screen_y

    def box_to_center(self, x1: int, y1: int, x2: int, y2: int) -> Tuple[int, int]:
        """
        Convert bounding box to center point.

        UI-TARS outputs boxes as [x1, y1, x2, y2] in 0-1000 range.
        Returns center point in screen coordinates.
        """
        # Normalize to 0-1 range
        center_x = ((x1 + x2) / 2) / 1000
        center_y = ((y1 + y2) / 2) / 1000

        # Scale to screen
        return self.normalize_to_screen(center_x, center_y)


@dataclass
class RetryConfig:
    """
    Tiered retry configuration from UI-TARS.

    Different operations need different timeout strategies:
    - Screenshots: Fast retries (5s) - usually transient issues
    - Model calls: Slow retries (30s) - API latency expected
    - Actions: Medium retries (5s) - element may need time to appear
    """
    screenshot_timeout: float = 5.0
    screenshot_max_retries: int = 3

    model_timeout: float = 30.0
    model_max_retries: int = 2

    action_timeout: float = 5.0
    action_max_retries: int = 3

    # Error thresholds for termination
    max_screenshot_errors: int = 5
    max_consecutive_errors: int = 3


@dataclass
class ConversationContext:
    """
    Manages conversation history with screenshot context.

    UI-TARS pattern: Keep only last N screenshots to limit token usage.
    Default: 5 screenshots (configurable)
    """
    max_screenshots: int = 5
    messages: List[Dict[str, Any]] = field(default_factory=list)
    screenshot_count: int = 0

    def add_message(self, role: str, content: str, screenshot_b64: Optional[str] = None):
        """Add message with optional screenshot"""
        message = {"role": role, "content": content}

        if screenshot_b64:
            message["images"] = [screenshot_b64]
            self.screenshot_count += 1

            # Prune old screenshots if over limit
            self._prune_screenshots()

        self.messages.append(message)

    def _prune_screenshots(self):
        """Remove screenshots from oldest messages to stay under limit"""
        if self.screenshot_count <= self.max_screenshots:
            return

        removed = 0
        for msg in self.messages:
            if "images" in msg and removed < (self.screenshot_count - self.max_screenshots):
                del msg["images"]
                removed += 1

        self.screenshot_count -= removed
        logger.debug(f"Pruned {removed} old screenshots, keeping last {self.max_screenshots}")

    def get_messages(self) -> List[Dict[str, Any]]:
        """Get messages for LLM call"""
        return self.messages.copy()

    def clear(self):
        """Clear conversation history"""
        self.messages.clear()
        self.screenshot_count = 0


def create_system2_prompt(task: str, current_state: str = "") -> str:
    """
    Create System-2 reasoning prompt from UI-TARS pattern.

    System-2 reasoning requires explicit thought before action:
    1. Task decomposition
    2. Current state analysis
    3. Next step reasoning
    4. Action prediction
    """
    return f"""You are a GUI automation agent. Think step by step before acting.

TASK: {task}

{f"CURRENT STATE: {current_state}" if current_state else ""}

Before each action, you MUST provide:
1. THOUGHT: Analyze the current screen state and what needs to be done
2. REFLECTION: Consider if previous actions worked and what to adjust
3. ACTION: The specific action to take with coordinates

Format your response as:
THOUGHT: [Your reasoning about the current state and next step]
REFLECTION: [What worked/didn't work, any adjustments needed]
ACTION: [action_type](parameters)

Available actions:
- click(x, y) - Click at normalized coordinates (0-1000 range)
- type(text) - Type text into focused element
- scroll(direction) - Scroll up/down/left/right
- wait(seconds) - Wait for element to load
- done() - Task completed successfully
- error(reason) - Task cannot be completed

Remember: Coordinates are in 0-1000 range where (0,0) is top-left and (1000,1000) is bottom-right.
"""


async def retry_with_timeout(
    func: Callable,
    timeout: float,
    max_retries: int,
    operation_name: str = "operation"
) -> Any:
    """
    Execute function with tiered retry and timeout.

    Implements UI-TARS retry pattern with configurable timeouts.
    """
    last_error = None

    for attempt in range(max_retries):
        try:
            result = await asyncio.wait_for(func(), timeout=timeout)
            return result
        except asyncio.TimeoutError:
            last_error = TimeoutError(f"{operation_name} timed out after {timeout}s")
            logger.warning(f"{operation_name} timeout (attempt {attempt + 1}/{max_retries})")
        except Exception as e:
            last_error = e
            logger.warning(f"{operation_name} failed (attempt {attempt + 1}/{max_retries}): {e}")

        # Wait before retry (exponential backoff capped at timeout)
        if attempt < max_retries - 1:
            wait_time = min(2 ** attempt, timeout)
            await asyncio.sleep(wait_time)

    raise last_error or Exception(f"{operation_name} failed after {max_retries} attempts")


@dataclass
class ActionParser:
    """
    Parse UI-TARS style action outputs.

    Handles formats like:
    - click(start_box="(100,200)")
    - click(x=100, y=200)
    - type(text="hello")
    - scroll(direction="down")
    """

    # Coordinate normalization aliases
    COORDINATE_ALIASES = {
        "point": "start_box",
        "start_point": "start_box",
        "end_point": "end_box",
    }

    def parse(self, action_str: str, screen: Optional[ScreenContext] = None) -> Dict[str, Any]:
        """Parse action string into structured output"""
        import re

        # Extract action type and parameters
        match = re.match(r'(\w+)\((.*)\)', action_str.strip())
        if not match:
            return {"action_type": "unknown", "raw": action_str}

        action_type = match.group(1).lower()
        params_str = match.group(2)

        # Parse parameters
        params = self._parse_params(params_str)

        # Normalize coordinate parameter names
        for old_name, new_name in self.COORDINATE_ALIASES.items():
            if old_name in params:
                params[new_name] = params.pop(old_name)

        # Extract coordinates if present
        if "start_box" in params and screen:
            coords = self._parse_coordinates(params["start_box"])
            if coords:
                if len(coords) == 2:
                    # Point: (x, y)
                    params["x"], params["y"] = screen.normalize_from_1000(coords[0], coords[1])
                elif len(coords) == 4:
                    # Box: (x1, y1, x2, y2) -> center
                    params["x"], params["y"] = screen.box_to_center(*coords)

        return {
            "action_type": action_type,
            "action_inputs": params,
            "raw": action_str
        }

    def _parse_params(self, params_str: str) -> Dict[str, Any]:
        """Parse parameter string into dict"""
        import re

        params = {}
        # Match key=value or key="value" patterns
        pattern = r'(\w+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^,\s]+))'

        for match in re.finditer(pattern, params_str):
            key = match.group(1)
            value = match.group(2) or match.group(3) or match.group(4)
            params[key] = value

        return params

    def _parse_coordinates(self, coord_str: str) -> Optional[List[int]]:
        """Extract coordinates from string like '(100,200)' or '(10,20,30,40)'"""
        import re

        # Remove box markers
        coord_str = re.sub(r'<\|?box_start\|?>|<\|?box_end\|?>|<point>|<bbox>', '', coord_str)

        # Extract numbers
        numbers = re.findall(r'[-+]?\d+(?:\.\d+)?', coord_str)

        if numbers:
            return [int(float(n)) for n in numbers]
        return None


class GUIAgentLoop:
    """
    Main agent loop implementing UI-TARS patterns.

    Features:
    - Tiered retry timeouts
    - Screenshot context limiting
    - System-2 reasoning
    - Error threshold termination
    """

    def __init__(
        self,
        screenshot_fn: Callable,
        model_fn: Callable,
        execute_fn: Callable,
        config: Optional[RetryConfig] = None,
        max_loops: int = 25
    ):
        self.screenshot_fn = screenshot_fn
        self.model_fn = model_fn
        self.execute_fn = execute_fn
        self.config = config or RetryConfig()
        self.max_loops = max_loops

        self.status = AgentStatus.INIT
        self.context = ConversationContext()
        self.parser = ActionParser()

        # Error counters
        self.screenshot_errors = 0
        self.consecutive_errors = 0
        self.loop_count = 0

    async def run(self, task: str, screen: ScreenContext) -> Dict[str, Any]:
        """Execute agent loop until task completion or termination"""
        self.status = AgentStatus.RUNNING
        self.context.clear()

        # Add system prompt with System-2 reasoning
        system_prompt = create_system2_prompt(task)
        self.context.add_message("system", system_prompt)

        results = []

        while self.status == AgentStatus.RUNNING and self.loop_count < self.max_loops:
            self.loop_count += 1

            try:
                # 1. Capture screenshot with retry
                screenshot = await retry_with_timeout(
                    self.screenshot_fn,
                    self.config.screenshot_timeout,
                    self.config.screenshot_max_retries,
                    "screenshot"
                )
                self.screenshot_errors = 0

                # 2. Add to context (with pruning)
                self.context.add_message("user", f"Step {self.loop_count}:", screenshot)

                # 3. Get model prediction with retry
                messages = self.context.get_messages()
                prediction = await retry_with_timeout(
                    lambda: self.model_fn(messages),
                    self.config.model_timeout,
                    self.config.model_max_retries,
                    "model"
                )

                # 4. Parse action
                parsed = self.parser.parse(prediction, screen)
                action_type = parsed.get("action_type", "unknown")

                # 5. Check for terminal actions
                if action_type == "done":
                    self.status = AgentStatus.END
                    break
                elif action_type == "error":
                    self.status = AgentStatus.ERROR
                    break

                # 6. Execute action with retry
                result = await retry_with_timeout(
                    lambda: self.execute_fn(parsed),
                    self.config.action_timeout,
                    self.config.action_max_retries,
                    "action"
                )

                results.append({
                    "step": self.loop_count,
                    "action": parsed,
                    "result": result
                })

                self.consecutive_errors = 0

            except Exception as e:
                logger.error(f"Loop error at step {self.loop_count}: {e}")
                self.consecutive_errors += 1

                if "screenshot" in str(e).lower():
                    self.screenshot_errors += 1

                # Check error thresholds
                if self.screenshot_errors >= self.config.max_screenshot_errors:
                    logger.error("Max screenshot errors reached, terminating")
                    self.status = AgentStatus.ERROR
                    break

                if self.consecutive_errors >= self.config.max_consecutive_errors:
                    logger.error("Max consecutive errors reached, terminating")
                    self.status = AgentStatus.ERROR
                    break

        if self.loop_count >= self.max_loops:
            self.status = AgentStatus.MAX_LOOP

        return {
            "status": self.status.value,
            "loops": self.loop_count,
            "results": results
        }


# Export key utilities
__all__ = [
    "ScreenContext",
    "RetryConfig",
    "ConversationContext",
    "ActionParser",
    "GUIAgentLoop",
    "AgentStatus",
    "create_system2_prompt",
    "retry_with_timeout"
]
