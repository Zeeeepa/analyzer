"""
Command Parser for Eversale CLI
Parses natural language into structured browser actions for deterministic execution.
Matches Playwright MCP's precision by handling commands without LLM interpretation.
"""

import re
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from enum import Enum


class ActionType(Enum):
    """Types of browser actions we can execute deterministically."""
    NAVIGATE = "navigate"
    CLICK = "click"
    TYPE = "type"
    SCROLL = "scroll"
    WAIT = "wait"
    SCREENSHOT = "screenshot"
    SELECT = "select"
    HOVER = "hover"
    PRESS_KEY = "press_key"
    FILL_FORM = "fill_form"
    SEARCH = "search"
    EXTRACT = "extract"
    BACK = "back"
    FORWARD = "forward"
    REFRESH = "refresh"
    CLOSE = "close"
    # Enhanced UI-TARS features
    ENABLE_SYSTEM2 = "enable_system2"
    ENABLE_CONTEXT = "enable_context"
    ENABLE_RETRY = "enable_retry"
    ENABLE_NORMALIZE = "enable_normalize"
    UNKNOWN = "unknown"


@dataclass
class ParsedAction:
    """A structured browser action parsed from natural language."""
    action_type: ActionType
    target: Optional[str] = None  # URL, selector, or element description
    value: Optional[str] = None   # Text to type, option to select, etc.
    params: Optional[Dict[str, Any]] = None  # Additional parameters
    confidence: float = 1.0  # How confident we are in the parse (0-1)
    raw_text: str = ""  # Original text that was parsed

    def to_mcp_call(self) -> Optional[Tuple[str, Dict[str, Any]]]:
        """Convert to MCP tool call format (tool_name, params)."""
        if self.action_type == ActionType.NAVIGATE:
            return ("playwright_navigate", {"url": self.target})
        elif self.action_type == ActionType.CLICK:
            return ("playwright_click", {"element": self.target, "ref": self.params.get("ref") if self.params else None})
        elif self.action_type == ActionType.TYPE:
            return ("playwright_type", {"element": self.target, "text": self.value, "ref": self.params.get("ref") if self.params else None})
        elif self.action_type == ActionType.SCROLL:
            direction = self.params.get("direction", "down") if self.params else "down"
            return ("playwright_evaluate", {"function": f"window.scrollBy(0, {'500' if direction == 'down' else '-500'})"})
        elif self.action_type == ActionType.WAIT:
            seconds = self.params.get("seconds", 2) if self.params else 2
            return ("playwright_wait", {"time": seconds})
        elif self.action_type == ActionType.SCREENSHOT:
            return ("playwright_screenshot", {})
        elif self.action_type == ActionType.SELECT:
            return ("playwright_select_option", {"element": self.target, "values": [self.value]})
        elif self.action_type == ActionType.HOVER:
            return ("playwright_hover", {"element": self.target, "ref": self.params.get("ref") if self.params else None})
        elif self.action_type == ActionType.PRESS_KEY:
            return ("playwright_press_key", {"key": self.value})
        elif self.action_type == ActionType.SEARCH:
            # Search is typically type + submit
            return ("playwright_type", {"element": self.target or "search box", "text": self.value, "submit": True})
        elif self.action_type == ActionType.BACK:
            return ("playwright_navigate_back", {})
        elif self.action_type == ActionType.FORWARD:
            return ("playwright_evaluate", {"function": "window.history.forward()"})
        elif self.action_type == ActionType.REFRESH:
            return ("playwright_evaluate", {"function": "window.location.reload()"})
        elif self.action_type == ActionType.CLOSE:
            return ("playwright_close", {})
        return None


