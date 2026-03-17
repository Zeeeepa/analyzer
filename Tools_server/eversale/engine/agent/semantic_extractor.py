"""
Semantic Element Extractor - Extract rich features from DOM elements

Extracts:
- Multiple selector candidates (CSS, XPath)
- Semantic features (role, text, attrs, domPath, bbox)
- Used for DOM map building and self-healing selectors
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional, Tuple
import hashlib
import json
from loguru import logger


@dataclass
class ExtractedElement:
    """Full semantic extraction of a DOM element"""
    # Selector candidates
    css_selectors: List[str] = field(default_factory=list)
    xpath_selectors: List[str] = field(default_factory=list)

    # Semantic features
    tag: str = ""
    role: Optional[str] = None
    text: Optional[str] = None  # trimmed, max 256 chars
    aria_label: Optional[str] = None
    placeholder: Optional[str] = None
    name: Optional[str] = None
    id: Optional[str] = None
    classes: List[str] = field(default_factory=list)
    data_attrs: Dict[str, str] = field(default_factory=dict)  # data-testid, etc.
    dom_path: str = ""  # e.g. "html>body>div:nth-of-type(2)>button"

    # Position
    bbox: Optional[Dict[str, float]] = None  # {x, y, width, height}

    # Metadata
    is_visible: bool = True
    is_interactive: bool = False

    def to_semantic_id(self) -> str:
        """Generate unique ID based on semantic signature"""
        sig = f"{self.dom_path}::{self.text or ''}::{self.role or ''}"
        return hashlib.md5(sig.encode()).hexdigest()[:16]

    def to_dict(self) -> Dict:
        return asdict(self)


class SemanticExtractor:
    """
    Extract semantic features from Playwright elements.

    Usage:
        extractor = SemanticExtractor(page)
        extracted = await extractor.extract(element)
        # or
        extracted = await extractor.extract_at_point(x, y)
    """

    def __init__(self, page):
        self.page = page

    async def extract(self, element) -> Optional[ExtractedElement]:
        """Extract full semantic features from a Playwright element"""
        try:
            # Use page.evaluate to extract everything in one call
            raw_data = await element.evaluate(EXTRACT_ELEMENT_JS)

            if not raw_data:
                return None

            # Generate selectors from extracted data
            css_selectors = self._generate_css_selectors(raw_data)
            xpath_selectors = self._generate_xpath_selectors(raw_data)

            return ExtractedElement(
                css_selectors=css_selectors,
                xpath_selectors=xpath_selectors,
                tag=raw_data.get("tag", ""),
                role=raw_data.get("role"),
                text=raw_data.get("text"),
                aria_label=raw_data.get("ariaLabel"),
                placeholder=raw_data.get("placeholder"),
                name=raw_data.get("name"),
                id=raw_data.get("id"),
                classes=raw_data.get("classes", []),
                data_attrs=raw_data.get("dataAttrs", {}),
                dom_path=raw_data.get("domPath", ""),
                bbox=raw_data.get("bbox"),
                is_visible=raw_data.get("isVisible", False),
                is_interactive=raw_data.get("isInteractive", False)
            )
        except Exception as e:
            logger.warning(f"Failed to extract element: {e}")
            return None

    async def extract_at_point(self, x: float, y: float) -> Optional[ExtractedElement]:
        """Extract element at coordinates"""
        try:
            # Get element at point
            element = await self.page.evaluate_handle(
                f"document.elementFromPoint({x}, {y})"
            )

            if not element:
                return None

            # Extract using the element handle
            raw_data = await element.evaluate(EXTRACT_ELEMENT_JS)

            if not raw_data:
                return None

            # Generate selectors
            css_selectors = self._generate_css_selectors(raw_data)
            xpath_selectors = self._generate_xpath_selectors(raw_data)

            return ExtractedElement(
                css_selectors=css_selectors,
                xpath_selectors=xpath_selectors,
                tag=raw_data.get("tag", ""),
                role=raw_data.get("role"),
                text=raw_data.get("text"),
                aria_label=raw_data.get("ariaLabel"),
                placeholder=raw_data.get("placeholder"),
                name=raw_data.get("name"),
                id=raw_data.get("id"),
                classes=raw_data.get("classes", []),
                data_attrs=raw_data.get("dataAttrs", {}),
                dom_path=raw_data.get("domPath", ""),
                bbox=raw_data.get("bbox"),
                is_visible=raw_data.get("isVisible", False),
                is_interactive=raw_data.get("isInteractive", False)
            )
        except Exception as e:
            logger.warning(f"Failed to extract element at point ({x}, {y}): {e}")
            return None

    async def extract_all_interactive(self) -> List[ExtractedElement]:
        """Extract all interactive elements on page (for DOM map building)"""
        try:
            # Use evaluate to get all interactive elements data in one call
            elements_data = await self.page.evaluate(EXTRACT_ALL_INTERACTIVE_JS)

            if not elements_data:
                return []

            results = []
            for raw_data in elements_data:
                try:
                    # Generate selectors for each element
                    css_selectors = self._generate_css_selectors(raw_data)
                    xpath_selectors = self._generate_xpath_selectors(raw_data)

                    element = ExtractedElement(
                        css_selectors=css_selectors,
                        xpath_selectors=xpath_selectors,
                        tag=raw_data.get("tag", ""),
                        role=raw_data.get("role"),
                        text=raw_data.get("text"),
                        aria_label=raw_data.get("ariaLabel"),
                        placeholder=raw_data.get("placeholder"),
                        name=raw_data.get("name"),
                        id=raw_data.get("id"),
                        classes=raw_data.get("classes", []),
                        data_attrs=raw_data.get("dataAttrs", {}),
                        dom_path=raw_data.get("domPath", ""),
                        bbox=raw_data.get("bbox"),
                        is_visible=raw_data.get("isVisible", False),
                        is_interactive=raw_data.get("isInteractive", False)
                    )
                    results.append(element)
                except Exception as e:
                    logger.warning(f"Failed to process element: {e}")
                    continue

            return results
        except Exception as e:
            logger.error(f"Failed to extract interactive elements: {e}")
            return []

    def _generate_css_selectors(self, data: Dict) -> List[str]:
        """Generate multiple CSS selector candidates from extracted data"""
        selectors = []

        # Priority 1: ID selector
        if data.get("id"):
            selectors.append(f"#{data['id']}")

        # Priority 2: data-testid (common in modern apps)
        data_attrs = data.get("dataAttrs", {})
        if "data-testid" in data_attrs:
            selectors.append(f'[data-testid="{data_attrs["data-testid"]}"]')

        # Priority 3: aria-label (good for accessibility)
        if data.get("ariaLabel"):
            aria_label = data["ariaLabel"].replace('"', '\\"')
            selectors.append(f'[aria-label="{aria_label}"]')

        # Priority 4: name attribute (for forms)
        if data.get("name"):
            selectors.append(f'[name="{data["name"]}"]')

        # Priority 5: tag + classes
        tag = data.get("tag", "")
        classes = data.get("classes", [])
        if tag and classes:
            class_str = ".".join(classes)
            selectors.append(f"{tag}.{class_str}")
        elif tag:
            selectors.append(tag)

        # Priority 6: placeholder (for inputs)
        if data.get("placeholder"):
            placeholder = data["placeholder"].replace('"', '\\"')
            selectors.append(f'[placeholder="{placeholder}"]')

        # Priority 7: Other data attributes
        for attr_name, attr_value in data_attrs.items():
            if attr_name != "data-testid":  # already added
                selectors.append(f'[{attr_name}="{attr_value}"]')

        # Priority 8: DOM path selector (most specific, but fragile)
        if data.get("domPath"):
            # Convert "div > button:nth-of-type(2)" to "div > button:nth-of-type(2)"
            selectors.append(data["domPath"])

        return selectors

    def _generate_xpath_selectors(self, data: Dict) -> List[str]:
        """Generate XPath selector candidates"""
        selectors = []

        # Priority 1: ID
        if data.get("id"):
            selectors.append(f'//*[@id="{data["id"]}"]')

        # Priority 2: data-testid
        data_attrs = data.get("dataAttrs", {})
        if "data-testid" in data_attrs:
            selectors.append(f'//*[@data-testid="{data_attrs["data-testid"]}"]')

        # Priority 3: aria-label
        if data.get("ariaLabel"):
            aria_label = data["ariaLabel"].replace('"', '\\"')
            selectors.append(f'//*[@aria-label="{aria_label}"]')

        # Priority 4: Text content (for links/buttons)
        tag = data.get("tag", "")
        text = data.get("text", "")
        if text and len(text) < 50:  # Only for short text
            text_escaped = text.replace('"', '\\"')
            if tag:
                selectors.append(f'//{tag}[contains(text(), "{text_escaped}")]')
            else:
                selectors.append(f'//*[contains(text(), "{text_escaped}")]')

        # Priority 5: name attribute
        if data.get("name"):
            selectors.append(f'//*[@name="{data["name"]}"]')

        # Priority 6: placeholder
        if data.get("placeholder"):
            placeholder = data["placeholder"].replace('"', '\\"')
            selectors.append(f'//*[@placeholder="{placeholder}"]')

        return selectors


# JavaScript to inject for extraction
EXTRACT_ELEMENT_JS = '''
(element) => {
    if (!element) return null;

    const rect = element.getBoundingClientRect();
    const style = getComputedStyle(element);

    // Get all attributes
    const attrs = {};
    for (const attr of element.attributes) {
        attrs[attr.name] = attr.value;
    }

    // Build DOM path
    const buildDomPath = (el) => {
        const path = [];
        let current = el;
        while (current && current.nodeType === 1) {
            const tag = current.tagName.toLowerCase();
            const parent = current.parentElement;
            if (!parent) {
                path.unshift(tag);
                break;
            }
            const siblings = Array.from(parent.children).filter(c => c.tagName === current.tagName);
            const index = siblings.indexOf(current) + 1;
            path.unshift(index > 1 ? `${tag}:nth-of-type(${index})` : tag);
            current = parent;
        }
        return path.join(' > ');
    };

    // Determine if interactive
    const interactiveTags = ['a', 'button', 'input', 'select', 'textarea'];
    const isInteractive = interactiveTags.includes(element.tagName.toLowerCase()) ||
        element.getAttribute('role') === 'button' ||
        element.getAttribute('role') === 'link' ||
        element.onclick !== null ||
        element.getAttribute('tabindex') !== null;

    return {
        tag: element.tagName.toLowerCase(),
        id: element.id || null,
        classes: Array.from(element.classList),
        role: element.getAttribute('role') || null,
        text: (element.textContent || '').trim().slice(0, 256),
        ariaLabel: element.getAttribute('aria-label') || null,
        placeholder: element.getAttribute('placeholder') || null,
        name: element.getAttribute('name') || null,
        dataAttrs: Object.fromEntries(
            Object.entries(attrs).filter(([k]) => k.startsWith('data-'))
        ),
        domPath: buildDomPath(element),
        bbox: {
            x: rect.x,
            y: rect.y,
            width: rect.width,
            height: rect.height
        },
        isVisible: rect.width > 0 && rect.height > 0 &&
            style.display !== 'none' &&
            style.visibility !== 'hidden' &&
            style.opacity !== '0',
        isInteractive: isInteractive
    };
}
'''

EXTRACT_ALL_INTERACTIVE_JS = '''
() => {
    const interactive = document.querySelectorAll(
        'a, button, input, select, textarea, [role="button"], [role="link"], [onclick], [tabindex]'
    );

    const results = [];

    for (const element of interactive) {
        const rect = element.getBoundingClientRect();
        const style = getComputedStyle(element);

        // Get all attributes
        const attrs = {};
        for (const attr of element.attributes) {
            attrs[attr.name] = attr.value;
        }

        // Build DOM path
        const buildDomPath = (el) => {
            const path = [];
            let current = el;
            while (current && current.nodeType === 1) {
                const tag = current.tagName.toLowerCase();
                const parent = current.parentElement;
                if (!parent) {
                    path.unshift(tag);
                    break;
                }
                const siblings = Array.from(parent.children).filter(c => c.tagName === current.tagName);
                const index = siblings.indexOf(current) + 1;
                path.unshift(index > 1 ? `${tag}:nth-of-type(${index})` : tag);
                current = parent;
            }
            return path.join(' > ');
        };

        // Determine if interactive
        const interactiveTags = ['a', 'button', 'input', 'select', 'textarea'];
        const isInteractive = interactiveTags.includes(element.tagName.toLowerCase()) ||
            element.getAttribute('role') === 'button' ||
            element.getAttribute('role') === 'link' ||
            element.onclick !== null ||
            element.getAttribute('tabindex') !== null;

        // Skip if not visible
        const isVisible = rect.width > 0 && rect.height > 0 &&
            style.display !== 'none' &&
            style.visibility !== 'hidden' &&
            style.opacity !== '0';

        if (!isVisible) continue;

        results.push({
            tag: element.tagName.toLowerCase(),
            id: element.id || null,
            classes: Array.from(element.classList),
            role: element.getAttribute('role') || null,
            text: (element.textContent || '').trim().slice(0, 256),
            ariaLabel: element.getAttribute('aria-label') || null,
            placeholder: element.getAttribute('placeholder') || null,
            name: element.getAttribute('name') || null,
            dataAttrs: Object.fromEntries(
                Object.entries(attrs).filter(([k]) => k.startsWith('data-'))
            ),
            domPath: buildDomPath(element),
            bbox: {
                x: rect.x,
                y: rect.y,
                width: rect.width,
                height: rect.height
            },
            isVisible: isVisible,
            isInteractive: isInteractive
        });
    }

    return results;
}
'''
