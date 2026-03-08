"""
Web to Markdown Converter - Jina Reader Style
Converts any webpage into clean LLM-friendly markdown.

Inspired by:
- Jina Reader (r.jina.ai) - Simple URL prefix API
- Crawl4AI - Fit markdown with noise filtering
- Firecrawl - Multiple output formats

Features:
1. HTML to clean Markdown conversion
2. Readability-style content extraction (main content only)
3. Fit markdown (removes boilerplate, nav, ads)
4. Optional image captioning with VLM
5. CSS selector targeting
6. PDF support (via extraction)
"""

import re
import time
import hashlib
from typing import Dict, List, Any, Optional, Tuple
from loguru import logger

# Try to import html2text for markdown conversion
try:
    import html2text
    HTML2TEXT_AVAILABLE = True
except ImportError:
    HTML2TEXT_AVAILABLE = False
    logger.warning("html2text not installed. Run: pip install html2text")

# Try to import trafilatura for intelligent content extraction
try:
    import trafilatura
    TRAFILATURA_AVAILABLE = True
except ImportError:
    TRAFILATURA_AVAILABLE = False
    logger.warning("trafilatura not installed. Run: pip install trafilatura")

# Try to import readability-lxml for content extraction
try:
    from readability import Document as ReadabilityDocument
    READABILITY_AVAILABLE = True
except ImportError:
    READABILITY_AVAILABLE = False


