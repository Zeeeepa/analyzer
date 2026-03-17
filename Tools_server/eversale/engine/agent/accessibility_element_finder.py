"""
Accessibility-First Element Finder - Playwright MCP Reliability Pattern

This module achieves element-finding reliability by using accessibility tree refs
instead of fragile CSS selectors. This is the core pattern behind Playwright MCP's
success at reliable element interaction.

WHY ACCESSIBILITY REFS WIN:
1. Stable - Based on semantic structure, not DOM implementation
2. Fast - No complex CSS queries
3. Human-aligned - Matches how users describe elements
4. Vision-compatible - Works with screenshots + AI descriptions

KEY INSIGHT FROM PLAYWRIGHT MCP:
Instead of: page.click('button.btn-primary.mt-3[data-test="submit"]')
Use: page.click('[ref=s1e5]') where s1e5 is from accessibility snapshot

The accessibility tree is:
- Faster to parse (structured, smaller than full DOM)
- More stable (semantic roles don't change as often as classes)
- Better for AI (natural language names match user descriptions)

USAGE:
    finder = SmartElementFinder()

    # Option 1: With MCP client
    ref = await finder.find_element(mcp_client, "search button")
    await mcp_client.call_tool('playwright_click', {'ref': ref.ref})

    # Option 2: With Playwright page directly
    ref = await finder.find_element(page, "email input")
    await page.click(f'[data-ref="{ref.ref}"]')

    # Option 3: Smart matching
    snapshot = await page.accessibility.snapshot()
    parser = AccessibilityTreeParser()
    refs = parser.parse_snapshot(snapshot)
    buttons = parser.find_by_role(refs, "button")
    search_btn = parser.find_by_name(refs, "search", fuzzy=True)

Author: Eversale Team
Date: December 2024
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import re
from loguru import logger


# ==============================================================================
# CORE DATA STRUCTURES
# ==============================================================================

@dataclass
class AccessibilityRef:
    """
    A reference to an element in the accessibility tree.

    The ref format (e.g., 's1e5') is Playwright's internal identifier that maps
    to specific elements. This is more stable than CSS selectors.

    Attributes:
        ref: The accessibility reference (e.g., 's1e5', 's2b3')
        role: ARIA role (button, textbox, link, checkbox, etc.)
        name: Accessible name (button text, input label, link text)
        value: Current value (for inputs)
        description: Additional descriptive text
        bounds: Bounding box {x, y, width, height}
    """
    ref: str
    role: str
    name: str
    value: Optional[str] = None
    description: Optional[str] = None
    bounds: Optional[Dict[str, float]] = None

    def __str__(self) -> str:
        """Human-readable representation"""
        parts = [self.role, f'"{self.name}"']
        if self.ref:
            parts.append(f'[ref={self.ref}]')
        return ' '.join(parts)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'ref': self.ref,
            'role': self.role,
            'name': self.name,
            'value': self.value,
            'description': self.description,
            'bounds': self.bounds
        }


# ==============================================================================
# ACCESSIBILITY TREE PARSER
# ==============================================================================

class AccessibilityTreeParser:
    """
    Parse accessibility snapshots into structured AccessibilityRef objects.

    Handles two formats:
    1. MCP snapshot markdown (from playwright_snapshot):
       - button "Submit" [ref=s1e3]
       - textbox "Email" [ref=s1e5]

    2. Playwright accessibility snapshot dict:
       {"role": "button", "name": "Submit", "children": [...]}

    The parser extracts:
    - Element role (semantic type)
    - Element name (visible text/label)
    - Ref ID (for reliable targeting)
    - Hierarchy information (for context)
    """

    # Interactive roles that can be clicked
    CLICKABLE_ROLES = {
        'button', 'link', 'menuitem', 'tab', 'checkbox', 'radio',
        'switch', 'option', 'treeitem', 'gridcell', 'columnheader',
        'rowheader', 'menuitemcheckbox', 'menuitemradio'
    }

    # Interactive roles that can receive text input
    FILLABLE_ROLES = {
        'textbox', 'searchbox', 'spinbutton', 'combobox', 'textarea'
    }

    # Pattern to match accessibility tree lines
    # Format: - role "name" [ref=XXX]
    ELEMENT_PATTERN = re.compile(
        r'^\s*-?\s*(\w+)\s+"([^"]*)"(?:\s+\[ref=(\w+)\])?',
        re.MULTILINE
    )

    def parse_snapshot(self, snapshot_content: Any) -> List[AccessibilityRef]:
        """
        Parse accessibility snapshot into list of refs.

        Args:
            snapshot_content: Either:
                - String (markdown from MCP snapshot)
                - Dict (from page.accessibility.snapshot())

        Returns:
            List of AccessibilityRef objects
        """
        if isinstance(snapshot_content, str):
            return self._parse_markdown(snapshot_content)
        elif isinstance(snapshot_content, dict):
            return self._parse_tree(snapshot_content)
        else:
            logger.warning(f"Unknown snapshot format: {type(snapshot_content)}")
            return []

    def _parse_markdown(self, markdown: str) -> List[AccessibilityRef]:
        """Parse MCP-style markdown snapshot"""
        refs = []

        for match in self.ELEMENT_PATTERN.finditer(markdown):
            role = match.group(1).lower()
            name = match.group(2)
            ref = match.group(3)

            if ref:  # Only include elements with refs
                refs.append(AccessibilityRef(
                    ref=ref,
                    role=role,
                    name=name
                ))

        return refs

    def _parse_tree(self, node: Dict, refs: Optional[List[AccessibilityRef]] = None) -> List[AccessibilityRef]:
        """Parse Playwright accessibility tree recursively"""
        if refs is None:
            refs = []

        # Extract current node
        role = node.get('role', '').lower()
        name = node.get('name', '')
        value = node.get('value')
        description = node.get('description')

        # Generate ref ID (Playwright uses internal IDs)
        # In practice, we'd get this from the snapshot with locator mapping
        ref_id = node.get('ref', f's{len(refs)}e{len(refs)}')

        # Add element if it has a role and name
        if role and (name or value):
            refs.append(AccessibilityRef(
                ref=ref_id,
                role=role,
                name=name or value or '',
                value=value,
                description=description
            ))

        # Recurse children
        for child in node.get('children', []):
            self._parse_tree(child, refs)

        return refs

    def find_by_role(self, refs: List[AccessibilityRef], role: str) -> List[AccessibilityRef]:
        """
        Find all elements with specific role.

        Args:
            refs: List of accessibility refs
            role: Role to match (button, textbox, link, etc.)

        Returns:
            List of matching refs
        """
        role_lower = role.lower()
        return [r for r in refs if r.role == role_lower]

    def find_by_name(
        self,
        refs: List[AccessibilityRef],
        name: str,
        fuzzy: bool = True
    ) -> List[AccessibilityRef]:
        """
        Find elements by accessible name.

        Args:
            refs: List of accessibility refs
            name: Name to match
            fuzzy: If True, use partial case-insensitive match

        Returns:
            List of matching refs
        """
        if fuzzy:
            name_lower = name.lower()
            return [
                r for r in refs
                if name_lower in r.name.lower()
            ]
        else:
            return [r for r in refs if r.name == name]

    def find_by_text(self, refs: List[AccessibilityRef], text: str) -> List[AccessibilityRef]:
        """
        Find elements containing text in name, value, or description.

        Args:
            refs: List of accessibility refs
            text: Text to search for

        Returns:
            List of matching refs
        """
        text_lower = text.lower()
        matches = []

        for ref in refs:
            if text_lower in ref.name.lower():
                matches.append(ref)
            elif ref.value and text_lower in ref.value.lower():
                matches.append(ref)
            elif ref.description and text_lower in ref.description.lower():
                matches.append(ref)

        return matches

    def find_interactive(self, refs: List[AccessibilityRef]) -> List[AccessibilityRef]:
        """
        Find all clickable or typeable elements.

        Returns:
            List of interactive refs
        """
        return [
            r for r in refs
            if r.role in self.CLICKABLE_ROLES or r.role in self.FILLABLE_ROLES
        ]

    def find_clickable(self, refs: List[AccessibilityRef]) -> List[AccessibilityRef]:
        """Find all clickable elements"""
        return [r for r in refs if r.role in self.CLICKABLE_ROLES]

    def find_fillable(self, refs: List[AccessibilityRef]) -> List[AccessibilityRef]:
        """Find all fillable (input) elements"""
        return [r for r in refs if r.role in self.FILLABLE_ROLES]


# ==============================================================================
# SMART ELEMENT FINDER
# ==============================================================================

class SmartElementFinder:
    """
    Intelligent element finder using accessibility tree + fuzzy matching.

    This is the high-level API that combines parsing with smart matching.
    It understands natural language descriptions and finds the best match.

    Examples:
        - "search button" -> button with name containing "search"
        - "email input" -> textbox with name/label containing "email"
        - "login link" -> link with text containing "login"
        - "submit" -> button OR link with name containing "submit"

    Strategy:
    1. Get accessibility snapshot (from MCP or Playwright)
    2. Parse into AccessibilityRef objects
    3. Score each element against the description
    4. Return best match above confidence threshold
    """

    def __init__(self, min_confidence: float = 0.3):
        """
        Initialize finder.

        Args:
            min_confidence: Minimum confidence score to accept a match (0-1)
        """
        self.parser = AccessibilityTreeParser()
        self.min_confidence = min_confidence

        # Common role synonyms for better matching
        self.role_synonyms = {
            'button': ['btn', 'submit', 'click'],
            'textbox': ['input', 'field', 'box', 'text'],
            'searchbox': ['search', 'find'],
            'link': ['anchor', 'href'],
            'checkbox': ['check', 'toggle'],
            'combobox': ['dropdown', 'select']
        }

    async def find_element(
        self,
        page_or_mcp: Any,
        description: str,
        role_hint: Optional[str] = None
    ) -> Optional[AccessibilityRef]:
        """
        Find element matching natural language description.

        Args:
            page_or_mcp: Either Playwright page or MCP client
            description: Natural language description of element
            role_hint: Optional role filter (button, textbox, link, etc.)

        Returns:
            AccessibilityRef if found, None otherwise

        Example:
            ref = await finder.find_element(page, "search button")
            if ref:
                await page.click(f'[data-ref="{ref.ref}"]')
        """
        # Get snapshot
        snapshot = await self._get_snapshot(page_or_mcp)
        if not snapshot:
            logger.error("Failed to get accessibility snapshot")
            return None

        # Parse into refs
        refs = self.parser.parse_snapshot(snapshot)
        if not refs:
            logger.warning("No elements found in accessibility snapshot")
            return None

        # Find best match
        return self._find_best_match(refs, description, role_hint)

    async def find_all_matching(
        self,
        page_or_mcp: Any,
        description: str,
        role_hint: Optional[str] = None,
        max_results: int = 10
    ) -> List[AccessibilityRef]:
        """
        Find all elements matching description, sorted by confidence.

        Args:
            page_or_mcp: Playwright page or MCP client
            description: Natural language description
            role_hint: Optional role filter
            max_results: Maximum number of results to return

        Returns:
            List of matching refs, sorted by confidence (best first)
        """
        snapshot = await self._get_snapshot(page_or_mcp)
        if not snapshot:
            return []

        refs = self.parser.parse_snapshot(snapshot)
        if not refs:
            return []

        # Score all elements
        scored = []
        for ref in refs:
            if role_hint and ref.role != role_hint:
                continue

            score = self._score_match(ref, description)
            if score >= self.min_confidence:
                scored.append((score, ref))

        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)

        return [ref for _, ref in scored[:max_results]]

    async def _get_snapshot(self, page_or_mcp: Any) -> Any:
        """Get accessibility snapshot from page or MCP client"""
        # Check if it's an MCP client (has call_tool method)
        if hasattr(page_or_mcp, 'call_tool'):
            try:
                result = await page_or_mcp.call_tool('playwright_snapshot', {})
                # MCP returns dict with 'content' or 'text' key
                if isinstance(result, dict):
                    return result.get('content') or result.get('text') or result.get('markdown', '')
                return result
            except Exception as e:
                logger.error(f"MCP snapshot failed: {e}")
                return None

        # Otherwise assume it's a Playwright page
        elif hasattr(page_or_mcp, 'accessibility'):
            try:
                return await page_or_mcp.accessibility.snapshot()
            except Exception as e:
                logger.error(f"Playwright snapshot failed: {e}")
                return None

        else:
            logger.error(f"Unknown page type: {type(page_or_mcp)}")
            return None

    def _find_best_match(
        self,
        refs: List[AccessibilityRef],
        description: str,
        role_hint: Optional[str] = None
    ) -> Optional[AccessibilityRef]:
        """Find single best matching element"""
        best_ref = None
        best_score = 0.0

        for ref in refs:
            # Apply role filter if specified
            if role_hint and ref.role != role_hint:
                continue

            score = self._score_match(ref, description)
            if score > best_score:
                best_score = score
                best_ref = ref

        if best_score >= self.min_confidence:
            logger.debug(f"Found match: {best_ref} (confidence: {best_score:.2f})")
            return best_ref

        logger.debug(f"No match found above confidence {self.min_confidence} (best: {best_score:.2f})")
        return None

    def _score_match(self, ref: AccessibilityRef, description: str) -> float:
        """
        Score how well an element matches a description.

        Scoring factors:
        - Role mentioned in description (+0.3)
        - Name contains keywords (+0.3 per keyword)
        - Exact name match (+0.4)
        - Role synonym match (+0.2)

        Returns:
            Confidence score 0-1
        """
        desc_lower = description.lower()
        name_lower = ref.name.lower()
        role_lower = ref.role.lower()

        score = 0.0

        # Extract keywords (words > 2 chars)
        keywords = [w for w in desc_lower.split() if len(w) > 2]

        # 1. Role matching
        if role_lower in desc_lower:
            score += 0.3
        else:
            # Check role synonyms
            for synonym_list in self.role_synonyms.get(role_lower, []):
                if any(syn in desc_lower for syn in synonym_list):
                    score += 0.2
                    break

        # 2. Name matching
        for keyword in keywords:
            if keyword in name_lower:
                score += 0.3

        # 3. Exact match bonus
        if name_lower == desc_lower or name_lower in keywords:
            score += 0.4

        # 4. Value matching (for inputs with current values)
        if ref.value and any(kw in ref.value.lower() for kw in keywords):
            score += 0.2

        return min(1.0, score)  # Cap at 1.0


# ==============================================================================
# CONVENIENCE FUNCTIONS
# ==============================================================================

async def find_element(page_or_mcp: Any, description: str) -> Optional[AccessibilityRef]:
    """
    Quick helper to find element by description.

    Args:
        page_or_mcp: Playwright page or MCP client
        description: Natural language description

    Returns:
        AccessibilityRef or None

    Example:
        ref = await find_element(page, "login button")
        if ref:
            print(f"Found: {ref}")
    """
    finder = SmartElementFinder()
    return await finder.find_element(page_or_mcp, description)


async def find_button(page_or_mcp: Any, description: str) -> Optional[AccessibilityRef]:
    """Find button by description"""
    finder = SmartElementFinder()
    return await finder.find_element(page_or_mcp, description, role_hint='button')


async def find_input(page_or_mcp: Any, description: str) -> Optional[AccessibilityRef]:
    """Find input/textbox by description"""
    finder = SmartElementFinder()
    for role in ['textbox', 'searchbox']:
        ref = await finder.find_element(page_or_mcp, description, role_hint=role)
        if ref:
            return ref
    return None


async def find_link(page_or_mcp: Any, description: str) -> Optional[AccessibilityRef]:
    """Find link by description"""
    finder = SmartElementFinder()
    return await finder.find_element(page_or_mcp, description, role_hint='link')


def parse_snapshot(snapshot: Any) -> List[AccessibilityRef]:
    """
    Parse snapshot into refs (synchronous helper).

    Args:
        snapshot: Snapshot content (string or dict)

    Returns:
        List of AccessibilityRef objects
    """
    parser = AccessibilityTreeParser()
    return parser.parse_snapshot(snapshot)


# ==============================================================================
# TESTING AND EXAMPLES
# ==============================================================================

async def _test_parser():
    """Test the parser with example snapshots"""
    print("=" * 60)
    print("Accessibility Element Finder Test")
    print("=" * 60)

    # Test markdown parsing
    print("\n1. Markdown Snapshot Parsing:")
    markdown_snapshot = """
    - button "Search" [ref=s1e3]
    - textbox "Email address" [ref=s1e5]
    - link "Sign in" [ref=s1e7]
    - button "Submit" [ref=s1e9]
    """

    parser = AccessibilityTreeParser()
    refs = parser.parse_snapshot(markdown_snapshot)
    print(f"   Found {len(refs)} elements:")
    for ref in refs:
        print(f"   - {ref}")

    # Test finding
    print("\n2. Finding Elements:")
    buttons = parser.find_by_role(refs, "button")
    print(f"   Buttons: {[str(b) for b in buttons]}")

    email_input = parser.find_by_name(refs, "email", fuzzy=True)
    print(f"   Email inputs: {[str(e) for e in email_input]}")

    # Test smart matching
    print("\n3. Smart Matching:")
    finder = SmartElementFinder()

    test_descriptions = [
        "search button",
        "email input",
        "sign in link",
        "submit"
    ]

    for desc in test_descriptions:
        match = finder._find_best_match(refs, desc)
        if match:
            print(f"   '{desc}' -> {match}")
        else:
            print(f"   '{desc}' -> No match")

    print("\n" + "=" * 60)
    print("Test complete!")


if __name__ == "__main__":
    import asyncio
    asyncio.run(_test_parser())
