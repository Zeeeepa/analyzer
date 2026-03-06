"""
Zero-Shot Coordinate Targeting Engine

Instead of fragile CSS selectors, use coordinates from accessibility snapshots.
This matches how humans interact - we see elements and click positions, not selectors.

Key advantages:
1. Works even when selectors change between page loads
2. Faster than selector-based clicking (no DOM query)
3. More reliable for dynamically generated content
4. Natural integration with vision models
"""

import asyncio
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from loguru import logger
import re
import json


@dataclass
class ElementCoordinate:
    """Element position on screen"""
    x: int
    y: int
    width: int
    height: int
    center_x: int = field(init=False)
    center_y: int = field(init=False)

    def __post_init__(self):
        self.center_x = self.x + self.width // 2
        self.center_y = self.y + self.height // 2

    def click_point(self, offset_x: int = 0, offset_y: int = 0) -> Tuple[int, int]:
        """Get click coordinates with optional offset"""
        return (self.center_x + offset_x, self.center_y + offset_y)

    def is_visible(self, viewport_width: int = 1280, viewport_height: int = 720) -> bool:
        """Check if element is in viewport"""
        return (
            0 <= self.center_x <= viewport_width and
            0 <= self.center_y <= viewport_height
        )


@dataclass
class TargetedElement:
    """An element with targeting information"""
    ref: str  # Accessibility reference (e.g., "ref=s2b3")
    role: str  # button, link, textbox, etc.
    name: str  # Accessible name/label
    coords: Optional[ElementCoordinate]
    selector_hint: Optional[str] = None  # Backup selector if available
    confidence: float = 1.0


class AccessibilityParser:
    """
    Parse Playwright accessibility snapshots into targetable elements.

    Snapshot format:
    - button "Submit" [ref=s1e3]
    - link "Home" [ref=s1e4]
    - textbox "Email" [ref=s1e5]
    """

    # Regex to parse accessibility tree lines
    ELEMENT_PATTERN = re.compile(
        r'^\s*-?\s*(\w+)\s+"([^"]*)"(?:\s+\[ref=(\w+)\])?',
        re.MULTILINE
    )

    # Roles that are clickable
    CLICKABLE_ROLES = {'button', 'link', 'menuitem', 'tab', 'checkbox', 'radio', 'switch'}

    # Roles that are fillable
    FILLABLE_ROLES = {'textbox', 'searchbox', 'spinbutton', 'combobox', 'textarea'}

    def parse_snapshot(self, snapshot_text: str) -> List[TargetedElement]:
        """Parse accessibility snapshot into elements"""
        elements = []

        for match in self.ELEMENT_PATTERN.finditer(snapshot_text):
            role = match.group(1).lower()
            name = match.group(2)
            ref = match.group(3) if match.group(3) else None

            if not ref:
                continue

            elements.append(TargetedElement(
                ref=ref,
                role=role,
                name=name,
                coords=None,  # Will be populated by bounding box lookup
                selector_hint=self._guess_selector(role, name)
            ))

        return elements

    def _guess_selector(self, role: str, name: str) -> Optional[str]:
        """Generate a backup selector from role/name"""
        if not name:
            return None

        # Escape special characters
        escaped_name = name.replace('"', '\\"')

        # ARIA role selectors
        return f'[role="{role}"][aria-label*="{escaped_name}"], {role}:has-text("{escaped_name}")'

    def find_by_description(
        self,
        elements: List[TargetedElement],
        description: str,
        role_filter: Optional[str] = None
    ) -> Optional[TargetedElement]:
        """
        Find element matching natural language description.

        Examples:
        - "the submit button" -> button with name containing "submit"
        - "email input" -> textbox with name containing "email"
        - "login link" -> link with name containing "login"
        """
        description_lower = description.lower()

        # Extract keywords
        keywords = [w for w in description_lower.split() if len(w) > 2]

        # Score each element
        best_match = None
        best_score = 0

        for elem in elements:
            # Apply role filter if specified
            if role_filter and elem.role != role_filter:
                continue

            # Check role mentioned in description
            role_score = 0
            if elem.role in description_lower:
                role_score = 0.3
            elif any(r in description_lower for r in ['button', 'btn']) and elem.role == 'button':
                role_score = 0.25
            elif any(r in description_lower for r in ['link', 'click']) and elem.role == 'link':
                role_score = 0.25
            elif any(r in description_lower for r in ['input', 'field', 'box']) and elem.role in self.FILLABLE_ROLES:
                role_score = 0.25

            # Check name match
            name_lower = elem.name.lower()
            name_score = 0
            for kw in keywords:
                if kw in name_lower:
                    name_score += 0.3

            # Exact match bonus
            if any(kw == name_lower for kw in keywords):
                name_score += 0.2

            total_score = role_score + name_score

            if total_score > best_score:
                best_score = total_score
                best_match = elem
                best_match.confidence = min(1.0, total_score)

        if best_match and best_score >= 0.3:
            return best_match

        return None


