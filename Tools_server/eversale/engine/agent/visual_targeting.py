"""
Visual Targeting - Dual Strategy: Vision-Based Coordinates + Robust Selector Synthesis

Combines two approaches for maximum reliability:
1. Vision-based coordinate targeting (Moondream) - Works when selectors fail
2. Robust selector synthesis from visual location - Fast, cached, resilient to DOM changes

After locating an element visually, generate minimal-attribute selectors that:
- Are resilient to class name changes (React/Tailwind dynamic classes)
- Use stable attributes (id, aria-label, data-testid, role)
- Have fallback chain if primary fails
- Cache successful selectors per site

Flow:
  Vision Model → Element Location → Selector Synthesis → Validation → Cache
  OR: Load cached selector → Validate → Use (if still valid)

Author: Eversale AI
Date: 2025-12-07
"""

import asyncio
import base64
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any
from urllib.parse import urlparse
from loguru import logger

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    logger.warning("Ollama not available locally")

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False


@dataclass
class SelectorChain:
    """A selector with fallback strategies."""
    primary: str           # Best selector (most robust)
    fallbacks: List[str]   # Alternative selectors (in priority order)
    visual_coords: Tuple[int, int]  # Fallback to coordinates if all selectors fail
    confidence: float      # 0-1 confidence in primary selector
    element_type: str      # button, input, link, etc.
    description: str       # Human-readable description
    site_domain: str       # Domain this selector is valid for

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SelectorChain':
        """Load from dict."""
        return cls(**data)


@dataclass
class TargetingResult:
    """Result of visual element targeting."""
    success: bool
    coordinates: Optional[Tuple[int, int]] = None
    selector_chain: Optional[SelectorChain] = None
    confidence: float = 0.0
    element_description: str = ""
    error: Optional[str] = None
    strategy_used: str = "none"  # "cached_selector", "synthesized_selector", "visual_coords"

    def __post_init__(self):
        if self.selector_chain is None and self.coordinates:
            # Create minimal selector chain with just coordinates
            self.selector_chain = SelectorChain(
                primary="",
                fallbacks=[],
                visual_coords=self.coordinates,
                confidence=self.confidence,
                element_type="unknown",
                description=self.element_description,
                site_domain=""
            )


class SelectorCache:
    """Persistent cache of successful selectors per site."""

    def __init__(self, cache_dir: Path = None):
        """Initialize selector cache.

        Args:
            cache_dir: Directory to store cache files (default: ~/.eversale/selector_cache)
        """
        if cache_dir is None:
            cache_dir = Path.home() / ".eversale" / "selector_cache"
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # In-memory cache: {domain: {description_hash: SelectorChain}}
        self.memory_cache: Dict[str, Dict[str, SelectorChain]] = {}

    def _get_cache_file(self, domain: str) -> Path:
        """Get cache file path for domain."""
        # Sanitize domain for filename
        safe_domain = re.sub(r'[^\w\-.]', '_', domain)
        return self.cache_dir / f"{safe_domain}.json"

    def _hash_description(self, description: str) -> str:
        """Create hash of element description."""
        return hashlib.md5(description.lower().strip().encode()).hexdigest()[:16]

    def load_domain(self, domain: str) -> None:
        """Load cached selectors for domain into memory."""
        if domain in self.memory_cache:
            return  # Already loaded

        cache_file = self._get_cache_file(domain)
        if not cache_file.exists():
            self.memory_cache[domain] = {}
            return

        try:
            with open(cache_file, 'r') as f:
                data = json.load(f)

            self.memory_cache[domain] = {
                key: SelectorChain.from_dict(val)
                for key, val in data.items()
            }
            logger.info(f"Loaded {len(self.memory_cache[domain])} cached selectors for {domain}")
        except Exception as e:
            logger.warning(f"Failed to load selector cache for {domain}: {e}")
            self.memory_cache[domain] = {}

    def save_domain(self, domain: str) -> None:
        """Save cached selectors for domain to disk."""
        if domain not in self.memory_cache:
            return

        cache_file = self._get_cache_file(domain)
        try:
            data = {
                key: chain.to_dict()
                for key, chain in self.memory_cache[domain].items()
            }
            with open(cache_file, 'w') as f:
                json.dump(data, f, indent=2)
            logger.debug(f"Saved {len(data)} selectors to cache for {domain}")
        except Exception as e:
            logger.warning(f"Failed to save selector cache for {domain}: {e}")

    def get(self, domain: str, description: str) -> Optional[SelectorChain]:
        """Get cached selector for element description.

        Args:
            domain: Site domain (e.g., "example.com")
            description: Element description (e.g., "submit button")

        Returns:
            SelectorChain if found, None otherwise
        """
        self.load_domain(domain)
        desc_hash = self._hash_description(description)
        return self.memory_cache.get(domain, {}).get(desc_hash)

    def set(self, selector_chain: SelectorChain) -> None:
        """Cache a successful selector.

        Args:
            selector_chain: SelectorChain to cache
        """
        domain = selector_chain.site_domain
        self.load_domain(domain)

        if domain not in self.memory_cache:
            self.memory_cache[domain] = {}

        desc_hash = self._hash_description(selector_chain.description)
        self.memory_cache[domain][desc_hash] = selector_chain

        # Save to disk
        self.save_domain(domain)

    def clear_domain(self, domain: str) -> None:
        """Clear all cached selectors for a domain."""
        cache_file = self._get_cache_file(domain)
        if cache_file.exists():
            cache_file.unlink()

        if domain in self.memory_cache:
            del self.memory_cache[domain]

        logger.info(f"Cleared selector cache for {domain}")


