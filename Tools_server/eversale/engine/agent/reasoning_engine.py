"""
ReAct Loop & Reasoning Engine

Extracted from brain_enhanced_v2.py to handle:
- LLM reasoning phase (_reason)
- Result reflection phase (_reflect)
- Vision analysis and verification
- Common sense checks
- Tool call validation

This module provides the ReasoningEngine mixin class that can be
inherited by the main agent brain class.
"""

import asyncio
import base64
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger
from rich.console import Console

# Type hint for ActionResult - will be imported from parent
try:
    from dataclasses import dataclass

    @dataclass
    class ActionResult:
        """Result of a tool execution."""
        success: bool
        data: Any = None
        error: str = None
        screenshot: bytes = None
except ImportError:
    pass

console = Console()


class ReasoningEngineMixin:
    """
    Mixin class providing ReAct loop reasoning capabilities.

    This class should be inherited by the main agent brain class.
    It expects the following attributes to be present on self:
    - resource_monitor: ResourceMonitor instance
    - crash_recovery: CrashRecovery instance
    - memory_arch: MemoryArchitecture instance (optional)
    - ollama_client: Ollama client for LLM calls
    - browser: Browser instance (optional)
    - mcp: MCP client for tool calls
    - hallucination_guard: HallucinationGuard instance (optional)
    - vision_model: str - name of vision model
    - model: str - name of main LLM model
    - temperature: float - LLM temperature
    - llm_timeout: int - timeout for LLM calls
    - messages: List[Dict] - conversation history
    - stats: Dict - statistics tracking
    - _reason_cache: Cache instance
    - _goal_summary: str - current goal summary
    - _goal_keywords: List[str] - keywords for goal assertion
    - _last_screenshot_hash: str - hash of last screenshot
    - _last_screenshot_issue: str - any issue with last screenshot
    - _actions_expected_change: Set[str] - actions that should change page
    - describe_mode: bool - whether in describe-only mode
    - _describe_retry_done: bool - whether describe retry was attempted
    - _last_issues: List[str] - last detected issues
    """

    # Actions that should result in visible page changes
    _actions_expected_change = {
        'playwright_navigate', 'playwright_click', 'playwright_fill',
        'browser_click', 'browser_type', 'browser_navigate'
    }

    async def _reason(self, tools: List[Dict]) -> Dict:
        """REASON phase: LLM decides what to do."""
        from agent.resource_monitor import ResourceError

        # Check resources before expensive LLM call
        try:
            self.resource_monitor.check_and_enforce()
            self.stats['resource_checks'] = self.stats.get('resource_checks', 0) + 1
        except ResourceError as e:
            logger.error(f"Resource limit exceeded: {e}")
            self.stats['resource_warnings'] = self.stats.get('resource_warnings', 0) + 1
            # Save state for recovery
            self.crash_recovery.save_full_state(
                prompt=getattr(self, 'current_prompt', 'Unknown'),
                iteration=self.iteration,
                messages=self.messages,
                tool_results=[]
            )
            raise

        # Throttle if needed
        if self.resource_monitor.throttle_if_needed():
            logger.warning("Throttled due to high resource usage")
            self.stats['throttle_count'] = self.stats.get('throttle_count', 0) + 1

        try:
            # Generate cache key from model name + hash of last 3 messages
            context_key = json.dumps(self.messages[-3:], sort_keys=True, default=str)
            cache_key_hash = hashlib.md5(context_key.encode()).hexdigest()[:16]
            cache_key = f"{self.model}_{cache_key_hash}"

            # Check cache (TTL: 300 seconds / 5 minutes)
            cached = self._reason_cache.get("reason", cache_key)
            if cached is not None:
                self.stats['cache_hits'] = self.stats.get('cache_hits', 0) + 1
                logger.debug(f"[CACHE HIT] LLM response cache hit (key: {cache_key[:8]}...)")

                # Re-append cached message to maintain state
                self.messages.append(cached)
                return cached

            # Cache miss - make LLM call
            self.stats['cache_misses'] = self.stats.get('cache_misses', 0) + 1
            logger.debug(f"[CACHE MISS] LLM response cache miss (key: {cache_key[:8]}...)")

            # Enrich context with memory if available
            if self.memory_arch:
                try:
                    # Get the current task from most recent user message
                    query = self._goal_summary if hasattr(self, '_goal_summary') and self._goal_summary else ""
                    if not query and self.messages:
                        for msg in reversed(self.messages):
                            if msg.get('role') == 'user':
                                query = msg.get('content', '')[:200]
                                break

                    if query and self.memory_arch:
                        # Get enriched context with relevant memories
                        enriched_context = self.memory_arch.get_enriched_context(
                            query=query,
                            detailed_steps=5,
                            limit_per_type=2
                        )

                        # Add as system-level guidance (prepend to messages)
                        if enriched_context and len(enriched_context) > 100:
                            # Check if we already have a memory context message
                            has_memory_context = any(
                                msg.get('role') == 'user' and '[Memory Context]' in msg.get('content', '')
                                for msg in self.messages
                            )

                            if not has_memory_context:
                                # Insert memory context after system prompt (index 1)
                                memory_msg = {
                                    'role': 'user',
                                    'content': f"[Memory Context - Relevant Past Experiences]\n{enriched_context[:1000]}"
                                }
                                # Insert at position 1 (after system prompt)
                                if len(self.messages) > 1:
                                    self.messages.insert(1, memory_msg)
                                    logger.debug(f"[MEMORY] Added enriched context from memory architecture")
                except Exception as e:
                    logger.debug(f"Memory enrichment failed: {e}")

            # CONTINUOUS PERCEPTION: Add visual awareness context
            # This makes the agent aware of what it's currently "seeing" on the page
            if hasattr(self, 'browser_manager') and self.browser_manager:
                try:
                    perception_state = self.browser_manager.get_perception_state()
                    if perception_state and perception_state.interactive_elements:
                        # Check if we already have a perception context message
                        has_perception_context = any(
                            msg.get('role') == 'user' and '[Visual Context]' in msg.get('content', '')
                            for msg in self.messages[-5:]  # Only check recent messages
                        )

                        # CRITICAL: Skip visual context if page content was already injected
                        # This prevents creating 2 consecutive user messages that confuse LLM
                        last_user_msg = next(
                            (msg.get('content', '') for msg in reversed(self.messages) if msg.get('role') == 'user'),
                            ''
                        )
                        has_completion_instruction = 'Just generate the final response' in last_user_msg or \
                                                     'complete the original task' in last_user_msg
                        if has_completion_instruction:
                            logger.debug("[PERCEPTION] Skipping visual context - page content already injected")
                            has_perception_context = True  # Skip adding more context

                        if not has_perception_context:
                            # Build a concise visual context with ACTION GUIDANCE
                            elements_summary = []
                            action_hints = []

                            for el in perception_state.interactive_elements[:15]:  # Top 15 elements
                                text = el.get('text', '')[:40] or el.get('ariaLabel', '')[:40]
                                tag = el.get('tag', 'element')
                                selector = el.get('selector', '')

                                if text:
                                    elements_summary.append(f"- {tag}: {text}")

                                    # Generate action hints based on element type
                                    if tag == 'input':
                                        input_type = el.get('type', 'text')
                                        if selector:
                                            action_hints.append(f"  → Use playwright_fill with selector '{selector}' to enter text")
                                    elif tag == 'button':
                                        if selector:
                                            action_hints.append(f"  → Use playwright_click with selector '{selector}' to click")

                            if elements_summary:
                                visual_context = f"[Visual Context - Current Page State]\n"
                                visual_context += f"URL: {perception_state.page_url}\n"
                                visual_context += f"Title: {perception_state.page_title}\n\n"
                                visual_context += "Interactive elements visible:\n" + "\n".join(elements_summary[:10])

                                # Add action guidance if we have hints
                                if action_hints and len(action_hints) <= 5:
                                    visual_context += "\n\nSuggested actions:\n" + "\n".join(action_hints[:5])

                                # Critical instruction to prevent navigation loops
                                visual_context += "\n\nIMPORTANT: Page already loaded. DO NOT navigate again. Use playwright_fill for inputs and playwright_click for buttons."

                                # Add as latest context (append, not insert)
                                self.messages.append({
                                    'role': 'user',
                                    'content': visual_context
                                })
                                logger.debug("[PERCEPTION] Added visual context with action guidance")
                except Exception as e:
                    logger.debug(f"Perception context failed: {e}")

            # FIRST LLM CALL: Use Kimi for task understanding (iteration 0)
            # MIDDLE LLM CALLS: Use fast execution model (0000/ui-tars-1.5-7b:latest)
            # This is part of the general-purpose autonomous agent pattern
            response = None
            use_kimi = (
                getattr(self, 'iteration', 0) == 0 and
                hasattr(self, 'kimi_client') and
                self.kimi_client and
                hasattr(self.kimi_client, 'client') and
                self.kimi_client.client
            )

            if use_kimi:
                # FIRST CALL: Use Kimi for complex task understanding
                try:
                    logger.info("[KIMI] Using Kimi for initial task understanding (iteration 0)")
                    # Convert messages to OpenAI format
                    openai_messages = []
                    for msg in self.messages:
                        role = msg.get('role', 'user')
                        content = msg.get('content', '')
                        openai_messages.append({'role': role, 'content': content})

                    kimi_response = await asyncio.wait_for(
                        self.kimi_client.client.chat.completions.create(
                            model=self.kimi_client.model,
                            messages=openai_messages,
                            temperature=self.temperature,
                            max_tokens=4096
                        ),
                        timeout=30  # Kimi timeout
                    )
                    if kimi_response and kimi_response.choices:
                        # Convert Kimi response to ollama format
                        kimi_content = kimi_response.choices[0].message.content
                        response = {
                            'message': {
                                'role': 'assistant',
                                'content': kimi_content,
                                'tool_calls': None  # Kimi doesn't do tool calls here
                            }
                        }
                        logger.info(f"[KIMI] Task understanding complete ({len(kimi_content)} chars)")
                except Exception as kimi_error:
                    logger.warning(f"[KIMI] Initial understanding failed, falling back to local: {kimi_error}")
                    response = None

            # Fall back to local ollama for execution steps or if Kimi failed
            if not response:
                try:
                    response = await asyncio.wait_for(
                        asyncio.to_thread(
                            self.ollama_client.chat,
                            model=self.model,
                            messages=self.messages,
                            tools=tools,
                            options={'temperature': self.temperature}
                        ),
                        timeout=self.llm_timeout
                    )
                except asyncio.TimeoutError:
                    logger.error(f"LLM call timed out after {self.llm_timeout}s")
                    return {'content': f'LLM reasoning timed out after {self.llm_timeout}s. Stopping task.'}

            # Convert Pydantic Message to dict for consistent handling
            msg = response['message']
            if hasattr(msg, 'model_dump'):
                msg = msg.model_dump()
            elif not isinstance(msg, dict):
                msg = dict(msg)

            # Strip thinking tags from Qwen3 models (they output <think>...</think>)
            if msg.get('content'):
                content = msg['content']
                # Remove <think>...</think> blocks (including multiline)
                content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
                # Also remove orphaned tags
                content = re.sub(r'</?think>', '', content)
                msg['content'] = content.strip()

            self.messages.append(msg)

            # Show reasoning
            if msg.get('content'):
                console.print(f"[dim]Thinking: {msg['content'][:100]}...[/dim]")

                # HALLUCINATION CHECK: Validate LLM response for hallucination indicators
                if self.hallucination_guard:
                    llm_validation = self.hallucination_guard.validate_llm_response(
                        msg['content'],
                        expected_source="browser" if self.browser else "file"
                    )
                    if not llm_validation.is_valid:
                        logger.warning(f"LLM HALLUCINATION indicators: {llm_validation.issues}")

                        # RECOVERY: If LLM claims it can't browse but we have browser, force browser action
                        if self.browser and any('cannot' in i.lower() or 'unable' in i.lower() or 'as an ai' in i.lower() for i in llm_validation.issues):
                            logger.warning(f"[LLM RECOVERY] LLM claimed inability - forcing browser tool usage")

                            # Extract any URL from the original prompt or context
                            url_match = re.search(r'https?://[^\s<>"\']+', self._goal_summary or '')
                            if url_match:
                                force_url = url_match.group(0)
                                logger.info(f"[LLM RECOVERY] Forcing navigation to: {force_url}")

                                # Inject a browser tool call to override the hallucination
                                if not msg.get('tool_calls'):
                                    msg['tool_calls'] = []

                                msg['tool_calls'].insert(0, {
                                    'id': f'recovery_{id(msg)}',
                                    'type': 'function',
                                    'function': {
                                        'name': 'playwright_navigate',
                                        'arguments': json.dumps({'url': force_url})
                                    }
                                })
                                msg['content'] = f"[RECOVERY] Overriding hallucination - navigating to {force_url} to get real data."
                                logger.success(f"[LLM RECOVERY] Injected browser navigation tool call")
                            else:
                                # No URL found - add guidance to message
                                msg['content'] += "\n\n[SYSTEM: You claimed you cannot browse, but you have browser access. Use playwright_navigate to go to a real URL and get actual data.]"

                    msg['_hallucination_warning'] = llm_validation.issues

            # Validate and correct tool calls before returning
            if msg.get('tool_calls'):
                msg['tool_calls'] = self._validate_tool_calls(msg['tool_calls'])

            # Cache the response (TTL: 300 seconds / 5 minutes)
            self._reason_cache.set("reason", cache_key, msg, ttl_seconds=300)
            logger.debug(f"[CACHE STORE] Cached LLM response (key: {cache_key[:8]}...)")

            return msg

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Reasoning failed: {error_msg}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            # Sanitize error message - aggressively strip HTML and long content
            # Strip all HTML-like content
            error_msg = re.sub(r'<[^>]*>', '', error_msg)  # Strip HTML tags
            error_msg = re.sub(r'<!DOCTYPE[^>]*>', '', error_msg, flags=re.IGNORECASE)
            error_msg = re.sub(r'<html[^>]*>.*?</html>', '', error_msg, flags=re.DOTALL | re.IGNORECASE)
            if len(error_msg) > 200:
                error_msg = error_msg[:200] + "..."
            # If still looks like HTML or eversale.io contamination, just give a generic message
            # Be specific to avoid false positives on legitimate "Sign in" pages
            contamination_markers = ['DOCTYPE', 'favicon', 'eversale.io', 'EverSale',
                                     'Skip to main content EverSale', 'Sign in View pricing', '_app/immutable']
            html_indicators = ['<html', '<head', '<body', '<script', '<style']
            is_html = any(ind.lower() in error_msg.lower() for ind in html_indicators)
            is_contaminated = any(marker.lower() in error_msg.lower() for marker in contamination_markers)
            if is_html or is_contaminated:
                error_msg = "Processing failed - retrying with different approach"
            return {'content': f'I encountered an issue: {error_msg}. Let me try a different approach.'}

    def _validate_tool_calls(self, tool_calls: List[Dict]) -> List[Dict]:
        """Validate and correct tool calls - fix hallucinated tool names."""
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

        available_tools = set(self.mcp.tools.keys()) if hasattr(self.mcp, 'tools') else set()

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

    async def _reflect(self, results: List['ActionResult']) -> Dict:
        """REFLECT phase: Analyze results, possibly with vision."""

        # Check if any failed
        failures = [r for r in results if not r.success]
        if failures:
            return {
                'done': False,
                'retry_needed': True,
                'issue': failures[0].error
            }

        vision_result = await self._collect_vision_insight(results)
        common_issue, dom_feedback = await self._common_sense_verification(vision_result)
        assert_issue = self._assert_success(dom_feedback, vision_result)
        issues = [i for i in (common_issue, assert_issue) if i]
        if vision_result:
            self._append_vision_tool_message(vision_result, 'vision_analysis')

            # If describe-only and we hit an error banner, try one controlled reload before returning
            if (
                self.describe_mode
                and vision_result.get('error_detected')
                and not self._describe_retry_done
                and self.browser
                and getattr(self.browser, "page", None)
            ):
                self._describe_retry_done = True
                try:
                    current_url = self.browser.page.url
                except Exception as e:
                    logger.warning(f"Failed to get current URL for describe-mode reload: {e}")
                    current_url = None

                try:
                    if current_url:
                        await self.mcp.call_tool('playwright_navigate', {'url': current_url})
                        await asyncio.sleep(1)  # allow page to settle
                    retry_shot = await self._take_screenshot()
                    if retry_shot:
                        retry_vision = await self._vision_analyze(retry_shot)
                        self.stats['vision_calls'] += 1
                        if retry_vision:
                            vision_result = retry_vision
                            self._append_vision_tool_message(vision_result, 'vision_analysis_retry')
                except Exception as e:
                    logger.warning(f"Describe-mode reload failed, continuing with original vision result: {e}")

            # If user just wants a description, return the vision summary directly
            if self.describe_mode and vision_result:
                summary = (
                    vision_result.get('raw_summary')
                    or vision_result.get('summary')
                    or vision_result.get('page_state')
                    or "Visual summary unavailable."
                )
                if issues:
                    summary += f" (Additional checks: {'; '.join(issues)})"
                if vision_result.get('error_detected'):
                    summary += " (Note: Page shows an error banner.)"
                response = {'done': True, 'summary': summary}
                self._last_issues = issues
                return response

            if issues:
                response = {
                    'done': False,
                    'retry_needed': True,
                    'issue': '; '.join(issues)
                }
                self._last_issues = issues
                return response

            if vision_result.get('error_detected'):
                response = {
                    'done': False,
                    'retry_needed': True,
                    'issue': vision_result.get('error', 'Visual verification failed')
                }
                self._last_issues = issues
                return response

            if vision_result.get('task_complete'):
                response = {
                    'done': True,
                    'summary': vision_result.get('summary', 'Task complete')
                }
                self._last_issues = issues
                return response

        if common_issue:
            return {
                'done': False,
                'retry_needed': True,
                'issue': common_issue
            }
        self._last_issues = issues
        return {'done': False, 'retry_needed': False}

    async def _collect_vision_insight(self, results: List['ActionResult']) -> Dict:
        """
        Ensure we always have a vision-based check; try existing screenshots first,
        then capture a fresh one if needed.
        """
        screenshot = next((r.screenshot for r in reversed(results) if r.screenshot), None)
        if not screenshot and self.browser:
            screenshot = await self._take_screenshot()

        if screenshot:
            self._record_screenshot_bytes(screenshot, action_name=None)
            result = await self._vision_analyze(screenshot)
            self.stats['vision_calls'] += 1
            if result:
                return result

        return {}

    def _append_vision_tool_message(self, vision_result: Dict, name: str):
        """Log vision analysis output into the message stream for auditing."""
        try:
            self.messages.append({
                'role': 'tool',
                'name': name,
                'content': json.dumps(vision_result)[:2000]
            })
        except Exception as e:
            logger.debug(f"Failed to append vision message {name}: {e}")

    async def _common_sense_verification(self, vision_result: Dict) -> Tuple[Optional[str], str]:
        """Run heuristics that enforce common-sense verification at every step."""
        dom_feedback = await self._fetch_dom_feedback()
        text_issue = self._detect_text_issue(dom_feedback)
        if text_issue:
            return text_issue, dom_feedback

        if self._last_screenshot_issue:
            issue = self._last_screenshot_issue
            self._last_screenshot_issue = None
            return issue, dom_feedback

        health_issue = await self._health_pulse(dom_feedback)
        if health_issue:
            return health_issue, dom_feedback

        return None, dom_feedback

    def _assert_success(self, dom_feedback: str, vision_result: Dict) -> Optional[str]:
        """Check if goal keywords are present in the observed page."""
        if not self._goal_keywords:
            return None

        combined = " ".join([
            dom_feedback or "",
            vision_result.get('raw_summary', ''),
            vision_result.get('summary', '')
        ]).lower()

        if any(kw in combined for kw in self._goal_keywords):
            return None

        excerpt = ", ".join(self._goal_keywords[:3])
        return f"Goal keywords ({excerpt}) not referenced in the observed page."

    async def _vision_analyze(self, screenshot: bytes) -> Dict:
        """Use vision model to analyze screenshot."""

        if not self.vision_model:
            logger.warning("No vision model configured; skipping visual analysis")
            return {'error': 'vision model not configured'}

        try:
            # Encode screenshot
            b64 = base64.b64encode(screenshot).decode('utf-8')

            response = self.ollama_client.chat(
                model=self.vision_model,
                messages=[{
                    'role': 'user',
                    'content': 'Analyze this screenshot. Is there an error message? Is a task/form complete? What do you see?',
                    'images': [b64]
                }],
                options={'temperature': 0.1}
            )

            content = response.get('message', {}).get('content', '')

            # Parse response
            error_words = ['error', 'failed', 'invalid', 'wrong', 'denied']
            complete_words = ['success', 'complete', 'submitted', 'thank you', 'confirmed']
            summary_full = content.strip()

            return {
                'error_detected': any(w in content.lower() for w in error_words),
                'task_complete': any(w in content.lower() for w in complete_words),
                # Keep a compact summary but also return the full text for describe mode
                'summary': summary_full[:500],
                'raw_summary': summary_full
            }

        except Exception as e:
            logger.warning(f"Vision analysis failed: {e}")
            return {}

    # =========================================================================
    # Helper methods for DOM feedback and health checks
    # =========================================================================

    async def _fetch_dom_feedback(self) -> str:
        """Capture text/DOM feedback for heuristic checks."""
        try:
            snapshot = await self.mcp.call_tool('playwright_snapshot', {})
            parts = [
                snapshot.get('summary', ''),
                snapshot.get('snapshot', ''),
                snapshot.get('url', '')
            ]
            content = "\n".join(line for line in parts if line)
            if content:
                return content
        except Exception as e:
            logger.debug(f"Snapshot feedback unavailable: {e}")

        try:
            text_result = await self.mcp.call_tool('playwright_get_text', {'selector': 'body'})
            text = text_result.get('text') if isinstance(text_result, dict) else ''
            return text or ''
        except Exception as e:
            logger.debug(f"Text feedback unavailable: {e}")
            return ''

    def _detect_text_issue(self, text: str) -> Optional[str]:
        """Detect common error indicators in page text."""
        return self.browser_manager.detect_text_issue(text)

    async def _health_pulse(self, dom_feedback: str) -> Optional[str]:
        """Periodic health check executed every few iterations."""
        if self.stats['iterations'] == 0 or self.stats['iterations'] % 3 != 0:
            return None

        self.stats['health_checks'] = self.stats.get('health_checks', 0) + 1
        if not dom_feedback:
            return None

        lower = dom_feedback.lower()
        pulse_keywords = ['timeout', 'captcha', 'cloudflare', 'network error', 'service unavailable']
        for word in pulse_keywords:
            if word in lower:
                return f"Health pulse found '{word}' in page snapshot."
        return None

    # =========================================================================
    # Screenshot handling methods
    # =========================================================================

    def _record_screenshot_bytes(self, screenshot: Optional[bytes], action_name: Optional[str] = None) -> Optional[str]:
        """Track screenshot hashes and flag unexpected no-change scenarios."""
        if not screenshot:
            return None

        new_hash = hashlib.md5(screenshot).hexdigest()
        issue = None

        if (
            self._last_screenshot_hash
            and action_name
            and action_name in self._actions_expected_change
            and new_hash == self._last_screenshot_hash
        ):
            issue = f"Screenshot unchanged after {action_name}; page may not have loaded or changed."

        self._last_screenshot_hash = new_hash
        self._last_screenshot_issue = issue
        return issue

    async def _take_screenshot(self) -> Optional[bytes]:
        """Take screenshot of current page."""
        if not self.browser:
            return None

        try:
            screenshot = await self.browser.page.screenshot()
            return screenshot
        except Exception as e:
            logger.debug(f"Screenshot capture failed: {e}")
            return None

    async def _capture_screenshot(self, tool_name: str, result: Any) -> Optional[bytes]:
        """
        Prefer the screenshot produced by the tool (if it saved a file),
        otherwise fall back to capturing the current page.
        """
        # Try to read the path the tool returned
        if isinstance(result, dict):
            path = result.get('filepath') or result.get('path')
            if path:
                try:
                    file_path = Path(path)
                    if file_path.exists():
                        return file_path.read_bytes()
                except Exception as e:
                    logger.debug(f"Could not read screenshot from {path}: {e}")

        # Fallback: take a fresh screenshot
        try:
            return await self._take_screenshot()
        except Exception as e:
            logger.debug(f"Fallback screenshot failed after {tool_name}: {e}")
            return None
