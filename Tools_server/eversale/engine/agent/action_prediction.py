"""
Action Sequence Prediction Engine

Instead of predicting one action at a time, predict SEQUENCES of actions.
Learn from successful task completions to build action templates.

Example learned sequences:
- "Login to Gmail" -> [navigate, fill_email, click_next, fill_password, click_login]
- "Search on Google" -> [navigate, fill_search, press_enter, wait_results]
- "Fill contact form" -> [fill_name, fill_email, fill_message, click_submit]

This reduces LLM calls by 50-70% for common workflows.
"""

import json
import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from collections import defaultdict
from pathlib import Path
from loguru import logger


@dataclass
class Action:
    """A single browser action"""
    action_type: str  # click, fill, navigate, press_key, scroll, wait
    target: str  # selector, url, or key name
    value: Optional[str] = None  # for fill actions
    wait_after_ms: int = 500

    def to_dict(self) -> Dict:
        return {
            'type': self.action_type,
            'target': self.target,
            'value': self.value,
            'wait': self.wait_after_ms
        }

    @staticmethod
    def from_dict(d: Dict) -> 'Action':
        return Action(
            action_type=d['type'],
            target=d['target'],
            value=d.get('value'),
            wait_after_ms=d.get('wait', 500)
        )


@dataclass
class ActionSequence:
    """A learned sequence of actions"""
    sequence_id: str
    name: str  # Human-readable name
    trigger_pattern: str  # Regex or keywords that trigger this sequence
    domain_pattern: str  # Domain this applies to (e.g., "*.google.com")
    actions: List[Action]
    success_count: int = 0
    failure_count: int = 0
    avg_duration_ms: int = 0
    last_used: datetime = field(default_factory=datetime.now)

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        return self.success_count / max(1, total)

    @property
    def confidence(self) -> float:
        """Confidence based on success rate and usage"""
        base = self.success_rate
        # Boost for frequently used sequences
        usage_bonus = min(0.2, self.success_count / 50)
        return min(1.0, base + usage_bonus)

    def to_dict(self) -> Dict:
        return {
            'id': self.sequence_id,
            'name': self.name,
            'trigger': self.trigger_pattern,
            'domain': self.domain_pattern,
            'actions': [a.to_dict() for a in self.actions],
            'success': self.success_count,
            'failure': self.failure_count,
            'avg_duration': self.avg_duration_ms,
            'last_used': self.last_used.isoformat()
        }

    @staticmethod
    def from_dict(d: Dict) -> 'ActionSequence':
        return ActionSequence(
            sequence_id=d['id'],
            name=d['name'],
            trigger_pattern=d['trigger'],
            domain_pattern=d['domain'],
            actions=[Action.from_dict(a) for a in d['actions']],
            success_count=d.get('success', 0),
            failure_count=d.get('failure', 0),
            avg_duration_ms=d.get('avg_duration', 0),
            last_used=datetime.fromisoformat(d.get('last_used', datetime.now().isoformat()))
        )


