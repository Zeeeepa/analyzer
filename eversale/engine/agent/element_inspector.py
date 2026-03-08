"""
Element Inspector - Deep Analysis of DOM Elements

Provides detailed information about elements:
1. All attributes and computed styles
2. Accessibility properties
3. Event listeners
4. Parent/child relationships
5. Visibility and interactability status

Used to:
- Generate robust selectors
- Understand why interactions fail
- Detect dynamic elements
"""

import asyncio
import re
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
from enum import Enum
from loguru import logger


class SelectorStrategy(Enum):
    """Different selector strategies, ordered by preference."""
    ID = "id"
    ARIA_LABEL = "aria-label"
    DATA_TESTID = "data-testid"
    TEXT_CONTENT = "text-content"
    CLASS = "class"
    TAG_STRUCTURE = "tag-structure"
    XPATH = "xpath"


@dataclass
class ElementSnapshot:
    """Comprehensive snapshot of a DOM element's state."""

    # Basic info
    tag_name: str
    id: Optional[str] = None
    classes: List[str] = field(default_factory=list)
    attributes: Dict[str, str] = field(default_factory=dict)

    # Text content
    inner_text: str = ""
    text_content: str = ""
    value: Optional[str] = None  # For inputs
    placeholder: Optional[str] = None

    # Position and size
    bounding_box: Dict[str, float] = field(default_factory=dict)  # x, y, width, height
    is_in_viewport: bool = False

    # Visibility
    is_visible: bool = False
    is_displayed: bool = False  # Not display:none
    opacity: float = 1.0

    # Interactability
    is_enabled: bool = True
    is_readonly: bool = False
    accepts_pointer: bool = True
    is_focusable: bool = False
    is_editable: bool = False

    # Accessibility
    role: Optional[str] = None
    aria_label: Optional[str] = None
    aria_describedby: Optional[str] = None
    aria_disabled: Optional[str] = None
    tabindex: Optional[int] = None

    # Hierarchy
    parent_tag: str = ""
    child_count: int = 0
    sibling_index: int = 0

    # Computed styles
    z_index: str = "auto"
    position: str = "static"  # static, relative, absolute, fixed
    overflow: str = "visible"
    display: str = "block"

    # Framework hints
    has_react_fiber: bool = False
    has_vue_instance: bool = False
    has_angular_scope: bool = False

    # Event listeners (if available via CDP)
    event_listeners: List[str] = field(default_factory=list)

    # Stability indicators
    has_stable_id: bool = False
    has_stable_classes: bool = False
    likely_dynamic: bool = False


@dataclass
class SelectorQualityReport:
    """Analysis of selector quality and recommendations."""
    recommended_selector: str
    confidence: float  # 0.0 to 1.0
    strategy: SelectorStrategy
    alternatives: List[Tuple[str, float, SelectorStrategy]] = field(default_factory=list)  # (selector, confidence, strategy)
    warnings: List[str] = field(default_factory=list)
    stability_score: float = 0.0  # How likely selector is to remain valid


@dataclass
class DynamicAnalysis:
    """Analysis of element dynamism over time."""
    is_dynamic: bool
    change_frequency: str  # "stable", "occasional", "frequent"
    changed_attributes: List[str] = field(default_factory=list)
    recommended_stable_selector: Optional[str] = None
    observation_count: int = 0
    observation_duration: float = 0.0  # seconds