class WebToMarkdown:
    """
    Converts web pages to clean, LLM-friendly markdown.

    Usage:
        converter = WebToMarkdown()
        markdown = await converter.convert(page)  # From Playwright page
        markdown = converter.convert_html(html_string)  # From HTML string
    """

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}

        # Cache for converted pages (15 min TTL like Claude Code WebFetch)
        self._cache: Dict[str, Tuple[Dict[str, Any], float]] = {}
        self._cache_ttl = config.get('cache_ttl', 900) if config else 900  # 15 minutes

        # Configure html2text
        if HTML2TEXT_AVAILABLE:
            self.h2t = html2text.HTML2Text()
            self.h2t.ignore_links = False
            self.h2t.ignore_images = False
            self.h2t.ignore_emphasis = False
            self.h2t.body_width = 0  # Don't wrap
            self.h2t.unicode_snob = True
            self.h2t.skip_internal_links = True
            self.h2t.inline_links = True
            self.h2t.protect_links = True
            # Ignore scripts and styles
            self.h2t.ignore_tables = False
        else:
            self.h2t = None

        # Noise patterns to remove (boilerplate, navigation, ads)
        self.noise_patterns = [
            # Navigation
            r'<nav[^>]*>.*?</nav>',
            r'<header[^>]*>.*?</header>',
            r'<footer[^>]*>.*?</footer>',
            r'<aside[^>]*>.*?</aside>',
            # Scripts and styles
            r'<script[^>]*>.*?</script>',
            r'<style[^>]*>.*?</style>',
            r'<noscript[^>]*>.*?</noscript>',
            # Ads and tracking
            r'<div[^>]*class="[^"]*ad[^"]*"[^>]*>.*?</div>',
            r'<div[^>]*id="[^"]*ad[^"]*"[^>]*>.*?</div>',
            r'<!--.*?-->',
            # Social share buttons
            r'<div[^>]*class="[^"]*share[^"]*"[^>]*>.*?</div>',
            r'<div[^>]*class="[^"]*social[^"]*"[^>]*>.*?</div>',
            # Comments sections
            r'<div[^>]*id="[^"]*comment[^"]*"[^>]*>.*?</div>',
            r'<section[^>]*class="[^"]*comment[^"]*"[^>]*>.*?</section>',
        ]

        # Boilerplate text patterns to remove from final markdown
        self.boilerplate_patterns = [
            r'^\s*Cookie Policy.*$',
            r'^\s*Privacy Policy.*$',
            r'^\s*Terms of Service.*$',
            r'^\s*All rights reserved.*$',
            r'^\s*Copyright ©.*$',
            r'^\s*Subscribe to our newsletter.*$',
            r'^\s*Follow us on.*$',
            r'^\s*Share this.*$',
            r'^\s*Loading\.\.\.$',
            r'^\s*Please wait.*$',
        ]

    def _get_cache_key(self, url: str, target_selector: Optional[str] = None, fit_markdown: bool = True) -> str:
        """Generate cache key from URL and options."""
        key_str = f"{url}|{target_selector or ''}|{fit_markdown}"
        return hashlib.md5(key_str.encode()).hexdigest()

    def _get_cached(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get cached result if still valid."""
        if cache_key in self._cache:
            result, timestamp = self._cache[cache_key]
            if time.time() - timestamp < self._cache_ttl:
                logger.debug(f"Cache hit for {cache_key[:16]}...")
                return result
            else:
                del self._cache[cache_key]
        return None

    def _set_cached(self, cache_key: str, result: Dict[str, Any]) -> None:
        """Store result in cache."""
        self._cache[cache_key] = (result, time.time())
        # Clean old entries
        self._clean_cache()

    def _clean_cache(self) -> None:
        """Remove expired cache entries."""
        now = time.time()
        expired = [k for k, (_, ts) in self._cache.items() if now - ts >= self._cache_ttl]
        for k in expired:
            del self._cache[k]

    async def convert(
        self,
        page,
        target_selector: Optional[str] = None,
        include_images: bool = True,
        fit_markdown: bool = True
    ) -> Dict[str, Any]:
        """
        Convert a Playwright page to markdown.

        Args:
            page: Playwright page object
            target_selector: CSS selector to extract specific content (like x-target-selector)
            include_images: Include images with alt text
            fit_markdown: Apply noise filtering for cleaner LLM input

        Returns:
            {
                'markdown': str,
                'title': str,
                'url': str,
                'word_count': int,
                'links': List[Dict],
                'images': List[Dict],
                'metadata': Dict
            }
        """
        # Check cache first
        cache_key = self._get_cache_key(str(page.url), target_selector, fit_markdown)
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        try:
            url = page.url
            title = await page.title()

            # Get HTML content
            if target_selector:
                # Extract specific section
                try:
                    html = await page.eval_on_selector(
                        target_selector,
                        "el => el.outerHTML"
                    )
                except Exception:
                    logger.warning(f"Selector {target_selector} not found, using full page")
                    html = await page.content()
            else:
                html = await page.content()

            # Convert to markdown
            result = self.convert_html(html, fit_markdown=fit_markdown, include_images=include_images)
            result['url'] = url
            result['title'] = title

            # Extract metadata from page
            metadata = await self._extract_metadata(page)
            result['metadata'] = metadata

            # Cache the result
            self._set_cached(cache_key, result)

            return result

        except Exception as e:
            logger.error(f"Convert error: {e}")
            return {'error': str(e), 'markdown': '', 'url': '', 'title': ''}

    def convert_html(
        self,
        html: str,
        fit_markdown: bool = True,
        include_images: bool = True
    ) -> Dict[str, Any]:
        """
        Convert HTML string to markdown.

        Args:
            html: Raw HTML string
            fit_markdown: Apply heuristic filtering to remove noise
            include_images: Include images in output

        Returns:
            {
                'markdown': str,
                'raw_markdown': str (before fit filtering),
                'word_count': int,
                'links': List[Dict],
                'images': List[Dict]
            }
        """
        result = {
            'markdown': '',
            'raw_markdown': '',
            'word_count': 0,
            'links': [],
            'images': []
        }

        try:
            # DEBUG: Log input size

            # Step 0: Expand link titles - replace truncated text with title attribute
            # This helps with sites like books.toscrape.com where titles are truncated
            html = self._expand_link_titles(html)

            # Step 1: Try intelligent content extraction first (like Readability)
            main_content = self._extract_main_content(html)

            # Step 2: Remove noise from HTML
            if fit_markdown:
                main_content = self._remove_noise_html(main_content)

            # Step 3: Convert to markdown
            if HTML2TEXT_AVAILABLE and self.h2t:
                self.h2t.ignore_images = not include_images
                raw_markdown = self.h2t.handle(main_content)
            else:
                # Fallback: basic regex-based conversion
                raw_markdown = self._basic_html_to_markdown(main_content)

            result['raw_markdown'] = raw_markdown

            # Step 4: Apply fit markdown filtering
            if fit_markdown:
                markdown = self._fit_markdown(raw_markdown)
            else:
                markdown = raw_markdown

            # CRITICAL FIX: If fit_markdown stripped too much, use raw_markdown
            # E-commerce sites like Amazon have link-heavy content that gets filtered
            if len(markdown.strip()) < 500 and len(raw_markdown.strip()) > 500:
                logger.info(f"[web_to_markdown] fit_markdown too aggressive ({len(markdown)} chars), using raw_markdown ({len(raw_markdown)} chars)")
                markdown = raw_markdown

            result['markdown'] = markdown.strip()
            result['word_count'] = len(markdown.split())

            # Step 5: Extract links and images
            result['links'] = self._extract_links(html)
            result['images'] = self._extract_images(html)

            return result

        except Exception as e:
            logger.error(f"HTML convert error: {e}")
            result['error'] = str(e)
            return result

    def _extract_main_content(self, html: str, prefer_markdown: bool = False) -> str:
        """
        Extract main content using readability-style algorithms.
        Removes navigation, sidebars, footers, etc.

        Args:
            html: Raw HTML string
            prefer_markdown: If True, try to get markdown directly from trafilatura
        """
        # CRITICAL FIX: Detect e-commerce/search/listing pages where trafilatura fails
        # Trafilatura is designed for ARTICLES, not product listings. It strips out
        # product results as "noise". We need to detect these pages and skip trafilatura.
        is_search_page = self._is_search_or_listing_page(html)
        if is_search_page:
            logger.info("[web_to_markdown] Detected search/listing page - skipping trafilatura")
            return self._extract_body_content(html)

        # Try trafilatura first (best for article extraction)
        if TRAFILATURA_AVAILABLE:
            try:
                # First try to get markdown directly (preserves formatting better)
                if prefer_markdown:
                    extracted = trafilatura.extract(
                        html,
                        include_links=True,
                        include_images=True,
                        include_tables=True,
                        include_formatting=True,
                        no_fallback=False,
                        output_format='markdown'
                    )
                    if extracted and len(extracted) > 200:
                        return extracted

                # Fall back to HTML extraction for more control
                extracted = trafilatura.extract(
                    html,
                    include_links=True,
                    include_images=True,
                    include_tables=True,
                    include_formatting=True,
                    no_fallback=False,
                    output_format='html'
                )
                if extracted and len(extracted) > 200:
                    return extracted
            except Exception as e:
                logger.debug(f"Trafilatura extraction failed: {e}")

        # Try readability-lxml
        if READABILITY_AVAILABLE:
            try:
                doc = ReadabilityDocument(html)
                content = doc.summary()
                if content and len(content) > 200:
                    return content
            except Exception as e:
                logger.debug(f"Readability extraction failed: {e}")

        # Fallback: extract body with basic noise removal
        # Try to find main content containers
        content_selectors = [
            r'<main[^>]*>(.*?)</main>',
            r'<article[^>]*>(.*?)</article>',
            r'<div[^>]*class="[^"]*content[^"]*"[^>]*>(.*?)</div>',
            r'<div[^>]*id="[^"]*content[^"]*"[^>]*>(.*?)</div>',
            r'<div[^>]*class="[^"]*post[^"]*"[^>]*>(.*?)</div>',
            r'<div[^>]*class="[^"]*entry[^"]*"[^>]*>(.*?)</div>',
            # E-commerce specific selectors
            r'<div[^>]*class="[^"]*search-result[^"]*"[^>]*>(.*?)</div>',
            r'<div[^>]*class="[^"]*product[^"]*"[^>]*>(.*?)</div>',
            r'<div[^>]*id="[^"]*search[^"]*"[^>]*>(.*?)</div>',
            r'<div[^>]*data-component-type="[^"]*search[^"]*"[^>]*>(.*?)</div>',
        ]

        for pattern in content_selectors:
            match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
            if match and len(match.group(1)) > 500:
                return match.group(0)

        # Last resort: return body with only basic cleanup (NOT aggressive filtering)
        body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL | re.IGNORECASE)
        if body_match:
            body_content = body_match.group(1)
            # Only remove scripts and styles, keep everything else
            body_content = re.sub(r'<script[^>]*>.*?</script>', '', body_content, flags=re.DOTALL | re.IGNORECASE)
            body_content = re.sub(r'<style[^>]*>.*?</style>', '', body_content, flags=re.DOTALL | re.IGNORECASE)
            body_content = re.sub(r'<noscript[^>]*>.*?</noscript>', '', body_content, flags=re.DOTALL | re.IGNORECASE)
            return body_content

        return html

    def _is_search_or_listing_page(self, html: str) -> bool:
        """
        Detect if the page is a search results or listing page.
        These pages need special handling because trafilatura strips out
        product listings as "noise".
        """
        html_lower = html.lower()

        # E-commerce indicators (Amazon, eBay, Target, etc.)
        ecommerce_patterns = [
            'data-component-type="s-search-result"',  # Amazon
            'data-cel-widget="search_result_',  # Amazon
            's-result-item',  # Amazon
            'product-listing',
            'search-result',
            'listing-card',
            'srp-result',  # eBay
            'job-card',  # Indeed
            'job-listing',
            'biz-listing',  # Yelp
            'yelp-review',
            'restaurant-card',
            'hotel-card',
            'property-card',
            'airbnb',
            'booking.com',
            'price-pod',  # Travel sites
            'flight-result',
        ]

        # Check for at least 2 indicators (more reliable than 1)
        match_count = sum(1 for pattern in ecommerce_patterns if pattern in html_lower)
        if match_count >= 2:
            return True

        # URL-based detection from title or meta tags
        url_indicators = [
            'amazon.com/s?',  # Amazon search
            '/search?',
            '/jobs',
            '/listings',
            '/results',
            'indeed.com',
            'yelp.com',
            'booking.com',
            'kayak.com',
            'expedia.com',
            'target.com',
            'ebay.com',
        ]
        for indicator in url_indicators:
            if indicator in html_lower:
                return True

        return False

    def _extract_body_content(self, html: str) -> str:
        """
        Extract body content directly, skipping article extraction algorithms.
        Used for search/listing pages where trafilatura strips too much.
        """
        # First try to find Amazon-specific search results container
        amazon_selectors = [
            r'<div[^>]*data-component-type="s-search-result"[^>]*>(.*?)</div>\s*</div>\s*</div>',
            r'<div[^>]*class="[^"]*s-result-item[^"]*"[^>]*>(.*?)</div>',
            r'<span[^>]*class="[^"]*a-size-medium[^"]*"[^>]*>(.*?)</span>',  # Product titles
        ]

        # Try to extract main search results container
        main_containers = [
            r'<div[^>]*id="search"[^>]*>(.*?)</div>\s*<div[^>]*id="rhf"',  # Amazon search results
            r'<div[^>]*id="s-results-list-atf"[^>]*>(.*?)</div>',  # Amazon alternate
            r'<div[^>]*class="[^"]*search-results[^"]*"[^>]*>(.*?)</div>',
            r'<div[^>]*id="searchResultsTable"[^>]*>(.*?)</div>',
            r'<div[^>]*data-testid="search-results"[^>]*>(.*?)</div>',
        ]

        for pattern in main_containers:
            match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
            if match and len(match.group(0)) > 5000:  # Must have substantial content
                content = match.group(0)
                # Clean up scripts and styles
                content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL | re.IGNORECASE)
                content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL | re.IGNORECASE)
                logger.info(f"[web_to_markdown] Found search results container: {len(content)} chars")
                return content

        # Fallback: extract full body with cleanup
        body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL | re.IGNORECASE)
        if body_match:
            body_content = body_match.group(1)
            # Remove scripts, styles, and noscript
            body_content = re.sub(r'<script[^>]*>.*?</script>', '', body_content, flags=re.DOTALL | re.IGNORECASE)
            body_content = re.sub(r'<style[^>]*>.*?</style>', '', body_content, flags=re.DOTALL | re.IGNORECASE)
            body_content = re.sub(r'<noscript[^>]*>.*?</noscript>', '', body_content, flags=re.DOTALL | re.IGNORECASE)
            # Remove nav, header, footer for cleaner content
            body_content = re.sub(r'<nav[^>]*>.*?</nav>', '', body_content, flags=re.DOTALL | re.IGNORECASE)
            body_content = re.sub(r'<header[^>]*>.*?</header>', '', body_content, flags=re.DOTALL | re.IGNORECASE)
            body_content = re.sub(r'<footer[^>]*>.*?</footer>', '', body_content, flags=re.DOTALL | re.IGNORECASE)
            logger.info(f"[web_to_markdown] Using body fallback: {len(body_content)} chars")
            return body_content

        return html

    def _remove_noise_html(self, html: str) -> str:
        """Remove noise elements from HTML before conversion."""
        result = html

        for pattern in self.noise_patterns:
            result = re.sub(pattern, '', result, flags=re.DOTALL | re.IGNORECASE)

        return result

    def _fit_markdown(self, markdown: str) -> str:
        """
        Apply heuristic filtering to create 'fit' markdown.
        Removes boilerplate, excessive whitespace, and noise.

        Inspired by Crawl4AI's fit_markdown concept.
        """
        lines = markdown.split('\n')
        filtered_lines = []

        for line in lines:
            stripped = line.strip()

            # Skip empty lines at start/end (keep one between paragraphs)
            if not stripped:
                if filtered_lines and filtered_lines[-1].strip():
                    filtered_lines.append('')
                continue

            # Skip boilerplate patterns
            skip = False
            for pattern in self.boilerplate_patterns:
                if re.match(pattern, stripped, re.IGNORECASE):
                    skip = True
                    break

            if skip:
                continue

            # Skip very short lines that look like navigation
            if len(stripped) < 3 and not stripped.startswith('#'):
                continue

            # Skip lines that are just special characters
            if re.match(r'^[\s\-_=\*\|\[\]]+$', stripped):
                continue

            # Skip excessive link-only lines (navigation)
            link_count = len(re.findall(r'\[([^\]]+)\]\([^)]+\)', stripped))
            word_count = len(stripped.split())
            if link_count > 3 and link_count / max(word_count, 1) > 0.5:
                continue

            filtered_lines.append(line)

        # Clean up excessive newlines
        result = '\n'.join(filtered_lines)
        result = re.sub(r'\n{4,}', '\n\n\n', result)

        return result

    def _expand_link_titles(self, html: str) -> str:
        """
        Expand link text with title attributes.
        Many sites (like books.toscrape.com) truncate displayed text but include
        full titles in the title attribute. This replaces truncated text with
        the full title when available.

        Example:
        <a href="..." title="A Light in the Attic">A Light in the ...</a>
        becomes:
        <a href="..." title="A Light in the Attic">A Light in the Attic</a>
        """
        def replace_link(match):
            full_tag = match.group(0)
            # Extract title attribute if present
            title_match = re.search(r'title="([^"]+)"', full_tag)
            if not title_match:
                return full_tag

            full_title = title_match.group(1)
            # Extract current link text
            text_match = re.search(r'>([^<]*)</a>', full_tag)
            if not text_match:
                return full_tag

            current_text = text_match.group(1).strip()

            # Check if text appears truncated (ends with ... or is much shorter than title)
            if (current_text.endswith('...') or
                current_text.endswith('…') or
                (len(current_text) < len(full_title) * 0.7 and len(full_title) > 20)):
                # Replace the text content with full title
                return re.sub(r'>([^<]*)</a>', f'>{full_title}</a>', full_tag)

            return full_tag

        # Match all anchor tags
        expanded = re.sub(r'<a\s+[^>]*>.*?</a>', replace_link, html, flags=re.DOTALL | re.IGNORECASE)
        return expanded

    def _basic_html_to_markdown(self, html: str) -> str:
        """Basic HTML to markdown conversion without external libraries."""
        text = html

        # Headers
        text = re.sub(r'<h1[^>]*>(.*?)</h1>', r'# \1\n', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<h2[^>]*>(.*?)</h2>', r'## \1\n', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<h3[^>]*>(.*?)</h3>', r'### \1\n', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<h4[^>]*>(.*?)</h4>', r'#### \1\n', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<h5[^>]*>(.*?)</h5>', r'##### \1\n', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<h6[^>]*>(.*?)</h6>', r'###### \1\n', text, flags=re.DOTALL | re.IGNORECASE)

        # Paragraphs and line breaks
        text = re.sub(r'<p[^>]*>(.*?)</p>', r'\1\n\n', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<div[^>]*>(.*?)</div>', r'\1\n', text, flags=re.DOTALL | re.IGNORECASE)

        # Links
        text = re.sub(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', r'[\2](\1)', text, flags=re.DOTALL | re.IGNORECASE)

        # Images
        text = re.sub(r'<img[^>]*alt="([^"]*)"[^>]*src="([^"]*)"[^>]*/?>', r'![\1](\2)', text, flags=re.IGNORECASE)
        text = re.sub(r'<img[^>]*src="([^"]*)"[^>]*alt="([^"]*)"[^>]*/?>', r'![\2](\1)', text, flags=re.IGNORECASE)
        text = re.sub(r'<img[^>]*src="([^"]*)"[^>]*/?>', r'![image](\1)', text, flags=re.IGNORECASE)

        # Bold and italic
        text = re.sub(r'<strong[^>]*>(.*?)</strong>', r'**\1**', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<b[^>]*>(.*?)</b>', r'**\1**', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<em[^>]*>(.*?)</em>', r'*\1*', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<i[^>]*>(.*?)</i>', r'*\1*', text, flags=re.DOTALL | re.IGNORECASE)

        # Lists
        text = re.sub(r'<li[^>]*>(.*?)</li>', r'- \1\n', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<ul[^>]*>(.*?)</ul>', r'\1\n', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<ol[^>]*>(.*?)</ol>', r'\1\n', text, flags=re.DOTALL | re.IGNORECASE)

        # Code
        text = re.sub(r'<code[^>]*>(.*?)</code>', r'`\1`', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<pre[^>]*>(.*?)</pre>', r'```\n\1\n```', text, flags=re.DOTALL | re.IGNORECASE)

        # Blockquotes
        text = re.sub(r'<blockquote[^>]*>(.*?)</blockquote>', r'> \1\n', text, flags=re.DOTALL | re.IGNORECASE)

        # Horizontal rules
        text = re.sub(r'<hr[^>]*/?>', '\n---\n', text, flags=re.IGNORECASE)

        # Remove remaining HTML tags
        text = re.sub(r'<[^>]+>', '', text)

        # Decode HTML entities
        text = text.replace('&nbsp;', ' ')
        text = text.replace('&lt;', '<')
        text = text.replace('&gt;', '>')
        text = text.replace('&amp;', '&')
        text = text.replace('&quot;', '"')
        text = text.replace('&#39;', "'")

        # Clean up whitespace
        text = re.sub(r' +', ' ', text)
        text = re.sub(r'\n +', '\n', text)
        text = re.sub(r'\n{3,}', '\n\n', text)

        return text.strip()

    def _extract_links(self, html: str) -> List[Dict[str, str]]:
        """Extract all links from HTML."""
        links = []
        pattern = r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>'

        for match in re.finditer(pattern, html, re.DOTALL | re.IGNORECASE):
            href = match.group(1)
            text = re.sub(r'<[^>]+>', '', match.group(2)).strip()

            if href and not href.startswith('#') and not href.startswith('javascript:'):
                links.append({
                    'href': href,
                    'text': text[:100] if text else ''
                })

        return links[:50]  # Limit to 50 links

    def _extract_images(self, html: str) -> List[Dict[str, str]]:
        """Extract all images from HTML."""
        images = []
        pattern = r'<img[^>]*src="([^"]*)"[^>]*>'

        for match in re.finditer(pattern, html, re.IGNORECASE):
            src = match.group(1)
            # Try to get alt text
            alt_match = re.search(r'alt="([^"]*)"', match.group(0), re.IGNORECASE)
            alt = alt_match.group(1) if alt_match else ''

            if src and not src.startswith('data:'):
                images.append({
                    'src': src,
                    'alt': alt
                })

        return images[:20]  # Limit to 20 images

    async def _extract_metadata(self, page) -> Dict[str, Any]:
        """Extract metadata from page."""
        try:
            metadata = await page.evaluate("""
                () => {
                    const getMeta = (names) => {
                        for (const name of names) {
                            const el = document.querySelector(`meta[property="${name}"], meta[name="${name}"]`);
                            if (el?.content) return el.content;
                        }
                        return '';
                    };

                    return {
                        description: getMeta(['og:description', 'description', 'twitter:description']),
                        author: getMeta(['author', 'og:author', 'article:author']),
                        published: getMeta(['article:published_time', 'date', 'pubdate']),
                        siteName: getMeta(['og:site_name']),
                        type: getMeta(['og:type']),
                        image: getMeta(['og:image', 'twitter:image']),
                        locale: getMeta(['og:locale']),
                        keywords: getMeta(['keywords'])
                    };
                }
            """)
            return metadata
        except Exception:
            return {}


# Convenience function for quick conversions
async def url_to_markdown(
    playwright_client,
    url: str,
    target_selector: Optional[str] = None,
    fit_markdown: bool = True
) -> Dict[str, Any]:
    """
    Jina Reader-style: Convert URL to LLM-friendly markdown.

    Usage:
        result = await url_to_markdown(browser, "https://example.com")
        print(result['markdown'])

    Like Jina's r.jina.ai prefix, but as a function.
    """
    converter = WebToMarkdown()

    # Navigate to URL
    await playwright_client.navigate(url)

    # Convert page to markdown
    result = await converter.convert(
        playwright_client.page,
        target_selector=target_selector,
        fit_markdown=fit_markdown
    )

    return result


def html_to_markdown(html: str, fit_markdown: bool = True) -> str:
    """
    Quick helper: Convert HTML string to markdown.

    Usage:
        md = html_to_markdown("<h1>Hello</h1><p>World</p>")
    """
    converter = WebToMarkdown()
    result = converter.convert_html(html, fit_markdown=fit_markdown)
    return result['markdown']