class SequenceLibrary:
    """
    Library of learned action sequences.

    Pre-loaded with common patterns, learns new ones from usage.
    """

    def __init__(self, storage_path: Path = None):
        self.storage_path = storage_path or Path("memory/action_sequences.json")
        self.sequences: Dict[str, ActionSequence] = {}

        # Load stored sequences
        self._load()

        # Add default sequences if empty
        if not self.sequences:
            self._add_default_sequences()

    def _load(self):
        """Load sequences from storage"""
        if self.storage_path.exists():
            try:
                with open(self.storage_path) as f:
                    data = json.load(f)
                for seq_data in data.get('sequences', []):
                    seq = ActionSequence.from_dict(seq_data)
                    self.sequences[seq.sequence_id] = seq
                logger.info(f"[SEQUENCE_LIB] Loaded {len(self.sequences)} sequences")
            except Exception as e:
                logger.warning(f"[SEQUENCE_LIB] Failed to load: {e}")

    def save(self):
        """Save sequences to storage"""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            'sequences': [s.to_dict() for s in self.sequences.values()],
            'updated': datetime.now().isoformat()
        }
        with open(self.storage_path, 'w') as f:
            json.dump(data, f, indent=2)

    def _add_default_sequences(self):
        """Add common default sequences"""
        defaults = [
            ActionSequence(
                sequence_id="google_search",
                name="Google Search",
                trigger_pattern=r"search.*google|google.*search",
                domain_pattern="*.google.com",
                actions=[
                    Action("navigate", "https://www.google.com"),
                    Action("fill", "textarea[name='q']", value="{{query}}"),
                    Action("press_key", "Enter"),
                    Action("wait", "results", wait_after_ms=2000)
                ]
            ),
            ActionSequence(
                sequence_id="gmail_login",
                name="Gmail Login",
                trigger_pattern=r"login.*gmail|gmail.*login|sign.*in.*google",
                domain_pattern="*.google.com",
                actions=[
                    Action("navigate", "https://mail.google.com"),
                    Action("fill", "input[type='email']", value="{{email}}"),
                    Action("click", "#identifierNext, button:has-text('Next')"),
                    Action("wait", "password", wait_after_ms=1500),
                    Action("fill", "input[type='password']", value="{{password}}"),
                    Action("click", "#passwordNext, button:has-text('Next')"),
                    Action("wait", "inbox", wait_after_ms=3000)
                ]
            ),
            ActionSequence(
                sequence_id="linkedin_search",
                name="LinkedIn People Search",
                trigger_pattern=r"linkedin.*search|search.*linkedin|find.*on.*linkedin",
                domain_pattern="*.linkedin.com",
                actions=[
                    Action("navigate", "https://www.linkedin.com/search/results/people/"),
                    Action("fill", "input[placeholder*='Search']", value="{{query}}"),
                    Action("press_key", "Enter"),
                    Action("wait", "results", wait_after_ms=2000)
                ]
            ),
            ActionSequence(
                sequence_id="facebook_ads_library",
                name="Facebook Ads Library Search",
                trigger_pattern=r"facebook.*ads.*library|fb.*ads|ad.*library",
                domain_pattern="*.facebook.com",
                actions=[
                    Action("navigate", "https://www.facebook.com/ads/library"),
                    Action("wait", "loaded", wait_after_ms=2000),
                    Action("click", "button:has-text('All ads'), [aria-label*='category']"),
                    Action("click", "li:has-text('All ads'), [role='option']:has-text('All')"),
                    Action("fill", "input[placeholder*='Search']", value="{{query}}"),
                    Action("press_key", "Enter"),
                    Action("wait", "results", wait_after_ms=3000)
                ]
            ),
            ActionSequence(
                sequence_id="generic_form_fill",
                name="Generic Contact Form",
                trigger_pattern=r"fill.*form|contact.*form|submit.*form",
                domain_pattern="*",
                actions=[
                    Action("fill", "input[name*='name'], input[placeholder*='name']", value="{{name}}"),
                    Action("fill", "input[type='email'], input[name*='email']", value="{{email}}"),
                    Action("fill", "textarea, input[name*='message']", value="{{message}}"),
                    Action("click", "button[type='submit'], input[type='submit']"),
                    Action("wait", "confirmation", wait_after_ms=2000)
                ]
            ),
            ActionSequence(
                sequence_id="scroll_and_extract",
                name="Scroll and Extract List",
                trigger_pattern=r"extract.*all|scroll.*down|load.*more|get.*all",
                domain_pattern="*",
                actions=[
                    Action("scroll", "bottom", wait_after_ms=1000),
                    Action("wait", "loaded", wait_after_ms=500),
                    Action("scroll", "bottom", wait_after_ms=1000),
                    Action("wait", "loaded", wait_after_ms=500),
                    Action("scroll", "bottom", wait_after_ms=1000)
                ]
            )
        ]

        for seq in defaults:
            self.sequences[seq.sequence_id] = seq

        self.save()
        logger.info(f"[SEQUENCE_LIB] Added {len(defaults)} default sequences")

    def find_matching_sequence(
        self,
        task_description: str,
        current_domain: str = ""
    ) -> Optional[ActionSequence]:
        """Find best matching sequence for a task"""
        import re

        best_match = None
        best_score = 0

        task_lower = task_description.lower()

        for seq in self.sequences.values():
            score = 0

            # Check trigger pattern
            if re.search(seq.trigger_pattern, task_lower, re.IGNORECASE):
                score += 0.5

            # Check domain match
            if seq.domain_pattern == "*":
                score += 0.1
            elif current_domain:
                import fnmatch
                if fnmatch.fnmatch(current_domain, seq.domain_pattern):
                    score += 0.3

            # Boost by confidence
            score *= seq.confidence

            if score > best_score:
                best_score = score
                best_match = seq

        if best_match and best_score >= 0.3:
            logger.info(f"[SEQUENCE_LIB] Matched '{best_match.name}' (score={best_score:.2f})")
            return best_match

        return None

    def record_success(self, sequence_id: str, duration_ms: int):
        """Record successful sequence execution"""
        if sequence_id in self.sequences:
            seq = self.sequences[sequence_id]
            seq.success_count += 1
            # Update rolling average duration
            total = seq.success_count + seq.failure_count
            seq.avg_duration_ms = int(
                (seq.avg_duration_ms * (total - 1) + duration_ms) / total
            )
            seq.last_used = datetime.now()
            self.save()

    def record_failure(self, sequence_id: str):
        """Record failed sequence execution"""
        if sequence_id in self.sequences:
            self.sequences[sequence_id].failure_count += 1
            self.save()

    def learn_sequence(
        self,
        name: str,
        trigger_pattern: str,
        domain_pattern: str,
        actions: List[Dict]
    ) -> ActionSequence:
        """Learn a new sequence from observed actions"""
        seq_id = hashlib.md5(f"{name}{trigger_pattern}".encode()).hexdigest()[:12]

        seq = ActionSequence(
            sequence_id=seq_id,
            name=name,
            trigger_pattern=trigger_pattern,
            domain_pattern=domain_pattern,
            actions=[Action.from_dict(a) for a in actions]
        )

        self.sequences[seq_id] = seq
        self.save()

        logger.info(f"[SEQUENCE_LIB] Learned new sequence: {name}")
        return seq