class VisualTargeting:
    """
    Dual-strategy element targeting:
    1. Try cached robust selector first (instant)
    2. If cache miss or invalid, use vision to locate + synthesize new selector
    3. Fall back to raw coordinates if selector synthesis fails
    """

    # Vision model for coordinate detection
    DEFAULT_VISION_MODEL = 'moondream'
    FALLBACK_VISION_MODELS = ['smolvlm', 'qwen2.5-vl:3b', 'minicpm-v']

    # Cloud API endpoint
    CLOUD_API_URL = 'https://eversale.io/api/llm/v1/chat/completions'

    # Patterns for detecting dynamic class names
    DYNAMIC_CLASS_PATTERNS = [
        r'^css-[a-z0-9]+$',              # CSS-in-JS: css-1a2b3c
        r'^sc-[a-zA-Z0-9]+$',            # Styled Components: sc-bdnxRM
        r'^[a-z]+-[0-9a-f]{6,}$',        # Tailwind JIT: hover-3f2a1b
        r'^_[a-z0-9]{5,}$',              # Next.js: _1a2b3c
        r'^[A-Z][a-z]*__[a-z0-9]+$',     # BEM with hash: Button__abc123
        r'^makeStyles-[a-z]+-[0-9]+$',   # Material-UI: makeStyles-root-1
        r'^jss[0-9]+$',                  # JSS: jss1, jss2
        r'^emotion-[0-9]+$',             # Emotion: emotion-0
    ]

    # Stable attribute priority (highest to lowest)
    STABLE_ATTRS = [
        'id',
        'data-testid',
        'data-test-id',
        'data-test',
        'aria-label',
        'aria-labelledby',
        'name',
        'role',
        'type',
        'placeholder',
        'alt',
        'title',
    ]

    def __init__(
        self,
        model: str = None,
        ollama_client = None,
        screen_width: int = 1920,
        screen_height: int = 1080,
        mode: str = 'auto',
        license_key: str = None,
        cache: SelectorCache = None
    ):
        """Initialize visual targeting with dual strategy.

        Args:
            model: Vision model for coordinate detection
            ollama_client: Optional Ollama client
            screen_width: Browser viewport width
            screen_height: Browser viewport height
            mode: 'auto', 'local', or 'cloud'
            license_key: License for cloud mode
            cache: SelectorCache instance
        """
        self.model = model or self.DEFAULT_VISION_MODEL
        self.client = ollama_client or (ollama.Client() if OLLAMA_AVAILABLE else None)
        self.screen_width = screen_width
        self.screen_height = screen_height
        self._model_verified = False
        self._use_cloud = False
        self._mode = mode
        self._license_key = license_key or self._load_license_key()
        self.cache = cache or SelectorCache()

    def _load_license_key(self) -> Optional[str]:
        """Load license key from ~/.eversale/license.key"""
        try:
            license_path = os.path.expanduser('~/.eversale/license.key')
            if os.path.exists(license_path):
                with open(license_path, 'r') as f:
                    return f.read().strip()
        except Exception:
            pass
        return None

    @staticmethod
    def is_dynamic_class(class_name: str) -> bool:
        """Detect React/Tailwind/CSS-in-JS dynamic classes.

        Args:
            class_name: CSS class name to check

        Returns:
            True if class appears to be dynamically generated

        Examples:
            >>> VisualTargeting.is_dynamic_class("css-1a2b3c")
            True
            >>> VisualTargeting.is_dynamic_class("btn-primary")
            False
            >>> VisualTargeting.is_dynamic_class("sc-bdnxRM")
            True
        """
        if not class_name or len(class_name) < 3:
            return False

        for pattern in VisualTargeting.DYNAMIC_CLASS_PATTERNS:
            if re.match(pattern, class_name):
                return True

        # Check for base64-ish random strings (high entropy)
        if len(class_name) > 8 and re.match(r'^[a-zA-Z0-9_-]+$', class_name):
            unique_chars = len(set(class_name))
            if unique_chars / len(class_name) > 0.6:
                return True

        return False

    @staticmethod
    def filter_stable_classes(classes: List[str]) -> List[str]:
        """Filter out dynamic classes, keep only stable ones.

        Args:
            classes: List of CSS class names

        Returns:
            List of stable class names

        Examples:
            >>> VisualTargeting.filter_stable_classes(["btn", "css-abc123", "primary"])
            ['btn', 'primary']
        """
        return [c for c in classes if not VisualTargeting.is_dynamic_class(c)]

    async def ensure_model_available(self) -> bool:
        """Verify vision model is available."""
        if self._model_verified:
            return True

        if self._mode == 'cloud':
            return await self._setup_cloud_mode()
        elif self._mode == 'local':
            return await self._setup_local_mode()
        else:  # auto
            if await self._setup_local_mode():
                return True
            logger.info("Local Ollama unavailable, trying cloud")
            return await self._setup_cloud_mode()

    async def _setup_local_mode(self) -> bool:
        """Set up local Ollama mode."""
        if not self.client:
            return False

        try:
            models_response = self.client.list()
            if hasattr(models_response, 'models'):
                available = [m.model.split(':')[0] for m in models_response.models]
            else:
                available = [m.get('name', m.get('model', '')).split(':')[0]
                           for m in models_response.get('models', [])]

            if self.model.split(':')[0] in available:
                self._model_verified = True
                self._use_cloud = False
                logger.info(f"Visual targeting using LOCAL {self.model}")
                return True

            for fallback in self.FALLBACK_VISION_MODELS:
                if fallback.split(':')[0] in available:
                    logger.warning(f"{self.model} not found, using {fallback}")
                    self.model = fallback
                    self._model_verified = True
                    self._use_cloud = False
                    return True

            return False
        except Exception as e:
            logger.debug(f"Local mode setup failed: {e}")
            return False

    async def _setup_cloud_mode(self) -> bool:
        """Set up cloud mode via eversale.io."""
        if not HTTPX_AVAILABLE:
            logger.error("httpx not installed - cloud mode unavailable")
            return False

        if not self._license_key:
            logger.error("No license key - cloud mode requires valid license")
            return False

        self._use_cloud = True
        self._model_verified = True
        logger.info("Visual targeting using CLOUD (RunPod A5000)")
        return True

    async def _cloud_inference(self, screenshot_b64: str, prompt: str) -> str:
        """Send visual inference request to cloud."""
        if not HTTPX_AVAILABLE:
            raise RuntimeError("httpx not installed")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self.CLOUD_API_URL,
                headers={
                    'Authorization': f'Bearer {self._license_key}',
                    'Content-Type': 'application/json'
                },
                json={
                    'model': self.model,
                    'messages': [{
                        'role': 'user',
                        'content': [
                            {'type': 'text', 'text': prompt},
                            {'type': 'image_url', 'image_url': {'url': f'data:image/jpeg;base64,{screenshot_b64}'}}
                        ]
                    }],
                    'max_tokens': 256,
                    'temperature': 0.1
                }
            )
            response.raise_for_status()
            result = response.json()
            return result.get('choices', [{}])[0].get('message', {}).get('content', '')

    async def extract_element_info(self, page, x: int, y: int) -> Dict[str, Any]:
        """Extract element attributes at coordinates for selector synthesis.

        Args:
            page: Playwright page
            x: X coordinate
            y: Y coordinate

        Returns:
            Dict with element info (tag, attributes, text, classes, etc.)
        """
        try:
            info = await page.evaluate(f"""
                () => {{
                    const element = document.elementFromPoint({x}, {y});
                    if (!element) return null;

                    const attrs = {{}};
                    for (const attr of element.attributes) {{
                        attrs[attr.name] = attr.value;
                    }}

                    let computedRole = element.getAttribute('role');
                    if (!computedRole) {{
                        const tagRoles = {{
                            'button': 'button',
                            'a': 'link',
                            'input': 'textbox',
                            'textarea': 'textbox',
                            'select': 'combobox',
                            'img': 'img',
                            'h1': 'heading',
                            'h2': 'heading',
                            'h3': 'heading',
                        }};
                        computedRole = tagRoles[element.tagName.toLowerCase()] || '';
                    }}

                    return {{
                        tag: element.tagName.toLowerCase(),
                        attributes: attrs,
                        text: element.textContent?.trim().substring(0, 100) || '',
                        innerHTML: element.innerHTML.substring(0, 500),
                        classes: Array.from(element.classList),
                        computedRole: computedRole,
                        isVisible: element.offsetParent !== null,
                        rect: element.getBoundingClientRect().toJSON(),
                    }};
                }}
            """)
            return info or {}
        except Exception as e:
            logger.error(f"Failed to extract element info: {e}")
            return {}

    def generate_selector_candidates(self, info: Dict[str, Any]) -> List[str]:
        """Generate candidate selectors from element info (ordered by robustness).

        Args:
            info: Element info dict from extract_element_info

        Returns:
            List of selector candidates
        """
        candidates = []
        attrs = info.get('attributes', {})
        tag = info.get('tag', '')
        classes = info.get('classes', [])
        text = info.get('text', '')
        role = info.get('computedRole', '')

        # 1. ID selector (if not dynamic)
        if 'id' in attrs and attrs['id'] and not self.is_dynamic_class(attrs['id']):
            candidates.append(f"#{attrs['id']}")

        # 2. Test IDs
        for attr in ['data-testid', 'data-test-id', 'data-test']:
            if attr in attrs and attrs[attr]:
                candidates.append(f"[{attr}='{attrs[attr]}']")

        # 3. ARIA label
        if 'aria-label' in attrs and attrs['aria-label']:
            label = attrs['aria-label'].replace("'", "\\'")
            candidates.append(f"[aria-label='{label}']")

        # 4. ARIA labelledby
        if 'aria-labelledby' in attrs and attrs['aria-labelledby']:
            candidates.append(f"[aria-labelledby='{attrs['aria-labelledby']}']")

        # 5. Name attribute
        if 'name' in attrs and attrs['name']:
            candidates.append(f"[name='{attrs['name']}']")

        # 6. Stable classes
        stable_classes = self.filter_stable_classes(classes)
        if stable_classes:
            for cls in stable_classes[:3]:
                candidates.append(f".{cls}")
            if len(stable_classes) >= 2:
                candidates.append(f".{'.'.join(stable_classes[:2])}")

        # 7. Role + text hint
        if role and text:
            text_hint = text[:30].replace("'", "\\'").replace('"', '\\"')
            candidates.append(f"[role='{role}']:has-text('{text_hint}')")

        # 8. Tag + type
        if tag in ['input', 'button', 'select', 'textarea'] and 'type' in attrs:
            candidates.append(f"{tag}[type='{attrs['type']}']")

        # 9. Placeholder
        if 'placeholder' in attrs and attrs['placeholder']:
            ph = attrs['placeholder'].replace("'", "\\'")
            candidates.append(f"{tag}[placeholder='{ph}']")

        # 10. Alt text
        if tag == 'img' and 'alt' in attrs and attrs['alt']:
            alt = attrs['alt'].replace("'", "\\'")
            candidates.append(f"img[alt='{alt}']")

        # 11. Title
        if 'title' in attrs and attrs['title']:
            title = attrs['title'].replace("'", "\\'")
            candidates.append(f"{tag}[title='{title}']")

        return candidates

    async def validate_selector(self, page, selector: str, expected_x: int,
                               expected_y: int, tolerance: int = 10) -> bool:
        """Validate selector returns 1 element at expected location.

        Args:
            page: Playwright page
            selector: CSS selector
            expected_x: Expected X coordinate
            expected_y: Expected Y coordinate
            tolerance: Pixel tolerance

        Returns:
            True if valid
        """
        try:
            count = await page.locator(selector).count()
            if count != 1:
                logger.debug(f"Selector '{selector}' matched {count} elements")
                return False

            element = page.locator(selector).first
            box = await element.bounding_box()
            if not box:
                return False

            center_x = box['x'] + box['width'] / 2
            center_y = box['y'] + box['height'] / 2

            if abs(center_x - expected_x) > tolerance or abs(center_y - expected_y) > tolerance:
                logger.debug(f"Selector at ({center_x:.0f}, {center_y:.0f}), expected ({expected_x}, {expected_y})")
                return False

            return True
        except Exception as e:
            logger.debug(f"Selector validation failed: {e}")
            return False

    async def synthesize_selector(self, page, x: int, y: int,
                                  description: str = "") -> Optional[SelectorChain]:
        """Synthesize robust selector from visual coordinates.

        Args:
            page: Playwright page
            x: X coordinate
            y: Y coordinate
            description: Element description for caching

        Returns:
            SelectorChain or None
        """
        url = await page.url()
        domain = urlparse(url).netloc

        # Extract element info at coordinates
        info = await self.extract_element_info(page, x, y)
        if not info or not info.get('tag'):
            logger.warning(f"No element found at ({x}, {y})")
            return None

        # Generate candidates
        candidates = self.generate_selector_candidates(info)
        if not candidates:
            logger.warning(f"No selector candidates for element at ({x}, {y})")
            return None

        # Validate candidates
        valid_selectors = []
        for selector in candidates:
            if await self.validate_selector(page, selector, x, y):
                valid_selectors.append(selector)
                logger.debug(f"Valid selector: {selector}")

        if not valid_selectors:
            logger.warning(f"No valid selectors for element at ({x}, {y})")
            return None

        # Build selector chain
        primary = valid_selectors[0]
        fallbacks = valid_selectors[1:5]

        # Calculate confidence
        confidence = 1.0
        if primary.startswith('#'):
            confidence = 0.95
        elif '[data-test' in primary:
            confidence = 0.90
        elif '[aria-label' in primary:
            confidence = 0.85
        elif primary.startswith('.') and '.' not in primary[1:]:
            confidence = 0.70
        else:
            confidence = 0.60

        chain = SelectorChain(
            primary=primary,
            fallbacks=fallbacks,
            visual_coords=(x, y),
            confidence=confidence,
            element_type=info.get('tag', 'unknown'),
            description=description or f"{info.get('tag', 'element')} at ({x}, {y})",
            site_domain=domain,
        )

        # Cache it
        if description:
            self.cache.set(chain)

        logger.info(f"Synthesized selector: {primary} (confidence: {confidence:.2f})")
        return chain

    def _parse_coordinates(self, response: str) -> Optional[Tuple[int, int]]:
        """Extract (x, y) from vision model response."""
        # Normalized bounding box
        bbox_patterns = [
            r'ids?\s*=\s*\[([\d.]+),\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)\]',
            r'\[([\d.]+),\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)\]',
            r'([\d.]+),\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)',
        ]

        for pattern in bbox_patterns:
            match = re.search(pattern, response)
            if match:
                x1, y1, x2, y2 = [float(m) for m in match.groups()]
                if all(0 <= v <= 1 for v in [x1, y1, x2, y2]):
                    center_x = (x1 + x2) / 2
                    center_y = (y1 + y2) / 2
                    x = int(center_x * self.screen_width)
                    y = int(center_y * self.screen_height)
                    logger.debug(f"Parsed bbox [{x1:.2f},{y1:.2f},{x2:.2f},{y2:.2f}] -> ({x}, {y})")
                    return (x, y)

        # Pixel coordinates
        pixel_patterns = [
            r'\((\d+),\s*(\d+)\)',
            r'(\d+),\s*(\d+)',
            r'x[=:]?\s*(\d+).*y[=:]?\s*(\d+)',
            r'at\s+(\d+)\s+(\d+)',
        ]

        for pattern in pixel_patterns:
            match = re.search(pattern, response, re.IGNORECASE)
            if match:
                x, y = int(match.group(1)), int(match.group(2))
                if 0 <= x <= self.screen_width and 0 <= y <= self.screen_height:
                    return (x, y)

        return None

    async def locate_element(
        self,
        page,
        screenshot_b64: str,
        element_description: str,
        context: str = ""
    ) -> TargetingResult:
        """Dual-strategy element location: cached selector → vision → synthesis.

        Strategy:
        1. Try cached selector (instant, if valid)
        2. Use vision to find coordinates
        3. Synthesize new selector from coordinates
        4. Cache new selector for future use

        Args:
            page: Playwright page
            screenshot_b64: Base64 screenshot
            element_description: Natural language description
            context: Optional context

        Returns:
            TargetingResult with coordinates and/or selector chain
        """
        url = await page.url()
        domain = urlparse(url).netloc

        # Strategy 1: Try cached selector
        cached = self.cache.get(domain, element_description)
        if cached and cached.primary:
            try:
                # Validate cached selector still works
                count = await page.locator(cached.primary).count()
                if count == 1:
                    box = await page.locator(cached.primary).first.bounding_box()
                    if box:
                        x = int(box['x'] + box['width'] / 2)
                        y = int(box['y'] + box['height'] / 2)
                        logger.info(f"Using cached selector: {cached.primary}")
                        return TargetingResult(
                            success=True,
                            coordinates=(x, y),
                            selector_chain=cached,
                            confidence=cached.confidence,
                            element_description=element_description,
                            strategy_used="cached_selector"
                        )
            except Exception as e:
                logger.debug(f"Cached selector invalid: {e}")

        # Strategy 2: Use vision to find coordinates
        if not await self.ensure_model_available():
            return TargetingResult(
                success=False,
                error="Vision model not available",
                element_description=element_description
            )

        try:
            prompt = f"Find the element with text {element_description} and return its x,y coordinates"
            if context:
                prompt = f"{context}. {prompt}"

            # Vision inference
            if self._use_cloud:
                content = await self._cloud_inference(screenshot_b64, prompt)
            else:
                response = await asyncio.to_thread(
                    self.client.chat,
                    model=self.model,
                    messages=[{
                        'role': 'user',
                        'content': prompt,
                        'images': [screenshot_b64]
                    }],
                    options={'temperature': 0.1}
                )
                content = response.get('message', {}).get('content', '')

            logger.debug(f"Vision response: {content[:200]}")
            coords = self._parse_coordinates(content)

            if not coords:
                return TargetingResult(
                    success=False,
                    error=f"Could not locate: {element_description}",
                    element_description=element_description
                )

            x, y = coords

            # Strategy 3: Synthesize selector from coordinates
            chain = await self.synthesize_selector(page, x, y, element_description)

            if chain:
                return TargetingResult(
                    success=True,
                    coordinates=(x, y),
                    selector_chain=chain,
                    confidence=chain.confidence,
                    element_description=element_description,
                    strategy_used="synthesized_selector"
                )
            else:
                # Fall back to raw coordinates
                return TargetingResult(
                    success=True,
                    coordinates=(x, y),
                    confidence=0.75,
                    element_description=element_description,
                    strategy_used="visual_coords"
                )

        except Exception as e:
            logger.warning(f"Visual targeting failed: {e}")
            return TargetingResult(
                success=False,
                error=str(e),
                element_description=element_description
            )

    async def click_with_fallback(self, page, result: TargetingResult) -> bool:
        """Click element using all available strategies.

        Order:
        1. Primary selector
        2. Fallback selectors
        3. Visual coordinates

        Args:
            page: Playwright page
            result: TargetingResult from locate_element

        Returns:
            True if click succeeded
        """
        if not result.success:
            return False

        chain = result.selector_chain

        # Try primary selector
        if chain and chain.primary:
            try:
                await page.click(chain.primary, timeout=5000)
                logger.info(f"Clicked using primary selector: {chain.primary}")
                return True
            except Exception as e:
                logger.debug(f"Primary selector failed: {e}")

        # Try fallback selectors
        if chain and chain.fallbacks:
            for i, fallback in enumerate(chain.fallbacks):
                try:
                    await page.click(fallback, timeout=5000)
                    logger.info(f"Clicked using fallback #{i+1}: {fallback}")
                    return True
                except Exception as e:
                    logger.debug(f"Fallback #{i+1} failed: {e}")

        # Last resort: coordinates
        if result.coordinates:
            try:
                x, y = result.coordinates
                await page.mouse.click(x, y)
                logger.info(f"Clicked using coordinates: ({x}, {y})")
                return True
            except Exception as e:
                logger.error(f"Coordinate click failed: {e}")

        return False

    async def fill_with_fallback(self, page, result: TargetingResult, text: str) -> bool:
        """Fill input using all available strategies.

        Args:
            page: Playwright page
            result: TargetingResult from locate_element
            text: Text to fill

        Returns:
            True if fill succeeded
        """
        if not result.success:
            return False

        chain = result.selector_chain

        # Try primary selector
        if chain and chain.primary:
            try:
                await page.fill(chain.primary, text, timeout=5000)
                logger.info(f"Filled using primary selector: {chain.primary}")
                return True
            except Exception as e:
                logger.debug(f"Primary selector failed: {e}")

        # Try fallback selectors
        if chain and chain.fallbacks:
            for i, fallback in enumerate(chain.fallbacks):
                try:
                    await page.fill(fallback, text, timeout=5000)
                    logger.info(f"Filled using fallback #{i+1}: {fallback}")
                    return True
                except Exception as e:
                    logger.debug(f"Fallback #{i+1} failed: {e}")

        # Last resort: click + type
        if result.coordinates:
            try:
                x, y = result.coordinates
                await page.mouse.click(x, y)
                await page.keyboard.type(text)
                logger.info(f"Filled using coordinates: ({x}, {y})")
                return True
            except Exception as e:
                logger.error(f"Coordinate fill failed: {e}")

        return False


