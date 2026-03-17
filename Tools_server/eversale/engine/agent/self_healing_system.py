#!/usr/bin/env python3
"""
Self-Healing Error Recovery System
Learns from failures and adapts strategy to reach 95%+ success
"""

from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from loguru import logger
import json
import asyncio
import time
import hashlib
import re
import sqlite3
from datetime import datetime
from pathlib import Path


@dataclass
class FailurePattern:
    """Record of a failure pattern and its solution"""
    error_type: str
    context: str
    failed_approach: Dict[str, Any]
    successful_approach: Optional[Dict[str, Any]]
    success_rate: float
    occurrences: int
    last_seen: datetime


@dataclass
class SiteProfile:
    """Site-specific learning profile for adaptive recovery."""
    domain: str
    selector_patterns: Dict[str, str] = field(default_factory=dict)  # purpose -> pattern
    success_rate: float = 0.0
    total_attempts: int = 0
    common_errors: List[str] = field(default_factory=list)
    preferred_strategies: List[str] = field(default_factory=list)
    last_updated: float = field(default_factory=time.time)


class SelfHealingSystem:
    """
    Advanced error recovery that learns and adapts
    Goal: Push success rate from 75-85% to 95%+

    New features:
    1. Proactive selector validation before use
    2. Site-specific learning profiles
    3. Layout change detection
    4. Alternative selector generation
    """

    HEALING_DB = Path.home() / ".eversale" / "self_healing.db"

    def __init__(self):
        # Knowledge base of failure patterns
        self.failure_patterns: Dict[str, FailurePattern] = {}

        # Success strategies database
        self.success_strategies: Dict[str, List[Dict]] = {
            'navigation': [],
            'interaction': [],
            'extraction': [],
        }

        # REAL success rate tracking
        self.strategy_stats: Dict[str, Dict[str, int]] = {}  # key -> {successes, failures, total}

        # Confidence thresholds
        self.min_confidence = 0.8  # Only execute if 80%+ confident

        # Proactive validation
        self._selector_cache: Dict[str, bool] = {}  # "domain:selector" -> valid
        self._cache_ttl = 300  # 5 minutes
        self._cache_timestamps: Dict[str, float] = {}

        # Site-specific learning
        self._site_profiles: Dict[str, SiteProfile] = {}
        self._profiles_path = Path("memory/site_profiles.json")

        # Layout change detection
        self._page_fingerprints: Dict[str, str] = {}  # url -> fingerprint

        # Initialize database and load existing data
        self._init_db()
        self.load_from_db()
        self._load_profiles()

    async def analyze_failure(
        self,
        error: Exception,
        context: Dict[str, Any],
        attempt_number: int
    ) -> Dict[str, Any]:
        """
        Deeply analyze why something failed
        Returns: Strategy to fix it
        """

        error_str = str(error).lower()

        # Pattern 1: Selector issues
        if 'selector' in error_str or 'element' in error_str:
            return await self._heal_selector_failure(context, error_str, attempt_number)

        # Pattern 2: Timing issues
        if 'timeout' in error_str or 'wait' in error_str:
            return await self._heal_timing_failure(context, error_str, attempt_number)

        # Pattern 3: Navigation issues
        if 'navigate' in error_str or 'load' in error_str:
            return await self._heal_navigation_failure(context, error_str, attempt_number)

        # Pattern 4: Data extraction issues
        if 'extract' in error_str or 'not found' in error_str:
            return await self._heal_extraction_failure(context, error_str, attempt_number)

        # Pattern 5: Unknown - try general strategies
        return await self._heal_unknown_failure(context, error_str, attempt_number)

    async def execute_strategy(self, strategy: Dict[str, Any],
                               playwright_client=None) -> Dict[str, Any]:
        """Execute a healing strategy and return result."""
        action = strategy.get('action', '')
        steps = strategy.get('steps', [])

        result = {
            'success': False,
            'action': action,
            'steps_executed': [],
            'error': None
        }

        try:
            for step in steps:
                step_type = step.get('type', '')

                if step_type == 'wait':
                    await asyncio.sleep(step.get('duration', 1))
                    result['steps_executed'].append(f"waited {step.get('duration')}s")

                elif step_type == 'screenshot' and playwright_client:
                    await playwright_client.screenshot()
                    result['steps_executed'].append("took screenshot")

                elif step_type == 'retry_selector' and playwright_client:
                    # Try alternative selectors
                    selectors = step.get('selectors', [])
                    for sel in selectors:
                        try:
                            element = await playwright_client.page.query_selector(sel)
                            if element:
                                result['found_selector'] = sel
                                result['steps_executed'].append(f"found: {sel}")
                                break
                        except:
                            continue

                elif step_type == 'refresh' and playwright_client:
                    await playwright_client.page.reload()
                    result['steps_executed'].append("refreshed page")

                elif step_type == 'javascript' and playwright_client:
                    script = step.get('script', '')
                    if script and not any(danger in script for danger in ['eval(', 'Function(']):
                        js_result = await playwright_client.page.evaluate(script)
                        result['steps_executed'].append(f"ran script")
                        result['js_result'] = js_result

            result['success'] = True

            # Record success for learning
            if hasattr(self, 'record_success'):
                self.record_success({'action': action}, strategy)

        except Exception as e:
            result['error'] = str(e)
            result['success'] = False

        return result

    async def _heal_selector_failure(
        self,
        context: Dict[str, Any],
        error: str,
        attempt: int
    ) -> Dict[str, Any]:
        """Heal selector-related failures"""

        selector = context.get('arguments', {}).get('selector', '')

        # Strategy progression based on attempt
        strategies = [
            # Attempt 1: Take screenshot to see what's there
            {
                'action': 'screenshot_first',
                'reason': 'Visual verification needed',
                'steps': [
                    {'function': 'playwright_screenshot'},
                    {'function': 'playwright_evaluate', 'arguments': {
                        'script': 'document.body.innerText.slice(0, 500)'
                    }}
                ]
            },
            # Attempt 2: Try more generic selector
            {
                'action': 'use_generic_selector',
                'reason': 'Original selector too specific',
                'modifications': {
                    'selector': self._generalize_selector(selector)
                }
            },
            # Attempt 3: Wait for page to load completely
            {
                'action': 'wait_for_load',
                'reason': 'Page may not be fully loaded',
                'steps': [
                    {'function': 'playwright_evaluate', 'arguments': {
                        'script': 'document.readyState'
                    }},
                    {'wait': 2000},  # Wait 2 seconds
                    # Then try original action
                ]
            },
            # Attempt 4: Search entire page for similar elements
            {
                'action': 'scan_page',
                'reason': 'Find all possible matches',
                'steps': [
                    {'function': 'playwright_evaluate', 'arguments': {
                        'script': f'''
                            (() => {{
                                const selector = {json.dumps(selector)};
                                try {{
                                    return Array.from(document.querySelectorAll('*'))
                                        .filter(el => {{
                                            try {{
                                                return el.matches(selector);
                                            }} catch(e) {{
                                                return false;
                                            }}
                                        }})
                                        .map(el => ({{
                                            tag: el.tagName,
                                            class: el.className,
                                            id: el.id,
                                            text: el.textContent.slice(0, 50)
                                        }}));
                                }} catch(e) {{
                                    return [];
                                }}
                            }})()
                        '''
                    }}
                ]
            }
        ]

        if attempt <= len(strategies):
            return strategies[attempt - 1]
        else:
            # Exhausted strategies - report detailed failure
            return {
                'action': 'detailed_report',
                'reason': 'All selector strategies exhausted',
                'report': await self._generate_failure_report(context, error)
            }

    async def _heal_timing_failure(
        self,
        context: Dict[str, Any],
        error: str,
        attempt: int
    ) -> Dict[str, Any]:
        """Heal timing-related failures"""

        # Exponential backoff with intelligent waits
        wait_strategies = [
            {'wait': 5000, 'reason': 'Standard wait'},
            {'wait': 10000, 'reason': 'Longer wait for slow loads'},
            {
                'action': 'wait_for_network_idle',
                'reason': 'Wait for all network requests',
                'steps': [
                    {'function': 'playwright_evaluate', 'arguments': {
                        'script': '''
                            new Promise(resolve => {
                                let timeout;
                                const check = () => {
                                    if (performance.getEntriesByType('resource')
                                        .filter(r => r.responseEnd === 0).length === 0) {
                                        resolve('ready');
                                    } else {
                                        timeout = setTimeout(check, 100);
                                    }
                                };
                                check();
                                setTimeout(() => resolve('timeout'), 30000);
                            })
                        '''
                    }}
                ]
            }
        ]

        if attempt <= len(wait_strategies):
            return wait_strategies[attempt - 1]

        return {'action': 'timeout_exceeded', 'reason': 'Page load timeout'}

    async def _heal_navigation_failure(
        self,
        context: Dict[str, Any],
        error: str,
        attempt: int
    ) -> Dict[str, Any]:
        """Heal navigation failures"""

        url = context.get('arguments', {}).get('url', '')

        strategies = [
            # Try https if http
            {
                'action': 'force_https',
                'modifications': {
                    'url': url.replace('http://', 'https://')
                }
            },
            # Add www if missing
            {
                'action': 'add_www',
                'modifications': {
                    'url': url.replace('https://', 'https://www.')
                }
            },
            # Remove www if present
            {
                'action': 'remove_www',
                'modifications': {
                    'url': url.replace('://www.', '://')
                }
            },
            # Try base domain only
            {
                'action': 'base_domain',
                'reason': 'Try homepage instead of specific path',
                'modifications': {
                    'url': '/'.join(url.split('/')[:3])  # Keep only protocol + domain
                }
            }
        ]

        if attempt <= len(strategies):
            return strategies[attempt - 1]

        return {'action': 'navigation_impossible', 'reason': 'URL unreachable'}

    async def _heal_extraction_failure(
        self,
        context: Dict[str, Any],
        error: str,
        attempt: int
    ) -> Dict[str, Any]:
        """Heal data extraction failures"""

        strategies = [
            # Take screenshot to see actual page
            {
                'action': 'visual_check',
                'steps': [
                    {'function': 'playwright_screenshot'},
                    {'function': 'playwright_evaluate', 'arguments': {
                        'script': 'document.documentElement.outerHTML.length'
                    }}
                ]
            },
            # Extract all text and search for patterns
            {
                'action': 'full_text_search',
                'steps': [
                    {'function': 'playwright_evaluate', 'arguments': {
                        'script': 'document.body.innerText'
                    }}
                ]
            },
            # Try alternative extraction methods
            {
                'action': 'alternative_extraction',
                'steps': [
                    {'function': 'playwright_evaluate', 'arguments': {
                        'script': '''
                            (() => {
                                const data = {
                                    title: document.title,
                                    headings: Array.from(document.querySelectorAll('h1,h2,h3'))
                                        .map(h => h.textContent.trim()),
                                    links: Array.from(document.querySelectorAll('a'))
                                        .slice(0, 10)
                                        .map(a => ({text: a.textContent.trim(), href: a.href})),
                                    forms: document.querySelectorAll('form').length,
                                    buttons: document.querySelectorAll('button').length
                                };
                                return JSON.stringify(data);
                            })()
                        '''
                    }}
                ]
            }
        ]

        if attempt <= len(strategies):
            return strategies[attempt - 1]

        return {'action': 'extraction_failed', 'reason': 'Data not found on page'}

    async def _heal_unknown_failure(
        self,
        context: Dict[str, Any],
        error: str,
        attempt: int
    ) -> Dict[str, Any]:
        """Generic healing for unknown errors"""

        return {
            'action': 'debug_mode',
            'steps': [
                {'function': 'playwright_screenshot'},
                {'function': 'playwright_evaluate', 'arguments': {
                    'script': '''
                        ({
                            url: window.location.href,
                            title: document.title,
                            readyState: document.readyState,
                            elements: document.querySelectorAll('*').length,
                            errors: window.console.errors || []
                        })
                    '''
                }}
            ],
            'reason': 'Collecting diagnostic information'
        }

    def _init_db(self):
        """Initialize SQLite database for persistence."""
        try:
            self.HEALING_DB.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.HEALING_DB)

            # Strategy stats table
            conn.execute('''CREATE TABLE IF NOT EXISTS strategy_stats
                (key TEXT PRIMARY KEY,
                 successes INTEGER DEFAULT 0,
                 failures INTEGER DEFAULT 0,
                 total INTEGER DEFAULT 0,
                 last_used TEXT)''')

            # Error patterns table
            conn.execute('''CREATE TABLE IF NOT EXISTS error_patterns
                (id INTEGER PRIMARY KEY AUTOINCREMENT,
                 pattern TEXT,
                 error_signature TEXT,
                 solution TEXT,
                 success_rate REAL,
                 created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')

            conn.commit()
            conn.close()
            logger.debug(f"[SELF-HEALING] Database initialized at {self.HEALING_DB}")
        except Exception as e:
            logger.error(f"[SELF-HEALING] Failed to initialize database: {e}")

    def save_to_db(self):
        """Persist learning to database."""
        try:
            conn = sqlite3.connect(self.HEALING_DB)

            # Save strategy stats
            for key, stats in self.strategy_stats.items():
                conn.execute('''INSERT OR REPLACE INTO strategy_stats
                    (key, successes, failures, total, last_used)
                    VALUES (?, ?, ?, ?, ?)''',
                    (key, stats['successes'], stats['failures'], stats['total'], datetime.now().isoformat()))

            conn.commit()
            conn.close()
            logger.debug(f"[SELF-HEALING] Saved {len(self.strategy_stats)} strategies to database")
        except Exception as e:
            logger.error(f"[SELF-HEALING] Failed to save to database: {e}")

    def load_from_db(self):
        """Load learning from database."""
        try:
            conn = sqlite3.connect(self.HEALING_DB)
            cursor = conn.execute('SELECT key, successes, failures, total FROM strategy_stats')

            count = 0
            for row in cursor:
                key, successes, failures, total = row
                self.strategy_stats[key] = {
                    'successes': successes,
                    'failures': failures,
                    'total': total
                }
                count += 1

            conn.close()
            logger.debug(f"[SELF-HEALING] Loaded {count} strategies from database")
        except Exception as e:
            logger.error(f"[SELF-HEALING] Failed to load from database: {e}")

    def cluster_similar_errors(self, error: str) -> str:
        """Group similar errors into patterns using regex clustering."""
        # Normalize error messages into patterns
        patterns = {
            'selector_not_found': r'(Element|Selector|Node).*not found',
            'timeout': r'(Timeout|timed out|exceeded)',
            'navigation': r'(Navigation|net::ERR_|Failed to navigate)',
            'stale_element': r'(stale|detached|removed)',
            'network_error': r'(ERR_CONNECTION|ERR_NAME_NOT_RESOLVED|Failed to fetch)',
            'javascript_error': r'(ReferenceError|TypeError|SyntaxError)',
            'permission_denied': r'(Permission denied|Access denied|Forbidden)',
            'rate_limit': r'(rate limit|too many requests|429)',
        }

        for pattern_name, regex in patterns.items():
            if re.search(regex, error, re.IGNORECASE):
                return pattern_name

        return 'unknown'

    def record_outcome(self, context: Dict, strategy: Dict, success: bool):
        """Track actual success/failure for each strategy."""
        error_type = self.cluster_similar_errors(context.get('error', ''))
        action = strategy.get('action', 'unknown')
        key = f"{error_type}_{action}"

        if key not in self.strategy_stats:
            self.strategy_stats[key] = {'successes': 0, 'failures': 0, 'total': 0}

        self.strategy_stats[key]['total'] += 1
        if success:
            self.strategy_stats[key]['successes'] += 1
        else:
            self.strategy_stats[key]['failures'] += 1

        # Persist to database after every 10 outcomes
        if self.strategy_stats[key]['total'] % 10 == 0:
            self.save_to_db()

        logger.debug(f"[SELF-HEALING] Recorded {key}: {self.strategy_stats[key]}")

    def get_success_rate(self, context: Dict, strategy: Dict) -> float:
        """Calculate true success rate from historical data."""
        error_type = self.cluster_similar_errors(context.get('error', ''))
        action = strategy.get('action', 'unknown')
        key = f"{error_type}_{action}"

        stats = self.strategy_stats.get(key, {'successes': 0, 'total': 0})

        # Return default when insufficient data (< 3 attempts)
        if stats['total'] < 3:
            return 0.5  # Neutral default

        return stats['successes'] / stats['total']

    def _generalize_selector(self, selector: str) -> str:
        """Make a selector more generic"""

        # Remove :nth-child
        selector = selector.split(':nth-child')[0]

        # Remove specific IDs in favor of classes
        if '#' in selector and '.' in selector:
            # Prefer class over ID
            selector = selector.split('#')[0]

        # Remove attribute values, keep attribute names
        selector = re.sub(r'=("[^"]*"|\'[^\']*\')', '', selector)

        return selector

    async def _generate_failure_report(
        self,
        context: Dict[str, Any],
        error: str
    ) -> Dict[str, Any]:
        """Generate detailed failure analysis"""

        return {
            'error': error,
            'context': context,
            'suggestions': [
                'Selector may not exist on this page',
                'Page structure may have changed',
                'JavaScript may not have loaded yet',
                'Element may be in an iframe'
            ],
            'next_steps': [
                'Take screenshot to verify page state',
                'Check browser console for errors',
                'Verify URL is correct',
                'Try manual inspection'
            ]
        }

    def record_failure(self, error: str, context: Dict[str, Any]):
        """Record a failure for learning and pattern detection."""
        # Extract key information
        function = context.get('function', 'unknown')
        error_type = self.cluster_similar_errors(error)
        pattern_key = f"{function}_{error_type}"

        # Track failure patterns
        if pattern_key not in self.failure_patterns:
            self.failure_patterns[pattern_key] = FailurePattern(
                error_type=error_type,
                context=json.dumps(context),
                failed_approach={'error': error, **context},
                successful_approach=None,
                success_rate=0.0,
                occurrences=1,
                last_seen=datetime.now()
            )
        else:
            pattern = self.failure_patterns[pattern_key]
            pattern.occurrences += 1
            pattern.last_seen = datetime.now()
            # Update success rate (decrease with each failure if no successes)
            if pattern.successful_approach is None:
                pattern.success_rate = 0.0

        # Use new tracking system
        context_with_error = {**context, 'error': error}
        strategy = {'action': 'original_attempt'}
        self.record_outcome(context_with_error, strategy, success=False)

        logger.debug(f"[SELF-HEALING] Recorded failure: {pattern_key} ({self.failure_patterns[pattern_key].occurrences} times)")

    def record_success(self, context: Dict[str, Any], strategy: Dict[str, Any]):
        """Record successful strategy for future use"""

        error_type = self.cluster_similar_errors(context.get('error', ''))
        pattern_key = f"{context.get('function')}_{error_type}"

        if pattern_key not in self.failure_patterns:
            self.failure_patterns[pattern_key] = FailurePattern(
                error_type=error_type,
                context=json.dumps(context),
                failed_approach=context.get('original_attempt', {}),
                successful_approach=strategy,
                success_rate=1.0,
                occurrences=1,
                last_seen=datetime.now()
            )
        else:
            pattern = self.failure_patterns[pattern_key]
            pattern.occurrences += 1
            pattern.successful_approach = strategy
            pattern.success_rate = (pattern.success_rate * (pattern.occurrences - 1) + 1.0) / pattern.occurrences
            pattern.last_seen = datetime.now()

        # Use new tracking system
        self.record_outcome(context, strategy, success=True)

    def get_best_strategy(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Get best known strategy for this type of task using REAL success rates"""

        # Find similar past successes using error clustering
        error_type = self.cluster_similar_errors(context.get('error', ''))

        # Find all strategies that worked for this error type
        candidates = []
        for key, stats in self.strategy_stats.items():
            if error_type in key and stats['total'] >= 3:  # Minimum 3 attempts
                success_rate = stats['successes'] / stats['total']
                if success_rate > 0.7:  # 70% threshold
                    action = key.split('_', 1)[1] if '_' in key else key
                    candidates.append({
                        'key': key,
                        'action': action,
                        'success_rate': success_rate,
                        'total_attempts': stats['total']
                    })

        if not candidates:
            return None

        # Sort by success rate, then by total attempts (more data = better)
        candidates.sort(key=lambda x: (x['success_rate'], x['total_attempts']), reverse=True)

        # Return best strategy
        best = candidates[0]
        logger.debug(f"[SELF-HEALING] Best strategy for {error_type}: {best['action']} ({best['success_rate']:.1%} success over {best['total_attempts']} attempts)")

        return {
            'action': best['action'],
            'success_rate': best['success_rate'],
            'confidence': min(best['success_rate'], best['total_attempts'] / 10)  # Confidence grows with more data
        }

    def get_learning_stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics about learned strategies."""
        total_strategies = len(self.strategy_stats)
        total_attempts = sum(s['total'] for s in self.strategy_stats.values())
        total_successes = sum(s['successes'] for s in self.strategy_stats.values())
        overall_success_rate = total_successes / total_attempts if total_attempts > 0 else 0

        # Group by error type
        error_type_stats = {}
        for key, stats in self.strategy_stats.items():
            error_type = key.split('_')[0] if '_' in key else 'unknown'
            if error_type not in error_type_stats:
                error_type_stats[error_type] = {'attempts': 0, 'successes': 0, 'strategies': 0}

            error_type_stats[error_type]['attempts'] += stats['total']
            error_type_stats[error_type]['successes'] += stats['successes']
            error_type_stats[error_type]['strategies'] += 1

        # Calculate success rate per error type
        for error_type, data in error_type_stats.items():
            data['success_rate'] = data['successes'] / data['attempts'] if data['attempts'] > 0 else 0

        # Find best performing strategies
        top_strategies = sorted(
            [(k, v) for k, v in self.strategy_stats.items() if v['total'] >= 3],
            key=lambda x: x[1]['successes'] / x[1]['total'],
            reverse=True
        )[:10]

        return {
            'total_strategies': total_strategies,
            'total_attempts': total_attempts,
            'total_successes': total_successes,
            'overall_success_rate': overall_success_rate,
            'error_type_breakdown': error_type_stats,
            'top_strategies': [
                {
                    'key': k,
                    'success_rate': v['successes'] / v['total'],
                    'attempts': v['total']
                }
                for k, v in top_strategies
            ]
        }

    def _get_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return parsed.netloc or parsed.path.split('/')[0]
        except:
            return "unknown"

    def _load_profiles(self):
        """Load site profiles from disk."""
        if self._profiles_path.exists():
            try:
                data = json.loads(self._profiles_path.read_text())
                for domain, profile_data in data.items():
                    self._site_profiles[domain] = SiteProfile(**profile_data)
                logger.info(f"Loaded {len(self._site_profiles)} site profiles")
            except Exception as e:
                logger.warning(f"Error loading site profiles: {e}")

    def _save_profiles(self):
        """Save site profiles to disk."""
        try:
            self._profiles_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                domain: asdict(profile)
                for domain, profile in self._site_profiles.items()
            }
            from .atomic_file import atomic_write_json
            atomic_write_json(self._profiles_path, data)
        except Exception as e:
            logger.warning(f"Error saving site profiles: {e}")

    async def validate_selector(self, selector: str, page, cache: bool = True) -> bool:
        """Proactively validate a selector exists on the page."""
        domain = self._get_domain(page.url)
        cache_key = f"{domain}:{selector}"

        # Check cache first
        if cache and cache_key in self._selector_cache:
            timestamp = self._cache_timestamps.get(cache_key, 0)
            if time.time() - timestamp < self._cache_ttl:
                return self._selector_cache[cache_key]

        # Validate on page
        try:
            element = await page.query_selector(selector)
            is_valid = element is not None

            # Update cache
            self._selector_cache[cache_key] = is_valid
            self._cache_timestamps[cache_key] = time.time()

            if not is_valid:
                logger.debug(f"Selector not found: {selector}")

            return is_valid
        except Exception as e:
            logger.warning(f"Error validating selector {selector}: {e}")
            return False

    async def get_alternative_selectors(self, original: str, page) -> List[str]:
        """Generate alternative selectors for an element."""
        alternatives = []

        # Try common variations
        if original.startswith("#"):
            # ID selector - try data attributes
            base = original[1:]
            alternatives.extend([
                f'[data-testid="{base}"]',
                f'[data-id="{base}"]',
                f'[aria-label*="{base}"]'
            ])
        elif original.startswith("."):
            # Class selector - try text content
            alternatives.extend([
                f'text="{original[1:]}"',
                f'[class*="{original[1:]}"]'
            ])

        # Extract text and try text-based selector
        try:
            element = await page.query_selector(original)
            if element:
                text = await element.text_content()
                if text and len(text) < 50:
                    alternatives.append(f'text="{text.strip()}"')
        except:
            pass

        # Validate alternatives
        valid = []
        for alt in alternatives:
            if await self.validate_selector(alt, page, cache=False):
                valid.append(alt)
                logger.info(f"Found alternative selector: {alt}")

        return valid

    def get_site_profile(self, domain: str) -> SiteProfile:
        """Get or create site profile."""
        if domain not in self._site_profiles:
            self._site_profiles[domain] = SiteProfile(domain=domain)
        return self._site_profiles[domain]

    def learn_from_success(self, domain: str, selector: str, purpose: str, strategy: str):
        """Learn from successful interaction."""
        profile = self.get_site_profile(domain)
        profile.selector_patterns[purpose] = selector
        profile.total_attempts += 1
        profile.success_rate = (
            (profile.success_rate * (profile.total_attempts - 1) + 1)
            / profile.total_attempts
        )
        if strategy not in profile.preferred_strategies:
            profile.preferred_strategies.append(strategy)
        profile.last_updated = time.time()
        self._save_profiles()
        logger.info(f"Learned success pattern for {domain}: {purpose} -> {selector}")

    def learn_from_failure(self, domain: str, error: str, strategy: str):
        """Learn from failed interaction."""
        profile = self.get_site_profile(domain)
        profile.total_attempts += 1
        profile.success_rate = (
            (profile.success_rate * (profile.total_attempts - 1))
            / profile.total_attempts
        )
        if error not in profile.common_errors:
            profile.common_errors.append(error)
            profile.common_errors = profile.common_errors[-10:]  # Keep last 10
        profile.last_updated = time.time()
        self._save_profiles()
        logger.debug(f"Learned failure pattern for {domain}: {error}")

    async def detect_layout_change(self, page) -> Tuple[bool, float]:
        """Detect if page layout has significantly changed."""
        url = page.url

        # Generate fingerprint of current page structure
        current_fingerprint = await self._generate_page_fingerprint(page)

        # Compare with stored fingerprint
        stored = self._page_fingerprints.get(url)
        if not stored:
            self._page_fingerprints[url] = current_fingerprint
            return False, 1.0

        # Calculate similarity
        similarity = self._calculate_fingerprint_similarity(stored, current_fingerprint)

        # Update stored fingerprint
        self._page_fingerprints[url] = current_fingerprint

        # Significant change if < 70% similar
        is_changed = similarity < 0.7

        if is_changed:
            logger.warning(f"Layout change detected on {url}: {similarity:.2%} similarity")
            # Clear selector cache for this domain
            domain = self._get_domain(url)
            self._clear_domain_cache(domain)

        return is_changed, similarity

    async def _generate_page_fingerprint(self, page) -> str:
        """Generate a fingerprint of page structure."""
        try:
            structure = await page.evaluate("""
                () => {
                    const elements = document.querySelectorAll('*');
                    const structure = [];
                    elements.forEach(el => {
                        if (el.tagName) {
                            structure.push(el.tagName.toLowerCase());
                            if (el.id) structure.push('#' + el.id);
                            if (el.className) structure.push('.' + el.className.split(' ')[0]);
                        }
                    });
                    return structure.slice(0, 500).join(',');  // First 500 elements
                }
            """)
            return hashlib.md5(structure.encode()).hexdigest()
        except:
            return ""

    def _calculate_fingerprint_similarity(self, fp1: str, fp2: str) -> float:
        """Calculate similarity between fingerprints."""
        if fp1 == fp2:
            return 1.0
        if not fp1 or not fp2:
            return 0.0
        # Simple character-based similarity
        matches = sum(c1 == c2 for c1, c2 in zip(fp1, fp2))
        return matches / max(len(fp1), len(fp2))

    def _clear_domain_cache(self, domain: str):
        """Clear selector cache for a domain."""
        keys_to_remove = [key for key in self._selector_cache.keys() if key.startswith(f"{domain}:")]
        for key in keys_to_remove:
            del self._selector_cache[key]
            if key in self._cache_timestamps:
                del self._cache_timestamps[key]
        logger.info(f"Cleared selector cache for domain: {domain}")

    def get_learned_selector(self, domain: str, purpose: str) -> Optional[str]:
        """Get a learned selector for a specific purpose on a domain."""
        profile = self._site_profiles.get(domain)
        if profile:
            return profile.selector_patterns.get(purpose)
        return None

    def get_site_stats(self, domain: str) -> Dict[str, Any]:
        """Get statistics for a specific site."""
        profile = self._site_profiles.get(domain)
        if profile:
            return {
                'domain': profile.domain,
                'success_rate': profile.success_rate,
                'total_attempts': profile.total_attempts,
                'common_errors': profile.common_errors,
                'preferred_strategies': profile.preferred_strategies,
                'learned_selectors': len(profile.selector_patterns)
            }
        return {}


# Singleton
self_healing = SelfHealingSystem()
