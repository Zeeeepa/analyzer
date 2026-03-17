"""
Semantic Action Cache - Skip model calls for common patterns

Caches successful action sequences for frequently-used workflows.
Expected cache hit rate: 30-40% of actions = 0ms inference time.
"""

from typing import Optional, List, Dict, Any
import re
from loguru import logger


# Common action patterns across platforms
ACTION_PATTERNS = {
    "linkedin_search_person": {
        "trigger": ["search linkedin", "find on linkedin", "linkedin person", "search for"],
        "url_match": "linkedin.com",
        "confidence": 0.95,
        "sequence": [
            {
                "tool": "playwright_click",
                "params": {"selector": "input.search-global-typeahead__input"}
            },
            {
                "tool": "playwright_fill",
                "params": {
                    "selector": "input.search-global-typeahead__input",
                    "value": "{query}"
                }
            },
            {
                "tool": "playwright_click",
                "params": {"selector": "button.search-global-typeahead__search-button"}
            }
        ]
    },

    "facebook_ads_search": {
        "trigger": ["facebook ads", "ads library", "search ads", "find advertiser"],
        "url_match": "facebook.com/ads/library",
        "confidence": 0.95,
        "sequence": [
            {
                "tool": "playwright_fill",
                "params": {
                    "selector": "input[placeholder='Search ads']",
                    "value": "{query}"
                }
            },
            {
                "tool": "playwright_click",
                "params": {"selector": "button[type='submit']"}
            }
        ]
    },

    "reddit_visit_subreddit": {
        "trigger": ["go to r/", "visit r/", "navigate to r/"],
        "url_match": "reddit.com",
        "confidence": 0.98,
        "sequence": [
            {
                "tool": "playwright_navigate",
                "params": {"url": "https://reddit.com/r/{subreddit}"}
            }
        ]
    },

    "linkedin_login": {
        "trigger": ["login to linkedin", "sign in linkedin", "authenticate linkedin"],
        "url_match": "linkedin.com",
        "confidence": 0.95,
        "sequence": [
            {
                "tool": "playwright_navigate",
                "params": {"url": "https://linkedin.com/login"}
            },
            {
                "tool": "playwright_fill",
                "params": {
                    "selector": "input#username",
                    "value": "{email}"
                }
            },
            {
                "tool": "playwright_fill",
                "params": {
                    "selector": "input#password",
                    "value": "{password}"
                }
            },
            {
                "tool": "playwright_click",
                "params": {"selector": "button[type='submit']"}
            }
        ]
    },

    "simple_navigation": {
        "trigger": ["navigate to", "go to", "open"],
        "url_match": None,  # Any URL
        "confidence": 0.99,
        "sequence": [
            {
                "tool": "playwright_navigate",
                "params": {"url": "{url}"}
            }
        ]
    },

    "scroll_down": {
        "trigger": ["scroll down", "scroll to bottom", "page down"],
        "url_match": None,
        "confidence": 0.99,
        "sequence": [
            {
                "tool": "playwright_evaluate",
                "params": {"script": "window.scrollBy(0, window.innerHeight)"}
            }
        ]
    },

    "scroll_up": {
        "trigger": ["scroll up", "scroll to top", "page up"],
        "url_match": None,
        "confidence": 0.99,
        "sequence": [
            {
                "tool": "playwright_evaluate",
                "params": {"script": "window.scrollBy(0, -window.innerHeight)"}
            }
        ]
    },

    "take_screenshot": {
        "trigger": ["screenshot", "capture page", "take picture"],
        "url_match": None,
        "confidence": 0.99,
        "sequence": [
            {
                "tool": "playwright_screenshot",
                "params": {}
            }
        ]
    }
}


