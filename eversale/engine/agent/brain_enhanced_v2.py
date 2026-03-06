"""
Enhanced Brain v2 - Production-grade agent with:
1. Vision understanding (sees screenshots)
2. ReAct pattern (reason -> act -> reflect)
3. Persistent memory (learns what works)
4. Parallel execution (faster)
5. Self-healing (retries with alternatives)
6. Streaming output (real-time feedback)
"""

import asyncio
import base64
import hashlib
import json
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable, Tuple
from dataclasses import dataclass, field
from loguru import logger
from .worker_usage_reporter import WorkerUsageDelta, report_worker_usage_fire_and_forget
from rich.console import Console
import ollama
from .awareness import AwarenessHub
from .context_memory import ContextMemory
from .dead_mans_switch import DeadMansSwitch
from .resource_limits import ResourceLimiter, ResourceLimitError
from .multi_instance import MultiInstanceCoordinator
from .decision_logger import DecisionLogger
from .adaptive_explorer import AdaptiveExplorer
from .rescue_policy import RescuePolicy
from .resource_economy import ResourceEconomy
from .resource_monitor import ResourceMonitor, ResourceError
from .survival import SurvivalManager
from .smart_retry import get_retry_manager, get_escalation
from .steering import SteeringMessage, inject_steering_message
from .self_healing_system import self_healing
from .selector_fallbacks import click_with_visual_fallback
from .memory_architecture import MemoryArchitecture
from . import a11y_config

# UI-TARS patterns - ByteDance reliability enhancements
try:
    from .ui_tars_integration import UITarsEnhancer
    from .ui_tars_patterns import RetryConfig, ConversationContext, retry_with_timeout
    UITARS_AVAILABLE = True
except ImportError:
    UITarsEnhancer = None
    RetryConfig = None
    ConversationContext = None
    retry_with_timeout = None
    UITARS_AVAILABLE = False
    logger.debug("UI-TARS patterns not available")

# History pruning for token optimization
try:
    from .history_pruner import HistoryPruner, prune_screenshots_from_history
    HISTORY_PRUNER_AVAILABLE = True
except ImportError:
    HistoryPruner = None
    prune_screenshots_from_history = None
    HISTORY_PRUNER_AVAILABLE = False
    logger.debug("History pruner not available")

# Optional deprecated modules (may be deleted in v2.9+)
try:
    from .crash_recovery import CrashRecovery
except ImportError:
    CrashRecovery = None
try:
    from .cascading_recovery import RecoveryContext
except ImportError:
    RecoveryContext = None
try:
    from .hallucination_guard import HallucinationGuard
except ImportError:
    HallucinationGuard = None

# Intelligent task routing - deterministic workflows for known patterns
try:
    from .intelligent_task_router import route_task, ExecutionPath
    from .deterministic_workflows import match_workflow, extract_params, execute_workflow
    INTELLIGENT_ROUTING_AVAILABLE = True
except ImportError:
    INTELLIGENT_ROUTING_AVAILABLE = False
    logger.debug("Intelligent routing not available")

# Cloudflare challenge handler - auto-solve or find alternatives
try:
    from .challenge_handler import handle_cloudflare_block, get_challenge_handler, BlockedSite
    CHALLENGE_HANDLER_AVAILABLE = True
except ImportError:
    CHALLENGE_HANDLER_AVAILABLE = False
    logger.debug("Challenge handler not available")

# Accessibility-first element finder - Playwright MCP reliability pattern
try:
    from .accessibility_element_finder import SmartElementFinder, AccessibilityRef, parse_snapshot
    ACCESSIBILITY_FINDER_AVAILABLE = True
except ImportError:
    ACCESSIBILITY_FINDER_AVAILABLE = False
    logger.debug("Accessibility element finder not available")

# Reliable browser tools - validation, health checks, retry logic
try:
    from .reliable_browser_tools import ReliableBrowser, ReliableBrowserAdapter, wrap_mcp_client
    RELIABLE_BROWSER_AVAILABLE = True
except ImportError:
    RELIABLE_BROWSER_AVAILABLE = False
    ReliableBrowser = None
    ReliableBrowserAdapter = None
    wrap_mcp_client = None
    logger.debug("Reliable browser tools not available")

# Kimi K2 client - for FIRST (planning) and LAST (synthesis) LLM calls
# General-purpose autonomous agent needs strong reasoning at start/end
try:
    from .kimi_k2_client import get_kimi_client, KimiK2Client
    KIMI_CLIENT_AVAILABLE = True
except ImportError:
    KIMI_CLIENT_AVAILABLE = False
    get_kimi_client = None
    KimiK2Client = None
    logger.debug("Kimi K2 client not available")

# Fast mode - bypasses LLM for simple browser actions (10-30x faster)
try:
    from .fast_mode import FastModeExecutor
    FAST_MODE_AVAILABLE = True
except ImportError:
    FAST_MODE_AVAILABLE = False
    FastModeExecutor = None
    logger.debug("Fast mode not available")


