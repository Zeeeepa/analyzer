"""
Selector Extractor - Forces agent to use REAL selectors from the DOM.

The model loves to hallucinate selectors from training data:
- .storylink (old HN/Reddit)
- .thing, .title.may-blank (old Reddit)
- .ads-table (doesn't exist)

This module extracts ACTUAL clickable/extractable elements from the current page
and forces the agent to pick from this list. No more guessing.
"""

import re
import json
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass
from loguru import logger


@dataclass
class ExtractedElement:
    """A real element from the DOM."""
    selector: str
    element_type: str  # button, link, input, text, etc.
    text: str
    attributes: Dict[str, str]
    confidence: float  # How reliable is this selector


class SelectorExtractor:
    """
    Extracts valid selectors from actual page content.

    Agent MUST pick from these - no hallucination allowed.
    """

    # Known broken selectors (from training failures)
    KNOWN_DEAD_SELECTORS = {
        # Old Reddit
        '.storylink', '.thing', '.title.may-blank', '.rank', '.score',
        '.comments', '.domain', '.entry', '.midcol', '.arrow',
        # Old HN
        '.athing', '.titlelink', '.subtext',
        # Generic hallucinations
        '.ads-table', '.ad-name', '.advertiser-name', '.ad-row',
        '.price-table', '.pricing-row', '.feature-list',
        '.main-content', '.sidebar', '.footer-links',
    }

    # Selector patterns that work on modern sites
    MODERN_SELECTOR_PATTERNS = [
        # Data attributes (most reliable)
        r'\[data-testid=["\'][^"\']+["\']\]',
        r'\[data-qa=["\'][^"\']+["\']\]',
        r'\[data-cy=["\'][^"\']+["\']\]',
        r'\[aria-label=["\'][^"\']+["\']\]',
        # Semantic selectors
        r'button\[type=["\'][^"\']+["\']\]',
        r'a\[href[*^$]?=["\'][^"\']+["\']\]',
        r'input\[name=["\'][^"\']+["\']\]',
        r'form\[action=["\'][^"\']+["\']\]',
    ]

    def __init__(self):
        # Failed selector memory (learned from training)
        self.failed_selectors: Dict[str, Dict] = {}
        self._load_failed_selectors()

    def extract_valid_selectors(self,
                                 page_html: str = None,
                                 page_snapshot: str = None,
                                 element_type: str = None) -> List[ExtractedElement]:
        """
        Extract valid selectors from the current page.

        Args:
            page_html: Raw HTML (if available)
            page_snapshot: Accessibility/text snapshot
            element_type: Filter for specific types (button, link, input, etc.)

        Returns:
            List of ExtractedElement with real, working selectors
        """
        elements = []

        if page_html:
            elements.extend(self._extract_from_html(page_html))

        if page_snapshot:
            elements.extend(self._extract_from_snapshot(page_snapshot))

        # Filter by type if requested
        if element_type:
            elements = [e for e in elements if e.element_type == element_type]

        # Remove known dead selectors
        elements = [e for e in elements if not self._is_dead_selector(e.selector)]

        # Sort by confidence
        elements.sort(key=lambda e: e.confidence, reverse=True)

        return elements

    def _extract_from_html(self, html: str) -> List[ExtractedElement]:
        """Extract selectors from raw HTML."""
        elements = []

        # Extract data-testid attributes (most reliable)
        testid_pattern = r'data-testid=["\']([^"\']+)["\']'
        for match in re.finditer(testid_pattern, html):
            testid = match.group(1)
            elements.append(ExtractedElement(
                selector=f'[data-testid="{testid}"]',
                element_type='unknown',
                text='',
                attributes={'data-testid': testid},
                confidence=0.95
            ))

        # Extract aria-label attributes
        aria_pattern = r'aria-label=["\']([^"\']+)["\']'
        for match in re.finditer(aria_pattern, html):
            label = match.group(1)
            elements.append(ExtractedElement(
                selector=f'[aria-label="{label}"]',
                element_type='unknown',
                text=label,
                attributes={'aria-label': label},
                confidence=0.9
            ))

        # Extract buttons with text
        button_pattern = r'<button[^>]*>([^<]+)</button>'
        for match in re.finditer(button_pattern, html, re.IGNORECASE):
            text = match.group(1).strip()
            if text and len(text) > 1:
                elements.append(ExtractedElement(
                    selector=f'button:has-text("{text}")',
                    element_type='button',
                    text=text,
                    attributes={},
                    confidence=0.85
                ))

        # Extract links with href
        link_pattern = r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>([^<]*)</a>'
        for match in re.finditer(link_pattern, html, re.IGNORECASE):
            href = match.group(1)
            text = match.group(2).strip()
            if href and not href.startswith('#'):
                elements.append(ExtractedElement(
                    selector=f'a[href="{href}"]',
                    element_type='link',
                    text=text,
                    attributes={'href': href},
                    confidence=0.8
                ))

        # Extract inputs with name/id
        input_pattern = r'<input[^>]*(?:name|id)=["\']([^"\']+)["\'][^>]*>'
        for match in re.finditer(input_pattern, html, re.IGNORECASE):
            name = match.group(1)
            elements.append(ExtractedElement(
                selector=f'input[name="{name}"], input[id="{name}"]',
                element_type='input',
                text='',
                attributes={'name': name},
                confidence=0.85
            ))

        return elements

    def _extract_from_snapshot(self, snapshot: str) -> List[ExtractedElement]:
        """Extract selectors from accessibility/text snapshot."""
        elements = []

        # Look for button/link patterns in snapshot
        # Format varies by snapshot type

        # Pattern: "button: Submit" or "[button] Submit"
        button_pattern = r'(?:button|Button)[:\s]+([^\n\r]+)'
        for match in re.finditer(button_pattern, snapshot):
            text = match.group(1).strip()
            if text and len(text) > 1 and len(text) < 50:
                elements.append(ExtractedElement(
                    selector=f'button:has-text("{text}")',
                    element_type='button',
                    text=text,
                    attributes={},
                    confidence=0.7
                ))

        # Pattern: "link: Click here" or "[link] About"
        link_pattern = r'(?:link|Link)[:\s]+([^\n\r]+)'
        for match in re.finditer(link_pattern, snapshot):
            text = match.group(1).strip()
            if text and len(text) > 1 and len(text) < 100:
                elements.append(ExtractedElement(
                    selector=f'a:has-text("{text}")',
                    element_type='link',
                    text=text,
                    attributes={},
                    confidence=0.65
                ))

        return elements

    def _is_dead_selector(self, selector: str) -> bool:
        """Check if selector is known to be broken."""
        selector_lower = selector.lower()

        # Check against known dead selectors
        for dead in self.KNOWN_DEAD_SELECTORS:
            if dead.lower() in selector_lower:
                return True

        # Check against learned failures
        if selector in self.failed_selectors:
            failure_info = self.failed_selectors[selector]
            if failure_info.get('failure_count', 0) >= 3:
                return True

        return False

    def record_selector_failure(self,
                                 selector: str,
                                 site: str,
                                 error: str,
                                 working_alternative: str = None):
        """
        Record a selector failure for learning.

        This builds the negative example database.
        """
        if selector not in self.failed_selectors:
            self.failed_selectors[selector] = {
                'sites': [],
                'failure_count': 0,
                'errors': [],
                'working_alternatives': []
            }

        info = self.failed_selectors[selector]
        info['failure_count'] += 1

        if site and site not in info['sites']:
            info['sites'].append(site)

        if error and error not in info['errors']:
            info['errors'].append(error[:100])

        if working_alternative:
            info['working_alternatives'].append({
                'selector': working_alternative,
                'site': site
            })

        self._save_failed_selectors()
        logger.info(f"[SELECTOR] Recorded failure: {selector} on {site}")

    def record_selector_success(self, selector: str, site: str):
        """Record a working selector for positive reinforcement."""
        # Could build a "known working" database
        pass

    def get_selector_suggestion(self,
                                 failed_selector: str,
                                 site: str = None) -> Optional[str]:
        """
        Get a working alternative for a failed selector.

        Uses learned failures to suggest replacements.
        """
        if failed_selector in self.failed_selectors:
            info = self.failed_selectors[failed_selector]
            alternatives = info.get('working_alternatives', [])

            # Prefer alternatives from same site
            if site:
                site_specific = [a for a in alternatives if a.get('site') == site]
                if site_specific:
                    return site_specific[0]['selector']

            # Return any working alternative
            if alternatives:
                return alternatives[0]['selector']

        # Generic fallback suggestions
        fallbacks = self._get_generic_fallback(failed_selector)
        return fallbacks[0] if fallbacks else None

    def _get_generic_fallback(self, selector: str) -> List[str]:
        """Generate generic fallback selectors."""
        fallbacks = []

        # If it's a class selector, try data-testid
        if selector.startswith('.'):
            class_name = selector[1:].split()[0]
            fallbacks.append(f'[data-testid*="{class_name}"]')
            fallbacks.append(f'[class*="{class_name}"]')

        # If it's an ID, try various patterns
        if selector.startswith('#'):
            id_name = selector[1:]
            fallbacks.append(f'[data-testid="{id_name}"]')
            fallbacks.append(f'[id="{id_name}"]')

        return fallbacks

    def format_for_prompt(self, elements: List[ExtractedElement], max_items: int = 20) -> str:
        """
        Format extracted elements for injection into LLM prompt.

        This forces the agent to pick from real selectors.
        """
        if not elements:
            return "No valid selectors found on page. Use generic text-based selection."

        lines = ["AVAILABLE SELECTORS (use these ONLY, do not invent selectors):"]

        for i, elem in enumerate(elements[:max_items]):
            text_preview = elem.text[:30] if elem.text else ""
            lines.append(f"  [{i+1}] {elem.selector}")
            if text_preview:
                lines.append(f"      text: \"{text_preview}\"")

        lines.append("")
        lines.append("FORBIDDEN: Do not use .storylink, .thing, .ads-table or other")
        lines.append("           selectors from your training data. Use ONLY the list above.")

        return "\n".join(lines)

    def _load_failed_selectors(self):
        """Load failed selector memory from disk."""
        from pathlib import Path
        path = Path("workspace/failed_selectors.json")

        if path.exists():
            try:
                with open(path) as f:
                    self.failed_selectors = json.load(f)
            except Exception:
                pass

    def _save_failed_selectors(self):
        """Save failed selector memory to disk."""
        from pathlib import Path
        path = Path("workspace/failed_selectors.json")
        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(path, 'w') as f:
                json.dump(self.failed_selectors, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save failed selectors: {e}")

    def get_stats(self) -> Dict:
        """Get selector learning stats."""
        return {
            'known_dead_selectors': len(self.KNOWN_DEAD_SELECTORS),
            'learned_failures': len(self.failed_selectors),
            'total_failure_count': sum(
                info.get('failure_count', 0)
                for info in self.failed_selectors.values()
            )
        }


# Singleton
_extractor = None

def get_selector_extractor() -> SelectorExtractor:
    """Get global selector extractor instance."""
    global _extractor
    if _extractor is None:
        _extractor = SelectorExtractor()
    return _extractor