class ActionCache:
    """
    Semantic action cache for common patterns

    Matches user goals to cached action sequences and returns them
    without calling the LLM.
    """

    def __init__(self):
        self.patterns = ACTION_PATTERNS
        self.hit_count = 0
        self.miss_count = 0

    def get_cached_action(
        self,
        goal: str,
        current_url: str,
        variables: Optional[Dict[str, str]] = None
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Check if goal matches a cached pattern

        Args:
            goal: User's goal/prompt
            current_url: Current page URL
            variables: Optional variables to interpolate

        Returns:
            List of tool calls or None if no match
        """

        goal_lower = goal.lower()

        # Try each pattern
        for pattern_name, pattern in self.patterns.items():
            # Check if trigger keywords match
            if not self._matches_trigger(goal_lower, pattern["trigger"]):
                continue

            # Check URL if pattern requires specific URL
            url_match = pattern.get("url_match")
            if url_match and url_match not in current_url:
                continue

            # Extract variables from goal
            extracted_vars = self._extract_variables(goal, pattern_name)

            # Merge with provided variables
            if variables:
                extracted_vars.update(variables)

            # Interpolate sequence
            sequence = self._interpolate_sequence(pattern["sequence"], extracted_vars)

            logger.info(f"✓ Cache HIT: {pattern_name} (confidence: {pattern['confidence']})")
            self.hit_count += 1

            return sequence

        logger.debug(f"Cache MISS for: {goal[:50]}")
        self.miss_count += 1

        return None

    def _matches_trigger(self, goal: str, triggers: List[str]) -> bool:
        """Check if goal matches any trigger keyword"""
        return any(trigger in goal for trigger in triggers)

    def _extract_variables(self, goal: str, pattern_name: str) -> Dict[str, str]:
        """Extract variables from goal based on pattern"""

        variables = {}

        # LinkedIn search: extract query
        if pattern_name == "linkedin_search_person":
            # "search linkedin for 'John Doe'" -> query="John Doe"
            match = re.search(r"(?:for|search)\s+['\"]?([^'\"]+)['\"]?", goal, re.IGNORECASE)
            if match:
                variables["query"] = match.group(1)

        # Facebook ads: extract query
        elif pattern_name == "facebook_ads_search":
            match = re.search(r"(?:for|search)\s+['\"]?([^'\"]+)['\"]?", goal, re.IGNORECASE)
            if match:
                variables["query"] = match.group(1)

        # Reddit subreddit
        elif pattern_name == "reddit_visit_subreddit":
            match = re.search(r"r/(\w+)", goal)
            if match:
                variables["subreddit"] = match.group(1)

        # Navigation: extract URL
        elif pattern_name == "simple_navigation":
            # Look for URL patterns
            url_pattern = r'https?://[^\s]+'
            match = re.search(url_pattern, goal)
            if match:
                variables["url"] = match.group(0)
            else:
                # Try domain patterns
                domain_match = re.search(r'(?:to|open)\s+([a-z0-9\-\.]+\.[a-z]{2,})', goal, re.IGNORECASE)
                if domain_match:
                    variables["url"] = "https://" + domain_match.group(1)

        return variables

    def _interpolate_sequence(
        self,
        sequence: List[Dict[str, Any]],
        variables: Dict[str, str]
    ) -> List[Dict[str, Any]]:
        """Interpolate variables into sequence"""

        interpolated = []

        for action in sequence:
            interpolated_action = {
                "tool": action["tool"],
                "params": {}
            }

            for key, value in action["params"].items():
                if isinstance(value, str) and '{' in value:
                    # Interpolate variable
                    try:
                        interpolated_action["params"][key] = value.format(**variables)
                    except KeyError as e:
                        logger.warning(f"Missing variable {e} for interpolation")
                        # Keep original template
                        interpolated_action["params"][key] = value
                else:
                    interpolated_action["params"][key] = value

            interpolated.append(interpolated_action)

        return interpolated

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""

        total = self.hit_count + self.miss_count
        hit_rate = (self.hit_count / total * 100) if total > 0 else 0

        return {
            "hits": self.hit_count,
            "misses": self.miss_count,
            "total": total,
            "hit_rate": f"{hit_rate:.1f}%"
        }

    def add_pattern(
        self,
        name: str,
        triggers: List[str],
        sequence: List[Dict[str, Any]],
        url_match: Optional[str] = None,
        confidence: float = 0.9
    ):
        """Dynamically add a new pattern to the cache"""

        self.patterns[name] = {
            "trigger": triggers,
            "url_match": url_match,
            "confidence": confidence,
            "sequence": sequence
        }

        logger.info(f"Added new pattern to cache: {name}")