class ElementInspector:
    """
    Deep analysis of DOM elements for robust automation.

    Provides comprehensive element information that enables:
    - Smart selector generation
    - Interaction failure diagnosis
    - Dynamic element detection
    - Accessibility-first targeting
    """

    # Patterns that indicate unstable IDs/classes
    UNSTABLE_ID_PATTERNS = [
        r'.*-\d{10,}$',  # Timestamps: button-1638234567890
        r'.*-[0-9a-f]{8,}$',  # Hash suffixes: element-a1b2c3d4
        r'^[0-9a-f]{8}-[0-9a-f]{4}',  # UUIDs
        r'.*-\d+$',  # Sequential IDs that may change
    ]

    UNSTABLE_CLASS_PATTERNS = [
        r'^css-[0-9a-z]+$',  # CSS-in-JS: css-1dbjc4n
        r'^_[0-9a-z]+$',  # Module CSS: _3a4bc
        r'.*-[0-9a-f]{5,}$',  # Hash suffixes
    ]

    # Framework detection patterns
    REACT_KEYS = ['__reactFiber$', '__reactProps$', '_reactRootContainer']
    VUE_KEYS = ['__vue__', '__v_']
    ANGULAR_KEYS = ['__ngContext__', 'ng-']

    def __init__(self, page):
        """Initialize inspector with Playwright page."""
        self.page = page

    async def inspect_element(self, selector: str) -> Optional[ElementSnapshot]:
        """
        Get comprehensive element information.

        Args:
            selector: CSS selector for the element

        Returns:
            ElementSnapshot or None if element not found
        """
        try:
            # Use Playwright's evaluate to extract all info in one go
            snapshot_data = await self.page.evaluate('''
                (selector) => {
                    const el = document.querySelector(selector);
                    if (!el) return null;

                    const rect = el.getBoundingClientRect();
                    const style = getComputedStyle(el);
                    const parent = el.parentElement;

                    // Check visibility
                    const isVisible = rect.width > 0 && rect.height > 0 &&
                                     style.visibility !== 'hidden' &&
                                     style.opacity !== '0';

                    // Check if in viewport
                    const inViewport = rect.top >= 0 && rect.left >= 0 &&
                                      rect.bottom <= window.innerHeight &&
                                      rect.right <= window.innerWidth;

                    // Extract all attributes
                    const attributes = {};
                    for (const attr of el.attributes) {
                        attributes[attr.name] = attr.value;
                    }

                    // Check framework instances
                    const hasReact = Object.keys(el).some(k => k.startsWith('__react'));
                    const hasVue = '__vue__' in el || '__v_skip' in el;
                    const hasAngular = '__ngContext__' in el;

                    // Get ARIA attributes
                    const ariaLabel = el.getAttribute('aria-label');
                    const ariaDescribedby = el.getAttribute('aria-describedby');
                    const ariaDisabled = el.getAttribute('aria-disabled');
                    const role = el.getAttribute('role') || el.role;

                    // Check focusability
                    const tabindex = el.tabIndex;
                    const isFocusable = tabindex >= 0 ||
                                       ['A', 'BUTTON', 'INPUT', 'SELECT', 'TEXTAREA'].includes(el.tagName);

                    // Check editability
                    const isEditable = el.isContentEditable ||
                                      (el.tagName === 'INPUT' && !el.readOnly) ||
                                      (el.tagName === 'TEXTAREA' && !el.readOnly);

                    // Get sibling index
                    const siblings = parent ? Array.from(parent.children) : [el];
                    const siblingIndex = siblings.indexOf(el);

                    return {
                        tag_name: el.tagName.toLowerCase(),
                        id: el.id || null,
                        classes: Array.from(el.classList),
                        attributes: attributes,

                        inner_text: el.innerText?.slice(0, 500) || '',
                        text_content: el.textContent?.slice(0, 500) || '',
                        value: el.value || null,
                        placeholder: el.placeholder || null,

                        bounding_box: {
                            x: rect.x,
                            y: rect.y,
                            width: rect.width,
                            height: rect.height,
                            top: rect.top,
                            left: rect.left,
                            bottom: rect.bottom,
                            right: rect.right
                        },
                        is_in_viewport: inViewport,

                        is_visible: isVisible,
                        is_displayed: style.display !== 'none',
                        opacity: parseFloat(style.opacity),

                        is_enabled: !el.disabled,
                        is_readonly: el.readOnly || false,
                        accepts_pointer: style.pointerEvents !== 'none',
                        is_focusable: isFocusable,
                        is_editable: isEditable,

                        role: role,
                        aria_label: ariaLabel,
                        aria_describedby: ariaDescribedby,
                        aria_disabled: ariaDisabled,
                        tabindex: tabindex >= 0 ? tabindex : null,

                        parent_tag: parent ? parent.tagName.toLowerCase() : '',
                        child_count: el.children.length,
                        sibling_index: siblingIndex,

                        z_index: style.zIndex,
                        position: style.position,
                        overflow: style.overflow,
                        display: style.display,

                        has_react_fiber: hasReact,
                        has_vue_instance: hasVue,
                        has_angular_scope: hasAngular
                    };
                }
            ''', selector)

            if not snapshot_data:
                logger.debug(f"Element not found: {selector}")
                return None

            # Convert to ElementSnapshot dataclass
            snapshot = ElementSnapshot(**snapshot_data)

            # Add stability analysis
            snapshot.has_stable_id = self._is_stable_id(snapshot.id) if snapshot.id else False
            snapshot.has_stable_classes = self._has_stable_classes(snapshot.classes)
            snapshot.likely_dynamic = snapshot.has_react_fiber or snapshot.has_vue_instance

            # Try to get event listeners (requires CDP)
            try:
                snapshot.event_listeners = await self._get_event_listeners(selector)
            except Exception:
                pass  # CDP may not be available

            return snapshot

        except Exception as e:
            logger.warning(f"Failed to inspect element {selector}: {e}")
            return None

    async def analyze_selector_quality(self, snapshot: ElementSnapshot) -> SelectorQualityReport:
        """
        Analyze which selector strategies would work best for this element.

        Args:
            snapshot: Element snapshot to analyze

        Returns:
            SelectorQualityReport with recommendations
        """
        candidates = []
        warnings = []

        # Strategy 1: ID selector
        if snapshot.id:
            if snapshot.has_stable_id:
                selector = f"#{snapshot.id}"
                confidence = 0.95
                candidates.append((selector, confidence, SelectorStrategy.ID))
            else:
                warnings.append(f"ID '{snapshot.id}' looks dynamically generated")
                selector = f"#{snapshot.id}"
                confidence = 0.5
                candidates.append((selector, confidence, SelectorStrategy.ID))

        # Strategy 2: ARIA label (very stable)
        if snapshot.aria_label:
            selector = f'[aria-label="{snapshot.aria_label}"]'
            confidence = 0.9
            candidates.append((selector, confidence, SelectorStrategy.ARIA_LABEL))

        # Strategy 3: data-testid (if present)
        if 'data-testid' in snapshot.attributes:
            testid = snapshot.attributes['data-testid']
            selector = f'[data-testid="{testid}"]'
            confidence = 0.85
            candidates.append((selector, confidence, SelectorStrategy.DATA_TESTID))

        # Strategy 4: Text content (for buttons/links)
        if snapshot.tag_name in ['button', 'a'] and snapshot.inner_text:
            text = snapshot.inner_text.strip()[:50]
            if len(text) > 2:
                selector = f'{snapshot.tag_name}:has-text("{text}")'
                confidence = 0.75
                candidates.append((selector, confidence, SelectorStrategy.TEXT_CONTENT))

        # Strategy 5: Stable classes
        if snapshot.has_stable_classes:
            stable_classes = [c for c in snapshot.classes if self._is_stable_class(c)]
            if stable_classes:
                class_selector = '.' + '.'.join(stable_classes[:3])
                selector = f"{snapshot.tag_name}{class_selector}"
                confidence = 0.7
                candidates.append((selector, confidence, SelectorStrategy.CLASS))
        else:
            if snapshot.classes:
                warnings.append("Classes appear to be CSS-in-JS or dynamically generated")

        # Strategy 6: Structural selector (parent + child position)
        if snapshot.parent_tag and snapshot.sibling_index >= 0:
            selector = f"{snapshot.parent_tag} > {snapshot.tag_name}:nth-child({snapshot.sibling_index + 1})"
            confidence = 0.6
            candidates.append((selector, confidence, SelectorStrategy.TAG_STRUCTURE))

        # Strategy 7: XPath with text (fallback)
        if snapshot.inner_text:
            text = snapshot.inner_text.strip()[:50]
            selector = f"//{snapshot.tag_name}[contains(text(), '{text}')]"
            confidence = 0.5
            candidates.append((selector, confidence, SelectorStrategy.XPATH))

        # Sort by confidence
        candidates.sort(key=lambda x: x[1], reverse=True)

        if not candidates:
            # Absolute fallback: tag name only
            candidates.append((snapshot.tag_name, 0.3, SelectorStrategy.TAG_STRUCTURE))
            warnings.append("No good selector found - element is very generic")

        # Calculate overall stability score
        stability_score = self._calculate_stability_score(snapshot)

        # Build report
        best_selector, best_confidence, best_strategy = candidates[0]
        alternatives = candidates[1:5]  # Top 5 alternatives

        return SelectorQualityReport(
            recommended_selector=best_selector,
            confidence=best_confidence,
            strategy=best_strategy,
            alternatives=alternatives,
            warnings=warnings,
            stability_score=stability_score
        )

    async def is_element_dynamic(
        self,
        selector: str,
        observation_duration: float = 2.0,
        observation_interval: float = 0.4
    ) -> DynamicAnalysis:
        """
        Check if element changes over time (React re-renders, etc.).

        Args:
            selector: CSS selector for element
            observation_duration: How long to observe (seconds)
            observation_interval: Time between snapshots (seconds)

        Returns:
            DynamicAnalysis report
        """
        snapshots = []
        observation_count = int(observation_duration / observation_interval)

        try:
            for _ in range(observation_count):
                snapshot = await self.inspect_element(selector)
                if snapshot:
                    snapshots.append(snapshot)
                await asyncio.sleep(observation_interval)

            if len(snapshots) < 2:
                return DynamicAnalysis(
                    is_dynamic=False,
                    change_frequency="unknown",
                    observation_count=len(snapshots),
                    observation_duration=observation_duration
                )

            # Compare snapshots to find changes
            changed_attrs = set()
            change_count = 0

            for i in range(1, len(snapshots)):
                prev = snapshots[i-1]
                curr = snapshots[i]

                # Check which attributes changed
                if prev.classes != curr.classes:
                    changed_attrs.add('classes')
                    change_count += 1

                if prev.attributes != curr.attributes:
                    changed_attrs.add('attributes')
                    change_count += 1

                if prev.inner_text != curr.inner_text:
                    changed_attrs.add('inner_text')
                    change_count += 1

                if prev.value != curr.value:
                    changed_attrs.add('value')
                    change_count += 1

                if prev.bounding_box != curr.bounding_box:
                    changed_attrs.add('position')
                    change_count += 1

            # Classify frequency
            change_rate = change_count / len(snapshots)
            if change_rate == 0:
                frequency = "stable"
            elif change_rate < 0.3:
                frequency = "occasional"
            else:
                frequency = "frequent"

            is_dynamic = change_count > 0

            # Generate stable selector recommendation
            stable_selector = None
            if is_dynamic and snapshots:
                # Prefer selectors based on stable attributes
                quality = await self.analyze_selector_quality(snapshots[0])
                # Filter for selectors that don't use changed attributes
                for alt_selector, confidence, strategy in quality.alternatives:
                    if strategy in [SelectorStrategy.ARIA_LABEL, SelectorStrategy.DATA_TESTID]:
                        stable_selector = alt_selector
                        break

                if not stable_selector:
                    stable_selector = quality.recommended_selector

            return DynamicAnalysis(
                is_dynamic=is_dynamic,
                change_frequency=frequency,
                changed_attributes=list(changed_attrs),
                recommended_stable_selector=stable_selector,
                observation_count=len(snapshots),
                observation_duration=observation_duration
            )

        except Exception as e:
            logger.warning(f"Dynamic analysis failed for {selector}: {e}")
            return DynamicAnalysis(
                is_dynamic=False,
                change_frequency="unknown",
                observation_count=0,
                observation_duration=observation_duration
            )

    async def get_element_ancestry(
        self,
        selector: str,
        depth: int = 5
    ) -> List[ElementSnapshot]:
        """
        Get parent elements up to specified depth.

        Args:
            selector: CSS selector for starting element
            depth: How many levels to traverse up

        Returns:
            List of ElementSnapshots from element to ancestors
        """
        ancestry = []

        try:
            # Get all ancestors in one evaluation
            ancestors_data = await self.page.evaluate('''
                (selector, depth) => {
                    let el = document.querySelector(selector);
                    if (!el) return [];

                    const ancestors = [];
                    let current = el;

                    for (let i = 0; i < depth && current; i++) {
                        const parent = current.parentElement;
                        if (!parent) break;

                        const rect = parent.getBoundingClientRect();
                        const style = getComputedStyle(parent);

                        ancestors.push({
                            tag_name: parent.tagName.toLowerCase(),
                            id: parent.id || null,
                            classes: Array.from(parent.classList),
                            inner_text: parent.innerText?.slice(0, 100) || '',
                            child_count: parent.children.length,
                            position: style.position,
                            display: style.display
                        });

                        current = parent;
                    }

                    return ancestors;
                }
            ''', selector, depth)

            # Convert to ElementSnapshot objects (partial)
            for data in ancestors_data:
                # Create minimal snapshot for ancestry
                snapshot = ElementSnapshot(
                    tag_name=data['tag_name'],
                    id=data.get('id'),
                    classes=data.get('classes', []),
                    inner_text=data.get('inner_text', ''),
                    child_count=data.get('child_count', 0),
                    position=data.get('position', 'static'),
                    display=data.get('display', 'block')
                )
                ancestry.append(snapshot)

            return ancestry

        except Exception as e:
            logger.warning(f"Failed to get ancestry for {selector}: {e}")
            return []

    async def get_similar_siblings(self, selector: str) -> List[ElementSnapshot]:
        """
        Find sibling elements with similar structure.

        Args:
            selector: CSS selector for reference element

        Returns:
            List of similar sibling snapshots
        """
        try:
            siblings_data = await self.page.evaluate('''
                (selector) => {
                    const el = document.querySelector(selector);
                    if (!el || !el.parentElement) return [];

                    const parent = el.parentElement;
                    const refTagName = el.tagName;
                    const refClasses = Array.from(el.classList);

                    // Find siblings with same tag and overlapping classes
                    const siblings = Array.from(parent.children)
                        .filter(sib => {
                            if (sib === el) return false;
                            if (sib.tagName !== refTagName) return false;

                            // Check class overlap
                            const sibClasses = Array.from(sib.classList);
                            const overlap = refClasses.filter(c => sibClasses.includes(c));
                            return overlap.length > 0;
                        })
                        .map((sib, idx) => {
                            const rect = sib.getBoundingClientRect();
                            return {
                                tag_name: sib.tagName.toLowerCase(),
                                id: sib.id || null,
                                classes: Array.from(sib.classList),
                                inner_text: sib.innerText?.slice(0, 100) || '',
                                bounding_box: {
                                    x: rect.x,
                                    y: rect.y,
                                    width: rect.width,
                                    height: rect.height
                                },
                                sibling_index: idx
                            };
                        });

                    return siblings;
                }
            ''', selector)

            # Convert to ElementSnapshot objects
            siblings = []
            for data in siblings_data:
                snapshot = ElementSnapshot(
                    tag_name=data['tag_name'],
                    id=data.get('id'),
                    classes=data.get('classes', []),
                    inner_text=data.get('inner_text', ''),
                    bounding_box=data.get('bounding_box', {}),
                    sibling_index=data.get('sibling_index', 0)
                )
                siblings.append(snapshot)

            return siblings

        except Exception as e:
            logger.warning(f"Failed to get siblings for {selector}: {e}")
            return []

    async def diagnose_interaction_failure(
        self,
        selector: str
    ) -> Dict[str, Any]:
        """
        Diagnose why an interaction with an element might fail.

        Args:
            selector: CSS selector that failed

        Returns:
            Dict with diagnosis information
        """
        snapshot = await self.inspect_element(selector)

        if not snapshot:
            return {
                'found': False,
                'reason': 'Element not found in DOM',
                'suggestions': [
                    'Check if selector is correct',
                    'Wait for element to load',
                    'Check if element is in iframe'
                ]
            }

        issues = []
        suggestions = []

        # Check visibility
        if not snapshot.is_visible:
            issues.append('Element is not visible')
            suggestions.append('Wait for element to become visible')

            if not snapshot.is_displayed:
                suggestions.append('Element has display:none - may need to trigger visibility')

            if snapshot.opacity < 0.1:
                suggestions.append('Element has very low opacity')

        # Check if in viewport
        if not snapshot.is_in_viewport:
            issues.append('Element is outside viewport')
            suggestions.append('Scroll element into view before interacting')

        # Check interactability
        if not snapshot.is_enabled:
            issues.append('Element is disabled')
            suggestions.append('Wait for element to be enabled or check form validation')

        if snapshot.is_readonly:
            issues.append('Element is read-only')
            suggestions.append('This element cannot be edited')

        if not snapshot.accepts_pointer:
            issues.append('Element has pointer-events:none')
            suggestions.append('Element is not clickable - may be overlaid')

        # Check if covered by other elements
        if snapshot.z_index != 'auto':
            suggestions.append(f'Element has z-index {snapshot.z_index} - check for overlays')

        # Check stability
        quality = await self.analyze_selector_quality(snapshot)
        if quality.confidence < 0.7:
            issues.append('Selector may be unstable')
            suggestions.append(f'Consider using: {quality.recommended_selector}')

        # Dynamic element check
        if snapshot.likely_dynamic:
            issues.append('Element appears to be dynamically rendered (React/Vue)')
            suggestions.append('Wait for rendering to complete or use aria-label selectors')

        return {
            'found': True,
            'is_interactable': len(issues) == 0,
            'issues': issues,
            'suggestions': suggestions,
            'snapshot': snapshot,
            'quality_report': quality
        }

    async def _get_event_listeners(self, selector: str) -> List[str]:
        """
        Get event listeners attached to element (requires CDP).

        Args:
            selector: CSS selector

        Returns:
            List of event types (e.g., ['click', 'mousedown'])
        """
        try:
            # This requires Chrome DevTools Protocol
            # For now, return empty list - can be enhanced later
            return []
        except Exception:
            return []

    def _is_stable_id(self, element_id: str) -> bool:
        """Check if ID looks stable (not dynamically generated)."""
        if not element_id:
            return False

        for pattern in self.UNSTABLE_ID_PATTERNS:
            if re.match(pattern, element_id):
                return False

        return True

    def _is_stable_class(self, class_name: str) -> bool:
        """Check if class name looks stable."""
        if not class_name:
            return False

        for pattern in self.UNSTABLE_CLASS_PATTERNS:
            if re.match(pattern, class_name):
                return False

        return True

    def _has_stable_classes(self, classes: List[str]) -> bool:
        """Check if element has any stable classes."""
        return any(self._is_stable_class(c) for c in classes)

    def _calculate_stability_score(self, snapshot: ElementSnapshot) -> float:
        """
        Calculate overall stability score for element.

        Returns:
            Score from 0.0 (very unstable) to 1.0 (very stable)
        """
        score = 0.0
        factors = 0

        # ID stability
        if snapshot.id:
            factors += 1
            if snapshot.has_stable_id:
                score += 0.3

        # ARIA attributes (very stable)
        if snapshot.aria_label:
            score += 0.3
            factors += 1

        if snapshot.role:
            score += 0.1
            factors += 1

        # data-testid
        if 'data-testid' in snapshot.attributes:
            score += 0.25
            factors += 1

        # Class stability
        if snapshot.classes:
            factors += 1
            if snapshot.has_stable_classes:
                score += 0.2

        # Framework hints (slightly reduces stability)
        if snapshot.has_react_fiber or snapshot.has_vue_instance:
            score -= 0.1
            factors += 1

        # Normalize
        if factors > 0:
            return max(0.0, min(1.0, score / factors))

        return 0.5  # Default middle score


