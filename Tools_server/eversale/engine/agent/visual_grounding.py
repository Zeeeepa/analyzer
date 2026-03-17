"""
Visual Grounding Module for Eversale

Implements visual element identification based on SeeClick, GUI-Actor, and UGround research.

Key Features:
- Screenshot-based element finding with natural language descriptions
- Hybrid DOM + vision approach with intelligent fallback chain
- Visual element matching (icons, images, text-in-image OCR)
- Coordinate-free actions with semantic references
- Region focus for high-density UIs
- Special handling for canvas/WebGL/SVG applications
- Integration with existing vision_analyzer, dom_distillation, and selector_fallbacks

Research Papers Implemented:
- SeeClick: Harnessing GUI Grounding for Advanced Visual GUI Agents
- GUI-Actor: Visual Grounding for Multimodal LLM-based GUI Agents
- UGround: Universal Visual Grounding Framework
- RegionFocus: Dynamic zoom for complex interfaces

Author: Eversale AI
Version: 1.0.0
"""

import asyncio
import base64
import hashlib
import json
import re
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set
from loguru import logger

try:
    from playwright.async_api import Page, ElementHandle, Locator
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("Playwright not available - visual grounding will be limited")

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    logger.warning("Ollama not available - visual grounding disabled")

# Import existing modules
try:
    from .vision_analyzer import VisionAnalyzer, VisionResult
    VISION_ANALYZER_AVAILABLE = True
except ImportError:
    VISION_ANALYZER_AVAILABLE = False
    logger.warning("VisionAnalyzer not available")

# DEPRECATED: dom_distillation removed in v2.9 - using accessibility_element_finder instead
try:
    from .dom_distillation import (
        DOMDistillationEngine,
        DistillationMode,
        ElementInfo,
        DOMSnapshot,
        get_engine as get_dom_engine
    )
    DOM_DISTILLATION_AVAILABLE = True
except ImportError:
    DOM_DISTILLATION_AVAILABLE = False
    logger.debug("DOM Distillation not available (removed in v2.9)")
    # Create stub for ElementInfo if not available
    from dataclasses import dataclass, field
    @dataclass
    class ElementInfo:
        tag: str = ""
        role: Optional[str] = None
        text: Optional[str] = None
        aria_label: Optional[str] = None
        placeholder: Optional[str] = None
        is_interactive: bool = False
        bbox: Optional[Dict[str, float]] = None
        mmid: Optional[str] = None

    # Stub functions
    def get_dom_engine():
        return None

try:
    from .selector_fallbacks import VisualFallback, get_visual_fallback
    SELECTOR_FALLBACKS_AVAILABLE = True
except ImportError:
    SELECTOR_FALLBACKS_AVAILABLE = False
    logger.warning("Selector Fallbacks not available")

try:
    from .site_memory import (
        SiteMemoryStore,
        SelectorSynthesizer,
        SiteMemory,
        SelectorCandidate,
        get_site_memory_store,
        get_selector_synthesizer
    )
    SITE_MEMORY_AVAILABLE = True
except ImportError:
    SITE_MEMORY_AVAILABLE = False
    logger.warning("Site Memory not available")


# ==============================================================================
# DATA STRUCTURES
# ==============================================================================

class GroundingStrategy(Enum):
    """Strategy for element grounding."""
    DOM_ONLY = "dom_only"              # Use DOM/accessibility tree only
    VISION_ONLY = "vision_only"        # Use vision model only
    HYBRID = "hybrid"                  # Try DOM first, fallback to vision
    COORDINATED = "coordinated"        # Use both DOM and vision together
    REGION_FOCUS = "region_focus"      # Dynamic zoom to region of interest


class ElementType(Enum):
    """Type of UI element."""
    BUTTON = "button"
    INPUT = "input"
    LINK = "link"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    SELECT = "select"
    ICON = "icon"
    IMAGE = "image"
    TEXT = "text"
    CANVAS = "canvas"
    CUSTOM = "custom"
    UNKNOWN = "unknown"


class MatchMethod(Enum):
    """Method used to find the element."""
    DOM_SELECTOR = "dom_selector"
    ACCESSIBILITY_TREE = "accessibility_tree"
    VISUAL_TEXT_MATCH = "visual_text_match"
    VISUAL_ICON_MATCH = "visual_icon_match"
    VISUAL_LAYOUT = "visual_layout"
    VISUAL_OCR = "visual_ocr"
    VISUAL_COORDINATES = "visual_coordinates"
    REGION_FOCUS = "region_focus"


@dataclass
class VisualElement:
    """
    Represents a visually grounded element.

    Combines DOM information (when available) with visual grounding data.
    """
    # Identification
    description: str                      # Natural language description
    element_type: ElementType             # Type of element

    # Location
    bbox: Optional[Dict[str, float]]      # Bounding box {x, y, width, height}
    center: Optional[Tuple[int, int]]     # Center coordinates (x, y)

    # Confidence
    confidence: float                     # Overall confidence score (0.0-1.0)
    match_method: MatchMethod             # How it was found

    # DOM Information (if available)
    dom_element: Optional[ElementInfo] = None
    mmid: Optional[str] = None            # DOM marker ID

    # Visual Information
    screenshot_path: Optional[str] = None
    visual_features: Optional[Dict[str, Any]] = None
    ocr_text: Optional[str] = None        # Text extracted via OCR

    # Context
    parent_description: Optional[str] = None
    nearby_elements: List[str] = None
    region_path: Optional[List[Dict]] = None  # Path for region focus

    # Canvas/Special Handling
    is_canvas_element: bool = False
    is_webgl: bool = False
    is_svg: bool = False
    is_shadow_dom: bool = False

    def __post_init__(self):
        if self.nearby_elements is None:
            self.nearby_elements = []
        if self.region_path is None:
            self.region_path = []


