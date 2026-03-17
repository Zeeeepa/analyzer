"""
Action Router - Uses tiny 0.6B model to handle simple actions

Routes 70% of actions through fast path (~10ms), only calling main model
for complex decisions.
"""

import ollama
import json
import re
import time
from typing import Dict, Any, Optional, Tuple
from loguru import logger


class ActionRouter:
    """
    Fast router using Qwen3-0.6B to classify and execute simple actions

    Simple actions: click known element, type text, scroll, navigate
    Complex actions: requires analysis, multi-step planning, error recovery
    """

    def __init__(self, model: str = "qwen2.5:0.5b-instruct"):
        self.model = model
        self.stats = {
            "total_calls": 0,
            "simple_handled": 0,
            "complex_escalated": 0,
            "avg_latency_ms": 0
        }

    def classify_and_execute(
        self,
        user_goal: str,
        page_context: str,
        confidence_threshold: float = 0.95
    ) -> Tuple[bool, Optional[Dict[str, Any]], float]:
        """
        Classify action and execute if simple

        Returns:
            (is_simple, action_dict, confidence)
            - is_simple: True if router can handle
            - action_dict: Tool call if simple, None otherwise
            - confidence: Router's confidence score
        """

        start_time = time.time()
        self.stats["total_calls"] += 1

        # Quick pattern matching for ultra-simple actions
        quick_action = self._try_quick_patterns(user_goal)
        if quick_action:
            latency = (time.time() - start_time) * 1000
            self._update_stats(latency, simple=True)
            logger.debug(f"Quick pattern match: {user_goal[:50]} -> {quick_action['tool']}")
            return True, quick_action, 0.99

        # Router model classification + execution
        prompt = self._build_classification_prompt(user_goal, page_context)

        try:
            response = ollama.generate(
                model=self.model,
                prompt=prompt,
                options={
                    "temperature": 0.1,
                    "num_predict": 150,
                    "stop": ["---"]
                }
            )

            result_text = response['response'].strip()

            # Parse response
            is_simple, action, confidence = self._parse_classification(result_text)

            latency = (time.time() - start_time) * 1000
            self._update_stats(latency, simple=is_simple)

            if is_simple and confidence >= confidence_threshold:
                logger.info(f"Router SIMPLE ({latency:.0f}ms, conf={confidence:.2f}): {user_goal[:50]}")
                self.stats["simple_handled"] += 1
                return True, action, confidence
            else:
                logger.info(f"Router COMPLEX (escalating to main): {user_goal[:50]}")
                self.stats["complex_escalated"] += 1
                return False, None, confidence

        except Exception as e:
            logger.error(f"Router error: {e}, escalating to main model")
            latency = (time.time() - start_time) * 1000
            self._update_stats(latency, simple=False)
            return False, None, 0.0

    def _try_quick_patterns(self, goal: str) -> Optional[Dict[str, Any]]:
        """Ultra-fast pattern matching for trivial actions"""

        goal_lower = goal.lower().strip()

        # Scroll patterns
        if goal_lower in ["scroll down", "page down", "scroll"]:
            return {
                "tool": "playwright_evaluate",
                "params": {"script": "window.scrollBy(0, window.innerHeight)"}
            }

        if goal_lower in ["scroll up", "page up"]:
            return {
                "tool": "playwright_evaluate",
                "params": {"script": "window.scrollBy(0, -window.innerHeight)"}
            }

        # Screenshot
        if "screenshot" in goal_lower or "capture" in goal_lower:
            return {
                "tool": "playwright_screenshot",
                "params": {}
            }

        # Simple navigation with explicit URL
        url_match = re.search(r'https?://[^\s]+', goal)
        if url_match and ("navigate" in goal_lower or "go to" in goal_lower):
            return {
                "tool": "playwright_navigate",
                "params": {"url": url_match.group(0)}
            }

        return None

    def _build_classification_prompt(self, goal: str, page_context: str) -> str:
        """Build prompt for router classification"""

        return f"""You are a fast action classifier for a web automation agent.

Goal: {goal[:300]}
Page: {page_context[:500]}

Classify this as SIMPLE or COMPLEX, then execute if simple.

SIMPLE (you can handle directly):
1. Click a specific element: "click the login button"
2. Type text: "type 'hello' in search box"
3. Navigate to URL: "go to example.com"
4. Scroll: "scroll down"
5. Screenshot: "take a screenshot"

COMPLEX (needs main model):
1. Ambiguous: "click the best result"
2. Requires analysis: "find the CEO's email"
3. Multi-step: "search for X then extract Y"
4. Error handling: previous action failed

Output format:

SIMPLE
{{"name": "playwright_click", "arguments": {{"selector": "#login-btn"}}}}
CONFIDENCE: 0.95

OR

COMPLEX
Reason: Requires finding and analyzing multiple elements
CONFIDENCE: 0.50

Examples:

Goal: "click the login button"
SIMPLE
{{"name": "playwright_click", "arguments": {{"selector": "button:has-text('Login')"}}}}
CONFIDENCE: 0.98

Goal: "find the email address on this page"
COMPLEX
Reason: Requires extracting and validating email from content
CONFIDENCE: 0.20

Now classify and execute:
"""

    def _parse_classification(self, response: str) -> Tuple[bool, Optional[Dict], float]:
        """
        Parse router response

        Returns: (is_simple, action_dict, confidence)
        """

        # Extract confidence
        confidence = 0.0
        conf_match = re.search(r'CONFIDENCE:\s*([\d\.]+)', response, re.IGNORECASE)
        if conf_match:
            confidence = float(conf_match.group(1))

        # Check if simple
        if response.strip().startswith("SIMPLE"):
            # Extract JSON
            json_match = re.search(r'\{[^}]+\}', response, re.DOTALL)
            if json_match:
                try:
                    tool_call = json.loads(json_match.group(0))

                    # Convert to our format
                    action = {
                        "tool": tool_call.get("name", ""),
                        "params": tool_call.get("arguments", {})
                    }

                    return True, action, confidence

                except json.JSONDecodeError as e:
                    logger.warning(f"Router JSON parse error: {e}")
                    return False, None, 0.0

        # Complex or failed to parse
        return False, None, confidence

    def _update_stats(self, latency_ms: float, simple: bool):
        """Update router statistics"""

        # Update average latency
        n = self.stats["total_calls"]
        current_avg = self.stats["avg_latency_ms"]
        self.stats["avg_latency_ms"] = ((current_avg * (n - 1)) + latency_ms) / n

    def get_stats(self) -> Dict[str, Any]:
        """Get router performance statistics"""

        total = self.stats["total_calls"]
        if total == 0:
            return self.stats

        simple_rate = (self.stats["simple_handled"] / total) * 100

        return {
            **self.stats,
            "simple_rate_pct": f"{simple_rate:.1f}%",
            "complex_rate_pct": f"{100 - simple_rate:.1f}%"
        }

    def reset_stats(self):
        """Reset statistics"""
        self.stats = {
            "total_calls": 0,
            "simple_handled": 0,
            "complex_escalated": 0,
            "avg_latency_ms": 0
        }