async def inspect_and_report(page, selector: str) -> None:
    """
    Convenience function to inspect element and print detailed report.

    Args:
        page: Playwright page
        selector: CSS selector to inspect
    """
    inspector = ElementInspector(page)

    logger.info(f"Inspecting element: {selector}")

    # Get snapshot
    snapshot = await inspector.inspect_element(selector)
    if not snapshot:
        logger.error(f"Element not found: {selector}")
        return

    # Analyze selector quality
    quality = await inspector.analyze_selector_quality(snapshot)

    # Check if dynamic
    dynamic = await inspector.is_element_dynamic(selector)

    # Print report
    print("\n" + "="*80)
    print(f"ELEMENT INSPECTION REPORT: {selector}")
    print("="*80)

    print(f"\nBasic Info:")
    print(f"  Tag: <{snapshot.tag_name}>")
    print(f"  ID: {snapshot.id or 'none'}")
    print(f"  Classes: {', '.join(snapshot.classes) if snapshot.classes else 'none'}")
    print(f"  Text: {snapshot.inner_text[:100] if snapshot.inner_text else 'none'}")

    print(f"\nVisibility:")
    print(f"  Visible: {snapshot.is_visible}")
    print(f"  In Viewport: {snapshot.is_in_viewport}")
    print(f"  Opacity: {snapshot.opacity}")

    print(f"\nInteractability:")
    print(f"  Enabled: {snapshot.is_enabled}")
    print(f"  Focusable: {snapshot.is_focusable}")
    print(f"  Editable: {snapshot.is_editable}")

    print(f"\nAccessibility:")
    print(f"  Role: {snapshot.role or 'none'}")
    print(f"  ARIA Label: {snapshot.aria_label or 'none'}")

    print(f"\nSelector Quality:")
    print(f"  Recommended: {quality.recommended_selector}")
    print(f"  Confidence: {quality.confidence:.0%}")
    print(f"  Strategy: {quality.strategy.value}")
    print(f"  Stability Score: {quality.stability_score:.0%}")

    if quality.warnings:
        print(f"\n  Warnings:")
        for warning in quality.warnings:
            print(f"    - {warning}")

    if quality.alternatives:
        print(f"\n  Alternatives:")
        for alt_selector, confidence, strategy in quality.alternatives[:3]:
            print(f"    - {alt_selector} ({confidence:.0%}, {strategy.value})")

    print(f"\nDynamic Analysis:")
    print(f"  Is Dynamic: {dynamic.is_dynamic}")
    print(f"  Change Frequency: {dynamic.change_frequency}")
    if dynamic.changed_attributes:
        print(f"  Changed Attributes: {', '.join(dynamic.changed_attributes)}")

    print(f"\nFramework Hints:")
    if snapshot.has_react_fiber:
        print(f"  - React component detected")
    if snapshot.has_vue_instance:
        print(f"  - Vue component detected")
    if snapshot.has_angular_scope:
        print(f"  - Angular component detected")

    print("\n" + "="*80)


# Integration with visual_targeting.py
def enhance_visual_targeting_with_inspection(targeting_result, snapshot: ElementSnapshot) -> Dict[str, Any]:
    """
    Enhance visual targeting results with element inspection data.

    Args:
        targeting_result: TargetingResult from visual_targeting
        snapshot: ElementSnapshot from inspection

    Returns:
        Enhanced result dict
    """
    return {
        'visual_coordinates': targeting_result.coordinates,
        'visual_confidence': targeting_result.confidence,
        'element_id': snapshot.id,
        'element_classes': snapshot.classes,
        'aria_label': snapshot.aria_label,
        'is_interactable': snapshot.is_enabled and snapshot.accepts_pointer,
        'stability_score': snapshot.has_stable_id or snapshot.aria_label is not None,
        'recommended_selector': None,  # Will be filled by analyze_selector_quality
    }