class CoordinateTargeting:
    """
    Click/fill elements using coordinates from accessibility refs.

    Workflow:
    1. Get accessibility snapshot (fast, structured)
    2. Parse into TargetedElement list
    3. Match user intent to element by description
    4. Get bounding box for element ref
    5. Click at center coordinates
    """

    def __init__(self):
        self.parser = AccessibilityParser()
        # Cache of element positions: {ref: ElementCoordinate}
        self.position_cache: Dict[str, ElementCoordinate] = {}
        self.cache_url: str = ""

        # Stats
        self.stats = {
            'coordinate_clicks': 0,
            'selector_fallbacks': 0,
            'targeting_failures': 0
        }

    async def get_snapshot_with_coords(self, page) -> Tuple[str, List[TargetedElement]]:
        """Get accessibility snapshot and populate coordinates"""
        # Get snapshot
        try:
            snapshot = await page.accessibility.snapshot()
            snapshot_text = self._serialize_snapshot(snapshot)
        except Exception as e:
            logger.warning(f"[COORD_TARGET] Snapshot failed: {e}")
            return "", []

        # Parse elements
        elements = self.parser.parse_snapshot(snapshot_text)

        # Get bounding boxes for all refs
        await self._populate_coordinates(page, elements)

        return snapshot_text, elements

    def _serialize_snapshot(self, node: Dict, indent: int = 0) -> str:
        """Convert snapshot dict to readable text format"""
        if not node:
            return ""

        lines = []
        prefix = "  " * indent

        role = node.get('role', 'unknown')
        name = node.get('name', '')

        # Create line
        line = f"{prefix}- {role} \"{name}\""
        if 'ref' in node:
            line += f" [ref={node['ref']}]"
        lines.append(line)

        # Recurse children
        for child in node.get('children', []):
            lines.append(self._serialize_snapshot(child, indent + 1))

        return '\n'.join(lines)

    async def _populate_coordinates(self, page, elements: List[TargetedElement]):
        """Get bounding boxes for elements via their refs"""
        current_url = page.url

        # Check if cache is valid
        if self.cache_url != current_url:
            self.position_cache.clear()
            self.cache_url = current_url

        for elem in elements:
            if elem.ref in self.position_cache:
                elem.coords = self.position_cache[elem.ref]
                continue

            try:
                # Use Playwright's internal ref system
                locator = page.get_by_test_id(elem.ref)
                if await locator.count() == 0:
                    # Try aria snapshot ref
                    locator = page.locator(f'[data-ref="{elem.ref}"]')

                if await locator.count() > 0:
                    box = await locator.bounding_box()
                    if box:
                        coords = ElementCoordinate(
                            x=int(box['x']),
                            y=int(box['y']),
                            width=int(box['width']),
                            height=int(box['height'])
                        )
                        elem.coords = coords
                        self.position_cache[elem.ref] = coords
            except Exception as e:
                logger.debug(f"[COORD_TARGET] Failed to get bbox for {elem.ref}: {e}")

    async def click_by_description(
        self,
        page,
        description: str,
        elements: Optional[List[TargetedElement]] = None
    ) -> Dict[str, Any]:
        """
        Click element matching description using coordinates.

        Args:
            page: Playwright page
            description: Natural language description ("submit button", "login link")
            elements: Pre-parsed elements (optional, will fetch if not provided)
        """
        if elements is None:
            _, elements = await self.get_snapshot_with_coords(page)

        # Find matching element
        target = self.parser.find_by_description(elements, description)

        if not target:
            self.stats['targeting_failures'] += 1
            return {
                'success': False,
                'error': f'No element found matching: {description}',
                'available': [f"{e.role}: {e.name}" for e in elements[:10]]
            }

        # Try coordinate click first
        if target.coords and target.coords.is_visible():
            try:
                x, y = target.coords.click_point()
                await page.mouse.click(x, y)
                self.stats['coordinate_clicks'] += 1

                logger.info(f"[COORD_TARGET] Clicked {target.role} '{target.name}' at ({x}, {y})")

                return {
                    'success': True,
                    'method': 'coordinate',
                    'element': {'role': target.role, 'name': target.name},
                    'coordinates': {'x': x, 'y': y},
                    'confidence': target.confidence
                }
            except Exception as e:
                logger.warning(f"[COORD_TARGET] Coordinate click failed: {e}")

        # Fallback to selector
        if target.selector_hint:
            try:
                await page.click(target.selector_hint, timeout=3000)
                self.stats['selector_fallbacks'] += 1

                return {
                    'success': True,
                    'method': 'selector_fallback',
                    'element': {'role': target.role, 'name': target.name},
                    'selector': target.selector_hint
                }
            except Exception as e:
                logger.warning(f"[COORD_TARGET] Selector fallback failed: {e}")

        self.stats['targeting_failures'] += 1
        return {
            'success': False,
            'error': f'Could not click element: {target.role} "{target.name}"',
            'tried': ['coordinate', 'selector']
        }

    async def fill_by_description(
        self,
        page,
        description: str,
        value: str,
        elements: Optional[List[TargetedElement]] = None
    ) -> Dict[str, Any]:
        """Fill input element matching description"""
        if elements is None:
            _, elements = await self.get_snapshot_with_coords(page)

        # Filter to fillable elements
        fillable = [e for e in elements if e.role in self.parser.FILLABLE_ROLES]

        target = self.parser.find_by_description(fillable, description, role_filter=None)

        if not target:
            return {
                'success': False,
                'error': f'No input found matching: {description}',
                'available_inputs': [f"{e.name}" for e in fillable[:5]]
            }

        # Click to focus, then type
        if target.coords and target.coords.is_visible():
            try:
                x, y = target.coords.click_point()
                await page.mouse.click(x, y)
                await page.keyboard.type(value)

                return {
                    'success': True,
                    'method': 'coordinate',
                    'element': {'role': target.role, 'name': target.name},
                    'value': value
                }
            except Exception as e:
                logger.warning(f"[COORD_TARGET] Coordinate fill failed: {e}")

        # Selector fallback
        if target.selector_hint:
            try:
                await page.fill(target.selector_hint, value, timeout=3000)
                return {
                    'success': True,
                    'method': 'selector_fallback',
                    'element': {'role': target.role, 'name': target.name},
                    'value': value
                }
            except:
                pass

        return {
            'success': False,
            'error': f'Could not fill element: {target.role} "{target.name}"'
        }

    async def click_at_ref(self, page, ref: str) -> Dict[str, Any]:
        """Click directly at accessibility ref (fastest path)"""
        if ref in self.position_cache:
            coords = self.position_cache[ref]
            x, y = coords.click_point()
            await page.mouse.click(x, y)
            self.stats['coordinate_clicks'] += 1
            return {'success': True, 'coordinates': {'x': x, 'y': y}}

        # Get fresh coordinates
        try:
            # Playwright's aria snapshot uses internal refs
            box = await page.evaluate(f'''
                () => {{
                    const el = document.querySelector('[data-ref="{ref}"]');
                    if (!el) return null;
                    const rect = el.getBoundingClientRect();
                    return {{x: rect.x, y: rect.y, width: rect.width, height: rect.height}};
                }}
            ''')

            if box:
                coords = ElementCoordinate(**box)
                self.position_cache[ref] = coords
                x, y = coords.click_point()
                await page.mouse.click(x, y)
                self.stats['coordinate_clicks'] += 1
                return {'success': True, 'coordinates': {'x': x, 'y': y}}
        except Exception as e:
            logger.error(f"[COORD_TARGET] click_at_ref failed: {e}")

        return {'success': False, 'error': f'Cannot find element with ref: {ref}'}

    def get_stats(self) -> Dict:
        """Get targeting statistics"""
        total = sum(self.stats.values())
        return {
            **self.stats,
            'coordinate_success_rate': self.stats['coordinate_clicks'] / max(1, total),
            'cache_size': len(self.position_cache)
        }


# Singleton
_coordinator: Optional[CoordinateTargeting] = None

def get_coordinate_targeting() -> CoordinateTargeting:
    """Get or create the coordinate targeting system"""
    global _coordinator
    if _coordinator is None:
        _coordinator = CoordinateTargeting()
    return _coordinator


# Convenience functions
async def smart_click(page, description: str) -> Dict:
    """Click element by natural language description"""
    targeting = get_coordinate_targeting()
    return await targeting.click_by_description(page, description)


async def smart_fill(page, description: str, value: str) -> Dict:
    """Fill input by natural language description"""
    targeting = get_coordinate_targeting()
    return await targeting.fill_by_description(page, description, value)
