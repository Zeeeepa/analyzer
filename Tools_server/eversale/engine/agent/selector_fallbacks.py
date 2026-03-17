"""
DEPRECATED: This module is no longer needed with the a11y-first architecture.

Selector fallbacks were needed when using CSS selectors that break on page changes.
With accessibility refs, elements are identified by semantic meaning (role + name),
not by page structure, so they don't break when the page changes.

This module is kept for backward compatibility only. All functions are stubs.

Migration guide:
- Old: Complex CSS selector fallback chains
- New: Accessibility-based element finding

The new approach:
1. Use a11y_snapshot to get stable element refs
2. Match elements by semantic meaning (name, role)
3. Use refs directly - no fallbacks needed
4. Refs survive page structure changes

For details, see:
- /mnt/c/ev29/cli/engine/agent/accessibility_element_finder.py
- /mnt/c/ev29/cli/engine/agent/ACCESSIBILITY_ELEMENT_FINDER_README.md
"""

import warnings
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class FallbackResult:
    """
    DEPRECATED: Stub for backward compatibility.

    With a11y refs, we don't need complex fallback results.
    """
    found: bool
    selector: Optional[str] = None
    method: str = "deprecated"
    confidence: float = 0.0
    coordinates: Optional[Tuple[int, int]] = None
    element: Optional[Any] = None
    alternatives: List[str] = field(default_factory=list)
    error: Optional[str] = "selector_fallbacks is deprecated - use accessibility refs"


class SelectorCache:
    """
    DEPRECATED: Stub for backward compatibility.

    Accessibility refs don't need caching - they're stable by design.
    """

    @staticmethod
    def load():
        """DEPRECATED: No-op."""
        pass

    @staticmethod
    def save():
        """DEPRECATED: No-op."""
        pass

    @staticmethod
    def get_domain(url: str) -> str:
        """DEPRECATED: Returns 'deprecated'."""
        return "deprecated"

    @staticmethod
    def make_key(element_type: str, description: str = "") -> str:
        """DEPRECATED: Returns 'deprecated'."""
        return "deprecated"

    @staticmethod
    def get(url: str, element_type: str, description: str = "") -> Optional[Dict]:
        """DEPRECATED: Returns None."""
        return None

    @staticmethod
    def set(url: str, element_type: str, description: str, selector: str, method: str = "unknown"):
        """DEPRECATED: No-op."""
        pass

    @staticmethod
    def invalidate(url: str, element_type: str, description: str):
        """DEPRECATED: No-op."""
        pass


class SelfHealingSelector:
    """
    DEPRECATED: Stub for backward compatibility.

    Use AccessibilityElementFinder instead.
    """

    def __init__(self, page):
        """Initialize stub."""
        warnings.warn(
            "SelfHealingSelector from selector_fallbacks is deprecated. "
            "Use AccessibilityElementFinder instead.",
            DeprecationWarning,
            stacklevel=2
        )
        self.page = page
        self.last_positions: Dict[str, Tuple[float, float]] = {}

    async def find_element(self, *args, **kwargs) -> Optional[Dict[str, Any]]:
        """DEPRECATED: Returns None."""
        return None

    async def find_and_click(self, *args, **kwargs) -> Dict[str, Any]:
        """DEPRECATED: Returns failure result."""
        return {'success': False, 'error': 'selector_fallbacks is deprecated - use a11y_click'}

    async def find_and_fill(self, *args, **kwargs) -> Dict[str, Any]:
        """DEPRECATED: Returns failure result."""
        return {'success': False, 'error': 'selector_fallbacks is deprecated - use a11y_type'}

    async def _try_selector(self, selector: str) -> Optional[Any]:
        """DEPRECATED: Returns None."""
        return None

    async def _search_by_text(self, text: str, element_type: str = "unknown") -> Optional[Dict[str, Any]]:
        """DEPRECATED: Returns None."""
        return None

    async def _generate_selector(self, element, tag: str) -> str:
        """DEPRECATED: Returns empty string."""
        return ""

    async def _find_by_coordinates(self, element_key: str) -> Optional[Dict[str, Any]]:
        """DEPRECATED: Returns None."""
        return None


