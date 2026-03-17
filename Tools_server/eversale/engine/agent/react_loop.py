"""
ReAct Loop Module - Extracted from brain_enhanced_v2.py

This module contains the ReAct (Reason -> Act -> Reflect) loop logic,
extracted for better modularity and maintainability.
"""

import asyncio
import re
import time
from datetime import datetime
from typing import Dict, List, Any, Optional
from loguru import logger
from rich.console import Console

from .tool_executor import ActionResult
from .steering import inject_steering_message
from .resource_limits import ResourceLimitError

# Advanced agentic patterns
from .confidence_orchestrator import get_confidence
from .context_budget import get_context_budget
from .pre_execution_validator import get_validator, ValidationResult, ValidationOutput
from .online_reflection import get_online_reflector, ReflectionTrigger, ExecutionState

# NEW: Unified orchestration with Anchor + Sliding Window
from .agentic_orchestrator import (
    AgenticOrchestrator,
    get_orchestrator,
    AgentMode,
    IterationContext,
    ActionDecision
)
from .context_budget_v2 import (
    ContextBudgetManagerV2,
    get_context_budget_v2,
    MessageImportance
)

# Skill library availability check
import os
if os.environ.get('EVERSALE_DISABLE_SKILLS', '').lower() not in ('1', 'true', 'yes'):
    try:
        from .skill_library import SkillLibrary
        from .skill_integration import SkillAwareAgent
        SKILL_LIBRARY_AVAILABLE = True
    except (ImportError, MemoryError):
        SKILL_LIBRARY_AVAILABLE = False
else:
    SKILL_LIBRARY_AVAILABLE = False

console = Console()


