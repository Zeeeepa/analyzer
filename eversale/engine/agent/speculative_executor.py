"""
Speculative Action Pre-Execution Engine

While the LLM is reasoning, predict and pre-execute likely next actions.
When decision arrives, use cached result or discard speculation.

Key insight: LLM thinking takes 1-3 seconds. Browser actions take 0.5-2s.
We can execute 2-3 speculative actions during LLM think time.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
from collections import defaultdict
from loguru import logger
import hashlib

@dataclass
class SpeculativeAction:
    """A speculative action to pre-execute"""
    action_type: str  # click, fill, navigate, extract
    target: str  # selector, url, or description
    confidence: float  # 0-1 probability this is the right action
    params: Dict[str, Any] = field(default_factory=dict)

@dataclass
class SpeculativeResult:
    """Result of speculative execution"""
    action: SpeculativeAction
    success: bool
    result: Any
    duration_ms: int
    timestamp: datetime
    cache_key: str

class ActionPredictor:
    """
    Predict next actions based on:
    1. Current page state (forms -> fill, buttons -> click)
    2. Task goal (extract -> look for data patterns)
    3. Historical patterns (what actions followed similar states)
    4. DOM structure (visible interactive elements)
    """

    def __init__(self):
        # Historical action patterns: {page_signature: [(action, frequency)]}
        self.patterns: Dict[str, List[tuple]] = defaultdict(list)
        # Task-based predictions
        self.task_hints = {
            'login': ['fill_email', 'fill_password', 'click_submit'],
            'search': ['fill_search', 'click_search', 'wait_results'],
            'extract': ['scroll', 'click_pagination', 'extract_data'],
            'form': ['fill_fields', 'click_submit', 'wait_confirmation'],
        }

    def predict_next_actions(
        self,
        page_state: Dict,
        task_goal: str,
        history: List[Dict],
        max_predictions: int = 3
    ) -> List[SpeculativeAction]:
        """Predict most likely next actions with confidence scores"""
        predictions = []

        # 1. Page-based predictions (highest confidence)
        # Look for obvious next steps
        if page_state.get('has_search_input') and 'search' in task_goal.lower():
            predictions.append(SpeculativeAction(
                action_type='fill',
                target='input[type="search"], input[name*="search"], [placeholder*="search"]',
                confidence=0.9,
                params={'extract_query_from_goal': True}
            ))

        if page_state.get('has_login_form'):
            predictions.append(SpeculativeAction(
                action_type='fill_login',
                target='form[action*="login"], #login-form',
                confidence=0.85
            ))

        # 2. Interactive elements on page
        buttons = page_state.get('buttons', [])
        for btn in buttons[:3]:
            if any(kw in btn.get('text', '').lower() for kw in ['submit', 'search', 'next', 'continue']):
                predictions.append(SpeculativeAction(
                    action_type='click',
                    target=btn.get('selector'),
                    confidence=0.7
                ))

        # 3. Historical patterns
        page_sig = self._get_page_signature(page_state)
        if page_sig in self.patterns:
            for action, freq in self.patterns[page_sig][:2]:
                predictions.append(SpeculativeAction(
                    action_type=action['type'],
                    target=action['target'],
                    confidence=min(0.6, freq / 10)  # Cap at 0.6 for historical
                ))

        # 4. Task-based hints
        for task_type, actions in self.task_hints.items():
            if task_type in task_goal.lower():
                # Add first unhit action from the sequence
                for act in actions:
                    if not self._action_in_history(act, history):
                        predictions.append(SpeculativeAction(
                            action_type=act.split('_')[0],
                            target=act,
                            confidence=0.5
                        ))
                        break

        # Sort by confidence and return top N
        predictions.sort(key=lambda x: x.confidence, reverse=True)
        return predictions[:max_predictions]

    def _get_page_signature(self, page_state: Dict) -> str:
        """Create a signature for the page state"""
        key_elements = [
            page_state.get('url_pattern', ''),
            str(page_state.get('form_count', 0)),
            str(page_state.get('button_count', 0)),
            page_state.get('page_type', 'unknown')
        ]
        return hashlib.md5('|'.join(key_elements).encode()).hexdigest()[:12]

    def _action_in_history(self, action_name: str, history: List[Dict]) -> bool:
        """Check if action type was already performed"""
        for h in history:
            if action_name in str(h.get('action', '')):
                return True
        return False

    def record_pattern(self, page_state: Dict, action_taken: Dict):
        """Learn from actual actions taken"""
        sig = self._get_page_signature(page_state)
        # Update frequency
        for i, (act, freq) in enumerate(self.patterns[sig]):
            if act.get('type') == action_taken.get('type') and act.get('target') == action_taken.get('target'):
                self.patterns[sig][i] = (act, freq + 1)
                return
        # New pattern
        self.patterns[sig].append((action_taken, 1))


class SpeculativeExecutor:
    """
    Execute speculative actions while LLM thinks.

    Architecture:
    - Main tab: Current user-visible state
    - Shadow tabs: Pre-execute predicted actions
    - Result cache: Store results keyed by action hash
    """

    def __init__(self, browser_manager, max_shadow_tabs: int = 2):
        self.browser = browser_manager
        self.predictor = ActionPredictor()
        self.max_shadow_tabs = max_shadow_tabs

        # Shadow tab pool
        self.shadow_tabs: List[Any] = []

        # Result cache: {action_hash: SpeculativeResult}
        self.result_cache: Dict[str, SpeculativeResult] = {}
        self.cache_ttl = timedelta(seconds=30)  # Results valid for 30s

        # Metrics
        self.stats = {
            'predictions_made': 0,
            'speculations_executed': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'time_saved_ms': 0
        }

        # Async lock for cache operations
        self._cache_lock = asyncio.Lock()

    async def initialize_shadow_tabs(self, context):
        """Create shadow tabs for speculative execution"""
        for i in range(self.max_shadow_tabs):
            try:
                tab = await context.new_page()
                await tab.set_viewport_size({'width': 1280, 'height': 720})
                self.shadow_tabs.append(tab)
                logger.debug(f"[SPECULATIVE] Created shadow tab {i+1}")
            except Exception as e:
                logger.warning(f"[SPECULATIVE] Failed to create shadow tab: {e}")

    async def speculate_during_llm_think(
        self,
        current_page_state: Dict,
        task_goal: str,
        action_history: List[Dict],
        current_url: str
    ) -> None:
        """
        Called when LLM starts thinking. Predict and pre-execute actions.
        """
        # Get predictions
        predictions = self.predictor.predict_next_actions(
            current_page_state,
            task_goal,
            action_history
        )

        if not predictions:
            return

        self.stats['predictions_made'] += len(predictions)
        logger.info(f"[SPECULATIVE] Predicting {len(predictions)} actions during LLM think")

        # Execute top predictions in shadow tabs
        tasks = []
        for i, pred in enumerate(predictions[:self.max_shadow_tabs]):
            if i < len(self.shadow_tabs):
                tasks.append(self._execute_in_shadow(
                    self.shadow_tabs[i],
                    pred,
                    current_url
                ))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _execute_in_shadow(
        self,
        shadow_tab,
        action: SpeculativeAction,
        base_url: str
    ) -> Optional[SpeculativeResult]:
        """Execute a speculative action in a shadow tab"""
        start = datetime.now()
        cache_key = self._get_action_hash(action, base_url)

        try:
            # Navigate shadow tab to current URL if needed
            if shadow_tab.url != base_url:
                await shadow_tab.goto(base_url, wait_until='domcontentloaded', timeout=5000)

            result = None

            if action.action_type == 'click':
                elem = await shadow_tab.query_selector(action.target)
                if elem:
                    await elem.click()
                    await shadow_tab.wait_for_load_state('networkidle', timeout=3000)
                    result = {'url': shadow_tab.url, 'clicked': True}

            elif action.action_type == 'extract':
                # Pre-extract data
                content = await shadow_tab.content()
                result = {'html_length': len(content), 'url': shadow_tab.url}

            elif action.action_type == 'scroll':
                await shadow_tab.evaluate('window.scrollBy(0, 500)')
                result = {'scrolled': True}

            duration = int((datetime.now() - start).total_seconds() * 1000)

            spec_result = SpeculativeResult(
                action=action,
                success=result is not None,
                result=result,
                duration_ms=duration,
                timestamp=datetime.now(),
                cache_key=cache_key
            )

            # Cache result
            async with self._cache_lock:
                self.result_cache[cache_key] = spec_result

            self.stats['speculations_executed'] += 1
            logger.debug(f"[SPECULATIVE] Pre-executed {action.action_type} in {duration}ms")

            return spec_result

        except Exception as e:
            logger.debug(f"[SPECULATIVE] Shadow execution failed: {e}")
            return None

    def check_cache(self, action_type: str, target: str, url: str) -> Optional[SpeculativeResult]:
        """Check if we have a cached result for this action"""
        cache_key = self._get_action_hash(
            SpeculativeAction(action_type, target, 0),
            url
        )

        if cache_key in self.result_cache:
            result = self.result_cache[cache_key]
            # Check TTL
            if datetime.now() - result.timestamp < self.cache_ttl:
                self.stats['cache_hits'] += 1
                self.stats['time_saved_ms'] += result.duration_ms
                logger.info(f"[SPECULATIVE] Cache HIT - saved {result.duration_ms}ms")
                return result

        self.stats['cache_misses'] += 1
        return None

    def _get_action_hash(self, action: SpeculativeAction, url: str) -> str:
        """Create unique hash for action+context"""
        key = f"{action.action_type}|{action.target}|{url}"
        return hashlib.md5(key.encode()).hexdigest()[:16]

    async def cleanup(self):
        """Close shadow tabs"""
        for tab in self.shadow_tabs:
            try:
                await tab.close()
            except:
                pass
        self.shadow_tabs.clear()

    def get_stats(self) -> Dict:
        """Get speculation statistics"""
        return {
            **self.stats,
            'cache_hit_rate': (
                self.stats['cache_hits'] / max(1, self.stats['cache_hits'] + self.stats['cache_misses'])
            ),
            'avg_time_saved_per_hit': (
                self.stats['time_saved_ms'] / max(1, self.stats['cache_hits'])
            )
        }


# Singleton instance
_speculative_executor: Optional[SpeculativeExecutor] = None

def get_speculative_executor(browser_manager=None) -> SpeculativeExecutor:
    """Get or create the speculative executor"""
    global _speculative_executor
    if _speculative_executor is None and browser_manager:
        _speculative_executor = SpeculativeExecutor(browser_manager)
    return _speculative_executor


async def speculate_wrapper(func: Callable, *args, **kwargs):
    """
    Wrapper that runs speculation while waiting for a slow operation.

    Usage:
        result = await speculate_wrapper(
            llm_call,  # The slow operation
            page_state=state,
            task_goal=goal
        )
    """
    executor = get_speculative_executor()

    # Start speculation in background
    spec_task = None
    if executor and kwargs.get('page_state') and kwargs.get('task_goal'):
        spec_task = asyncio.create_task(
            executor.speculate_during_llm_think(
                kwargs.pop('page_state'),
                kwargs.pop('task_goal'),
                kwargs.pop('action_history', []),
                kwargs.pop('current_url', '')
            )
        )

    # Run the main operation
    try:
        result = await func(*args, **kwargs)
    finally:
        # Wait for speculation to complete
        if spec_task:
            try:
                await asyncio.wait_for(spec_task, timeout=0.1)
            except asyncio.TimeoutError:
                pass  # Let speculation continue in background

    return result