class VisualFallback:
    """
    DEPRECATED: Stub for backward compatibility.

    Visual fallback is not needed with accessibility tree.
    """

    def __init__(self):
        """Initialize stub."""
        warnings.warn(
            "VisualFallback is deprecated. Use accessibility tree instead.",
            DeprecationWarning,
            stacklevel=2
        )
        self.has_vision = False
        self._grounding_engine = None

    async def find_element_by_description(self, page, description: str, screenshot: Optional[bytes] = None) -> Optional[Dict[str, Any]]:
        """DEPRECATED: Returns None."""
        return None

    async def click_by_description(self, page, description: str, screenshot: Optional[bytes] = None) -> Dict[str, Any]:
        """DEPRECATED: Returns failure result."""
        return {'success': False, 'error': 'VisualFallback is deprecated - use a11y tools'}

    async def find_element_visually(self, page, description: str, screenshot: Optional[bytes] = None) -> Optional[Tuple[float, float]]:
        """DEPRECATED: Returns None."""
        return None


def get_visual_fallback() -> VisualFallback:
    """DEPRECATED: Returns stub VisualFallback instance."""
    return VisualFallback()


def css_to_xpath(css_selector: str) -> Optional[str]:
    """DEPRECATED: Returns None. Use accessibility refs instead."""
    warnings.warn(
        "css_to_xpath is deprecated. Use accessibility refs instead.",
        DeprecationWarning,
        stacklevel=2
    )
    return None


def generate_selector_variants(original: str, context: Dict = None) -> List[str]:
    """DEPRECATED: Returns empty list. Use accessibility tree instead."""
    warnings.warn(
        "generate_selector_variants is deprecated. Use accessibility tree instead.",
        DeprecationWarning,
        stacklevel=2
    )
    return []


def generate_alternative_selectors(original: str, context: Dict = None) -> List[str]:
    """DEPRECATED: Returns empty list. Use accessibility tree instead."""
    return generate_selector_variants(original, context)


def calculate_text_similarity(text1: str, text2: str) -> float:
    """DEPRECATED: Returns 0.0. Use accessibility matching instead."""
    return 0.0


async def find_by_fuzzy_text(page, target_text: str, threshold: float = 0.8, element_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """DEPRECATED: Returns None. Use accessibility tree instead."""
    return None


async def explore_dom_for_element(page, hints: Dict[str, Any]) -> List[Dict[str, Any]]:
    """DEPRECATED: Returns empty list. Use accessibility tree instead."""
    return []


async def find_similar_elements(page, failed_selector: str) -> List[Dict[str, Any]]:
    """DEPRECATED: Returns empty list. Use accessibility tree instead."""
    return []


async def find_with_fallbacks(
    page,
    primary_selector: str = None,
    description: str = None,
    context: Dict[str, Any] = None,
    element_type: str = "unknown"
) -> FallbackResult:
    """
    DEPRECATED: Returns failure result. Use accessibility tree instead.
    """
    warnings.warn(
        "find_with_fallbacks is deprecated. Use accessibility tree with a11y tools instead.",
        DeprecationWarning,
        stacklevel=2
    )
    return FallbackResult(
        found=False,
        error="find_with_fallbacks is deprecated - use a11y_snapshot + a11y_click/type/etc"
    )


async def click_with_visual_fallback(page, selector: str = None, description: Optional[str] = None, context: Dict[str, Any] = None) -> Dict[str, Any]:
    """DEPRECATED: Returns failure result. Use a11y_click instead."""
    warnings.warn(
        "click_with_visual_fallback is deprecated. Use a11y_click instead.",
        DeprecationWarning,
        stacklevel=2
    )
    return {'success': False, 'error': 'click_with_visual_fallback is deprecated - use a11y_click'}


def get_fallback_metrics() -> Dict[str, Any]:
    """DEPRECATED: Returns empty metrics."""
    return {
        'available': False,
        'message': 'Fallback metrics deprecated - use accessibility tree instead'
    }


def reset_fallback_metrics():
    """DEPRECATED: No-op."""
    pass


# Export deprecated symbols for backward compatibility
__all__ = [
    'SelfHealingSelector',
    'SelectorCache',
    'VisualFallback',
    'FallbackResult',
    'find_with_fallbacks',
    'get_visual_fallback',
    'click_with_visual_fallback',
    'generate_selector_variants',
    'generate_alternative_selectors',
    'css_to_xpath',
    'find_by_fuzzy_text',
    'explore_dom_for_element',
    'find_similar_elements',
    'calculate_text_similarity',
    'get_fallback_metrics',
    'reset_fallback_metrics',
]