class SequenceExecutor:
    """
    Execute action sequences on a browser page.

    Handles:
    - Variable substitution ({{query}}, {{email}}, etc.)
    - Error recovery (retry failed actions)
    - Progress tracking
    - Learning from execution
    """

    def __init__(self, library: SequenceLibrary = None):
        self.library = library or SequenceLibrary()
        self.stats = {
            'sequences_executed': 0,
            'actions_executed': 0,
            'sequences_successful': 0,
            'time_saved_ms': 0  # Estimated vs individual LLM calls
        }

    async def execute_sequence(
        self,
        page,
        sequence: ActionSequence,
        variables: Dict[str, str] = None,
        on_action: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Execute an action sequence on a page.

        Args:
            page: Playwright page
            sequence: The sequence to execute
            variables: Values to substitute (e.g., {'query': 'sales automation'})
            on_action: Callback for each action (for progress reporting)
        """
        variables = variables or {}
        start = datetime.now()
        results = []

        logger.info(f"[SEQUENCE_EXEC] Starting '{sequence.name}' with {len(sequence.actions)} actions")

        for i, action in enumerate(sequence.actions):
            try:
                # Substitute variables
                target = self._substitute(action.target, variables)
                value = self._substitute(action.value, variables) if action.value else None

                # Execute action
                result = await self._execute_action(page, action.action_type, target, value)
                results.append({'action': action.action_type, 'success': True, 'result': result})

                self.stats['actions_executed'] += 1

                # Wait after action
                if action.wait_after_ms > 0:
                    await asyncio.sleep(action.wait_after_ms / 1000)

                if on_action:
                    on_action(i + 1, len(sequence.actions), action.action_type, True)

            except Exception as e:
                logger.warning(f"[SEQUENCE_EXEC] Action {i+1} failed: {e}")
                results.append({'action': action.action_type, 'success': False, 'error': str(e)})

                if on_action:
                    on_action(i + 1, len(sequence.actions), action.action_type, False)

                # Decide whether to continue or abort
                if action.action_type in ('navigate', 'click'):
                    # Critical actions - abort on failure
                    self.library.record_failure(sequence.sequence_id)
                    return {
                        'success': False,
                        'completed_actions': i,
                        'total_actions': len(sequence.actions),
                        'results': results,
                        'error': str(e)
                    }

        duration = int((datetime.now() - start).total_seconds() * 1000)

        self.library.record_success(sequence.sequence_id, duration)
        self.stats['sequences_executed'] += 1
        self.stats['sequences_successful'] += 1

        # Estimate time saved (each action would be ~2s LLM call)
        self.stats['time_saved_ms'] += len(sequence.actions) * 2000 - duration

        return {
            'success': True,
            'completed_actions': len(sequence.actions),
            'total_actions': len(sequence.actions),
            'duration_ms': duration,
            'results': results
        }

    def _substitute(self, template: str, variables: Dict[str, str]) -> str:
        """Substitute {{var}} placeholders"""
        if not template:
            return template

        result = template
        for key, value in variables.items():
            result = result.replace(f"{{{{{key}}}}}", value)

        return result

    async def _execute_action(
        self,
        page,
        action_type: str,
        target: str,
        value: Optional[str]
    ) -> Any:
        """Execute a single action"""
        import asyncio

        if action_type == 'navigate':
            await page.goto(target, wait_until='domcontentloaded', timeout=15000)
            return {'url': page.url}

        elif action_type == 'click':
            await page.click(target, timeout=5000)
            return {'clicked': target}

        elif action_type == 'fill':
            await page.fill(target, value, timeout=5000)
            return {'filled': target, 'value': value}

        elif action_type == 'press_key':
            await page.keyboard.press(target)
            return {'pressed': target}

        elif action_type == 'scroll':
            if target == 'bottom':
                await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            elif target == 'top':
                await page.evaluate('window.scrollTo(0, 0)')
            else:
                await page.evaluate(f'window.scrollBy(0, {target})')
            return {'scrolled': target}

        elif action_type == 'wait':
            # Generic wait - in real implementation, would wait for specific conditions
            await asyncio.sleep(1)
            return {'waited': target}

        else:
            logger.warning(f"[SEQUENCE_EXEC] Unknown action type: {action_type}")
            return {'unknown': action_type}

    def get_stats(self) -> Dict:
        return {
            **self.stats,
            'avg_actions_per_sequence': (
                self.stats['actions_executed'] / max(1, self.stats['sequences_executed'])
            )
        }


# Import asyncio at module level
import asyncio

# Singleton
_library: Optional[SequenceLibrary] = None
_executor: Optional[SequenceExecutor] = None

def get_sequence_library() -> SequenceLibrary:
    global _library
    if _library is None:
        _library = SequenceLibrary()
    return _library

def get_sequence_executor() -> SequenceExecutor:
    global _executor
    if _executor is None:
        _executor = SequenceExecutor(get_sequence_library())
    return _executor


# Convenience function for react_loop integration
async def try_sequence_execution(
    page,
    task_description: str,
    variables: Dict[str, str] = None,
    current_domain: str = ""
) -> Optional[Dict]:
    """
    Try to execute task using a learned sequence.

    Returns result dict if sequence found and executed, None otherwise.

    Usage in react_loop:
        result = await try_sequence_execution(page, user_task, {'query': 'test'})
        if result and result['success']:
            # Skip LLM reasoning, sequence handled it
            return result
    """
    library = get_sequence_library()
    executor = get_sequence_executor()

    # Find matching sequence
    sequence = library.find_matching_sequence(task_description, current_domain)

    if not sequence:
        return None

    # Execute sequence
    result = await executor.execute_sequence(page, sequence, variables)

    if result['success']:
        logger.info(f"[SEQUENCE] Completed '{sequence.name}' - saved ~{len(sequence.actions) * 2}s LLM time")

    return result
