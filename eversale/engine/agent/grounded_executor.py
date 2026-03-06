"""
Grounded Executor - Execution layer that keeps the model honest.

Fixes all the gaps:
1. DOM injection - Model sees actual page structure
2. Tool verification - Catch failures immediately, retry with alternatives
3. Selector constraint - Force picking from valid selectors
4. Session memory - Remember what worked on this page
5. State tracking - Track page state across actions
6. Screenshot to text - Convert visuals to text for non-multimodal models

No more hallucination. No more silent failures. Real grounding.
"""

import json
import re
import hashlib
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from loguru import logger


@dataclass
class PageState:
    """Current state of the page."""
    url: str
    title: str
    dom_summary: str
    valid_selectors: List[Dict]
    text_content: str
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    def get_hash(self) -> str:
        """Get hash of page state for comparison."""
        content = f"{self.url}:{self.title}:{self.dom_summary[:500]}"
        return hashlib.md5(content.encode()).hexdigest()[:12]


@dataclass
class ActionResult:
    """Result of a grounded action."""
    success: bool
    action_type: str
    selector_used: str
    result_data: Any
    error: Optional[str]
    retries: int = 0
    alternative_used: Optional[str] = None


@dataclass
class SessionMemory:
    """Memory of what works on specific pages/domains."""
    domain: str
    working_selectors: Dict[str, List[str]] = field(default_factory=dict)  # action -> selectors that work
    failed_selectors: Dict[str, List[str]] = field(default_factory=dict)   # action -> selectors that fail
    page_patterns: Dict[str, str] = field(default_factory=dict)  # page_hash -> notes
    last_updated: str = ""