class CommandParser:
    """
    Parses natural language commands into structured browser actions.
    Designed to match Playwright MCP's precision by deterministically
    handling common patterns without requiring LLM interpretation.
    """

    # Navigation patterns - match "go to", "navigate to", "open", etc.
    NAVIGATE_PATTERNS = [
        r'(?:go\s+to|navigate\s+to|open|visit|browse\s+to|head\s+to)\s+(.+)',
        r'(?:take\s+me\s+to|bring\s+up|load)\s+(.+)',
        r'(?:show\s+me|display|pull\s+up)\s+(.+)',
        r'(?:access|get\s+to)\s+(.+)',
        r'^(https?://\S+)$',  # Plain URL
        r'^(www\.\S+)$',  # www URL without protocol
    ]

    # Click patterns
    CLICK_PATTERNS = [
        r'click\s+(?:on\s+)?(?:the\s+)?(.+)',
        r'press\s+(?:the\s+)?(.+?)(?:\s+button)?$',
        r'tap\s+(?:on\s+)?(?:the\s+)?(.+)',
        r'select\s+(?:the\s+)?(.+?)(?:\s+option)?$',
        r'hit\s+(?:the\s+)?(.+?)(?:\s+button)?$',
        r'push\s+(?:the\s+)?(.+?)(?:\s+button)?$',
        r'activate\s+(?:the\s+)?(.+)',
        r'choose\s+(?:the\s+)?(.+)',
    ]

    # Type/input patterns
    TYPE_PATTERNS = [
        r'type\s+["\'](.+?)["\']\s+(?:in(?:to)?|in\s+the)\s+(.+)',
        r'enter\s+["\'](.+?)["\']\s+(?:in(?:to)?|in\s+the)\s+(.+)',
        r'fill\s+(?:in\s+)?(?:the\s+)?(.+?)\s+with\s+["\'](.+?)["\']',
        r'fill\s+(?:in\s+)?(?:the\s+)?(.+?)\s+with\s+(\S+)',  # Fill without quotes
        r'input\s+["\'](.+?)["\']\s+(?:in(?:to)?|in\s+the)\s+(.+)',
        r'type\s+(\S+)\s+(?:in(?:to)?|in\s+the)\s+(.+)',  # Type single word without quotes
        r'write\s+["\'](.+?)["\']\s+(?:in(?:to)?|in\s+the)\s+(.+)',
        r'write\s+(.+?)\s+(?:in(?:to)?|in\s+the)\s+(.+)',  # Write without quotes
        r'put\s+["\'](.+?)["\']\s+(?:in(?:to)?|in\s+the)\s+(.+)',
        r'put\s+(\S+)\s+(?:in(?:to)?|in\s+the)\s+(.+)',  # Put without quotes
        r'insert\s+["\'](.+?)["\']\s+(?:in(?:to)?|in\s+the)\s+(.+)',
        r'insert\s+(.+?)\s+(?:in(?:to)?|in\s+the)\s+(.+)',  # Insert without quotes
    ]

    # Search patterns (type + submit)
    SEARCH_PATTERNS = [
        r'search\s+(?:for\s+)?["\'](.+?)["\'](?:\s+(?:on|in|at)\s+(.+))?',
        r'search\s+(?:for\s+)?(.+?)(?:\s+(?:on|in|at)\s+(.+))?$',
        r'find\s+["\'](.+?)["\'](?:\s+(?:on|in|at)\s+(.+))?',
        r'find\s+(.+?)(?:\s+(?:on|in|at)\s+(.+))?$',  # Find without quotes
        r'look\s+(?:up|for)\s+["\'](.+?)["\'](?:\s+(?:on|in|at)\s+(.+))?',
        r'look\s+(?:up|for)\s+(.+?)(?:\s+(?:on|in|at)\s+(.+))?$',  # Look up without quotes
        r'google\s+["\'](.+?)["\']',
        r'google\s+(.+)$',
        r'query\s+(?:for\s+)?["\'](.+?)["\'](?:\s+(?:on|in|at)\s+(.+))?',
        r'query\s+(?:for\s+)?(.+)$',  # Query without quotes
    ]

    # Scroll patterns
    SCROLL_PATTERNS = [
        r'scroll\s+(down|up)(?:\s+(?:the\s+)?page)?',
        r'scroll\s+to\s+(?:the\s+)?(top|bottom)(?:\s+of\s+(?:the\s+)?page)?',
        r'page\s+(down|up)',
        r'go\s+to\s+(?:the\s+)?(top|bottom)(?:\s+of\s+(?:the\s+)?page)?',
        r'move\s+(down|up)(?:\s+(?:the\s+)?page)?',
    ]

    # Wait patterns
    WAIT_PATTERNS = [
        r'wait\s+(?:for\s+)?(\d+)\s*(?:seconds?|secs?|s)?',
        r'pause\s+(?:for\s+)?(\d+)\s*(?:seconds?|secs?|s)?',
        r'sleep\s+(?:for\s+)?(\d+)\s*(?:seconds?|secs?|s)?',
        r'wait(?:\s+a\s+(?:moment|bit|second))?',
        r'hold\s+(?:for\s+)?(\d+)\s*(?:seconds?|secs?|s)?',
        r'delay\s+(?:for\s+)?(\d+)\s*(?:seconds?|secs?|s)?',
    ]

    # Screenshot patterns
    SCREENSHOT_PATTERNS = [
        r'(?:take\s+)?(?:a\s+)?screenshot',
        r'capture\s+(?:the\s+)?(?:screen|page)',
        r'snap\s+(?:the\s+)?(?:screen|page)',
        r'screencap(?:ture)?',
        r'grab\s+(?:a\s+)?(?:screenshot|screen)',
    ]

    # Key press patterns
    KEY_PATTERNS = [
        r'press\s+(?:the\s+)?(enter|escape|tab|backspace|delete|space|arrow\s*(?:up|down|left|right))(?:\s+key)?',
        r'hit\s+(?:the\s+)?(enter|escape|tab|backspace|delete|space)(?:\s+key)?',
        r'push\s+(?:the\s+)?(enter|escape|tab)(?:\s+key)?',
    ]

    # Hover patterns
    HOVER_PATTERNS = [
        r'hover\s+(?:over\s+)?(?:the\s+)?(.+)',
        r'mouse\s+over\s+(?:the\s+)?(.+)',
        r'move\s+(?:mouse\s+)?to\s+(.+)',
    ]

    # Back/Forward patterns
    BACK_FORWARD_PATTERNS = [
        r'(?:go\s+)?back',
        r'navigate\s+back',
        r'previous\s+page',
        r'(?:go\s+)?forward',
        r'navigate\s+forward',
        r'next\s+page',
    ]

    # Refresh patterns
    REFRESH_PATTERNS = [
        r'refresh(?:\s+(?:the\s+)?page)?',
        r'reload(?:\s+(?:the\s+)?page)?',
        r'update\s+(?:the\s+)?page',
        r'f5',
    ]

    # Close patterns
    CLOSE_PATTERNS = [
        r'close(?:\s+(?:the\s+)?(?:tab|browser|window|page))?',
        r'exit(?:\s+(?:the\s+)?(?:tab|browser|window|page))?',
        r'quit(?:\s+(?:the\s+)?(?:browser|window))?',
    ]

    # UI-TARS System-2 reasoning patterns
    SYSTEM2_PATTERNS = [
        r'use\s+system[-\s]?2(?:\s+reasoning)?',
        r'enable\s+system[-\s]?2',
        r'with\s+system[-\s]?2',
        r'use\s+(?:thought|thinking)\s+(?:and\s+)?reflection',
        r'enable\s+(?:thought|thinking)\s+(?:and\s+)?reflection',
        r'think\s+before\s+acting',
        r'use\s+deliberate\s+reasoning',
    ]

    # ConversationContext patterns
    CONTEXT_PATTERNS = [
        r'(?:take\s+)?screenshot\s+with\s+context',
        r'use\s+conversation\s+context',
        r'enable\s+context\s+management',
        r'(?:keep|maintain)\s+screenshot\s+(?:history|context)',
        r'context[-\s]aware\s+screenshot',
    ]

    # UI-TARS retry config patterns
    RETRY_PATTERNS = [
        r'retry\s+with\s+tiered\s+timeouts?',
        r'use\s+tiered\s+(?:retry|timeouts?)',
        r'enable\s+smart\s+retry',
        r'use\s+ui[-\s]?tars\s+retry',
        r'retry\s+with\s+(?:exponential\s+)?backoff',
    ]

    # Coordinate normalization patterns
    NORMALIZE_PATTERNS = [
        r'normalize\s+coordinates?',
        r'use\s+normalized\s+coordinates?',
        r'enable\s+coordinate\s+normalization',
        r'use\s+0[-\s]?1000\s+(?:range|coordinates?)',
        r'(?:convert|transform)\s+coordinates?',
    ]

    # Service URL mappings (imported from service_mapper)
    SERVICE_URLS = {
        # Email services
        "gmail": "https://mail.google.com",
        "google mail": "https://mail.google.com",
        "mail.google": "https://mail.google.com",
        "zoho": "https://mail.zoho.com",
        "zoho mail": "https://mail.zoho.com",
        "outlook": "https://outlook.live.com",
        "yahoo mail": "https://mail.yahoo.com",
        "protonmail": "https://mail.proton.me",

        # Social media
        "facebook": "https://www.facebook.com",
        "fb": "https://www.facebook.com",
        "twitter": "https://twitter.com",
        "x": "https://twitter.com",
        "linkedin": "https://www.linkedin.com",
        "instagram": "https://www.instagram.com",
        "reddit": "https://www.reddit.com",
        "tiktok": "https://www.tiktok.com",
        "youtube": "https://www.youtube.com",

        # Google services
        "google": "https://www.google.com",
        "google maps": "https://www.google.com/maps",
        "maps": "https://www.google.com/maps",
        "google drive": "https://drive.google.com",
        "google docs": "https://docs.google.com",
        "google sheets": "https://sheets.google.com",
        "google calendar": "https://calendar.google.com",

        # Business/work
        "github": "https://github.com",
        "slack": "https://slack.com",
        "notion": "https://notion.so",
        "trello": "https://trello.com",
        "asana": "https://app.asana.com",
        "jira": "https://www.atlassian.com/software/jira",
        "hubspot": "https://app.hubspot.com",
        "salesforce": "https://login.salesforce.com",

        # Shopping/commerce
        "amazon": "https://www.amazon.com",
        "ebay": "https://www.ebay.com",
        "etsy": "https://www.etsy.com",
        "shopify": "https://www.shopify.com",

        # Ads/marketing
        "facebook ads": "https://www.facebook.com/ads/library",
        "fb ads": "https://www.facebook.com/ads/library",
        "fb ads library": "https://www.facebook.com/ads/library",
        "facebook ads library": "https://www.facebook.com/ads/library",
        "meta ads library": "https://www.facebook.com/ads/library",
        "google ads": "https://ads.google.com",

        # Other
        "wikipedia": "https://www.wikipedia.org",
        "bing": "https://www.bing.com",
        "duckduckgo": "https://duckduckgo.com",

        # AI Assistants
        "claude": "https://claude.ai",
        "claude.ai": "https://claude.ai",
        "anthropic": "https://claude.ai",
        "chatgpt": "https://chatgpt.com",
        "chatgpt.com": "https://chatgpt.com",
        "openai": "https://chatgpt.com",
        "chat.openai": "https://chatgpt.com",
        "gemini": "https://gemini.google.com",
        "google gemini": "https://gemini.google.com",
        "bard": "https://gemini.google.com",
        "perplexity": "https://www.perplexity.ai",
        "perplexity.ai": "https://www.perplexity.ai",
        "grok": "https://grok.com",
        "copilot": "https://copilot.microsoft.com",
        "microsoft copilot": "https://copilot.microsoft.com",

        # SDR/Outbound Tools
        "apollo": "https://app.apollo.io",
        "apollo.io": "https://app.apollo.io",
        "lemlist": "https://app.lemlist.com",
        "smartlead": "https://app.smartlead.ai",
        "smartlead.ai": "https://app.smartlead.ai",
        "instantly": "https://app.instantly.ai",
        "instantly.ai": "https://app.instantly.ai",
        "hunter": "https://hunter.io",
        "hunter.io": "https://hunter.io",
        "snov": "https://app.snov.io",
        "snov.io": "https://app.snov.io",
        "reply.io": "https://app.reply.io",
        "woodpecker": "https://app.woodpecker.co",
        "mailshake": "https://app.mailshake.com",
        "outreach": "https://app.outreach.io",
        "outreach.io": "https://app.outreach.io",
        "salesloft": "https://app.salesloft.com",
        "lusha": "https://www.lusha.com",
        "zoominfo": "https://app.zoominfo.com",
        "clearbit": "https://clearbit.com",
        "rocketreach": "https://rocketreach.co",
        "seamless": "https://www.seamless.ai",
        "seamless.ai": "https://www.seamless.ai",
        "warmbox": "https://app.warmbox.ai",
        "warmup inbox": "https://www.warmupinbox.com",
    }

    def __init__(self):
        """Initialize the command parser."""
        self._compile_patterns()

    def _compile_patterns(self):
        """Pre-compile regex patterns for performance."""
        self._navigate_re = [re.compile(p, re.IGNORECASE) for p in self.NAVIGATE_PATTERNS]
        self._click_re = [re.compile(p, re.IGNORECASE) for p in self.CLICK_PATTERNS]
        self._type_re = [re.compile(p, re.IGNORECASE) for p in self.TYPE_PATTERNS]
        self._search_re = [re.compile(p, re.IGNORECASE) for p in self.SEARCH_PATTERNS]
        self._scroll_re = [re.compile(p, re.IGNORECASE) for p in self.SCROLL_PATTERNS]
        self._wait_re = [re.compile(p, re.IGNORECASE) for p in self.WAIT_PATTERNS]
        self._screenshot_re = [re.compile(p, re.IGNORECASE) for p in self.SCREENSHOT_PATTERNS]
        self._key_re = [re.compile(p, re.IGNORECASE) for p in self.KEY_PATTERNS]
        self._hover_re = [re.compile(p, re.IGNORECASE) for p in self.HOVER_PATTERNS]
        self._back_forward_re = [re.compile(p, re.IGNORECASE) for p in self.BACK_FORWARD_PATTERNS]
        self._refresh_re = [re.compile(p, re.IGNORECASE) for p in self.REFRESH_PATTERNS]
        self._close_re = [re.compile(p, re.IGNORECASE) for p in self.CLOSE_PATTERNS]
        # UI-TARS feature patterns
        self._system2_re = [re.compile(p, re.IGNORECASE) for p in self.SYSTEM2_PATTERNS]
        self._context_re = [re.compile(p, re.IGNORECASE) for p in self.CONTEXT_PATTERNS]
        self._retry_re = [re.compile(p, re.IGNORECASE) for p in self.RETRY_PATTERNS]
        self._normalize_re = [re.compile(p, re.IGNORECASE) for p in self.NORMALIZE_PATTERNS]

    def parse(self, command: str) -> ParsedAction:
        """
        Parse a natural language command into a structured action.

        Args:
            command: Natural language command string

        Returns:
            ParsedAction with the structured action details
        """
        command = command.strip()
        if not command:
            return ParsedAction(ActionType.UNKNOWN, raw_text=command, confidence=0.0)

        # Try each parser in order of specificity
        # UI-TARS features checked first (highest priority)
        parsers = [
            (self._parse_system2, 0.95),
            (self._parse_context, 0.95),
            (self._parse_retry, 0.95),
            (self._parse_normalize, 0.95),
            (self._parse_back_forward, 0.95),
            (self._parse_refresh, 0.95),
            (self._parse_close, 0.95),
            (self._parse_navigate, 0.95),
            (self._parse_search, 0.9),
            (self._parse_type, 0.9),
            (self._parse_key, 0.95),  # Check key presses before clicks
            (self._parse_click, 0.85),
            (self._parse_scroll, 0.95),
            (self._parse_wait, 0.95),
            (self._parse_screenshot, 0.95),
            (self._parse_hover, 0.85),
        ]

        for parser, base_confidence in parsers:
            result = parser(command)
            if result:
                result.confidence = base_confidence
                result.raw_text = command
                return result

        # Check if it looks like a URL even without navigation verb
        if self._looks_like_url(command):
            url = self._normalize_url(command)
            return ParsedAction(
                ActionType.NAVIGATE,
                target=url,
                confidence=0.9,
                raw_text=command
            )

        return ParsedAction(ActionType.UNKNOWN, raw_text=command, confidence=0.0)

    def parse_sequence(self, text: str) -> List[ParsedAction]:
        """
        Parse a multi-command sequence into a list of actions.
        Splits on 'then', 'and then', 'after that', 'next', etc.

        Args:
            text: Multi-command string

        Returns:
            List of ParsedAction objects
        """
        # Split on sequence connectors
        connectors = r'\b(?:then|and\s+then|after\s+that|next|afterwards?|followed\s+by|finally|lastly)\b'
        parts = re.split(connectors, text, flags=re.IGNORECASE)

        actions = []
        for part in parts:
            part = part.strip()
            if part:
                action = self.parse(part)
                if action.action_type != ActionType.UNKNOWN:
                    actions.append(action)

        return actions

    def _parse_navigate(self, command: str) -> Optional[ParsedAction]:
        """Parse navigation commands."""
        for pattern in self._navigate_re:
            match = pattern.search(command)
            if match:
                target = match.group(1).strip()
                url = self._resolve_url(target)
                return ParsedAction(ActionType.NAVIGATE, target=url)
        return None

    def _parse_click(self, command: str) -> Optional[ParsedAction]:
        """Parse click commands."""
        for pattern in self._click_re:
            match = pattern.search(command)
            if match:
                target = match.group(1).strip()
                return ParsedAction(ActionType.CLICK, target=target)
        return None

    def _parse_type(self, command: str) -> Optional[ParsedAction]:
        """Parse type/input commands."""
        for pattern in self._type_re:
            match = pattern.search(command)
            if match:
                groups = match.groups()
                if len(groups) >= 2:
                    # Handle different group orders
                    if 'fill' in command.lower():
                        target, value = groups[0], groups[1]
                    else:
                        value, target = groups[0], groups[1]
                    return ParsedAction(ActionType.TYPE, target=target.strip(), value=value.strip())
        return None

    def _parse_search(self, command: str) -> Optional[ParsedAction]:
        """Parse search commands."""
        for pattern in self._search_re:
            match = pattern.search(command)
            if match:
                groups = match.groups()
                query = groups[0].strip() if groups[0] else ""
                target = groups[1].strip() if len(groups) > 1 and groups[1] else "search box"
                return ParsedAction(ActionType.SEARCH, target=target, value=query)
        return None

    def _parse_scroll(self, command: str) -> Optional[ParsedAction]:
        """Parse scroll commands."""
        for pattern in self._scroll_re:
            match = pattern.search(command)
            if match:
                direction = match.group(1).lower()
                if direction in ('top', 'up'):
                    direction = 'up'
                elif direction in ('bottom', 'down'):
                    direction = 'down'
                return ParsedAction(ActionType.SCROLL, params={"direction": direction})
        return None

    def _parse_wait(self, command: str) -> Optional[ParsedAction]:
        """Parse wait commands."""
        for pattern in self._wait_re:
            match = pattern.search(command)
            if match:
                groups = match.groups()
                seconds = int(groups[0]) if groups and groups[0] else 2
                return ParsedAction(ActionType.WAIT, params={"seconds": seconds})
        return None

    def _parse_screenshot(self, command: str) -> Optional[ParsedAction]:
        """Parse screenshot commands."""
        for pattern in self._screenshot_re:
            match = pattern.search(command)
            if match:
                return ParsedAction(ActionType.SCREENSHOT)
        return None

    def _parse_key(self, command: str) -> Optional[ParsedAction]:
        """Parse key press commands."""
        for pattern in self._key_re:
            match = pattern.search(command)
            if match:
                key = match.group(1).strip().lower()
                # Normalize key names
                key_map = {
                    'arrow up': 'ArrowUp',
                    'arrow down': 'ArrowDown',
                    'arrow left': 'ArrowLeft',
                    'arrow right': 'ArrowRight',
                    'arrowup': 'ArrowUp',
                    'arrowdown': 'ArrowDown',
                    'arrowleft': 'ArrowLeft',
                    'arrowright': 'ArrowRight',
                    'enter': 'Enter',
                    'escape': 'Escape',
                    'tab': 'Tab',
                    'backspace': 'Backspace',
                    'delete': 'Delete',
                    'space': 'Space',
                }
                key = key_map.get(key, key.title())
                return ParsedAction(ActionType.PRESS_KEY, value=key)
        return None

    def _parse_hover(self, command: str) -> Optional[ParsedAction]:
        """Parse hover commands."""
        for pattern in self._hover_re:
            match = pattern.search(command)
            if match:
                target = match.group(1).strip()
                return ParsedAction(ActionType.HOVER, target=target)
        return None

    def _parse_back_forward(self, command: str) -> Optional[ParsedAction]:
        """Parse back/forward navigation commands."""
        for pattern in self._back_forward_re:
            match = pattern.search(command)
            if match:
                command_lower = command.lower()
                if 'forward' in command_lower or 'next' in command_lower:
                    return ParsedAction(ActionType.FORWARD)
                else:
                    return ParsedAction(ActionType.BACK)
        return None

    def _parse_refresh(self, command: str) -> Optional[ParsedAction]:
        """Parse refresh commands."""
        for pattern in self._refresh_re:
            match = pattern.search(command)
            if match:
                return ParsedAction(ActionType.REFRESH)
        return None

    def _parse_close(self, command: str) -> Optional[ParsedAction]:
        """Parse close commands."""
        for pattern in self._close_re:
            match = pattern.search(command)
            if match:
                return ParsedAction(ActionType.CLOSE)
        return None

    def _parse_system2(self, command: str) -> Optional[ParsedAction]:
        """Parse System-2 reasoning enable commands."""
        for pattern in self._system2_re:
            match = pattern.search(command)
            if match:
                return ParsedAction(
                    ActionType.ENABLE_SYSTEM2,
                    params={"enabled": True, "require_thought": True, "require_reflection": True}
                )
        return None

    def _parse_context(self, command: str) -> Optional[ParsedAction]:
        """Parse ConversationContext enable commands."""
        for pattern in self._context_re:
            match = pattern.search(command)
            if match:
                return ParsedAction(
                    ActionType.ENABLE_CONTEXT,
                    params={"enabled": True, "max_screenshots": 5}
                )
        return None

    def _parse_retry(self, command: str) -> Optional[ParsedAction]:
        """Parse tiered retry config enable commands."""
        for pattern in self._retry_re:
            match = pattern.search(command)
            if match:
                return ParsedAction(
                    ActionType.ENABLE_RETRY,
                    params={
                        "enabled": True,
                        "screenshot_timeout": 5.0,
                        "model_timeout": 30.0,
                        "action_timeout": 5.0
                    }
                )
        return None

    def _parse_normalize(self, command: str) -> Optional[ParsedAction]:
        """Parse coordinate normalization enable commands."""
        for pattern in self._normalize_re:
            match = pattern.search(command)
            if match:
                return ParsedAction(
                    ActionType.ENABLE_NORMALIZE,
                    params={"enabled": True, "range": 1000}
                )
        return None

    def _resolve_url(self, target: str) -> str:
        """Resolve a target string to a full URL."""
        target_lower = target.lower().strip()

        # Check service mappings first (exact match)
        if target_lower in self.SERVICE_URLS:
            return self.SERVICE_URLS[target_lower]

        # Check partial matches - only for services with 3+ characters
        # This prevents "x" from matching "example.com"
        for service, url in self.SERVICE_URLS.items():
            # Skip short service names for partial matching
            if len(service) < 3:
                continue
            # Only match if service is a word boundary match in target
            if service in target_lower and not target_lower.endswith('.com') and not target_lower.endswith('.org'):
                return url

        # Normalize URL (handles actual URLs like example.com)
        return self._normalize_url(target)

    def _normalize_url(self, url: str) -> str:
        """Normalize a URL by adding protocol if missing."""
        url = url.strip()
        if url.startswith(('http://', 'https://')):
            return url
        if url.startswith('www.'):
            return f'https://{url}'
        if '.' in url and ' ' not in url:
            return f'https://{url}'
        return url

    def _looks_like_url(self, text: str) -> bool:
        """Check if text looks like a URL."""
        text = text.strip().lower()
        return (
            text.startswith(('http://', 'https://', 'www.')) or
            any(text.endswith(tld) for tld in ['.com', '.org', '.net', '.io', '.co', '.edu', '.gov']) or
            any(tld in text for tld in ['.com/', '.org/', '.net/', '.io/'])
        )

    def can_execute_directly(self, command: str) -> bool:
        """
        Check if a command can be executed directly without LLM.

        Args:
            command: Natural language command

        Returns:
            True if the command can be executed deterministically
        """
        action = self.parse(command)
        return action.action_type != ActionType.UNKNOWN and action.confidence >= 0.8

    def get_mcp_calls(self, command: str) -> List[Tuple[str, Dict[str, Any]]]:
        """
        Convert a command (possibly multi-step) to MCP tool calls.

        Args:
            command: Natural language command (single or multi-step)

        Returns:
            List of (tool_name, params) tuples for MCP execution
        """
        actions = self.parse_sequence(command)
        calls = []

        for action in actions:
            mcp_call = action.to_mcp_call()
            if mcp_call:
                calls.append(mcp_call)

        return calls


# Singleton instance for easy access
_parser_instance = None

def get_parser() -> CommandParser:
    """Get the singleton CommandParser instance."""
    global _parser_instance
    if _parser_instance is None:
        _parser_instance = CommandParser()
    return _parser_instance


def parse_command(command: str) -> ParsedAction:
    """Convenience function to parse a single command."""
    return get_parser().parse(command)


def parse_commands(text: str) -> List[ParsedAction]:
    """Convenience function to parse a multi-command sequence."""
    return get_parser().parse_sequence(text)


def can_execute_directly(command: str) -> bool:
    """Check if command can be executed without LLM."""
    return get_parser().can_execute_directly(command)


def get_mcp_calls(command: str) -> List[Tuple[str, Dict[str, Any]]]:
    """Get MCP tool calls for a command."""
    return get_parser().get_mcp_calls(command)
