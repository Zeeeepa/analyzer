"""
Tool Execution and Recovery System for Eversale Agent.

Extracted from brain_enhanced_v2.py to modularize tool execution,
validation, retry logic, and recovery mechanisms.
"""

import asyncio
import json
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from loguru import logger
from rich.console import Console

from .smart_retry import get_retry_manager, get_escalation
from .self_healing_system import self_healing

console = Console()

# Try to import skill library
try:
    from .skill_library import SkillAwareAgent
    SKILL_LIBRARY_AVAILABLE = True
except ImportError:
    SKILL_LIBRARY_AVAILABLE = False


@dataclass
class ActionResult:
    """Result of a tool execution."""
    success: bool
    data: Any = None
    error: str = None
    screenshot: bytes = None


# Tool name corrections for common hallucinations
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
    # Contacts
    'find_contacts': 'playwright_find_contacts',
    'get_contacts': 'playwright_find_contacts',
    'extract_contacts': 'playwright_extract_entities',
    'get_emails': 'playwright_extract_entities',
}

# Human-like progress messages - no technical jargon
# Import sentient output for varied messages
try:
    from .sentient_output import get_tool_message
    SENTIENT_MESSAGES_AVAILABLE = True
except ImportError:
    SENTIENT_MESSAGES_AVAILABLE = False

TOOL_PROGRESS_MESSAGES = {
    'playwright_navigate': 'Opening that up...',
    'playwright_click': 'Got it...',
    'playwright_fill': 'Typing that in...',
    'playwright_extract_page_fast': 'Gathering the info...',
    'playwright_get_markdown': 'Reading through this...',
    'playwright_screenshot': 'Capturing this...',
    'playwright_snapshot': 'Looking at the page...',
    'playwright_extract_fb_ads': 'Finding the ads...',
    'playwright_extract_reddit': 'Reading the posts...',
    'playwright_scroll': 'Scrolling...',
    'playwright_wait': 'Waiting a moment...',
    'playwright_select': 'Selecting that...',
    'playwright_hover': 'Looking at this...',
}