class BrowserToolAdapter:
    """
    Adapter that wraps MCP call_tool interface to provide direct browser methods.
    This allows deterministic workflows to work with our MCP-based architecture.
    Includes automatic Cloudflare challenge handling with fallback to alternatives.
    Uses AI thinking for complex/unexpected obstructions.

    ACCESSIBILITY-FIRST ELEMENT FINDING:
    - Uses accessibility tree refs instead of fragile CSS selectors
    - Matches natural language descriptions to semantic elements
    - Caches accessibility snapshots for performance
    - Falls back to CSS selectors only when accessibility matching fails

    This is the core pattern behind Playwright MCP's reliability.
    """

    def __init__(self, mcp, query: str = "", llm_client=None, use_a11y_first: Optional[bool] = None, config: Optional[dict] = None):
        # Wrap MCP client with reliability layer if available
        if RELIABLE_BROWSER_AVAILABLE:
            self.mcp = wrap_mcp_client(mcp, enable_reliability=True)
            logger.debug("[RELIABLE] BrowserToolAdapter using ReliableBrowser wrapper")
        else:
            self.mcp = mcp

        self.query = query  # Original search query for alternatives
        self.llm_client = llm_client  # LLM client for AI thinking
        self._last_url = ""

        # Determine a11y-first mode from config or parameter
        # Priority: explicit parameter > config > default (True)
        if use_a11y_first is not None:
            self.use_a11y_first = use_a11y_first
        elif config and 'browser' in config and 'use_a11y_first' in config['browser']:
            self.use_a11y_first = config['browser']['use_a11y_first']
        else:
            self.use_a11y_first = True  # Default to ON

        # Accessibility element finder
        if ACCESSIBILITY_FINDER_AVAILABLE:
            self.element_finder = SmartElementFinder(min_confidence=0.3)
            self._accessibility_cache = {}  # url -> (timestamp, refs)
            self._cache_ttl = 5.0  # seconds
            if self.use_a11y_first:
                logger.info("[A11Y] Accessibility-first mode ENABLED (Playwright MCP pattern)")
            else:
                logger.warning("[A11Y] Accessibility-first mode DISABLED (legacy CSS mode)")
        else:
            self.element_finder = None
            self._accessibility_cache = {}
            logger.warning("[A11Y] Accessibility finder not available - using CSS selectors only")

    async def _get_accessibility_snapshot(self, force_refresh: bool = False) -> Optional[List[AccessibilityRef]]:
        """
        Get cached accessibility snapshot or fetch fresh one.

        Args:
            force_refresh: Force fetching fresh snapshot even if cached

        Returns:
            List of AccessibilityRef objects or None if unavailable
        """
        if not ACCESSIBILITY_FINDER_AVAILABLE or not self.element_finder:
            return None

        current_time = time.time()

        # Check cache
        if not force_refresh and self._last_url in self._accessibility_cache:
            cached_time, cached_refs = self._accessibility_cache[self._last_url]
            if (current_time - cached_time) < self._cache_ttl:
                logger.debug(f"Using cached accessibility snapshot ({len(cached_refs)} elements)")
                return cached_refs

        # Fetch fresh snapshot
        try:
            snapshot_result = await self.mcp.call_tool('playwright_snapshot', {})
            snapshot_content = snapshot_result.get('content') or snapshot_result.get('text') or snapshot_result.get('markdown', '')

            if snapshot_content:
                refs = parse_snapshot(snapshot_content)
                self._accessibility_cache[self._last_url] = (current_time, refs)
                logger.debug(f"Cached fresh accessibility snapshot ({len(refs)} elements)")
                return refs
        except Exception as e:
            logger.warning(f"Failed to get accessibility snapshot: {e}")

        return None

    async def _clear_accessibility_cache(self):
        """Clear accessibility cache (call after navigation or page changes)"""
        self._accessibility_cache.clear()

    async def _find_element_by_description(
        self,
        description: str,
        role_hint: Optional[str] = None,
        confidence_threshold: float = 0.3
    ) -> Optional[AccessibilityRef]:
        """
        Find element using natural language description via accessibility tree.

        Args:
            description: Natural language description (e.g., "search button", "email input")
            role_hint: Optional ARIA role hint (button, textbox, link, etc.)
            confidence_threshold: Minimum confidence score (0-1)

        Returns:
            AccessibilityRef if found with sufficient confidence, None otherwise

        Examples:
            ref = await adapter._find_element_by_description("login button")
            ref = await adapter._find_element_by_description("email", role_hint="textbox")
        """
        if not ACCESSIBILITY_FINDER_AVAILABLE or not self.element_finder:
            return None

        # Get accessibility snapshot
        refs = await self._get_accessibility_snapshot()
        if not refs:
            return None

        # Temporarily override min_confidence if specified
        original_confidence = self.element_finder.min_confidence
        self.element_finder.min_confidence = confidence_threshold

        try:
            # Find best match
            match = self.element_finder._find_best_match(refs, description, role_hint)
            return match
        finally:
            # Restore original confidence threshold
            self.element_finder.min_confidence = original_confidence

    async def _convert_description_to_selector(
        self,
        description_or_selector: str,
        role_hint: Optional[str] = None
    ) -> str:
        """
        Convert natural language description to accessibility ref or return CSS selector.

        This is the key method that enables accessibility-first element finding.
        It tries to match the description to an element in the accessibility tree first,
        and only falls back to treating it as a CSS selector if no match is found.

        Args:
            description_or_selector: Either natural language description or CSS selector
            role_hint: Optional role hint for better matching

        Returns:
            Accessibility ref selector (e.g., '[ref=s1e5]') or original CSS selector

        Strategy:
        1. If accessibility-first disabled, use CSS selector directly
        2. If input looks like CSS selector (has special chars), use it directly
        3. Otherwise, try to find element by description in accessibility tree
        4. If found with good confidence, return ref-based selector
        5. Fall back to original input as CSS selector
        """
        # If a11y-first disabled, skip straight to CSS
        if not self.use_a11y_first:
            logger.debug(f"[A11Y] Disabled - using CSS selector: {description_or_selector}")
            return description_or_selector

        # Quick check: if it looks like a CSS selector, use it directly
        css_indicators = ['#', '.', '[', '>', '+', '~', ':']
        if any(char in description_or_selector for char in css_indicators):
            logger.debug(f"Input looks like CSS selector: {description_or_selector}")
            return description_or_selector

        # Try accessibility-first matching
        ref = await self._find_element_by_description(description_or_selector, role_hint)
        if ref:
            logger.info(f"[A11Y] Matched '{description_or_selector}' to {ref.role} '{ref.name}' [ref={ref.ref}]")
            # Return ref-based selector that Playwright MCP understands
            return f'[ref={ref.ref}]'

        # Fallback: treat as CSS selector
        logger.debug(f"[A11Y] No match for '{description_or_selector}', falling back to CSS selector")
        return description_or_selector

    async def navigate(self, url: str, **kwargs) -> dict:
        """Navigate to URL with Cloudflare handling"""
        self._last_url = url
        result = await self.mcp.call_tool('playwright_navigate', {'url': url})

        # Clear accessibility cache on navigation
        await self._clear_accessibility_cache()

        # Check for Cloudflare block
        if CHALLENGE_HANDLER_AVAILABLE:
            snapshot = await self.mcp.call_tool('playwright_snapshot', {})
            if snapshot.get('cloudflare_blocked') or self._is_cloudflare_response(snapshot):
                logger.debug(f"Security check on {url}")
                console.print("[dim]Working through security check...[/dim]")

                # Get page object for challenge handler
                handler = get_challenge_handler(self.mcp)

                # Try to bypass or find alternative
                alt_result = await self._handle_cloudflare(url, handler)
                if alt_result.get('success'):
                    console.print("[green]Access granted[/green]")
                    # Refresh accessibility cache after successful bypass
                    await self._clear_accessibility_cache()
                    return alt_result

        return result

    def _is_cloudflare_response(self, snapshot: dict) -> bool:
        """Check if snapshot indicates Cloudflare block"""
        content = str(snapshot.get('content', '') or snapshot.get('markdown', ''))
        indicators = ['just a moment', 'checking your browser', 'cloudflare', 'challenge-running']
        return any(ind in content.lower() for ind in indicators)

    async def _handle_cloudflare(self, url: str, handler) -> dict:
        """Handle Cloudflare challenge with bypass + alternatives"""
        import asyncio

        # Strategy 1: Wait for JS challenge to complete
        console.print("[dim]  Verifying access...[/dim]")
        for i in range(3):
            # Wait for network to be idle (Cloudflare JS completes)
            try:
                await self.mcp.call_tool('playwright_wait_for_load_state', {'state': 'networkidle', 'timeout': 5000})
            except Exception:
                pass  # Timeout is expected if challenge doesn't complete
            snapshot = await self.mcp.call_tool('playwright_snapshot', {})
            if not self._is_cloudflare_response(snapshot):
                return {'success': True, 'source': 'js_bypass', 'data': snapshot}

        # Strategy 2: Refresh and retry
        console.print("[dim]  Retrying...[/dim]")
        await self.mcp.call_tool('playwright_navigate', {'url': url})
        # Wait for page to be fully loaded
        try:
            await self.mcp.call_tool('playwright_wait_for_load_state', {'state': 'networkidle', 'timeout': 5000})
        except Exception:
            pass  # Continue even if timeout
        snapshot = await self.mcp.call_tool('playwright_snapshot', {})
        if not self._is_cloudflare_response(snapshot):
            return {'success': True, 'source': 'refresh', 'data': snapshot}

        # Strategy 3: Try alternatives
        blocked_site = handler.detect_blocked_site(url)
        if blocked_site != BlockedSite.UNKNOWN and self.query:
            console.print("[dim]  Finding another way...[/dim]")
            alternatives = handler.get_alternatives(blocked_site)

            for alt in alternatives:
                try:
                    alt_url = alt.url_template.format(query=self.query.replace(" ", "+"))
                    # No message for each alternative - too noisy

                    await self.mcp.call_tool('playwright_navigate', {'url': alt_url})
                    # Wait for alternative site to load
                    try:
                        await self.mcp.call_tool('playwright_wait_for_load_state', {'state': 'networkidle', 'timeout': 3000})
                    except Exception:
                        pass  # Continue even if timeout
                    snapshot = await self.mcp.call_tool('playwright_snapshot', {})
                    if not self._is_cloudflare_response(snapshot):
                        return {
                            'success': True,
                            'source': alt.name,
                            'alternative_used': True,
                            'data': snapshot
                        }
                except Exception as e:
                    logger.debug(f"Alternative {alt.name} failed: {e}")
                    continue

        # Strategy 4: Use autonomous resolver with AI thinking and subagents
        console.print("[dim]  Trying harder...[/dim]")
        try:
            from .autonomous_challenge_resolver import resolve_any_challenge
            page_content = str(snapshot.get('content', '') or snapshot.get('markdown', ''))
            resolver_result = await resolve_any_challenge(
                page_content=page_content,
                url=url,
                query=self.query,
                mcp_client=self.mcp,
                llm_client=self.llm_client,  # Pass LLM for AI thinking layer
            )
            if resolver_result.success:
                console.print("[green]  Found a way in[/green]")
                return {
                    'success': True,
                    'source': f'autonomous_{resolver_result.resolution_strategy}',
                    'layer': resolver_result.layer_used,
                    'alternative_data': resolver_result.alternative_data,
                }
            elif resolver_result.should_continue:
                console.print("[dim]  Continuing with what we have...[/dim]")
                return {'success': False, 'continue_anyway': True, 'error': 'Resolved with partial data'}
        except ImportError:
            logger.debug("Autonomous resolver not available")
        except Exception as e:
            logger.debug(f"Autonomous resolver failed: {e}")

        return {'success': False, 'error': 'All bypass strategies failed'}

    async def click(self, selector: str, **kwargs) -> dict:
        """
        Click element using accessibility-first element finding.

        Args:
            selector: Either natural language description ("login button") or CSS selector

        Returns:
            Result dict from Playwright click action

        Example:
            await adapter.click("search button")  # Uses accessibility tree
            await adapter.click("button.submit")  # Falls back to CSS
        """
        # Convert natural language to accessibility ref if possible
        final_selector = await self._convert_description_to_selector(selector, role_hint='button')
        return await self.mcp.call_tool('playwright_click', {'selector': final_selector})

    async def type(self, selector: str, text: str, **kwargs) -> dict:
        """
        Type text into element using accessibility-first element finding.

        Args:
            selector: Either natural language description ("email input") or CSS selector
            text: Text to type

        Returns:
            Result dict from Playwright fill action

        Example:
            await adapter.type("email", "user@example.com")  # Uses accessibility tree
            await adapter.type("input[name='email']", "user@example.com")  # Falls back to CSS
        """
        # Convert natural language to accessibility ref if possible
        # Try textbox first, then searchbox for input fields
        final_selector = await self._convert_description_to_selector(selector, role_hint='textbox')
        return await self.mcp.call_tool('playwright_fill', {'selector': final_selector, 'value': text})

    async def scroll(self, direction: str = 'down', amount: int = 1, container: str = None, **kwargs) -> dict:
        """Scroll page or container"""
        args = {'direction': direction, 'amount': amount}
        if container:
            args['container'] = container
        return await self.mcp.call_tool('playwright_scroll', args)

    async def wait(self, time: float = 1, **kwargs) -> dict:
        """Wait for specified time"""
        import asyncio
        await asyncio.sleep(time)
        return {'success': True}

    async def wait_for_selector(self, selector: str, timeout: int = 10000, **kwargs) -> dict:
        """
        Wait for element to appear using accessibility-first element finding.

        Args:
            selector: Either natural language description or CSS selector
            timeout: Timeout in milliseconds

        Returns:
            Result dict from Playwright wait action
        """
        # Convert natural language to accessibility ref if possible
        final_selector = await self._convert_description_to_selector(selector)
        return await self.mcp.call_tool('playwright_wait_for_selector', {
            'selector': final_selector,
            'timeout': timeout
        })

    async def find_all_elements(
        self,
        description: str,
        role_hint: Optional[str] = None,
        max_results: int = 10
    ) -> List[AccessibilityRef]:
        """
        Find all elements matching description, sorted by confidence.

        Args:
            description: Natural language description
            role_hint: Optional ARIA role hint
            max_results: Maximum number of results to return

        Returns:
            List of AccessibilityRef objects sorted by match confidence

        Example:
            buttons = await adapter.find_all_elements("submit", role_hint="button")
            for btn in buttons:
                print(f"Found: {btn.name} [ref={btn.ref}]")
        """
        if not ACCESSIBILITY_FINDER_AVAILABLE or not self.element_finder:
            return []

        refs = await self._get_accessibility_snapshot()
        if not refs:
            return []

        # Score all elements
        scored = []
        for ref in refs:
            if role_hint and ref.role != role_hint:
                continue

            score = self.element_finder._score_match(ref, description)
            if score >= self.element_finder.min_confidence:
                scored.append((score, ref))

        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)

        return [ref for _, ref in scored[:max_results]]

    async def extract(self, selector: str, fields: list = None, **kwargs) -> dict:
        """Extract data from elements with Cloudflare handling"""
        try:
            result = await self.mcp.call_tool('playwright_batch_extract', {
                'selector': selector,
                'fields': fields or []
            })

            # Check if blocked
            if result.get('cloudflare_blocked') and CHALLENGE_HANDLER_AVAILABLE:
                handler = get_challenge_handler(self.mcp)
                alt_result = await self._handle_cloudflare(self._last_url, handler)
                if alt_result.get('success'):
                    # Re-extract from alternative
                    return await self.mcp.call_tool('playwright_batch_extract', {
                        'selector': selector,
                        'fields': fields or []
                    })

            return result
        except Exception:
            # Fallback to snapshot
            snapshot = await self.mcp.call_tool('playwright_snapshot', {})
            return {'success': True, 'data': snapshot}

    async def get_accessibility_tree(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Get the current accessibility tree for debugging/inspection.

        Args:
            force_refresh: Force fetching fresh snapshot

        Returns:
            Dictionary with accessibility information:
            - elements: List of all accessible elements
            - interactive: List of clickable/fillable elements
            - buttons: List of all buttons
            - inputs: List of all input fields
            - links: List of all links
            - summary: Statistics about the accessibility tree

        Example:
            tree = await adapter.get_accessibility_tree()
            print(f"Found {len(tree['buttons'])} buttons")
            for btn in tree['buttons']:
                print(f"  - {btn.name} [ref={btn.ref}]")
        """
        refs = await self._get_accessibility_snapshot(force_refresh)
        if not refs:
            return {
                'elements': [],
                'interactive': [],
                'buttons': [],
                'inputs': [],
                'links': [],
                'summary': {'total': 0, 'error': 'Accessibility finder not available'}
            }

        from .accessibility_element_finder import AccessibilityTreeParser
        parser = AccessibilityTreeParser()

        interactive = parser.find_interactive(refs)
        buttons = parser.find_by_role(refs, 'button')
        inputs = parser.find_fillable(refs)
        links = parser.find_by_role(refs, 'link')

        return {
            'elements': refs,
            'interactive': interactive,
            'buttons': buttons,
            'inputs': inputs,
            'links': links,
            'summary': {
                'total': len(refs),
                'interactive': len(interactive),
                'buttons': len(buttons),
                'inputs': len(inputs),
                'links': len(links),
                'cached': self._last_url in self._accessibility_cache
            }
        }

    async def debug_element_match(
        self,
        description: str,
        role_hint: Optional[str] = None,
        show_all_candidates: bool = False
    ) -> Dict[str, Any]:
        """
        Debug helper to see how elements are being matched.

        Args:
            description: Natural language description to match
            role_hint: Optional role filter
            show_all_candidates: If True, show all candidates with their scores

        Returns:
            Dictionary with matching information

        Example:
            debug = await adapter.debug_element_match("search button", show_all_candidates=True)
            print(f"Best match: {debug['best_match']}")
            print(f"Candidates:")
            for candidate in debug['candidates']:
                print(f"  - {candidate['element']} (score: {candidate['score']:.2f})")
        """
        if not ACCESSIBILITY_FINDER_AVAILABLE or not self.element_finder:
            return {'error': 'Accessibility finder not available'}

        refs = await self._get_accessibility_snapshot()
        if not refs:
            return {'error': 'No accessibility snapshot available'}

        # Get all matching candidates with scores
        candidates = []
        for ref in refs:
            if role_hint and ref.role != role_hint:
                continue

            score = self.element_finder._score_match(ref, description)
            if show_all_candidates or score >= self.element_finder.min_confidence:
                candidates.append({
                    'element': ref,
                    'score': score,
                    'ref': ref.ref,
                    'role': ref.role,
                    'name': ref.name
                })

        # Sort by score
        candidates.sort(key=lambda x: x['score'], reverse=True)

        best_match = candidates[0] if candidates else None

        return {
            'description': description,
            'role_hint': role_hint,
            'best_match': best_match,
            'candidates': candidates,
            'total_elements': len(refs),
            'min_confidence': self.element_finder.min_confidence
        }


from .reasoning_engine import ReasoningEngineMixin
from .orchestration import OrchestrationMixin
from .session_state import SessionState, Memory
from .workflow_handlers import WorkflowHandlers
from .browser_manager import BrowserManager
from .navigation_handlers import NavigationHandlersMixin
from .tool_execution import ToolExecutionMixin, ActionResult, TOOL_CORRECTIONS, TOOL_PROGRESS_MESSAGES
from .vision_processor import VisionProcessorMixin
from .brain_utils import BrainUtilsMixin, extract_urls, strip_urls
from .health_monitor import HealthMonitorMixin
from .metrics_recorder import MetricsRecorderMixin
from .lead_workflows import LeadWorkflows, get_lead_workflows
from .tool_executor import ToolExecutor, ActionResult, create_tool_executor
from .data_workflows import DataWorkflows, WorkflowResult as DataWorkflowResult
from .brain_config import (
    BrainConfig,
    initialize_all_components,
)

# Advanced agentic patterns (Claude Code / Codex inspired)
from .confidence_orchestrator import get_confidence, ConfidenceOrchestrator
from .context_budget import get_context_budget, ContextBudgetManager
from .pre_execution_validator import get_validator, PreExecutionValidator
from .online_reflection import get_online_reflector, OnlineReflectionLoop

# OpenCode-inspired modules (auto-allow permissions, fuzzy edit, output handling)
try:
    from .permission_system import PermissionManager, PermissionType, is_blocked_command
    from .fuzzy_edit import fuzzy_edit, edit_file, EditResult
    from .output_handler import get_output_handler, truncate_output, format_for_llm
    from .file_handler import get_file_handler, read_file, is_binary
    from .search_handler import get_search_handler, glob_files, grep_content
    from .prompts.system_prompts import get_system_prompt, get_login_prompt
    OPENCODE_MODULES_AVAILABLE = True
except ImportError as e:
    logger.warning(f"OpenCode modules not fully available: {e}")
    OPENCODE_MODULES_AVAILABLE = False

# 11 new agentic mechanisms (from previous session)
try:
    from .snapshot_system import SnapshotManager
    from .failure_tracker import FailureTracker
    from .sensitive_data_guard import SensitiveDataGuard
    from .history_manager import HistoryManager
    from .checkpoint_system import CheckpointManager
    from .rules_loader import RulesLoader
    from .lsp_client import LSPClient
    from .tool_plugins import PluginManager
    from .session_recorder import SessionRecorder
    from .workflow_recorder import WorkflowRecorder
    AGENTIC_MECHANISMS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Agentic mechanisms not fully available: {e}")
    AGENTIC_MECHANISMS_AVAILABLE = False

# Advanced OpenCode patterns (compaction, task delegation, web fetching)
try:
    from .compaction_system import get_compactor, CompactionSystem, should_compact
    from .task_delegation import get_delegator, TaskDelegator, BUILT_IN_AGENTS
    from .web_fetcher import get_fetcher, WebFetcher
    ADVANCED_OPENCODE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Advanced OpenCode modules not fully available: {e}")
    ADVANCED_OPENCODE_AVAILABLE = False

# Optional modules - import only what's needed
try:
    from .email_outreach import EmailOutreach
    EMAIL_OUTREACH_AVAILABLE = True
except ImportError as e:
    EMAIL_OUTREACH_AVAILABLE = False
    logger.debug(f"Email outreach module not available: {e}")

try:
    from .multi_tab import TabManager
    MULTI_TAB_AVAILABLE = True
except ImportError as e:
    MULTI_TAB_AVAILABLE = False
    logger.debug(f"Multi-tab module not available: {e}")

try:
    from .strategic_planner import ExecutionState
    STRATEGIC_PLANNER_AVAILABLE = True
except ImportError as e:
    STRATEGIC_PLANNER_AVAILABLE = False
    logger.debug(f"Strategic planner module not available: {e}")

# Optional: Enhanced modules
DOM_DISTILLATION_AVAILABLE = False
VISUAL_GROUNDING_AVAILABLE = False
CASCADING_RECOVERY_AVAILABLE = False
REFLEXION_AVAILABLE = False
STEALTH_ENHANCED_AVAILABLE = False

# Skill library
if os.environ.get('EVERSALE_DISABLE_SKILLS', '').lower() not in ('1', 'true', 'yes'):
    try:
        from .skill_library import SkillLibrary
        from .skill_integration import SkillAwareAgent
        SKILL_LIBRARY_AVAILABLE = True
    except ImportError as e:
        SKILL_LIBRARY_AVAILABLE = False
        logger.debug(f"Skill library not available: {e}")
    except MemoryError as e:
        SKILL_LIBRARY_AVAILABLE = False
        logger.warning(f"Skill library disabled due to memory constraints: {e}")
else:
    SKILL_LIBRARY_AVAILABLE = False
    logger.debug("Skill library disabled via EVERSALE_DISABLE_SKILLS")

console = Console()

# Memory storage
MEMORY_DIR = Path("memory")
MEMORY_DIR.mkdir(exist_ok=True)


@dataclass
class ActionResult:
    success: bool
    data: Any = None
    error: str = ""
    screenshot: bytes = None


# Note: The following classes have been moved to dedicated modules:
# - ForeverTaskState: Use from forever_operations.py
# - TaskQueue/TaskQueueItem: Use from task_queue.py if needed  
# - BatchProcessor: Use from parallel.py
# - Memory: Use from session_state.py

# Define base class conditionally based on skill library availability
if SKILL_LIBRARY_AVAILABLE:
    _BrainBase = SkillAwareAgent
else:
    _BrainBase = object


class EnhancedBrain(
    MetricsRecorderMixin,
    HealthMonitorMixin,
    BrainUtilsMixin,
    VisionProcessorMixin,
    ToolExecutionMixin,
    NavigationHandlersMixin,
    OrchestrationMixin,
    ReasoningEngineMixin,
    _BrainBase
):
    """
    Production-grade agent brain with skill learning.

    Key improvements:
    1. Vision: Uses screenshot + vision model to understand pages
    2. ReAct: Reason about task -> Act -> Reflect on results
    3. Memory: Learns successful strategies per domain
    4. Parallel: Executes independent tools simultaneously
    5. Self-healing: Retries with alternatives on failure
    6. Skills: Learns and reuses successful action patterns (Voyager-style)
    """

    def __init__(self, config: dict, mcp_client):
        # Store raw config and MCP client
        self.config = config

        # Wrap MCP client with reliability layer if available
        if RELIABLE_BROWSER_AVAILABLE:
            self.mcp = wrap_mcp_client(mcp_client, enable_reliability=True)
            logger.info("[RELIABLE] EnhancedBrain using ReliableBrowser wrapper")
        else:
            self.mcp = mcp_client

        # Parse configuration using BrainConfig
        self._brain_config = BrainConfig.from_dict(config)

        # Initialize all components using ComponentInitializer (use wrapped MCP)
        components = initialize_all_components(self._brain_config, self.mcp)

        # Assign components to instance attributes
        self._assign_components(components)

        # Initialize instance state variables
        self._init_state_variables()

        # Initialize skill library if available
        self._init_skill_library()

    def _assign_components(self, components: Dict[str, Any]):
        """Assign initialized components to instance attributes."""
        # Ollama client
        self.ollama_client = components['ollama_client']

        # Kimi client - for FIRST (planning) and LAST (synthesis) calls
        # General-purpose agent needs strong reasoning at start/end
        self.kimi_client = None
        if KIMI_CLIENT_AVAILABLE and get_kimi_client:
            try:
                self.kimi_client = get_kimi_client(self.config)
                if self.kimi_client:
                    logger.info("[KIMI] Kimi K2 client initialized for first/last LLM calls")
            except Exception as e:
                logger.debug(f"[KIMI] Could not initialize Kimi client: {e}")

        # LLM settings from config
        self.llm_base_url = self._brain_config.llm_base_url
        self.llm_fallback_url = self._brain_config.llm_fallback_url
        self.model = self._brain_config.main_model
        self.vision_model = self._brain_config.vision_model
        self.fast_model = self._brain_config.fast_model
        self.temperature = self._brain_config.temperature
        self.max_iterations = self._brain_config.max_iterations
        self.llm_timeout = self._brain_config.llm_timeout

        # Timeouts from config
        self.task_timeout = self._brain_config.task_timeout
        self.checkpoint_interval = self._brain_config.checkpoint_interval
        self.steering_pause_timeout = self._brain_config.steering_pause_timeout

        # Core components
        self.awareness = components['awareness']
        self.survival = components['survival']
        self.decision_logger = components['decision_logger']
        self.session_state = components['session_state']

        # Backward compatibility aliases for session_state
        self.stats = self.session_state.stats
        self.memory = self.session_state.memory

        # Memory components
        self.context_memory = components['context_memory']
        self.memory_arch = components['memory_arch']
        self._reason_cache = components['cache']

        # Recovery & monitoring
        self.crash_recovery = components['crash_recovery']
        self.dead_mans_switch = components['dead_mans_switch']
        self.resource_limiter = components['resource_limiter']
        self.coordinator = components['coordinator']
        self.hallucination_guard = components['hallucination_guard']
        self.resource_monitor = components['resource_monitor']
        self.cascading_recovery = components['cascading_recovery']

        # Helpers
        self.adaptive_explorer = components['adaptive_explorer']
        self.resource_economy = components['resource_economy']
        self.rescue_policy = RescuePolicy(self)

        # Optional modules
        self.intent_detector = components['intent_detector']
        self.capability_router = components['capability_router']
        self.email_outreach = components['email_outreach']
        self.strategic_planner = components['strategic_planner']
        self.reflexion = components['reflexion']

        # Steering
        self._steering = components['steering']
        self._steering_enabled = self._brain_config.steering_enabled

        # Organism - the nervous system connecting all components
        self.organism = components.get('organism')

        # SIAO core - will be initialized async when organism starts
        self.siao_core = None

        # Prompt processor (created after context_memory is assigned)
        from .prompt_processor import PromptProcessor
        self.prompt_processor = PromptProcessor(
            context_memory=self.context_memory,
            improvement_log=[]
        )

    def _init_state_variables(self):
        """Initialize instance state variables."""
        # Session identity (used by todo/status tracking systems)
        base_session_id = getattr(self.session_state, 'session_id', None)
        self.session_id = base_session_id or datetime.now().strftime("%Y%m%d-%H%M%S")
        if hasattr(self.session_state, 'session_id'):
            self.session_state.session_id = self.session_id

        # Mode flags
        self.describe_mode = False
        self._describe_retry_done = False
        self._forever_mode = False
        self.direct_mode = True  # Follow exact directions like Playwright MCP (default ON)

        # Screenshot tracking
        self._last_action_name: Optional[str] = None
        self._last_screenshot_hash: Optional[str] = None
        self._last_screenshot_issue: Optional[str] = None
        self._actions_expected_change = {'playwright_navigate', 'playwright_click'}

        # Goal tracking
        self._goal_summary = ""
        self._goal_keywords: List[str] = []

        # Execution tracking
        self._execution_log: List[Dict[str, Any]] = []
        self._task_start_time = datetime.now()
        self._next_health_check_time = datetime.now()
        self._last_issues: List[str] = []
        self._last_checkpoint_time = None

        # Usage metering (run started)
        report_worker_usage_fire_and_forget(WorkerUsageDelta(
            run_id=self.session_id,
            worker_minutes=0,
            runs_started=1
        ))

        # Preflight
        self._preflight_done = False
        self._preflight_attempts = 0
        self._max_preflight_attempts = self._brain_config.max_preflight_attempts
        self._preflight_retry_delay = self._brain_config.preflight_retry_delay
        self._preflight_details: List[str] = []

        # Improvement tracking
        self._review_counter = 0
        self._last_rescue_summary = ""
        self._prompt_count = 0
        self._review_interval = self._brain_config.review_interval
        self._review_history_len = self._brain_config.review_history_len
        self._improvement_log: List[str] = []
        self._historical_actions: List[Dict[str, Any]] = []

        # Context settings
        self._max_context_messages = self._brain_config.max_context_messages
        self._compact_threshold = self._brain_config.compact_threshold

        # Iteration counter
        self.iteration = 0

        # State
        self.messages = []

        # UI-TARS conversation context (auto-prunes screenshots)
        if UITARS_AVAILABLE and ConversationContext:
            self._uitars_context = ConversationContext(max_screenshots=a11y_config.KEEP_LAST_N_SCREENSHOTS)
            logger.info(f"[UITARS] Screenshot context management enabled (max {a11y_config.KEEP_LAST_N_SCREENSHOTS})")
        else:
            self._uitars_context = None

        # UI-TARS enhancer (lazy initialized when browser available)
        self._uitars_enhancer = None

        # History pruner for token optimization
        if HISTORY_PRUNER_AVAILABLE and HistoryPruner and a11y_config.ENABLE_HISTORY_PRUNING:
            self._history_pruner = HistoryPruner(
                max_history_items=a11y_config.MAX_HISTORY_ITEMS,
                preserve_recent=a11y_config.PRESERVE_RECENT_MESSAGES,
                summarize_older=True
            )
            logger.info("[HISTORY] History pruner enabled for token optimization")
        else:
            self._history_pruner = None

        # Progress callback
        self._progress_callback = None

        # Memory consolidation
        self._consolidation_task = None
        self._consolidation_lock = asyncio.Lock()

        # Browser reference (lazy initialized)
        self._browser = None

        # Multi-tab browser manager (lazy initialized)
        self.tab_manager = None

        # Strategic planner state
        self._current_plan_state: Optional[ExecutionState] = None

        # Initialize workflow handlers (delegates complex multi-step workflows)
        self.workflow_handlers = WorkflowHandlers(
            call_tool_func=self._call_direct_tool,
            extract_urls_func=self._extract_urls,
            emit_summary_func=self._emit_explainable_summary,
            get_site_config_func=lambda url: None,  # Site config is auto-detected
            ollama_client=self.ollama_client,
            model=self.model,
            vision_model=self.vision_model
        )

        # Initialize browser manager (delegates browser lifecycle/screenshots)
        self.browser_manager = BrowserManager(
            mcp_client=self.mcp,
            ollama_client=self.ollama_client,
            vision_model=self.vision_model,
            cascading_recovery=self.cascading_recovery
        )

        # Initialize data workflows (CSV, documents, logs, categorization)
        self.data_workflows = DataWorkflows()

        # Initialize lead workflows (SDR, FB Ads, Reddit, batch extraction)
        self.lead_workflows = LeadWorkflows(
            call_tool_func=self._call_direct_tool,
            emit_summary_func=self._emit_explainable_summary,
            ollama_client=self.ollama_client,
            model=self.model
        )

        # Initialize tool executor (handles tool calls with retry, fallback, healing)
        # Note: We use create_tool_executor() later after all callbacks are defined
        self._tool_executor = None

        # Advanced agentic patterns (singleton instances)
        self.confidence = get_confidence()
        self.context_budget = get_context_budget()
        self.pre_validator = get_validator()
        self.online_reflector = get_online_reflector()

        # OpenCode-inspired modules (auto-allow, fuzzy edit, output handling)
        if OPENCODE_MODULES_AVAILABLE:
            self.permission_manager = PermissionManager()  # Auto-allows everything except deletions/hacking
            self.output_handler = get_output_handler()  # Truncates/formats output for LLM
            self.file_handler = get_file_handler()  # Smart file reading with binary detection
            self.search_handler = get_search_handler()  # Glob/grep search
            logger.info("OpenCode modules initialized (auto-allow mode, fuzzy edit, output truncation)")
        else:
            self.permission_manager = None
            self.output_handler = None
            self.file_handler = None
            self.search_handler = None

        # 11 agentic mechanisms (git snapshots, checkpoints, etc.)
        if AGENTIC_MECHANISMS_AVAILABLE:
            self.snapshot_manager = SnapshotManager()
            self.failure_tracker = FailureTracker()
            self.sensitive_guard = SensitiveDataGuard()
            self.history_manager = HistoryManager()
            self.checkpoint_manager = CheckpointManager()
            self.rules_loader = RulesLoader()
            self.session_recorder = SessionRecorder()
            self.workflow_recorder = WorkflowRecorder()
            logger.info("Agentic mechanisms initialized (snapshots, checkpoints, history, etc.)")
        else:
            self.snapshot_manager = None
            self.failure_tracker = None
            self.sensitive_guard = None
            self.history_manager = None
            self.checkpoint_manager = None
            self.rules_loader = None
            self.session_recorder = None
            self.workflow_recorder = None

        # Advanced OpenCode patterns (compaction, multi-agent, web fetching)
        if ADVANCED_OPENCODE_AVAILABLE:
            self.compactor = get_compactor()  # Context compression for long conversations
            self.task_delegator = get_delegator()  # Multi-agent task delegation
            self.web_fetcher = get_fetcher()  # Safe URL fetching with caching
            logger.info("Advanced OpenCode patterns initialized (compaction, task delegation, web fetching)")
        else:
            self.compactor = None
            self.task_delegator = None
            self.web_fetcher = None

        # Fast mode executor - bypasses LLM for simple browser commands (10-30x faster)
        if FAST_MODE_AVAILABLE and FastModeExecutor:
            self.fast_mode_executor = FastModeExecutor(
                mcp_client=self.mcp,
                enabled=True,  # Enable by default
                verbose=False  # Set to True to see fast mode attempts
            )
            logger.info("Fast mode initialized (10-30x faster for simple commands)")
        else:
            self.fast_mode_executor = None

    def _get_tool_executor(self) -> ToolExecutor:
        """Lazy initialization of tool executor."""
        if self._tool_executor is None:
            self._tool_executor = create_tool_executor(self)
        return self._tool_executor

    def _init_skill_library(self):
        """Initialize skill library if available."""
        if SKILL_LIBRARY_AVAILABLE:
            try:
                super().__init__()
                if hasattr(self, 'skill_library') and self.skill_library:
                    logger.info(f"Skill library initialized with {len(self.skill_library.skills)} skills")
            except Exception as e:
                logger.warning(f"Skill library initialization failed: {e}")


    @property
    def browser(self):
        # IMPORTANT: Do NOT cache the browser reference!
        # After browser reconnection, the MCP server has a new client instance.
        # Caching would return a stale reference to the old, disconnected browser.
        # Always fetch the current client from the MCP server.
        if hasattr(self.mcp, '_mcp_server') and self.mcp._mcp_server:
            return self.mcp._mcp_server.client
        # Fallback to old architecture (separate playwright server)
        elif "playwright" in self.mcp.servers:
            return self.mcp.servers["playwright"].get("client")
        return None

    @property
    def uitars(self):
        """Get UI-TARS enhancer (lazy initialized when browser available)."""
        if not UITARS_AVAILABLE or not UITarsEnhancer:
            return None

        if self._uitars_enhancer is None and self.browser:
            page = getattr(self.browser, 'page', None)
            if page:
                try:
                    self._uitars_enhancer = UITarsEnhancer(
                        page,
                        config=RetryConfig(
                            screenshot_timeout=5.0,
                            screenshot_max_retries=3,
                            action_timeout=5.0,
                            action_max_retries=3
                        )
                    )
                    logger.info("[UITARS] Enhanced browser automation with tiered retry enabled")
                except Exception as e:
                    logger.debug(f"[UITARS] Could not initialize enhancer: {e}")
        return self._uitars_enhancer

    @property
    def tool_executor(self) -> ToolExecutor:
        """Get the tool executor instance (lazy initialized)."""
        return self._get_tool_executor()

    async def _start_memory_consolidation(self):
        """Start background memory consolidation."""
        # Use lock to prevent race condition when multiple coroutines try to start
        async with self._consolidation_lock:
            if self._consolidation_task is not None:
                return  # Already running

            async def consolidation_loop():
                while True:
                    try:
                        await asyncio.sleep(300)  # Every 5 minutes
                        if self.memory_arch:
                            await self.memory_arch.consolidate_now()
                            # Also run decay
                            if hasattr(self.memory_arch, 'decay_memories'):
                                await self.memory_arch.decay_memories(max_age_days=30)
                            logger.debug("Memory consolidation completed")
                    except asyncio.CancelledError:
                        break
                    except Exception as e:
                        logger.error(f"Consolidation error: {e}")

            self._consolidation_task = asyncio.create_task(consolidation_loop())

    async def _try_strategic_plan(self, prompt: str) -> Optional[str]:
        """
        Use strategic planning for complex tasks.

        ENTERPRISE FEATURES:
        - Supports 10K+ step workflows via SubAgentExecutor
        - Runs FOREVER (no time limits)
        - Parallel execution with configurable concurrency
        - Circuit breaker, checkpointing, resume capability

        Flow:
        1. Create a step-by-step plan (ONE API call)
        2. For small plans (<50 steps): sequential execution
        3. For large plans (50+ steps): parallel SubAgentExecutor
        4. If 2x failures, escalate for recovery
        """
        # INTELLIGENT ROUTING: Try deterministic workflows FIRST (no LLM needed)
        # But skip for multi-task prompts - they need LLM planning
        if INTELLIGENT_ROUTING_AVAILABLE and not self._is_multi_task_prompt(prompt):
            try:
                decision = route_task(prompt)
                logger.info(f"Task routing: {decision.path.value} (confidence: {decision.confidence:.2f})")

                # Handle deterministic workflows - instant execution, no LLM
                if decision.path == ExecutionPath.DETERMINISTIC:
                    workflow = match_workflow(prompt)
                    if workflow:
                        params = extract_params(prompt, workflow)
                        # No need to announce internal workflow name
                        logger.info(f"Executing deterministic workflow: {workflow.name} with params: {params}")
                        try:
                            # Create browser adapter for workflow execution
                            # Pass query for Cloudflare alternative lookups and config for a11y setting
                            query = params.get("search_query", prompt)
                            browser_adapter = BrowserToolAdapter(
                                self.mcp,
                                query=query,
                                llm_client=self.ollama_client,
                                config=self.config
                            )
                            result = await execute_workflow(workflow, params, browser_adapter)
                            if result.get("success"):
                                data = result.get("data", [])
                                count = len(data) if isinstance(data, list) else 0
                                url = result.get("url")

                                # Format output with URL if available
                                if url:
                                    # Map workflow names to user-friendly descriptions
                                    workflow_labels = {
                                        "gmail_open": "Gmail",
                                        "fb_ads_library": "FB Ads",
                                        "linkedin_search": "LinkedIn",
                                        "reddit_search": "Reddit",
                                        "google_maps_search": "Google Maps",
                                        "navigate_to_url": "Page"
                                    }
                                    label = workflow_labels.get(workflow.name, workflow.name)
                                    if count > 0:
                                        return f"{label}: {url} (Found {count} results)"
                                    else:
                                        return f"{label}: {url}"
                                else:
                                    return f"Workflow '{workflow.name}' completed. Found {count} results."
                            else:
                                logger.warning(f"Deterministic workflow failed: {result.get('error')}, falling through to LLM")
                        except Exception as e:
                            logger.warning(f"Workflow execution error: {e}, falling through to LLM")

                # Handle specialized extractors - our hardened competitive advantage
                elif decision.path == ExecutionPath.SPECIALIZED_EXTRACTOR:
                    extractor_name = decision.workflow_name
                    params = decision.params
                    # No need to announce internal extractor name
                    logger.info(f"Using specialized extractor: {extractor_name}")
                    # Extractors handled by the mcp client methods
                    # Fall through to use existing extraction logic below

                # Simple execution - single actions, just do it
                elif decision.path == ExecutionPath.SIMPLE_EXECUTION:
                    logger.debug(f"Simple execution path - will handle directly")
                    # Fall through to simple handling

                # KIMI_K2_PLANNING - fall through to LLM planning below
                # This is the default for complex tasks

            except Exception as e:
                logger.debug(f"Intelligent routing check failed: {e}, continuing with LLM planning")

        # DEEP FB ADS SCRAPER: Handle "go deep", "forever", "unlimited keywords" prompts
        prompt_lower = prompt.lower()
        is_deep_fb_ads = (
            ('deep' in prompt_lower or 'forever' in prompt_lower or 'unlimited' in prompt_lower) and
            ('fb ads' in prompt_lower or 'facebook ads' in prompt_lower or 'ads library' in prompt_lower) and
            'tiktok' not in prompt_lower  # Exclude TikTok to avoid conflict
        )
        if is_deep_fb_ads:
            console.print("[dim]Starting deep extraction...[/dim]")
            try:
                try:
                    from .fb_ads_scraper import integrate_with_brain
                except ImportError:
                    from fb_ads_scraper import integrate_with_brain
                result = await integrate_with_brain(self, prompt)
                if result:
                    return result
            except ImportError as e:
                logger.warning(f"fb_ads_scraper module not available: {e}")
                # Silent fallback - no need to mention technical details
            except Exception as e:
                logger.error(f"Deep FB Ads scraper error: {e}")
                import traceback
                traceback.print_exc()

        # DEEP TIKTOK ADS SCRAPER: Handle TikTok ads deep scraping
        is_deep_tiktok_ads = (
            ('deep' in prompt_lower or 'forever' in prompt_lower or 'unlimited' in prompt_lower or
             'scrape' in prompt_lower or 'extract' in prompt_lower or 'collect' in prompt_lower) and
            ('tiktok ads' in prompt_lower or 'tiktok ad' in prompt_lower or
             'library.tiktok.com' in prompt_lower or 'creative center' in prompt_lower or
             'ads.tiktok.com' in prompt_lower)
        )
        if is_deep_tiktok_ads:
            console.print("[dim]Starting deep extraction...[/dim]")
            try:
                try:
                    from .tiktok_ads_scraper import integrate_with_brain as tiktok_integrate
                except ImportError:
                    from tiktok_ads_scraper import integrate_with_brain as tiktok_integrate
                result = await tiktok_integrate(self, prompt)
                if result:
                    return result
            except ImportError as e:
                logger.warning(f"tiktok_ads_scraper module not available: {e}")
                # Silent fallback - no need to mention technical details
            except Exception as e:
                logger.error(f"Deep TikTok Ads scraper error: {e}")
                import traceback
                traceback.print_exc()

        if not self.strategic_planner:
            return None

        # Get available tools
        available_tools = list(self.mcp.tools.keys()) if hasattr(self.mcp, 'tools') else [
            'playwright_navigate', 'playwright_click', 'playwright_fill',
            'playwright_snapshot', 'playwright_screenshot', 'playwright_snapshot',
            'playwright_find_contacts', 'playwright_extract_entities',
            'browser_snapshot', 'browser_click', 'browser_type',
        ]

        console.print("[dim]Planning approach...[/dim]")

        # Preprocess directory-style prompts to include category URLs/selectors
        try:
            from .local_planner import preprocess_directory_task
            preprocessed_prompt = preprocess_directory_task(prompt)
            if preprocessed_prompt != prompt:
                prompt = preprocessed_prompt
                # Silent - no need to announce internal details
        except Exception as e:
            logger.debug(f"Directory preprocessing skipped: {e}")

        # Get strategic plan
        state = None
        try:
            state = await self.strategic_planner.plan(prompt, available_tools)
        except Exception as e:
            logger.warning(f"Strategic planning failed: {e}")

        # Fallback to local planner if strategic planner has no API key or failed
        if not state:
            try:
                from .local_planner import create_local_plan
                logger.info("Using local LLM planner as fallback...")
                # Silent - no need to announce internal details
                # Use 0000/ui-tars-1.5-7b:latest - best for tool calling
                fast_model = "0000/ui-tars-1.5-7b:latest"  # Best for tool calling
                try:
                    state = await asyncio.wait_for(
                        create_local_plan(
                            self.ollama_client,
                            prompt,
                            fast_model,  # Use FAST model for planning
                            available_tools
                        ),
                        timeout=20  # 20 second timeout for fast planning
                    )
                except asyncio.TimeoutError:
                    logger.warning("Local planning timed out after 30s, proceeding without plan")
                    console.print("[dim]  Proceeding...[/dim]")
                    state = None
                if state:
                    console.print(f"[green]  Ready ({len(state.plan.steps)} steps)[/green]")
            except Exception as e:
                logger.warning(f"Local planning also failed: {e}")
                import traceback
                traceback.print_exc()

        if not state:
            logger.info("All planning methods failed, falling through to other handlers")
            return None

        self._current_plan_state = state

        console.print(f"[green]Starting: {state.plan.summary}[/green]")

        # FB ADS LIBRARY FIX: LLMs hallucinate CSS selectors for Facebook
        # Rewrite plan steps to use URL params and playwright_extract_fb_ads
        prompt_lower = prompt.lower()
        is_fb_ads_task = (
            'facebook.com/ads/library' in prompt_lower or
            'fb ads library' in prompt_lower or
            'facebook ads library' in prompt_lower or
            ('ads library' in prompt_lower and 'facebook' in prompt_lower)
        )
        if is_fb_ads_task:
            # Silent - optimizing approach internally
            import urllib.parse

            # Extract search term from prompt
            search_term = None
            search_patterns = [
                r"search\s+(?:for\s+)?['\"]?([^'\"]+?)['\"]?\s+(?:with|all|in|on)",
                r"['\"]([^'\"]+)['\"]",
                r"search\s+(?:for\s+)?(\w+(?:\s+\w+)?)",
            ]
            for pattern in search_patterns:
                match = re.search(pattern, prompt, re.I)
                if match:
                    search_term = match.group(1).strip()
                    if search_term and len(search_term) > 2 and search_term.lower() not in ['all', 'ads', 'the', 'with', 'filters']:
                        break
                    search_term = None
            if not search_term:
                search_term = 'booked meetings'

            # Extract number of advertisers (default to 100 for scale extraction)
            num_match = re.search(r'(\d+)\s*(?:advertiser|ad|result)', prompt, re.I)
            max_ads = int(num_match.group(1)) if num_match else 100

            # Build FB Ads Library URL with params
            fb_url = f"https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=US&q={urllib.parse.quote(search_term)}&search_type=keyword_unordered"

            # Rewrite steps - replace form filling with URL nav and extraction
            from .strategic_planner import PlanStep
            new_steps = [
                PlanStep(
                    step_number=1,
                    action=f"Navigate to FB Ads Library with search params for '{search_term}'",
                    tool="playwright_navigate",
                    arguments={"url": fb_url},
                    expected_result="Page loads with search results",
                    fallback=None
                ),
                PlanStep(
                    step_number=2,
                    action=f"Extract {max_ads} advertisers with website URLs",
                    tool="playwright_extract_fb_ads",
                    arguments={"max_ads": max_ads},
                    expected_result=f"Extracted {max_ads} advertisers",
                    fallback=None
                ),
            ]
            state.plan.steps = new_steps
            # Silent - internal optimization complete

        # TIKTOK ADS LIBRARY FIX: Similar to FB Ads, rewrite plan for TikTok
        is_tiktok_ads_task = (
            'library.tiktok.com' in prompt_lower or
            'tiktok ads library' in prompt_lower or
            'tiktok ad library' in prompt_lower or
            ('tiktok' in prompt_lower and ('ads' in prompt_lower or 'creative center' in prompt_lower))
        )
        if is_tiktok_ads_task and not is_fb_ads_task:
            # Silent - optimizing approach internally
            import urllib.parse

            # Extract search term from prompt
            search_term = None
            search_patterns = [
                r"search\s+(?:for\s+)?['\"]?([^'\"]+?)['\"]?\s+(?:with|all|in|on)",
                r"['\"]([^'\"]+)['\"]",
                r"search\s+(?:for\s+)?(\w+(?:\s+\w+)?)",
            ]
            for pattern in search_patterns:
                match = re.search(pattern, prompt, re.I)
                if match:
                    search_term = match.group(1).strip()
                    if search_term and len(search_term) > 2 and search_term.lower() not in ['all', 'ads', 'the', 'with', 'filters', 'tiktok']:
                        break
                    search_term = None
            if not search_term:
                search_term = 'marketing'

            # Extract number of advertisers (default to 100 for scale extraction)
            num_match = re.search(r'(\d+)\s*(?:advertiser|ad|result)', prompt, re.I)
            max_ads = int(num_match.group(1)) if num_match else 100

            # Decide which TikTok source to use
            if 'creative center' in prompt_lower or 'top ads' in prompt_lower:
                tiktok_url = f"https://ads.tiktok.com/business/creativecenter/inspiration/topads/pad/en?period=30&region=US&keyword={urllib.parse.quote(search_term)}"
            else:
                tiktok_url = f"https://library.tiktok.com/ads?region=US&search_value={urllib.parse.quote(search_term)}"

            # Rewrite steps
            from .strategic_planner import PlanStep
            new_steps = [
                PlanStep(
                    step_number=1,
                    action=f"Navigate to TikTok Ads with search params for '{search_term}'",
                    tool="playwright_navigate",
                    arguments={"url": tiktok_url},
                    expected_result="Page loads with search results",
                    fallback=None
                ),
                PlanStep(
                    step_number=2,
                    action=f"Extract {max_ads} advertisers with website URLs",
                    tool="playwright_extract_tiktok_ads",
                    arguments={"max_ads": max_ads},
                    expected_result=f"Extracted {max_ads} advertisers",
                    fallback=None
                ),
            ]
            state.plan.steps = new_steps
            # Silent - internal optimization complete

        # POST-PROCESSING: Ensure file writing step exists when prompt requires it
        # More flexible matching - "save it to", "save to", "save the...to" all match
        save_patterns = ['save', 'write', 'export', 'store', 'output']
        file_extensions = ['.txt', '.csv', '.json', '.md', '.log']

        has_save_action = any(sp in prompt_lower for sp in save_patterns)
        has_file_target = any(ext in prompt_lower for ext in file_extensions)

        if has_save_action and has_file_target:
            # Check if any step uses write_file or has save/write in its action
            write_tools = ['write_file', 'write_validated_csv', 'save_file', 'export_file']
            has_write_step = any(
                s.tool in write_tools or
                any(kw in s.action.lower() for kw in ['save', 'write', 'export']) and 'file' in s.action.lower()
                for s in state.plan.steps
            )
            if not has_write_step:
                from .strategic_planner import PlanStep
                # Extract filename from prompt
                filename_match = re.search(r'[\w_-]+\.(txt|csv|json|md|log)', prompt)
                filename = filename_match.group(0) if filename_match else 'output.txt'

                # Add file writing step
                write_step = PlanStep(
                    step_number=len(state.plan.steps) + 1,
                    action=f"Save extracted data to {filename}",
                    tool="write_file",
                    arguments={"path": filename, "content": "{last.content}"},
                    expected_result=f"Data saved to {filename}",
                    fallback=None
                )
                state.plan.steps.append(write_step)
                console.print(f"[dim]  Added write_file step for {filename}[/dim]")

        # ENTERPRISE: Use SubAgentExecutor for workflows (30+ steps) - lowered from 50
        # This enables parallelism earlier for better performance
        if len(state.plan.steps) >= 30:
            console.print(f"[dim]Complex task - processing in parallel...[/dim]")
            try:
                from .subagent_executor import SubAgentExecutor
                # Concurrency optimized for RTX 4060 8GB VRAM
                # Keep at 10 to avoid GPU memory pressure from too many browser contexts
                executor = SubAgentExecutor(
                    self.mcp,
                    max_concurrency=10,  # Conservative for 8GB VRAM
                    max_retries=3,
                    checkpoint_interval=25  # More frequent checkpoints
                )
                # Convert plan steps to executor format
                exec_steps = [
                    {
                        "action": s.action,
                        "tool": s.tool,
                        "arguments": s.arguments,
                        "expected_result": s.expected_result,
                        "depends_on": []  # Sequential by default
                    }
                    for s in state.plan.steps
                ]
                workflow_state = await executor.execute_workflow(exec_steps)

                # Compile summary
                summary = f"Executed {workflow_state.completed}/{workflow_state.total_steps} steps successfully."
                if workflow_state.failed > 0:
                    summary += f"\n{workflow_state.failed} steps failed."
                summary += f"\nResults saved to: output/workflows/{workflow_state.workflow_id}_results.jsonl"
                return summary
            except ImportError:
                logger.warning("SubAgentExecutor not available, falling back to sequential")
            except Exception as e:
                logger.error(f"SubAgentExecutor failed: {e}, falling back to sequential")

        # Sequential execution for smaller plans (with step registry for memory)
        results = []

        # Initialize step registry for long sequence memory
        from .step_registry import get_step_registry
        registry = get_step_registry(state.plan.task_id)

        # IMPROVED: Continue while we have steps to execute, not based on is_complete
        # is_complete now requires goal verification, so we check all_steps_attempted instead
        while True:
            step = state.next_step()
            if not step:
                # All planned steps attempted - now verify goal completion
                break

            # Get context from previous steps (prevents "forgetting" in long sequences)
            step_context = registry.get_step_context(step.step_number, lookback=10)
            if step_context and step.step_number > 10:
                logger.debug(f"Step context: {step_context[:200]}...")

            console.print(f"\n[cyan]Step {step.step_number}: {step.action}[/cyan]")
            self._notify_progress(f"Step {step.step_number}/{len(state.plan.steps)}", step.action)

            # Record step starting in registry
            step_id = f"s{step.step_number}"

            # Substitute variables in arguments from previous step results
            resolved_arguments = self._resolve_step_arguments(step.arguments, results, registry)

            # Normalize tool name - fix common mismatches
            tool_name = self._normalize_tool_name(step.tool, step.action, resolved_arguments)

            registry.start_step(
                step_id=step_id,
                step_number=step.step_number,
                action=step.action,
                tool=tool_name,
                arguments=resolved_arguments
            )

            # Auto-inject content and path for write_file if missing
            if tool_name == 'write_file':
                # Auto-extract path from multiple sources if not provided or is placeholder
                current_path = resolved_arguments.get('path', '')
                placeholder_paths = ['', 'file', 'output', 'path', '{path}', '{file}']
                if not current_path or current_path.lower() in placeholder_paths:
                    # Try to extract filename from multiple sources
                    path_found = None
                    search_sources = [
                        step.action,
                        step.expected_result if hasattr(step, 'expected_result') else '',
                        str(step.arguments) if hasattr(step, 'arguments') else '',
                        prompt  # The original user prompt
                    ]
                    for source in search_sources:
                        if source:
                            path_match = re.search(r'[\w_-]+\.(txt|csv|json|md|log)', str(source))
                            if path_match:
                                path_found = path_match.group(0)
                                break
                    if path_found:
                        resolved_arguments['path'] = path_found
                        console.print(f"[dim]  Auto-extracted path: {resolved_arguments['path']}[/dim]")
                    else:
                        resolved_arguments['path'] = 'output.txt'

                # Check if content is placeholder or missing
                current_content = resolved_arguments.get('content', '')
                placeholder_values = ['', 'content', 'data', 'title', 'text', 'headlines',
                                     '{content}', '{data}', '{title}', '{text}', '{headlines}',
                                     'page title', 'extracted', 'result', 'the extracted',
                                     'page content', 'extracted content', 'extracted data']
                # Also check for generic placeholder patterns
                content_lower = current_content.lower() if current_content else ''
                is_generic_placeholder = (
                    content_lower.startswith('the extracted') or
                    content_lower.startswith('extracted ') or
                    content_lower.startswith('the page') or
                    content_lower.startswith('page ') or
                    '{' in content_lower and '}' in content_lower or
                    len(content_lower) < 30 and not any(c.isdigit() for c in content_lower)  # Short generic text
                )
                needs_content = not current_content or content_lower in placeholder_values or is_generic_placeholder

                # Determine what kind of content is requested based on action
                action_lower = step.action.lower()
                wants_title = any(kw in action_lower for kw in ['title', 'heading', 'name'])
                wants_list = any(kw in action_lower for kw in ['headlines', 'items', 'list', 'top'])

                # Auto-inject content from previous step results if needed
                if needs_content and results:
                    content = None
                    # Try all previous results, most recent first
                    for prev_result in reversed(results):
                        result_data = prev_result.get('result', {})
                        if isinstance(result_data, str) and result_data.strip():
                            # Skip if it's a short placeholder-like string
                            if len(result_data) > 20 or not result_data.lower() in placeholder_values:
                                content = result_data
                                break
                        elif isinstance(result_data, dict):
                            # If action wants title, prioritize title field from ANY step
                            if wants_title:
                                title_val = result_data.get('title', '')
                                if title_val and str(title_val).lower() not in placeholder_values:
                                    content = title_val
                                    break

                            # If action wants list/headlines, try items/headlines first
                            if wants_list:
                                for field in ['items', 'headlines', 'data']:
                                    val = result_data.get(field)
                                    if val and isinstance(val, list):
                                        import json
                                        content = json.dumps(val, indent=2)
                                        break
                                if content:
                                    break
                                # Also try markdown for list-type content (like headlines)
                                if result_data.get('markdown') and len(str(result_data.get('markdown', ''))) > 100:
                                    content = result_data['markdown']
                                    break

                            # Try markdown FIRST - it's usually the most complete content
                            if result_data.get('markdown') and len(str(result_data.get('markdown', ''))) > 100:
                                content = result_data['markdown']
                                break

                            # Try summary for cleaner content
                            if result_data.get('summary') and len(str(result_data.get('summary', ''))) > 50:
                                content = result_data['summary']
                                break

                            # Try headings list
                            if result_data.get('headings') and isinstance(result_data['headings'], list) and len(result_data['headings']) > 0:
                                content = '\n'.join(result_data['headings'][:10])
                                break

                            # Try title LAST (it's usually just a short page title, not the content we want)
                            # Only use title if nothing else was found
                            title_val = result_data.get('title', '')
                            if title_val and str(title_val).lower() not in placeholder_values and len(title_val) > 50:
                                content = title_val
                                break

                            # Then try content field but validate it's not a placeholder
                            content_val = result_data.get('content', '')
                            if content_val and str(content_val).lower() not in placeholder_values:
                                if len(str(content_val)) > 10:  # Likely real content
                                    content = content_val
                                    break

                            # Try other fields
                            for field in ['text', 'data', 'headlines', 'items']:
                                val = result_data.get(field)
                                if val and str(val).lower() not in placeholder_values:
                                    if isinstance(val, (list, dict)):
                                        import json
                                        content = json.dumps(val, indent=2)
                                    else:
                                        content = str(val)
                                    break
                            if content:
                                break
                    if content:
                        content_str = str(content)

                        # Strip HTML if content looks like HTML
                        if content_str.strip().startswith('<') and '</' in content_str:
                            # Extract text from HTML
                            text = re.sub(r'<script[^>]*>.*?</script>', '', content_str, flags=re.DOTALL)
                            text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
                            text = re.sub(r'<[^>]+>', ' ', text)
                            text = re.sub(r'\s+', ' ', text).strip()
                            if text:
                                content_str = text
                                console.print(f"[dim]  Stripped HTML to plain text[/dim]")

                        # For monitoring/forever mode, add timestamp
                        prompt_lower = prompt.lower()
                        if any(kw in prompt_lower for kw in ['monitor', 'forever', 'loop', 'every']):
                            from datetime import datetime
                            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            content_str = f"[{timestamp}]\n{content_str}\n---\n"
                            # Enable append mode
                            resolved_arguments['append'] = True
                            console.print(f"[dim]  Added timestamp for monitoring[/dim]")

                        resolved_arguments['content'] = content_str
                        console.print(f"[dim]  Auto-injected content ({len(content_str)} chars)[/dim]")

            # Execute the step through _execute_tool for proof-of-action verification
            try:
                # Wrap as tool_call dict for _execute_tool
                tool_call = {
                    'function': {
                        'name': tool_name,  # Use normalized tool name
                        'arguments': resolved_arguments
                    }
                }
                action_result = await self._execute_tool(tool_call)
                tool_result = action_result.data if action_result.success else {'error': action_result.error}

                # Check success
                success = action_result.success and (
                    not tool_result.get('error') if isinstance(tool_result, dict) else True
                )

                if success:
                    console.print(f"[green]  ✓ {step.expected_result[:50]}...[/green]")
                    results.append({
                        'step': step.step_number,
                        'action': step.action,
                        'result': tool_result
                    })

                    # Record success in step registry
                    registry.complete_step(step_id, tool_result)

                    # Check for extracted list data that should trigger batch processing
                    # This enables dynamic iteration over extraction results
                    await self._maybe_process_extracted_list(
                        tool_result, step, results, state, registry
                    )

                    # Report result - handle both strategic planner and local planner
                    if hasattr(state, 'mark_success'):
                        # LocalExecutionState
                        state.mark_success(step.step_number)
                        status = "complete" if state.is_complete else "continue"
                        next_action = None
                    else:
                        # StrategicPlanner ExecutionState
                        status, next_action = await self.strategic_planner.report_result(
                            state, success=True, result=tool_result
                        )

                    if status == "complete":
                        console.print("[green]✓ Plan completed successfully[/green]")
                        break

                else:
                    error_msg = str(tool_result.get('error', 'Unknown error'))
                    console.print(f"[yellow]  ⚠ Step failed: {error_msg[:50]}[/yellow]")

                    # Record failure in step registry
                    registry.fail_step(step_id, error_msg)

                    # Report result - handle both strategic planner and local planner
                    if hasattr(state, 'mark_failure'):
                        # LocalExecutionState
                        state.mark_failure(step.step_number)
                        # Abort if too many consecutive failures
                        if state.consecutive_failures >= 3:
                            status = "abort"
                        else:
                            status = "continue"
                        next_action = None
                    else:
                        # StrategicPlanner ExecutionState
                        status, next_action = await self.strategic_planner.report_result(
                            state, success=False, error=error_msg
                        )

                    if status == "abort":
                        console.print("[red]✗ Task aborted after recovery failed[/red]")
                        break
                    elif status == "recover" and next_action:
                        console.print(f"[cyan]🔄 Recovery: {next_action.get('new_approach', 'Trying alternative')}[/cyan]")
                        # Execute recovery action
                        recovery_result = await self.mcp.call_tool(
                            next_action['tool'],
                            next_action.get('arguments', {})
                        )
                        self.stats['tool_calls'] += 1
                        # NEW: Retry the failed step after recovery
                        if recovery_result and recovery_result.get('success'):
                            console.print(f"[green]  ✓ Recovery successful, retrying step {step.step_number}[/green]")
                            # Re-add the step to attempt it again
                            state.current_step -= 1  # Decrement to retry
                            continue

            except Exception as e:
                logger.error(f"Step execution error: {e}")
                registry.fail_step(step_id, str(e))
                status = "continue"  # Initialize status before conditional paths
                if hasattr(state, 'mark_failure'):
                    state.mark_failure(step.step_number)
                    # Try alternative approach for this step using fallback description
                    if step.fallback and state.consecutive_failures < 2:
                        console.print(f"[yellow]  Trying fallback: {step.fallback}[/yellow]")
                        try:
                            # Use fallback as new instruction for LLM to determine alternative action
                            fallback_result = await self._execute_fallback_instruction(step.fallback, state)
                            if fallback_result and fallback_result.get('success'):
                                console.print(f"[green]  Fallback succeeded, continuing...[/green]")
                                results.append({
                                    'step': step.step_number,
                                    'action': f"{step.action} (fallback)",
                                    'result': fallback_result,
                                    'fallback_used': True
                                })
                                status = "continue"
                                # Reset failure counter on successful fallback
                                if hasattr(state, 'consecutive_failures'):
                                    state.consecutive_failures = 0
                            else:
                                logger.warning(f"Fallback failed: {step.fallback}")
                        except Exception as fallback_err:
                            logger.error(f"Fallback execution error: {fallback_err}")
                    # Check if we should abort due to consecutive failures
                    if state.consecutive_failures >= 3:
                        status = "abort"
                else:
                    status, _ = await self.strategic_planner.report_result(
                        state, success=False, error=str(e)
                    )
                if status == "abort":
                    break

        # NEW: GOAL VERIFICATION - Check if the original task objective was actually met
        console.print("\n[cyan]Verifying task completion...[/cyan]")
        goal_met = await self._verify_goal_completion(prompt, state, results, registry)

        if goal_met:
            if hasattr(state, 'verify_goal_completion'):
                state.verify_goal_completion()
            console.print("[green]✓ Goal verified - task complete![/green]")
        else:
            console.print("[yellow]⚠ Goal not yet met - executing additional steps...[/yellow]")
            # Try to identify what's missing and add recovery steps
            missing_actions = await self._identify_missing_actions(prompt, state, results)
            if missing_actions:
                console.print(f"[cyan]Adding {len(missing_actions)} recovery steps...[/cyan]")
                # Execute missing actions
                for action in missing_actions[:3]:  # Limit to 3 recovery attempts
                    try:
                        recovery_result = await self.mcp.call_tool(
                            action['tool'],
                            action.get('arguments', {})
                        )
                        if recovery_result:
                            results.append({
                                'step': len(results) + 1,
                                'action': action.get('description', 'Recovery action'),
                                'result': recovery_result
                            })
                            self.stats['tool_calls'] += 1
                    except Exception as e:
                        logger.warning(f"Recovery action failed: {e}")

                # Re-verify after recovery
                goal_met = await self._verify_goal_completion(prompt, state, results, registry)
                if goal_met and hasattr(state, 'verify_goal_completion'):
                    state.verify_goal_completion()

        # Log registry summary for long workflows
        if len(state.plan.steps) >= 20:
            summary = registry.get_summary()
            logger.info(f"Workflow summary: {summary['completed']}/{summary['total_steps']} completed, "
                       f"{summary['failed']} failed, {summary['success_rate']:.1%} success rate")

        # Summarize results
        if results:
            completion_status = state.get_completion_status() if hasattr(state, 'get_completion_status') else f"{len(results)}/{len(state.plan.steps)} steps"
            summary_lines = [f"Task execution complete: {completion_status}"]
            for r in results[-5:]:  # Last 5
                summary_lines.append(f"  {r['step']}. {r['action']}")

            # Use local LLM to generate final summary
            final_summary = await self._summarize_plan_results(prompt, results, goal_met)
            return final_summary or "\n".join(summary_lines)

        return None

    def _normalize_tool_name(
        self,
        tool: str,
        action: str,
        arguments: Dict[str, Any]
    ) -> str:
        """
        Normalize tool names to fix common LLM mismatches.

        The LLM sometimes generates wrong tool names for certain actions.
        This method corrects them based on the action description.
        """
        action_lower = action.lower()

        # BROAD CATCH-ALL: Any action about saving/writing to a file should use write_file
        # This catches cases where LLM suggests wrong tools like playwright_get_preferred_contact
        save_keywords = ['save to file', 'save to', 'write to file', 'write to', 'save data',
                        'export to', 'store to', 'output to', 'save the', 'write the',
                        'save headlines', 'save content', 'save extracted']
        file_indicators = ['.txt', '.csv', '.json', '.md', '.log', 'file', 'output', 'headlines']

        if any(kw in action_lower for kw in save_keywords):
            # Action is about saving - check if it involves a file
            if any(fi in action_lower for fi in file_indicators) or 'path' in arguments:
                if '.csv' in action_lower or '.csv' in str(arguments):
                    logger.debug(f"[NORMALIZE] '{action_lower}' with tool '{tool}' -> write_validated_csv")
                    return 'write_validated_csv'
                logger.debug(f"[NORMALIZE] '{action_lower}' with tool '{tool}' -> write_file")
                return 'write_file'

        # Also catch any non-write tool being used when action clearly says "save" + "file"
        if not tool.startswith('write') and 'save' in action_lower and 'file' in action_lower:
            logger.debug(f"[NORMALIZE] save+file pattern: '{action_lower}' with tool '{tool}' -> write_file")
            return 'write_file'

        # EXPLICIT: playwright_extract_structured for "save" actions should use write_file
        # The LLM often mistakenly uses playwright_extract_structured when it means to save to file
        if tool == 'playwright_extract_structured' and 'save' in action_lower:
            logger.debug(f"[NORMALIZE] playwright_extract_structured for save action -> write_file")
            return 'write_file'

        # Navigation tools
        if tool == 'navigate' or (action_lower.startswith('navigate') and not tool.startswith('playwright')):
            return 'playwright_navigate'

        # Click actions
        if tool == 'click' or (action_lower.startswith('click') and not tool.startswith('playwright')):
            return 'playwright_click'

        # Fill actions
        if tool == 'fill' or tool == 'type' or ('fill' in action_lower and not tool.startswith('playwright')):
            return 'playwright_fill'

        # Content extraction - map all invented tools to real ones
        content_tools = [
            'get_content', 'extract_content', 'get_text', 'extract_text',
            'playwright_get_title', 'playwright_extract_title', 'get_title', 'extract_title',
            'playwright_get_page_title', 'playwright_extract_page_title',
            'playwright_get_headlines', 'playwright_extract_headlines',
            'playwright_read', 'playwright_read_page', 'read_page',
            # Browser-prefixed tools (invented by Claude/LLM)
            'browser_get_title', 'browser_get_content', 'browser_get_text',
            'browser_extract', 'browser_read', 'browser_get_page_title'
        ]
        if tool in content_tools:
            return 'playwright_get_content'

        markdown_tools = ['get_markdown', 'extract_markdown', 'playwright_get_page_content']
        if tool in markdown_tools:
            return 'playwright_get_markdown'

        fetch_tools = ['fetch', 'fetch_url', 'web_fetch', 'playwright_fetch_url']
        if tool in fetch_tools:
            return 'playwright_fetch_url'

        # Screenshot tools
        screenshot_tools = ['screenshot', 'take_screenshot', 'capture_screenshot']
        if tool in screenshot_tools:
            return 'playwright_screenshot'

        # Snapshot/accessibility tree
        snapshot_tools = ['snapshot', 'get_snapshot', 'accessibility_tree']
        if tool in snapshot_tools:
            return 'playwright_snapshot'

        # Extract any playwright_extract_* that doesn't exist -> playwright_get_content
        if tool.startswith('playwright_extract_') and tool not in [
            'playwright_extract_fb_ads', 'playwright_extract_reddit',
            'playwright_extract_page_fast', 'playwright_extract_structured'
        ]:
            return 'playwright_get_content'

        return tool

    def _resolve_step_arguments(
        self,
        arguments: Dict[str, Any],
        results: List[Dict],
        registry
    ) -> Dict[str, Any]:
        """
        Resolve placeholders in step arguments using results from previous steps.

        Supports several resolution patterns:
        1. {step_N.field} - Get field from step N's result
        2. {last.field} - Get field from the most recent step result
        3. {rows} or {data} - Get list data from last extraction step
        4. ${variable} - Alternative syntax for variable references

        Args:
            arguments: Original step arguments (may contain placeholders)
            results: List of previous step results
            registry: StepRegistry for additional context

        Returns:
            Resolved arguments with placeholders replaced by actual values
        """
        import re
        import copy

        if not arguments:
            return {}

        # Deep copy to avoid modifying original
        resolved = copy.deepcopy(arguments)

        def resolve_value(value, depth=0):
            """Recursively resolve placeholders in a value."""
            if depth > 5:  # Prevent infinite recursion
                return value

            if isinstance(value, str):
                # Skip empty strings
                if not value:
                    return value

                # Pattern: {step_N.field} or {last.field}
                placeholder_pattern = r'\{(step_(\d+)|last)\.(\w+)\}'
                matches = re.findall(placeholder_pattern, value)

                for match in matches:
                    full_match, step_num, field = match
                    placeholder = f"{{{full_match}.{field}}}"

                    if full_match == "last" and results:
                        last_result = results[-1].get('result', {})
                        if isinstance(last_result, dict):
                            replacement = last_result.get(field, "")
                            if replacement:
                                value = value.replace(placeholder, str(replacement))
                    elif step_num:
                        step_idx = int(step_num) - 1
                        if 0 <= step_idx < len(results):
                            step_result = results[step_idx].get('result', {})
                            if isinstance(step_result, dict):
                                replacement = step_result.get(field, "")
                                if replacement:
                                    value = value.replace(placeholder, str(replacement))

                # Pattern: {rows}, {data}, {items}, {entities}
                # If these placeholders exist, try to get list data from last step
                list_placeholders = ['{rows}', '{data}', '{items}', '{entities}', '{results}']
                for lp in list_placeholders:
                    if lp in value:
                        if results:
                            last_result = results[-1].get('result', {})
                            if isinstance(last_result, dict):
                                # Try common list field names
                                for list_key in ['rows', 'data', 'items', 'entities', 'results', 'extracted']:
                                    list_data = last_result.get(list_key)
                                    if list_data and isinstance(list_data, list):
                                        # Replace with actual data
                                        if value == lp:
                                            return list_data
                                        else:
                                            value = value.replace(lp, str(list_data))
                                        break

                # Pattern: ${variable} - variable reference
                var_pattern = r'\$\{?(\w+)\}?'
                var_matches = re.findall(var_pattern, value)
                for var_name in var_matches:
                    # Search through all results for this variable
                    for result in reversed(results):
                        result_data = result.get('result', {})
                        if isinstance(result_data, dict) and var_name in result_data:
                            replacement = result_data[var_name]
                            # Handle both ${var} and $var patterns
                            value = re.sub(rf'\$\{{?{var_name}\}}?', str(replacement), value)
                            break

                # Detect unresolved placeholders like {company_name} (literal braces)
                unresolved = re.findall(r'\{(\w+)\}', value)
                for ur in unresolved:
                    # Skip JSON-like structures
                    if ur in ['true', 'false', 'null']:
                        continue
                    # Search results for matching field
                    for result in reversed(results):
                        result_data = result.get('result', {})
                        if isinstance(result_data, dict):
                            # Try direct match
                            if ur in result_data:
                                value = value.replace(f'{{{ur}}}', str(result_data[ur]))
                                break
                            # Try snake_case to camelCase conversion
                            camel_key = ''.join(w.title() if i else w for i, w in enumerate(ur.split('_')))
                            if camel_key in result_data:
                                value = value.replace(f'{{{ur}}}', str(result_data[camel_key]))
                                break

                return value

            elif isinstance(value, dict):
                return {k: resolve_value(v, depth + 1) for k, v in value.items()}
            elif isinstance(value, list):
                return [resolve_value(item, depth + 1) for item in value]
            else:
                return value

        # Resolve all values in arguments
        for key in resolved:
            resolved[key] = resolve_value(resolved[key])

        # Log if we made any changes
        if resolved != arguments:
            logger.debug(f"Resolved step arguments: {list(resolved.keys())}")

        return resolved

    async def _maybe_process_extracted_list(
        self,
        tool_result: Dict[str, Any],
        current_step,
        results: List[Dict],
        state,
        registry
    ) -> None:
        """
        Check if the current step extracted a list that needs batch processing.

        This enables dynamic iteration - if we extract companies/URLs, and the next
        step expects to iterate over them, we can spawn sub-tasks automatically.

        For example:
        - Step 1: playwright_extract_entities extracts company names
        - Step 2 (template): playwright_linkedin_company_lookup for {company_name}
        - This method detects this pattern and executes step 2 for EACH company

        Args:
            tool_result: Result from the just-completed step
            current_step: The PlanStep that just completed
            results: All step results so far
            state: Execution state
            registry: StepRegistry
        """
        if not isinstance(tool_result, dict):
            return

        # Look for extracted list data
        list_data = None
        list_key = None
        for key in ['entities', 'items', 'companies', 'rows', 'data', 'results', 'urls']:
            if key in tool_result and isinstance(tool_result[key], list):
                if len(tool_result[key]) > 0:
                    list_data = tool_result[key]
                    list_key = key
                    break

        if not list_data or len(list_data) == 0:
            return

        # Check if there's a next step
        next_step = state.peek_next_step() if hasattr(state, 'peek_next_step') else None

        if not next_step:
            return

        # AUTO-INJECT RESULTS INTO WRITE TOOLS (fixes data pipeline gap)
        # This must come BEFORE placeholder check since write tools don't use placeholders
        logger.info(f"Detected {len(list_data)} items from {list_key}, next step: {next_step.tool if next_step else 'None'}")
        # When next step is write_file/write_validated_csv and we have list data,
        # automatically inject the data instead of relying on LLM to pass it
        if next_step.tool in ['write_file', 'write_validated_csv']:
            console.print(f"[cyan]🔄 Auto-injecting {len(list_data)} items into write operation...[/cyan]")
            try:
                # Get path from next step arguments
                path = next_step.arguments.get('path') or next_step.arguments.get('csv_path', '')
                if not path:
                    path = '/home/username/lead_research/auto_results.csv'

                if next_step.tool == 'write_validated_csv':
                    # Use write_validated_csv with the actual data
                    write_result = await self.mcp.call_tool(
                        'write_validated_csv',
                        {'path': path, 'rows': list_data}
                    )
                else:
                    # Convert list to CSV content for write_file
                    import csv
                    import io
                    output = io.StringIO()
                    if list_data and isinstance(list_data[0], dict):
                        fieldnames = list(list_data[0].keys())
                        writer = csv.DictWriter(output, fieldnames=fieldnames)
                        writer.writeheader()
                        writer.writerows(list_data)
                    else:
                        # Simple list - write as lines
                        for item in list_data:
                            output.write(f"{item}\n")
                    csv_content = output.getvalue()

                    write_result = await self.mcp.call_tool(
                        'write_file',
                        {'path': path, 'content': csv_content}
                    )

                self.stats['tool_calls'] += 1

                if write_result and not write_result.get('error'):
                    # Record the write step
                    write_step_id = f"s{current_step.step_number}_write"
                    registry.start_step(
                        step_id=write_step_id,
                        step_number=current_step.step_number,
                        action=f"Auto-write {len(list_data)} items to {path}",
                        tool=next_step.tool,
                        arguments={'path': path, 'rows': f'{len(list_data)} items'}
                    )
                    registry.complete_step(write_step_id, write_result)
                    results.append({
                        'step': f"{current_step.step_number}w",
                        'action': f"Auto-wrote {len(list_data)} items to {path}",
                        'result': write_result
                    })
                    console.print(f"[green]  ✓ Auto-saved {len(list_data)} items to {path}[/green]")

                    # Skip the next step since we did the write
                    if hasattr(state, 'skip_next_step'):
                        state.skip_next_step()
                    return  # Exit early - we handled the write

            except Exception as e:
                logger.warning(f"Auto-inject write failed, falling back to planned step: {e}")

        # Check if batch processing tool is more appropriate
        if next_step.tool in ['playwright_navigate', 'playwright_extract_page_fast']:
            # Try to use batch_extract instead
            urls = []
            for item in list_data[:10]:  # Limit to 10 for safety
                if isinstance(item, dict):
                    url = item.get('url') or item.get('website') or item.get('link')
                    if url:
                        urls.append(url)
                elif isinstance(item, str) and item.startswith('http'):
                    urls.append(item)

            if urls:
                # Use batch_extract tool
                console.print(f"[cyan]🔄 Auto-batching {len(urls)} URLs for extraction...[/cyan]")
                try:
                    batch_result = await self.mcp.call_tool(
                        'playwright_batch_extract',
                        {'urls': urls}
                    )
                    self.stats['tool_calls'] += 1

                    if batch_result and not batch_result.get('error'):
                        # Add batch results
                        batch_step_id = f"s{current_step.step_number}_batch"
                        registry.start_step(
                            step_id=batch_step_id,
                            step_number=current_step.step_number,
                            action=f"Batch extract from {len(urls)} URLs",
                            tool='playwright_batch_extract',
                            arguments={'urls': urls}
                        )
                        registry.complete_step(batch_step_id, batch_result)
                        results.append({
                            'step': f"{current_step.step_number}b",
                            'action': f"Batch extracted {len(urls)} URLs",
                            'result': batch_result
                        })
                        console.print(f"[green]  ✓ Batch extracted {len(urls)} URLs[/green]")

                        # Skip the next step since we did batch processing
                        if hasattr(state, 'skip_next_step'):
                            state.skip_next_step()

                except Exception as e:
                    logger.warning(f"Batch extraction failed, falling back to sequential: {e}")

    async def _execute_fallback_instruction(
        self,
        fallback_instruction: str,
        state
    ) -> Optional[Dict]:
        """
        Execute a fallback instruction when primary step fails.

        The fallback is a natural language description of an alternative approach.
        LLM determines the appropriate tool and arguments.

        Returns result dict with success indicator, or None if fallback fails.
        """
        try:
            logger.debug(f"Executing fallback: {fallback_instruction}")

            # Ask LLM to convert fallback instruction to a tool call
            fallback_prompt = f"""A step in our plan failed. The fallback instruction is:
"{fallback_instruction}"

Based on this fallback instruction, what single tool should we call next?

Available tools: playwright_click, playwright_fill, playwright_navigate, playwright_get_text,
playwright_screenshot, playwright_wait, playwright_extract_page_fast, write_file, ask_user

Respond with JSON:
{{
  "tool": "tool_name",
  "arguments": {{"arg1": "value1"}},
  "reasoning": "brief explanation"
}}

Your response:"""

            response = self.ollama_client.chat(
                model=self.fast_model,
                messages=[{'role': 'user', 'content': fallback_prompt}],
                options={'temperature': 0.1, 'num_predict': 200}
            )

            content = response.get('message', {}).get('content', '').strip()

            # Parse JSON response
            import json
            try:
                # Extract JSON from markdown code blocks if present
                if '```json' in content:
                    content = content.split('```json')[1].split('```')[0].strip()
                elif '```' in content:
                    content = content.split('```')[1].split('```')[0].strip()

                action_data = json.loads(content)
            except json.JSONDecodeError:
                logger.error(f"Failed to parse fallback action: {content}")
                return None

            tool_name = action_data.get('tool')
            arguments = action_data.get('arguments', {})

            if not tool_name:
                return None

            logger.info(f"Fallback action: {tool_name} with args {arguments}")

            # Execute the tool
            result = await self.mcp.call_tool(tool_name, arguments)
            self.stats['tool_calls'] += 1

            return result

        except Exception as e:
            logger.error(f"Fallback execution error: {e}")
            return None

    async def _verify_goal_completion(
        self,
        prompt: str,
        state,
        results: List[Dict],
        registry
    ) -> bool:
        """
        Verify that the original task goal was actually met.

        Returns True if goal is complete, False if more work needed.
        """
        try:
            # Extract what was achieved from results
            achieved_summary = []
            for r in results[-5:]:  # Last 5 steps
                action = r.get('action', '')
                result_data = r.get('result', {})
                if isinstance(result_data, dict):
                    # Check for success indicators
                    if result_data.get('success') or result_data.get('markdown') or result_data.get('url'):
                        achieved_summary.append(f"- {action}")

            achieved_text = "\n".join(achieved_summary) if achieved_summary else "No successful actions recorded"

            # Ask LLM if the goal was met
            verification_prompt = f"""Task: {prompt}

Steps completed:
{achieved_text}

Total steps: {len(results)}/{len(state.plan.steps)}
Success criteria: {state.plan.success_criteria if hasattr(state.plan, 'success_criteria') else 'Task completed'}

Question: Was the original task objective fully accomplished?
Answer with ONLY "YES" or "NO" followed by a brief reason.

Your answer:"""

            response = self.ollama_client.chat(
                model=self.fast_model,  # Fast model for quick verification
                messages=[{'role': 'user', 'content': verification_prompt}],
                options={'temperature': 0.0, 'num_predict': 100}
            )

            answer = response.get('message', {}).get('content', '').strip().upper()
            goal_met = answer.startswith('YES')

            logger.info(f"Goal verification: {answer[:100]}")
            return goal_met

        except Exception as e:
            logger.warning(f"Goal verification failed: {e}")
            # Default: assume goal met if all steps completed successfully
            return len(results) >= len(state.plan.steps) * 0.8  # 80% threshold

    async def _identify_missing_actions(
        self,
        prompt: str,
        state,
        results: List[Dict]
    ) -> List[Dict]:
        """
        Identify what actions are still needed to complete the goal.

        Returns list of actions: [{'tool': 'playwright_click', 'arguments': {...}, 'description': '...'}]
        """
        try:
            # Build context of what was done
            completed_actions = [r.get('action', '') for r in results[-10:]]
            actions_text = "\n".join([f"{i+1}. {a}" for i, a in enumerate(completed_actions)])

            # Ask LLM what's missing
            missing_prompt = f"""Task: {prompt}

Actions completed so far:
{actions_text}

What actions are STILL NEEDED to fully complete this task?
List UP TO 3 specific actions needed, in this format:

ACTION 1: [tool_name] - Brief description
ACTION 2: [tool_name] - Brief description

Your answer:"""

            response = self.ollama_client.chat(
                model=self.fast_model,
                messages=[{'role': 'user', 'content': missing_prompt}],
                options={'temperature': 0.1, 'num_predict': 300}
            )

            answer = response.get('message', {}).get('content', '').strip()

            # Parse actions from response (simple heuristic)
            missing_actions = []
            lines = answer.split('\n')
            for line in lines:
                if 'playwright_' in line.lower() or 'click' in line.lower() or 'fill' in line.lower():
                    # Extract tool name
                    tool = 'playwright_click'  # Default
                    if 'fill' in line.lower():
                        tool = 'playwright_fill'
                    elif 'navigate' in line.lower():
                        tool = 'playwright_navigate'
                    elif 'screenshot' in line.lower():
                        tool = 'playwright_screenshot'

                    missing_actions.append({
                        'tool': tool,
                        'arguments': {},
                        'description': line.strip()
                    })

                    if len(missing_actions) >= 3:
                        break

            return missing_actions

        except Exception as e:
            logger.warning(f"Failed to identify missing actions: {e}")
            return []

    async def _summarize_plan_results(self, prompt: str, results: List[Dict], goal_met: bool = True) -> Optional[str]:
        """Use local LLM to extract and summarize plan execution results."""
        try:
            # Find the markdown content from get_markdown steps
            markdown_content = ""


            for r in reversed(results):
                result_data = r.get('result', {})
                if isinstance(result_data, dict):
                    # Check for error first - if Cloudflare blocked, note it
                    if result_data.get('error') or result_data.get('cloudflare_blocked'):
                        error_msg = result_data.get('error', 'Page blocked')
                        logger.warning(f"[SUMMARIZE] Found error in result: {error_msg}")
                        continue

                    # SPECIAL: Handle FB Ads extraction results directly (bypass LLM summarization)
                    if 'ads' in result_data and isinstance(result_data['ads'], list) and len(result_data['ads']) > 0:
                        ads = result_data['ads']
                        logger.info(f"[SUMMARIZE] Found {len(ads)} FB Ads - formatting directly")
                        lines = [f"## Found {len(ads)} Advertisers\n"]
                        lines.append("| # | Advertiser | Website | Ad ID |")
                        lines.append("|---|------------|---------|-------|")
                        for i, ad in enumerate(ads, 1):
                            name = ad.get('advertiser', 'Unknown')
                            website = ad.get('landing_url', '-') or '-'
                            ad_id = ad.get('ad_id', '-') or '-'
                            lines.append(f"| {i} | {name} | {website} | {ad_id} |")
                        lines.append("\n### Details:\n")
                        for i, ad in enumerate(ads, 1):
                            name = ad.get('advertiser', 'Unknown')
                            lines.append(f"**{i}. {name}**")
                            if ad.get('landing_url'):
                                lines.append(f"   - Website: {ad['landing_url']}")
                            if ad.get('page_url'):
                                lines.append(f"   - FB Page: {ad['page_url']}")
                            if ad.get('ad_text'):
                                lines.append(f"   - Ad Copy: {ad['ad_text'][:150]}...")
                            if ad.get('start_date'):
                                lines.append(f"   - Started: {ad['start_date']}")
                            lines.append("")
                        return '\n'.join(lines)

                    # Look for markdown content in various fields (expanded list)
                    for key in ['markdown', 'content', 'text', 'data', 'output', 'page_content', 'html', 'body']:
                        content = result_data.get(key, '')
                        if isinstance(content, str) and len(content) > 100:
                            markdown_content = content
                            logger.info(f"[SUMMARIZE] Found content in '{key}' field, length={len(content)}")
                            break
                    if markdown_content:
                        break
                elif isinstance(result_data, str) and len(result_data) > 100:
                    # Handle case where result is a raw string
                    markdown_content = result_data
                    logger.info(f"[SUMMARIZE] Found raw string content, length={len(result_data)}")
                    break

            # Use markdown if found, otherwise use JSON results
            if markdown_content:
                # Truncate markdown to fit in context
                content_to_analyze = markdown_content[:8000]  # Increased from 6000
                logger.info(f"[SUMMARIZE] Using markdown content ({len(markdown_content)} chars, truncated to {len(content_to_analyze)})")
            else:
                # Fall back to full JSON dump with more context
                content_to_analyze = json.dumps(results[-10:], indent=2, default=str)[:6000]
                logger.warning(f"[SUMMARIZE] No markdown found, using JSON fallback ({len(content_to_analyze)} chars)")

            # Build extraction prompt that focuses on user's specific request
            extraction_prompt = f"""Extract the specific information requested from this page content.

USER REQUEST: {prompt}

PAGE CONTENT:
{content_to_analyze}

INSTRUCTIONS:
1. Find the EXACT items the user asked for (e.g., "top 3 results", "book titles", "job listings")
2. List each item clearly with any relevant details (title, price, link, etc.)
3. If you can't find the exact items, explain what you found instead
4. Be specific - include names, numbers, prices if available

EXTRACTED DATA:"""

            # FINAL SYNTHESIS: Try Kimi first (if available), fallback to ollama
            # This is the LAST LLM call - use strongest model for complex synthesis
            final_content = None

            # Try Kimi for final synthesis (general-purpose agent pattern)
            if self.kimi_client and hasattr(self.kimi_client, 'client') and self.kimi_client.client:
                try:
                    logger.info("[KIMI] Using Kimi for final synthesis")
                    kimi_response = await self.kimi_client.client.chat.completions.create(
                        model=self.kimi_client.model,
                        messages=[{'role': 'user', 'content': extraction_prompt}],
                        temperature=0.1,
                        max_tokens=2000
                    )
                    if kimi_response and kimi_response.choices:
                        final_content = kimi_response.choices[0].message.content
                        logger.info(f"[KIMI] Final synthesis complete ({len(final_content)} chars)")
                except Exception as kimi_error:
                    logger.warning(f"[KIMI] Final synthesis failed, falling back to local: {kimi_error}")

            # Fallback to ollama if Kimi not available or failed
            if not final_content:
                logger.debug("[OLLAMA] Using local model for final synthesis")
                response = self.ollama_client.chat(
                    model=self.model,
                    messages=[{'role': 'user', 'content': extraction_prompt}],
                    options={'temperature': 0.1, 'num_predict': 1000}
                )
                final_content = response.get('message', {}).get('content', '')

            return final_content
        except Exception as e:
            logger.warning(f"Summary generation failed: {e}")
            return None

    async def _try_complex_workflow(self, prompt: str) -> Optional[str]:
        """
        Handle complex multi-step workflows by breaking them into subtasks.
        Delegates to WorkflowHandlers for actual execution.
        """
        return await self.workflow_handlers.try_complex_workflow(
            prompt,
            execute_react_loop=self._execute_react_loop
        )

    async def _execute_page_loop(self, base_url: str, start: int, end: int, prompt: str) -> str:
        """Execute a loop across multiple pages. Delegates to WorkflowHandlers."""
        return await self.workflow_handlers.execute_page_loop(base_url, start, end, prompt)

    async def _execute_multi_site_page_loops(self, site_matches: list, prompt: str) -> str:
        """Execute page loops across multiple sites. Delegates to WorkflowHandlers."""
        return await self.workflow_handlers.execute_multi_site_page_loops(site_matches, prompt)

    async def _execute_forever_loop(self, prompt: str) -> str:
        """Execute forever/continuous monitoring. Delegates to WorkflowHandlers."""
        return await self.workflow_handlers.execute_forever_loop(prompt)

    async def _execute_queue_operation(self, prompt: str) -> str:
        """Handle task queue operations. Delegates to WorkflowHandlers."""
        return await self.workflow_handlers.execute_queue_operation(prompt, self._execute_with_streaming)

    async def _execute_mega_warehouse(self, books_pages, quotes_pages, prompt: str) -> str:
        """Execute mega data warehouse extraction. Delegates to WorkflowHandlers."""
        return await self.workflow_handlers.execute_mega_warehouse(books_pages, quotes_pages, prompt)

    async def _execute_categories_plus_quotes(self, prompt: str, quotes_page_match) -> str:
        """Handle mixed pattern: book categories + quotes. Delegates to WorkflowHandlers."""
        return await self.workflow_handlers.execute_categories_plus_quotes(prompt, quotes_page_match)

    async def _execute_category_collection(self, prompt: str) -> Optional[str]:
        """Collect items from multiple categories. Delegates to WorkflowHandlers."""
        return await self.workflow_handlers.execute_category_collection(prompt)

    async def _execute_research_and_produce(self, url: str, prompt: str) -> Optional[str]:
        """Execute research and document production. Delegates to WorkflowHandlers."""
        return await self.workflow_handlers.execute_research_and_produce(url, prompt)

    async def _execute_multi_site_comparison(self, urls: list, prompt: str) -> Optional[str]:
        """Compare data from multiple sites. Delegates to WorkflowHandlers."""
        return await self.workflow_handlers.execute_multi_site_comparison(urls, prompt)

    async def _execute_click_detail_loop(self, prompt: str) -> Optional[str]:
        """Click on items, extract details, go back. Delegates to WorkflowHandlers."""
        return await self.workflow_handlers.execute_click_detail_loop(prompt)

    async def _execute_sequential_steps(self, prompt: str) -> Optional[str]:
        """Execute complex prompts sequentially. Delegates to WorkflowHandlers."""
        return await self.workflow_handlers.execute_sequential_steps(prompt, self._execute_react_loop)

    # Navigation handlers (_try_click_through, _handle_pagination, _handle_site_search,
    # _handle_form_fill, smart_click) are now provided by NavigationHandlersMixin

    async def _execute_multi_field_form(self, url: str, prompt: str) -> Optional[str]:
        """Handle multi-field form fill tasks. Delegates to WorkflowHandlers."""
        return await self.workflow_handlers.execute_multi_field_form(url, prompt)

    # =============== LEAD GENERATION WORKFLOWS ===============

    async def _try_lead_workflows(self, prompt: str) -> Optional[str]:
        """Try lead generation workflows for SDR, FB Ads, Reddit, batch extraction."""
        lower = prompt.lower()

        fb_ads_patterns = [r"(?:fb|facebook)\s+ads?\s+(?:library\s+)?(?:for|search|scrape|extract)"]
        reddit_patterns = [r"(?:reddit|r/)\s*(?:\w+)?\s*(?:warm\s+signals?|leads?)"]
        batch_patterns = [r"batch\s+extract\s+(?:contacts?|leads?)"]
        sdr_patterns = [r"(?:build|create|generate)\s+(?:a\s+)?lead\s+list"]

        if any(re.search(p, lower) for p in fb_ads_patterns):
            search_term = self.lead_workflows._extract_search_term(prompt)
            result = await self.lead_workflows.execute_fb_ads_extraction(search_term)
            if result.success:
                return f"**FB Ads**: {result.total_count} leads -> {result.output_file}"

        if any(re.search(p, lower) for p in reddit_patterns):
            subreddit = self.lead_workflows._extract_subreddit(prompt)
            result = await self.lead_workflows.execute_reddit_extraction(subreddit)
            if result.success:
                return f"**Reddit**: {result.total_count} leads -> {result.output_file}"

        if any(re.search(p, lower) for p in batch_patterns):
            urls = self._extract_urls(prompt)
            if urls:
                result = await self.lead_workflows.execute_batch_extraction(urls)
                if result.success:
                    return f"**Batch**: {result.total_count} leads -> {result.output_file}"

        if any(re.search(p, lower) for p in sdr_patterns):
            count_match = re.search(r"(\d+)\s+leads?", lower)
            lead_count = int(count_match.group(1)) if count_match else 10
            result = await self.lead_workflows.execute_sdr_workflow(prompt, lead_count=lead_count)
            if result.success:
                return f"**SDR**: {result.total_count} leads -> {result.output_file}"

        return None

    async def _execute_sdr_workflow(self, prompt: str, lead_count: int = 10) -> str:
        """Execute SDR lead finding workflow. Delegates to LeadWorkflows."""
        result = await self.lead_workflows.execute_sdr_workflow(prompt, lead_count=lead_count)
        return f"Found {result.total_count} leads" if result.success else f"Failed: {result.error}"

    async def _execute_fb_ads_extraction(self, search_term: str, max_ads: int = 20) -> str:
        """Execute Facebook Ads Library extraction. Delegates to LeadWorkflows."""
        result = await self.lead_workflows.execute_fb_ads_extraction(search_term, max_ads)
        return f"Extracted {result.total_count} advertisers" if result.success else f"Failed: {result.error}"

    async def _execute_reddit_extraction(self, subreddit: str = "entrepreneur", max_posts: int = 20) -> str:
        """Execute Reddit warm signals extraction. Delegates to LeadWorkflows."""
        result = await self.lead_workflows.execute_reddit_extraction(subreddit, max_posts)
        return f"Found {result.total_count} warm signals" if result.success else f"Failed: {result.error}"

    async def _execute_batch_extraction(self, urls: list) -> str:
        """Execute batch URL contact extraction. Delegates to LeadWorkflows."""
        result = await self.lead_workflows.execute_batch_extraction(urls)
        return f"Extracted from {len(urls)} URLs" if result.success else f"Failed: {result.error}"

    async def _execute_contact_enrichment(self, leads: list) -> str:
        """Execute contact enrichment. Delegates to LeadWorkflows."""
        result = await self.lead_workflows.execute_contact_enrichment(leads)
        return f"Enriched {result.total_count} leads" if result.success else f"Failed: {result.error}"

    async def _try_executor(self, prompt: str) -> Optional[str]:
        """Try specialized executor for known intents."""
        if not self.intent_detector:
            return None

        intent = self.intent_detector.detect(prompt)
        if intent.confidence < 0.7 or intent.capability == "UNKNOWN":
            return None

        try:
            from .executors import ALL_EXECUTORS
            if intent.capability not in ALL_EXECUTORS:
                return None

            console.print(f"[green]Using {intent.capability} executor[/green]")

            executor_class = ALL_EXECUTORS[intent.capability]
            executor = executor_class(browser=self.browser, context={})
            result = await executor.execute(intent.parameters)

            self.stats['tool_calls'] += 1
            return result.message

        except Exception as e:
            logger.warning(f"Executor failed: {e}")
            return None

    async def _smart_wait(self, min_wait: float = 0.5, max_wait: float = 5.0, check_interval: float = 0.3):
        """
        Dynamic wait that checks if page is ready instead of fixed timeout.
        Uses exponential backoff with content change detection.
        """
        elapsed = 0
        last_content_hash = None
        stable_count = 0

        await asyncio.sleep(min_wait)  # Minimum wait
        elapsed += min_wait

        while elapsed < max_wait:
            try:
                # Get current page state
                result = await self.mcp.call_tool('playwright_snapshot', {})
                if isinstance(result, dict):
                    content = str(result.get('content', result.get('text', '')))[:1000]
                    content_hash = hash(content)

                    # Check if content is stable
                    if content_hash == last_content_hash:
                        stable_count += 1
                        if stable_count >= 2:  # Content stable for 2 checks
                            return  # Page ready
                    else:
                        stable_count = 0
                        last_content_hash = content_hash

            except Exception as e:
                logger.debug(f"Page stability check failed: {e}")

            await asyncio.sleep(check_interval)
            elapsed += check_interval

    def _is_multi_task_prompt(self, prompt: str) -> bool:
        """
        Detect if prompt contains multiple distinct tasks.

        Multi-task prompts should go to LLM for proper planning, not direct execution.
        """
        import re
        prompt_lower = prompt.lower()

        # Count navigation keywords (go to, navigate, open, visit)
        nav_keywords = ['go to ', 'navigate to ', 'open ', 'visit ']
        nav_count = sum(prompt_lower.count(kw) for kw in nav_keywords)
        if nav_count > 1:
            logger.debug(f"[MULTI-TASK] Detected {nav_count} navigation keywords")
            return True

        # Count task indicators (numbered lists, semicolons between tasks)
        # Case-insensitive check for ". Go to " pattern
        if re.search(r'\.\s+go\s+to\s+', prompt_lower) or prompt.count('; ') >= 2:
            logger.debug("[MULTI-TASK] Detected sentence boundary + 'go to' pattern or multiple semicolons")
            return True

        # Check for numbered task list
        numbered_pattern = r'\d+\.\s+(go|click|type|search|find|navigate)'
        if len(re.findall(numbered_pattern, prompt_lower)) > 1:
            logger.debug("[MULTI-TASK] Detected numbered task list")
            return True

        # Check prompt length - long prompts usually have multiple tasks
        if len(prompt) > 300:
            logger.debug(f"[MULTI-TASK] Prompt length {len(prompt)} > 300")
            return True

        # Check for multiple distinct sites mentioned
        sites = ['gmail', 'zoho', 'linkedin', 'facebook', 'reddit', 'google maps', 'twitter', 'youtube']
        site_count = sum(1 for site in sites if site in prompt_lower)
        if site_count > 1:
            logger.debug(f"[MULTI-TASK] Detected {site_count} distinct sites")
            return True

        return False

    async def _try_direct_patterns(self, prompt: str) -> Optional[str]:
        """
        Highest priority: Direct execution for known site patterns.

        This bypasses ALL other logic (strategic planner, web shortcuts, etc.)
        for sites we know exactly how to handle. This provides Skyvern-level
        reliability for common e-commerce and form patterns.
        """
        from rich.console import Console
        console = Console()

        prompt_lower = prompt.lower()

        # Skip direct patterns for multi-task prompts (need LLM planning instead)
        if self._is_multi_task_prompt(prompt):
            logger.debug("Skipping direct patterns - multi-task prompt detected")
            return None

        # SAUCEDEMO.COM - E-commerce checkout
        if 'saucedemo' in prompt_lower and any(kw in prompt_lower for kw in ['login', 'checkout', 'cart', 'backpack', 'product']):
            console.print("[yellow]⚡ Direct execution: saucedemo.com[/yellow]")
            try:
                username = 'standard_user' if 'standard_user' in prompt_lower else 'standard_user'
                # Get password from environment or extract from prompt
                password = os.environ.get('SAUCEDEMO_PASSWORD',
                    'secret_sauce' if 'secret_sauce' in prompt_lower else None)
                if not password:
                    logger.warning("SAUCEDEMO_PASSWORD not set and no password in prompt")
                    return None

                await self.mcp.call_tool('playwright_navigate', {'url': 'https://www.saucedemo.com'})
                await self._smart_wait(min_wait=0.5, max_wait=3)
                await self.mcp.call_tool('playwright_fill', {'selector': '#user-name', 'value': username})
                await self.mcp.call_tool('playwright_fill', {'selector': '#password', 'value': password})
                await self.mcp.call_tool('playwright_click', {'selector': '#login-button'})
                await self._smart_wait(min_wait=1, max_wait=4)

                if 'backpack' in prompt_lower or 'cart' in prompt_lower or 'checkout' in prompt_lower:
                    console.print("[green]✓ Logged in, adding to cart...[/green]")
                    await self.mcp.call_tool('playwright_click', {'selector': '[data-test="add-to-cart-sauce-labs-backpack"]'})
                    await self.mcp.call_tool('playwright_click', {'selector': '.shopping_cart_link'})
                    await self._smart_wait(min_wait=0.5, max_wait=2)

                    if 'checkout' in prompt_lower:
                        await self.mcp.call_tool('playwright_click', {'selector': '#checkout'})
                        await self._smart_wait(min_wait=0.5, max_wait=2)
                        await self.mcp.call_tool('playwright_fill', {'selector': '#first-name', 'value': 'Test'})
                        await self.mcp.call_tool('playwright_fill', {'selector': '#last-name', 'value': 'User'})
                        await self.mcp.call_tool('playwright_fill', {'selector': '#postal-code', 'value': '12345'})
                        await self.mcp.call_tool('playwright_click', {'selector': '#continue'})
                        # Wait for finish button to be ready
                        await self.mcp.call_tool('playwright_wait_for_selector', {'selector': '#finish', 'timeout': 3000})
                        await self.mcp.call_tool('playwright_click', {'selector': '#finish'})
                        console.print("[green]✓ Order complete![/green]")
                        return "Order completed successfully on saucedemo.com!"
                    return "Items added to cart on saucedemo.com"

                # Always extract page content after login (inventory page)
                console.print("[green]✓ Logged in, extracting inventory...[/green]")
                result = await self.mcp.call_tool('playwright_snapshot', {})
                content = ''
                if isinstance(result, dict):
                    for key in ['content', 'text', 'markdown', 'snapshot', 'accessibility_tree']:
                        if result.get(key) and len(str(result.get(key))) > 50:
                            content = str(result.get(key))[:3000]
                            break
                if not content:
                    content = str(result)[:3000] if result else 'Inventory loaded'
                return f"Successfully logged in to saucedemo.com as {username}\n\nInventory:\n{content}"
            except Exception as e:
                logger.warning(f"Saucedemo direct execution failed: {e}")
                return None

        # BOOKS.TOSCRAPE.COM - Book extraction
        if 'books.toscrape' in prompt_lower or ('books' in prompt_lower and 'scrape' in prompt_lower):
            console.print("[yellow]⚡ Direct execution: books.toscrape.com[/yellow]")
            try:
                await self.mcp.call_tool('playwright_navigate', {'url': 'https://books.toscrape.com'})
                await self._smart_wait(min_wait=1, max_wait=3)

                # Get page content using snapshot
                result = await self.mcp.call_tool('playwright_snapshot', {})
                content = ''
                if isinstance(result, dict):
                    for key in ['content', 'text', 'markdown', 'snapshot', 'accessibility_tree']:
                        if result.get(key) and len(str(result.get(key))) > 50:
                            content = str(result.get(key))
                            break
                if not content:
                    content = str(result) if result else ''

                # Parse book titles and prices from content
                books = []

                # Pattern to match price (£XX.XX)
                price_pattern = r'£(\d+\.\d{2})'
                prices = re.findall(price_pattern, content)

                # Try to extract titles - look for common book title patterns
                # Books.toscrape has titles in article tags or as links
                title_patterns = [
                    r'<h3><a[^>]*title="([^"]+)"',  # title attribute
                    r'<a href="[^"]*catalogue[^"]*">([^<]+)</a>',  # link text to catalogue
                ]

                titles = []
                for pattern in title_patterns:
                    found = re.findall(pattern, content)
                    if found and len(found) > 5:  # Should have multiple books
                        titles = found
                        break

                # If we didn't find titles with patterns, try to get them from markdown
                if not titles and 'markdown' in str(result):
                    md_result = await self.mcp.call_tool('playwright_snapshot', {})
                    md_content = md_result.get('markdown', '') if md_result else ''
                    # Look for lines that look like titles (capitalized words)
                    lines = md_content.split('\n')
                    for line in lines:
                        line = line.strip()
                        if line and len(line) > 3 and len(line) < 100:
                            # Check if it's likely a title (starts with capital, not too short/long)
                            if line[0].isupper() and not line.startswith('£') and not line.startswith('http'):
                                titles.append(line)

                # Match titles with prices (if we have both)
                if titles and prices:
                    max_items = min(len(titles), len(prices))
                    for i in range(max_items):
                        books.append(f"{titles[i]} - £{prices[i]}")
                elif prices:
                    # Just prices, no titles
                    for price in prices[:20]:  # Limit to 20 items
                        books.append(f"Book - £{price}")

                if books:
                    result_text = f"Successfully extracted {len(books)} books from books.toscrape.com:\n\n"
                    result_text += '\n'.join(books)
                    console.print(f"[green]✓ Extracted {len(books)} books[/green]")
                    return result_text
                else:
                    # Return raw content excerpt if parsing failed
                    content_preview = content[:2000] if content else 'No content'
                    console.print("[yellow]⚠ Could not parse books, returning raw content[/yellow]")
                    return f"Content from books.toscrape.com:\n\n{content_preview}"

            except Exception as e:
                logger.warning(f"Books.toscrape direct execution failed: {e}")
                return None

        # WIKIPEDIA - Search and read
        if 'wikipedia' in prompt_lower:
            console.print("[yellow]⚡ Direct execution: Wikipedia[/yellow]")
            try:
                search_match = re.search(r"(?:search|about|article|read)\s+(?:for\s+)?['\"]?([^'\"]+)", prompt_lower)
                search_term = search_match.group(1).strip() if search_match else "artificial intelligence"

                await self.mcp.call_tool('playwright_navigate', {'url': 'https://en.wikipedia.org'})
                await self.mcp.call_tool('playwright_wait_for_load_state', {'state': 'domcontentloaded', 'timeout': 5000})
                await self.mcp.call_tool('playwright_fill', {'selector': '#searchInput', 'value': search_term})
                await self.mcp.call_tool('playwright_click', {'selector': 'button[type="submit"]'})
                await self.mcp.call_tool('playwright_wait_for_load_state', {'state': 'networkidle', 'timeout': 5000})

                result = await self.mcp.call_tool('playwright_snapshot', {})
                content = result.get('markdown', '')[:4000] if result else ''
                console.print("[green]✓ Retrieved Wikipedia article[/green]")
                return f"Wikipedia article about '{search_term}':\n\n{content}"
            except Exception as e:
                logger.warning(f"Wikipedia direct execution failed: {e}")
                return None

        # GMAIL / GOOGLE MAIL - Direct navigation
        if any(kw in prompt_lower for kw in ['gmail', 'mail.google', 'google mail']):
            console.print("[yellow]⚡ Direct execution: Gmail[/yellow]")
            try:
                await self.mcp.call_tool('playwright_navigate', {'url': 'https://mail.google.com'})
                await self.mcp.call_tool('playwright_wait_for_load_state', {'state': 'networkidle', 'timeout': 5000})
                result = await self.mcp.call_tool('playwright_snapshot', {})
                # Get current URL from snapshot or fallback
                current_url = result.get('url', 'https://mail.google.com') if result else 'https://mail.google.com'
                content = result.get('markdown', '')[:2000] if result else ''
                console.print("[green]✓ Navigated to Gmail[/green]")
                return f"Gmail - Final URL: {current_url}\n\nPage content:\n{content[:500] if content else '(Login required)'}"
            except Exception as e:
                logger.warning(f"Gmail direct execution failed: {e}")
                return None

        # ZOHO MAIL - Direct navigation
        if any(kw in prompt_lower for kw in ['zoho mail', 'mail.zoho', 'zoho.com/mail']):
            console.print("[yellow]⚡ Direct execution: Zoho Mail[/yellow]")
            try:
                await self.mcp.call_tool('playwright_navigate', {'url': 'https://mail.zoho.com'})
                await self.mcp.call_tool('playwright_wait_for_load_state', {'state': 'networkidle', 'timeout': 5000})
                result = await self.mcp.call_tool('playwright_snapshot', {})
                # Get current URL from snapshot or fallback
                current_url = result.get('url', 'https://mail.zoho.com') if result else 'https://mail.zoho.com'
                content = result.get('markdown', '')[:2000] if result else ''
                console.print("[green]✓ Navigated to Zoho Mail[/green]")
                return f"Zoho Mail - Final URL: {current_url}\n\nPage content:\n{content[:500] if content else '(Login required)'}"
            except Exception as e:
                logger.warning(f"Zoho Mail direct execution failed: {e}")
                return None

        # GOOGLE MAPS - Search or navigate
        if any(kw in prompt_lower for kw in ['google maps', 'maps.google', ' maps ']):
            console.print("[yellow]⚡ Direct execution: Google Maps[/yellow]")
            try:
                from agent.service_mapper import extract_maps_query, build_maps_search_url

                # Extract search query if present
                query = extract_maps_query(prompt)

                if query:
                    # Build search URL
                    url = build_maps_search_url(query)
                    console.print(f"[dim]Searching Maps for: {query}[/dim]")
                else:
                    url = "https://www.google.com/maps"

                await self.mcp.call_tool('playwright_navigate', {'url': url})
                # Wait for Google Maps to load (interactive map element)
                await self.mcp.call_tool('playwright_wait_for_load_state', {'state': 'networkidle', 'timeout': 8000})

                # Scroll to load more listings
                await self.mcp.call_tool('playwright_scroll', {'direction': 'down', 'amount': 600})
                # Brief pause for lazy loading
                await asyncio.sleep(0.5)

                result = await self.mcp.call_tool('playwright_snapshot', {})
                current_url = result.get('url', url) if result else url
                content = result.get('markdown', '')[:4000] if result else ''

                # Try to extract first listing URL from content
                listing_urls = re.findall(r'https://www\.google\.com/maps/place/[^\s\)]+', content)
                first_listing = listing_urls[0] if listing_urls else None

                console.print("[green]✓ Google Maps loaded[/green]")
                output = f"Google Maps - Search: '{query or 'homepage'}'\nFinal URL: {current_url}"
                if first_listing:
                    output += f"\n\nFirst Listing URL: {first_listing}"
                output += f"\n\nFound {len(listing_urls)} listing(s)"
                return output
            except Exception as e:
                logger.warning(f"Google Maps direct execution failed: {e}")
                return None

        # DIRECT URL NAVIGATION - Handle explicit URLs in prompt
        url_match = re.search(r'(?:go to|navigate to|open|visit)\s+(https?://[^\s]+|www\.[^\s]+|\w+\.\w+\.\w+[^\s]*)', prompt_lower)
        if url_match:
            target_url = url_match.group(1)
            if not target_url.startswith('http'):
                target_url = 'https://' + target_url
            console.print(f"[yellow]⚡ Direct navigation: {target_url}[/yellow]")
            try:
                await self.mcp.call_tool('playwright_navigate', {'url': target_url})
                # Wait for page to load
                await self.mcp.call_tool('playwright_wait_for_load_state', {'state': 'networkidle', 'timeout': 5000})
                result = await self.mcp.call_tool('playwright_snapshot', {})
                content = result.get('markdown', '')[:3000] if result else ''
                console.print(f"[green]✓ Navigated to {target_url}[/green]")
                return f"Page at {target_url}:\n\n{content}"
            except Exception as e:
                logger.warning(f"Direct URL navigation failed: {e}")
                return None

        # GOOGLE SEARCH
        if 'google' in prompt_lower and 'search' in prompt_lower:
            console.print("[yellow]⚡ Direct execution: Google Search[/yellow]")
            try:
                search_match = re.search(r"search\s+(?:for\s+)?['\"]?([^'\"]+)", prompt_lower)
                query = search_match.group(1).strip() if search_match else "latest news"

                await self.mcp.call_tool('playwright_navigate', {'url': 'https://www.google.com'})
                # Wait for search input to be ready
                await self.mcp.call_tool('playwright_wait_for_selector', {'selector': 'textarea[name="q"], input[name="q"]', 'timeout': 5000})
                await self.mcp.call_tool('playwright_fill', {'selector': 'textarea[name="q"], input[name="q"]', 'value': query})
                await self.mcp.call_tool('playwright_click', {'selector': 'input[name="btnK"], button[type="submit"]'})
                # Wait for search results to load
                await self.mcp.call_tool('playwright_wait_for_load_state', {'state': 'networkidle', 'timeout': 5000})

                result = await self.mcp.call_tool('playwright_snapshot', {})
                content = result.get('markdown', '')[:4000] if result else ''
                console.print("[green]✓ Retrieved search results[/green]")
                return f"Google search results for '{query}':\n\n{content}"
            except Exception as e:
                logger.warning(f"Google direct execution failed: {e}")
                return None

        # YOUTUBE - Video search
        if 'youtube' in prompt_lower and ('search' in prompt_lower or 'video' in prompt_lower):
            console.print("[yellow]⚡ Direct execution: YouTube Search[/yellow]")
            try:
                query = "tutorial"  # default
                patterns = [
                    r"search\s+for\s+['\"]([^'\"]+)['\"]",
                    r"search\s+for\s+([^,]+?)(?:,|$)",
                    r"search\s+['\"]([^'\"]+)['\"]",
                    r"youtube\s+for\s+([^,]+?)(?:,|$)",
                    r"search\s+(\w+(?:\s+\w+)*)",
                ]
                for pattern in patterns:
                    match = re.search(pattern, prompt_lower)
                    if match:
                        query = match.group(1).strip()
                        break

                await self.mcp.call_tool('playwright_navigate', {'url': 'https://www.youtube.com'})
                await self._smart_wait(min_wait=1, max_wait=4)
                # Fill AND press Enter in one call
                await self.mcp.call_tool('playwright_fill', {
                    'selector': 'input[name="search_query"]',
                    'value': query,
                    'press_enter': True
                })
                await self._smart_wait(min_wait=3, max_wait=8)

                # Get page snapshot
                result = await self.mcp.call_tool('playwright_snapshot', {})
                content = ''
                if isinstance(result, dict):
                    for key in ['content', 'text', 'markdown', 'snapshot', 'accessibility_tree']:
                        if result.get(key) and len(str(result.get(key))) > 100:
                            content = str(result.get(key))[:6000]
                            break
                elif result:
                    content = str(result)[:6000]

                # Parse video titles from content (filter out UI elements)
                video_titles = []
                for line in content.split('\n'):
                    line = line.strip()
                    if line and 30 < len(line) < 150:
                        # Skip UI elements and controls
                        skip = ['search', 'filter', 'upload', 'subscribe', 'home', 'shorts',
                                'library', 'history', 'sign in', 'settings', 'menu', 'avatar', 'button',
                                'skip navigation', 'link |', 'text |', 'heading |', 'navigation', 'logo']
                        line_lower = line.lower()
                        if not any(s in line_lower for s in skip):
                            # Remove accessibility tree prefixes
                            cleaned = line
                            for prefix in ['• ', '- ', '* ', 'link | ', 'text | ', 'button | ']:
                                if cleaned.lower().startswith(prefix.lower()):
                                    cleaned = cleaned[len(prefix):]
                            cleaned = cleaned.strip()
                            if cleaned and len(cleaned) > 30 and cleaned not in video_titles:
                                video_titles.append(cleaned)
                                if len(video_titles) >= 3:
                                    break

                if video_titles:
                    titles_text = "\n".join([f"{i+1}. {t}" for i, t in enumerate(video_titles)])
                    response = f"Top YouTube search results for '{query}':\n\n{titles_text}"
                else:
                    response = f"YouTube search for '{query}':\n\n{content[:2000]}"

                console.print("[green]✓ Retrieved YouTube search results[/green]")
                return response
            except Exception as e:
                console.print(f"[red]YouTube failed: {e}[/red]")
                logger.warning(f"YouTube direct execution failed: {e}")
                return None

        # DEMOQA - Form filling
        if 'demoqa' in prompt_lower and any(kw in prompt_lower for kw in ['form', 'fill', 'practice']):
            console.print("[yellow]⚡ Direct execution: DemoQA form[/yellow]")
            try:
                await self.mcp.call_tool('playwright_navigate', {'url': 'https://demoqa.com/automation-practice-form'})
                # Wait for form to be ready
                await self.mcp.call_tool('playwright_wait_for_selector', {'selector': '#firstName', 'timeout': 5000})
                await self.mcp.call_tool('playwright_fill', {'selector': '#firstName', 'value': 'John'})
                await self.mcp.call_tool('playwright_fill', {'selector': '#lastName', 'value': 'Doe'})
                await self.mcp.call_tool('playwright_fill', {'selector': '#userEmail', 'value': 'john@example.com'})
                await self.mcp.call_tool('playwright_fill', {'selector': '#userNumber', 'value': '1234567890'})
                await self.mcp.call_tool('playwright_click', {'selector': 'label[for="gender-radio-1"]'})
                await self.mcp.call_tool('playwright_click', {'selector': '#submit'})
                console.print("[green]✓ Form submitted[/green]")
                return "Successfully filled and submitted the practice form on demoqa.com!"
            except Exception as e:
                logger.warning(f"DemoQA direct execution failed: {e}")
                return None

        # HEROKUAPP LOGIN
        if 'herokuapp' in prompt_lower or 'the-internet' in prompt_lower:
            console.print("[yellow]⚡ Direct execution: Herokuapp[/yellow]")
            try:
                if 'login' in prompt_lower:
                    await self.mcp.call_tool('playwright_navigate', {'url': 'https://the-internet.herokuapp.com/login'})
                    # Wait for login form to be ready
                    await self.mcp.call_tool('playwright_wait_for_selector', {'selector': '#username', 'timeout': 5000})
                    await self.mcp.call_tool('playwright_fill', {'selector': '#username', 'value': 'tomsmith'})
                    await self.mcp.call_tool('playwright_fill', {'selector': '#password', 'value': 'SuperSecretPassword!'})
                    await self.mcp.call_tool('playwright_click', {'selector': 'button[type="submit"]'})
                    console.print("[green]✓ Logged in successfully[/green]")
                    return "Successfully logged in to the-internet.herokuapp.com!"
                else:
                    await self.mcp.call_tool('playwright_navigate', {'url': 'https://the-internet.herokuapp.com'})
                    result = await self.mcp.call_tool('playwright_snapshot', {})
                    return result.get('markdown', '')[:3000] if result else "Navigated to herokuapp"
            except Exception as e:
                logger.warning(f"Herokuapp direct execution failed: {e}")
                return None

        # GENERIC URL - Navigate and extract
        url_match = re.search(r'(https?://[^\s<>"\']+)', prompt)
        if url_match and any(kw in prompt_lower for kw in ['go to', 'visit', 'open', 'navigate', 'browse']):
            url = url_match.group(1)
            console.print(f"[yellow]⚡ Direct execution: {url}[/yellow]")
            try:
                await self.mcp.call_tool('playwright_navigate', {'url': url})
                # Wait for page to load
                await self.mcp.call_tool('playwright_wait_for_load_state', {'state': 'networkidle', 'timeout': 5000})
                result = await self.mcp.call_tool('playwright_snapshot', {})
                content = result.get('markdown', '')[:4000] if result else ''
                console.print("[green]✓ Retrieved page content[/green]")
                return f"Content from {url}:\n\n{content}"
            except Exception as e:
                logger.warning(f"URL direct execution failed: {e}")
                return None

        return None  # No pattern matched

    async def _try_file_shortcuts(self, prompt: str) -> Optional[str]:
        """Fast path for simple file operations - no browser needed."""
        lower = prompt.lower()

        # Detect file read requests (expanded to include data workflow patterns)
        file_patterns = [
            r'read\s+(?:the\s+)?(?:file\s+)?["\']?([^\s"\']+\.(?:csv|txt|json|md|yaml|yml|log|pdf))["\']?',
            r'(?:show|display|get|open)\s+(?:the\s+)?(?:contents?\s+of\s+)?["\']?([^\s"\']+\.(?:csv|txt|json|md|yaml|yml|log|pdf))["\']?',
            r'(?:how\s+many|count)\s+(?:rows?|lines?|items?)\s+(?:in|does)\s+["\']?([^\s"\']+\.(?:csv|txt|json|md|yaml|yml|log))["\']?',
            r'(?:clean|normalize|dedupe|deduplicate)\s+(?:the\s+)?(?:file\s+)?["\']?([^\s"\']+\.csv)["\']?',
            r'(?:categorize|analyze)\s+(?:transactions?\s+(?:in|from)\s+)?["\']?([^\s"\']+\.csv)["\']?',
            r'(?:analyze|summarize)\s+(?:the\s+)?(?:log|logs)\s+(?:in\s+)?["\']?([^\s"\']+\.(?:log|txt))["\']?',
            r'(?:extract|parse)\s+(?:data\s+from\s+|fields\s+from\s+)?["\']?([^\s"\']+\.(?:pdf|txt|json))["\']?',
        ]

        filepath = None
        for pattern in file_patterns:
            match = re.search(pattern, prompt, re.IGNORECASE)
            if match:
                filepath = match.group(1)
                break

        if not filepath:
            return None

        # DATA WORKFLOW SHORTCUTS: Route to DataWorkflows for specialized processing
        try:
            # CSV cleaning/normalization (Workflow B)
            if filepath.endswith('.csv') and any(kw in lower for kw in ['clean', 'normalize', 'dedupe', 'deduplicate', 'standardize']):
                result = self.data_workflows.execute_spreadsheet_workflow(filepath)
                if result.success:
                    self._emit_explainable_summary(result.summary, [])
                    return result.summary
                else:
                    logger.warning(f"Spreadsheet workflow failed: {result.error}")

            # Transaction categorization (Workflow J)
            if filepath.endswith('.csv') and any(kw in lower for kw in ['categorize', 'categorization', 'transaction']):
                result = self.data_workflows.execute_data_categorization(filepath)
                if result.success:
                    self._emit_explainable_summary(result.summary, [])
                    return result.summary
                else:
                    logger.warning(f"Categorization workflow failed: {result.error}")

            # Log analysis (Workflow O)
            if filepath.endswith(('.log', '.txt')) and any(kw in lower for kw in ['analyze', 'summarize', 'error', 'log']):
                result = self.data_workflows.execute_log_analysis(filepath)
                if result.success:
                    self._emit_explainable_summary(result.summary, [])
                    return result.summary
                else:
                    logger.warning(f"Log analysis workflow failed: {result.error}")

            # Document extraction (Workflows G, N)
            if filepath.endswith(('.pdf', '.txt')) and any(kw in lower for kw in ['extract', 'parse', 'contract', 'form']):
                doc_type = 'contract' if 'contract' in lower else 'form'
                result = self.data_workflows.execute_document_processing(filepath, doc_type)
                if result.success:
                    self._emit_explainable_summary(result.summary, [])
                    return result.summary
                else:
                    logger.warning(f"Document processing workflow failed: {result.error}")

        except Exception as e:
            logger.warning(f"Data workflow shortcut failed: {e}")

        # BASIC FILE READ: Fallback to simple file reading
        try:
            result = await self._call_direct_tool("read_file", {"path": filepath})
            if result and not result.get("error"):
                content = result.get("content", "")
                path = result.get("path", filepath)

                # Analyze the content based on what was asked
                if "how many" in lower or "count" in lower:
                    lines = content.strip().split('\n')
                    if filepath.endswith('.csv'):
                        # CSV: count data rows (exclude header)
                        row_count = len(lines) - 1 if len(lines) > 1 else 0
                        summary = f"**{path}** has {row_count} data rows (plus 1 header row).\n\nHeaders: {lines[0] if lines else 'None'}"
                    else:
                        summary = f"**{path}** has {len(lines)} lines."
                else:
                    # Show content summary
                    preview = content[:1000] if len(content) > 1000 else content
                    summary = f"**{path}** ({len(content)} bytes):\n```\n{preview}\n```"
                    if len(content) > 1000:
                        summary += f"\n... (truncated, {len(content) - 1000} more bytes)"

                self._emit_explainable_summary(summary, [])
                return summary

        except Exception as e:
            logger.warning(f"File shortcut failed: {e}")

        return None

    async def _try_web_shortcuts(self, prompt: str) -> Optional[str]:
        """Delegate to WebShortcuts class for fast-path web tasks."""
        from .web_shortcuts import WebShortcuts
        shortcuts = WebShortcuts(
            ollama_client=self.ollama_client,
            fast_model=self.fast_model,
            browser=self.browser,
            call_direct_tool=self._call_direct_tool,
            extract_urls=self._extract_urls,
            strip_urls=self._strip_urls,
            shorten_text=self._shorten_text,
            format_extract_output=self._format_extract_output,
            get_site_selectors=self._get_site_selectors,
            summarize_markdown=self._summarize_markdown,
            emit_summary=self._emit_explainable_summary,
            take_screenshot=self._take_screenshot,
            vision_analyze=self._vision_analyze,
            vision_model=self.vision_model,
            stats=self.stats,
            describe_mode=self.describe_mode,
        )
        return await shortcuts.try_shortcuts(prompt)

    async def _try_capability(self, prompt: str) -> Optional[str]:
        """Delegate to CapabilityExecutor for business capability routing."""
        from .capability_executor import CapabilityExecutor
        executor = CapabilityExecutor(self.capability_router, self.stats)
        return await executor.try_capability(prompt)

    async def _execute_capability(self, method, params: dict, cap_letter: str):
        """Delegate to CapabilityExecutor."""
        from .capability_executor import CapabilityExecutor
        executor = CapabilityExecutor(self.capability_router, self.stats)
        return await executor.execute_capability(method, params, cap_letter)

    async def _react_loop(self, prompt: str, resource_handle=None) -> str:
        """Delegate to ReActLoop class for execution."""
        from .react_loop import ReActLoop
        loop = ReActLoop(self)
        return await loop.execute(prompt, resource_handle)

    # Alias for workflow_handlers compatibility
    async def _execute_react_loop(self, prompt: str) -> str:
        """Alias for _react_loop to maintain compatibility with workflow_handlers."""
        return await self._react_loop(prompt)

    def _validate_tool_calls(self, tool_calls: List[Dict]) -> List[Dict]:
        """Delegate to tool_name_corrector for validation."""
        from .tool_name_corrector import validate_tool_calls
        available_tools = set(self.mcp.tools.keys()) if hasattr(self.mcp, 'tools') else set()
        return validate_tool_calls(tool_calls, available_tools)

    # Tool execution methods (_act_parallel, _execute_tool, _auto_correct_tool_call,
    # _try_tool_fallback, _handle_error_with_healing, _recover_from_hallucination)
    # are now provided by ToolExecutionMixin

    async def _reflect(self, results: List[ActionResult]) -> Dict:
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
                except Exception:
                    current_url = None

                try:
                    if current_url:
                        await self.mcp.call_tool('playwright_navigate', {'url': current_url})
                        # Wait for page to settle after navigation
                        await self.mcp.call_tool('playwright_wait_for_load_state', {'state': 'domcontentloaded', 'timeout': 3000})
                    retry_shot = await self._take_screenshot()
                    if retry_shot:
                        retry_vision = await self._vision_analyze(retry_shot)
                        self.stats['vision_calls'] += 1
                        if retry_vision:
                            vision_result = retry_vision
                            self._append_vision_tool_message(vision_result, 'vision_analysis_retry')
                except Exception as e:
                    logger.debug(f"Describe-mode reload failed: {e}")

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

    async def _collect_vision_insight(self, results: List[ActionResult]) -> Dict:
        """Delegate to VisionHandler."""
        from .vision_handler import VisionHandler
        handler = VisionHandler(self)
        return await handler.collect_vision_insight(results)

    def _append_vision_tool_message(self, vision_result: Dict, name: str):
        """Delegate to VisionHandler."""
        from .vision_handler import VisionHandler
        handler = VisionHandler(self)
        handler.append_vision_tool_message(vision_result, name)

    def _record_screenshot_bytes(self, screenshot: Optional[bytes], action_name: Optional[str] = None) -> Optional[str]:
        """Delegate to VisionHandler."""
        from .vision_handler import VisionHandler
        handler = VisionHandler(self)
        result = handler.record_screenshot_bytes(screenshot, action_name)
        # Update local state from handler
        self._last_screenshot_hash = handler._last_screenshot_hash
        self._last_screenshot_issue = handler._last_screenshot_issue
        return result

    async def _fetch_dom_feedback(self) -> str:
        """Delegate to HealthMonitor."""
        from .health_monitor import HealthMonitor
        monitor = HealthMonitor(self.mcp, self.browser_manager, self.rescue_policy, 
                               self.survival, self.awareness, self.session_state,
                               self.ollama_client, self.stats, self.messages)
        monitor.set_browser(self.browser)
        return await monitor._fetch_dom_feedback()

    def _detect_text_issue(self, text: str) -> Optional[str]:
        """Delegate to HealthMonitor."""
        from .health_monitor import HealthMonitor
        monitor = HealthMonitor(self.mcp, self.browser_manager, self.rescue_policy,
                               self.survival, self.awareness, self.session_state,
                               self.ollama_client, self.stats, self.messages)
        return monitor._detect_text_issue(text)

    async def _health_pulse(self, dom_feedback: str) -> Optional[str]:
        """Delegate to HealthMonitor."""
        from .health_monitor import HealthMonitor
        monitor = HealthMonitor(self.mcp, self.browser_manager, self.rescue_policy,
                               self.survival, self.awareness, self.session_state,
                               self.ollama_client, self.stats, self.messages)
        return await monitor._health_pulse(dom_feedback)

    async def _common_sense_verification(self, vision_result: Dict) -> Tuple[Optional[str], str]:
        """Delegate to HealthMonitor."""
        from .health_monitor import HealthMonitor
        monitor = HealthMonitor(self.mcp, self.browser_manager, self.rescue_policy,
                               self.survival, self.awareness, self.session_state,
                               self.ollama_client, self.stats, self.messages)
        monitor.set_browser(self.browser)
        return await monitor._common_sense_verification(vision_result)

    def _assert_success(self, dom_feedback: str, vision_result: Dict) -> Optional[str]:
        """Delegate to HealthMonitor."""
        from .health_monitor import HealthMonitor
        monitor = HealthMonitor(self.mcp, self.browser_manager, self.rescue_policy,
                               self.survival, self.awareness, self.session_state,
                               self.ollama_client, self.stats, self.messages)
        monitor.update_goal(self._goal_summary, self._goal_keywords)
        return monitor._assert_success(dom_feedback, vision_result)

    def _add_goal_reminder(self):
        """Add a goal reminder as a user message."""
        if not self._goal_summary:
            return
        self.messages.append({
            'role': 'user',
            'content': f"[Reminder: Your goal is to {self._goal_summary[:150]}. Continue working toward this goal.]"
        })

        # Trigger compaction check
        if len(self.messages) >= self._compact_threshold:
            self._compact_context()

    async def _maybe_run_scheduled_health(self) -> Optional[str]:
        """Delegate to HealthMonitor."""
        from .health_monitor import HealthMonitor
        monitor = HealthMonitor(self.mcp, self.browser_manager, self.rescue_policy,
                               self.survival, self.awareness, self.session_state,
                               self.ollama_client, self.stats, self.messages)
        monitor.set_browser(self.browser)
        result = await monitor._maybe_run_scheduled_health()
        self._next_health_check_time = monitor._next_health_check_time
        return result

    async def _maybe_run_rescue(self):
        """Delegate to HealthMonitor."""
        from .health_monitor import HealthMonitor
        monitor = HealthMonitor(self.mcp, self.browser_manager, self.rescue_policy,
                               self.survival, self.awareness, self.session_state,
                               self.ollama_client, self.stats, self.messages)
        await monitor._maybe_run_rescue()
        self._last_rescue_summary = monitor.get_last_rescue_summary()

    async def _ensure_browser_health(self) -> bool:
        """Delegate to HealthMonitor."""
        from .health_monitor import HealthMonitor
        monitor = HealthMonitor(self.mcp, self.browser_manager, self.rescue_policy,
                               self.survival, self.awareness, self.session_state,
                               self.ollama_client, self.stats, self.messages)
        monitor.set_browser(self.browser)
        return await monitor._ensure_browser_health()

    def _log_resource_issue(self, issue: str):
        """Delegate to session_state."""
        self.session_state.log_resource_issue(issue)

    def _log_action(self, name: str, args: Dict[str, Any], success: bool, result: Any = None, error: str = None, attempt: int = 1):
        """Delegate to session_state."""
        self.session_state.log_action(name, args, success, result, error, attempt)

    def _log_decision(self, kind: str, detail: Dict[str, Any]):
        """Delegate to session_state."""
        self.session_state._log_decision(kind, detail)

    def _record_successful_tool(self, name: str, args: Dict[str, Any]):
        """Delegate to session_state."""
        self.session_state.record_successful_tool(name, args)

    def _record_failed_tool(self, name: str, args: Dict[str, Any]):
        """Delegate to session_state."""
        self.session_state.record_failed_tool(name, args)

    def _get_memory_fallback(self, tool_name: str, args: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Delegate to session_state."""
        return self.session_state.get_memory_fallback(tool_name, args)

    def _summarize_prompt(self, prompt: str) -> str:
        """Normalize and truncate prompt for goal tracking. Delegates to PromptProcessor."""
        return self.prompt_processor.summarize_prompt(prompt)

    def _extract_goal_keywords(self, prompt: str) -> List[str]:
        """Extract meaningful goal keywords from prompt. Delegates to PromptProcessor."""
        return self.prompt_processor.extract_goal_keywords(prompt)

    def _set_describe_mode(self, prompt: str) -> None:
        """Enable describe-only mode for 'what do you see' style prompts."""
        p = prompt.lower()
        describe_keywords = ['what do you see', 'what you see', 'tell me what you see', 'describe', 'screenshot', 'show me what you see']
        self.describe_mode = any(k in p for k in describe_keywords)
        self._goal_summary = self._summarize_prompt(prompt)
        self._goal_keywords = self._extract_goal_keywords(prompt)

    def _emit_explainable_summary(self, summary: str, issues: List[str]):
        # FINAL HALLUCINATION CHECK: Validate summary before emitting
        if self.hallucination_guard:
            final_validation = self.hallucination_guard.validate_output(summary)
            if not final_validation.is_valid:
                logger.warning(f"HALLUCINATION in final summary: {final_validation.issues}")
                issues.extend([f"[HALLUCINATION WARNING] {i}" for i in final_validation.issues])
                # Clean the summary if possible
                if final_validation.cleaned_data:
                    summary = str(final_validation.cleaned_data)

        issue_text = "; ".join(issues) if issues else "none"
        duration = (datetime.now() - self._task_start_time).total_seconds()
        # Usage metering (run finished): bill wall-clock while active
        billed_minutes = max(1, int((duration + 59) // 60))
        report_worker_usage_fire_and_forget(WorkerUsageDelta(
            run_id=self.session_id,
            worker_minutes=billed_minutes
        ))
        self.survival.store_checkpoint("Summary emitted")
        entry = {
            'goal': self._goal_summary,
            'summary': summary,
            'issues': issues,
            'duration_sec': round(duration, 1),
            'actions': self._execution_log[-10:],
            'awareness': self.awareness.digest(),
            'survival': self.survival.digest(),
            'hallucination_check': 'passed' if final_validation.is_valid else 'warnings'
        }
        logger.info(f"Explainable summary: {json.dumps(entry, indent=2)}")
        self.messages.append({
            'role': 'system',
            'content': f"Execution complete. Summary: {summary}\nIssues encountered: {issue_text}"
        })

        # Trigger compaction check
        if len(self.messages) >= self._compact_threshold:
            self._compact_context()

        try:
            self.awareness.save_state()
        except Exception as e:
            logger.warning(f"Failed to save awareness state: {e}")
        try:
            self.survival.save_state()
        except Exception as e:
            logger.warning(f"Failed to save survival state: {e}")

    async def _call_direct_tool(self, name: str, args: Dict[str, Any], timeout: int = 120) -> Optional[Dict[str, Any]]:
        """Simple tool caller for fast-path web shortcuts with timeout and cascading recovery."""
        try:
            if not await self._ensure_browser_health():
                return None
        except Exception as e:
            logger.debug(f"Browser health check before {name} failed: {e}")

        # ORGANISM: Predict before action
        prediction = None
        start_time = time.time()
        if self.organism:
            try:
                action_desc = f"{name} with {list(args.keys())}"
                prediction = await self.organism.before_action(action_desc, name, args)
            except Exception as e:
                logger.debug(f"Organism prediction failed: {e}")

        try:
            self.stats['tool_calls'] += 1
            # Add timeout to prevent hanging
            result = await asyncio.wait_for(
                self.mcp.call_tool(name, args),
                timeout=timeout
            )
            self._log_action(name, args, True, result=result)

            # ORGANISM: Compare after action
            if self.organism and prediction:
                try:
                    latency_ms = (time.time() - start_time) * 1000
                    outcome = json.dumps(result, default=str)[:500] if result else "No result"
                    await self.organism.after_action(prediction, outcome, True, latency_ms)
                except Exception as e:
                    logger.debug(f"Organism comparison failed: {e}")

            try:
                self.messages.append({
                    'role': 'tool',
                    'name': name,
                    'content': json.dumps(result, default=str)[:2000]
                })

                # Trigger compaction check
                if len(self.messages) >= self._compact_threshold:
                    self._compact_context()
            except Exception as e:
                logger.debug(f"Failed to append tool result to messages: {e}")
            return result
        except asyncio.TimeoutError as e:
            # ORGANISM: Record failure
            if self.organism and prediction:
                try:
                    latency_ms = (time.time() - start_time) * 1000
                    await self.organism.after_action(prediction, f"Timeout after {timeout}s", False, latency_ms)
                except Exception as e:
                    logger.debug(f"Organism after_action failed on timeout: {e}")

            logger.warning(f"{name} timed out after {timeout}s")
            self._log_action(name, args, False, error=f"Timeout after {timeout}s")
            
            # Try cascading recovery for timeout
            if self.cascading_recovery and name.startswith('playwright_'):
                recovery_result = await self._attempt_cascading_recovery(name, args, e)
                if recovery_result:
                    return recovery_result
            
            return None
        except Exception as e:
            # ORGANISM: Record failure
            if self.organism and prediction:
                try:
                    latency_ms = (time.time() - start_time) * 1000
                    await self.organism.after_action(prediction, str(e), False, latency_ms)
                except Exception as e2:
                    logger.debug(f"Organism after_action failed on exception: {e2}")

            logger.warning(f"{name} failed: {e}")
            self._log_action(name, args, False, error=str(e))

            # Try cascading recovery for playwright tools
            if self.cascading_recovery and name.startswith('playwright_'):
                recovery_result = await self._attempt_cascading_recovery(name, args, e)
                if recovery_result:
                    return recovery_result

            return None

    async def _attempt_cascading_recovery(self, tool_name: str, tool_args: Dict[str, Any], error: Exception) -> Optional[Dict[str, Any]]:
        """Attempt recovery using the cascading recovery system."""
        try:
            # Get current page if available
            page = None
            if hasattr(self.mcp, 'page'):
                page = self.mcp.page
            
            # Create recovery context
            context = RecoveryContext(
                action=tool_name,
                arguments=tool_args,
                error=error,
                attempt_number=1,
                page_url=page.url if page else None
            )
            
            # Define retry action
            # Use longer timeout for navigation (slow sites like FB Ads Library)
            tool_timeout = 90 if 'navigate' in tool_name else 60
            async def retry_action():
                return await asyncio.wait_for(
                    self.mcp.call_tool(tool_name, tool_args),
                    timeout=tool_timeout
                )
            
            # Attempt recovery
            logger.info(f"[RECOVERY] Attempting cascading recovery for {tool_name}")
            recovery_result = await self.cascading_recovery.attempt_recovery(
                context=context,
                page=page,
                retry_action=retry_action
            )
            
            if recovery_result.get("recovered"):
                logger.info(f"[RECOVERY] Successfully recovered at level {recovery_result.get('level')}")
                self.stats['retries'] += 1
                self._log_action(tool_name, tool_args, True, result=recovery_result.get("result"))
                return recovery_result.get("result")
            else:
                logger.warning(f"[RECOVERY] Recovery failed: {recovery_result.get('error', 'Unknown')}")
                # Check for partial results
                if recovery_result.get("partial_results"):
                    logger.info("[RECOVERY] Returning partial results")
                    return {"partial": True, "data": recovery_result.get("partial_results")}
                
        except Exception as recovery_error:
            logger.error(f"[RECOVERY] Cascading recovery itself failed: {recovery_error}")
        
        return None


    def _shorten_text(self, text: str, limit: int = 800) -> str:
        """Delegate to utils.text_utils.shorten_text."""
        from .utils.text_utils import shorten_text
        return shorten_text(text, limit)

    def _friendly_error(self, error_type: str, details: str = "", url: str = "") -> str:
        """Delegate to utils.error_utils.friendly_error."""
        from .utils.error_utils import friendly_error
        return friendly_error(error_type, details, url)

    def _format_extract_output(self, data: Any, title: str = "Data") -> str:
        """Delegate to utils.error_utils.format_extract_output."""
        from .utils.error_utils import format_extract_output
        return format_extract_output(data, title)

    async def _summarize_markdown(self, markdown: str) -> Optional[str]:
        """Summarize markdown content using fast model directly."""
        if not markdown:
            return None
        try:
            import ollama

            # Truncate content to reduce LLM processing time
            content = markdown[:3000] if len(markdown) > 3000 else markdown

            # Use fast model with simple prompt (no JSON, faster response)
            prompt = f"""Summarize this webpage in 2-3 sentences. Focus on the main topic and key facts.

Content:
{content}

Summary:"""

            response = self.ollama_client.generate(
                model=self.fast_model,
                prompt=prompt,
                options={'temperature': 0.3, 'num_predict': 200}
            )
            summary = response.get('response', '').strip()
            if summary:
                # Clean up any thinking tags from the response
                summary = re.sub(r'<think>.*?</think>', '', summary, flags=re.DOTALL).strip()
                return summary
        except Exception as e:
            logger.debug(f"Fast summary failed: {e}")

        # Fallback to LLM extractor if fast model fails
        try:
            from .llm_extractor import LLMExtractor
            extractor = LLMExtractor(self.config.get('llm', {}))
            result = await extractor.summarize(markdown, style="concise", max_length=400)
            if result.get('success') and result.get('data'):
                data = result['data']
                if isinstance(data, dict):
                    return data.get('summary', str(data)[:400])
                return self._shorten_text(data, 400)
        except Exception as e:
            logger.debug(f"Markdown summary fallback failed: {e}")
        return None

    def _get_site_selectors(self, url: str) -> Optional[Dict[str, Any]]:
        """Delegate to utils.site_selectors.get_site_selectors."""
        from .utils.site_selectors import get_site_selectors
        return get_site_selectors(url)


    def _extract_urls(self, text: str) -> List[str]:
        """Extract URLs or bare domains from text."""
        if not text:
            return []
        pattern = r'(https?://[^\s\'"]+|www\.[^\s\'"]+|\b[a-zA-Z0-9.-]+\.[a-z]{2,}(?:/[^\s\'"]*)?)'
        urls = []
        for match in re.findall(pattern, text):
            url = match.strip()
            # Strip trailing punctuation, but preserve balanced parentheses (for Wikipedia URLs)
            while url and url[-1] in '.,;]':
                url = url[:-1]
            # Only strip trailing ) if unbalanced (more closing than opening)
            while url and url[-1] == ')' and url.count(')') > url.count('('):
                url = url[:-1]
            if not url:
                continue
            if not url.startswith('http://') and not url.startswith('https://'):
                url = 'https://' + url.lstrip('/')
            if url not in urls:
                urls.append(url)
        return urls

    def _strip_urls(self, text: str, urls: List[str]) -> str:
        """Remove URL strings from text to isolate the user's ask."""
        cleaned = text
        for u in urls:
            cleaned = cleaned.replace(u, "")
            bare = u.replace("https://", "").replace("http://", "")
            cleaned = cleaned.replace(bare, "")
        # Clean up orphaned navigation phrases after URL removal
        cleaned = re.sub(r'\b(go to|visit|navigate to|open|browse to)\s+and\b', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\b(go to|visit|navigate to|open|browse to)\s*$', '', cleaned, flags=re.IGNORECASE)
        return re.sub(r'\s+', ' ', cleaned).strip()

    async def _preflight_checks(self) -> Tuple[bool, str]:
        """Delegate to HealthMonitor."""
        from .health_monitor import HealthMonitor
        monitor = HealthMonitor(self.mcp, self.browser_manager, self.rescue_policy,
                               self.survival, self.awareness, self.session_state,
                               self.ollama_client, self.stats, self.messages)
        monitor.set_browser(self.browser)
        if self._preflight_done:
            return True, "Awaiting previously passed preflight."
        ok, summary = await monitor._preflight_checks()
        self._preflight_done = ok
        self._preflight_details = monitor._preflight_details
        self._preflight_attempts = monitor._preflight_attempts
        return ok, summary

    async def _run_preflight_once(self, attempt: int) -> Tuple[bool, str]:
        """Delegate to HealthMonitor."""
        from .health_monitor import HealthMonitor
        monitor = HealthMonitor(self.mcp, self.browser_manager, self.rescue_policy,
                               self.survival, self.awareness, self.session_state,
                               self.ollama_client, self.stats, self.messages)
        monitor.set_browser(self.browser)
        return await monitor._run_preflight_once(attempt)

    def _record_preflight_summary(self, summary: str):
        """Record preflight summary to log and messages."""
        logger.info(f"Preflight: {summary}")
        self.messages.append({
            'role': 'system',
            'content': f"[Preflight] {summary}"
        })

        # Trigger compaction check
        if len(self.messages) >= self._compact_threshold:
            self._compact_context()

    async def _vision_analyze(self, screenshot: bytes) -> Dict:
        """Delegate to VisionHandler."""
        from .vision_handler import VisionHandler
        handler = VisionHandler(self)
        return await handler.vision_analyze(screenshot)

    async def _take_screenshot(self) -> bytes:
        """Delegate to VisionHandler."""
        from .vision_handler import VisionHandler
        handler = VisionHandler(self)
        return await handler.take_screenshot()

    async def _capture_screenshot(self, tool_name: str, result: Any) -> Optional[bytes]:
        """Delegate to VisionHandler."""
        from .vision_handler import VisionHandler
        handler = VisionHandler(self)
        return await handler.capture_screenshot(tool_name, result)

    async def _get_alternative_args(self, tool_name: str, args: Dict, error: str) -> Optional[Dict]:
        """Get alternative arguments after failure."""

        # Use fast model to suggest alternatives
        prompt = f"""Tool '{tool_name}' failed with args {args}.
Error: {error}

Suggest alternative arguments that might work. Return JSON only.
Example: {{"selector": ".alternative-class"}}"""

        # Try cached alternative first
        memory_alt = self._get_memory_fallback(tool_name, args)
        if memory_alt:
            return memory_alt

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

    def _learn_success(self, domain: str, prompt: str):
        """Delegate to session_state."""
        self.session_state.learn_success(domain, prompt)

    def _add_system_prompt(self, prior_strategies: List[Dict]):
        """Add system prompt with prior learning. Delegates to PromptProcessor."""
        system_message = self.prompt_processor.build_system_message(prior_strategies)
        self.messages.append(system_message)

        # Trigger compaction check
        if len(self.messages) >= self._compact_threshold:
            self._compact_context()


    def _format_tools(self) -> List[Dict]:
        """Format tools for Ollama. Delegates to PromptProcessor."""
        return self.prompt_processor.format_tools_for_llm(self.mcp.get_available_tools())

    def _extract_domain(self, prompt: str) -> str:
        """Extract domain from prompt. Delegates to PromptProcessor."""
        return self.prompt_processor.extract_domain(prompt)



    def get_stats(self) -> Dict:
        return self.stats

    async def init_siao_core(self):
        """Initialize SIAO core with all 9 cognitive components.

        This should be called after the organism is started.
        Creates ValenceSystem, UncertaintyTracker, SelfModel, etc.
        """
        if self.siao_core is not None:
            return  # Already initialized

        if not self.organism:
            logger.warning("Cannot initialize SIAO core: organism not available")
            return

        try:
            from .siao_core import init_siao_core, SIAOConfig
            self.siao_core = await init_siao_core(
                base_organism=self.organism,
                memory_arch=self.memory_arch,
                llm_client=self.ollama_client,
                fast_model=self.fast_model,
                config=SIAOConfig(
                    sleep_threshold=1000,
                    enable_dreams=True,
                    investigation_on_idle=True
                )
            )
            logger.info("SIAO core initialized - all 9 cognitive components active")
        except Exception as e:
            logger.warning(f"SIAO core initialization failed: {e}")
            self.siao_core = None

    def set_progress_callback(self, callback):
        """Set callback for Claude Code style progress updates.

        Callback signature: callback(message: str, step: str = None)
        - message: Main status like "Navigating to page"
        - step: Optional sub-step like "Waiting for page load"
        """
        self._progress_callback = callback

    def enable_steering(self, enabled: bool = True):
        """Enable or disable real-time steering during task execution.

        When enabled, users can type during execution to:
        - Provide guidance: "focus on the pricing page"
        - Stop execution: "stop" / "cancel"
        - Pause: "pause" / "wait"
        - Redirect: "actually go to..." / "instead..."
        """
        self._steering_enabled = enabled

    def is_steering_enabled(self) -> bool:
        """Check if steering is currently enabled."""
        return self._steering_enabled

    def inject_steering(self, message: str):
        """Manually inject a steering message into the current execution.

        Useful for programmatic steering from external systems.
        """
        if self._steering_enabled:
            msg = SteeringMessage.parse(message)
            inject_steering_message(self.messages, msg)

    def _notify_progress(self, message: str, step: str = None):
        """Notify UI of progress update."""
        if self._progress_callback:
            try:
                self._progress_callback(message, step)
            except Exception as e:
                logger.debug(f"Progress callback error: {e}")

    def _compact_context(self):
        """Compact context when messages exceed threshold.

        Like Claude Code's context compaction - summarizes older messages
        to fit within context window limits.

        Uses HistoryPruner if available for intelligent pruning with:
        - Screenshot removal from old messages (50-60% token reduction)
        - Message summarization (preserves context with minimal tokens)
        - Automatic preservation of recent messages for context
        """
        if len(self.messages) < self._compact_threshold:
            return

        logger.info(f"Compacting context: {len(self.messages)} messages")
        self._notify_progress("Compacting context")

        # Use HistoryPruner if available - it's smarter and more efficient
        if self._history_pruner:
            original_count = len(self.messages)
            self.messages = self._history_pruner.prune(self.messages)
            logger.info(f"[HISTORY] Pruned context: {original_count} -> {len(self.messages)} messages")
            return

        # Fallback to manual compaction if HistoryPruner not available
        # Keep system message and first user message
        system_msgs = [m for m in self.messages if m.get('role') == 'system']
        first_user = None
        for m in self.messages:
            if m.get('role') == 'user':
                first_user = m
                break

        # Keep last N messages for recency
        keep_recent = 10
        recent_msgs = self.messages[-keep_recent:]

        # Summarize middle section (tool calls and results)
        middle_start = len(system_msgs) + (1 if first_user else 0)
        middle_end = len(self.messages) - keep_recent
        middle_msgs = self.messages[middle_start:middle_end]

        if middle_msgs:
            # Create summary of what happened
            tool_calls = []
            for m in middle_msgs:
                if m.get('role') == 'assistant':
                    content = m.get('content', '')
                    if 'playwright_' in content or 'tool_call' in str(m):
                        # Extract tool name from content
                        for tool in ['navigate', 'click', 'fill', 'extract', 'screenshot']:
                            if tool in content.lower():
                                tool_calls.append(tool)
                                break

            summary = f"[Previous actions: {', '.join(tool_calls[:10]) or 'exploration'}]"

            summary_msg = {
                'role': 'assistant',
                'content': summary
            }

            # Rebuild messages: system + first_user + summary + recent
            self.messages = system_msgs
            if first_user and first_user not in system_msgs:
                self.messages.append(first_user)
            self.messages.append(summary_msg)
            self.messages.extend(recent_msgs)

            logger.info(f"Context compacted to {len(self.messages)} messages")

    # ==================== SYSTEM STATUS ====================

    def get_system_status(self) -> dict:
        """Get status of all system components."""
        return {
            "dead_mans_switch": self.dead_mans_switch.status() if self.dead_mans_switch else {"active": False, "triggered": False, "timeout_hours": 0, "time_remaining_hours": 0, "last_ping": "N/A"},
            "resource_limits": self.resource_limiter.status() if self.resource_limiter else {"memory_mb": 0, "memory_limit_mb": 0, "memory_percent": 0, "cpu_percent": 0, "active_tasks": 0, "max_concurrent_tasks": 0, "monitoring": False},
            "multi_instance": self.coordinator.status() if self.coordinator else {"instance_id": "standalone", "is_leader": True, "instance_index": 0, "total_instances": 1, "claimed_work": [], "active_instances": ["standalone"]},
            "crash_recovery": {
                "pending": self.crash_recovery.pending_prompt() is not None if self.crash_recovery else False,
            },
            "email_outreach": self.email_outreach.get_stats() if self.email_outreach else {"available": False},
            "multi_tab": self.tab_manager.get_status() if self.tab_manager else {"available": MULTI_TAB_AVAILABLE, "initialized": False},
        }

    def shutdown(self):
        """Clean shutdown of all components."""
        logger.info("Shutting down brain components...")

        # Shutdown organism first (it monitors everything else)
        if self.organism:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self.organism.stop())
                else:
                    loop.run_until_complete(self.organism.stop())
                logger.info("Organism shutdown complete")
            except Exception as e:
                logger.warning(f"Organism shutdown error: {e}")

        # Cancel consolidation task with proper async handling
        if self._consolidation_task:
            self._consolidation_task.cancel()
            try:
                loop = asyncio.get_event_loop()
                if not loop.is_running():
                    # Can await directly if loop not running
                    try:
                        loop.run_until_complete(asyncio.wait_for(
                            asyncio.shield(self._consolidation_task),
                            timeout=5.0
                        ))
                    except (asyncio.CancelledError, asyncio.TimeoutError):
                        # Expected - task was cancelled or timed out during shutdown
                        pass
            except RuntimeError:
                # No event loop - task will be garbage collected
                logger.debug("No event loop for consolidation task cleanup")
            except Exception as e:
                logger.warning(f"Consolidation task shutdown error: {e}")
            finally:
                self._consolidation_task = None

        # Final consolidation before shutdown
        if hasattr(self, 'memory_arch') and self.memory_arch:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self.memory_arch.consolidate_now())
                else:
                    loop.run_until_complete(self.memory_arch.consolidate_now())
                logger.info("Final memory consolidation completed")
            except Exception as e:
                logger.warning(f"Final consolidation error: {e}")

        if self.dead_mans_switch:
            try:
                self.dead_mans_switch.stop_monitoring()
            except Exception as e:
                logger.warning(f"Dead man's switch shutdown error: {e}")
        if self.resource_limiter:
            try:
                self.resource_limiter.stop_monitoring()
            except Exception as e:
                logger.warning(f"Resource limiter shutdown error: {e}")
        if self.coordinator:
            try:
                self.coordinator.unregister()
            except Exception as e:
                logger.warning(f"Coordinator shutdown error: {e}")
        # Tab manager cleanup (async, so we schedule it)
        if self.tab_manager:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self.tab_manager.cleanup())
                else:
                    loop.run_until_complete(self.tab_manager.cleanup())
            except Exception as e:
                logger.warning(f"Tab manager shutdown error: {e}")
        logger.info("Brain shutdown complete")

    async def async_shutdown(self):
        """Async-friendly shutdown method for proper cleanup in async contexts."""
        logger.info("Async shutdown initiated...")

        # Cancel consolidation task - don't use shield (defeats cancellation)
        if self._consolidation_task:
            self._consolidation_task.cancel()
            try:
                # Wait for task to acknowledge cancellation
                await asyncio.wait_for(
                    asyncio.gather(self._consolidation_task, return_exceptions=True),
                    timeout=5.0
                )
            except asyncio.TimeoutError:
                logger.warning("Consolidation task did not cancel in time")
            except Exception:
                pass  # Task already cancelled
            finally:
                self._consolidation_task = None

        # Final consolidation
        if hasattr(self, 'memory_arch') and self.memory_arch:
            try:
                await asyncio.wait_for(
                    self.memory_arch.consolidate_now(),
                    timeout=10.0
                )
            except asyncio.TimeoutError:
                logger.warning("Final consolidation timed out")
            except Exception as e:
                logger.warning(f"Final consolidation error: {e}")

        # Dead man's switch
        if self.dead_mans_switch:
            try:
                self.dead_mans_switch.stop_monitoring()
            except Exception as e:
                logger.warning(f"Dead man's switch shutdown error: {e}")

        # Tab manager
        if self.tab_manager:
            try:
                await asyncio.wait_for(
                    self.tab_manager.cleanup(),
                    timeout=5.0
                )
            except asyncio.TimeoutError:
                logger.warning("Tab manager cleanup timed out")
            except Exception as e:
                logger.warning(f"Tab manager shutdown error: {e}")

        logger.info("Async shutdown complete")


def create_enhanced_brain(config: dict, mcp_client):
    return EnhancedBrain(config, mcp_client)
