"""
Execution Coordinator - Tool execution with error handling and recovery.

This module contains the core tool execution logic extracted from brain_enhanced_v2.py
to improve code organization and maintainability.
"""

import asyncio
import ast
import json
import re
import urllib.parse
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from loguru import logger
from rich.console import Console

from .smart_retry import get_retry_manager, get_escalation
from .self_healing_system import self_healing

console = Console()


@dataclass
class ActionResult:
    """Result of a tool execution."""
    success: bool
    data: Any = None
    error: str = ""
    screenshot: Any = None


async def execute_tool(brain, tool_name: str, tool_args: Dict[str, Any]) -> ActionResult:
    """
    Execute a single tool call with error handling and recovery.

    This function handles the complete lifecycle of tool execution:
    - Resource cost estimation and checking
    - Progress notification
    - DOM fingerprinting for action verification
    - Tool execution with timeout
    - Action verification (for browser actions)
    - Hallucination detection and recovery
    - Screenshot capture for visual context
    - Smart retry logic with alternative strategies
    - Self-healing on failures
    - Memory and skill recording

    Args:
        brain: The brain instance containing MCP client, browser, and state
        tool_name: Name of the tool to execute (e.g., 'playwright_navigate')
        tool_args: Dictionary of arguments to pass to the tool

    Returns:
        ActionResult containing:
        - success: Whether execution succeeded
        - data: Tool result data (if successful)
        - error: Error message (if failed)
        - screenshot: Screenshot data (for navigation/click/screenshot tools)

    Example:
        result = await execute_tool(
            brain,
            'playwright_navigate',
            {'url': 'https://example.com'}
        )
        if result.success:
            print(f"Navigation succeeded: {result.data}")
        else:
            print(f"Navigation failed: {result.error}")
    """

    func = {'name': tool_name, 'arguments': tool_args}
    name = tool_name
    args = tool_args

    # Extract tool_call_id for proper Ollama tool response format
    tool_call_id = tool_args.get('_tool_call_id', '')
    if '_tool_call_id' in tool_args:
        args = {k: v for k, v in tool_args.items() if k != '_tool_call_id'}

    if isinstance(args, str):
        try:
            args = json.loads(args)
        except (json.JSONDecodeError, ValueError) as e:
            logger.debug(f"Could not parse args as JSON: {e}")
            args = {}

    # AUTO-CORRECTION: Fix common model mistakes before execution
    name, args = await brain._auto_correct_tool_call(name, args)

    cost, cost_reason = brain.resource_economy.estimate(name, args if isinstance(args, dict) else {}) if brain.resource_economy else (1.0, "default")
    issues = brain.resource_monitor.check()
    if issues and cost >= 2.0:
        warning = f"Resource limit prevents calling {name}: {', '.join(issues)}"
        brain._log_resource_issue(warning)
        return ActionResult(success=False, error=warning)
    brain.stats['tool_calls'] += 1
    console.print(f"  [yellow]{name}[/yellow] [dim]{cost_reason}[/dim]")

    # Human-readable progress for UI (Claude Code style)
    tool_messages = {
        'playwright_navigate': 'Navigating to page',
        'playwright_click': 'Clicking element',
        'playwright_fill': 'Filling form',
        'playwright_extract_page_fast': 'Extracting page data',
        'playwright_get_markdown': 'Reading page content',
        'playwright_screenshot': 'Taking screenshot',
        'playwright_snapshot': 'Getting page structure',
        'playwright_extract_fb_ads': 'Extracting ads',
        'playwright_extract_reddit': 'Extracting posts',
    }
    progress_msg = tool_messages.get(name, f'Running {name}')
    brain._notify_progress(progress_msg)

    # CLAUDE CODE STYLE: Get DOM fingerprint before browser actions for proof-of-action
    before_fingerprint = None
    action_tools = {'playwright_click', 'playwright_fill', 'browser_click', 'browser_type'}
    if name in action_tools or name.startswith('browser_'):
        try:
            before_fingerprint = await asyncio.wait_for(
                brain.mcp.call_tool('browser_fingerprint', {}),
                timeout=5
            )
        except Exception as e:
            pass  # Fingerprint is optional, don't fail the action

    # Try up to 3 times with different approaches
    for attempt in range(3):
        try:
            # Add timeout to prevent hanging - 30 seconds for browser ops, 60 for others
            tool_timeout = 30 if 'playwright' in name or 'browser_' in name else 60
            result = await asyncio.wait_for(
                brain.mcp.call_tool(name, args),
                timeout=tool_timeout
            )

            # CLAUDE CODE STYLE: Verify action had effect
            if before_fingerprint and before_fingerprint.get('success'):
                try:
                    verification = await asyncio.wait_for(
                        brain.mcp.call_tool('browser_verify_action', {
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
                except Exception as e:
                    pass  # Verification is optional

            # HALLUCINATION CHECK: Validate tool output for fake/placeholder data
            url_arg = args.get('url', '') if isinstance(args, dict) else ''
            if brain.hallucination_guard:
                validation = brain.hallucination_guard.validate_output(
                    result,
                    source_tool=name,
                    source_url=url_arg
                )
            else:
                validation = type('obj', (object,), {'is_valid': True, 'issues': []})()
            if not validation.is_valid:
                logger.warning(f"HALLUCINATION DETECTED in {name}: {validation.issues}")

                # RECOVERY: Attempt to get real data instead of fake
                recovered_result = await brain._recover_from_hallucination(
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
            tool_msg = {
                'role': 'tool',
                'content': json.dumps(result, default=str)[:2000],
                'name': name
            }
            # Include tool_call_id if present (required for Ollama to match responses)
            if tool_call_id:
                tool_msg['tool_call_id'] = tool_call_id
            brain.messages.append(tool_msg)

            # Capture screenshot for vision (navigation/click/screenshot tools)
            screenshot = None
            if brain.browser and ('navigate' in name or 'click' in name or 'screenshot' in name):
                screenshot = await brain._capture_screenshot(name, result)
                if screenshot:
                    brain._record_screenshot_bytes(screenshot, action_name=name)

            brain._last_action_name = name
            brain._record_successful_tool(name, args)
            brain._log_action(name, args, True, result=result, attempt=attempt+1)

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
            if brain.memory_arch:
                try:
                    observation = json.dumps(result, default=str)[:500] if result else "Success"
                    reasoning = brain.messages[-1].get('content', '') if brain.messages else ''
                    brain.memory_arch.add_step(
                        action=name,
                        observation=observation,
                        reasoning=reasoning[:200],
                        tool_calls=[{'name': name, 'arguments': args}],
                        success=True
                    )
                except Exception as e:
                    logger.debug(f"Memory step recording failed: {e}")

            # Record action for skill learning
            if hasattr(brain, 'record_action'):
                try:
                    brain.record_action(tool=name, arguments=args, result=result)
                except Exception as e:
                    logger.debug(f"Skill action recording failed: {e}")

            return ActionResult(success=True, data=result, screenshot=screenshot)

        except asyncio.TimeoutError:
            error_msg = f"Tool {name} timed out after {tool_timeout}s"
            logger.warning(error_msg)
            brain._record_failed_tool(name, args)
            brain._log_action(name, args, False, error=error_msg, attempt=attempt+1)

            # Try fallback for timed-out tools
            fallback_result = await brain._try_tool_fallback(name, args)
            if fallback_result:
                fallback_msg = {
                    'role': 'tool',
                    'content': json.dumps(fallback_result, default=str)[:2000],
                    'name': name
                }
                if tool_call_id:
                    fallback_msg['tool_call_id'] = tool_call_id
                brain.messages.append(fallback_msg)
                return ActionResult(success=True, data=fallback_result)

            error_tool_msg = {
                'role': 'tool',
                'content': json.dumps({'error': error_msg}),
                'name': name
            }
            if tool_call_id:
                error_tool_msg['tool_call_id'] = tool_call_id
            brain.messages.append(error_tool_msg)
            return ActionResult(success=False, error=error_msg)

        except Exception as e:
            logger.warning(f"Tool {name} attempt {attempt+1} failed: {e}")

            brain._record_failed_tool(name, args)
            brain._log_action(name, args, False, error=str(e), attempt=attempt+1)

            # Record failure in self-healing system for learning
            try:
                self_healing.record_failure(
                    error=str(e),
                    context={
                        'function': name,
                        'arguments': args,
                        'url': brain.browser.page.url if brain.browser and brain.browser.page else '',
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
                healing_result = await brain._handle_error_with_healing(
                    error=e,
                    context={
                        'function': name,
                        'arguments': args,
                        'url': brain.browser.page.url if brain.browser and brain.browser.page else '',
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
                    brain.messages.append(skip_msg)
                    return ActionResult(success=False, error=f"Skipped: {loop_reason}")

            if attempt < 2:
                # Get smart recommendation for next strategy
                rec = retry_mgr.get_recommendation(name, args, str(e))
                if rec['action'] == 'retry_with_strategy':
                    logger.info(f"Smart retry: {rec.get('reason', 'trying alternative')}")

                # Try alternative approach
                args = await brain._get_alternative_args(name, args, str(e))
                if not args:
                    break
                brain.stats['retries'] += 1
            else:
                final_error_msg = {
                    'role': 'tool',
                    'content': json.dumps({'error': str(e)}),
                    'name': name
                }
                if tool_call_id:
                    final_error_msg['tool_call_id'] = tool_call_id
                brain.messages.append(final_error_msg)
                return ActionResult(success=False, error=str(e))

    return ActionResult(success=False, error="Max retries exceeded")


async def try_complex_workflow(brain, prompt: str) -> Optional[str]:
    """
    Handle complex multi-step workflows by breaking them into subtasks.
    Detects patterns like "do X, then Y, then Z" and executes sequentially.

    Delegate to workflow_handlers for complex workflow routing.
    """
    from .workflow_handlers import try_complex_workflow as _try_complex_workflow
    return await _try_complex_workflow(brain, prompt)


async def execute_page_loop(brain, base_url: str, start: int, end: int, prompt: str) -> str:
    """
    Execute paginated extraction loop across multiple pages.

    Auto-detects pagination patterns and works with any e-commerce/content site.
    Example demo sites (for testing only): books.toscrape.com, quotes.toscrape.com

    Delegate to workflow_handlers for page loop execution.

    Args:
        brain: The brain instance containing MCP client and tools
        base_url: Base URL to paginate through
        start: Starting page number
        end: Ending page number
        prompt: User prompt for context (used for filtering results)

    Returns:
        Summary string with extracted data and statistics
    """
    from .workflow_handlers import execute_page_loop as _execute_page_loop
    return await _execute_page_loop(brain, base_url, start, end, prompt)


# ============================================================================
# Web Shortcuts Delegation
# ============================================================================

async def try_web_shortcuts(brain, prompt: str) -> Optional[str]:
    """
    Delegate to web_shortcuts module for fast-path handling.

    This is a thin wrapper that delegates to the extracted web_shortcuts module.
    The actual implementation contains ~390 lines of fast-path logic for:
    - Math calculations
    - Simple questions
    - URL validation
    - Search queries
    - Wikipedia lookups
    - Site mapping
    - Adaptive crawling
    - Q&A from pages
    - Entity extraction
    - Structured data extraction
    - Markdown summaries

    Args:
        brain: The brain instance containing MCP client, browser, and state
        prompt: The user's prompt/question

    Returns:
        Optional[str]: The result summary if a shortcut was triggered, None otherwise
    """
    from .web_shortcuts import try_web_shortcuts as _try_web_shortcuts
    return await _try_web_shortcuts(brain, prompt)


# ============================================================================
# Tool Dispatch Functions
# ============================================================================

def validate_tool_calls(brain, tool_calls: List[Dict]) -> List[Dict]:
    """
    Validate and correct tool calls - fix hallucinated tool names.

    This function maps common hallucinated/incorrect tool names to their
    correct equivalents, preventing the LLM from calling non-existent tools.

    Args:
        brain: The brain instance containing MCP client
        tool_calls: List of tool call dictionaries from LLM

    Returns:
        List of corrected tool call dictionaries
    """
    if not tool_calls:
        return tool_calls

    # Map of common hallucinated/wrong tool names to correct ones
    tool_corrections = {
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

    available_tools = set(brain.mcp.tools.keys()) if hasattr(brain.mcp, 'tools') else set()

    corrected = []
    for tc in tool_calls:
        func = tc.get('function', {})
        name = func.get('name', '')

        # Check if tool exists
        if name not in available_tools:
            # Try to correct the name
            corrected_name = tool_corrections.get(name.lower())
            if corrected_name and corrected_name in available_tools:
                logger.info(f"Corrected tool name: {name} -> {corrected_name}")
                func['name'] = corrected_name
            elif name.lower() in tool_corrections:
                # Even if not in available_tools, use the correction
                corrected_name = tool_corrections[name.lower()]
                logger.info(f"Corrected tool name: {name} -> {corrected_name}")
                func['name'] = corrected_name
            else:
                # Skip invalid tools entirely
                logger.warning(f"Skipping unknown tool: {name}")
                continue

        corrected.append(tc)

    return corrected


async def act_parallel(brain, tool_calls: List[Dict]) -> List[ActionResult]:
    """
    ACT phase: Execute tools in parallel when possible.

    Groups tool calls into parallelizable and sequential categories.
    Navigation and click actions must be sequential; others can run in parallel.

    Args:
        brain: The brain instance containing MCP client and state
        tool_calls: List of tool call dictionaries

    Returns:
        List of ActionResult objects from all tool executions
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
            *[execute_tool(brain, tc.get('function', {}).get('name', ''),
                          tc.get('function', {}).get('arguments', {})) for tc in parallel],
            return_exceptions=True
        )
        for r in parallel_results:
            if isinstance(r, Exception):
                results.append(ActionResult(success=False, error=str(r)))
            else:
                results.append(r)

    # Execute sequential tools
    for tc in sequential:
        func = tc.get('function', {})
        result = await execute_tool(brain, func.get('name', ''), func.get('arguments', {}))
        results.append(result)

    return results


async def auto_correct_tool_call(brain, name: str, args: Dict) -> tuple:
    """
    Auto-correct common model mistakes before execution.

    Common mistakes this fixes:
    1. smart_type with url param -> navigate first, then type
    2. playwright_fill with url param -> navigate first, then fill
    3. wait_and_click with url param -> navigate first, then click
    4. extract_table with url param -> navigate first, then extract

    Args:
        brain: The brain instance containing MCP client
        name: Tool name
        args: Tool arguments dictionary

    Returns:
        Tuple of (corrected_name, corrected_args)
    """
    if not isinstance(args, dict):
        return name, args

    url = args.get('url')

    # FIX 1: smart_type called with 'url' - model wants to navigate then type
    if name == 'smart_type' and url:
        logger.info(f"[AUTO-FIX] smart_type called with url - navigating to {url} first")
        try:
            await brain.mcp.call_tool('playwright_navigate', {'url': url})
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
            await brain.mcp.call_tool('playwright_navigate', {'url': url})
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
            await brain.mcp.call_tool('playwright_navigate', {'url': url})
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
            await brain.mcp.call_tool('playwright_navigate', {'url': url})
            await asyncio.sleep(1)
            corrected_args = {k: v for k, v in args.items() if k != 'url'}
            return name, corrected_args
        except Exception as e:
            logger.warning(f"[AUTO-FIX] Navigation failed: {e}")
            return name, args

    return name, args


async def try_tool_fallback(brain, name: str, args: Dict) -> Optional[Dict]:
    """
    Try a simpler/faster fallback when a tool times out.

    Args:
        brain: The brain instance containing MCP client and browser
        name: Tool name that failed
        args: Original tool arguments

    Returns:
        Fallback result dictionary or None if no fallback available
    """
    try:
        if name == 'playwright_navigate':
            url = args.get('url', '')
            if url:
                logger.info(f"Fallback: trying playwright_get_markdown for {url}")
                return await asyncio.wait_for(
                    brain.mcp.call_tool('playwright_get_markdown', {'url': url}),
                    timeout=15
                )

        elif name == 'playwright_snapshot':
            if brain.browser and brain.browser.page:
                title = await brain.browser.page.title()
                return {'title': title, 'fallback': True, 'note': 'Full snapshot timed out'}

        elif name == 'playwright_get_text':
            selector = args.get('selector', '')
            return {'error': f'Element {selector} not found or page too slow', 'fallback': True}

        elif name == 'playwright_llm_extract':
            url = args.get('url', '')
            if url:
                logger.info(f"Fallback: trying playwright_get_markdown for {url}")
                result = await asyncio.wait_for(
                    brain.mcp.call_tool('playwright_get_markdown', {'url': url}),
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


async def handle_error_with_healing(brain, error: Exception, context: Dict[str, Any], attempt: int = 1) -> Optional[Dict[str, Any]]:
    """
    Use self-healing system to recover from errors.

    Args:
        brain: The brain instance
        error: The exception that occurred
        context: Context dict with function name, args, etc.
        attempt: Current attempt number

    Returns:
        Strategy dict if recovery possible, None otherwise
    """
    try:
        strategy = await self_healing.analyze_failure(
            error=error,
            context=context,
            attempt_number=attempt
        )

        if not strategy:
            return None

        logger.info(f"[SELF-HEALING] Applying strategy: {strategy.get('action', 'unknown')}")

        result = await self_healing.execute_strategy(
            strategy=strategy,
            playwright_client=brain.browser
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
    brain,
    tool_name: str,
    original_args: Dict,
    issues: List[str],
    original_result: Any
) -> Optional[Dict]:
    """
    HALLUCINATION RECOVERY: When fake data is detected, force real data fetching.

    Recovery strategies:
    1. If browser available → navigate and extract real data
    2. If search needed → perform real web search
    3. If contact info fake → use playwright_extract_page_fast on real URL

    Args:
        brain: The brain instance
        tool_name: Name of the tool that produced hallucinated output
        original_args: Original arguments passed to the tool
        issues: List of detected hallucination issues
        original_result: The original (hallucinated) result

    Returns:
        Recovered real data dictionary or None if recovery failed
    """
    logger.warning(f"[HALLUCINATION RECOVERY] Attempting to get real data for {tool_name}")

    try:
        has_fake_email = any('email' in i.lower() for i in issues)
        has_fake_phone = any('phone' in i.lower() for i in issues)
        has_fake_name = any('name' in i.lower() for i in issues)
        has_fake_company = any('company' in i.lower() for i in issues)
        has_llm_hallucination = any('llm' in i.lower() or 'hallucination indicator' in i.lower() for i in issues)

        url = original_args.get('url', '') if isinstance(original_args, dict) else ''

        # Recovery Strategy 1: Re-extract from real URL with browser
        if brain.browser and url and (has_fake_email or has_fake_phone or has_fake_name):
            logger.info(f"[RECOVERY] Re-extracting contacts from {url} using browser")

            await brain.mcp.call_tool('playwright_navigate', {'url': url})
            await asyncio.sleep(2)

            real_result = await asyncio.wait_for(
                brain.mcp.call_tool('playwright_extract_page_fast', {'url': url}),
                timeout=30
            )

            if brain.hallucination_guard:
                new_validation = brain.hallucination_guard.validate_output(
                    real_result, source_tool='playwright_extract_page_fast', source_url=url
                )
            else:
                new_validation = type('obj', (object,), {'is_valid': True, 'issues': []})()

            if new_validation.is_valid:
                logger.success(f"[RECOVERY] Got real data from {url}")
                real_result['_recovery'] = 'hallucination_recovery_success'
                return real_result
            else:
                logger.warning(f"[RECOVERY] Still seeing issues, trying contact page...")
                contact_urls = [
                    url.rstrip('/') + '/contact',
                    url.rstrip('/') + '/contact-us',
                    url.rstrip('/') + '/about',
                ]
                for contact_url in contact_urls:
                    try:
                        contact_result = await asyncio.wait_for(
                            brain.mcp.call_tool('playwright_extract_page_fast', {'url': contact_url}),
                            timeout=20
                        )
                        if brain.hallucination_guard:
                            contact_validation = brain.hallucination_guard.validate_output(
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
        if has_llm_hallucination and brain.browser:
            logger.info(f"[RECOVERY] LLM hallucinated - forcing real browser action")

            if url:
                await brain.mcp.call_tool('playwright_navigate', {'url': url})
                await asyncio.sleep(2)

                screenshot = await brain._take_screenshot()
                real_content = await brain.mcp.call_tool('playwright_snapshot', {})

                if real_content and not real_content.get('error'):
                    real_content['_recovery'] = 'forced_browser_action'
                    real_content['_proof'] = 'screenshot_taken' if screenshot else 'no_screenshot'
                    logger.success(f"[RECOVERY] Forced real browser navigation to {url}")
                    return real_content

        # Recovery Strategy 3: Search for real company/contact info
        if has_fake_company and brain.browser:
            company_name = None
            if isinstance(original_result, dict):
                company_name = original_result.get('company') or original_result.get('company_name')

            if company_name and 'acme' not in company_name.lower() and 'test' not in company_name.lower():
                logger.info(f"[RECOVERY] Searching for real company: {company_name}")
                search_url = f"https://www.google.com/search?q={company_name.replace(' ', '+')}+contact"

                await brain.mcp.call_tool('playwright_navigate', {'url': search_url})
                await asyncio.sleep(2)

                search_result = await brain.mcp.call_tool('playwright_snapshot', {})
                if search_result:
                    search_result['_recovery'] = 'company_search_recovery'
                    return search_result

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


async def get_alternative_args(brain, tool_name: str, args: Dict, error: str) -> Optional[Dict]:
    """
    Get alternative arguments after failure using fast LLM model.

    Args:
        brain: The brain instance
        tool_name: Name of the failed tool
        args: Original arguments that failed
        error: Error message from failure

    Returns:
        Alternative arguments dictionary or None if no alternative found
    """
    prompt = f"""Tool '{tool_name}' failed with args {args}.
Error: {error}

Suggest alternative arguments that might work. Return JSON only.
Example: {{"selector": ".alternative-class"}}"""

    # Try cached alternative first
    memory_alt = brain._get_memory_fallback(tool_name, args)
    if memory_alt:
        return memory_alt

    try:
        response = brain.ollama_client.generate(
            model=brain.fast_model,
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


async def call_direct_tool(brain, name: str, args: Dict[str, Any], timeout: int = 45) -> Optional[Dict[str, Any]]:
    """
    Simple tool caller for fast-path web shortcuts with timeout and cascading recovery.

    Args:
        brain: The brain instance
        name: Tool name to call
        args: Tool arguments
        timeout: Timeout in seconds (default 45)

    Returns:
        Tool result dictionary or None on failure
    """
    try:
        if not await brain._ensure_browser_health():
            return None
    except Exception as e:
        logger.debug(f"Browser health check before {name} failed: {e}")

    try:
        brain.stats['tool_calls'] += 1
        result = await asyncio.wait_for(
            brain.mcp.call_tool(name, args),
            timeout=timeout
        )
        brain._log_action(name, args, True, result=result)
        try:
            brain.messages.append({
                'role': 'tool',
                'name': name,
                'content': json.dumps(result, default=str)[:2000]
            })
        except Exception:
            pass
        return result
    except asyncio.TimeoutError as e:
        logger.warning(f"{name} timed out after {timeout}s")
        brain._log_action(name, args, False, error=f"Timeout after {timeout}s")

        if brain.cascading_recovery and name.startswith('playwright_'):
            recovery_result = await brain._attempt_cascading_recovery(name, args, e)
            if recovery_result:
                return recovery_result

        return None
    except Exception as e:
        logger.warning(f"{name} failed: {e}")
        brain._log_action(name, args, False, error=str(e))

        if brain.cascading_recovery and name.startswith('playwright_'):
            recovery_result = await brain._attempt_cascading_recovery(name, args, e)
            if recovery_result:
                return recovery_result

        return None
