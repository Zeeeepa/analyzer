"""
Intelligent Task Router - Routes tasks to optimal execution paths.

ARCHITECTURE:
1. Deterministic workflows - Known patterns (FB Ads, LinkedIn, etc.) - NO LLM needed
2. Specialized extractors - Our hardened competitive advantage extractors
3. Kimi K2 for ALL planning - Best thinking model handles strategy
4. 0000/ui-tars-1.5-7b:latest for tool execution - Cheap, fast tool calling after plan made
5. Sub-agents for verification - Double-check results

This gives us:
- Speed: Known patterns execute instantly without LLM
- Quality: Kimi K2 plans everything that needs planning
- Cost: 0000/ui-tars-1.5-7b:latest handles cheap tool execution
- Reliability: Sub-agents verify results
"""

import re
from typing import Dict, Any, Optional, Tuple
from enum import Enum
from dataclasses import dataclass
from loguru import logger


class ExecutionPath(Enum):
    """How a task should be executed."""
    DETERMINISTIC = "deterministic"  # Known workflow, no LLM needed
    SPECIALIZED_EXTRACTOR = "specialized_extractor"  # Use our hardened extractors
    KIMI_K2_PLANNING = "kimi_k2_planning"  # Kimi K2 plans, 0000/ui-tars-1.5-7b:latest executes
    SIMPLE_EXECUTION = "simple_execution"  # Single action, just execute it


@dataclass
class RoutingDecision:
    """Result of task routing."""
    path: ExecutionPath
    workflow_name: Optional[str]  # If deterministic
    params: Dict[str, Any]        # Extracted parameters
    confidence: float             # 0.0-1.0
    reasoning: str                # Why this path was chosen
    needs_verification: bool = True  # Should sub-agents verify?


