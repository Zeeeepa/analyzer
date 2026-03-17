"""
Tool Executor Module

Extracted from brain_enhanced_v2.py (lines 1715-2420) to handle all tool execution logic:
- Tool validation and name correction
- Parallel and sequential tool execution
- Error handling and self-healing
- Hallucination detection and recovery
- Retry logic with smart fallbacks

This module reduces brain_enhanced_v2.py complexity and makes tool execution
testable and reusable across different agent implementations.
"""

import asyncio
import base64
import json
import re
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from loguru import logger
from rich.console import Console

from .self_healing_system import self_healing
from .smart_retry import get_retry_manager, get_verifier, get_escalation

# Visual targeting for vision-first element location
try:
    from .visual_targeting import get_visual_targeting, click_with_visual_targeting
    VISUAL_TARGETING_AVAILABLE = True
except ImportError:
    VISUAL_TARGETING_AVAILABLE = False
    logger.warning("Visual targeting not available")

console = Console()


@dataclass
class ActionResult:
    """Result of a tool execution."""
    success: bool
    data: Any = None
    error: str = ""
    screenshot: bytes = None


# Tool name corrections mapping - fixes common LLM hallucinations
TOOL_CORRECTIONS = {
    # Navigation variations
    'navigate': 'playwright_navigate',
    'goto': 'playwright_navigate',
    'go_to': 'playwright_navigate',
    'browser_navigate': 'playwright_navigate',
    'open_url': 'playwright_navigate',
    'visit': 'playwright_navigate',
    'browse': 'playwright_navigate',
    # Text/content extraction
    'get_text': 'playwright_get_text',
    'get_element_text': 'playwright_get_text',
    'extract_text': 'playwright_get_text',
    'read_page': 'playwright_get_markdown',
    'get_page': 'playwright_get_markdown',
    'get_content': 'playwright_get_markdown',
    'page_content': 'playwright_get_markdown',
    # Snapshot variations
    'snapshot': 'playwright_snapshot',
    'get_snapshot': 'playwright_snapshot',
    'page_snapshot': 'playwright_snapshot',
    'accessibility': 'playwright_snapshot',
    # Click variations
    'click': 'playwright_click',
    'click_element': 'playwright_click',
    'press': 'playwright_click',
    # Fill variations
    'fill': 'playwright_fill',
    'type': 'playwright_fill',
    'input': 'playwright_fill',
    'enter_text': 'playwright_fill',
    # Screenshot
    'screenshot': 'playwright_screenshot',
    'take_screenshot': 'playwright_screenshot',
    'capture': 'playwright_screenshot',
    # Extract variations
    'extract': 'playwright_llm_extract',
    'llm_extract': 'playwright_llm_extract',
    'extract_data': 'playwright_llm_extract',
    'scrape': 'playwright_llm_extract',
    # Direct CSS extraction (NO LLM - 100% accurate)
    'extract_list': 'playwright_extract_list',
    'extract_items': 'playwright_extract_list',
    'get_list': 'playwright_extract_list',
    'extract_structured': 'playwright_extract_structured',
    # Contacts
    'find_contacts': 'playwright_find_contacts',
    'get_contacts': 'playwright_find_contacts',
    'extract_contacts': 'playwright_extract_entities',
    'get_emails': 'playwright_extract_entities',
}

# Human-readable progress messages for tools (Claude Code style)
TOOL_PROGRESS_MESSAGES = {
    'playwright_navigate': 'Navigating to page',
    'playwright_click': 'Clicking element',
    'playwright_fill': 'Filling form',
    'playwright_extract_page_fast': 'Extracting page data',
    'playwright_get_markdown': 'Reading page content',
    'playwright_screenshot': 'Taking screenshot',
    'playwright_snapshot': 'Getting page structure',
    'playwright_extract_fb_ads': 'Extracting ads',
    'playwright_extract_reddit': 'Extracting posts',
    'playwright_extract_list': 'Extracting list items (CSS)',
    'playwright_extract_structured': 'Extracting structured data',
}