# Global instance
_targeting_instance: Optional[VisualTargeting] = None

def get_visual_targeting(
    model: str = None,
    ollama_client = None,
    cache: SelectorCache = None
) -> VisualTargeting:
    """Get or create global VisualTargeting instance.

    Returns:
        VisualTargeting instance
    """
    global _targeting_instance

    if _targeting_instance is None:
        _targeting_instance = VisualTargeting(
            model=model,
            ollama_client=ollama_client,
            cache=cache
        )

    return _targeting_instance


# Example usage
if __name__ == "__main__":
    import asyncio
    from playwright.async_api import async_playwright

    async def demo():
        """Demo: dual-strategy targeting on Amazon."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            page = await browser.new_page()

            await page.goto("https://www.amazon.com")

            # Initialize targeting
            targeting = VisualTargeting()

            # Take screenshot
            screenshot = await page.screenshot()
            screenshot_b64 = base64.b64encode(screenshot).decode()

            # Locate search box (first visit - will use vision + synthesis)
            result1 = await targeting.locate_element(
                page,
                screenshot_b64,
                "search box"
            )

            if result1.success:
                print(f"\nFirst visit:")
                print(f"  Strategy: {result1.strategy_used}")
                print(f"  Coordinates: {result1.coordinates}")
                if result1.selector_chain:
                    print(f"  Primary selector: {result1.selector_chain.primary}")
                    print(f"  Fallbacks: {result1.selector_chain.fallbacks[:3]}")

                # Fill search box
                await targeting.fill_with_fallback(page, result1, "laptop")
                await asyncio.sleep(1)

            # Navigate away and back
            await page.goto("https://www.amazon.com/gp/help/customer/display.html")
            await asyncio.sleep(1)
            await page.goto("https://www.amazon.com")

            # Take new screenshot
            screenshot = await page.screenshot()
            screenshot_b64 = base64.b64encode(screenshot).decode()

            # Locate search box again (should use cached selector)
            result2 = await targeting.locate_element(
                page,
                screenshot_b64,
                "search box"
            )

            if result2.success:
                print(f"\nSecond visit:")
                print(f"  Strategy: {result2.strategy_used}")
                print(f"  Coordinates: {result2.coordinates}")
                if result2.selector_chain:
                    print(f"  Primary selector: {result2.selector_chain.primary}")

            await browser.close()

    asyncio.run(demo())