class GroundedExecutor:
    """
    Execution layer that grounds the model in reality.

    Every action is:
    1. Constrained to valid selectors from actual DOM
    2. Verified immediately after execution
    3. Retried with alternatives on failure
    4. Recorded for future learning
    """

    def __init__(self, mcp_client):
        self.mcp = mcp_client

        # Current page state
        self.current_state: Optional[PageState] = None

        # Session memory per domain
        self.session_memory: Dict[str, SessionMemory] = {}
        self.memory_path = Path("workspace/session_memory.json")
        self._load_memory()

        # Action history for this session
        self.action_history: List[ActionResult] = []

        # Stats
        self.stats = {
            'actions_attempted': 0,
            'actions_succeeded': 0,
            'retries_needed': 0,
            'alternatives_used': 0,
            'hallucinations_blocked': 0
        }

    # =========================================================================
    # 1. DOM INJECTION - Get actual page structure for prompts
    # =========================================================================

    async def get_page_state(self) -> PageState:
        """
        Get current page state including DOM structure.

        This is what gets injected into prompts so the model
        can see ACTUAL elements, not guess from training data.
        """
        try:
            # Get URL via JavaScript evaluation
            url_result = await self.mcp.call_tool('playwright_evaluate', {
                'script': 'window.location.href'
            })
            url = self._extract_string(url_result) or 'unknown'

            # Get page title
            title = ""
            try:
                title_result = await self.mcp.call_tool('playwright_evaluate', {
                    'script': 'document.title'
                })
                title = self._extract_string(title_result) or ""
            except Exception:
                pass

            # Get visible text content
            text_result = await self.mcp.call_tool('playwright_get_text', {'selector': 'body'})
            text_content = self._extract_string(text_result, 'text') or ""

            # Get DOM summary with selectors
            dom_summary, valid_selectors = await self._extract_dom_structure()

            self.current_state = PageState(
                url=url,
                title=title,
                dom_summary=dom_summary,
                valid_selectors=valid_selectors,
                text_content=text_content[:5000]  # Limit size
            )

            return self.current_state

        except Exception as e:
            logger.error(f"[GROUNDED] Failed to get page state: {e}")
            return PageState(
                url='error',
                title='',
                dom_summary='Could not read page',
                valid_selectors=[],
                text_content=''
            )

    async def _extract_dom_structure(self) -> Tuple[str, List[Dict]]:
        """
        Extract simplified DOM structure with valid selectors.

        Returns human-readable summary + list of actionable elements.
        """
        try:
            # JavaScript to extract actionable elements
            extract_script = """
            (() => {
                const elements = [];

                // Buttons
                document.querySelectorAll('button, [role="button"], input[type="submit"], input[type="button"]').forEach((el, i) => {
                    if (i < 20) {
                        const text = el.textContent?.trim().slice(0, 50) || el.value || '';
                        const selector = el.getAttribute('data-testid')
                            ? `[data-testid="${el.getAttribute('data-testid')}"]`
                            : el.id
                                ? `#${el.id}`
                                : el.className
                                    ? `.${el.className.split(' ')[0]}`
                                    : `button:has-text("${text.slice(0, 20)}")`;
                        elements.push({type: 'button', text, selector, tag: el.tagName});
                    }
                });

                // Links
                document.querySelectorAll('a[href]').forEach((el, i) => {
                    if (i < 30) {
                        const text = el.textContent?.trim().slice(0, 50) || '';
                        const href = el.getAttribute('href');
                        const selector = el.getAttribute('data-testid')
                            ? `[data-testid="${el.getAttribute('data-testid')}"]`
                            : `a[href="${href}"]`;
                        elements.push({type: 'link', text, selector, href: href?.slice(0, 100)});
                    }
                });

                // Inputs
                document.querySelectorAll('input, textarea, select').forEach((el, i) => {
                    if (i < 15) {
                        const name = el.name || el.id || '';
                        const placeholder = el.placeholder || '';
                        const selector = el.name
                            ? `[name="${el.name}"]`
                            : el.id
                                ? `#${el.id}`
                                : `input[placeholder="${placeholder}"]`;
                        elements.push({type: 'input', name, placeholder, selector, inputType: el.type});
                    }
                });

                // Data containers (for extraction)
                document.querySelectorAll('[data-testid], article, [role="article"], .post, .item, .card').forEach((el, i) => {
                    if (i < 20) {
                        const testId = el.getAttribute('data-testid');
                        const selector = testId
                            ? `[data-testid="${testId}"]`
                            : el.className
                                ? `.${el.className.split(' ')[0]}`
                                : el.tagName.toLowerCase();
                        elements.push({type: 'container', selector, childCount: el.children.length});
                    }
                });

                return elements;
            })()
            """.strip()

            result = await self.mcp.call_tool('playwright_evaluate', {
                'script': extract_script
            })

            elements = []
            if isinstance(result, list):
                elements = result
            elif isinstance(result, dict) and 'result' in result:
                elements = result['result'] if isinstance(result['result'], list) else []

            # Build human-readable summary
            summary_lines = ["PAGE STRUCTURE:"]

            buttons = [e for e in elements if e.get('type') == 'button']
            if buttons:
                summary_lines.append("\nBUTTONS:")
                for b in buttons[:10]:
                    summary_lines.append(f"  • {b.get('text', 'unnamed')[:30]} → {b.get('selector')}")

            links = [e for e in elements if e.get('type') == 'link']
            if links:
                summary_lines.append("\nLINKS:")
                for l in links[:15]:
                    summary_lines.append(f"  • {l.get('text', 'unnamed')[:30]} → {l.get('selector')}")

            inputs = [e for e in elements if e.get('type') == 'input']
            if inputs:
                summary_lines.append("\nINPUTS:")
                for inp in inputs[:10]:
                    summary_lines.append(f"  • {inp.get('name') or inp.get('placeholder', 'unnamed')} → {inp.get('selector')}")

            containers = [e for e in elements if e.get('type') == 'container']
            if containers:
                summary_lines.append("\nDATA CONTAINERS:")
                for c in containers[:10]:
                    summary_lines.append(f"  • {c.get('selector')} ({c.get('childCount', 0)} children)")

            return "\n".join(summary_lines), elements

        except Exception as e:
            logger.error(f"[GROUNDED] DOM extraction failed: {e}")
            return "Could not extract DOM structure", []

    def format_page_context_for_prompt(self, page_state: PageState = None) -> str:
        """
        Format page state for injection into LLM prompt.

        This replaces hallucination with ground truth.
        """
        state = page_state or self.current_state
        if not state:
            return "PAGE STATE: Not available - navigate to a page first"

        # Get domain memory
        domain = self._extract_domain(state.url)
        memory = self.session_memory.get(domain)

        lines = [
            "=" * 60,
            "CURRENT PAGE STATE (use this, don't guess)",
            "=" * 60,
            f"URL: {state.url}",
            f"Title: {state.title}",
            "",
            state.dom_summary,
            ""
        ]

        # Add session memory hints
        if memory and memory.working_selectors:
            lines.append("KNOWN WORKING SELECTORS ON THIS SITE:")
            for action, selectors in list(memory.working_selectors.items())[:5]:
                lines.append(f"  {action}: {', '.join(selectors[:3])}")
            lines.append("")

        if memory and memory.failed_selectors:
            lines.append("KNOWN BROKEN SELECTORS (don't use):")
            for action, selectors in list(memory.failed_selectors.items())[:5]:
                lines.append(f"  ✗ {', '.join(selectors[:3])}")
            lines.append("")

        lines.append("=" * 60)
        lines.append("IMPORTANT: Use selectors from the list above.")
        lines.append("Do NOT invent selectors like .storylink, .thing, etc.")
        lines.append("=" * 60)

        return "\n".join(lines)

    # =========================================================================
    # 2. TOOL VERIFICATION + RETRY - Catch failures immediately
    # =========================================================================

    async def execute_action(self,
                              action_type: str,
                              selector: str = None,
                              params: Dict = None) -> ActionResult:
        """
        Execute an action with verification and automatic retry.

        If the selector fails, immediately try alternatives.
        """
        self.stats['actions_attempted'] += 1
        params = params or {}

        # Check if selector is known to be broken
        if selector and self._is_known_broken(selector):
            self.stats['hallucinations_blocked'] += 1
            alternative = self._get_alternative_selector(action_type, selector)
            if alternative:
                logger.info(f"[GROUNDED] Blocked hallucinated selector '{selector}', using '{alternative}'")
                selector = alternative
            else:
                return ActionResult(
                    success=False,
                    action_type=action_type,
                    selector_used=selector,
                    result_data=None,
                    error=f"Blocked hallucinated selector: {selector}"
                )

        # Try the action
        result = await self._try_action(action_type, selector, params)

        # If failed, try alternatives
        retries = 0
        max_retries = 3

        while not result.success and retries < max_retries:
            retries += 1
            self.stats['retries_needed'] += 1

            # Get alternative selector
            alternative = self._get_alternative_selector(action_type, selector, exclude=[selector])

            if not alternative:
                # Try to find from current DOM
                if self.current_state and self.current_state.valid_selectors:
                    matching = self._find_matching_selector(action_type, self.current_state.valid_selectors)
                    if matching:
                        alternative = matching

            if alternative:
                logger.info(f"[GROUNDED] Retry {retries}: trying alternative '{alternative}'")
                result = await self._try_action(action_type, alternative, params)
                result.alternative_used = alternative
                result.retries = retries

                if result.success:
                    self.stats['alternatives_used'] += 1
                    # Record the working alternative
                    self._record_selector_success(action_type, alternative)
                    self._record_selector_failure(action_type, selector)
            else:
                break

        # Record final result
        if result.success:
            self.stats['actions_succeeded'] += 1
            if selector:
                self._record_selector_success(action_type, result.selector_used)
        else:
            if selector:
                self._record_selector_failure(action_type, selector)

        self.action_history.append(result)
        return result

    async def _try_action(self, action_type: str, selector: str, params: Dict) -> ActionResult:
        """Try to execute a single action."""
        try:
            # Map action types to tool calls
            tool_mapping = {
                'click': ('playwright_click', {'selector': selector}),
                'type': ('playwright_fill', {'selector': selector, 'value': params.get('value', '')}),
                'fill': ('playwright_fill', {'selector': selector, 'value': params.get('value', '')}),
                'navigate': ('playwright_navigate', {'url': params.get('url', selector)}),
                'screenshot': ('playwright_screenshot', {}),
                'scroll': ('playwright_evaluate', {'script': 'window.scrollBy(0, 500)'}),
                'extract': ('playwright_get_text', {'selector': 'body'}),
            }

            if action_type not in tool_mapping:
                return ActionResult(
                    success=False,
                    action_type=action_type,
                    selector_used=selector or '',
                    result_data=None,
                    error=f"Unknown action type: {action_type}"
                )

            tool_name, tool_params = tool_mapping[action_type]

            # Execute
            result = await self.mcp.call_tool(tool_name, tool_params)

            # Check for errors
            result_str = str(result).lower() if result else ''
            error_indicators = ['error', 'not found', 'no element', 'timeout', 'failed']

            has_error = any(ind in result_str for ind in error_indicators)

            if has_error:
                return ActionResult(
                    success=False,
                    action_type=action_type,
                    selector_used=selector or '',
                    result_data=result,
                    error=result_str[:200]
                )

            return ActionResult(
                success=True,
                action_type=action_type,
                selector_used=selector or '',
                result_data=result,
                error=None
            )

        except Exception as e:
            return ActionResult(
                success=False,
                action_type=action_type,
                selector_used=selector or '',
                result_data=None,
                error=str(e)
            )

    # =========================================================================
    # 3. SELECTOR VALIDATION - Block hallucinated selectors
    # =========================================================================

    def _is_known_broken(self, selector: str) -> bool:
        """Check if selector is known to be broken/hallucinated."""
        from agent.selector_extractor import SelectorExtractor

        # Check against known dead selectors
        if selector.lower() in [s.lower() for s in SelectorExtractor.KNOWN_DEAD_SELECTORS]:
            return True

        # Check session memory
        domain = self._extract_domain(self.current_state.url) if self.current_state else ''
        if domain in self.session_memory:
            memory = self.session_memory[domain]
            for failed_list in memory.failed_selectors.values():
                if selector in failed_list:
                    return True

        return False

    def _get_alternative_selector(self,
                                   action_type: str,
                                   failed_selector: str,
                                   exclude: List[str] = None) -> Optional[str]:
        """Get an alternative selector for a failed one."""
        exclude = exclude or []

        # Check session memory for working alternatives
        if self.current_state:
            domain = self._extract_domain(self.current_state.url)
            if domain in self.session_memory:
                memory = self.session_memory[domain]
                working = memory.working_selectors.get(action_type, [])
                for sel in working:
                    if sel not in exclude:
                        return sel

        # Check negative examples store
        try:
            from training.negative_examples import get_negative_store
            store = get_negative_store()
            domain = self._extract_domain(self.current_state.url) if self.current_state else ''
            alt = store.get_working_alternative(failed_selector, domain)
            if alt and alt not in exclude:
                return alt
        except Exception:
            pass

        return None

    def _find_matching_selector(self, action_type: str, elements: List[Dict]) -> Optional[str]:
        """Find a selector from DOM that might match the action type."""
        type_mapping = {
            'click': ['button', 'link'],
            'type': ['input'],
            'fill': ['input'],
        }

        target_types = type_mapping.get(action_type, [])

        for elem in elements:
            if elem.get('type') in target_types:
                return elem.get('selector')

        return None

    # =========================================================================
    # 4. SESSION MEMORY - Remember what works
    # =========================================================================

    def _record_selector_success(self, action_type: str, selector: str):
        """Record that a selector worked."""
        if not self.current_state:
            return

        domain = self._extract_domain(self.current_state.url)

        if domain not in self.session_memory:
            self.session_memory[domain] = SessionMemory(domain=domain)

        memory = self.session_memory[domain]

        if action_type not in memory.working_selectors:
            memory.working_selectors[action_type] = []

        if selector not in memory.working_selectors[action_type]:
            memory.working_selectors[action_type].append(selector)
            # Keep list bounded
            memory.working_selectors[action_type] = memory.working_selectors[action_type][-20:]

        memory.last_updated = datetime.now().isoformat()
        self._save_memory()

    def _record_selector_failure(self, action_type: str, selector: str):
        """Record that a selector failed."""
        if not self.current_state:
            return

        domain = self._extract_domain(self.current_state.url)

        if domain not in self.session_memory:
            self.session_memory[domain] = SessionMemory(domain=domain)

        memory = self.session_memory[domain]

        if action_type not in memory.failed_selectors:
            memory.failed_selectors[action_type] = []

        if selector not in memory.failed_selectors[action_type]:
            memory.failed_selectors[action_type].append(selector)
            memory.failed_selectors[action_type] = memory.failed_selectors[action_type][-50:]

        memory.last_updated = datetime.now().isoformat()
        self._save_memory()

        # Also record to global negative store
        try:
            from training.negative_examples import get_negative_store
            store = get_negative_store()
            store.record_selector_failure(selector, domain, "Failed during execution")
        except Exception:
            pass

    def _load_memory(self):
        """Load session memory from disk."""
        if self.memory_path.exists():
            try:
                with open(self.memory_path) as f:
                    data = json.load(f)
                    for domain, mem_data in data.items():
                        self.session_memory[domain] = SessionMemory(**mem_data)
            except Exception as e:
                logger.warning(f"Could not load session memory: {e}")

    def _save_memory(self):
        """Save session memory to disk."""
        try:
            self.memory_path.parent.mkdir(parents=True, exist_ok=True)
            data = {domain: asdict(mem) for domain, mem in self.session_memory.items()}
            with open(self.memory_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save session memory: {e}")

    # =========================================================================
    # 5. STATE TRACKING - Track changes across actions
    # =========================================================================

    async def track_state_change(self) -> Dict:
        """
        Track what changed after an action.

        Returns dict with before/after comparison.
        """
        old_state = self.current_state
        new_state = await self.get_page_state()

        changes = {
            'url_changed': old_state.url != new_state.url if old_state else True,
            'title_changed': old_state.title != new_state.title if old_state else True,
            'content_changed': old_state.get_hash() != new_state.get_hash() if old_state else True,
            'old_url': old_state.url if old_state else None,
            'new_url': new_state.url,
        }

        return changes

    # =========================================================================
    # 6. SCREENSHOT TO TEXT - For non-multimodal models
    # =========================================================================

    async def screenshot_to_text(self) -> str:
        """
        Convert current page to text description.

        Since llama3.1 can't see images, we convert the visual
        state to text using DOM + accessibility info.
        """
        if not self.current_state:
            await self.get_page_state()

        state = self.current_state

        lines = [
            "VISUAL PAGE STATE (text representation):",
            f"Page: {state.title}",
            f"URL: {state.url}",
            "",
            "VISIBLE ELEMENTS:",
            state.dom_summary,
            "",
            "PAGE TEXT CONTENT:",
            state.text_content[:2000],
        ]

        return "\n".join(lines)

    # =========================================================================
    # UTILITIES
    # =========================================================================

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        if not url:
            return 'unknown'
        match = re.search(r'https?://(?:www\.)?([^/]+)', url)
        return match.group(1) if match else 'unknown'

    def _extract_string(self, result: Any, key: str = None) -> str:
        """Extract string from tool result."""
        if isinstance(result, str):
            return result
        if isinstance(result, dict):
            if key and key in result:
                return str(result[key])
            for k in ['content', 'text', 'result', 'url', 'value']:
                if k in result:
                    return str(result[k])
        return str(result) if result else ''

    def get_stats(self) -> Dict:
        """Get execution stats."""
        return {
            **self.stats,
            'success_rate': self.stats['actions_succeeded'] / self.stats['actions_attempted']
                if self.stats['actions_attempted'] > 0 else 0,
            'domains_in_memory': len(self.session_memory),
            'action_history_size': len(self.action_history)
        }


# Factory function
def create_grounded_executor(mcp_client) -> GroundedExecutor:
    """Create a grounded executor instance."""
    return GroundedExecutor(mcp_client)