class ToolExecutor:
    """
    Handles all tool execution logic including validation, correction,
    parallel execution, error handling, and recovery.

    Extracted from EnhancedBrain to reduce complexity and improve testability.
    """

    def __init__(
        self,
        mcp_client,
        browser,
        stats: Dict,
        messages: List,
        hallucination_guard=None,
        resource_monitor=None,
        resource_economy=None,
        memory_arch=None,
        cascading_recovery=None,
        session_state=None,
        ollama_client=None,
        fast_model: str = None,
        visual_targeting_enabled: bool = True,
    ):
        """
        Initialize ToolExecutor with dependencies.

        Args:
            mcp_client: MCP client for calling tools
            browser: Browser instance (can be None)
            stats: Statistics dict to update
            messages: Message list reference for conversation history
            hallucination_guard: Guard instance for detecting fake data
            resource_monitor: Monitor for resource limits
            resource_economy: Economy for cost estimation
            memory_arch: Memory architecture for recording steps
            cascading_recovery: Recovery system instance
            session_state: Session state for learning and logging
            ollama_client: Ollama client for LLM calls
            fast_model: Fast model name for alternative generation
            visual_targeting_enabled: Enable visual-first element targeting (default: True)
        """
        self.mcp = mcp_client
        self.browser = browser
        self.stats = stats
        self.messages = messages
        self.hallucination_guard = hallucination_guard
        self.resource_monitor = resource_monitor
        self.resource_economy = resource_economy
        self.memory_arch = memory_arch
        self.cascading_recovery = cascading_recovery
        self.session_state = session_state
        self.ollama_client = ollama_client
        self.fast_model = fast_model
        self.visual_targeting_enabled = visual_targeting_enabled and VISUAL_TARGETING_AVAILABLE
        self._last_action_name = None

        # Log visual targeting status
        if self.visual_targeting_enabled:
            logger.info("Visual targeting ENABLED - using vision-first element location")
        else:
            logger.info("Visual targeting DISABLED - using traditional selectors only")

    def validate_tool_calls(self, tool_calls: List[Dict]) -> List[Dict]:
        """
        Validate and correct tool calls - fix hallucinated tool names.

        Args:
            tool_calls: List of tool call dicts from LLM

        Returns:
            List of corrected tool calls
        """
        if not tool_calls:
            return tool_calls

        available_tools = set(self.mcp.tools.keys()) if hasattr(self.mcp, 'tools') else set()

        corrected = []
        for tc in tool_calls:
            func = tc.get('function', {})
            name = func.get('name', '')

            # Check if tool exists
            if name not in available_tools:
                # Try to correct the name
                corrected_name = TOOL_CORRECTIONS.get(name.lower())
                if corrected_name and corrected_name in available_tools:
                    logger.info(f"Corrected tool name: {name} -> {corrected_name}")
                    func['name'] = corrected_name
                elif name.lower() in TOOL_CORRECTIONS:
                    # Even if not in available_tools, use the correction
                    corrected_name = TOOL_CORRECTIONS[name.lower()]
                    logger.info(f"Corrected tool name: {name} -> {corrected_name}")
                    func['name'] = corrected_name
                else:
                    # Skip invalid tools entirely
                    logger.warning(f"Skipping unknown tool: {name}")
                    continue

            corrected.append(tc)

        return corrected

    async def execute_parallel(self, tool_calls: List[Dict]) -> List[ActionResult]:
        """
        Execute tools in parallel when possible.

        Navigation and click tools must be sequential, others can be parallel.

        Args:
            tool_calls: List of tool call dicts

        Returns:
            List of ActionResult objects
        """
        # Group into parallelizable and sequential
        parallel = []
        sequential = []

        for tc in tool_calls:
            name = tc.get('function', {}).get('name', '')
            # Navigation must be sequential, others can parallel
            if 'navigate' in name or 'click' in name:
                sequential.append(tc)
            else:
                parallel.append(tc)

        results = []

        # Execute parallel tools
        if parallel:
            console.print(f"[yellow]Executing {len(parallel)} tools in parallel[/yellow]")
            parallel_results = await asyncio.gather(
                *[self.execute_tool(tc) for tc in parallel],
                return_exceptions=True
            )
            results.extend(parallel_results)

        # Execute sequential tools
        for tc in sequential:
            result = await self.execute_tool(tc)
            results.append(result)

        return results

    async def execute_tool(self, tool_call: Dict) -> ActionResult:
        """
        Execute single tool with retry logic.

        Args:
            tool_call: Tool call dict with function name and arguments

        Returns:
            ActionResult with success status and data/error
        """
        func = tool_call.get('function', {})
        name = func.get('name', '')
        args = func.get('arguments', {})
        # Extract tool_call_id for proper Ollama tool response format
        tool_call_id = tool_call.get('id', '')

        if isinstance(args, str):
            try:
                args = json.loads(args)
            except (json.JSONDecodeError, ValueError) as e:
                logger.debug(f"Could not parse args as JSON: {e}")
                args = {}

        # AUTO-CORRECTION: Fix common model mistakes before execution
        name, args = await self.auto_correct_tool_call(name, args)

        # VISUAL TARGETING: Try vision-first for click actions (before selector fallback)
        if self.visual_targeting_enabled and 'click' in name.lower():
            visual_result = await self._try_visual_click(name, args)
            if visual_result and visual_result.success:
                # Visual click succeeded - record and return
                tool_msg = {
                    'role': 'tool',
                    'content': json.dumps(visual_result.data, default=str)[:2000],
                    'name': name
                }
                if tool_call_id:
                    tool_msg['tool_call_id'] = tool_call_id
                self.messages.append(tool_msg)

                self._last_action_name = name
                if self.session_state:
                    self.session_state.record_successful_tool(name, args)
                    self.session_state.log_action(name, args, True, result=visual_result.data, attempt=1)

                return visual_result

        # Check resource limits
        cost, cost_reason = self.resource_economy.estimate(name, args if isinstance(args, dict) else {}) if self.resource_economy else (1.0, "default")
        issues = self.resource_monitor.check() if self.resource_monitor else []
        if issues and cost >= 2.0:
            warning = f"Resource limit prevents calling {name}: {', '.join(issues)}"
            if self.session_state:
                self.session_state.log_resource_issue(warning)
            return ActionResult(success=False, error=warning)

        self.stats['tool_calls'] += 1
        console.print(f"  [yellow]{name}[/yellow] [dim]{cost_reason}[/dim]")

        # Human-readable progress for UI
        progress_msg = TOOL_PROGRESS_MESSAGES.get(name, f'Running {name}')
        # Note: notify_progress would be called from brain_enhanced_v2 if needed

        # Get DOM fingerprint before browser actions for proof-of-action
        before_fingerprint = None
        action_tools = {'playwright_click', 'playwright_fill', 'browser_click', 'browser_type'}
        if name in action_tools or name.startswith('browser_'):
            try:
                before_fingerprint = await asyncio.wait_for(
                    self.mcp.call_tool('browser_fingerprint', {}),
                    timeout=5
                )
            except Exception:
                pass  # Fingerprint is optional

        # Try up to 3 times with different approaches
        for attempt in range(3):
            try:
                # Add timeout to prevent hanging
                # Extraction tools need more time (LLM fallbacks)
                if 'extract' in name or 'batch' in name or 'llm_' in name:
                    tool_timeout = 90  # 90 seconds for extraction tools
                elif 'playwright' in name or 'browser_' in name:
                    tool_timeout = 45  # 45 seconds for basic browser ops
                else:
                    tool_timeout = 60
                result = await asyncio.wait_for(
                    self.mcp.call_tool(name, args),
                    timeout=tool_timeout
                )

                # Verify action had effect
                if before_fingerprint and before_fingerprint.get('success'):
                    try:
                        verification = await asyncio.wait_for(
                            self.mcp.call_tool('browser_verify_action', {
                                'before_fp': before_fingerprint,
                                'action_type': 'click' if 'click' in name else 'type'
                            }),
                            timeout=5
                        )
                        if verification.get('success'):
                            result['_verification'] = {
                                'action_verified': verification.get('action_verified', False),
                                'changes': verification.get('changes', [])
                            }
                    except Exception:
                        pass  # Verification is optional

                # HALLUCINATION CHECK: Validate tool output for fake/placeholder data
                url_arg = args.get('url', '') if isinstance(args, dict) else ''
                if self.hallucination_guard:
                    validation = self.hallucination_guard.validate_output(
                        result,
                        source_tool=name,
                        source_url=url_arg
                    )
                else:
                    validation = type('obj', (object,), {'is_valid': True, 'issues': []})()

                if not validation.is_valid:
                    logger.warning(f"HALLUCINATION DETECTED in {name}: {validation.issues}")

                    # RECOVERY: Attempt to get real data instead of fake
                    recovered_result = await self.recover_from_hallucination(
                        tool_name=name,
                        original_args=args,
                        issues=validation.issues,
                        original_result=result
                    )

                    if recovered_result and recovered_result.get('_recovery') not in ['failed', 'error']:
                        logger.success(f"[HALLUCINATION RECOVERY] Successfully recovered real data")
                        result = recovered_result
                    elif validation.cleaned_data:
                        # Use cleaned data if recovery failed but we have cleaned version
                        result = validation.cleaned_data
                        result['_note'] = 'Fake data removed, some fields may be missing'
                    else:
                        # Last resort: mark as suspicious
                        result = {
                            "warning": "FAKE DATA DETECTED - Recovery attempted but failed",
                            "issues": validation.issues,
                            "guidance": "Use browser tools (playwright_navigate, playwright_extract_page_fast) with a real URL to get actual data",
                            "original": result
                        }

                # Add to messages with tool_call_id for proper Ollama tool response matching
                tool_msg = {
                    'role': 'tool',
                    'content': json.dumps(result, default=str)[:2000],
                    'name': name
                }
                if tool_call_id:
                    tool_msg['tool_call_id'] = tool_call_id
                self.messages.append(tool_msg)

                # Capture screenshot for vision (handled by brain_enhanced_v2)
                screenshot = None
                # Note: Screenshot capture would be handled by caller if needed

                self._last_action_name = name
                if self.session_state:
                    self.session_state.record_successful_tool(name, args)
                    self.session_state.log_action(name, args, True, result=result, attempt=attempt+1)

                # Smart retry: Record success for learning
                retry_mgr = get_retry_manager()
                retry_mgr.record_attempt(
                    action=name,
                    strategy=f"attempt_{attempt+1}",
                    args=args,
                    success=True,
                    result=result
                )

                # Record step in memory architecture
                if self.memory_arch:
                    try:
                        observation = json.dumps(result, default=str)[:500] if result else "Success"
                        reasoning = self.messages[-1].get('content', '') if self.messages else ''
                        self.memory_arch.add_step(
                            action=name,
                            observation=observation,
                            reasoning=reasoning[:200],
                            tool_calls=[{'name': name, 'arguments': args}],
                            success=True
                        )
                    except Exception as e:
                        logger.debug(f"Memory step recording failed: {e}")

                return ActionResult(success=True, data=result, screenshot=screenshot)

            except asyncio.TimeoutError:
                error_msg = f"Tool {name} timed out after {tool_timeout}s"
                logger.warning(error_msg)
                if self.session_state:
                    self.session_state.record_failed_tool(name, args)
                    self.session_state.log_action(name, args, False, error=error_msg, attempt=attempt+1)

                # Try fallback for timed-out tools
                fallback_result = await self.try_tool_fallback(name, args)
                if fallback_result:
                    fallback_msg = {
                        'role': 'tool',
                        'content': json.dumps(fallback_result, default=str)[:2000],
                        'name': name
                    }
                    if tool_call_id:
                        fallback_msg['tool_call_id'] = tool_call_id
                    self.messages.append(fallback_msg)
                    return ActionResult(success=True, data=fallback_result)

                error_tool_msg = {
                    'role': 'tool',
                    'content': json.dumps({'error': error_msg}),
                    'name': name
                }
                if tool_call_id:
                    error_tool_msg['tool_call_id'] = tool_call_id
                self.messages.append(error_tool_msg)
                return ActionResult(success=False, error=error_msg)

            except Exception as e:
                logger.warning(f"Tool {name} attempt {attempt+1} failed: {e}")

                if self.session_state:
                    self.session_state.record_failed_tool(name, args)
                    self.session_state.log_action(name, args, False, error=str(e), attempt=attempt+1)

                # Record failure in self-healing system
                try:
                    self_healing.record_failure(
                        error=str(e),
                        context={
                            'function': name,
                            'arguments': args,
                            'url': self.browser.page.url if self.browser and self.browser.page else '',
                            'error_type': type(e).__name__,
                            'attempt': attempt + 1
                        }
                    )
                except Exception as healing_err:
                    logger.debug(f"Failed to record in self-healing: {healing_err}")

                # Smart retry: Record failure
                retry_mgr = get_retry_manager()
                retry_mgr.record_attempt(
                    action=name,
                    strategy=f"attempt_{attempt+1}",
                    args=args,
                    success=False,
                    error=str(e)
                )

                # Try self-healing on first failure
                if attempt == 0:
                    healing_result = await self.handle_error_with_healing(
                        error=e,
                        context={
                            'function': name,
                            'arguments': args,
                            'url': self.browser.page.url if self.browser and self.browser.page else '',
                            'error_type': type(e).__name__
                        },
                        attempt=attempt + 1
                    )
                    if healing_result and healing_result.get('success'):
                        logger.info("[SELF-HEALING] Continuing after successful recovery")

                # Check if stuck in loop
                is_loop, loop_reason = retry_mgr.is_stuck_in_loop()
                if is_loop:
                    logger.warning(f"Loop detected: {loop_reason}")
                    escalation = get_escalation()
                    if escalation.should_escalate(attempt + 1, attempt + 1):
                        console.print(f"\n[yellow]Stuck: {loop_reason}[/yellow]")
                        console.print("[dim]Skipping this action and continuing...[/dim]\n")
                        skip_msg = {
                            'role': 'tool',
                            'content': json.dumps({'error': f'Skipped due to repeated failures: {str(e)[:100]}'}),
                            'name': name
                        }
                        if tool_call_id:
                            skip_msg['tool_call_id'] = tool_call_id
                        self.messages.append(skip_msg)
                        return ActionResult(success=False, error=f"Skipped: {loop_reason}")

                if attempt < 2:
                    # Get smart recommendation for next strategy
                    rec = retry_mgr.get_recommendation(name, args, str(e))
                    if rec['action'] == 'retry_with_strategy':
                        logger.info(f"Smart retry: {rec.get('reason', 'trying alternative')}")

                    # Try alternative approach
                    args = await self._get_alternative_args(name, args, str(e))
                    if not args:
                        break
                    self.stats['retries'] += 1
                else:
                    final_error_msg = {
                        'role': 'tool',
                        'content': json.dumps({'error': str(e)}),
                        'name': name
                    }
                    if tool_call_id:
                        final_error_msg['tool_call_id'] = tool_call_id
                    self.messages.append(final_error_msg)
                    return ActionResult(success=False, error=str(e))

        return ActionResult(success=False, error="Max retries exceeded")

    async def _try_visual_click(self, tool_name: str, args: Dict) -> Optional[ActionResult]:
        """
        Attempt to click using visual targeting as the FIRST strategy.

        This is called BEFORE traditional selector-based clicking.
        Uses vision models to locate elements based on visual appearance.

        Args:
            tool_name: Name of the click tool (playwright_click, etc.)
            args: Tool arguments (may contain selector, description, etc.)

        Returns:
            ActionResult if visual click succeeded, None if should fallback to selectors
        """
        if not self.browser or not self.browser.page:
            logger.debug("[VISUAL TARGETING] No browser page available")
            return None

        try:
            page = self.browser.page

            # Extract target description from args
            # Priority: description > selector text > inferred from selector
            target_description = None

            if isinstance(args, dict):
                # Check for explicit description
                target_description = args.get('description') or args.get('visual_description')

                # If no description, try to infer from selector
                if not target_description and 'selector' in args:
                    selector = args['selector']
                    # Extract meaningful text from selector
                    if ':has-text(' in selector:
                        import re
                        match = re.search(r':has-text\([\'"]([^\'"]+)[\'"]\)', selector)
                        if match:
                            target_description = f"{match.group(1)} button"
                    elif 'submit' in selector.lower():
                        target_description = "Submit button"
                    elif 'login' in selector.lower() or 'sign' in selector.lower():
                        target_description = "Login button"
                    elif 'search' in selector.lower():
                        target_description = "Search button"
                    # Add more common patterns as needed

            if not target_description:
                logger.debug("[VISUAL TARGETING] No description available, falling back to selectors")
                return None

            logger.info(f"[VISUAL TARGETING] Attempting to click: {target_description}")

            # Take screenshot
            screenshot = await page.screenshot()
            screenshot_b64 = base64.b64encode(screenshot).decode()

            # Use visual targeting to locate element
            targeting = get_visual_targeting()
            result = await targeting.locate_element(screenshot_b64, target_description)

            if result.success and result.coordinates:
                x, y = result.coordinates
                logger.success(
                    f"[VISUAL TARGETING] Located element at ({x}, {y}) "
                    f"with confidence {result.confidence:.2f}"
                )

                # Use humanized click if available
                if hasattr(self.browser, 'humanized_click'):
                    await self.browser.humanized_click(x, y)
                else:
                    # Standard coordinate click
                    await page.mouse.click(x, y)

                # Return success
                return ActionResult(
                    success=True,
                    data={
                        'success': True,
                        'method': 'visual_targeting',
                        'coordinates': (x, y),
                        'confidence': result.confidence,
                        'description': target_description
                    }
                )
            else:
                logger.debug(
                    f"[VISUAL TARGETING] Could not locate '{target_description}' visually, "
                    f"falling back to selectors"
                )
                return None

        except Exception as e:
            logger.warning(f"[VISUAL TARGETING] Error: {e}, falling back to selectors")
            return None

    async def auto_correct_tool_call(self, name: str, args: Dict) -> Tuple[str, Dict]:
        """
        Auto-correct common model mistakes before execution.

        Fixes cases where model calls a tool with 'url' parameter when it should
        navigate first, then call the tool. Also normalizes parameter names.

        Args:
            name: Tool name
            args: Tool arguments

        Returns:
            Tuple of (corrected_name, corrected_args)
        """
        if not isinstance(args, dict):
            return name, args

        # SITE-AWARE TOOL ROUTING: Force CSS extraction on known sites
        # This bypasses LLM's poor tool selection and prevents hallucination
        EXTRACTION_TOOLS = {
            'playwright_batch_extract', 'playwright_get_content', 'playwright_llm_extract',
            'playwright_extract_structured', 'extract_data', 'get_page_data', 'scrape_page',
            'extract_items', 'get_items', 'extract_table'
        }
        KNOWN_SITES = [
            'news.ycombinator.com', 'amazon.com', 'ebay.com', 'github.com/trending',
            'reddit.com', 'linkedin.com/jobs', 'indeed.com', 'zillow.com'
        ]

        if name in EXTRACTION_TOOLS:
            # Get current URL from browser - try multiple sources
            current_url = ''
            try:
                # Try playwright_direct browser
                if hasattr(self, 'browser') and self.browser:
                    if hasattr(self.browser, 'page') and self.browser.page:
                        current_url = self.browser.page.url or ''
                    elif hasattr(self.browser, 'current_url'):
                        current_url = self.browser.current_url or ''
                # Try MCP playwright context
                if not current_url and hasattr(self, 'mcp') and self.mcp:
                    if hasattr(self.mcp, 'playwright') and self.mcp.playwright:
                        pw = self.mcp.playwright
                        if hasattr(pw, 'page') and pw.page:
                            current_url = pw.page.url or ''
                        elif hasattr(pw, 'current_url'):
                            current_url = pw.current_url or ''
            except Exception as e:
                logger.debug(f"Could not get current URL: {e}")

            # Check if we're on a known site
            is_known_site = any(site in current_url for site in KNOWN_SITES)

            if is_known_site:
                logger.info(f"[AUTO-FIX] Redirecting {name} -> playwright_extract_list on known site: {current_url}")
                # Extract limit from args if present
                limit = args.get('limit', args.get('count', args.get('max_items', 10)))
                return 'playwright_extract_list', {'limit': limit}

        # PARAMETER NORMALIZATION: Fix common parameter name variations
        # playwright_fill: normalize text/content/input -> value
        if name == 'playwright_fill':
            if 'value' not in args:
                for alt in ['text', 'content', 'input', 'query']:
                    if alt in args:
                        args['value'] = args.pop(alt)
                        logger.debug(f"[AUTO-FIX] Normalized {alt} -> value for playwright_fill")
                        break
            if 'selector' not in args:
                for alt in ['element', 'target', 'field']:
                    if alt in args:
                        args['selector'] = args.pop(alt)
                        logger.debug(f"[AUTO-FIX] Normalized {alt} -> selector for playwright_fill")
                        break

        # playwright_click: normalize element/target -> selector
        if name == 'playwright_click':
            if 'selector' not in args:
                for alt in ['element', 'target', 'mmid', 'button']:
                    if alt in args:
                        args['selector'] = args.pop(alt)
                        logger.debug(f"[AUTO-FIX] Normalized {alt} -> selector for playwright_click")
                        break

        # playwright_navigate: normalize href/link -> url
        if name == 'playwright_navigate':
            if 'url' not in args:
                for alt in ['href', 'link', 'address', 'page']:
                    if alt in args:
                        args['url'] = args.pop(alt)
                        logger.debug(f"[AUTO-FIX] Normalized {alt} -> url for playwright_navigate")
                        break

        url = args.get('url')

        # FIX 1: smart_type called with 'url' - navigate first
        if name == 'smart_type' and url:
            logger.info(f"[AUTO-FIX] smart_type called with url - navigating to {url} first")
            try:
                await self.mcp.call_tool('playwright_navigate', {'url': url})
                await asyncio.sleep(1)
                corrected_args = {k: v for k, v in args.items() if k != 'url'}
                if not corrected_args.get('selector') and not corrected_args.get('text'):
                    return 'playwright_snapshot', {}
                return name, corrected_args
            except Exception as e:
                logger.warning(f"[AUTO-FIX] Navigation failed: {e}")
                return name, args

        # FIX 2: playwright_fill with url param
        if name == 'playwright_fill' and url:
            logger.info(f"[AUTO-FIX] playwright_fill called with url - navigating to {url} first")
            try:
                await self.mcp.call_tool('playwright_navigate', {'url': url})
                await asyncio.sleep(1)
                corrected_args = {k: v for k, v in args.items() if k != 'url'}
                return name, corrected_args
            except Exception as e:
                logger.warning(f"[AUTO-FIX] Navigation failed: {e}")
                return name, args

        # FIX 3: wait_and_click with url param
        if name == 'wait_and_click' and url:
            logger.info(f"[AUTO-FIX] wait_and_click called with url - navigating to {url} first")
            try:
                await self.mcp.call_tool('playwright_navigate', {'url': url})
                await asyncio.sleep(1)
                corrected_args = {k: v for k, v in args.items() if k != 'url'}
                return name, corrected_args
            except Exception as e:
                logger.warning(f"[AUTO-FIX] Navigation failed: {e}")
                return name, args

        # FIX 4: extract_table with url param
        if name == 'extract_table' and url:
            logger.info(f"[AUTO-FIX] extract_table called with url - navigating to {url} first")
            try:
                await self.mcp.call_tool('playwright_navigate', {'url': url})
                await asyncio.sleep(1)
                corrected_args = {k: v for k, v in args.items() if k != 'url'}
                return name, corrected_args
            except Exception as e:
                logger.warning(f"[AUTO-FIX] Navigation failed: {e}")
                return name, args

        return name, args

    async def try_tool_fallback(self, name: str, args: Dict) -> Optional[Dict]:
        """
        Try a simpler/faster fallback when a tool times out.

        Args:
            name: Tool name that timed out
            args: Original arguments

        Returns:
            Fallback result dict or None
        """
        try:
            # Fallbacks for common timeout scenarios
            if name == 'playwright_navigate':
                url = args.get('url', '')
                if url:
                    logger.info(f"Fallback: trying playwright_get_markdown for {url}")
                    return await asyncio.wait_for(
                        self.mcp.call_tool('playwright_get_markdown', {'url': url}),
                        timeout=15
                    )

            elif name == 'playwright_snapshot':
                if self.browser and self.browser.page:
                    title = await self.browser.page.title()
                    return {'title': title, 'fallback': True, 'note': 'Full snapshot timed out'}

            elif name == 'playwright_get_text':
                selector = args.get('selector', '')
                return {'error': f'Element {selector} not found or page too slow', 'fallback': True}

            elif name == 'playwright_llm_extract':
                url = args.get('url', '')
                if url:
                    logger.info(f"Fallback: trying playwright_get_markdown for {url}")
                    result = await asyncio.wait_for(
                        self.mcp.call_tool('playwright_get_markdown', {'url': url}),
                        timeout=15
                    )
                    if result and not result.get('error'):
                        result['fallback'] = True
                        result['note'] = 'LLM extraction timed out, showing raw markdown'
                    return result

            return None

        except Exception as e:
            logger.warning(f"Fallback also failed: {e}")
            return None

    async def handle_error_with_healing(
        self,
        error: Exception,
        context: Dict[str, Any],
        attempt: int = 1
    ) -> Optional[Dict[str, Any]]:
        """
        Use self-healing system to recover from errors.

        Args:
            error: The exception that occurred
            context: Context dict with function name, args, etc.
            attempt: Current attempt number

        Returns:
            Strategy dict if recovery possible, None otherwise
        """
        try:
            # Analyze the failure and get recovery strategy
            strategy = await self_healing.analyze_failure(
                error=error,
                context=context,
                attempt_number=attempt
            )

            if not strategy:
                return None

            logger.info(f"[SELF-HEALING] Applying strategy: {strategy.get('action', 'unknown')}")

            # Execute the healing strategy
            result = await self_healing.execute_strategy(
                strategy=strategy,
                playwright_client=self.browser
            )

            if result.get('success'):
                logger.success(f"[SELF-HEALING] Recovery successful: {result.get('steps_executed', [])}")
                return result
            else:
                logger.debug(f"[SELF-HEALING] Recovery failed: {result.get('error')}")
                return None

        except Exception as e:
            logger.debug(f"[SELF-HEALING] Error in healing system: {e}")
            return None

    async def recover_from_hallucination(
        self,
        tool_name: str,
        original_args: Dict,
        issues: List[str],
        original_result: Any
    ) -> Optional[Dict]:
        """
        HALLUCINATION RECOVERY: When fake data is detected, force real data fetching.

        Recovery strategies:
        1. If browser available -> navigate and extract real data
        2. If contact info fake -> use playwright_extract_page_fast on real URL
        3. If company name fake -> search for real company info

        Args:
            tool_name: Name of tool that returned fake data
            original_args: Arguments passed to original tool
            issues: List of detected issues
            original_result: Original (fake) result

        Returns:
            Recovered result dict or None
        """
        logger.warning(f"[HALLUCINATION RECOVERY] Attempting to get real data for {tool_name}")

        try:
            # Determine what kind of fake data was detected
            has_fake_email = any('email' in i.lower() for i in issues)
            has_fake_phone = any('phone' in i.lower() for i in issues)
            has_fake_name = any('name' in i.lower() for i in issues)
            has_fake_company = any('company' in i.lower() for i in issues)
            has_llm_hallucination = any('llm' in i.lower() or 'hallucination indicator' in i.lower() for i in issues)

            # Get URL from args or context
            url = original_args.get('url', '') if isinstance(original_args, dict) else ''

            # Recovery Strategy 1: Re-extract from real URL with browser
            if self.browser and url and (has_fake_email or has_fake_phone or has_fake_name):
                logger.info(f"[RECOVERY] Re-extracting contacts from {url} using browser")

                # Navigate first
                await self.mcp.call_tool('playwright_navigate', {'url': url})
                await asyncio.sleep(2)

                # Use fast extraction to get real contacts
                real_result = await asyncio.wait_for(
                    self.mcp.call_tool('playwright_extract_page_fast', {'url': url}),
                    timeout=30
                )

                # Validate the new result
                if self.hallucination_guard:
                    new_validation = self.hallucination_guard.validate_output(
                        real_result, source_tool='playwright_extract_page_fast', source_url=url
                    )
                else:
                    new_validation = type('obj', (object,), {'is_valid': True, 'issues': []})()

                if new_validation.is_valid:
                    logger.success(f"[RECOVERY] Got real data from {url}")
                    real_result['_recovery'] = 'hallucination_recovery_success'
                    return real_result
                else:
                    # Try contact pages
                    logger.warning(f"[RECOVERY] Still seeing issues, trying contact page...")
                    contact_urls = [
                        url.rstrip('/') + '/contact',
                        url.rstrip('/') + '/contact-us',
                        url.rstrip('/') + '/about',
                    ]
                    for contact_url in contact_urls:
                        try:
                            contact_result = await asyncio.wait_for(
                                self.mcp.call_tool('playwright_extract_page_fast', {'url': contact_url}),
                                timeout=20
                            )
                            if self.hallucination_guard:
                                contact_validation = self.hallucination_guard.validate_output(
                                    contact_result, source_tool='playwright_extract_page_fast', source_url=contact_url
                                )
                            else:
                                contact_validation = type('obj', (object,), {'is_valid': True, 'issues': []})()
                            if contact_validation.is_valid and contact_result.get('emails'):
                                logger.success(f"[RECOVERY] Found real contacts at {contact_url}")
                                contact_result['_recovery'] = 'contact_page_recovery'
                                return contact_result
                        except Exception as e:
                            logger.debug(f"Recovery attempt failed for {contact_url}: {e}")
                            continue

            # Recovery Strategy 2: LLM claimed it can't browse - force browser action
            if has_llm_hallucination and self.browser:
                logger.info(f"[RECOVERY] LLM hallucinated - forcing real browser action")

                if url:
                    await self.mcp.call_tool('playwright_navigate', {'url': url})
                    await asyncio.sleep(2)

                    # Get actual page content
                    real_content = await self.mcp.call_tool('playwright_snapshot', {})

                    if real_content and not real_content.get('error'):
                        real_content['_recovery'] = 'forced_browser_action'
                        logger.success(f"[RECOVERY] Forced real browser navigation to {url}")
                        return real_content

            # Recovery Strategy 3: Search for real company/contact info
            if has_fake_company and self.browser:
                company_name = None
                if isinstance(original_result, dict):
                    company_name = original_result.get('company') or original_result.get('company_name')

                if company_name and 'acme' not in company_name.lower() and 'test' not in company_name.lower():
                    logger.info(f"[RECOVERY] Searching for real company: {company_name}")
                    search_url = f"https://www.google.com/search?q={company_name.replace(' ', '+')}+contact"

                    await self.mcp.call_tool('playwright_navigate', {'url': search_url})
                    await asyncio.sleep(2)

                    search_result = await self.mcp.call_tool('playwright_snapshot', {})
                    if search_result:
                        search_result['_recovery'] = 'company_search_recovery'
                        return search_result

            # Recovery Strategy 4: Return error with guidance
            logger.warning(f"[RECOVERY] Could not recover real data - returning guidance")
            return {
                '_recovery': 'failed',
                '_guidance': 'FAKE DATA DETECTED - Please provide a real URL or use browser tools to fetch actual data',
                '_issues': issues,
                '_original_tool': tool_name
            }

        except Exception as e:
            logger.error(f"[RECOVERY] Hallucination recovery failed: {e}")
            return {
                '_recovery': 'error',
                '_error': str(e),
                '_issues': issues
            }

    async def _get_alternative_args(self, tool_name: str, args: Dict, error: str) -> Optional[Dict]:
        """
        Get alternative arguments after failure.

        Uses fast LLM to suggest alternatives, or falls back to memory.

        Args:
            tool_name: Tool name that failed
            args: Original arguments
            error: Error message

        Returns:
            Alternative arguments dict or None
        """
        # Try cached alternative first
        if self.session_state:
            memory_alt = self.session_state.get_memory_fallback(tool_name, args)
            if memory_alt:
                return memory_alt

        # Use fast model to suggest alternatives
        if not self.ollama_client or not self.fast_model:
            return None

        prompt = f"""Tool '{tool_name}' failed with args {args}.
Error: {error}

Suggest alternative arguments that might work. Return JSON only.
Example: {{"selector": ".alternative-class"}}"""

        try:
            response = self.ollama_client.generate(
                model=self.fast_model,
                prompt=prompt,
                options={'temperature': 0.3}
            )

            match = re.search(r'\{[^}]+\}', response.get('response', ''))
            if match:
                alt = json.loads(match.group(0))
                return {**args, **alt}

        except (json.JSONDecodeError, KeyError) as e:
            logger.debug(f"Alternative generation parse error: {e}")
        except Exception as e:
            logger.warning(f"Alternative generation failed: {e}")

        return None


def create_tool_executor(brain, visual_targeting_enabled: bool = True) -> ToolExecutor:
    """
    Factory function to create a ToolExecutor from an EnhancedBrain instance.

    This bridges the gap between the brain's components and the ToolExecutor,
    allowing lazy initialization after all brain components are set up.

    Args:
        brain: EnhancedBrain instance with all components initialized
        visual_targeting_enabled: Enable visual-first element targeting (default: True)

    Returns:
        Configured ToolExecutor instance
    """
    return ToolExecutor(
        mcp_client=brain.mcp,
        browser=brain.browser,
        stats=brain.stats,
        messages=brain.messages,
        hallucination_guard=brain.hallucination_guard,
        resource_monitor=brain.resource_monitor,
        resource_economy=brain.resource_economy,
        memory_arch=brain.memory_arch,
        cascading_recovery=brain.cascading_recovery,
        session_state=brain.session_state,
        ollama_client=brain.ollama_client,
        fast_model=brain.fast_model,
        visual_targeting_enabled=visual_targeting_enabled,
    )
