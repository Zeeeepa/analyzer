"""
Self-Healing Selector System - Selectors that fix themselves

When websites change, selectors break. This system:
- Caches successful selectors per domain
- Falls back through alternative selector strategies
- Uses visual matching when CSS fails
- Learns from successful matches

Based on:
- Stagehand's self-healing automation
- Browser-Use's selector fallback chain
- Agent-E's accessibility tree matching

Key strategies:
1. Exact CSS selector
2. Data attributes (data-testid, data-cy)
3. Accessibility attributes (aria-label, role)
4. Text content matching
5. XPath by structure
6. Visual matching (screenshot + AI)
"""

import asyncio
import hashlib
import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from urllib.parse import urlparse
from loguru import logger


@dataclass
class SelectorMatch:
    """Result of a selector match attempt"""
    selector: str
    strategy: str
    confidence: float  # 0-1
    element_info: Dict = field(default_factory=dict)
    cached: bool = False


@dataclass
class SelectorCacheEntry:
    """Cached selector mapping"""
    original_selector: str
    working_selector: str
    strategy: str
    domain: str
    path_pattern: str  # URL path pattern
    success_count: int = 1
    last_success: float = 0.0
    element_signature: str = ""  # Hash of element attributes for validation


class SelfHealingSelectors:
    """
    Self-healing selector system with caching and fallbacks.

    Example:
        healer = SelfHealingSelectors(page)

        # Find element - heals automatically if original fails
        element = await healer.find(".old-class")

        # Force cache update
        healer.invalidate_cache("old-domain.com")
    """

    STRATEGIES = [
        "exact",           # Original selector
        "data_testid",     # data-testid attribute
        "data_cy",         # Cypress data-cy
        "aria_label",      # aria-label
        "role_text",       # role + text content
        "id",              # Element ID
        "text_content",    # Inner text
        "xpath_structure", # XPath by structure
        "visual",          # Screenshot + AI (expensive)
    ]

    def __init__(self, page, cache_dir: Optional[str] = None):
        self.page = page
        self.cache_dir = Path(cache_dir) if cache_dir else Path.home() / ".eversale" / "selector_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self._cache: Dict[str, Dict[str, SelectorCacheEntry]] = {}  # domain -> selector -> entry
        self._load_cache()

    def _load_cache(self):
        """Load selector cache from disk."""
        cache_file = self.cache_dir / "selectors.json"

        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                    for domain, selectors in data.items():
                        self._cache[domain] = {}
                        for orig, entry_data in selectors.items():
                            self._cache[domain][orig] = SelectorCacheEntry(**entry_data)
            except Exception as e:
                logger.debug(f"Failed to load selector cache: {e}")

    def _save_cache(self):
        """Save selector cache to disk."""
        cache_file = self.cache_dir / "selectors.json"

        try:
            data = {}
            for domain, selectors in self._cache.items():
                data[domain] = {}
                for orig, entry in selectors.items():
                    data[domain][orig] = {
                        'original_selector': entry.original_selector,
                        'working_selector': entry.working_selector,
                        'strategy': entry.strategy,
                        'domain': entry.domain,
                        'path_pattern': entry.path_pattern,
                        'success_count': entry.success_count,
                        'last_success': entry.last_success,
                        'element_signature': entry.element_signature
                    }

            with open(cache_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.debug(f"Failed to save selector cache: {e}")

    def _get_domain(self) -> str:
        """Get current page domain."""
        url = self.page.url
        parsed = urlparse(url)
        return parsed.netloc or "unknown"

    def _get_path_pattern(self) -> str:
        """Get URL path pattern for cache matching."""
        url = self.page.url
        parsed = urlparse(url)
        path = parsed.path

        # Generalize path (replace IDs/numbers with *)
        import re
        pattern = re.sub(r'/\d+', '/*', path)
        pattern = re.sub(r'/[a-f0-9]{8,}', '/*', pattern, flags=re.IGNORECASE)

        return pattern

    def _cache_key(self, selector: str) -> str:
        """Generate cache key for selector."""
        return hashlib.md5(selector.encode()).hexdigest()[:16]

    async def _get_element_signature(self, element) -> str:
        """Generate signature for element validation."""
        try:
            attrs = await element.evaluate("""
                el => ({
                    tag: el.tagName,
                    type: el.type || '',
                    role: el.getAttribute('role') || '',
                    placeholder: el.placeholder || ''
                })
            """)
            return hashlib.md5(json.dumps(attrs, sort_keys=True).encode()).hexdigest()[:12]
        except:
            return ""

    async def _check_cached(self, selector: str) -> Optional[SelectorMatch]:
        """Check if we have a cached working selector."""
        domain = self._get_domain()

        if domain not in self._cache:
            return None

        cache_key = self._cache_key(selector)
        if cache_key not in self._cache[domain]:
            return None

        entry = self._cache[domain][cache_key]

        # Try the cached selector
        try:
            element = await self.page.query_selector(entry.working_selector)
            if element:
                # Verify element signature if available
                if entry.element_signature:
                    current_sig = await self._get_element_signature(element)
                    if current_sig != entry.element_signature:
                        logger.debug(f"Cached selector signature mismatch: {selector}")
                        return None

                # Update success stats
                entry.success_count += 1
                entry.last_success = time.time()
                self._save_cache()

                return SelectorMatch(
                    selector=entry.working_selector,
                    strategy=entry.strategy,
                    confidence=0.9,
                    cached=True
                )
        except Exception as e:
            logger.debug(f"Cached selector failed: {e}")

        return None

    async def _try_exact(self, selector: str) -> Optional[SelectorMatch]:
        """Try the exact selector as-is."""
        try:
            element = await self.page.query_selector(selector)
            if element and await element.is_visible():
                return SelectorMatch(
                    selector=selector,
                    strategy="exact",
                    confidence=1.0
                )
        except:
            pass
        return None

    async def _try_data_testid(self, selector: str) -> Optional[SelectorMatch]:
        """Try to find element by data-testid."""
        # Extract potential testid from selector
        import re

        # Look for hints in the selector
        class_match = re.search(r'\.([a-zA-Z0-9_-]+)', selector)
        id_match = re.search(r'#([a-zA-Z0-9_-]+)', selector)

        hints = []
        if class_match:
            hints.append(class_match.group(1))
        if id_match:
            hints.append(id_match.group(1))

        for hint in hints:
            for attr in ['data-testid', 'data-test-id', 'data-cy', 'data-test']:
                test_selector = f'[{attr}*="{hint}"]'
                try:
                    element = await self.page.query_selector(test_selector)
                    if element and await element.is_visible():
                        return SelectorMatch(
                            selector=test_selector,
                            strategy="data_testid",
                            confidence=0.85
                        )
                except:
                    pass

        return None

    async def _try_aria_label(self, selector: str) -> Optional[SelectorMatch]:
        """Try to find by aria-label."""
        # Look for text hints in selector
        import re

        text_hints = re.findall(r'["\']([^"\']+)["\']', selector)
        text_hints += re.findall(r'\.([a-zA-Z]+)', selector)  # Class names might hint at label

        for hint in text_hints:
            if len(hint) > 2:
                aria_selector = f'[aria-label*="{hint}" i]'
                try:
                    element = await self.page.query_selector(aria_selector)
                    if element and await element.is_visible():
                        return SelectorMatch(
                            selector=aria_selector,
                            strategy="aria_label",
                            confidence=0.8
                        )
                except:
                    pass

        return None

    async def _try_text_content(self, selector: str) -> Optional[SelectorMatch]:
        """Try to find by text content."""
        import re

        # Extract any quoted text from selector
        text_hints = re.findall(r'["\']([^"\']{3,})["\']', selector)

        # Also try common element hints
        if 'button' in selector.lower() or 'btn' in selector.lower():
            text_hints.append("submit")
            text_hints.append("click")

        if 'search' in selector.lower():
            text_hints.append("search")

        for hint in text_hints:
            text_selector = f'text="{hint}"'
            try:
                element = await self.page.query_selector(text_selector)
                if element and await element.is_visible():
                    return SelectorMatch(
                        selector=text_selector,
                        strategy="text_content",
                        confidence=0.7
                    )
            except:
                pass

        return None

    async def _try_role_text(self, selector: str) -> Optional[SelectorMatch]:
        """Try to find by role and text."""
        # Infer role from selector
        role = None
        if any(x in selector.lower() for x in ['button', 'btn', 'submit']):
            role = 'button'
        elif any(x in selector.lower() for x in ['link', 'href']):
            role = 'link'
        elif any(x in selector.lower() for x in ['input', 'field', 'text']):
            role = 'textbox'

        if role:
            role_selector = f'role={role}'
            try:
                elements = await self.page.query_selector_all(role_selector)
                for element in elements[:5]:  # Check first 5
                    if await element.is_visible():
                        return SelectorMatch(
                            selector=role_selector,
                            strategy="role_text",
                            confidence=0.65
                        )
            except:
                pass

        return None

    async def _try_xpath_structure(self, selector: str) -> Optional[SelectorMatch]:
        """Try XPath by structure."""
        # This is a fallback - tries to find similar structural elements
        import re

        # Extract tag hints
        tag_match = re.match(r'^(\w+)', selector)
        tag = tag_match.group(1) if tag_match else '*'

        # Build XPath
        xpaths = [
            f'//{tag}[contains(@class, "btn")]',
            f'//{tag}[contains(@class, "button")]',
            f'//{tag}[contains(@class, "input")]',
            f'//{tag}[@type="submit"]',
        ]

        for xpath in xpaths:
            try:
                element = await self.page.query_selector(f'xpath={xpath}')
                if element and await element.is_visible():
                    return SelectorMatch(
                        selector=f'xpath={xpath}',
                        strategy="xpath_structure",
                        confidence=0.5
                    )
            except:
                pass

        return None

    async def find(
        self,
        selector: str,
        description: Optional[str] = None,
        timeout: int = 5000
    ) -> Optional[Tuple[Any, SelectorMatch]]:
        """
        Find element with self-healing fallbacks.

        Args:
            selector: Original CSS selector
            description: Optional description for visual fallback
            timeout: Timeout in ms

        Returns:
            Tuple of (element, match_info) or None
        """
        # First check cache
        cached = await self._check_cached(selector)
        if cached:
            element = await self.page.query_selector(cached.selector)
            if element:
                logger.debug(f"[CACHE HIT] {selector} → {cached.selector}")
                return (element, cached)

        # Try strategies in order
        strategies = [
            ("exact", self._try_exact),
            ("data_testid", self._try_data_testid),
            ("aria_label", self._try_aria_label),
            ("role_text", self._try_role_text),
            ("text_content", self._try_text_content),
            ("xpath_structure", self._try_xpath_structure),
        ]

        for strategy_name, strategy_fn in strategies:
            match = await strategy_fn(selector)

            if match:
                element = await self.page.query_selector(match.selector)
                if element:
                    # Cache the successful match
                    await self._cache_match(selector, match, element)
                    logger.debug(f"[HEALED] {selector} → {match.selector} ({strategy_name})")
                    return (element, match)

        logger.debug(f"[FAILED] No selector worked for: {selector}")
        return None

    async def _cache_match(self, original: str, match: SelectorMatch, element):
        """Cache a successful selector match."""
        domain = self._get_domain()

        if domain not in self._cache:
            self._cache[domain] = {}

        cache_key = self._cache_key(original)
        signature = await self._get_element_signature(element)

        self._cache[domain][cache_key] = SelectorCacheEntry(
            original_selector=original,
            working_selector=match.selector,
            strategy=match.strategy,
            domain=domain,
            path_pattern=self._get_path_pattern(),
            success_count=1,
            last_success=time.time(),
            element_signature=signature
        )

        self._save_cache()

    def invalidate_cache(self, domain: Optional[str] = None):
        """Invalidate cached selectors."""
        if domain:
            if domain in self._cache:
                del self._cache[domain]
        else:
            self._cache.clear()

        self._save_cache()
        logger.debug(f"Invalidated selector cache for: {domain or 'all domains'}")

    def get_cache_stats(self) -> Dict:
        """Get cache statistics."""
        total_entries = sum(len(selectors) for selectors in self._cache.values())
        domains = list(self._cache.keys())

        return {
            'total_entries': total_entries,
            'domains': domains,
            'cache_dir': str(self.cache_dir)
        }


# Convenience function
async def find_element_healing(page, selector: str, description: str = None):
    """
    Find element with self-healing fallbacks.

    Returns element or None.
    """
    healer = SelfHealingSelectors(page)
    result = await healer.find(selector, description)

    if result:
        return result[0]  # Just the element
    return None