class ToolExecutionMixin:
    """
    Mixin class providing tool execution and recovery capabilities.

    Requires the parent class to have:
    - mcp: MCP client with call_tool method
    - browser: Browser manager instance
    - stats: Dict for tracking statistics
    - messages: List for conversation messages
    - resource_economy: ResourceEconomy instance (optional)
    - resource_monitor: ResourceMonitor instance
    - hallucination_guard: HallucinationGuard instance (optional)
    - memory_arch: MemoryArchitecture instance (optional)
    - _notify_progress(message): Method to notify progress
    - _log_action(...): Method to log actions
    - _log_resource_issue(issue): Method to log resource issues
    - _record_successful_tool(name, args): Method to record successes
    - _record_failed_tool(name, args): Method to record failures
    - _capture_screenshot(name, result): Method to capture screenshots
    - _record_screenshot_bytes(screenshot, action_name): Method to record screenshots
    - _take_screenshot(): Method to take screenshots
    - _get_alternative_args(name, args, error): Method to get alternative args
    """

    def _validate_tool_calls(self, tool_calls: List[Dict]) -> List[Dict]:
        """Validate and correct tool calls - fix hallucinated tool names."""
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

    async def _act_parallel(self, tool_calls: List[Dict]) -> List[ActionResult]:
        """ACT phase: Execute tools in parallel when possible."""

        # Track navigated URLs to prevent loops (reset per task, not per call)
        if not hasattr(self, '_navigated_urls'):
            self._navigated_urls = set()
        if not hasattr(self, '_navigation_count'):
            self._navigation_count = {}

        # Group into parallelizable and sequential
        parallel = []
        sequential = []

        for tc in tool_calls:
            name = tc.get('function', {}).get('name', '')
            args = tc.get('function', {}).get('arguments', {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except (json.JSONDecodeError, ValueError):
                    args = {}

            # Check for duplicate navigation (loop detection)
            if 'navigate' in name:
                url = args.get('url', '')
                if url:
                    # Normalize URL for comparison
                    url_normalized = url.rstrip('/').lower()

                    # Track navigation count per URL
                    self._navigation_count[url_normalized] = self._navigation_count.get(url_normalized, 0) + 1

                    # If we've navigated to this URL more than twice, skip it
                    if self._navigation_count[url_normalized] > 2:
                        console.print(f"[yellow]⚠ Skipping repeated navigation to {url} (already visited {self._navigation_count[url_normalized]-1}x)[/yellow]")
                        continue  # Skip this tool call entirely

                    self._navigated_urls.add(url_normalized)

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
                *[self._execute_tool(tc) for tc in parallel],
                return_exceptions=True
            )
            results.extend(parallel_results)

        # Execute sequential tools
        for tc in sequential:
            result = await self._execute_tool(tc)
            results.append(result)

        return results

    async def _execute_tool(self, tool_call: Dict) -> ActionResult:
        """Execute single tool with retry logic."""

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
        name, args = await self._auto_correct_tool_call(name, args)

        cost, cost_reason = self.resource_economy.estimate(name, args if isinstance(args, dict) else {}) if self.resource_economy else (1.0, "default")
        issues = self.resource_monitor.check()
        if issues and cost >= 2.0:
            warning = f"Resource limit prevents calling {name}: {', '.join(issues)}"
            self._log_resource_issue(warning)
            return ActionResult(success=False, error=warning)
        self.stats['tool_calls'] += 1
        console.print(f"  [yellow]{name}[/yellow] [dim]{cost_reason}[/dim]")

        # Human-readable progress for UI (Claude Code style)
        progress_msg = TOOL_PROGRESS_MESSAGES.get(name, f'Running {name}')
        self._notify_progress(progress_msg)

        # CLAUDE CODE STYLE: Get DOM fingerprint before browser actions for proof-of-action
        before_fingerprint = None
        action_tools = {'playwright_click', 'playwright_fill', 'browser_click', 'browser_type'}
        if name in action_tools or name.startswith('browser_'):
            try:
                before_fingerprint = await asyncio.wait_for(
                    self.mcp.call_tool('browser_fingerprint', {}),
                    timeout=5
                )
            except Exception:
                pass  # Fingerprint is optional, don't fail the action

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

                # CLAUDE CODE STYLE: Verify action had effect
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
                    recovered_result = await self._recover_from_hallucination(
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
                        # Last resort: mark as suspicious and include recovery guidance
                        result = {
                            "warning": "FAKE DATA DETECTED - Recovery attempted but failed",
                            "issues": validation.issues,
                            "guidance": "Use browser tools (playwright_navigate, playwright_extract_page_fast) with a real URL to get actual data",
                            "original": result
                        }

                # Add to messages with tool_call_id for proper Ollama tool response matching
                # For markdown/extraction tools, preserve more content (up to 8000 chars) to ensure data isn't lost
                content_limit = 8000 if name in ['playwright_get_markdown', 'playwright_extract_page_fast', 'playwright_llm_extract'] else 2000
                tool_msg = {
                    'role': 'tool',
                    'content': json.dumps(result, default=str)[:content_limit],
                    'name': name
                }
                # Include tool_call_id if present (required for Ollama to match responses)
                if tool_call_id:
                    tool_msg['tool_call_id'] = tool_call_id
                self.messages.append(tool_msg)

                # Capture screenshot for vision (navigation/click/screenshot tools)
                screenshot = None
                if self.browser and ('navigate' in name or 'click' in name or 'screenshot' in name):
                    screenshot = await self._capture_screenshot(name, result)
                    if screenshot:
                        self._record_screenshot_bytes(screenshot, action_name=name)

                self._last_action_name = name
                self._record_successful_tool(name, args)
                self._log_action(name, args, True, result=result, attempt=attempt+1)

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

                # Record action for skill learning
                if SKILL_LIBRARY_AVAILABLE and hasattr(self, 'record_action_safe'):
                    self.record_action_safe(tool=name, arguments=args, result=result)

                return ActionResult(success=True, data=result, screenshot=screenshot)

            except asyncio.TimeoutError:
                error_msg = f"Tool {name} timed out after {tool_timeout}s"
                logger.warning(error_msg)
                self._record_failed_tool(name, args)
                self._log_action(name, args, False, error=error_msg, attempt=attempt+1)

                # Try fallback for timed-out tools
                fallback_result = await self._try_tool_fallback(name, args)
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

                self._record_failed_tool(name, args)
                self._log_action(name, args, False, error=str(e), attempt=attempt+1)

                # Record failure in self-healing system for learning
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

                # Smart retry: Record failure and get recommendation
                retry_mgr = get_retry_manager()
                retry_mgr.record_attempt(
                    action=name,
                    strategy=f"attempt_{attempt+1}",
                    args=args,
                    success=False,
                    error=str(e)
                )

                # Try self-healing before giving up
                if attempt == 0:  # Only on first failure
                    healing_result = await self._handle_error_with_healing(
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
                        # Self-healing succeeded, continue with original action
                        logger.info("[SELF-HEALING] Continuing after successful recovery")
                        # Don't break - continue with retry

                # Check if we're stuck in a loop
                is_loop, loop_reason = retry_mgr.is_stuck_in_loop()
                if is_loop:
                    logger.warning(f"Loop detected: {loop_reason}")
                    # Escalate to user
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

    async def _auto_correct_tool_call(self, name: str, args: Dict) -> Tuple[str, Dict]:
        """Auto-correct common model mistakes before execution.

        Common mistakes this fixes:
        1. smart_type with url param -> navigate first, then type
        2. playwright_fill with url param -> navigate first, then fill
        3. wait_and_click with url param -> navigate first, then click
        """
        if not isinstance(args, dict):
            return name, args

        url = args.get('url')

        # FIX 1: smart_type called with 'url' - model wants to navigate then type
        if name == 'smart_type' and url:
            logger.info(f"[AUTO-FIX] smart_type called with url - navigating to {url} first")
            try:
                # Navigate to the URL first
                await self.mcp.call_tool('playwright_navigate', {'url': url})
                await asyncio.sleep(1)  # Wait for page load
                # Remove url from args and continue with smart_type
                corrected_args = {k: v for k, v in args.items() if k != 'url'}
                if not corrected_args.get('selector') and not corrected_args.get('text'):
                    # If only url was provided, just return after navigation
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

    async def _try_tool_fallback(self, name: str, args: Dict) -> Optional[Dict]:
        """Try a simpler/faster fallback when a tool times out."""
        try:
            # Fallbacks for common timeout scenarios
            if name == 'playwright_navigate':
                url = args.get('url', '')
                if url:
                    # Try just getting markdown without full navigation
                    logger.info(f"Fallback: trying playwright_get_markdown for {url}")
                    return await asyncio.wait_for(
                        self.mcp.call_tool('playwright_get_markdown', {'url': url}),
                        timeout=15
                    )

            elif name == 'playwright_snapshot':
                # If snapshot times out, try getting just the title
                if self.browser and self.browser.page:
                    title = await self.browser.page.title()
                    return {'title': title, 'fallback': True, 'note': 'Full snapshot timed out'}

            elif name == 'playwright_get_text':
                selector = args.get('selector', '')
                # If get_text times out, return a helpful message
                return {'error': f'Element {selector} not found or page too slow', 'fallback': True}

            elif name == 'playwright_llm_extract':
                url = args.get('url', '')
                if url:
                    # Try simpler markdown extraction
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

    async def _handle_error_with_healing(
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

    async def _recover_from_hallucination(
        self,
        tool_name: str,
        original_args: Dict,
        issues: List[str],
        original_result: Any
    ) -> Optional[Dict]:
        """
        HALLUCINATION RECOVERY: When fake data is detected, force real data fetching.

        This method attempts to get REAL data when hallucination is detected:
        1. If browser available -> navigate and extract real data
        2. If search needed -> perform real web search
        3. If contact info fake -> use playwright_extract_page_fast on real URL
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

                # Navigate first to ensure we're on the page
                await self.mcp.call_tool('playwright_navigate', {'url': url})
                await asyncio.sleep(2)  # Let page load

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
                    # Still fake? Try contact page
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

                # If we have a URL context, go there and extract
                if url:
                    await self.mcp.call_tool('playwright_navigate', {'url': url})
                    await asyncio.sleep(2)

                    # Take screenshot to prove we browsed
                    screenshot = await self._take_screenshot()

                    # Get actual page content
                    real_content = await self.mcp.call_tool('playwright_snapshot', {})

                    if real_content and not real_content.get('error'):
                        real_content['_recovery'] = 'forced_browser_action'
                        real_content['_proof'] = 'screenshot_taken' if screenshot else 'no_screenshot'
                        logger.success(f"[RECOVERY] Forced real browser navigation to {url}")
                        return real_content

            # Recovery Strategy 3: Search for real company/contact info
            if has_fake_company and self.browser:
                # Extract company name from original result if possible
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

            # Recovery Strategy 4: If all else fails, return error with guidance
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


# Export ActionResult for use by other modules
__all__ = ['ToolExecutionMixin', 'ActionResult', 'TOOL_CORRECTIONS', 'TOOL_PROGRESS_MESSAGES']
