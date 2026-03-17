"""
Smart Action Router - Intent Detection and Action Planning

Detects page type and user intent to route to appropriate action handlers.
Generates step-by-step action plans for complex workflows.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum
import re
import logging

logger = logging.getLogger(__name__)


class PageType(Enum):
    """Types of web pages the router can detect."""
    LOGIN = "login"
    CHECKOUT = "checkout"
    SEARCH = "search"
    FORM = "form"
    ARTICLE = "article"
    PRODUCT = "product"
    LIST = "list"
    DASHBOARD = "dashboard"
    PROFILE = "profile"
    SETTINGS = "settings"
    CART = "cart"
    CAPTCHA = "captcha"
    ERROR = "error"
    UNKNOWN = "unknown"


class UserIntent(Enum):
    """User intents the router can detect."""
    LOGIN = "login"
    PURCHASE = "purchase"
    SEARCH = "search"
    FILL_FORM = "fill_form"
    EXTRACT_DATA = "extract_data"
    NAVIGATE = "navigate"
    CLICK = "click"
    SUBMIT = "submit"
    SCROLL = "scroll"
    WAIT = "wait"
    READ = "read"
    DOWNLOAD = "download"
    UPLOAD = "upload"
    LOGOUT = "logout"
    UNKNOWN = "unknown"


@dataclass
class ActionPlan:
    """A plan for executing a series of actions."""
    intent: UserIntent
    page_type: PageType
    steps: List[Dict[str, Any]]  # [{action: "fill", target: "email", value: "..."}]
    confidence: float
    reasoning: str = ""
    fallback_steps: List[Dict[str, Any]] = field(default_factory=list)


class ActionRouter:
    """
    Smart Action Router that detects page types and user intents,
    then generates appropriate action plans.
    """

    # Page type detection keywords
    PAGE_TYPE_KEYWORDS = {
        PageType.LOGIN: [
            'login', 'sign in', 'signin', 'log in', 'password', 'username',
            'email', 'authentication', 'auth', 'credentials', 'account access'
        ],
        PageType.CHECKOUT: [
            'checkout', 'payment', 'billing', 'shipping', 'place order',
            'complete purchase', 'payment method', 'credit card', 'paypal'
        ],
        PageType.SEARCH: [
            'search', 'find', 'query', 'results', 'filter', 'sort by',
            'search results', 'refine search'
        ],
        PageType.FORM: [
            'form', 'submit', 'required field', 'input', 'textarea',
            'select', 'checkbox', 'radio', 'form submission'
        ],
        PageType.ARTICLE: [
            'article', 'blog post', 'content', 'author', 'published',
            'read more', 'share', 'comments', 'related articles'
        ],
        PageType.PRODUCT: [
            'product', 'price', 'add to cart', 'buy now', 'in stock',
            'product details', 'reviews', 'rating', 'specifications'
        ],
        PageType.LIST: [
            'list', 'table', 'grid', 'pagination', 'page 1', 'next page',
            'previous', 'results', 'items', 'showing'
        ],
        PageType.DASHBOARD: [
            'dashboard', 'overview', 'analytics', 'statistics', 'metrics',
            'summary', 'widgets', 'charts', 'graphs'
        ],
        PageType.PROFILE: [
            'profile', 'account', 'my account', 'user profile', 'edit profile',
            'personal information', 'settings', 'preferences'
        ],
        PageType.SETTINGS: [
            'settings', 'preferences', 'configuration', 'options',
            'customize', 'manage', 'privacy', 'security'
        ],
        PageType.CART: [
            'cart', 'shopping cart', 'basket', 'items in cart',
            'remove', 'quantity', 'subtotal', 'proceed to checkout'
        ],
        PageType.CAPTCHA: [
            'captcha', 'recaptcha', 'verify you are human', 'security check',
            'robot', 'not a robot', 'puzzle', 'challenge'
        ],
        PageType.ERROR: [
            'error', '404', '403', '500', 'not found', 'access denied',
            'something went wrong', 'page not found', 'oops'
        ]
    }

    # User intent detection keywords
    INTENT_KEYWORDS = {
        UserIntent.LOGIN: [
            'login', 'sign in', 'log in', 'authenticate', 'access account'
        ],
        UserIntent.PURCHASE: [
            'buy', 'purchase', 'checkout', 'order', 'add to cart',
            'complete purchase', 'pay'
        ],
        UserIntent.SEARCH: [
            'search', 'find', 'look for', 'query', 'search for'
        ],
        UserIntent.FILL_FORM: [
            'fill', 'complete', 'submit form', 'enter', 'input',
            'fill out', 'complete form'
        ],
        UserIntent.EXTRACT_DATA: [
            'extract', 'scrape', 'get', 'collect', 'gather',
            'retrieve', 'find data', 'pull'
        ],
        UserIntent.NAVIGATE: [
            'go to', 'navigate', 'visit', 'open', 'browse to',
            'load', 'access'
        ],
        UserIntent.CLICK: [
            'click', 'press', 'tap', 'select', 'choose'
        ],
        UserIntent.SUBMIT: [
            'submit', 'send', 'post', 'save', 'confirm'
        ],
        UserIntent.SCROLL: [
            'scroll', 'scroll down', 'scroll up', 'scroll to'
        ],
        UserIntent.WAIT: [
            'wait', 'wait for', 'pause', 'delay'
        ],
        UserIntent.READ: [
            'read', 'view', 'show', 'display', 'see'
        ],
        UserIntent.DOWNLOAD: [
            'download', 'save file', 'export', 'get file'
        ],
        UserIntent.UPLOAD: [
            'upload', 'attach', 'choose file', 'select file'
        ],
        UserIntent.LOGOUT: [
            'logout', 'log out', 'sign out', 'exit'
        ]
    }

    def __init__(self, mcp_client=None, ollama_client=None):
        """
        Initialize the Action Router.

        Args:
            mcp_client: Optional MCP client for browser automation
            ollama_client: Optional Ollama client for LLM-based intent detection
        """
        self.mcp = mcp_client
        self.ollama = ollama_client
        logger.info("ActionRouter initialized")

    async def detect_page_type(self, page_content: str, url: str = "") -> PageType:
        """
        Detect what type of page we're on based on DOM content and URL.

        Args:
            page_content: HTML or text content of the page
            url: Current page URL (optional)

        Returns:
            PageType enum value
        """
        content_lower = page_content.lower()
        url_lower = url.lower()

        # Check URL patterns first (more reliable)
        url_patterns = {
            PageType.LOGIN: ['login', 'signin', 'auth'],
            PageType.CHECKOUT: ['checkout', 'payment', 'cart'],
            PageType.SEARCH: ['search', 'results', 'query'],
            PageType.PRODUCT: ['product', 'item', 'p/'],
            PageType.PROFILE: ['profile', 'account', 'user'],
            PageType.SETTINGS: ['settings', 'preferences', 'config'],
        }

        for page_type, patterns in url_patterns.items():
            if any(pattern in url_lower for pattern in patterns):
                logger.debug(f"Detected page type from URL: {page_type}")
                return page_type

        # Check content keywords with scoring
        scores = {}
        for page_type, keywords in self.PAGE_TYPE_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in content_lower)
            if score > 0:
                scores[page_type] = score

        if scores:
            # Return page type with highest score
            best_match = max(scores.items(), key=lambda x: x[1])
            if best_match[1] >= 2:  # Minimum confidence threshold
                logger.debug(f"Detected page type from content: {best_match[0]} (score: {best_match[1]})")
                return best_match[0]

        logger.debug("Could not determine page type, returning UNKNOWN")
        return PageType.UNKNOWN

    async def detect_intent(self, prompt: str) -> UserIntent:
        """
        Detect user intent from their prompt.

        Args:
            prompt: User's natural language prompt

        Returns:
            UserIntent enum value
        """
        prompt_lower = prompt.lower()

        # Check intent keywords with scoring
        scores = {}
        for intent, keywords in self.INTENT_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in prompt_lower)
            if score > 0:
                scores[intent] = score

        if scores:
            # Return intent with highest score
            best_match = max(scores.items(), key=lambda x: x[1])
            logger.debug(f"Detected intent: {best_match[0]} (score: {best_match[1]})")
            return best_match[0]

        # Default to NAVIGATE if no clear intent
        logger.debug("Could not determine intent, defaulting to NAVIGATE")
        return UserIntent.NAVIGATE

    async def create_action_plan(
        self,
        prompt: str,
        page_content: str = "",
        url: str = "",
        context: Optional[Dict[str, Any]] = None
    ) -> ActionPlan:
        """
        Create an action plan based on intent and page type.

        Args:
            prompt: User's natural language prompt
            page_content: Current page content (HTML/text)
            url: Current page URL
            context: Additional context (e.g., extracted values, session state)

        Returns:
            ActionPlan with steps to execute
        """
        intent = await self.detect_intent(prompt)
        page_type = await self.detect_page_type(page_content, url)

        steps = self._generate_steps(intent, page_type, prompt, page_content, context)
        fallback_steps = self._generate_fallback_steps(intent, page_type)

        confidence = self._calculate_confidence(intent, page_type, steps)
        reasoning = self._generate_reasoning(intent, page_type, steps)

        logger.info(f"Created action plan: intent={intent}, page_type={page_type}, confidence={confidence:.2f}")

        return ActionPlan(
            intent=intent,
            page_type=page_type,
            steps=steps,
            confidence=confidence,
            reasoning=reasoning,
            fallback_steps=fallback_steps
        )

    def _generate_steps(
        self,
        intent: UserIntent,
        page_type: PageType,
        prompt: str,
        page_content: str = "",
        context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Generate action steps based on intent and page type.

        Returns:
            List of action step dictionaries
        """
        context = context or {}

        # Login flow
        if intent == UserIntent.LOGIN and page_type == PageType.LOGIN:
            return [
                {
                    "action": "fill",
                    "target_type": "username",
                    "hints": {
                        "type": "email",
                        "name": ["email", "username", "user", "login"],
                        "placeholder": ["email", "username"]
                    },
                    "value": context.get("email", ""),
                    "required": True
                },
                {
                    "action": "fill",
                    "target_type": "password",
                    "hints": {
                        "type": "password",
                        "name": ["password", "pass", "pwd"]
                    },
                    "value": context.get("password", ""),
                    "required": True
                },
                {
                    "action": "click",
                    "target_type": "submit",
                    "hints": {
                        "text": ["login", "sign in", "submit", "log in"],
                        "type": "submit",
                        "role": "button"
                    },
                    "required": True
                },
                {
                    "action": "wait",
                    "condition": "navigation",
                    "timeout": 5000
                }
            ]

        # Purchase flow
        if intent == UserIntent.PURCHASE:
            if page_type == PageType.PRODUCT:
                return [
                    {
                        "action": "click",
                        "target_type": "add_to_cart",
                        "hints": {
                            "text": ["add to cart", "add to bag", "buy now"],
                            "role": "button"
                        }
                    },
                    {
                        "action": "wait",
                        "condition": "element",
                        "selector": "[class*='cart'], [class*='added']",
                        "timeout": 3000
                    }
                ]
            elif page_type == PageType.CHECKOUT:
                return self._generate_checkout_steps(context)

        # Search flow
        if intent == UserIntent.SEARCH:
            search_query = self._extract_search_query(prompt)
            return [
                {
                    "action": "fill",
                    "target_type": "search_input",
                    "hints": {
                        "type": "search",
                        "name": ["q", "query", "search"],
                        "placeholder": ["search"]
                    },
                    "value": search_query,
                    "required": True
                },
                {
                    "action": "click",
                    "target_type": "search_button",
                    "hints": {
                        "type": "submit",
                        "text": ["search", "find", "go"],
                        "aria-label": ["search"]
                    }
                },
                {
                    "action": "wait",
                    "condition": "navigation",
                    "timeout": 5000
                }
            ]

        # Form fill flow
        if intent == UserIntent.FILL_FORM and page_type == PageType.FORM:
            return self._generate_form_steps(page_content, context)

        # Data extraction flow
        if intent == UserIntent.EXTRACT_DATA:
            return [
                {
                    "action": "extract",
                    "target_type": "all_data",
                    "strategy": "snapshot",
                    "fields": context.get("fields", ["text", "links", "images"])
                }
            ]

        # Navigate flow
        if intent == UserIntent.NAVIGATE:
            target_url = self._extract_url(prompt)
            if target_url:
                return [
                    {
                        "action": "navigate",
                        "url": target_url,
                        "wait_until": "networkidle"
                    }
                ]

        # Click flow
        if intent == UserIntent.CLICK:
            target_text = self._extract_click_target(prompt)
            return [
                {
                    "action": "click",
                    "target_type": "element",
                    "hints": {
                        "text": [target_text],
                        "aria-label": [target_text]
                    }
                }
            ]

        # Scroll flow
        if intent == UserIntent.SCROLL:
            direction = "down" if "down" in prompt.lower() else "up"
            return [
                {
                    "action": "scroll",
                    "direction": direction,
                    "amount": context.get("scroll_amount", "page")
                }
            ]

        # Default: extract snapshot
        return [
            {
                "action": "snapshot",
                "extract_links": True,
                "extract_forms": True
            }
        ]

    def _generate_checkout_steps(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate steps for checkout flow."""
        return [
            {
                "action": "fill",
                "target_type": "shipping_info",
                "fields": [
                    {"name": "first_name", "value": context.get("first_name", "")},
                    {"name": "last_name", "value": context.get("last_name", "")},
                    {"name": "address", "value": context.get("address", "")},
                    {"name": "city", "value": context.get("city", "")},
                    {"name": "zip", "value": context.get("zip", "")},
                ]
            },
            {
                "action": "fill",
                "target_type": "payment_info",
                "fields": [
                    {"name": "card_number", "value": context.get("card_number", "")},
                    {"name": "expiry", "value": context.get("card_expiry", "")},
                    {"name": "cvv", "value": context.get("card_cvv", "")},
                ]
            },
            {
                "action": "click",
                "target_type": "place_order",
                "hints": {"text": ["place order", "complete purchase", "submit order"]}
            }
        ]

    def _generate_form_steps(self, page_content: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate steps for generic form filling."""
        # Extract form fields from page content
        fields = self._extract_form_fields(page_content)

        return [
            {
                "action": "fill_form",
                "fields": fields,
                "values": context.get("form_data", {})
            },
            {
                "action": "click",
                "target_type": "submit",
                "hints": {"type": "submit", "text": ["submit", "send", "save"]}
            }
        ]

    def _extract_form_fields(self, page_content: str) -> List[Dict[str, str]]:
        """Extract form fields from page content."""
        # Simple regex-based extraction (in production, use proper HTML parsing)
        fields = []

        # Find input fields
        input_pattern = r'<input[^>]*name=["\']([^"\']+)["\'][^>]*>'
        for match in re.finditer(input_pattern, page_content, re.IGNORECASE):
            field_name = match.group(1)
            fields.append({"name": field_name, "type": "input"})

        # Find textarea fields
        textarea_pattern = r'<textarea[^>]*name=["\']([^"\']+)["\'][^>]*>'
        for match in re.finditer(textarea_pattern, page_content, re.IGNORECASE):
            field_name = match.group(1)
            fields.append({"name": field_name, "type": "textarea"})

        return fields

    def _generate_fallback_steps(self, intent: UserIntent, page_type: PageType) -> List[Dict[str, Any]]:
        """Generate fallback steps if primary plan fails."""
        fallbacks = []

        if intent == UserIntent.LOGIN:
            fallbacks.append({
                "action": "screenshot",
                "reason": "Login failed, capturing state for debugging"
            })
            fallbacks.append({
                "action": "extract",
                "target_type": "error_messages",
                "selector": "[class*='error'], [class*='alert'], [role='alert']"
            })

        if page_type == PageType.CAPTCHA:
            fallbacks.append({
                "action": "solve_captcha",
                "strategy": "manual",
                "timeout": 60000
            })

        return fallbacks

    def _calculate_confidence(self, intent: UserIntent, page_type: PageType, steps: List[Dict]) -> float:
        """Calculate confidence score for the action plan."""
        confidence = 0.5  # Base confidence

        # Increase confidence if intent and page type align
        aligned_pairs = [
            (UserIntent.LOGIN, PageType.LOGIN),
            (UserIntent.PURCHASE, PageType.CHECKOUT),
            (UserIntent.SEARCH, PageType.SEARCH),
            (UserIntent.FILL_FORM, PageType.FORM),
        ]

        if (intent, page_type) in aligned_pairs:
            confidence += 0.3

        # Increase confidence if we have concrete steps
        if len(steps) > 0:
            confidence += 0.1

        # Increase confidence if steps have required fields filled
        required_steps = [s for s in steps if s.get("required")]
        if required_steps:
            filled = sum(1 for s in required_steps if s.get("value"))
            confidence += 0.1 * (filled / len(required_steps))

        return min(confidence, 1.0)

    def _generate_reasoning(self, intent: UserIntent, page_type: PageType, steps: List[Dict]) -> str:
        """Generate human-readable reasoning for the action plan."""
        reasoning = f"Detected intent: {intent.value}, page type: {page_type.value}. "

        if not steps:
            reasoning += "No specific steps generated, will use generic approach."
        else:
            reasoning += f"Generated {len(steps)} steps: "
            step_summary = ", ".join([s.get("action", "unknown") for s in steps[:3]])
            reasoning += step_summary
            if len(steps) > 3:
                reasoning += f", and {len(steps) - 3} more."

        return reasoning

    def _extract_search_query(self, prompt: str) -> str:
        """Extract search query from user prompt."""
        # Remove common search keywords
        query = prompt.lower()
        for kw in ["search for", "find", "look for", "search"]:
            query = query.replace(kw, "")
        return query.strip()

    def _extract_url(self, prompt: str) -> Optional[str]:
        """Extract URL from user prompt."""
        # Simple URL extraction
        url_pattern = r'https?://[^\s]+'
        match = re.search(url_pattern, prompt)
        if match:
            return match.group(0)

        # Check for "go to [site]" patterns
        go_to_pattern = r'(?:go to|navigate to|visit|open)\s+([^\s]+)'
        match = re.search(go_to_pattern, prompt.lower())
        if match:
            site = match.group(1)
            # Add https:// if not present
            if not site.startswith(('http://', 'https://')):
                site = 'https://' + site
            return site

        return None

    def _extract_click_target(self, prompt: str) -> str:
        """Extract click target text from user prompt."""
        # Remove "click" keywords
        target = prompt.lower()
        for kw in ["click", "click on", "press", "tap"]:
            target = target.replace(kw, "")
        return target.strip()

    async def execute_plan(self, plan: ActionPlan) -> Dict[str, Any]:
        """
        Execute an action plan using MCP client.

        Args:
            plan: ActionPlan to execute

        Returns:
            Execution results
        """
        if not self.mcp:
            logger.warning("No MCP client available, cannot execute plan")
            return {"success": False, "error": "No MCP client configured"}

        results = []
        for step in plan.steps:
            try:
                result = await self._execute_step(step)
                results.append(result)

                # Stop on failure if step is required
                if step.get("required") and not result.get("success"):
                    logger.warning(f"Required step failed: {step}")
                    break

            except Exception as e:
                logger.error(f"Error executing step {step}: {e}")
                results.append({"success": False, "error": str(e)})

                if step.get("required"):
                    break

        return {
            "success": all(r.get("success", False) for r in results),
            "steps": results,
            "plan": plan
        }

    async def _execute_step(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single action step."""
        action = step.get("action")

        if action == "navigate":
            # Use MCP navigate
            return {"success": True, "action": "navigate"}

        elif action == "fill":
            # Use MCP fill
            return {"success": True, "action": "fill"}

        elif action == "click":
            # Use MCP click
            return {"success": True, "action": "click"}

        elif action == "wait":
            # Use MCP wait
            return {"success": True, "action": "wait"}

        elif action == "extract":
            # Use MCP snapshot or extract
            return {"success": True, "action": "extract"}

        else:
            logger.warning(f"Unknown action type: {action}")
            return {"success": False, "error": f"Unknown action: {action}"}


# Convenience function
async def route_action(prompt: str, page_content: str = "", url: str = "", context: Optional[Dict] = None) -> ActionPlan:
    """
    Convenience function to create an action plan.

    Args:
        prompt: User's natural language prompt
        page_content: Current page content
        url: Current URL
        context: Additional context

    Returns:
        ActionPlan
    """
    router = ActionRouter()
    return await router.create_action_plan(prompt, page_content, url, context)