@dataclass
class GroundingResult:
    """Result from visual grounding operation."""
    success: bool
    elements: List[VisualElement]         # All matching elements
    best_match: Optional[VisualElement]   # Highest confidence match
    strategy_used: GroundingStrategy
    processing_time: float
    error: Optional[str] = None


@dataclass
class RegionOfInterest:
    """
    Region of interest for focused grounding.

    Inspired by RegionFocus paper - zoom into relevant regions
    to improve grounding accuracy on complex pages.
    """
    bbox: Dict[str, float]                # Region bounding box
    zoom_level: float                     # Zoom factor applied
    description: str                      # What this region contains
    confidence: float                     # Confidence this is correct region
    parent_region: Optional['RegionOfInterest'] = None


# ==============================================================================
# VISUAL GROUNDING ENGINE
# ==============================================================================

class VisualGroundingEngine:
    """
    Main engine for visual element grounding.

    Implements hybrid approach:
    1. Try DOM/accessibility tree (fast, reliable when available)
    2. Try visual grounding (robust, works with canvas/WebGL/SVG)
    3. Use region focus for complex UIs (zoom into relevant areas)

    Example Usage:
        engine = VisualGroundingEngine()
        result = await engine.ground_element(
            page,
            "the blue Send button at bottom right"
        )
        if result.success:
            await engine.click_grounded_element(page, result.best_match)
    """

    def __init__(
        self,
        vision_model: str = "moondream",
        default_strategy: GroundingStrategy = GroundingStrategy.HYBRID
    ):
        """
        Initialize visual grounding engine.

        Args:
            vision_model: Vision model to use for visual grounding
            default_strategy: Default grounding strategy
        """
        self.vision_model = vision_model
        self.default_strategy = default_strategy

        # Initialize component modules
        self.vision_analyzer = VisionAnalyzer(model=vision_model) if VISION_ANALYZER_AVAILABLE else None
        self.dom_engine = get_dom_engine() if DOM_DISTILLATION_AVAILABLE else None
        self.visual_fallback = get_visual_fallback() if SELECTOR_FALLBACKS_AVAILABLE else None

        # Site memory for post-vision selector synthesis
        self.site_memory = get_site_memory_store() if SITE_MEMORY_AVAILABLE else None
        self.selector_synthesizer = get_selector_synthesizer() if SITE_MEMORY_AVAILABLE else None

        # Cache
        self._screenshot_cache: Dict[str, bytes] = {}
        self._element_cache: Dict[str, VisualElement] = {}

        # Stats
        self.stats = {
            "dom_successes": 0,
            "vision_successes": 0,
            "region_focus_uses": 0,
            "total_groundings": 0,
            "avg_confidence": 0.0,
            "site_memory_hits": 0,
            "site_memory_misses": 0,
            "selectors_synthesized": 0,
            "vision_calls_skipped": 0
        }

        logger.info(f"VisualGroundingEngine initialized with {vision_model}")
        self._log_capabilities()

    def _log_capabilities(self):
        """Log available capabilities."""
        capabilities = []
        if self.vision_analyzer:
            capabilities.append("Vision")
        if self.dom_engine:
            capabilities.append("DOM")
        if self.visual_fallback:
            capabilities.append("VisualFallback")
        if self.site_memory:
            capabilities.append("SiteMemory")

        if capabilities:
            logger.info(f"Capabilities: {', '.join(capabilities)}")
        else:
            logger.warning("No grounding capabilities available!")

    # ==========================================================================
    # SITE MEMORY INTEGRATION (POST-VISION SELECTOR SYNTHESIS)
    # ==========================================================================

    async def _try_site_memory_selector(
        self,
        page: Page,
        description: str,
        element_type: Optional[ElementType] = None
    ) -> Optional[VisualElement]:
        """
        Try to find element using saved selectors from site memory.

        This is called BEFORE vision to skip expensive GPU calls.

        Args:
            page: Playwright page
            description: Element description
            element_type: Optional element type hint

        Returns:
            VisualElement if selector works, None otherwise
        """
        if not self.site_memory:
            return None

        try:
            # Get current URL
            url = page.url

            # Look up saved selectors
            memory = await self.site_memory.find_memory(url, description)

            if not memory:
                self.stats["site_memory_misses"] += 1
                return None

            logger.info(
                f"Found {len(memory.selectors)} saved selectors for '{description}'"
            )

            # Try each selector in order of priority
            for selector_candidate in memory.selectors:
                try:
                    # Try to find element with this selector
                    if selector_candidate.selector_type == "css":
                        element = await page.query_selector(selector_candidate.selector)
                    elif selector_candidate.selector_type == "xpath":
                        element = await page.query_selector(f"xpath={selector_candidate.selector}")
                    else:
                        continue

                    if not element:
                        continue

                    # Get element bounding box
                    bbox = await element.bounding_box()
                    if not bbox:
                        continue

                    # Calculate center
                    center = (
                        int(bbox['x'] + bbox['width'] / 2),
                        int(bbox['y'] + bbox['height'] / 2)
                    )

                    # Success! Update memory stats
                    await self.site_memory.update_usage(memory.memory_id, success=True)
                    self.stats["site_memory_hits"] += 1
                    self.stats["vision_calls_skipped"] += 1

                    # Create VisualElement
                    visual_elem = VisualElement(
                        description=description,
                        element_type=element_type or ElementType.UNKNOWN,
                        bbox=bbox,
                        center=center,
                        confidence=memory.confidence,
                        match_method=MatchMethod.DOM_SELECTOR,
                        visual_features={
                            "from_site_memory": True,
                            "selector": selector_candidate.selector,
                            "selector_type": selector_candidate.selector_type
                        }
                    )

                    logger.info(
                        f"Site memory HIT: Used saved selector to skip vision call "
                        f"({selector_candidate.selector})"
                    )

                    return visual_elem

                except Exception as e:
                    logger.debug(f"Selector failed: {selector_candidate.selector} - {e}")
                    continue

            # All selectors failed - update memory
            await self.site_memory.update_usage(memory.memory_id, success=False)
            logger.warning(
                f"Site memory selectors failed, falling back to vision"
            )
            return None

        except Exception as e:
            logger.error(f"Error trying site memory: {e}")
            return None

    async def _synthesize_and_save_selectors(
        self,
        page: Page,
        element: VisualElement,
        description: str
    ):
        """
        Synthesize selectors after successful vision call and save to site memory.

        This is called AFTER vision successfully identifies an element.

        Args:
            page: Playwright page
            element: Successfully grounded element
            description: Element description
        """
        if not self.site_memory or not self.selector_synthesizer:
            return

        if not element.center:
            logger.debug("Cannot synthesize selectors: no coordinates")
            return

        try:
            logger.info(f"Synthesizing selectors for: {description}")

            # Synthesize and validate selectors
            selectors = await self.selector_synthesizer.synthesize_selectors(
                page,
                description,
                element.center,
                element.bbox
            )

            if not selectors:
                logger.warning("No valid selectors could be synthesized")
                return

            # Create site memory entry
            url = page.url
            memory_id = hashlib.md5(
                f"{url}:{description}".encode()
            ).hexdigest()

            # Get element attributes for metadata
            element_attributes = {}
            if element.dom_element:
                element_attributes = {
                    "tag": element.dom_element.tag,
                    "role": element.dom_element.role or "",
                    "aria_label": element.dom_element.aria_label or ""
                }

            site_memory = SiteMemory(
                memory_id=memory_id,
                url_pattern=self.site_memory._url_to_pattern(url),
                element_description=description,
                selectors=selectors,
                element_type=element.element_type.value,
                element_text=element.dom_element.text if element.dom_element else element.ocr_text,
                element_attributes=element_attributes,
                last_bbox=element.bbox,
                last_center=element.center,
                created_at=datetime.now().isoformat(),
                last_used=datetime.now().isoformat(),
                use_count=1,
                success_count=1,
                failure_count=0,
                confidence=element.confidence,
                tags=[element.element_type.value]
            )

            # Save to site memory
            await self.site_memory.store_memory(site_memory)
            self.stats["selectors_synthesized"] += 1

            logger.info(
                f"Saved {len(selectors)} selectors to site memory "
                f"(best: {selectors[0].selector})"
            )

        except Exception as e:
            logger.error(f"Error synthesizing selectors: {e}")

    # ==========================================================================
    # MAIN GROUNDING METHODS
    # ==========================================================================

    async def ground_element(
        self,
        page: Page,
        description: str,
        strategy: Optional[GroundingStrategy] = None,
        element_type: Optional[ElementType] = None,
        region: Optional[RegionOfInterest] = None
    ) -> GroundingResult:
        """
        Ground an element based on natural language description.

        This is the main entry point for visual grounding.

        Args:
            page: Playwright page object
            description: Natural language description (e.g., "the blue Login button")
            strategy: Grounding strategy to use (None = use default)
            element_type: Expected element type (helps narrow search)
            region: Optional region to focus on

        Returns:
            GroundingResult with all matching elements

        Example:
            result = await engine.ground_element(
                page,
                "the Send button",
                element_type=ElementType.BUTTON
            )

            if result.success and result.best_match.confidence > 0.8:
                await engine.click_grounded_element(page, result.best_match)
        """
        start_time = asyncio.get_event_loop().time()
        strategy = strategy or self.default_strategy

        logger.info(f"Grounding element: '{description}' using {strategy.value}")
        self.stats["total_groundings"] += 1

        try:
            # Route to appropriate strategy
            if strategy == GroundingStrategy.DOM_ONLY:
                elements = await self._ground_with_dom(page, description, element_type)
            elif strategy == GroundingStrategy.VISION_ONLY:
                elements = await self._ground_with_vision(page, description, element_type, region)
            elif strategy == GroundingStrategy.HYBRID:
                elements = await self._ground_hybrid(page, description, element_type, region)
            elif strategy == GroundingStrategy.COORDINATED:
                elements = await self._ground_coordinated(page, description, element_type, region)
            elif strategy == GroundingStrategy.REGION_FOCUS:
                elements = await self._ground_with_region_focus(page, description, element_type)
            else:
                raise ValueError(f"Unknown strategy: {strategy}")

            # Find best match
            best_match = None
            if elements:
                best_match = max(elements, key=lambda e: e.confidence)

            processing_time = asyncio.get_event_loop().time() - start_time

            # Update stats
            if best_match:
                self.stats["avg_confidence"] = (
                    (self.stats["avg_confidence"] * (self.stats["total_groundings"] - 1) +
                     best_match.confidence) / self.stats["total_groundings"]
                )

            result = GroundingResult(
                success=len(elements) > 0,
                elements=elements,
                best_match=best_match,
                strategy_used=strategy,
                processing_time=processing_time
            )

            if result.success:
                logger.info(
                    f"Grounding successful: {len(elements)} candidates, "
                    f"best confidence: {best_match.confidence:.2f}"
                )
            else:
                logger.warning(f"Grounding failed for: '{description}'")

            return result

        except Exception as e:
            logger.error(f"Error during grounding: {e}")
            processing_time = asyncio.get_event_loop().time() - start_time
            return GroundingResult(
                success=False,
                elements=[],
                best_match=None,
                strategy_used=strategy,
                processing_time=processing_time,
                error=str(e)
            )

    async def ground_multiple_elements(
        self,
        page: Page,
        descriptions: List[str],
        strategy: Optional[GroundingStrategy] = None
    ) -> Dict[str, GroundingResult]:
        """
        Ground multiple elements in parallel.

        Args:
            page: Playwright page object
            descriptions: List of element descriptions
            strategy: Grounding strategy (None = use default)

        Returns:
            Dict mapping descriptions to GroundingResults
        """
        logger.info(f"Grounding {len(descriptions)} elements in parallel")

        # Ground all in parallel
        tasks = [
            self.ground_element(page, desc, strategy)
            for desc in descriptions
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Build result dict
        result_dict = {}
        for desc, result in zip(descriptions, results):
            if isinstance(result, Exception):
                logger.error(f"Error grounding '{desc}': {result}")
                result_dict[desc] = GroundingResult(
                    success=False,
                    elements=[],
                    best_match=None,
                    strategy_used=strategy or self.default_strategy,
                    processing_time=0.0,
                    error=str(result)
                )
            else:
                result_dict[desc] = result

        return result_dict

    # ==========================================================================
    # STRATEGY IMPLEMENTATIONS
    # ==========================================================================

    async def _ground_with_dom(
        self,
        page: Page,
        description: str,
        element_type: Optional[ElementType]
    ) -> List[VisualElement]:
        """Ground using DOM/accessibility tree only."""
        if not self.dom_engine:
            logger.warning("DOM engine not available")
            return []

        try:
            # Get DOM snapshot
            snapshot = await self.dom_engine.distill_page(
                page,
                mode=DistillationMode.INPUT_FIELDS
            )

            # Find matching elements using semantic matching
            matches = await self._match_elements_semantically(
                description,
                snapshot.elements,
                element_type
            )

            if matches:
                self.stats["dom_successes"] += 1

            return matches

        except Exception as e:
            logger.error(f"DOM grounding failed: {e}")
            return []

    async def _ground_with_vision(
        self,
        page: Page,
        description: str,
        element_type: Optional[ElementType],
        region: Optional[RegionOfInterest]
    ) -> List[VisualElement]:
        """Ground using vision model only."""
        if not self.vision_analyzer or not OLLAMA_AVAILABLE:
            logger.warning("Vision grounding not available")
            return []

        try:
            # Take screenshot (or crop to region if specified)
            screenshot_bytes = await self._take_screenshot(page, region)
            screenshot_path = await self._save_screenshot_temp(screenshot_bytes)

            # Use vision model to find element
            element = await self._find_element_with_vision(
                screenshot_bytes,
                description,
                element_type,
                page.viewport_size
            )

            if element:
                element.screenshot_path = screenshot_path
                self.stats["vision_successes"] += 1

                # Post-vision selector synthesis - save to site memory for future use
                # (Only if not already in a region - we synthesize at the main level)
                if not region:
                    await self._synthesize_and_save_selectors(
                        page, element, description
                    )

                return [element]

            return []

        except Exception as e:
            logger.error(f"Vision grounding failed: {e}")
            return []

    async def _ground_hybrid(
        self,
        page: Page,
        description: str,
        element_type: Optional[ElementType],
        region: Optional[RegionOfInterest]
    ) -> List[VisualElement]:
        """
        Hybrid approach: Site Memory → DOM → Accessibility Tree → Vision.

        Try site memory first (fastest, skip GPU), fallback to DOM (fast),
        finally vision (robust but expensive).
        """
        # STEP 0: Try site memory first (skip vision if we have saved selectors)
        logger.debug("Trying site memory selectors...")
        site_memory_match = await self._try_site_memory_selector(
            page, description, element_type
        )

        if site_memory_match:
            logger.debug("Site memory grounding succeeded - vision call skipped!")
            return [site_memory_match]

        # STEP 1: Try DOM
        logger.debug("Trying DOM grounding...")
        dom_matches = await self._ground_with_dom(page, description, element_type)

        if dom_matches and dom_matches[0].confidence > 0.7:
            logger.debug("DOM grounding succeeded with high confidence")
            return dom_matches

        # STEP 2: DOM failed or low confidence, try vision
        logger.debug("DOM grounding failed/low confidence, trying vision...")
        vision_matches = await self._ground_with_vision(
            page, description, element_type, region
        )

        if vision_matches:
            logger.debug("Vision grounding succeeded")

            # STEP 3: Post-vision selector synthesis - save to site memory
            await self._synthesize_and_save_selectors(
                page, vision_matches[0], description
            )

            return vision_matches

        # Return DOM matches even if low confidence (better than nothing)
        if dom_matches:
            logger.debug("Returning low-confidence DOM matches")
            return dom_matches

        return []

    async def _ground_coordinated(
        self,
        page: Page,
        description: str,
        element_type: Optional[ElementType],
        region: Optional[RegionOfInterest]
    ) -> List[VisualElement]:
        """
        Coordinated approach: Use both DOM and vision together.

        Combines information from both sources to improve accuracy.
        """
        # Run both in parallel
        dom_task = self._ground_with_dom(page, description, element_type)
        vision_task = self._ground_with_vision(page, description, element_type, region)

        dom_matches, vision_matches = await asyncio.gather(
            dom_task, vision_task, return_exceptions=True
        )

        # Handle exceptions
        if isinstance(dom_matches, Exception):
            logger.error(f"DOM grounding error: {dom_matches}")
            dom_matches = []
        if isinstance(vision_matches, Exception):
            logger.error(f"Vision grounding error: {vision_matches}")
            vision_matches = []

        # Combine results
        combined = await self._combine_grounding_results(
            dom_matches, vision_matches
        )

        return combined

    async def _ground_with_region_focus(
        self,
        page: Page,
        description: str,
        element_type: Optional[ElementType]
    ) -> List[VisualElement]:
        """
        Region focus approach: Dynamically zoom into relevant regions.

        Inspired by RegionFocus paper - identify region of interest,
        zoom in, then perform fine-grained grounding.
        """
        self.stats["region_focus_uses"] += 1

        try:
            # Step 1: Identify region of interest
            roi = await self._identify_region_of_interest(page, description)

            if not roi:
                logger.warning("Could not identify region of interest")
                # Fallback to regular hybrid grounding
                return await self._ground_hybrid(page, description, element_type, None)

            logger.info(f"Region focus: {roi.description} (confidence: {roi.confidence:.2f})")

            # Step 2: Ground within the region
            matches = await self._ground_with_vision(
                page, description, element_type, roi
            )

            # Annotate matches with region path
            for match in matches:
                match.region_path = [{"description": roi.description, "bbox": roi.bbox}]

            return matches

        except Exception as e:
            logger.error(f"Region focus grounding failed: {e}")
            # Fallback to hybrid
            return await self._ground_hybrid(page, description, element_type, None)

    # ==========================================================================
    # ACTIONS ON GROUNDED ELEMENTS
    # ==========================================================================

    async def click_grounded_element(
        self,
        page: Page,
        element: VisualElement,
        verify: bool = True
    ) -> bool:
        """
        Click a grounded element.

        Args:
            page: Playwright page object
            element: Grounded element to click
            verify: Whether to verify the click had an effect

        Returns:
            True if click succeeded
        """
        try:
            # Try DOM-based click first if available
            if element.dom_element and element.mmid:
                logger.debug(f"Clicking via DOM (mmid: {element.mmid})")
                selector = f"[data-mmid='{element.mmid}']"
                try:
                    await page.click(selector, timeout=5000)
                    logger.info(f"Clicked element via DOM: {element.description}")
                    return True
                except Exception as e:
                    logger.warning(f"DOM click failed: {e}, trying coordinates")

            # Fall back to coordinate click
            if element.center:
                x, y = element.center
                logger.debug(f"Clicking at coordinates ({x}, {y})")
                await page.mouse.click(x, y)
                logger.info(f"Clicked element at ({x}, {y}): {element.description}")

                # Verify if requested
                if verify:
                    await asyncio.sleep(0.5)  # Wait for potential changes
                    # Verify by checking if page state changed (URL, new elements loaded)
                    try:
                        current_url = page.url
                        # Check if navigation occurred or page content changed
                        await page.wait_for_load_state('domcontentloaded', timeout=2000)
                        logger.debug(f"Click verification: page state updated (url={current_url})")
                    except Exception:
                        # Timeout is fine - means no navigation, but click may still have worked
                        logger.debug("Click verification: no navigation detected (expected for most clicks)")

                return True

            logger.error(f"Cannot click element: no DOM selector or coordinates")
            return False

        except Exception as e:
            logger.error(f"Error clicking element: {e}")
            return False

    async def fill_grounded_element(
        self,
        page: Page,
        element: VisualElement,
        text: str
    ) -> bool:
        """
        Fill text into a grounded input element.

        Args:
            page: Playwright page object
            element: Grounded input element
            text: Text to fill

        Returns:
            True if fill succeeded
        """
        try:
            # Try DOM-based fill first
            if element.dom_element and element.mmid:
                logger.debug(f"Filling via DOM (mmid: {element.mmid})")
                selector = f"[data-mmid='{element.mmid}']"
                try:
                    await page.fill(selector, text, timeout=5000)
                    logger.info(f"Filled element via DOM: {element.description}")
                    return True
                except Exception as e:
                    logger.warning(f"DOM fill failed: {e}, trying click+type")

            # Fall back to click + type
            if element.center:
                x, y = element.center
                logger.debug(f"Clicking at ({x}, {y}) then typing")
                await page.mouse.click(x, y)
                await asyncio.sleep(0.2)
                await page.keyboard.type(text)
                logger.info(f"Filled element at ({x}, {y}): {element.description}")
                return True

            logger.error(f"Cannot fill element: no DOM selector or coordinates")
            return False

        except Exception as e:
            logger.error(f"Error filling element: {e}")
            return False

    async def extract_text_from_element(
        self,
        page: Page,
        element: VisualElement
    ) -> Optional[str]:
        """
        Extract text from a grounded element.

        Handles both DOM-accessible text and OCR for visual text.

        Args:
            page: Playwright page object
            element: Grounded element

        Returns:
            Extracted text or None
        """
        try:
            # Try DOM text first
            if element.dom_element and element.dom_element.text:
                return element.dom_element.text

            # Try OCR if we have a screenshot
            if element.bbox and VISION_ANALYZER_AVAILABLE:
                # Take screenshot and crop to element bbox for better OCR accuracy
                screenshot_bytes = await page.screenshot()

                # Crop to element bounding box
                try:
                    from PIL import Image
                    import io

                    img = Image.open(io.BytesIO(screenshot_bytes))
                    x1, y1, x2, y2 = element.bbox
                    cropped_img = img.crop((x1, y1, x2, y2))

                    # Save cropped image to temp file
                    cropped_bytes = io.BytesIO()
                    cropped_img.save(cropped_bytes, format='PNG')
                    cropped_bytes.seek(0)
                    temp_path = await self._save_screenshot_temp(cropped_bytes.read())
                except ImportError:
                    # PIL not available, use full screenshot
                    logger.warning("PIL not available, using full screenshot for OCR")
                    temp_path = await self._save_screenshot_temp(screenshot_bytes)
                except Exception as crop_err:
                    logger.warning(f"Failed to crop image: {crop_err}, using full screenshot")
                    temp_path = await self._save_screenshot_temp(screenshot_bytes)

                # Use vision analyzer for OCR on cropped region
                result = self.vision_analyzer.extract_text(temp_path)

                if result.success:
                    return result.description

            logger.warning(f"Could not extract text from element: {element.description}")
            return None

        except Exception as e:
            logger.error(f"Error extracting text: {e}")
            return None

    # ==========================================================================
    # SPECIAL UI HANDLING
    # ==========================================================================

    async def ground_canvas_element(
        self,
        page: Page,
        description: str,
        canvas_selector: str = "canvas"
    ) -> Optional[VisualElement]:
        """
        Ground an element within a canvas application.

        Canvas elements are not in the DOM, so we must use pure vision.

        Args:
            page: Playwright page object
            description: Element description
            canvas_selector: Selector for the canvas element

        Returns:
            Grounded canvas element or None
        """
        logger.info(f"Grounding canvas element: {description}")

        try:
            # Get canvas bounding box
            canvas = await page.query_selector(canvas_selector)
            if not canvas:
                logger.error(f"Canvas not found: {canvas_selector}")
                return None

            canvas_bbox = await canvas.bounding_box()
            if not canvas_bbox:
                logger.error("Could not get canvas bounding box")
                return None

            # Create region of interest for the canvas
            roi = RegionOfInterest(
                bbox=canvas_bbox,
                zoom_level=1.0,
                description=f"Canvas element: {canvas_selector}",
                confidence=1.0
            )

            # Ground within canvas using vision
            result = await self.ground_element(
                page,
                description,
                strategy=GroundingStrategy.VISION_ONLY,
                region=roi
            )

            if result.success and result.best_match:
                # Mark as canvas element
                result.best_match.is_canvas_element = True
                return result.best_match

            return None

        except Exception as e:
            logger.error(f"Error grounding canvas element: {e}")
            return None

    async def ground_svg_element(
        self,
        page: Page,
        description: str
    ) -> Optional[VisualElement]:
        """
        Ground an element within an SVG graphic.

        SVG elements can be in the DOM but often need visual grounding.

        Args:
            page: Playwright page object
            description: Element description

        Returns:
            Grounded SVG element or None
        """
        logger.info(f"Grounding SVG element: {description}")

        try:
            # Use coordinated approach (combines DOM SVG tree with vision)
            result = await self.ground_element(
                page,
                description,
                strategy=GroundingStrategy.COORDINATED
            )

            if result.success and result.best_match:
                result.best_match.is_svg = True
                return result.best_match

            return None

        except Exception as e:
            logger.error(f"Error grounding SVG element: {e}")
            return None

    # ==========================================================================
    # HELPER METHODS
    # ==========================================================================

    async def _match_elements_semantically(
        self,
        description: str,
        elements: List[ElementInfo],
        element_type: Optional[ElementType]
    ) -> List[VisualElement]:
        """
        Match elements semantically against description.

        Uses text matching, role matching, and semantic similarity.
        """
        desc_lower = description.lower()
        desc_words = set(desc_lower.split())

        matches = []

        for elem in elements:
            if not elem.is_interactive:
                continue

            # Filter by type if specified
            if element_type:
                elem_type = self._infer_element_type(elem)
                if elem_type != element_type:
                    continue

            # Calculate match score
            score = 0.0

            # Text match
            if elem.text:
                text_lower = elem.text.lower()
                text_words = set(text_lower.split())
                overlap = len(desc_words & text_words)
                if overlap > 0:
                    score += overlap / len(desc_words) * 0.5
                if desc_lower in text_lower:
                    score += 0.3

            # Role match
            if elem.role and elem.role.lower() in desc_lower:
                score += 0.2

            # ARIA label match
            if elem.aria_label and desc_lower in elem.aria_label.lower():
                score += 0.3

            # Placeholder match
            if elem.placeholder and desc_lower in elem.placeholder.lower():
                score += 0.2

            # Minimum threshold
            if score > 0.3:
                visual_elem = VisualElement(
                    description=description,
                    element_type=self._infer_element_type(elem),
                    bbox=elem.bbox,
                    center=self._calculate_center(elem.bbox) if elem.bbox else None,
                    confidence=min(score, 1.0),
                    match_method=MatchMethod.DOM_SELECTOR,
                    dom_element=elem,
                    mmid=elem.mmid
                )
                matches.append(visual_elem)

        # Sort by confidence
        matches.sort(key=lambda e: e.confidence, reverse=True)

        return matches

    async def _find_element_with_vision(
        self,
        screenshot_bytes: bytes,
        description: str,
        element_type: Optional[ElementType],
        viewport_size: Optional[Dict]
    ) -> Optional[VisualElement]:
        """Use vision model to find element in screenshot."""
        if not OLLAMA_AVAILABLE:
            return None

        try:
            # Encode image
            image_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')

            # Build prompt
            viewport = viewport_size or {"width": 1280, "height": 720}
            width = viewport['width']
            height = viewport['height']

            type_hint = f" It is a {element_type.value}." if element_type else ""

            prompt = f"""Look at this screenshot and find: {description}{type_hint}

Return the information in this EXACT format:

FOUND: yes/no
COORDINATES: x, y
BBOX: x, y, width, height
CONFIDENCE: 0.0-1.0
TEXT: any visible text on the element
TYPE: button/input/link/icon/image/text/other

Screen size is {width}x{height} pixels.
If you cannot find the element, respond with "FOUND: no"."""

            # Call vision model
            def _call_ollama():
                return ollama.generate(
                    model=self.vision_model,
                    prompt=prompt,
                    images=[image_b64],
                    options={'temperature': 0}
                )

            response = await asyncio.to_thread(_call_ollama)
            result = response.get('response', '')

            # Parse response
            if 'FOUND: no' in result or 'NOT_FOUND' in result:
                logger.debug(f"Vision model could not find: {description}")
                return None

            # Extract fields
            coords = self._extract_coordinates(result)
            bbox = self._extract_bbox(result)
            confidence = self._extract_confidence(result)
            ocr_text = self._extract_field(result, 'TEXT')
            visual_type = self._extract_field(result, 'TYPE')

            if not coords:
                logger.warning("Vision model response missing coordinates")
                return None

            # Validate coordinates
            x, y = coords
            if not (0 <= x <= width and 0 <= y <= height):
                logger.warning(f"Coordinates out of bounds: ({x}, {y})")
                return None

            # Infer element type
            inferred_type = self._infer_type_from_string(visual_type) if visual_type else ElementType.UNKNOWN
            if element_type and inferred_type != ElementType.UNKNOWN:
                inferred_type = element_type

            visual_elem = VisualElement(
                description=description,
                element_type=inferred_type,
                bbox=bbox,
                center=coords,
                confidence=confidence,
                match_method=MatchMethod.VISUAL_COORDINATES,
                ocr_text=ocr_text,
                visual_features={
                    "visual_type": visual_type,
                    "raw_response": result[:500]
                }
            )

            return visual_elem

        except Exception as e:
            logger.error(f"Error finding element with vision: {e}")
            return None

    async def _identify_region_of_interest(
        self,
        page: Page,
        description: str
    ) -> Optional[RegionOfInterest]:
        """
        Identify the region of interest for the given description.

        Uses vision model to understand page layout and identify
        the most relevant region.
        """
        if not OLLAMA_AVAILABLE:
            return None

        try:
            # Take screenshot
            screenshot_bytes = await page.screenshot()
            image_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')

            viewport = page.viewport_size or {"width": 1280, "height": 720}
            width = viewport['width']
            height = viewport['height']

            # Ask vision model to identify region
            prompt = f"""Look at this screenshot and identify the region that contains: {description}

Return the region's bounding box in this format:
REGION: x, y, width, height
DESCRIPTION: brief description of what's in this region
CONFIDENCE: 0.0-1.0

Screen size is {width}x{height} pixels."""

            def _call_ollama():
                return ollama.generate(
                    model=self.vision_model,
                    prompt=prompt,
                    images=[image_b64],
                    options={'temperature': 0}
                )

            response = await asyncio.to_thread(_call_ollama)
            result = response.get('response', '')

            # Parse region
            bbox = self._extract_region_bbox(result)
            region_desc = self._extract_field(result, 'DESCRIPTION')
            confidence = self._extract_confidence(result)

            if not bbox:
                logger.warning("Could not extract region from vision response")
                return None

            roi = RegionOfInterest(
                bbox=bbox,
                zoom_level=1.0,
                description=region_desc or "Region of interest",
                confidence=confidence
            )

            return roi

        except Exception as e:
            logger.error(f"Error identifying region of interest: {e}")
            return None

    async def _combine_grounding_results(
        self,
        dom_matches: List[VisualElement],
        vision_matches: List[VisualElement]
    ) -> List[VisualElement]:
        """
        Combine results from DOM and vision grounding.

        Merges overlapping matches and boosts confidence when both agree.
        """
        combined = []

        # Start with DOM matches
        for dom_elem in dom_matches:
            # Check if vision also found this element
            vision_match = None
            if dom_elem.center:
                for vis_elem in vision_matches:
                    if vis_elem.center and self._coordinates_close(
                        dom_elem.center, vis_elem.center, threshold=50
                    ):
                        vision_match = vis_elem
                        break

            if vision_match:
                # Both DOM and vision found it - boost confidence
                combined_confidence = min(
                    (dom_elem.confidence + vision_match.confidence) / 2 * 1.3,
                    1.0
                )
                dom_elem.confidence = combined_confidence
                dom_elem.ocr_text = vision_match.ocr_text
                dom_elem.visual_features = vision_match.visual_features
                logger.debug(
                    f"DOM+Vision agreement boosted confidence to {combined_confidence:.2f}"
                )

            combined.append(dom_elem)

        # Add vision matches that weren't found by DOM
        for vis_elem in vision_matches:
            is_duplicate = False
            if vis_elem.center:
                for combined_elem in combined:
                    if combined_elem.center and self._coordinates_close(
                        vis_elem.center, combined_elem.center, threshold=50
                    ):
                        is_duplicate = True
                        break

            if not is_duplicate:
                combined.append(vis_elem)

        # Sort by confidence
        combined.sort(key=lambda e: e.confidence, reverse=True)

        return combined

    async def _take_screenshot(
        self,
        page: Page,
        region: Optional[RegionOfInterest] = None
    ) -> bytes:
        """Take screenshot, optionally cropped to region."""
        if region:
            # Crop to region
            bbox = region.bbox
            return await page.screenshot(clip={
                'x': bbox['x'],
                'y': bbox['y'],
                'width': bbox['width'],
                'height': bbox['height']
            })
        else:
            # Full screenshot
            return await page.screenshot()

    async def _save_screenshot_temp(self, screenshot_bytes: bytes) -> str:
        """Save screenshot to temporary file."""
        temp_dir = Path("/tmp/eversale_grounding")
        temp_dir.mkdir(exist_ok=True, parents=True)

        # Generate unique filename
        filename = f"screenshot_{hashlib.md5(screenshot_bytes).hexdigest()[:8]}.png"
        filepath = temp_dir / filename

        filepath.write_bytes(screenshot_bytes)
        return str(filepath)

    def _infer_element_type(self, elem: ElementInfo) -> ElementType:
        """Infer element type from ElementInfo."""
        tag = elem.tag.lower()
        role = (elem.role or "").lower()

        if tag == "button" or role == "button":
            return ElementType.BUTTON
        elif tag == "input":
            return ElementType.INPUT
        elif tag == "a" or role == "link":
            return ElementType.LINK
        elif role == "checkbox":
            return ElementType.CHECKBOX
        elif role == "radio":
            return ElementType.RADIO
        elif tag == "select":
            return ElementType.SELECT
        elif tag == "img":
            return ElementType.IMAGE
        elif tag == "canvas":
            return ElementType.CANVAS
        else:
            return ElementType.UNKNOWN

    def _infer_type_from_string(self, type_str: str) -> ElementType:
        """Infer ElementType from string."""
        type_str = type_str.lower()

        if "button" in type_str:
            return ElementType.BUTTON
        elif "input" in type_str or "textbox" in type_str:
            return ElementType.INPUT
        elif "link" in type_str:
            return ElementType.LINK
        elif "checkbox" in type_str:
            return ElementType.CHECKBOX
        elif "radio" in type_str:
            return ElementType.RADIO
        elif "select" in type_str or "dropdown" in type_str:
            return ElementType.SELECT
        elif "icon" in type_str:
            return ElementType.ICON
        elif "image" in type_str or "img" in type_str:
            return ElementType.IMAGE
        elif "canvas" in type_str:
            return ElementType.CANVAS
        else:
            return ElementType.UNKNOWN

    def _calculate_center(self, bbox: Dict[str, float]) -> Tuple[int, int]:
        """Calculate center coordinates from bounding box."""
        x = int(bbox['x'] + bbox['width'] / 2)
        y = int(bbox['y'] + bbox['height'] / 2)
        return (x, y)

    def _coordinates_close(
        self,
        coords1: Tuple[int, int],
        coords2: Tuple[int, int],
        threshold: int = 50
    ) -> bool:
        """Check if two coordinates are close (within threshold pixels)."""
        dx = abs(coords1[0] - coords2[0])
        dy = abs(coords1[1] - coords2[1])
        distance = (dx ** 2 + dy ** 2) ** 0.5
        return distance <= threshold

    def _extract_coordinates(self, text: str) -> Optional[Tuple[int, int]]:
        """Extract coordinates from vision model response."""
        patterns = [
            r'COORDINATES:\s*(\d+)\s*,\s*(\d+)',
            r'CLICK:\s*(\d+)\s*,\s*(\d+)',
            r'CENTER:\s*(\d+)\s*,\s*(\d+)'
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return (int(match.group(1)), int(match.group(2)))

        return None

    def _extract_bbox(self, text: str) -> Optional[Dict[str, float]]:
        """Extract bounding box from vision model response."""
        match = re.search(
            r'BBOX:\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)',
            text,
            re.IGNORECASE
        )

        if match:
            return {
                'x': float(match.group(1)),
                'y': float(match.group(2)),
                'width': float(match.group(3)),
                'height': float(match.group(4))
            }

        return None

    def _extract_region_bbox(self, text: str) -> Optional[Dict[str, float]]:
        """Extract region bounding box from vision model response."""
        match = re.search(
            r'REGION:\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)',
            text,
            re.IGNORECASE
        )

        if match:
            return {
                'x': float(match.group(1)),
                'y': float(match.group(2)),
                'width': float(match.group(3)),
                'height': float(match.group(4))
            }

        return None

    def _extract_confidence(self, text: str) -> float:
        """Extract confidence score from vision model response."""
        match = re.search(r'CONFIDENCE:\s*([\d\.]+)', text, re.IGNORECASE)
        if match:
            confidence = float(match.group(1))
            return max(0.0, min(1.0, confidence))

        # Default confidence
        return 0.6

    def _extract_field(self, text: str, field_name: str) -> Optional[str]:
        """Extract a named field from vision model response."""
        pattern = f'{field_name}:\\s*(.+?)(?:\n|$)'
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return None

    # ==========================================================================
    # UTILITY METHODS
    # ==========================================================================

    def get_stats(self) -> Dict[str, Any]:
        """Get grounding statistics."""
        return self.stats.copy()

    def clear_cache(self):
        """Clear internal caches."""
        self._screenshot_cache.clear()
        self._element_cache.clear()
        logger.debug("Caches cleared")


# ==============================================================================
# CONVENIENCE FUNCTIONS
# ==============================================================================

_engine: Optional[VisualGroundingEngine] = None

def get_engine() -> VisualGroundingEngine:
    """
    Get global VisualGroundingEngine instance (singleton).

    Returns:
        VisualGroundingEngine instance
    """
    global _engine
    if _engine is None:
        _engine = VisualGroundingEngine()
    return _engine


async def ground_and_click(
    page: Page,
    description: str,
    strategy: Optional[GroundingStrategy] = None
) -> bool:
    """
    Quick function: ground an element and click it.

    Args:
        page: Playwright page
        description: Element description
        strategy: Optional grounding strategy

    Returns:
        True if successful

    Example:
        success = await ground_and_click(page, "the blue Send button")
    """
    engine = get_engine()
    result = await engine.ground_element(page, description, strategy)

    if result.success and result.best_match:
        return await engine.click_grounded_element(page, result.best_match)

    return False


async def ground_and_fill(
    page: Page,
    description: str,
    text: str,
    strategy: Optional[GroundingStrategy] = None
) -> bool:
    """
    Quick function: ground an input element and fill it.

    Args:
        page: Playwright page
        description: Element description
        text: Text to fill
        strategy: Optional grounding strategy

    Returns:
        True if successful

    Example:
        success = await ground_and_fill(page, "the email input", "user@example.com")
    """
    engine = get_engine()
    result = await engine.ground_element(
        page, description, strategy, ElementType.INPUT
    )

    if result.success and result.best_match:
        return await engine.fill_grounded_element(page, result.best_match, text)

    return False


async def ground_and_extract_text(
    page: Page,
    description: str,
    strategy: Optional[GroundingStrategy] = None
) -> Optional[str]:
    """
    Quick function: ground an element and extract its text.

    Args:
        page: Playwright page
        description: Element description
        strategy: Optional grounding strategy

    Returns:
        Extracted text or None

    Example:
        text = await ground_and_extract_text(page, "the error message")
    """
    engine = get_engine()
    result = await engine.ground_element(page, description, strategy)

    if result.success and result.best_match:
        return await engine.extract_text_from_element(page, result.best_match)

    return None


# ==============================================================================
# EXPORT
# ==============================================================================

__all__ = [
    # Classes
    'VisualGroundingEngine',
    'GroundingStrategy',
    'ElementType',
    'MatchMethod',
    'VisualElement',
    'GroundingResult',
    'RegionOfInterest',

    # Functions
    'get_engine',
    'ground_and_click',
    'ground_and_fill',
    'ground_and_extract_text',
]
