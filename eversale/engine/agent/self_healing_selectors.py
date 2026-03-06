"""
DEPRECATED: This module is no longer needed with the a11y-first architecture.

Accessibility refs are stable and don't need healing. The a11y tree provides
stable references that don't break when page structure changes.

This module is kept for backward compatibility only. All functions are stubs
that return unchanged inputs or no-op results.

Migration guide:
- Old: Use self-healing selectors with CSS fallbacks
- New: Use accessibility tree with refs (via accessibility_element_finder.py)

The new approach:
1. Get accessibility snapshot
2. Match element by name/role (semantic, not structural)
3. Use stable ref (e.g., [ref=s1e5])
4. No healing needed - refs are stable across page changes

For details, see:
- /mnt/c/ev29/cli/engine/agent/accessibility_element_finder.py
- /mnt/c/ev29/cli/engine/agent/ACCESSIBILITY_ELEMENT_FINDER_README.md
"""

import warnings
from typing import Dict, Optional, Any


def heal_selector(selector: str, *args, **kwargs) -> str:
    """
    DEPRECATED: Returns selector unchanged. Use accessibility refs instead.

    Args:
        selector: CSS selector (unchanged)
        *args: Ignored
        **kwargs: Ignored

    Returns:
        Original selector unchanged
    """
    warnings.warn(
        "heal_selector is deprecated. Use accessibility refs instead. "
        "See accessibility_element_finder.py for the modern approach.",
        DeprecationWarning,
        stacklevel=2
    )
    return selector


class SelfHealingSelector:
    """
    DEPRECATED: Stub class for backward compatibility.

    All methods are no-ops. Use AccessibilityElementFinder instead.
    """

    def __init__(self, mcp_client, visual_finder=None):
        """Initialize stub instance."""
        warnings.warn(
            "SelfHealingSelector is deprecated. Use AccessibilityElementFinder instead.",
            DeprecationWarning,
            stacklevel=2
        )
        self.mcp = mcp_client
        self.visual_finder = visual_finder

    async def find_element(self, page, selector_hints: dict) -> Optional[str]:
        """DEPRECATED: Returns None. Use accessibility tree instead."""
        return None

    async def click(self, page, selector_hints: dict) -> bool:
        """DEPRECATED: Returns False. Use a11y_click instead."""
        return False

    async def fill(self, page, selector_hints: dict, value: str) -> bool:
        """DEPRECATED: Returns False. Use a11y_type instead."""
        return False

    async def get_text(self, page, selector_hints: dict) -> Optional[str]:
        """DEPRECATED: Returns None. Use a11y_snapshot instead."""
        return None

    def invalidate_cache(self, domain: Optional[str] = None):
        """DEPRECATED: No-op."""
        pass

    def get_stats(self) -> dict:
        """DEPRECATED: Returns empty stats."""
        return {'available': False, 'cached_pages': 0}


async def find_and_click(mcp_client, page, selector_hints: dict) -> bool:
    """
    DEPRECATED: Stub function for backward compatibility.

    Returns False. Use a11y_click with accessibility refs instead.
    """
    warnings.warn(
        "find_and_click is deprecated. Use a11y_click with accessibility refs.",
        DeprecationWarning,
        stacklevel=2
    )
    return False


async def find_and_fill(mcp_client, page, selector_hints: dict, value: str) -> bool:
    """
    DEPRECATED: Stub function for backward compatibility.

    Returns False. Use a11y_type with accessibility refs instead.
    """
    warnings.warn(
        "find_and_fill is deprecated. Use a11y_type with accessibility refs.",
        DeprecationWarning,
        stacklevel=2
    )
    return False


# Export deprecated symbols for backward compatibility
__all__ = [
    'heal_selector',
    'SelfHealingSelector',
    'find_and_click',
    'find_and_fill'
]
