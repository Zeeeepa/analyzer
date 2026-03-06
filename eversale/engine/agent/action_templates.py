"""
Action Templates - Pre-defined sequences for common browser operations.
Matches Playwright MCP's precision by providing deterministic action flows.
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Callable
from enum import Enum
import re
from urllib.parse import urlparse


class TemplateCategory(Enum):
    """Categories of action templates."""
    NAVIGATION = "navigation"
    AUTHENTICATION = "authentication"
    SEARCH = "search"
    FORM = "form"
    EXTRACTION = "extraction"
    SOCIAL = "social"
    EMAIL = "email"
    CONFIGURATION = "configuration"  # UI-TARS feature toggles


@dataclass
class ActionStep:
    """A single step in an action template."""
    tool: str  # MCP tool name
    params: Dict[str, Any]  # Tool parameters
    description: str  # Human-readable description
    wait_after: float = 0.5  # Seconds to wait after action
    optional: bool = False  # If True, continue even if this step fails
    condition: Optional[str] = None  # Condition to check before executing


@dataclass
class ActionTemplate:
    """A template for a common browser operation."""
    name: str
    description: str
    category: TemplateCategory
    triggers: List[str]  # Patterns that trigger this template
    steps: List[ActionStep]
    variables: Dict[str, str] = None  # Variables to extract from prompt

    def matches(self, prompt: str) -> bool:
        """Check if prompt matches this template.

        Uses more precise matching:
        - Trigger must appear at word boundaries
        - For navigation templates, the service name should be the primary target
        """
        # Handle JSON-wrapped goals like: {"type":"task","prompt":"Go to FB Ads..."}
        actual_prompt = prompt
        try:
            import json
            parsed = json.loads(prompt)
            if isinstance(parsed, dict) and 'prompt' in parsed:
                actual_prompt = parsed['prompt']
        except (json.JSONDecodeError, TypeError):
            pass

        prompt_lower = actual_prompt.lower().strip()

        for trigger in self.triggers:
            trigger_lower = trigger.lower()

            # For exact phrase matches (like "go to gmail"), check as-is
            if trigger_lower in prompt_lower:
                # Make sure it's at a word boundary
                pattern = rf'\b{re.escape(trigger_lower)}\b'
                if re.search(pattern, prompt_lower):
                    # Additional check: for service templates, ensure it's the main target
                    # not just mentioned incidentally
                    if self.category in [TemplateCategory.EMAIL, TemplateCategory.NAVIGATION]:
                        # The trigger should be near the start or after "go to", "open", etc.
                        if re.search(rf'^(?:open|go to|check|visit|navigate to)?\s*{re.escape(trigger_lower)}', prompt_lower):
                            return True
                        # Or it should be the only service mentioned
                        if prompt_lower.count(trigger_lower) == 1 and len(prompt_lower) < 50:
                            return True
                    else:
                        return True

        return False

    def extract_variables(self, prompt: str) -> Dict[str, str]:
        """Extract variables from prompt based on template patterns.

        Supports patterns with multiple capture groups (alternation) -
        uses the first non-None group found.
        Also supports _default values when no match is found.
        """
        extracted = {}
        if not self.variables:
            return extracted

        # Handle JSON-wrapped goals like: {"type":"task","prompt":"Go to FB Ads..."}
        # Extract the actual prompt string before processing
        normalized_prompt = prompt
        try:
            import json
            parsed = json.loads(prompt)
            if isinstance(parsed, dict) and 'prompt' in parsed:
                normalized_prompt = parsed['prompt']
        except (json.JSONDecodeError, TypeError):
            pass

        # Normalize prompt: convert escaped quotes to regular quotes
        # This handles JSON-formatted goals like: \"booked meetings\" -> "booked meetings"
        normalized_prompt = normalized_prompt.replace('\\"', '"').replace("\\'", "'")

        # Get default value if specified
        default_value = self.variables.get("_default")

        for var_name, pattern in self.variables.items():
            # Skip special keys
            if var_name.startswith("_"):
                continue

            match = re.search(pattern, normalized_prompt, re.I)
            if match:
                # Handle patterns with alternation - find first non-None group
                value = None
                for group in match.groups():
                    if group is not None:
                        value = group.strip()
                        break
                if value:
                    # Strip any remaining surrounding quotes
                    if (value.startswith('"') and value.endswith('"')) or \
                       (value.startswith("'") and value.endswith("'")):
                        value = value[1:-1]
                    extracted[var_name] = value
            elif default_value and var_name not in extracted:
                # Use default value if no match found
                extracted[var_name] = default_value

        return extracted


# Common action templates
TEMPLATES = [
    # Gmail operations
    ActionTemplate(
        name="open_gmail",
        description="Open Gmail inbox",
        category=TemplateCategory.EMAIL,
        triggers=["open gmail", "go to gmail", "check gmail", "gmail inbox"],
        steps=[
            ActionStep("playwright_navigate", {"url": "https://mail.google.com"}, "Opening Gmail..."),
            ActionStep("playwright_snapshot", {}, "Loading inbox..."),
        ]
    ),

    ActionTemplate(
        name="compose_gmail",
        description="Compose new email in Gmail",
        category=TemplateCategory.EMAIL,
        triggers=["compose email", "new email", "write email", "send email"],
        steps=[
            ActionStep("playwright_navigate", {"url": "https://mail.google.com"}, "Opening Gmail..."),
            ActionStep("playwright_click", {"element": "Compose button"}, "Opening compose..."),
            ActionStep("playwright_snapshot", {}, "Ready to write..."),
        ],
        variables={"recipient": r'to\s+([^\s,]+)', "subject": r'subject[:\s]+["\']?([^"\']+)["\']?'}
    ),

    # Google Maps operations
    ActionTemplate(
        name="search_google_maps",
        description="Search for businesses on Google Maps and extract agency/business listings",
        category=TemplateCategory.SEARCH,
        triggers=["google maps", "find on maps", "search maps", "maps search", "find businesses"],
        steps=[
            ActionStep("playwright_navigate", {"url": "https://www.google.com/maps/search/{query}"}, "Searching businesses...", wait_after=1.5),
            ActionStep("playwright_wait", {"time": 2}, "Loading map results..."),
            ActionStep("playwright_scroll", {"direction": "down", "amount": 600}, "Finding more listings...", wait_after=0.8),
            ActionStep("playwright_extract_list", {"limit": 10}, "Collecting business info..."),
        ],
        variables={"query": r'for\s+([a-zA-Z0-9\s]+?)(?:\s*\.|$|,)', "_default": "lead generation agency"}
    ),

    # Facebook Ads Library
    ActionTemplate(
        name="search_fb_ads",
        description="Search Facebook Ads Library and extract advertiser data",
        category=TemplateCategory.SEARCH,
        triggers=["facebook ads library", "fb ads library", "meta ads library", "facebook ads search", "fb ads"],
        steps=[
            ActionStep("playwright_navigate", {"url": "https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=US&media_type=all&q={query}&search_type=keyword_unordered"}, "Searching ads...", wait_after=3.0),
            ActionStep("playwright_wait", {"time": 3}, "Loading results...", wait_after=1.0),
            ActionStep("playwright_scroll", {"direction": "down", "amount": 3000}, "Finding more prospects...", wait_after=0.8),
            ActionStep("playwright_scroll", {"direction": "down", "amount": 3000}, "Loading more...", wait_after=0.8),
            ActionStep("playwright_scroll", {"direction": "down", "amount": 3000}, "Almost there...", wait_after=0.8),
            ActionStep("playwright_extract_fb_ads", {"max_ads": 100}, "Collecting prospects...", wait_after=0.5),
        ],
        # Extract query from various formats:
        # 1. search "quoted term" - prioritize quoted terms after search
        # 2. for "quoted term" - quoted term after "for"
        # 3. for unquoted term - unquoted term after "for" ending at .,;
        # 4. keywords: term - term after keywords/with
        # 5. Fallback: any quoted term in the prompt
        variables={"query": r'(?:search\s+["\']([^"\']+)["\']|for\s+["\']([^"\']+)["\']|for\s+(\S+(?:\s+\S+)*?)(?:\s*[.,;]|$)|(?:with|keywords?)[:\s]+["\']?([^"\';,]+)["\']?|["\']([^"\']{3,})["\'])'}
    ),

    # LinkedIn operations
    ActionTemplate(
        name="search_linkedin",
        description="Search on LinkedIn for people/companies and extract prospects",
        category=TemplateCategory.SOCIAL,
        triggers=["linkedin search", "search linkedin", "find on linkedin", "go to linkedin"],
        steps=[
            ActionStep("playwright_navigate", {"url": "https://www.linkedin.com/search/results/all/?keywords={query}"}, "Searching LinkedIn...", wait_after=1.5),
            ActionStep("playwright_wait", {"time": 2}, "Loading profiles..."),
            ActionStep("playwright_scroll", {"direction": "down", "amount": 400}, "Finding more...", wait_after=0.6),
            ActionStep("playwright_extract_list", {"limit": 100}, "Collecting prospects..."),
        ],
        variables={"query": r'(?:output\s+\d+\s+([^;]+?)\s+(?:URL|prospect)|(?:search|find)\s+["\']?(.+?)["\']?(?:\s+on linkedin|\s*$))'}
    ),

    # Reddit operations
    ActionTemplate(
        name="search_reddit",
        description="Search on Reddit for topics and extract user profiles",
        category=TemplateCategory.SOCIAL,
        triggers=["reddit search", "search reddit", "find on reddit", "reddit posts", "go to reddit"],
        steps=[
            ActionStep("playwright_navigate", {"url": "https://www.reddit.com/search/?q={query}&type=link"}, "Searching Reddit...", wait_after=2.0),
            ActionStep("playwright_wait", {"time": 2}, "Loading posts..."),
            ActionStep("playwright_scroll", {"direction": "down", "amount": 800}, "Finding discussions...", wait_after=0.8),
            ActionStep("playwright_scroll", {"direction": "down", "amount": 800}, "Loading more...", wait_after=0.8),
            ActionStep("playwright_extract_list", {"limit": 30, "type": "reddit_users"}, "Collecting user profiles..."),
        ],
        variables={"query": r'(?:from\s+([^.\n]+?)\s+talk|about\s+([^.\n]+?)(?:\s*\.|$)|discussing\s+([^.\n]+?)(?:\s*\.|$|,|\s+or\s+)|(?:search|find)\s+["\']?(.+?)["\']?(?:\s+on reddit|\s*$))', "_default": "lead generation"}
    ),

    ActionTemplate(
        name="reddit_subreddit",
        description="Visit a specific subreddit",
        category=TemplateCategory.SOCIAL,
        triggers=["r/", "subreddit"],
        steps=[
            ActionStep("playwright_navigate", {"url": "https://www.reddit.com/r/{subreddit}"}, "Navigate to subreddit"),
            ActionStep("playwright_snapshot", {}, "Capture subreddit state"),
        ],
        variables={"subreddit": r'r/(\w+)'}
    ),

    # Google Search
    ActionTemplate(
        name="google_search",
        description="Search on Google",
        category=TemplateCategory.SEARCH,
        triggers=["google search", "search google", "google for"],
        steps=[
            ActionStep("playwright_navigate", {"url": "https://www.google.com"}, "Navigate to Google"),
            ActionStep("playwright_snapshot", {}, "Capture search page"),
        ],
        variables={"query": r'(?:search|google|find)\s+(?:for\s+)?["\']?(.+?)["\']?(?:\s+on google|\s*$)'}
    ),

    # Zoho Mail
    ActionTemplate(
        name="open_zoho_mail",
        description="Open Zoho Mail inbox",
        category=TemplateCategory.EMAIL,
        triggers=["zoho mail", "go to zoho", "check zoho", "zoho inbox"],
        steps=[
            ActionStep("playwright_navigate", {"url": "https://mail.zoho.com"}, "Opening Zoho Mail..."),
            ActionStep("playwright_snapshot", {}, "Loading inbox..."),
        ]
    ),

    # YouTube
    ActionTemplate(
        name="search_youtube",
        description="Search on YouTube",
        category=TemplateCategory.SEARCH,
        triggers=["youtube search", "search youtube", "find video", "youtube video"],
        steps=[
            ActionStep("playwright_navigate", {"url": "https://www.youtube.com"}, "Navigate to YouTube"),
            ActionStep("playwright_snapshot", {}, "Capture YouTube state"),
        ],
        variables={"query": r'(?:search|find|watch)\s+["\']?(.+?)["\']?(?:\s+on youtube|\s+video|\s*$)'}
    ),

    # Twitter/X
    ActionTemplate(
        name="search_twitter",
        description="Search on Twitter/X",
        category=TemplateCategory.SOCIAL,
        triggers=["twitter search", "search twitter", "x search", "search x"],
        steps=[
            ActionStep("playwright_navigate", {"url": "https://twitter.com"}, "Navigate to Twitter"),
            ActionStep("playwright_snapshot", {}, "Capture Twitter state"),
        ],
        variables={"query": r'(?:search|find)\s+["\']?(.+?)["\']?(?:\s+on twitter|\s+on x|\s*$)'}
    ),

    # GitHub
    ActionTemplate(
        name="search_github",
        description="Search on GitHub",
        category=TemplateCategory.SEARCH,
        triggers=["github search", "search github", "find repo", "github repo"],
        steps=[
            ActionStep("playwright_navigate", {"url": "https://github.com"}, "Navigate to GitHub"),
            ActionStep("playwright_snapshot", {}, "Capture GitHub state"),
        ],
        variables={"query": r'(?:search|find|repo)\s+["\']?(.+?)["\']?(?:\s+on github|\s*$)'}
    ),

    # Login template (generic)
    ActionTemplate(
        name="login_generic",
        description="Generic login flow",
        category=TemplateCategory.AUTHENTICATION,
        triggers=["login to", "sign in to", "log in to"],
        steps=[
            ActionStep("playwright_snapshot", {}, "Check current login state"),
        ],
        variables={"site": r'(?:login|sign in|log in)\s+to\s+["\']?(.+?)["\']?(?:\s|$)'}
    ),

    # Screenshot template
    ActionTemplate(
        name="take_screenshot",
        description="Take a screenshot of the current page",
        category=TemplateCategory.EXTRACTION,
        triggers=["screenshot", "capture screen", "take picture"],
        steps=[
            ActionStep("playwright_screenshot", {}, "Take screenshot"),
        ]
    ),

    # Scroll page
    ActionTemplate(
        name="scroll_page",
        description="Scroll the page",
        category=TemplateCategory.NAVIGATION,
        triggers=["scroll down", "scroll up", "scroll page"],
        steps=[
            ActionStep("playwright_evaluate", {"function": "window.scrollBy(0, 500)"}, "Scroll down"),
        ]
    ),

    # Extract data
    ActionTemplate(
        name="extract_data",
        description="Extract data from current page",
        category=TemplateCategory.EXTRACTION,
        triggers=["extract", "get data", "scrape", "collect"],
        steps=[
            ActionStep("playwright_snapshot", {}, "Capture page for extraction"),
        ]
    ),

    # UI-TARS System-2 reasoning
    ActionTemplate(
        name="enable_system2_reasoning",
        description="Enable System-2 reasoning with THOUGHT and REFLECTION prompts",
        category=TemplateCategory.CONFIGURATION,
        triggers=[
            "use system-2 reasoning",
            "enable system-2",
            "use thought and reflection",
            "think before acting",
            "use deliberate reasoning"
        ],
        steps=[
            ActionStep("configure_system2", {"enabled": True}, "Enable System-2 reasoning mode"),
        ]
    ),

    # ConversationContext screenshot management
    ActionTemplate(
        name="enable_conversation_context",
        description="Enable conversation context with screenshot history management",
        category=TemplateCategory.CONFIGURATION,
        triggers=[
            "screenshot with context",
            "use conversation context",
            "enable context management",
            "keep screenshot history",
            "context-aware screenshot"
        ],
        steps=[
            ActionStep("configure_context", {"enabled": True, "max_screenshots": 5}, "Enable conversation context"),
        ]
    ),

    # UI-TARS tiered retry config
    ActionTemplate(
        name="enable_tiered_retry",
        description="Enable tiered retry timeouts (screenshot: 5s, model: 30s, action: 5s)",
        category=TemplateCategory.CONFIGURATION,
        triggers=[
            "retry with tiered timeouts",
            "use tiered retry",
            "enable smart retry",
            "use ui-tars retry",
            "retry with backoff"
        ],
        steps=[
            ActionStep("configure_retry", {
                "enabled": True,
                "screenshot_timeout": 5.0,
                "model_timeout": 30.0,
                "action_timeout": 5.0
            }, "Enable tiered retry configuration"),
        ]
    ),

    # Coordinate normalization
    ActionTemplate(
        name="enable_coordinate_normalization",
        description="Enable coordinate normalization (0-1000 range to screen pixels)",
        category=TemplateCategory.CONFIGURATION,
        triggers=[
            "normalize coordinates",
            "use normalized coordinates",
            "enable coordinate normalization",
            "use 0-1000 range",
            "transform coordinates"
        ],
        steps=[
            ActionStep("configure_normalize", {"enabled": True, "range": 1000}, "Enable coordinate normalization"),
        ]
    ),
]


class TemplateEngine:
    """Engine for matching and executing action templates."""

    def __init__(self, templates: List[ActionTemplate] = None):
        self.templates = templates or TEMPLATES

    def find_template(self, prompt: str) -> Optional[ActionTemplate]:
        """Find the best matching template for a prompt."""
        for template in self.templates:
            if template.matches(prompt):
                return template
        return None

    def get_template_by_name(self, name: str) -> Optional[ActionTemplate]:
        """Get a template by its name."""
        for template in self.templates:
            if template.name == name:
                return template
        return None

    def list_templates(self, category: TemplateCategory = None) -> List[ActionTemplate]:
        """List all templates, optionally filtered by category."""
        if category:
            return [t for t in self.templates if t.category == category]
        return self.templates

    async def execute_template(
        self,
        template: ActionTemplate,
        prompt: str,
        mcp_client,
        callback: Callable[[str], None] = None
    ) -> Dict[str, Any]:
        """
        Execute a template's action steps with PERMANENT AUTO-RETRY RULE:
        When headless extraction fails or returns empty, automatically retry with visible browser.

        Args:
            template: The template to execute
            prompt: Original user prompt (for variable extraction)
            mcp_client: MCP client for tool execution
            callback: Optional callback for progress updates

        Returns:
            Dictionary with execution results including final URL
        """
        # PERMANENT RULE: First try, then retry with visible browser if headless fails
        results = await self._execute_template_once(template, prompt, mcp_client, callback)

        # Check if we need to retry with visible browser
        extraction_status = results.get("extraction_status", "")

        # Determine if we're in headless mode - check through adapter chain
        is_headless = False
        try:
            # Try different ways to access headless setting through adapter chain
            client = mcp_client

            # Unwrap ReliableBrowserAdapter if present
            if hasattr(client, '_mcp_client'):
                client = client._mcp_client

            # Check EversaleMCPServer headless setting
            if hasattr(client, 'headless'):
                is_headless = client.headless
            elif hasattr(client, '_headless'):
                is_headless = client._headless
            elif hasattr(client, 'browser_options') and isinstance(client.browser_options, dict):
                is_headless = client.browser_options.get('headless', False)
        except Exception:
            # Assume headless if we can't determine
            is_headless = True

        # PERMANENT AUTO-RETRY RULE: If extraction failed/empty in headless, retry visible
        if extraction_status in ("empty", "failed") and is_headless:
            from loguru import logger
            logger.debug(f"Retrying ({extraction_status})")

            if callback:
                callback("Trying another approach...")

            # Switch to visible browser mode
            try:
                # Unwrap adapter layers to find the actual PlaywrightClient
                # Structure: mcp_client (EversaleMCPServer) -> client (PlaywrightClient)
                # Or: mcp_client (ReliableBrowserAdapter) -> _mcp_client -> client
                browser_client = None
                mcp_server = mcp_client

                # Try to find PlaywrightClient through various adapter chains
                if hasattr(mcp_client, '_mcp_client'):
                    mcp_server = mcp_client._mcp_client
                if hasattr(mcp_server, 'client'):
                    browser_client = mcp_server.client
                elif hasattr(mcp_server, 'playwright_tools'):
                    browser_client = mcp_server.playwright_tools

                # Set headless=False on MCP server and PlaywrightClient
                if hasattr(mcp_server, 'headless'):
                    mcp_server.headless = False
                if browser_client and hasattr(browser_client, 'headless'):
                    browser_client.headless = False

                # Close existing browser and reset page/context for clean restart
                if browser_client:
                    if hasattr(browser_client, 'browser') and browser_client.browser:
                        try:
                            await browser_client.browser.close()
                        except Exception:
                            pass
                        browser_client.browser = None
                    if hasattr(browser_client, 'context'):
                        browser_client.context = None
                    if hasattr(browser_client, 'page'):
                        browser_client.page = None

                    # Reinitialize browser with visible mode
                    if hasattr(browser_client, 'connect'):
                        logger.debug("Reinitializing browser...")
                        await browser_client.connect()
                else:
                    # Fall back to reinitializing MCP server
                    if hasattr(mcp_server, '_initialized'):
                        mcp_server._initialized = False
                    if hasattr(mcp_server, 'initialize'):
                        await mcp_server.initialize()

                # Retry execution with visible browser
                results = await self._execute_template_once(template, prompt, mcp_client, callback)
                results["retry_reason"] = "retried"

                logger.debug(f"Retry result: {results.get('extraction_status')} - {results.get('extraction_count', 0)} items")
            except Exception as e:
                from loguru import logger
                logger.debug(f"Retry failed: {e}")

        return results

    async def _execute_template_once(
        self,
        template: ActionTemplate,
        prompt: str,
        mcp_client,
        callback: Callable[[str], None] = None
    ) -> Dict[str, Any]:
        """
        Execute a template's action steps once (internal method).
        Called by execute_template which handles auto-retry logic.
        """
        results = {
            "template": template.name,
            "steps_executed": 0,
            "steps_failed": 0,
            "outputs": [],
            "variables": template.extract_variables(prompt),
        }

        # Valid tools implemented in playwright_direct.py call_tool()
        # Full Playwright MCP parity - all 22 tools available
        VALID_TOOLS = {
            # Core browser actions
            'playwright_navigate', 'playwright_click', 'playwright_fill', 'playwright_snapshot',
            'playwright_screenshot', 'playwright_evaluate', 'playwright_get_markdown', 'playwright_fetch_url',
            'playwright_type', 'playwright_select', 'playwright_hover', 'playwright_scroll',
            'playwright_wait', 'browser_snapshot', 'browser_click', 'browser_type',
            # Playwright MCP parity tools (added for full compatibility)
            'navigate_back', 'playwright_navigate_back', 'browser_navigate_back',
            'drag', 'playwright_drag', 'browser_drag',
            'file_upload', 'playwright_file_upload', 'browser_file_upload',
            'browser_tabs', 'tabs_list', 'playwright_tabs_list',
            'handle_dialog', 'playwright_handle_dialog', 'browser_handle_dialog',
            'fill_form', 'playwright_fill_form', 'browser_fill_form',
            'resize', 'playwright_resize', 'browser_resize',
            'close', 'playwright_close', 'browser_close',
            'wait_for', 'playwright_wait_for', 'browser_wait_for',
            'console_messages', 'playwright_console_messages', 'browser_console_messages',
            'network_requests', 'playwright_network_requests', 'browser_network_requests',
            # Extraction tools
            'playwright_extract_list', 'playwright_extract_fb_ads', 'get_page_info',
            # Accessibility tools
            'a11y_snapshot', 'a11y_click', 'a11y_type', 'a11y_hover', 'a11y_select',
            # Batch tools
            'batch_execute', 'playwright_batch_execute'
        }

        last_url = None
        last_output = None

        # Extract variables for substitution
        variables = results["variables"]

        for i, step in enumerate(template.steps):
            if callback:
                callback(f"Step {i + 1}/{len(template.steps)}: {step.description}")

            # Skip unknown tools instead of failing
            if step.tool not in VALID_TOOLS:
                from loguru import logger
                logger.warning(f"Skipping unknown tool in template: {step.tool}")
                results["outputs"].append({
                    "step": i + 1,
                    "tool": step.tool,
                    "description": step.description,
                    "output": f"Skipped (unknown tool: {step.tool})",
                    "success": True  # Don't fail the template
                })
                continue

            try:
                # Substitute variables in step params
                step_params = {}
                for key, value in step.params.items():
                    if isinstance(value, str):
                        # Replace {variable} placeholders with extracted values
                        # URL-encode values when inserting into URLs
                        from urllib.parse import quote
                        for var_name, var_value in variables.items():
                            placeholder = f"{{{var_name}}}"
                            if placeholder in value:
                                # URL-encode if this is a URL parameter
                                if key == "url" and "?" in value:
                                    # Encode for query string (preserve + for spaces in searches)
                                    encoded_value = quote(var_value, safe='')
                                else:
                                    encoded_value = var_value
                                value = value.replace(placeholder, encoded_value)

                        # Handle unsubstituted placeholders in URLs
                        # If URL still has {var} placeholders, use base URL instead
                        if key == "url" and "{" in value and "}" in value:
                            import re
                            # Extract base URL (everything before query params with placeholders)
                            if "?" in value:
                                base_url = value.split("?")[0]
                                # Check if query string has unresolved placeholders
                                query_part = value.split("?", 1)[1] if "?" in value else ""
                                if re.search(r'\{[^}]+\}', query_part):
                                    value = base_url  # Use base URL without query params
                            elif re.search(r'/\{[^}]+\}', value):
                                # Placeholder in path segment - remove it
                                value = re.sub(r'/\{[^}]+\}/?', '/', value)
                    step_params[key] = value

                # Execute the step
                output = await mcp_client.call_tool(step.tool, step_params)
                last_output = output

                # Extract URL from output (handle ToolResult, dict, and nested structures)
                url = None
                if hasattr(output, 'data') and output.data:
                    # ToolResult object - URL is in output.data['url']
                    if isinstance(output.data, dict):
                        url = output.data.get('url')
                elif isinstance(output, dict):
                    # Plain dict - URL is in output['url']
                    url = output.get('url')
                    # Also check nested data dict
                    if not url and isinstance(output.get('data'), dict):
                        url = output['data'].get('url')
                if url:
                    last_url = url

                results["outputs"].append({
                    "step": i + 1,
                    "tool": step.tool,
                    "description": step.description,
                    "output": str(output)[:500] if output else "OK",
                    "success": True
                })
                results["steps_executed"] += 1

                # Wait if specified
                if step.wait_after > 0:
                    import asyncio
                    await asyncio.sleep(step.wait_after)

            except Exception as e:
                results["outputs"].append({
                    "step": i + 1,
                    "tool": step.tool,
                    "description": step.description,
                    "error": str(e),
                    "success": False
                })
                results["steps_failed"] += 1

                # Stop if non-optional step fails
                if not step.optional:
                    break

        results["success"] = results["steps_failed"] == 0

        # Add final URL to top-level results
        if last_url:
            results["url"] = last_url

        # Add extracted data from last output if available
        # Handle ToolResult objects from both reliability_core.py and playwright_direct.py
        output_data = None

        if hasattr(last_output, 'data'):
            # ToolResult object - extract data attribute
            if isinstance(last_output.data, dict):
                output_data = last_output.data
            elif last_output.data is not None:
                # Data exists but isn't a dict - store as-is
                results['data'] = last_output.data
        elif isinstance(last_output, dict):
            # Plain dict output
            output_data = last_output

        # Extract prospect data from known keys
        if isinstance(output_data, dict):
            # List of keys that contain extracted prospect data
            # These will all be normalized to 'data' key for consistent access
            # Priority order: first key in this list that has data wins
            extraction_keys = ['ads', 'posts', 'items', 'listings', 'results', 'profiles', 'data']

            # Copy all metadata keys to results
            for key in ['title', 'summary', 'url', 'source_url', 'ads_count', 'extraction_method']:
                if key in output_data and output_data[key] is not None:
                    results[key] = output_data[key]

            # Find and normalize extraction data
            # Priority: first non-empty extraction key becomes normalized 'data'
            normalized_from_key = None
            for key in extraction_keys:
                if key in output_data and output_data[key]:
                    # Set normalized 'data' from first extraction key found
                    if normalized_from_key is None:
                        results['data'] = output_data[key]
                        normalized_from_key = key
                    # Copy with original key name (preserve both 'ads', 'posts', etc.)
                    # But don't overwrite 'data' if we already normalized from a different key
                    if key != 'data' or normalized_from_key == 'data':
                        results[key] = output_data[key]

        # MANDATORY: Add extraction_status field for better user feedback
        # This field must be checked by orchestration to ensure users always see prospect data or explanation
        extracted_data = (
            results.get("data") or
            results.get("items") or
            results.get("ads") or
            results.get("posts") or
            results.get("listings") or
            results.get("results") or
            results.get("profiles") or
            []
        )

        if extracted_data and isinstance(extracted_data, list) and len(extracted_data) > 0:
            # Success: we found prospect data
            results["extraction_status"] = "success"
            results["extraction_count"] = len(extracted_data)

            # Provide multi-item output when user asks for many leads / URLs-only.
            formatted_output = format_extracted_data_for_prompt(prompt, extracted_data)
            if formatted_output:
                results["formatted_output"] = formatted_output

            # Build user-friendly summary for first prospect
            first_item = extracted_data[0] if extracted_data else {}
            if isinstance(first_item, dict):
                prospect_name = (
                    first_item.get("advertiser") or
                    first_item.get("title") or
                    first_item.get("name") or
                    first_item.get("author") or
                    first_item.get("link", "")[:60]
                )
                prospect_url = first_item.get("url") or first_item.get("link") or first_item.get("landing_url")
                if prospect_name and prospect_url:
                    results["extraction_summary"] = f"Prospect: {prospect_name} | {prospect_url} (Found {len(extracted_data)} total)"
                elif prospect_name:
                    results["extraction_summary"] = f"Prospect: {prospect_name} (Found {len(extracted_data)} total)"
                else:
                    results["extraction_summary"] = f"Found {len(extracted_data)} prospect(s) at {last_url or 'page'}"
        elif results.get("success") and last_url:
            # Empty: page loaded successfully but no prospects found
            results["extraction_status"] = "empty"
            results["extraction_count"] = 0
            results["extraction_summary"] = f"No prospects extracted from {last_url} - page may require login or have no results"
        else:
            # Failed: extraction or navigation failed
            results["extraction_status"] = "failed"
            results["extraction_count"] = 0
            results["extraction_summary"] = f"Extraction failed - {results.get('outputs', [{}])[-1].get('error', 'unknown error')}" if results.get("outputs") else "Extraction failed"

        return results


# -----------------------------------------------------------------------------
# Output helpers (used by orchestration + multi-task mode)
# -----------------------------------------------------------------------------

def _is_urls_only_prompt(prompt: str) -> bool:
    p = (prompt or "").lower()
    return (
        ("output only" in p and ("url" in p or "urls" in p or "username" in p or "usernames" in p)) or
        ("urls only" in p) or
        ("no explanations" in p) or
        ("output only urls" in p) or
        ("output only url" in p)
    )


def _wants_many_leads(prompt: str) -> bool:
    p = (prompt or "").lower()
    return (
        "as many" in p or
        "as many leads" in p or
        "return as many" in p or
        ("max " in p and "minute" in p) or
        ("spend max" in p and "minute" in p)
    )


def _extract_requested_count(prompt: str) -> Optional[int]:
    """
    Extract explicit requested count from a prompt.

    Examples:
      - "find 1 advertiser"
      - "output 10 leads"
      - "return 25 profiles"
    """
    p = (prompt or "").lower()
    patterns = [
        r'\bfind\s+(\d{1,3})\b',
        r'\boutput\s+(\d{1,3})\b',
        r'\breturn\s+(\d{1,3})\b',
        r'\bget\s+(\d{1,3})\b',
        r'\bcollect\s+(\d{1,3})\b',
        r'\btarget\s+(\d{1,3})\b',
    ]
    for pat in patterns:
        m = re.search(pat, p)
        if m:
            try:
                n = int(m.group(1))
                if n > 0:
                    return n
            except Exception:
                continue
    return None


def _is_social_url(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
        return any(h in host for h in ["facebook.com", "fb.com", "instagram.com", "tiktok.com"])
    except Exception:
        return False


def format_extracted_data_for_prompt(prompt: str, extracted_data: List[Any]) -> Optional[str]:
    """
    Produce multi-item output when the user asks for many leads or URLs-only.

    - URLs-only: returns one URL per line (deduped, preserves order)
    - Otherwise: returns numbered name + "Advertiser URL:" pairs (parsable by ProspectCollector)
    """
    if not extracted_data or not isinstance(extracted_data, list):
        return None

    urls_only = _is_urls_only_prompt(prompt)
    wants_many = _wants_many_leads(prompt)
    requested_count = _extract_requested_count(prompt)

    # Keep output bounded; multi-task mode can call repeatedly if needed.
    # Precedence: "as many" wins over "find 1" style constraints.
    if wants_many:
        max_items = max(50, requested_count or 0)
    elif requested_count:
        max_items = max(1, min(200, requested_count))
    else:
        max_items = 10

    seen_urls = set()
    lines: List[str] = []
    numbered_count = 0

    def pick_url(item: Dict[str, Any]) -> Optional[str]:
        for key in (
            "final_url",
            "landing_url",
            "landingPageUrl",
            "destination_url",
            "url",
            "link",
            "page_url",
            "fb_page_url",
        ):
            val = item.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        return None

    def add_url(url: str) -> bool:
        url = (url or "").strip()
        if not url or url in seen_urls:
            return False
        seen_urls.add(url)
        lines.append(url if urls_only else f"Advertiser URL: {url}")
        return True

    for item in extracted_data:
        if not isinstance(item, dict):
            continue

        name = (item.get("advertiser") or item.get("name") or item.get("title") or item.get("author") or "").strip()
        url = pick_url(item)
        if not url:
            continue

        # Prefer external landing URLs over social URLs when both exist
        if _is_social_url(url):
            candidate = item.get("landing_url") or item.get("final_url")
            if isinstance(candidate, str) and candidate.strip() and not _is_social_url(candidate):
                url = candidate.strip()

        if urls_only:
            add_url(url)
        else:
            if name:
                numbered_count += 1
                lines.append(f"{numbered_count}. {name}")
                add_url(url)
            else:
                add_url(url)

        if len(seen_urls) >= max_items:
            break

    # Only return for prompts that asked for it, or when there's enough to justify a list.
    if urls_only or wants_many or len(seen_urls) > 1:
        return "\n".join(lines) if lines else None
    return None


# Singleton engine instance
_engine_instance = None


def get_template_engine() -> TemplateEngine:
    """Get the singleton template engine instance."""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = TemplateEngine()
    return _engine_instance


def find_template(prompt: str) -> Optional[ActionTemplate]:
    """Find a matching template for the given prompt."""
    return get_template_engine().find_template(prompt)


def list_templates(category: TemplateCategory = None) -> List[ActionTemplate]:
    """List available templates."""
    return get_template_engine().list_templates(category)


async def execute_template(
    template_or_name,
    prompt: str,
    mcp_client,
    callback: Callable[[str], None] = None
) -> Dict[str, Any]:
    """Execute a template by name or template object."""
    engine = get_template_engine()

    if isinstance(template_or_name, str):
        template = engine.get_template_by_name(template_or_name)
    else:
        template = template_or_name

    if not template:
        return {"success": False, "error": f"Template not found: {template_or_name}"}

    return await engine.execute_template(template, prompt, mcp_client, callback)