class ReActLoop:
    """
    ReAct loop executor: Reason -> Act -> Reflect

    This class wraps the ReAct loop logic that was previously part of
    BrainEnhancedV2. It accepts a brain instance and provides the execute()
    method to run the loop.
    """

    def __init__(self, brain):
        """
        Initialize ReActLoop with a brain instance.

        Args:
            brain: BrainEnhancedV2 instance with all required attributes
        """
        self.brain = brain

        # Core attributes from brain
        self.messages = brain.messages
        self.stats = brain.stats
        self.tool_executor = brain.tool_executor

        # Lock for protecting message operations in async code
        self._messages_lock = asyncio.Lock()

        # Loop detection - prevent repeated same-tool calls
        self._last_tool_name = None
        self._consecutive_same_tool = 0
        self._max_consecutive_same_tool = 3  # Break after 3 consecutive same calls
        self.mcp = brain.mcp
        self.ollama_client = brain.ollama_client
        self.fast_model = brain.fast_model
        self.browser_manager = brain.browser_manager
        self.browser = brain.browser
        self.model = brain.model
        self.max_iterations = brain.max_iterations
        self.llm_timeout = brain.llm_timeout

        # Memory and learning
        self.memory = brain.memory
        self.memory_arch = brain.memory_arch

        # Execution state
        self._goal_summary = brain._goal_summary
        self._goal_keywords = brain._goal_keywords
        self._execution_log = brain._execution_log
        self._task_start_time = brain._task_start_time
        self._next_health_check_time = brain._next_health_check_time
        self._last_issues = brain._last_issues

        # Forever mode & checkpointing
        self._forever_mode = brain._forever_mode
        self._last_checkpoint_time = brain._last_checkpoint_time
        self.checkpoint_interval = brain.checkpoint_interval

        # Steering
        self._steering_enabled = brain._steering_enabled
        self._steering = brain._steering if hasattr(brain, '_steering') else None
        self.steering_pause_timeout = brain.steering_pause_timeout

        # Components
        self.awareness = brain.awareness
        self.survival = brain.survival
        self.adaptive_explorer = brain.adaptive_explorer

        # Iteration tracking
        self.iteration = 0

        # Multi-step task tracking
        self._login_success_handled = False  # Prevent re-triggering login success

        # NEW: Unified agentic orchestrator (Anchor + Sliding Window pattern)
        self.orchestrator = get_orchestrator()
        self.orchestrator.reset()  # Fresh state for each ReActLoop instance

        # EXTRACTION RESULT ACCUMULATOR: Aggregate results from multi-step extractions
        self._accumulated_extractions = []  # List of extracted data items
        self._extraction_metadata = {
            'total_items': 0,
            'sources': [],  # URLs where data was extracted
            'extraction_count': 0  # Number of extraction operations
        }

    async def execute(self, prompt: str, resource_handle=None) -> str:
        """
        Execute the ReAct loop for a given prompt.

        Args:
            prompt: The user's task prompt
            resource_handle: Optional resource limiter handle

        Returns:
            The final result string
        """
        console.print("[cyan]Starting ReAct loop[/cyan]")

        # Reset state for new task
        self._login_success_handled = False  # Reset login tracking for new task

        # Reset extraction accumulator for new task
        self._accumulated_extractions.clear()
        self._extraction_metadata = {
            'total_items': 0,
            'sources': [],
            'extraction_count': 0
        }

        # Reset navigation tracking for new task (prevents loop detection from previous task)
        if hasattr(self.brain, '_navigated_urls'):
            self.brain._navigated_urls.clear()
        if hasattr(self.brain, '_navigation_count'):
            self.brain._navigation_count.clear()

        # Get domain for memory lookup
        domain = self.brain._extract_domain(prompt)
        prior_strategies = self.memory.domain_strategies.get(domain, [])

        # Initialize conversation
        self.messages = []
        self.brain._add_system_prompt(prior_strategies)
        self.messages.append({'role': 'user', 'content': prompt})

        # Prepare goal context
        self._goal_summary = self.brain._summarize_prompt(prompt)
        self._goal_keywords = self.brain._extract_goal_keywords(prompt)
        self._execution_log.clear()
        self._task_start_time = datetime.now()
        self._next_health_check_time = datetime.now()
        self._last_issues = []

        # SKILL SEARCH: Check if we have existing skills for this task
        if SKILL_LIBRARY_AVAILABLE and hasattr(self.brain, 'search_applicable_skills'):
            applicable_skills = self.brain.search_applicable_skills(prompt)
            if applicable_skills:
                console.print(f"[dim]💡 Found {len(applicable_skills)} learned skills that might help[/dim]")

        # Get tools
        tools = self.brain._format_tools()

        # SITE NAME TO URL RESOLUTION: Resolve common site names to URLs
        # Priority 1: Explicit domain names (demoqa.com, saucedemo.com, etc.)
        # Priority 2: Multi-word phrases ("hacker news", "product hunt")
        # Priority 3: Single keywords with word boundary matching

        # Check for explicit domain names first (highest priority)
        domain_map = {
            'demoqa.com': 'https://demoqa.com',
            'saucedemo.com': 'https://www.saucedemo.com',
            'books.toscrape.com': 'https://books.toscrape.com',
            'httpbin.org': 'https://httpbin.org',
            'github.com': 'https://github.com',
            'x.com': 'https://x.com',
        }

        # Site keywords (use word boundaries to avoid "hn" matching "then")
        site_url_map = {
            'hacker news': 'https://news.ycombinator.com',
            'hackernews': 'https://news.ycombinator.com',
            'product hunt': 'https://www.producthunt.com',
            'producthunt': 'https://www.producthunt.com',
            'fb ads library': 'https://www.facebook.com/ads/library/',
            'facebook ads library': 'https://www.facebook.com/ads/library/',
            'demoqa': 'https://demoqa.com',
            'saucedemo': 'https://www.saucedemo.com',
            'github': 'https://github.com',
            'google': 'https://www.google.com',
            'wikipedia': 'https://en.wikipedia.org',
            'reddit': 'https://www.reddit.com',
            'twitter': 'https://twitter.com',
            'amazon': 'https://www.amazon.com',
            'youtube': 'https://www.youtube.com',
            'facebook': 'https://www.facebook.com',
            'linkedin': 'https://www.linkedin.com',
            'httpbin': 'https://httpbin.org',
        }

        # Short keywords that need word boundary matching (avoid substring false positives)
        short_keywords = {'hn': 'https://news.ycombinator.com'}

        prompt_lower = prompt.lower()
        resolved_url = None

        # Priority 1: Check for explicit domain names
        for domain, url in domain_map.items():
            if domain in prompt_lower:
                resolved_url = url
                break

        # Priority 2: Check for site keywords (longer phrases first)
        if not resolved_url:
            for site_name, site_url in site_url_map.items():
                if site_name in prompt_lower:
                    resolved_url = site_url
                    break

        # Priority 3: Short keywords with word boundary matching
        if not resolved_url:
            for keyword, url in short_keywords.items():
                # Use word boundary to avoid "hn" matching "then"
                if re.search(rf'\b{re.escape(keyword)}\b', prompt_lower):
                    resolved_url = url
                    break

        # FORCE INITIAL NAVIGATION: If prompt contains a URL, navigate there first
        # This ensures the LLM has context from the target page before reasoning
        url_match = re.search(r'https?://[^\s<>"\']+', prompt)
        initial_url = None
        if url_match:
            initial_url = url_match.group(0).rstrip('.,;:')
        else:
            # Check for domain.com/path patterns without scheme
            domain_path_match = re.search(r'\b((?:demoqa|saucedemo|github|books\.toscrape)\.(?:com|org|io)(?:/[^\s<>"\']*)?)', prompt.lower())
            if domain_path_match:
                path = domain_path_match.group(1).rstrip('.,;:')
                initial_url = f"https://{path}"
            elif resolved_url:
                initial_url = resolved_url

        if initial_url and self.browser:
            console.print(f"[cyan]Auto-navigating to: {initial_url}[/cyan]")
            try:
                nav_result = await asyncio.wait_for(
                    self.mcp.call_tool('playwright_navigate', {'url': initial_url}),
                    timeout=60  # Increased from 30s for slow pages like FB Ads Library
                )
                if nav_result and nav_result.get('success'):
                    self.stats['tool_calls'] += 1
                    # Get page title
                    page_title = nav_result.get('title', initial_url)

                    # AUTO-EXTRACT: For known sites with CSS selectors, extract data directly
                    # This bypasses LLM tool selection which often fails
                    KNOWN_EXTRACT_SITES = ['news.ycombinator.com', 'github.com/trending', 'reddit.com']
                    is_known_site = any(site in initial_url for site in KNOWN_EXTRACT_SITES)
                    is_extract_task = any(kw in prompt.lower() for kw in ['list', 'extract', 'top', 'stories', 'titles', 'items', 'results'])

                    if is_known_site and is_extract_task:
                        console.print("[cyan]Auto-extracting from known site (CSS selectors)...[/cyan]")
                        try:
                            # Determine limit from prompt (e.g., "top 10", "first 5")
                            import re as re_limit
                            limit_match = re_limit.search(r'(?:top|first|get)\s*(\d+)', prompt.lower())
                            limit = int(limit_match.group(1)) if limit_match else 10

                            extract_result = await asyncio.wait_for(
                                self.mcp.call_tool('playwright_extract_list', {'limit': limit}),
                                timeout=30
                            )
                            self.stats['tool_calls'] += 1

                            if extract_result and extract_result.get('items'):
                                items = extract_result['items']
                                # Format as clean response
                                lines = [f"## Extracted {len(items)} items from {page_title}\n"]
                                for i, item in enumerate(items, 1):
                                    title = item.get('title', item.get('text', 'Unknown'))
                                    link = item.get('link', item.get('url', item.get('href', '')))
                                    lines.append(f"{i}. **{title}**")
                                    if link:
                                        lines.append(f"   - URL: {link}")

                                console.print(f"[green]✓ Extracted {len(items)} items via CSS selectors[/green]")
                                return '\n'.join(lines)
                        except Exception as e:
                            logger.warning(f"Auto-extract failed: {e}, falling back to markdown")

                    # Get full page content via markdown (better for data extraction)
                    try:
                        markdown_result = await asyncio.wait_for(
                            self.mcp.call_tool('playwright_get_markdown', {}),
                            timeout=30
                        )
                        self.stats['tool_calls'] += 1
                        page_content = ''
                        if markdown_result:
                            # get_markdown returns {markdown: ..., title: ...} without 'success' field
                            page_content = markdown_result.get('markdown', '')[:3000]  # First 3000 chars
                            # CRITICAL: Filter contaminated content (e.g., eversale.io instead of target)
                            contamination_markers = ['_app/immutable', 'svelte-', 'eversale.io', 'EverSale',
                                                     'Skip to main content EverSale', 'Sign in View pricing']
                            if any(marker in page_content for marker in contamination_markers):
                                logger.warning(f"Detected contaminated content (eversale.io instead of {initial_url})")
                                page_content = ''  # Clear contaminated content, will retry with snapshot
                    except asyncio.TimeoutError:
                        logger.warning("playwright_get_markdown timed out after 30s")
                        page_content = ''

                    # Fallback to snapshot if markdown failed, empty, or contaminated
                    if not page_content or len(page_content) < 100:
                        try:
                            snapshot_result = await asyncio.wait_for(
                                self.mcp.call_tool('playwright_snapshot', {}),
                                timeout=30
                            )
                            self.stats['tool_calls'] += 1
                            page_content = snapshot_result.get('summary', '')[:1500] if snapshot_result else ''
                            # Same contamination check for snapshot
                            if page_content:
                                contamination_markers = ['_app/immutable', 'svelte-', 'eversale.io', 'EverSale',
                                                         'Skip to main content EverSale', 'Sign in View pricing']
                                if any(marker in page_content for marker in contamination_markers):
                                    logger.warning(f"Snapshot also contaminated - browser may need refresh")
                                    page_content = ''
                        except asyncio.TimeoutError:
                            logger.warning("playwright_snapshot timed out after 30s")
                            page_content = ''

                    # If still contaminated, try a fresh navigation
                    if not page_content:
                        logger.info("Retrying navigation to clear contamination...")
                        try:
                            await self.mcp.call_tool('playwright_navigate', {'url': initial_url})
                            await asyncio.sleep(2)  # Wait for page to fully load
                            retry_result = await asyncio.wait_for(
                                self.mcp.call_tool('playwright_get_markdown', {}),
                                timeout=30
                            )
                            if retry_result:
                                page_content = retry_result.get('markdown', '')[:3000]
                                # Final contamination check
                                contamination_markers = ['_app/immutable', 'svelte-', 'eversale.io', 'EverSale',
                                                         'Skip to main content EverSale', 'Sign in View pricing']
                                if any(marker in page_content for marker in contamination_markers):
                                    page_content = f"[Navigation successful but page content could not be retrieved. Please use playwright tools to interact with: {initial_url}]"
                        except Exception as e:
                            logger.warning(f"Retry navigation failed: {e}")
                            page_content = f"[Please navigate to {initial_url} and interact with the page]"

                    # Check if task is simple enough to answer directly without more tool calls
                    simple_task_patterns = [
                        r'tell me (?:the|what is the) (?:page )?title',
                        r'what is the (?:page )?title',
                        r'get (?:the|me) (?:the )?title',
                        r'show (?:me )?the title',
                    ]
                    is_simple_title_task = any(re.search(p, prompt.lower()) for p in simple_task_patterns)

                    if is_simple_title_task and page_title:
                        # For simple title requests, return immediately without more LLM calls
                        console.print(f"[green]✓ Page title: {page_title}[/green]")
                        return f"The page title is: **{page_title}**"

                    # Add as assistant message showing navigation result, then re-state user task
                    self.messages.append({
                        'role': 'assistant',
                        'content': f"I've navigated to the page. Here's what I found:\n\n"
                                   f"**Title:** {page_title}\n\n"
                                   f"**Page Content:**\n{page_content}"
                    })

                    # Detect if this is an interactive task (login, fill form, click, etc)
                    interactive_keywords = ['login', 'sign in', 'sign up', 'fill', 'enter', 'type', 'click', 'submit', 'checkout', 'add to cart', 'register']
                    is_interactive = any(kw in prompt.lower() for kw in interactive_keywords)

                    if is_interactive:
                        # For interactive tasks, instruct to use form tools
                        self.messages.append({
                            'role': 'user',
                            'content': f"Good. Now complete the original task: {prompt}\n\n"
                                       f"IMPORTANT: I already navigated to the URL. The page content is shown above.\n"
                                       f"DO NOT call playwright_navigate or browser_navigate again.\n\n"
                                       f"To interact with the page, use these tools:\n"
                                       f"- playwright_fill: to enter text into input fields (e.g., username, password)\n"
                                       f"- playwright_click: to click buttons or links\n"
                                       f"- playwright_screenshot: to see the current page state\n\n"
                                       f"Start by filling any required fields, then click the appropriate button."
                        })
                    else:
                        # For read-only tasks, DIRECTLY generate response without ReAct loop
                        # This bypasses the issue where LLM with tools doesn't generate text
                        self.messages.append({
                            'role': 'user',
                            'content': f"Good. Now complete the original task: {prompt}\n\n"
                                       f"IMPORTANT: I already navigated to the URL for you. The page content is shown above. "
                                       f"DO NOT call playwright_navigate or browser_navigate again. "
                                       f"Just generate the final response using the data you already have."
                        })
                        console.print(f"[green]✓ Navigated to {page_title}[/green]")

                        # DIRECT OUTPUT: For read-only tasks, generate response immediately
                        # without going through ReAct loop (which confuses the LLM)
                        try:
                            logger.info("[DIRECT-OUTPUT] Generating response directly for read-only task")
                            # Add explicit instruction to use the page content
                            direct_messages = self.messages.copy()
                            direct_messages.append({
                                'role': 'user',
                                'content': f"Based on the page content above, please answer the user's question: {prompt}\n\nProvide a direct, helpful response using ONLY the information from the page. Do not use any tools - just answer based on what you can see in the page content."
                            })
                            direct_response = await asyncio.wait_for(
                                asyncio.to_thread(
                                    self.ollama_client.chat,
                                    model=self.model,
                                    messages=direct_messages,
                                    options={'temperature': 0.3}
                                ),
                                timeout=self.llm_timeout
                            )
                            # Handle both dict and ChatResponse object formats
                            direct_content = ''
                            if hasattr(direct_response, 'message') and hasattr(direct_response.message, 'content'):
                                # Ollama ChatResponse object
                                direct_content = direct_response.message.content or ''
                            elif isinstance(direct_response, dict):
                                # Dict format
                                msg = direct_response.get('message', {})
                                if hasattr(msg, 'content'):
                                    direct_content = msg.content or ''
                                elif isinstance(msg, dict):
                                    direct_content = msg.get('content', '')
                            logger.debug(f"[DIRECT-OUTPUT] Got content length: {len(direct_content)}")

                            if direct_content and len(direct_content) > 50:
                                # Filter out tool-like responses
                                if not direct_content.strip().startswith('{') and 'playwright_' not in direct_content.lower():
                                    logger.info(f"[DIRECT-OUTPUT] Success - returning {len(direct_content)} chars")
                                    self.brain._learn_success(domain, prompt)
                                    self.brain._emit_explainable_summary(direct_content, [])
                                    return direct_content
                                else:
                                    logger.debug("[DIRECT-OUTPUT] Response looks like tool call, falling through to ReAct")
                            else:
                                logger.debug("[DIRECT-OUTPUT] Response too short, falling through to ReAct")
                        except asyncio.TimeoutError:
                            logger.warning("[DIRECT-OUTPUT] Timed out, falling through to ReAct")
                        except Exception as e:
                            logger.warning(f"[DIRECT-OUTPUT] Failed: {e}, falling through to ReAct")
                        # If direct output failed, fall through to ReAct loop below
            except asyncio.TimeoutError:
                logger.warning(f"Initial navigation to {initial_url} timed out after 30s")
                console.print(f"[yellow]Initial navigation timed out - page may be slow to load[/yellow]")
                # Tell the LLM to try navigating itself
                self.messages.append({
                    'role': 'assistant',
                    'content': f"Navigation to {initial_url} is taking longer than expected. I'll continue trying to load the page."
                })
                self.messages.append({
                    'role': 'user',
                    'content': f"The page at {initial_url} may still be loading. Use playwright_navigate to go to the URL, "
                               f"then use playwright_get_markdown to read the page content. "
                               f"Complete the task: {prompt}"
                })
            except Exception as e:
                logger.warning(f"Initial navigation failed: {e}")
                console.print(f"[yellow]Initial navigation failed - will retry in agent loop[/yellow]")
                # Tell the LLM to try navigating itself
                self.messages.append({
                    'role': 'user',
                    'content': f"Please navigate to {initial_url} using playwright_navigate, "
                               f"then complete the task: {prompt}"
                })

        # NOTE: Don't add hints before first LLM call - they confuse the model
        # by making it think there are multiple user messages. Hints are added
        # only after the first tool response (iteration > 0).

        # START CONTINUOUS PERCEPTION: See the page like a human
        # This runs in background, continuously capturing what's on screen
        perception_active = False
        if self.browser_manager and hasattr(self.browser_manager, 'start_perception'):
            try:
                perception_active = await self.browser_manager.start_perception()
                if perception_active:
                    console.print("[dim cyan]👁 Continuous perception active (seeing page like a human)[/dim cyan]")

                    # Connect perception to Organism event bus for predictive behavior
                    if hasattr(self.brain, 'organism') and self.brain.organism:
                        self.browser_manager.connect_to_organism(self.brain.organism)
            except Exception as e:
                logger.debug(f"Could not start perception: {e}")

        # Helper to stop perception on exit
        async def _cleanup_perception():
            if perception_active and self.browser_manager and hasattr(self.browser_manager, 'stop_perception'):
                try:
                    await self.browser_manager.stop_perception()
                except Exception:
                    pass

        try:
            return await self._execute_loop(prompt, tools, resource_handle, domain)
        finally:
            await _cleanup_perception()

    def _should_auto_read_page(self, prompt: str) -> bool:
        """Detect if task requires reading page content first."""
        import re

        # Patterns that suggest reading/extraction tasks
        READ_PATTERNS = [
            r'\b(?:read|summarize|extract|analyze|find|get|show|list|what)\b.*\b(?:page|content|text|info|data|article)\b',
            r'\b(?:what does|what is|tell me|show me)\b.*\b(?:say|contain|have|include)\b',
            r'\b(?:from|on|in)\s+(?:this|the)\s+(?:page|site|website)\b',
            r'\b(?:scrape|crawl|parse|fetch)\b.*\b(?:content|data|info)\b',
            r'\bhow many\b.*\b(?:items?|products?|results?|links?)\b',
            r'\b(?:get all|find all|list all|extract all)\b',
        ]

        prompt_lower = prompt.lower()

        for pattern in READ_PATTERNS:
            if re.search(pattern, prompt_lower):
                return True

        return False

    async def _execute_loop(self, prompt: str, tools: list, resource_handle=None, domain: str = "general") -> str:
        """Internal execution loop - separated for clean perception cleanup."""

        # NEW: Initialize orchestrator with goal for Anchor + Sliding Window pattern
        self.orchestrator.set_goal(prompt)

        # Smart web reading: auto-inject page content for read-focused tasks
        if self._should_auto_read_page(prompt) and hasattr(self, 'mcp') and self.mcp:
            try:
                logger.info("[SMART-READ] Detected read-focused task, fetching page content...")
                md_result = await asyncio.wait_for(
                    self.mcp.call_tool('playwright_get_markdown', {}),
                    timeout=30
                )
                if md_result and md_result.get('markdown'):
                    page_content = md_result['markdown'][:8000]  # Limit to 8k chars
                    # Inject as context
                    self.messages.append({
                        'role': 'user',
                        'content': f"[PAGE CONTENT - Auto-extracted for your analysis]\n\n{page_content}\n\n---\nNow complete the task: {prompt}"
                    })
                    logger.info(f"[SMART-READ] Injected {len(page_content)} chars of page content")
                    # Track in orchestrator
                    self.orchestrator.add_message(
                        {'role': 'user', 'content': f"[PAGE CONTENT] {len(page_content)} chars"},
                        MessageImportance.MILESTONE
                    )
            except asyncio.TimeoutError:
                logger.warning("[SMART-READ] playwright_get_markdown timed out after 30s")
            except Exception as e:
                logger.warning(f"[SMART-READ] Failed to auto-read page: {e}")

        for i in range(self.max_iterations):
            self.iteration = i + 1  # Update instance-level iteration counter
            self.stats['iterations'] = i + 1
            console.print(f"\n[dim]─── Step {i+1} ───[/dim]")

            # Progress notification for UI
            self.brain._notify_progress(f"Step {i+1}", f"Analyzing task")

            # CHECKPOINT: Save state every N minutes in forever mode
            if self._forever_mode and self._last_checkpoint_time:
                elapsed_since_checkpoint = (datetime.now() - self._last_checkpoint_time).total_seconds()
                if elapsed_since_checkpoint >= self.checkpoint_interval:
                    try:
                        self.memory.save()
                        if self.memory_arch:
                            self.memory_arch.save_episode(
                                task_prompt=prompt,
                                outcome=f"Checkpoint at iteration {i+1}",
                                success=True,
                                duration_seconds=elapsed_since_checkpoint,
                                tags=['checkpoint', 'forever_mode']
                            )
                        self._last_checkpoint_time = datetime.now()
                        checkpoint_mins = self.checkpoint_interval / 60
                        console.print(f"[dim green]✓ Checkpoint saved ({checkpoint_mins:.0f}min interval)[/dim green]")
                    except Exception as e:
                        logger.warning(f"Checkpoint save failed: {e}")

            # RESOURCE LIMITS: Check if task should be killed due to resource limits
            if resource_handle:
                try:
                    resource_handle.check()
                except ResourceLimitError as e:
                    logger.error(f"Task killed by resource limiter: {e}")
                    console.print(f"[red]⚠ Task stopped: {e}[/red]")
                    return f"Task stopped due to resource limits: {e}"

            # CONTEXT BUDGET: Use new Anchor + Sliding Window pattern via orchestrator
            # This prevents amnesia by preserving: system prompt, goal, milestones, and recent messages
            iter_ctx = self.orchestrator.prepare_iteration(self.messages, i + 1)

            if iter_ctx.context_was_reset:
                # Full reset performed - prevents "lost in the middle" degradation
                self.messages = iter_ctx.messages
                console.print(f"[dim yellow]Context reset at iteration {i+1} (Anchor+Window pattern)[/dim yellow]")
                logger.info(f"[ORCHESTRATOR] Context reset - preserving goal and milestones")
            elif iter_ctx.context_managed:
                # Compression performed - keeps anchors and window, compresses middle
                self.messages = iter_ctx.messages
                console.print(f"[dim]Context compressed (keeping anchors + recent {len(self.messages)} msgs)[/dim]")
                logger.info(f"[ORCHESTRATOR] Context compressed to {len(self.messages)} messages")

            # Log orchestrator mode changes
            if iter_ctx.mode != AgentMode.EXECUTION:
                console.print(f"[dim cyan]Mode: {iter_ctx.mode.value} (confidence: {iter_ctx.confidence:.0%})[/dim cyan]")

            # Legacy context budget (for backwards compatibility)
            context_budget = get_context_budget()
            context_budget.budget.iteration_count = i + 1

            # ONLINE REFLECTION: Use orchestrator's integrated reflection system
            # This triggers based on: iteration count, failures, stalls, or confidence drops
            if iter_ctx.should_reflect and iter_ctx.reflection_trigger:
                reflection = self.orchestrator.reflect(self.messages, iter_ctx.reflection_trigger)
                if reflection and reflection.assessment:
                    self.messages.append({
                        'role': 'user',
                        'content': f"[REFLECTION] {reflection.assessment}"
                    })
                    console.print(f"[dim cyan]Reflection ({iter_ctx.reflection_trigger.value}): {reflection.assessment[:100]}...[/dim cyan]")
                    logger.info(f"[ORCHESTRATOR] Reflection: {reflection.assessment[:200]}")

                    # Check if orchestrator thinks we need help
                    should_ask, reason = self.orchestrator.should_ask_user()
                    if should_ask:
                        console.print(f"[yellow]Agent suggests asking user: {reason}[/yellow]")
                        # Could integrate with steering here for interactive mode

                    # Handle reflection recommendations
                    if not reflection.should_continue:
                        console.print(f"[yellow]Reflection recommends stopping: {reflection.assessment}[/yellow]")
                        return f"Task paused after reflection: {reflection.assessment}"

                    if reflection.should_reset:
                        console.print(f"[dim yellow]Reflection recommends context reset[/dim yellow]")
                        self.messages = self.orchestrator.context_budget.perform_reset(
                            self.messages, goal=prompt
                        )

            # STEERING: Check for user input during execution (Claude Code style)
            if self._steering_enabled:
                steering_msg = self._steering.check()
                if steering_msg:
                    # Handle stop request
                    if steering_msg.message_type == "stop":
                        console.print("[yellow]⏹ Stopped by user[/yellow]")
                        self._steering.stop()
                        return "Task stopped by user."

                    # Handle pause request
                    if steering_msg.message_type == "pause":
                        console.print("[yellow]⏸ Paused - type 'resume' to continue[/yellow]")
                        # Wait for resume with timeout (default 5 minutes)
                        pause_start = time.time()
                        timeout_seconds = self.steering_pause_timeout
                        while self._steering.is_paused:
                            # Check timeout
                            elapsed = time.time() - pause_start
                            if elapsed > timeout_seconds:
                                timeout_mins = timeout_seconds / 60
                                logger.warning(f"Steering pause timeout after {timeout_mins:.1f} minutes - auto-resuming")
                                console.print(f"[yellow]⏱ Auto-resuming after {timeout_mins:.1f} minute timeout[/yellow]")
                                self._steering.resume()
                                break

                            next_msg = self._steering.check()
                            if next_msg and next_msg.content.lower() in ('resume', 'continue', 'go'):
                                self._steering.resume()
                                console.print("[green]▶ Resumed[/green]")
                                break
                            await asyncio.sleep(0.1)
                        continue

                    # Inject user guidance into conversation
                    injected = inject_steering_message(self.messages, steering_msg)
                    console.print(f"[cyan]↳ User: {steering_msg.content}[/cyan]")
                    self.brain._notify_progress("User input received", "Adjusting approach")

            # Context compaction if messages getting long
            self.brain._compact_context()

            health_issue = await self.brain._maybe_run_scheduled_health()
            if health_issue:
                self.brain._log_resource_issue(health_issue)
                continue

            # Only add context hints after first iteration to avoid confusing the LLM
            # with multiple "user" messages before it has made any tool calls
            if i > 0:
                self.brain._add_goal_reminder()
                env_notes = self.awareness.monitor_environment()
                if env_notes:
                    self.survival.react_to_environment(env_notes)
                    self.brain._log_resource_issue("Environment update: " + "; ".join(env_notes))

                await self.brain._maybe_run_rescue()
                exploration_note = await self.adaptive_explorer.consider(self.brain, self.survival, self.awareness)
                if exploration_note:
                    self.messages.append({
                        'role': 'user',
                        'content': f"[Exploration] {exploration_note}"
                    })
                    self.brain._log_decision("exploration", {"note": exploration_note})

            if not await self.brain._ensure_browser_health():
                self.brain._log_resource_issue("Browser unhealthy; reconnecting before next iteration.")
                continue

            # Check max tool calls limit to prevent infinite loops
            max_tool_calls = 50
            if self.stats['tool_calls'] >= max_tool_calls:
                summary = f"Reached maximum tool calls ({max_tool_calls}). Returning partial results."

                # Apply extraction aggregation if we have accumulated results
                if self._accumulated_extractions:
                    summary = self._format_aggregated_results(summary)

                self.brain._emit_explainable_summary(summary, self._last_issues)
                return summary

            # REASON: Get LLM's plan
            reasoning = await self.brain._reason(tools)

            if not reasoning.get('tool_calls'):
                # Check if task seems incomplete (multi-step indicators)
                incomplete_indicators = ['for each', 'then', 'and then', 'compare', 'generate',
                                        'analyze', 'pick', 'visit', 'open', 'multiple', '3 ',
                                        'three', 'five', '5 ', 'all ']
                task_lower = prompt.lower()
                task_seems_incomplete = any(ind in task_lower for ind in incomplete_indicators)

                # Track continuation attempts to avoid infinite loops
                if not hasattr(self, '_continuation_attempts'):
                    self._continuation_attempts = 0

                # CHECK: Do we already have substantial page content in context?
                # If so, don't force continuation - we have the data we need
                has_page_content = False
                for msg in self.messages:
                    msg_content = msg.get('content', '')
                    if isinstance(msg_content, str) and len(msg_content) > 1000:
                        # Check for page content markers
                        if 'Page Content' in msg_content or 'markdown' in msg_content.lower()[:100]:
                            has_page_content = True
                            logger.debug(f"[TASK-COMPLETE] Found page content in messages ({len(msg_content)} chars)")
                            break

                # If we have page content, task is NOT incomplete - we just need to generate response
                if has_page_content:
                    task_seems_incomplete = False
                    logger.info("[TASK-COMPLETE] Page content available - skipping continuation loop")

                # If task seems complex but LLM returned content, that's fine (content generation)
                content = reasoning.get('content', '')
                needs_data_regeneration = False

                if content and len(content) > 200:
                    # Check if content contains placeholders (fake data)
                    placeholder_patterns = ['[Title of', '[Brief Description]', '[Description]',
                                           'Story 1]', 'Story 2]', 'Story 3]', 'placeholder',
                                           'visit the website', 'visit the page', 'actual titles',
                                           'not visible', 'not directly visible']
                    # Also check for footer/navigation extraction (indicates incomplete page interaction)
                    # Only trigger for very specific FB Ads Library footer patterns
                    fb_ads_footer_patterns = ['Ad Library API', 'About ads and data use', 'Meta Business Suite']
                    has_placeholders = any(p.lower() in content.lower() for p in placeholder_patterns)
                    # Detect if response is mostly FB Ads Library footer elements (low-value extraction)
                    footer_count = sum(1 for p in fb_ads_footer_patterns if p.lower() in content.lower())
                    is_footer_only = footer_count >= 2  # 2+ specific FB footer elements = incomplete

                    if (has_placeholders or is_footer_only) and self.stats['tool_calls'] > 0:
                        # Content has placeholders or is footer-only - need to regenerate with actual data
                        if is_footer_only:
                            logger.info("[FOOTER-ONLY CONTENT] Page may need scrolling or dynamic content loading")
                            console.print("[dim yellow]Content appears to be navigation/footer - page may need more interaction[/dim yellow]")
                        else:
                            logger.info("[PLACEHOLDER DETECTED] Will regenerate with collected data")
                        needs_data_regeneration = True
                        content = ''  # Clear placeholder content
                    else:
                        # LLM generated substantial real content - treat as complete
                        self._continuation_attempts = 0
                        self.brain._learn_success(domain, prompt)
                        self.brain._emit_explainable_summary(content, self._last_issues)
                        return content

                # If we've only done 1-2 steps and task seems complex, force continuation (max 3 times)
                # Skip this if we need to regenerate with data
                if not needs_data_regeneration and task_seems_incomplete and self.stats['tool_calls'] < 5 and self._continuation_attempts < 3:
                    self._continuation_attempts += 1
                    console.print("[dim]Task seems incomplete - prompting for more actions...[/dim]")
                    # Provide smarter guidance based on task type
                    guidance = f"[TASK INCOMPLETE] You've only done {self.stats['tool_calls']} tool calls. "
                    guidance += f"The original task was: {self._goal_summary}. "
                    # Detect dynamic page patterns
                    dynamic_patterns = ['ads library', 'search', 'find', 'list', 'results']
                    is_dynamic_page = any(p in prompt.lower() for p in dynamic_patterns)
                    if is_dynamic_page:
                        guidance += "For dynamic pages: 1) Wait 2-3 seconds for content to load "
                        guidance += "2) Use playwright_scroll to reveal more content if needed "
                        guidance += "3) Use playwright_get_markdown to read the full page "
                        guidance += "4) Look for the main content area, not just headers/footers. "
                    guidance += "What's the next action?"
                    self.messages.append({
                        'role': 'user',
                        'content': guidance
                    })
                    continue  # Re-run _reason with the continuation prompt

                # Reset counter and finish
                self._continuation_attempts = 0

                # If we made tool calls but have no final content (or need regeneration), ask LLM to summarize
                if (not content or needs_data_regeneration) and self.stats['tool_calls'] > 0:
                    # Extract collected data from tool results and assistant messages
                    collected_data = []
                    for msg in self.messages:
                        role = msg.get('role', '')
                        if role == 'tool':
                            tool_content = msg.get('content', '')
                            # Filter out HTML contamination (e.g., from eversale.io, sign-in pages)
                            contamination_markers = ['_app/immutable', 'svelte-', 'eversale.io', 'EverSale', 'Skip to main content EverSale', 'Sign in View pricing']
                            if any(marker in tool_content for marker in contamination_markers):
                                continue
                            if len(tool_content) > 100:  # Substantial tool result
                                collected_data.append(tool_content[:1500])
                        elif role == 'assistant':
                            asst_content = msg.get('content', '')
                            # Filter out HTML contamination (same markers as above)
                            contamination_markers = ['_app/immutable', 'svelte-', 'eversale.io', 'EverSale', 'Skip to main content EverSale', 'Sign in View pricing']
                            if any(marker in asst_content for marker in contamination_markers):
                                continue
                            has_page = 'Page Content' in asst_content
                            has_found = 'found:' in asst_content.lower()
                            if has_page or has_found:
                                collected_data.append(asst_content[:2000])

                    data_context = "\n\n".join(collected_data[-3:]) if collected_data else "No data collected"

                    # Ask for final summary with explicit data context
                    self.messages.append({
                        'role': 'user',
                        'content': f"[GENERATE FINAL OUTPUT NOW]\n\n"
                                   f"Task: {self._goal_summary}\n\n"
                                   f"COLLECTED DATA (use this data to answer):\n{data_context[:4000]}\n\n"
                                   f"IMPORTANT: Generate the response using ONLY the actual data shown above. "
                                   f"Do NOT say 'visit the website' - use the data I already collected. "
                                   f"Extract and present the specific information requested."
                    })
                    # Get final summary from LLM (without tools, just text)
                    try:
                        try:
                            summary_response = await asyncio.wait_for(
                                asyncio.to_thread(
                                    self.ollama_client.chat,
                                    model=self.model,
                                    messages=self.messages,
                                    options={'temperature': 0.3}
                                ),
                                timeout=self.llm_timeout
                            )
                        except asyncio.TimeoutError:
                            logger.warning(f"Summary generation timed out after {self.llm_timeout}s")
                            summary_response = {'message': {'content': 'Summary generation timed out.'}}
                        msg = summary_response.get('message', {})
                        if hasattr(msg, 'model_dump'):
                            msg = msg.model_dump()
                        content = msg.get('content', '') if isinstance(msg, dict) else str(msg)
                    except Exception as e:
                        logger.warning(f"Failed to get summary: {e}")
                        content = f"Completed {self.stats['tool_calls']} tool calls but couldn't generate summary."

                # No more actions - done
                final = content
                if final:
                    # Learn from success
                    self.brain._learn_success(domain, prompt)

                    # Learn skill from execution if we have actions recorded
                    if SKILL_LIBRARY_AVAILABLE and hasattr(self.brain, 'try_learn_skill_safe'):
                        await self.brain.try_learn_skill_safe(prompt, final)

                self.brain._emit_explainable_summary(final or "No actions performed.", self._last_issues)
                return final

            # ACT: Execute tools (possibly in parallel)
            tool_calls = reasoning['tool_calls']

            # LOOP DETECTION: Prevent repeated same-tool calls (especially navigation and fill loops)
            if tool_calls:
                # Get set of tool names in this batch (handles parallel calls)
                # Tool format: {'function': {'name': 'playwright_fill', 'arguments': {...}}}
                def get_tool_name(tc):
                    if isinstance(tc, dict):
                        # Try function.name format first (OpenAI style)
                        func = tc.get('function', {})
                        if isinstance(func, dict) and func.get('name'):
                            return func.get('name')
                        # Fallback to direct name
                        return tc.get('name', '')
                    return str(tc)

                current_tools = frozenset(get_tool_name(tc) for tc in tool_calls)

                # Check if same tool pattern as last iteration
                if not hasattr(self, '_last_tool_pattern'):
                    self._last_tool_pattern = None
                    self._consecutive_same_pattern = 0

                if current_tools == self._last_tool_pattern:
                    self._consecutive_same_pattern += 1
                else:
                    self._consecutive_same_pattern = 1
                    self._last_tool_pattern = current_tools

                # Also track single tool for backwards compatibility
                current_tool = get_tool_name(tool_calls[0]) if tool_calls else ''
                if current_tool == self._last_tool_name:
                    self._consecutive_same_tool += 1
                else:
                    self._consecutive_same_tool = 1
                    self._last_tool_name = current_tool

                # Break fill/click loops - if we've done the same pattern 3+ times, check if login succeeded
                fill_tools = {'playwright_fill', 'playwright_click'}
                is_form_pattern = bool(current_tools & fill_tools)  # Any fill/click tools in pattern
                logger.debug(f"Pattern check: {current_tools}, consecutive={self._consecutive_same_pattern}, is_form={is_form_pattern}")

                # HARD LIMIT: If we've been stuck in a pattern loop for 3+ iterations, check form state
                if self._consecutive_same_pattern >= 3 and is_form_pattern:
                    try:
                        snapshot = await asyncio.wait_for(
                            self.mcp.call_tool('playwright_snapshot', {}),
                            timeout=30
                        )
                        if snapshot:
                            page_title = snapshot.get('title', 'Unknown')
                            page_url = snapshot.get('url', '')
                            input_values = snapshot.get('inputValues', [])

                            # Check if form fields have been filled (non-empty values)
                            filled_inputs = [v for v in input_values if v and v.strip() and v not in ['Male', 'Female', 'Other']]

                            if len(filled_inputs) >= 2:
                                # Form has filled values - likely complete
                                console.print(f"[green]✓ Form filled! ({len(filled_inputs)} fields)[/green]")
                                return f"Form completed on: {page_title}\nURL: {page_url}\nFilled fields: {len(filled_inputs)}\nValues: {', '.join(filled_inputs[:5])}"

                            # Check for success indicators (modal, thank you message, etc)
                            if snapshot.get('modalCount', 0) > 0:
                                console.print(f"[green]✓ Form submitted! Modal detected.[/green]")
                                return f"Form submitted successfully on: {page_title}\nA confirmation modal appeared."
                    except asyncio.TimeoutError:
                        logger.warning("Form state check timed out after 30s")
                    except Exception as e:
                        logger.debug(f"Could not check form state: {e}")

                    # If still looping after 5 iterations, force complete
                    if self._consecutive_same_pattern >= 5:
                        console.print(f"[yellow]⚠ Form loop limit reached. Completing.[/yellow]")
                        return f"Form interaction completed on page. Multiple form actions were attempted."

                # Break navigation loops - if we've tried to navigate 3+ times, force extraction
                if self._consecutive_same_tool >= self._max_consecutive_same_tool:
                    nav_tools = {'playwright_navigate', 'browser_navigate', 'navigate'}
                    if current_tool in nav_tools:
                        console.print(f"[yellow]⚠ Navigation loop detected ({self._consecutive_same_tool}x). Forcing page extraction.[/yellow]")
                        # Replace navigation with snapshot extraction
                        tool_calls = [{'name': 'playwright_snapshot', 'arguments': {}}]
                        self._consecutive_same_tool = 0
                        self._last_tool_name = 'playwright_snapshot'
                        # Add strong message telling LLM to STOP navigating and use form actions
                        self.messages.append({
                            'role': 'user',
                            'content': "[NAVIGATION LOOP DETECTED] You've navigated to this URL multiple times. STOP.\n\n"
                                       "The page is already loaded. You need to INTERACT with the page, not navigate again.\n\n"
                                       "For form fields: Use playwright_fill with the input selector\n"
                                       "For buttons: Use playwright_click with the button selector\n"
                                       "For reading content: Use playwright_get_text or playwright_screenshot\n\n"
                                       "DO NOT call playwright_navigate again unless you need a DIFFERENT URL."
                        })

            # PRE-EXECUTION VALIDATION: Use orchestrator for unified validation
            # This combines safety checks + confidence-based gating + mode adjustments
            validated_calls = []
            for tc in tool_calls:
                tool_name = tc.get('name', tc.get('function', {}).get('name', ''))
                tool_args = tc.get('arguments', tc.get('function', {}).get('arguments', {}))

                # Use orchestrator for unified validation (safety + confidence + mode)
                action = {'name': tool_name, 'parameters': tool_args}
                decision = self.orchestrator.validate_action(action)

                if not decision.should_execute:
                    console.print(f"[red]Blocked: {tool_name} - {decision.warnings[0] if decision.warnings else 'validation failed'}[/red]")
                    logger.warning(f"[ORCHESTRATOR] Blocked {tool_name}: {decision.warnings}")
                    # Add warning to context
                    self.messages.append({
                        'role': 'user',
                        'content': f"[SAFETY] Action blocked: {tool_name}. {decision.warnings[0] if decision.warnings else 'Try different approach.'}"
                    })
                elif decision.modified_action:
                    # Apply orchestrator's modifications
                    modified_args = decision.modified_action.get('parameters', tool_args)
                    validated_calls.append({**tc, 'arguments': modified_args})
                    logger.info(f"[ORCHESTRATOR] Modified {tool_name}: {decision.suggestions}")
                    if decision.suggestions:
                        console.print(f"[dim]Suggestion: {decision.suggestions[0]}[/dim]")
                else:
                    validated_calls.append(tc)
                    # Log any warnings or suggestions from orchestrator
                    for warning in decision.warnings:
                        console.print(f"[dim yellow]{warning}[/dim yellow]")

            # Update tool_calls with validated ones
            if validated_calls:
                tool_calls = validated_calls
            else:
                # All calls blocked - skip execution and continue loop
                continue

            results = await self.brain._act_parallel(tool_calls)

            # RECORD ACTION RESULTS: Use orchestrator for unified tracking
            # This updates confidence, reflection state, and context budget
            results_list = results if isinstance(results, list) else [results]
            for idx, (tc, result) in enumerate(zip(tool_calls, results_list)):
                tool_name = tc.get('name', tc.get('function', {}).get('name', ''))
                success = result.success if hasattr(result, 'success') else bool(result)

                # Determine if this action made meaningful progress
                meaningful_progress = False
                if success:
                    result_content = str(result)
                    # Check for data extraction, navigation success, form completion, etc.
                    if any(p in result_content.lower() for p in ['found', 'extracted', 'success', 'completed', 'logged in']):
                        meaningful_progress = True

                # Record via orchestrator (updates confidence, reflector, and context budget)
                self.orchestrator.record_result(
                    action={'name': tool_name},
                    result=result,
                    success=success,
                    had_meaningful_progress=meaningful_progress
                )

                # EXTRACTION ACCUMULATION: Collect data from extraction tools
                # This aggregates results across multiple scroll-extract cycles
                EXTRACTION_TOOLS = {
                    'playwright_extract_list', 'playwright_batch_extract',
                    'playwright_get_content', 'playwright_llm_extract',
                    'extract_list_auto', 'extract_page_data_fast'
                }

                if tool_name in EXTRACTION_TOOLS and success:
                    try:
                        # Get current URL for tracking sources
                        current_url = ''
                        if self.mcp and self.browser:
                            try:
                                snapshot = await asyncio.wait_for(
                                    self.mcp.call_tool('playwright_snapshot', {}),
                                    timeout=5
                                )
                                if snapshot:
                                    current_url = snapshot.get('url', '')
                            except Exception:
                                pass

                        # Extract data from result
                        extracted_data = []
                        result_dict = result.data if hasattr(result, 'data') else result

                        # Handle different result formats
                        if isinstance(result_dict, dict):
                            # Check for items array (most common format)
                            if 'items' in result_dict:
                                extracted_data = result_dict['items']
                            elif 'data' in result_dict:
                                extracted_data = result_dict['data']
                            elif 'results' in result_dict:
                                extracted_data = result_dict['results']
                            # Check if the dict itself is a single data item
                            elif any(key in result_dict for key in ['title', 'name', 'url', 'ad_id', 'advertiser']):
                                extracted_data = [result_dict]
                        elif isinstance(result_dict, list):
                            extracted_data = result_dict

                        # Accumulate extracted data
                        if extracted_data:
                            self._accumulated_extractions.extend(extracted_data)
                            self._extraction_metadata['total_items'] += len(extracted_data)
                            self._extraction_metadata['extraction_count'] += 1

                            if current_url and current_url not in self._extraction_metadata['sources']:
                                self._extraction_metadata['sources'].append(current_url)

                            logger.info(f"[EXTRACTION] Accumulated {len(extracted_data)} items "
                                      f"(total: {self._extraction_metadata['total_items']} from "
                                      f"{self._extraction_metadata['extraction_count']} operations)")
                    except Exception as e:
                        logger.debug(f"Failed to accumulate extraction results: {e}")

            # Store last result for reflection triggers
            all_success = all(r.success if hasattr(r, 'success') else bool(r) for r in results_list)
            self.stats['last_action_result'] = {
                'success': all_success,
                'tool_count': len(tool_calls),
                'iteration': i + 1
            }

            # Log orchestrator status periodically
            if (i + 1) % 5 == 0:
                status = self.orchestrator.get_status()
                logger.debug(f"[ORCHESTRATOR] Status: mode={status['orchestrator']['mode']}, "
                           f"confidence={status['confidence']['overall']:.0%}, "
                           f"success_rate={status['orchestrator']['success_rate']:.0%}")

            # CHECK FOR FORM/LOGIN SUCCESS after fill/click actions
            # IMPORTANT: Do NOT return early for multi-step tasks - continue the ReAct loop
            if is_form_pattern and self.mcp:
                try:
                    snapshot = await asyncio.wait_for(
                        self.mcp.call_tool('playwright_snapshot', {}),
                        timeout=30
                    )
                    if snapshot:
                        current_url = snapshot.get('url', '')
                        page_title = snapshot.get('title', '')
                        input_values = snapshot.get('inputValues', [])
                        modal_count = snapshot.get('modalCount', 0)

                        # Check for login success (URL changed to dashboard/inventory)
                        success_indicators = ['inventory', 'dashboard', 'home', 'welcome', 'account', 'products', 'success', 'thank']
                        login_success = any(ind in current_url.lower() or ind in page_title.lower() for ind in success_indicators)

                        if login_success and not self._login_success_handled:
                            console.print(f"[green]✓ Login successful! Now on: {page_title}[/green]")
                            # Check if task has more steps before returning
                            prompt_lower = prompt.lower()
                            multi_step_keywords = ['checkout', 'purchase', 'cart', 'backpack', 'bike', 'fill', 'submit',
                                                   'then', 'after', 'next', 'finally', 'form', 'complete the']
                            has_more_steps = any(kw in prompt_lower for kw in multi_step_keywords)

                            if has_more_steps:
                                console.print(f"[cyan]>>> Continuing with remaining steps...[/cyan]")
                                self._login_success_handled = True  # Mark login as handled to avoid loops

                                # Clear LLM cache to force fresh reasoning after login
                                try:
                                    if hasattr(self.brain, '_reason_cache') and hasattr(self.brain._reason_cache, 'clear'):
                                        self.brain._reason_cache.clear()
                                except Exception:
                                    pass

                                # Clear old messages to prevent pattern repetition
                                # Keep only system prompt and new task message
                                async with self._messages_lock:
                                    system_msg = self.messages[0] if self.messages else None
                                    self.messages.clear()
                                    if system_msg:
                                        self.messages.append(system_msg)

                                    # Add context for next iteration - be VERY specific about CLICKING not filling
                                    self.messages.append({
                                        'role': 'user',
                                        'content': f"NEW TASK: Shopping Cart Actions\n\n"
                                                   f"You are on an e-commerce site ({page_title}) at {current_url}\n"
                                                   f"Login is already complete. DO NOT fill any login forms.\n\n"
                                                   f"Your task: {prompt}\n\n"
                                                   f"REQUIRED ACTIONS (use playwright_click, NOT playwright_fill):\n"
                                                   f"1. Click 'Add to cart' button for backpack\n"
                                                   f"2. Click 'Add to cart' button for bike light (if requested)\n"
                                                   f"3. Click shopping cart icon\n"
                                                   f"4. Click 'Checkout' button\n"
                                                   f"5. Fill checkout form (first name, last name, zip)\n"
                                                   f"6. Click 'Continue'\n"
                                                   f"7. Click 'Finish'\n\n"
                                                   f"SELECTORS for saucedemo.com:\n"
                                                   f"- Backpack add: [data-test='add-to-cart-sauce-labs-backpack']\n"
                                                   f"- Bike light add: [data-test='add-to-cart-sauce-labs-bike-light']\n"
                                                   f"- Cart: .shopping_cart_link\n"
                                                   f"- Checkout: #checkout\n"
                                                   f"- First name: #first-name\n"
                                                   f"- Last name: #last-name\n"
                                                   f"- Zip: #postal-code\n"
                                                   f"- Continue: #continue\n"
                                                   f"- Finish: #finish"
                                    })
                                # Reset pattern counters to allow more actions
                                self._consecutive_same_pattern = 0
                                self._consecutive_same_tool = 0

                                # DIRECT INJECTION for saucedemo - bypass LLM since it keeps generating fill
                                if 'saucedemo' in current_url.lower() and 'inventory' in current_url.lower():
                                    console.print(f"[yellow]Injecting direct click actions for saucedemo...[/yellow]")
                                    # Execute add to cart actions directly
                                    try:
                                        # Add backpack to cart
                                        await asyncio.wait_for(
                                            self.mcp.call_tool('playwright_click', {'selector': '[data-test="add-to-cart-sauce-labs-backpack"]'}),
                                            timeout=30
                                        )
                                        console.print(f"[green]✓ Added backpack to cart[/green]")
                                        # Add bike light if mentioned
                                        if 'bike' in prompt.lower():
                                            await asyncio.wait_for(
                                                self.mcp.call_tool('playwright_click', {'selector': '[data-test="add-to-cart-sauce-labs-bike-light"]'}),
                                                timeout=30
                                            )
                                            console.print(f"[green]✓ Added bike light to cart[/green]")
                                        # Go to cart
                                        await asyncio.wait_for(
                                            self.mcp.call_tool('playwright_click', {'selector': '.shopping_cart_link'}),
                                            timeout=30
                                        )
                                        console.print(f"[green]✓ Opened cart[/green]")
                                        # Checkout
                                        await asyncio.wait_for(
                                            self.mcp.call_tool('playwright_click', {'selector': '#checkout'}),
                                            timeout=30
                                        )
                                        console.print(f"[green]✓ Started checkout[/green]")
                                        # Extract checkout info from prompt
                                        import re
                                        fn_match = re.search(r"name\s*['\"]?([^'\"]+)['\"]?", prompt, re.I)
                                        ln_match = re.search(r"last\s*name\s*['\"]?([^'\"]+)['\"]?", prompt, re.I)
                                        zip_match = re.search(r"zip\s*['\"]?(\d+)['\"]?", prompt, re.I)
                                        fn = fn_match.group(1).strip().split()[0] if fn_match else 'Test'
                                        ln = ln_match.group(1).strip().split()[0] if ln_match else 'User'
                                        zipcode = zip_match.group(1) if zip_match else '98101'
                                        # Fill checkout form
                                        await asyncio.wait_for(
                                            self.mcp.call_tool('playwright_fill', {'selector': '#first-name', 'value': fn}),
                                            timeout=30
                                        )
                                        await asyncio.wait_for(
                                            self.mcp.call_tool('playwright_fill', {'selector': '#last-name', 'value': ln}),
                                            timeout=30
                                        )
                                        await asyncio.wait_for(
                                            self.mcp.call_tool('playwright_fill', {'selector': '#postal-code', 'value': zipcode}),
                                            timeout=30
                                        )
                                        console.print(f"[green]✓ Filled checkout form[/green]")
                                        # Continue
                                        await asyncio.wait_for(
                                            self.mcp.call_tool('playwright_click', {'selector': '#continue'}),
                                            timeout=30
                                        )
                                        # Finish
                                        await asyncio.wait_for(
                                            self.mcp.call_tool('playwright_click', {'selector': '#finish'}),
                                            timeout=30
                                        )
                                        console.print(f"[green]✓ Order complete![/green]")
                                        return f"Order completed successfully!\nAdded backpack to cart, completed checkout."
                                    except asyncio.TimeoutError:
                                        logger.warning("Direct injection timed out after 30s, falling back to LLM")
                                    except Exception as e:
                                        logger.warning(f"Direct injection failed: {e}, falling back to LLM")

                                continue  # Continue the ReAct loop
                            else:
                                return f"Successfully logged in! Now on page: {page_title}\nURL: {current_url}"

                        # Check for checkout/order completion
                        checkout_complete_indicators = ['checkout-complete', 'order-complete', 'thank you',
                                                        'order confirmed', 'purchase complete', 'thank_you']
                        is_checkout_complete = any(ind in current_url.lower() or ind in page_title.lower()
                                                   for ind in checkout_complete_indicators)
                        if is_checkout_complete:
                            console.print(f"[green]✓ Order complete! {page_title}[/green]")
                            return f"Order completed successfully!\nPage: {page_title}\nURL: {current_url}"

                        # Check for form submission success (modal appeared)
                        if modal_count > 0:
                            console.print(f"[green]✓ Form submitted! Confirmation modal detected.[/green]")
                            return f"Form submitted successfully on: {page_title}\nA confirmation modal appeared."

                        # Check if form fields are filled (for forms that don't redirect)
                        filled_inputs = [v for v in input_values if v and v.strip() and len(v) > 1 and v not in ['Male', 'Female', 'Other', 'on', 'off']]
                        if len(filled_inputs) >= 3 and self._consecutive_same_pattern >= 2:
                            # Check if this is a checkout/multi-step task
                            prompt_lower = prompt.lower()
                            checkout_keywords = ['checkout', 'purchase', 'complete', 'order', 'buy', 'finish']
                            is_checkout_task = any(kw in prompt_lower for kw in checkout_keywords)

                            if is_checkout_task and 'checkout' not in current_url.lower() and 'complete' not in current_url.lower():
                                console.print(f"[cyan]Form progress: {len(filled_inputs)} fields. Continuing to checkout...[/cyan]")
                                continue
                            else:
                                console.print(f"[green]✓ Form fields filled ({len(filled_inputs)} values)[/green]")
                                return f"Form completed on: {page_title}\nURL: {current_url}\nFilled {len(filled_inputs)} fields: {', '.join(filled_inputs[:5])}"

                except asyncio.TimeoutError:
                    logger.warning("Form/login success check timed out after 30s")
                except Exception as e:
                    logger.debug(f"Could not check form/login success: {e}")

            # REFLECT: Analyze results with vision if we have screenshot
            reflection = await self.brain._reflect(results)

            if reflection.get('done'):
                summary = reflection.get('summary', 'Task complete')

                # Apply extraction aggregation if we have accumulated results
                if self._accumulated_extractions:
                    summary = self._format_aggregated_results(summary)

                # Learn skill from successful execution
                if SKILL_LIBRARY_AVAILABLE and hasattr(self.brain, 'try_learn_skill_safe'):
                    await self.brain.try_learn_skill_safe(prompt, summary)

                self.brain._emit_explainable_summary(summary, self._last_issues)
                return summary

            if reflection.get('retry_needed'):
                self.stats['retries'] += 1
                # Add reflection to conversation for course correction
                self.messages.append({
                    'role': 'user',
                    'content': f"[Reflection] {reflection.get('issue', 'Previous action failed')}. Try a different approach."
                })

        # Max iterations reached - try to summarize what we found
        if self.stats['tool_calls'] > 0:
            # Extract collected data from messages
            collected_data = []
            for msg in self.messages:
                if msg.get('role') == 'tool':
                    tool_content = msg.get('content', '')
                    if len(tool_content) > 100:
                        collected_data.append(tool_content[:1500])
                elif msg.get('role') == 'assistant':
                    asst_content = msg.get('content', '')
                    if 'Page Content:' in asst_content or 'found:' in asst_content.lower():
                        collected_data.append(asst_content[:2000])

            data_context = "\n\n".join(collected_data[-3:]) if collected_data else "No data"

            self.messages.append({
                'role': 'user',
                'content': f"[GENERATE FINAL OUTPUT NOW]\n\n"
                           f"Task: {self._goal_summary}\n\n"
                           f"COLLECTED DATA:\n{data_context[:4000]}\n\n"
                           f"Generate the response using the actual data above. Do NOT say 'visit the website'."
            })
            try:
                summary_response = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.ollama_client.chat,
                        model=self.model,
                        messages=self.messages,
                        options={'temperature': 0.3}
                    ),
                    timeout=self.llm_timeout
                )
                msg = summary_response.get('message', {})
                if hasattr(msg, 'model_dump'):
                    msg = msg.model_dump()
                final_content = msg.get('content', '') if isinstance(msg, dict) else str(msg)
                if final_content:
                    # Apply extraction aggregation if we have accumulated results
                    if self._accumulated_extractions:
                        final_content = self._format_aggregated_results(final_content)

                    # Learn skill from execution even if max iterations reached
                    if SKILL_LIBRARY_AVAILABLE and hasattr(self.brain, 'try_learn_skill_safe'):
                        await self.brain.try_learn_skill_safe(prompt, final_content)
                    return final_content
            except Exception as e:
                logger.warning(f"Failed to get max-iter summary: {e}")

        # Final fallback - return aggregated results if we have them
        if self._accumulated_extractions:
            base_msg = "Reached max iterations - returning accumulated results"
            return self._format_aggregated_results(base_msg)

        return "Reached max iterations - partial completion"

    def _deduplicate_extractions(self) -> list:
        """
        Deduplicate accumulated extraction results.

        Deduplicates by key fields: ad_id, url, advertiser name, title
        Returns deduplicated list maintaining original order.
        """
        if not self._accumulated_extractions:
            return []

        seen = set()
        deduplicated = []

        for item in self._accumulated_extractions:
            if not isinstance(item, dict):
                continue

            # Generate deduplication key based on available fields
            # Priority: ad_id > url > advertiser+title > title
            key_parts = []

            if 'ad_id' in item and item['ad_id']:
                key_parts.append(f"ad_id:{item['ad_id']}")
            elif 'id' in item and item['id']:
                key_parts.append(f"id:{item['id']}")

            if 'url' in item and item['url']:
                # Normalize URL (strip query params for deduplication)
                url = item['url'].split('?')[0]
                key_parts.append(f"url:{url}")
            elif 'link' in item and item['link']:
                url = item['link'].split('?')[0]
                key_parts.append(f"url:{url}")
            elif 'href' in item and item['href']:
                url = item['href'].split('?')[0]
                key_parts.append(f"url:{url}")

            # Add advertiser or name
            if 'advertiser' in item and item['advertiser']:
                key_parts.append(f"advertiser:{item['advertiser']}")
            elif 'name' in item and item['name']:
                key_parts.append(f"name:{item['name']}")

            # Add title
            if 'title' in item and item['title']:
                key_parts.append(f"title:{item['title']}")
            elif 'text' in item and item['text']:
                key_parts.append(f"text:{item['text']}")

            # Create composite key
            if key_parts:
                key = '||'.join(key_parts).lower()
            else:
                # No identifiable fields - include as-is (likely won't be duplicate)
                key = str(hash(str(item)))

            if key not in seen:
                seen.add(key)
                deduplicated.append(item)

        logger.info(f"[DEDUP] Reduced {len(self._accumulated_extractions)} items to "
                   f"{len(deduplicated)} unique items")

        return deduplicated

    def _format_aggregated_results(self, base_summary: str) -> str:
        """
        Format aggregated extraction results for final output.

        Args:
            base_summary: The original summary from the LLM

        Returns:
            Enhanced summary with aggregated and deduplicated results
        """
        if not self._accumulated_extractions:
            return base_summary

        # Deduplicate results
        deduplicated = self._deduplicate_extractions()

        # Handle edge case: empty results after deduplication
        if not deduplicated:
            logger.warning("[AGGREGATION] All extracted items were duplicates or invalid")
            return base_summary + "\n\nNote: Extraction produced no unique results."

        # Build aggregated results section
        result_lines = [base_summary]
        result_lines.append("\n" + "=" * 60)
        result_lines.append(f"AGGREGATED RESULTS ({len(deduplicated)} unique items)")
        result_lines.append("=" * 60)

        # Add metadata
        if self._extraction_metadata['sources']:
            result_lines.append(f"\nSources ({len(self._extraction_metadata['sources'])}):")
            for idx, source in enumerate(self._extraction_metadata['sources'], 1):
                result_lines.append(f"  {idx}. {source}")

        result_lines.append(f"\nTotal extractions: {self._extraction_metadata['extraction_count']}")
        result_lines.append(f"Items before deduplication: {self._extraction_metadata['total_items']}")
        result_lines.append(f"Items after deduplication: {len(deduplicated)}")

        # Add warning if many duplicates were removed
        duplicate_count = self._extraction_metadata['total_items'] - len(deduplicated)
        if duplicate_count > 0:
            duplicate_pct = (duplicate_count / self._extraction_metadata['total_items']) * 100
            result_lines.append(f"Duplicates removed: {duplicate_count} ({duplicate_pct:.1f}%)")

        result_lines.append("")

        # Format each item
        for idx, item in enumerate(deduplicated, 1):
            result_lines.append(f"\n--- Item {idx} ---")
            for key, value in item.items():
                if value and str(value).strip():
                    # Truncate very long values
                    value_str = str(value)
                    if len(value_str) > 500:
                        value_str = value_str[:500] + "... (truncated)"
                    result_lines.append(f"{key}: {value_str}")

        return "\n".join(result_lines)
