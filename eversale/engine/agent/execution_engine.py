"""
Execution Engine - Handles tool execution logic extracted from brain_enhanced_v2.py

Responsibilities:
- Execute tools (single and parallel)
- Auto-correct common tool call mistakes
- Retry with fallbacks on failure
- Record actions for skill learning
- Handle hallucination recovery
"""

import asyncio
import json
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from loguru import logger
from rich.console import Console

console = Console()


@dataclass
class ActionResult:
    """Result of executing a tool action."""
    success: bool
    data: Optional[Dict] = None
    error: Optional[str] = None
    screenshot: Optional[bytes] = None


class ExecutionEngine:
    """
    Handles tool execution - running tools, retrying on failure, auto-correction.

    Extracted from EnhancedBrain to separate execution concerns from reasoning.
    """

    # Tool progress messages for UI
    TOOL_MESSAGES = {
        'playwright_navigate': 'Navigating to page',
        'playwright_click': 'Clicking element',
        'playwright_fill': 'Filling form',
        'playwright_extract_page_fast': 'Extracting page data',
        'playwright_get_markdown': 'Reading page content',
        'playwright_screenshot': 'Taking screenshot',
        'playwright_snapshot': 'Getting page structure',
        'playwright_extract_fb_ads': 'Extracting ads',
        'playwright_extract_reddit': 'Extracting posts',
        'playwright_batch_extract': 'Batch extracting contacts',
        'playwright_find_contacts': 'Finding contact information',
        'playwright_get_text': 'Extracting text content',
        'playwright_export_code': 'Exporting workflow code',
    }

    # Tools that modify DOM and should run sequentially
    SEQUENTIAL_TOOLS = {'navigate', 'click', 'fill'}

    def __init__(
        self,
        mcp,
        browser=None,
        hallucination_guard=None,
        resource_economy=None,
        resource_monitor=None,
        memory_arch=None,
        stats: Optional[Dict] = None,
        progress_callback=None
    ):
        self.mcp = mcp
        self.browser = browser
        self.hallucination_guard = hallucination_guard
        self.resource_economy = resource_economy
        self.resource_monitor = resource_monitor
        self.memory_arch = memory_arch
        self.stats = stats or {}
        self._progress_callback = progress_callback
        self.messages = []  # Will be set by parent

    def set_messages(self, messages: List[Dict]):
        """Set reference to message history for adding tool responses."""
        self.messages = messages

    async def execute_parallel(self, tool_calls: List[Dict]) -> List[ActionResult]:
        """
        Execute tools in parallel when possible, sequential when needed.

        Navigation and click actions run sequentially (order matters).
        Other tools can run in parallel for speed.
        """
        parallel = []
        sequential = []

        for tc in tool_calls:
            name = tc.get('function', {}).get('name', '')
            is_sequential = any(s in name for s in self.SEQUENTIAL_TOOLS)
            if is_sequential:
                sequential.append(tc)
            else:
                parallel.append(tc)

        results = []

        # Execute sequential tools first (order matters for navigation)
        for tc in sequential:
            result = await self.execute_single(tc)
            results.append(result)

        # Execute parallel tools
        if parallel:
            console.print(f"[yellow]Executing {len(parallel)} tools in parallel[/yellow]")
            parallel_results = await asyncio.gather(
                *[self.execute_single(tc) for tc in parallel],
                return_exceptions=True
            )
            for r in parallel_results:
                if isinstance(r, Exception):
                    results.append(ActionResult(success=False, error=str(r)))
                else:
                    results.append(r)

        return results

    async def execute_single(self, tool_call: Dict, max_retries: int = 3) -> ActionResult:
        """
        Execute a single tool with retry logic.

        Args:
            tool_call: Tool call dict with function name and arguments
            max_retries: Maximum retry attempts

        Returns:
            ActionResult with success/failure and data
        """
        func = tool_call.get('function', {})
        name = func.get('name', '')
        args = func.get('arguments', {})
        tool_call_id = tool_call.get('id', '')

        # Parse args if string
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except (json.JSONDecodeError, ValueError):
                args = {}

        # Auto-correct common mistakes
        name, args = await self.auto_correct(name, args)

        # Check resource limits
        if self.resource_economy and self.resource_monitor:
            cost, cost_reason = self.resource_economy.estimate(name, args if isinstance(args, dict) else {})
            issues = self.resource_monitor.check()
            if issues and cost >= 2.0:
                warning = f"Resource limit prevents calling {name}: {', '.join(issues)}"
                logger.warning(warning)
                return ActionResult(success=False, error=warning)
            console.print(f"  [yellow]{name}[/yellow] [dim]{cost_reason}[/dim]")
        else:
            console.print(f"  [yellow]{name}[/yellow]")

        self.stats['tool_calls'] = self.stats.get('tool_calls', 0) + 1

        # Progress notification
        progress_msg = self.TOOL_MESSAGES.get(name, f'Running {name}')
        self._notify_progress(progress_msg)

        # Retry loop
        last_error = None
        for attempt in range(max_retries):
            try:
                tool_timeout = 30 if 'playwright' in name or 'browser_' in name else 60
                result = await asyncio.wait_for(
                    self.mcp.call_tool(name, args),
                    timeout=tool_timeout
                )

                # Validate for hallucinations
                result = await self._validate_result(name, args, result)

                # Add to messages
                self._add_tool_message(name, result, tool_call_id)

                # Record success
                self._record_action(name, args, result, True, attempt)

                return ActionResult(success=True, data=result)

            except asyncio.TimeoutError:
                error_msg = f"Tool {name} timed out after {tool_timeout}s"
                logger.warning(error_msg)

                # Try fallback
                fallback = await self._try_fallback(name, args)
                if fallback:
                    self._add_tool_message(name, fallback, tool_call_id)
                    self._record_action(name, args, fallback, True, attempt)
                    return ActionResult(success=True, data=fallback)

                self._add_tool_message(name, {'error': error_msg}, tool_call_id)
                self._record_action(name, args, {'error': error_msg}, False, attempt)
                return ActionResult(success=False, error=error_msg)

            except Exception as e:
                last_error = str(e)
                logger.warning(f"Tool {name} attempt {attempt+1}/{max_retries} failed: {e}")

                if attempt < max_retries - 1:
                    # Get alternative args for retry
                    new_args = await self._get_alternative_args(name, args, last_error)
                    if new_args:
                        logger.info(f"Retrying with alternative arguments")
                        args = new_args
                        self.stats['retries'] = self.stats.get('retries', 0) + 1
                        await asyncio.sleep(1)  # Brief delay before retry
                        continue

                    # Wait before retry
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    self.stats['retries'] = self.stats.get('retries', 0) + 1
                else:
                    # Final attempt failed
                    self._add_tool_message(name, {'error': last_error}, tool_call_id)
                    self._record_action(name, args, {'error': last_error}, False, attempt)

        return ActionResult(success=False, error=last_error or "Max retries exceeded")

    async def auto_correct(self, name: str, args: Dict) -> Tuple[str, Dict]:
        """
        Auto-correct common model mistakes before execution.

        Fixes cases where model passes URL to tools that don't accept it -
        navigates first, then calls the tool.
        """
        if not isinstance(args, dict):
            return name, args

        url = args.get('url')

        # Tools that shouldn't have URL param - navigate first
        tools_needing_nav = ['smart_type', 'playwright_fill', 'wait_and_click', 'extract_table', 'playwright_click']

        if name in tools_needing_nav and url:
            logger.info(f"[AUTO-FIX] {name} called with url - navigating to {url} first")
            try:
                await self.mcp.call_tool('playwright_navigate', {'url': url})
                await asyncio.sleep(2)  # Wait for page load
                corrected_args = {k: v for k, v in args.items() if k != 'url'}
                return name, corrected_args
            except Exception as e:
                logger.warning(f"[AUTO-FIX] Navigation failed: {e}")

        # Fix common argument mistakes
        if name == 'playwright_navigate':
            # Ensure URL has protocol
            if url and not url.startswith(('http://', 'https://')):
                args['url'] = f'https://{url}'
                logger.info(f"[AUTO-FIX] Added https:// to URL: {args['url']}")

        return name, args

    async def _validate_result(self, name: str, args: Dict, result: Dict) -> Dict:
        """Validate result for hallucinations and attempt recovery."""
        if not self.hallucination_guard:
            return result

        url_arg = args.get('url', '') if isinstance(args, dict) else ''
        validation = self.hallucination_guard.validate_output(
            result,
            source_tool=name,
            source_url=url_arg
        )

        if not validation.is_valid:
            logger.warning(f"HALLUCINATION DETECTED in {name}: {validation.issues}")

            # Attempt recovery
            recovered = await self._recover_from_hallucination(name, args, validation.issues, result)
            if recovered and recovered.get('_recovery') not in ['failed', 'error']:
                logger.success("[HALLUCINATION RECOVERY] Recovered real data")
                return recovered
            elif hasattr(validation, 'cleaned_data') and validation.cleaned_data:
                result = validation.cleaned_data
                result['_note'] = 'Fake data removed'
            else:
                result = {
                    "warning": "FAKE DATA DETECTED",
                    "issues": validation.issues,
                    "guidance": "Use browser tools with real URL",
                    "original": result
                }

        return result

    async def _recover_from_hallucination(
        self,
        tool_name: str,
        original_args: Dict,
        issues: List[str],
        original_result: Dict
    ) -> Optional[Dict]:
        """Attempt to recover real data after detecting hallucination."""
        try:
            # Try getting real page content
            if 'extract' in tool_name or 'get' in tool_name:
                url = original_args.get('url', '')
                if url:
                    logger.info(f"Attempting hallucination recovery for {url}")
                    real_result = await asyncio.wait_for(
                        self.mcp.call_tool('playwright_get_markdown', {'url': url}),
                        timeout=30
                    )
                    if real_result and real_result.get('content'):
                        real_result['_recovery'] = 'success'
                        return real_result
        except Exception as e:
            logger.debug(f"Hallucination recovery failed: {e}")

        return {'_recovery': 'failed', '_issues': issues}

    async def _try_fallback(self, name: str, args: Dict) -> Optional[Dict]:
        """Try fallback when tool times out."""
        try:
            if name == 'playwright_navigate':
                url = args.get('url', '')
                if url:
                    logger.info(f"Fallback: trying playwright_get_markdown for {url}")
                    return await asyncio.wait_for(
                        self.mcp.call_tool('playwright_get_markdown', {'url': url}),
                        timeout=30
                    )
            elif name == 'playwright_extract_page_fast':
                url = args.get('url', '')
                if url:
                    logger.info(f"Fallback: trying playwright_get_markdown for {url}")
                    return await asyncio.wait_for(
                        self.mcp.call_tool('playwright_get_markdown', {'url': url}),
                        timeout=30
                    )
        except Exception as e:
            logger.debug(f"Fallback failed: {e}")
        return None

    async def _get_alternative_args(self, name: str, args: Dict, error: str) -> Optional[Dict]:
        """Get alternative arguments for retry based on error."""
        # For selector-based tools, try broader selectors
        if 'selector' in args and ('not found' in error.lower() or 'timeout' in error.lower()):
            selector = args['selector']
            alternatives = []

            # Try variations
            if selector.startswith('.'):
                # Class selector - try partial match
                class_name = selector[1:]
                alternatives.append(f"[class*='{class_name}']")
            elif selector.startswith('#'):
                # ID selector - try data attribute
                id_name = selector[1:]
                alternatives.append(f"[id*='{id_name}']")

            # Try tag name if available
            if ' ' in selector:
                alternatives.append(selector.split()[0])

            # Last resort - common fallbacks
            alternatives.extend(['button', 'a', 'input'])

            for alt in alternatives:
                if alt != selector:
                    new_args = args.copy()
                    new_args['selector'] = alt
                    logger.info(f"Trying alternative selector: {alt}")
                    return new_args

        # For URL-based tools, try adding/removing www
        if 'url' in args and 'connection' in error.lower():
            url = args['url']
            if 'www.' in url:
                new_url = url.replace('www.', '')
            else:
                domain_start = url.find('://') + 3
                new_url = url[:domain_start] + 'www.' + url[domain_start:]

            new_args = args.copy()
            new_args['url'] = new_url
            logger.info(f"Trying alternative URL: {new_url}")
            return new_args

        return None

    def _add_tool_message(self, name: str, result: Dict, tool_call_id: str = ""):
        """Add tool result to message history."""
        # Truncate large results to prevent memory issues
        content = json.dumps(result, default=str)
        if len(content) > 2000:
            content = content[:2000] + "... [truncated]"

        tool_msg = {
            'role': 'tool',
            'content': content,
            'name': name
        }
        if tool_call_id:
            tool_msg['tool_call_id'] = tool_call_id

        self.messages.append(tool_msg)

    def _record_action(self, name: str, args: Dict, result: Dict, success: bool, attempt: int):
        """Record action for learning/skill building."""
        if self.memory_arch:
            try:
                observation = json.dumps(result, default=str)[:500] if result else "Success"
                self.memory_arch.add_step(
                    action=name,
                    observation=observation,
                    reasoning="",
                    tool_calls=[{'name': name, 'arguments': args}],
                    success=success
                )
            except Exception as e:
                logger.debug(f"Memory recording failed: {e}")

    def _notify_progress(self, message: str):
        """Notify UI of progress."""
        if self._progress_callback:
            try:
                self._progress_callback(message, None)
            except Exception:
                pass