class IntelligentTaskRouter:
    """
    Routes tasks to optimal execution paths.

    Priority order:
    1. Deterministic workflows - Known patterns, NO LLM needed (fastest)
    2. Specialized extractors - Our hardened competitive advantage tools
    3. Simple execution - Single actions like click/type (just do it)
    4. Kimi K2 planning - EVERYTHING ELSE gets Kimi K2 for planning
       Then 0000/ui-tars-1.5-7b:latest executes the plan cheaply
       Then sub-agents verify results

    Key insight: Kimi K2 is our best thinking model. Use it for ALL planning.
    0000/ui-tars-1.5-7b:latest is cheap and fast for tool execution after plan is made.
    """

    # Patterns that map to deterministic workflows
    # IMPORTANT: These patterns should be SPECIFIC to avoid misrouting navigation commands
    DETERMINISTIC_PATTERNS = {
        # FB Ads Library
        "fb_ads": [
            r"(?:facebook|fb|meta)\s*ads?\s*(?:library)?",
            r"ads?\s*library",
            r"search.*(?:facebook|fb|meta).*ads?",
            r"find.*advertisers?\s*on.*(?:facebook|fb)",
            r"(?:go\s+to|open|visit)\s+(?:fb|facebook|meta)\s*ads",  # "go to fb ads..."
            r"advertiser\s*urls?\s*for",  # "advertiser URLs for 'booked meetings'"
        ],
        # LinkedIn - SPECIFIC patterns (not just any mention of LinkedIn)
        "linkedin": [
            r"(?:search|find|look)\s+(?:on\s+)?linkedin",  # "search linkedin", "find on linkedin"
            r"linkedin\s+(?:search|for)\s+",  # "linkedin search for", "linkedin for"
            r"linkedin.*(?:people|profiles?|companies|leads?)",  # "linkedin people", etc.
            r"(?:go\s+to|open|visit)\s+linkedin\s+(?:and|to)",  # "go to linkedin and...", "open linkedin to..."
            r"linkedin.*(?:sdr|prospect|agency)",  # "linkedin SDR", "linkedin prospects"
        ],
        # Reddit - SPECIFIC patterns (not just any mention of Reddit)
        "reddit": [
            r"(?:search|find)\s+(?:on\s+)?reddit",  # "search reddit", "find on reddit"
            r"reddit\s+(?:search|for|posts?|users?)",  # "reddit search", "reddit posts", etc.
            r"r/\w+",  # Subreddit pattern
            r"find.*warm.*leads?.*reddit",
            r"(?:go\s+to|open|visit)\s+reddit\s+(?:and|to)",  # "go to reddit and...", "open reddit to..."
            r"reddit.*(?:profile|user)\s*urls?",  # "reddit user profile URLs"
            r"reddit.*(?:discussing|about|on)\s+",  # "reddit discussing lead generation"
        ],
        # Google Maps
        "google_maps": [
            r"google\s*maps?\s*(?:search)?",
            r"(?:find|search)\s*(?:local\s*)?businesses?",
            r"maps?\s*(?:search|lookup)",
            r"(?:go\s+to|open|visit)\s+google\s*maps?\s+(?:and|to)",  # "go to google maps and..."
            r"google\s*maps?.*(?:listing|agency|business)",  # "google maps listing", "google maps agency"
        ],
        # Gmail
        "gmail": [
            r"(?:open|check|go\s*to)\s*gmail",
            r"gmail\s*(?:inbox|email)?",
            r"check\s*(?:my\s*)?email",
        ],
    }

    # Patterns that need specialized extractors
    EXTRACTOR_PATTERNS = {
        "fb_ads_extractor": [
            r"extract.*(?:facebook|fb)\s*ads?",
            r"scrape.*(?:facebook|fb)\s*ads?",
            r"get.*advertisers?.*(?:facebook|fb)",
        ],
        "reddit_extractor": [
            r"extract.*reddit\s*posts?",
            r"find.*warm.*leads?.*reddit",
            r"scrape.*reddit",
        ],
        "linkedin_extractor": [
            r"extract.*linkedin\s*(?:profiles?|companies?)",
            r"scrape.*linkedin",
        ],
    }

    # Simple single-action patterns (just execute, no planning needed)
    SIMPLE_EXECUTION_PATTERNS = [
        r"^(?:click|type|scroll|press|hover|select)\s+",
        r"^take\s*(?:a\s*)?screenshot",
        r"^(?:get|what\s*is)\s*(?:the\s*)?(?:page\s*)?title",
        r"^go\s*back$",
        r"^refresh$",
        r"^close\s*(?:the\s*)?(?:tab|window|popup)",
    ]

    # UI-TARS feature configuration patterns (simple execution)
    UITARS_CONFIG_PATTERNS = [
        r"(?:use|enable)\s+system[-\s]?2",
        r"(?:use|enable)\s+(?:thought|thinking)\s+(?:and\s+)?reflection",
        r"screenshot\s+with\s+context",
        r"(?:use|enable)\s+conversation\s+context",
        r"retry\s+with\s+tiered\s+timeouts?",
        r"(?:use|enable)\s+tiered\s+(?:retry|timeouts?)",
        r"normalize\s+coordinates?",
        r"(?:use|enable)\s+normalized\s+coordinates?",
    ]

    # Navigation patterns (simple, just navigate)
    # Priority: Catch navigation commands BEFORE they can be misrouted to other handlers
    SIMPLE_NAVIGATION_PATTERNS = [
        # Explicit URLs
        r"^(?:go\s*to|open|navigate\s*to)\s+https?://[^\s]+$",
        r"^(?:visit|open)\s+\w+\.\w+$",  # visit google.com
        # Service/site navigation (go to Gmail, go to Zoho Mail, etc.)
        r"(?:go\s+to|navigate\s+to|open|visit)\s+(?:the\s+)?(?:\w+\s+)?(?:login|site|page|website|portal|mail|inbox)",
        # "go to X" where X is a service name (not a search/extract command)
        r"(?:go\s+to|navigate\s+to|open|visit)\s+(?!.*(?:search|find|extract|scrape))",
    ]

    def route(self, prompt: str) -> RoutingDecision:
        """
        Determine the optimal execution path for a task.

        ROUTING LOGIC:
        1. Deterministic workflows - Known patterns, NO LLM needed
        2. Specialized extractors - Our hardened tools
        3. Simple execution - Single actions, just do it
        4. Kimi K2 planning - EVERYTHING ELSE (Kimi plans, 0000/ui-tars-1.5-7b:latest executes)

        Args:
            prompt: User's natural language prompt

        Returns:
            RoutingDecision with path, workflow, params, confidence, reasoning
        """
        prompt_lower = prompt.lower().strip()

        # 1. Check for deterministic workflows first (fastest - no LLM at all)
        for workflow_name, patterns in self.DETERMINISTIC_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, prompt_lower, re.I):
                    params = self._extract_params(prompt, workflow_name)
                    return RoutingDecision(
                        path=ExecutionPath.DETERMINISTIC,
                        workflow_name=workflow_name,
                        params=params,
                        confidence=0.95,
                        reasoning=f"Deterministic workflow '{workflow_name}' - no LLM needed",
                        needs_verification=False  # Deterministic = reliable
                    )

        # 2. Check for specialized extractor patterns (our competitive advantage)
        for extractor_name, patterns in self.EXTRACTOR_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, prompt_lower, re.I):
                    params = self._extract_params(prompt, extractor_name)
                    return RoutingDecision(
                        path=ExecutionPath.SPECIALIZED_EXTRACTOR,
                        workflow_name=extractor_name,
                        params=params,
                        confidence=0.9,
                        reasoning=f"Specialized extractor '{extractor_name}' - hardened & bulletproof",
                        needs_verification=False  # Already bulletproof
                    )

        # 3. Check for UI-TARS configuration patterns (simple execution)
        for pattern in self.UITARS_CONFIG_PATTERNS:
            if re.search(pattern, prompt_lower, re.I):
                return RoutingDecision(
                    path=ExecutionPath.SIMPLE_EXECUTION,
                    workflow_name=None,
                    params={"uitars_config": True},
                    confidence=0.95,
                    reasoning="UI-TARS feature configuration - simple toggle",
                    needs_verification=False
                )

        # 4. Check for simple single-action patterns (just execute, no planning)
        for pattern in self.SIMPLE_EXECUTION_PATTERNS:
            if re.search(pattern, prompt_lower, re.I):
                return RoutingDecision(
                    path=ExecutionPath.SIMPLE_EXECUTION,
                    workflow_name=None,
                    params={},
                    confidence=0.9,
                    reasoning="Single action - just execute it",
                    needs_verification=False  # Too simple to verify
                )

        # 5. Check for simple navigation (just go there)
        for pattern in self.SIMPLE_NAVIGATION_PATTERNS:
            if re.search(pattern, prompt_lower, re.I):
                url_match = re.search(r'https?://[^\s]+', prompt)
                return RoutingDecision(
                    path=ExecutionPath.SIMPLE_EXECUTION,
                    workflow_name=None,
                    params={"url": url_match.group(0) if url_match else ""},
                    confidence=0.9,
                    reasoning="Simple navigation - just go there",
                    needs_verification=False
                )

        # 6. EVERYTHING ELSE: Kimi K2 for planning, 0000/ui-tars-1.5-7b:latest for execution
        # This is the key insight: Kimi K2 is our BEST model, use it for ALL planning
        return RoutingDecision(
            path=ExecutionPath.KIMI_K2_PLANNING,
            workflow_name=None,
            params={},
            confidence=0.85,
            reasoning="Kimi K2 will plan this task, 0000/ui-tars-1.5-7b:latest will execute, sub-agents will verify",
            needs_verification=True  # Sub-agents should double-check
        )

    def _extract_params(self, prompt: str, workflow_name: str) -> Dict[str, Any]:
        """Extract parameters from prompt based on workflow type."""
        params = {}
        prompt_lower = prompt.lower()
        query = None

        # Try quoted text first (e.g., "booked meetings")
        quoted_match = re.search(r'["\']([^"\']+)["\']', prompt)
        if quoted_match:
            query = quoted_match.group(1).strip()

        # Try to extract topic/query from common patterns
        if not query:
            # Pattern: "discussing X" or "about X"
            topic_match = re.search(r'(?:discussing|about|on|for)\s+([a-zA-Z0-9\s\-]+?)(?:\s*\.|$|,|\s+or\s+|\s+and\s+output)', prompt, re.I)
            if topic_match:
                query = topic_match.group(1).strip()

        if not query:
            # Pattern: "for 'X'" or "for X"
            for_match = re.search(r'\bfor\s+[\'"]?([a-zA-Z0-9\s\-]+?)[\'"]?(?:\s*\.|$|,|\s+and\s+)', prompt, re.I)
            if for_match:
                query = for_match.group(1).strip()

        if not query:
            # Pattern: keywords after the platform mention
            platform_patterns = {
                "fb_ads": r'(?:fb|facebook|meta)\s+ads?\s+(?:library\s+)?(?:and\s+)?(?:output|find|get|search)?.*?(?:for\s+)?["\']?([a-zA-Z0-9\s\-]+?)["\']?(?:\s*\.|$)',
                "reddit": r'reddit\s+(?:and\s+)?(?:output|find|get|search)?.*?(?:discussing|about|for|on)\s+([a-zA-Z0-9\s\-]+?)(?:\s*\.|$|,|\s+or\s+)',
                "linkedin": r'linkedin\s+(?:and\s+)?(?:output|find|get|search)?.*?(?:for\s+)?["\']?([a-zA-Z0-9\s\-]+?)["\']?(?:\s*\.|$)',
                "google_maps": r'google\s*maps?\s+(?:and\s+)?(?:output|find|get|search)?.*?(?:for\s+)?["\']?([a-zA-Z0-9\s\-]+?)["\']?(?:\s*\.|$)',
            }
            pattern = platform_patterns.get(workflow_name)
            if pattern:
                match = re.search(pattern, prompt_lower)
                if match:
                    query = match.group(1).strip()

        # Remove common prefixes as fallback
        if not query:
            prefixes = {
                "fb_ads": [
                    "search facebook ads for ", "search fb ads for ",
                    "find advertisers on facebook for ", "facebook ads library for "
                ],
                "linkedin": [
                    "search linkedin for ", "find on linkedin ",
                    "linkedin search for ", "find people on linkedin "
                ],
                "reddit": [
                    "search reddit for ", "find on reddit ",
                    "reddit search for ", "r/"
                ],
                "google_maps": [
                    "search google maps for ", "find businesses ",
                    "google maps search for ", "local businesses "
                ],
                "gmail": ["open gmail", "check email", "gmail inbox"],
            }
            for prefix in prefixes.get(workflow_name, []):
                if prompt_lower.startswith(prefix):
                    query = prompt[len(prefix):].strip()
                    break

        # Clean up query
        if query:
            query = query.strip('"').strip("'").strip()
            # Remove common trailing words
            query = re.sub(r'\s+(urls?|profiles?|advertiser|listing)s?\s*$', '', query, flags=re.I)
            if query:
                params["search_query"] = query

        # Extract URL if present
        url_match = re.search(r'https?://[^\s]+', prompt)
        if url_match:
            params["url"] = url_match.group(0)

        return params

    def should_use_kimi_k2(self, prompt: str) -> Tuple[bool, str]:
        """
        Quick check if task should use Kimi K2.

        Returns:
            (should_use, reason)
        """
        decision = self.route(prompt)
        should_use = decision.path == ExecutionPath.KIMI_K2_PLANNING
        return should_use, decision.reasoning


# Singleton instance
_router_instance = None


def get_router() -> IntelligentTaskRouter:
    """Get the singleton router instance."""
    global _router_instance
    if _router_instance is None:
        _router_instance = IntelligentTaskRouter()
    return _router_instance


def route_task(prompt: str) -> RoutingDecision:
    """Route a task to optimal execution path."""
    return get_router().route(prompt)


def should_use_kimi_k2(prompt: str) -> Tuple[bool, str]:
    """Quick check if task should use Kimi K2."""
    return get_router().should_use_kimi_k2(prompt)
