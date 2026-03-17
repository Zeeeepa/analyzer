"""
Site Mapper - Firecrawl Map Endpoint Style
Quickly discover all URLs on a website.

Inspired by:
- Firecrawl's /map endpoint - Get all URLs from a site fast
- Crawl4AI's graph crawler - Smart traversal

Features:
1. Fast URL discovery (sitemap.xml, HTML parsing)
2. URL categorization (pages, blog, products, etc.)
3. Depth-limited crawling
4. Intelligent filtering (skip images, assets)
"""

import re
import asyncio
from typing import Dict, List, Any, Optional, Set
from urllib.parse import urljoin, urlparse
from loguru import logger

# Try to import xml parser
try:
    import xml.etree.ElementTree as ET
    XML_AVAILABLE = True
except ImportError:
    XML_AVAILABLE = False


class SiteMapper:
    """
    Fast URL discovery for websites.

    Usage:
        mapper = SiteMapper()
        urls = await mapper.map_site(browser, "https://example.com")
    """

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.max_urls = config.get('max_urls', 500) if config else 500
        self.max_depth = config.get('max_depth', 3) if config else 3

        # URL patterns to skip
        self.skip_patterns = [
            r'\.(jpg|jpeg|png|gif|svg|ico|webp|bmp)$',
            r'\.(css|js|woff|woff2|ttf|eot)$',
            r'\.(pdf|doc|docx|xls|xlsx|ppt|pptx)$',
            r'\.(zip|tar|gz|rar)$',
            r'\.(mp3|mp4|wav|avi|mov|wmv)$',
            r'#',  # Skip anchors
            r'\?.*utm_',  # Skip tracking params
            r'/wp-admin/',
            r'/wp-json/',
            r'/feed/',
            r'/cdn-cgi/',
            r'/tag/',  # Often redundant tag pages
            r'/author/',  # Author archive pages
            r'/page/\d+',  # Pagination (optional)
        ]

        # URL categorization patterns
        self.category_patterns = {
            'blog': [r'/blog/', r'/posts/', r'/articles/', r'/news/'],
            'product': [r'/product/', r'/products/', r'/shop/', r'/item/', r'/store/'],
            'category': [r'/category/', r'/categories/', r'/collection/'],
            'about': [r'/about', r'/team/', r'/company/', r'/story/'],
            'contact': [r'/contact', r'/support/', r'/help/'],
            'legal': [r'/privacy', r'/terms', r'/policy', r'/legal/'],
            'pricing': [r'/pricing', r'/plans/', r'/packages/'],
            'features': [r'/features/', r'/solutions/', r'/services/'],
            'docs': [r'/docs/', r'/documentation/', r'/api/', r'/guide/'],
            'careers': [r'/careers/', r'/jobs/', r'/hiring/'],
        }

    async def map_site(
        self,
        playwright_client,
        url: str,
        max_urls: Optional[int] = None,
        max_depth: Optional[int] = None,
        include_sitemap: bool = True,
        categorize: bool = True
    ) -> Dict[str, Any]:
        """
        Map all URLs on a website.

        Args:
            playwright_client: PlaywrightClient instance
            url: Base URL to map
            max_urls: Maximum URLs to discover
            max_depth: Maximum crawl depth
            include_sitemap: Try to fetch sitemap.xml
            categorize: Categorize discovered URLs

        Returns:
            {
                'urls': List[str],
                'categorized': Dict[str, List[str]],
                'count': int,
                'base_url': str,
                'sitemap_found': bool
            }
        """
        max_urls = max_urls or self.max_urls
        max_depth = max_depth or self.max_depth

        # Parse base URL
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        domain = parsed.netloc

        discovered_urls: Set[str] = set()
        categorized: Dict[str, List[str]] = {cat: [] for cat in self.category_patterns.keys()}
        categorized['other'] = []
        sitemap_found = False

        try:
            # Step 1: Try to fetch sitemap.xml (fastest method)
            if include_sitemap:
                sitemap_urls = await self._fetch_sitemap(playwright_client, base_url)
                if sitemap_urls:
                    sitemap_found = True
                    for u in sitemap_urls[:max_urls]:
                        if self._is_valid_url(u, domain):
                            discovered_urls.add(u)

                    logger.info(f"Found {len(sitemap_urls)} URLs in sitemap")

            # Step 2: Crawl homepage for additional links
            if len(discovered_urls) < max_urls:
                homepage_urls = await self._extract_links_from_page(
                    playwright_client, url, domain
                )
                for u in homepage_urls:
                    if len(discovered_urls) >= max_urls:
                        break
                    if self._is_valid_url(u, domain):
                        discovered_urls.add(u)

            # Step 3: Crawl discovered pages (limited depth)
            if max_depth > 1 and len(discovered_urls) < max_urls:
                to_crawl = list(discovered_urls)[:50]  # Limit pages to crawl
                for page_url in to_crawl:
                    if len(discovered_urls) >= max_urls:
                        break
                    try:
                        page_urls = await self._extract_links_from_page(
                            playwright_client, page_url, domain
                        )
                        for u in page_urls:
                            if len(discovered_urls) >= max_urls:
                                break
                            if self._is_valid_url(u, domain):
                                discovered_urls.add(u)
                    except Exception as e:
                        logger.debug(f"Error crawling {page_url}: {e}")
                        continue

            # Step 4: Categorize URLs
            if categorize:
                for u in discovered_urls:
                    category = self._categorize_url(u)
                    categorized[category].append(u)

            return {
                'urls': sorted(list(discovered_urls)),
                'categorized': {k: v for k, v in categorized.items() if v},
                'count': len(discovered_urls),
                'base_url': base_url,
                'domain': domain,
                'sitemap_found': sitemap_found
            }

        except Exception as e:
            logger.error(f"Site mapping error: {e}")
            return {
                'error': str(e),
                'urls': list(discovered_urls),
                'count': len(discovered_urls),
                'base_url': base_url
            }

    async def _fetch_sitemap(
        self,
        playwright_client,
        base_url: str
    ) -> List[str]:
        """Fetch and parse sitemap.xml"""
        urls = []
        sitemap_urls_to_try = [
            f"{base_url}/sitemap.xml",
            f"{base_url}/sitemap_index.xml",
            f"{base_url}/sitemap-index.xml",
            f"{base_url}/sitemap1.xml",
        ]

        for sitemap_url in sitemap_urls_to_try:
            try:
                result = await playwright_client.navigate(sitemap_url)
                if result.get('error'):
                    continue

                # Get page content
                content_result = await playwright_client.get_content()
                if content_result.get('error'):
                    continue

                content = content_result.get('content', '')

                # Check if it's XML
                if '<?xml' in content or '<urlset' in content or '<sitemapindex' in content:
                    # Parse sitemap
                    parsed_urls = self._parse_sitemap_xml(content)
                    urls.extend(parsed_urls)

                    # Check for sitemap index (nested sitemaps)
                    if '<sitemapindex' in content:
                        nested_sitemaps = self._extract_nested_sitemaps(content)
                        for nested in nested_sitemaps[:5]:  # Limit nested sitemaps
                            try:
                                await playwright_client.navigate(nested)
                                nested_content = await playwright_client.get_content()
                                if nested_content.get('content'):
                                    nested_urls = self._parse_sitemap_xml(nested_content['content'])
                                    urls.extend(nested_urls)
                            except Exception:
                                continue

                    if urls:
                        return urls

            except Exception as e:
                logger.debug(f"Sitemap fetch error for {sitemap_url}: {e}")
                continue

        return urls

    def _parse_sitemap_xml(self, xml_content: str) -> List[str]:
        """Parse sitemap XML and extract URLs."""
        urls = []

        try:
            # Try XML parsing
            if XML_AVAILABLE:
                # Remove namespace for easier parsing
                xml_content = re.sub(r'xmlns="[^"]+"', '', xml_content)
                root = ET.fromstring(xml_content)

                for url_elem in root.findall('.//url/loc'):
                    if url_elem.text:
                        urls.append(url_elem.text.strip())

        except Exception:
            pass

        # Fallback: regex extraction
        if not urls:
            loc_pattern = r'<loc>([^<]+)</loc>'
            matches = re.findall(loc_pattern, xml_content)
            urls = [m.strip() for m in matches if m.strip()]

        return urls

    def _extract_nested_sitemaps(self, xml_content: str) -> List[str]:
        """Extract nested sitemap URLs from sitemap index."""
        sitemaps = []

        try:
            if XML_AVAILABLE:
                xml_content = re.sub(r'xmlns="[^"]+"', '', xml_content)
                root = ET.fromstring(xml_content)

                for sitemap_elem in root.findall('.//sitemap/loc'):
                    if sitemap_elem.text:
                        sitemaps.append(sitemap_elem.text.strip())

        except Exception:
            pass

        if not sitemaps:
            loc_pattern = r'<loc>([^<]+\.xml[^<]*)</loc>'
            matches = re.findall(loc_pattern, xml_content)
            sitemaps = [m.strip() for m in matches if m.strip()]

        return sitemaps

    async def _extract_links_from_page(
        self,
        playwright_client,
        url: str,
        domain: str
    ) -> List[str]:
        """Extract all links from a page."""
        urls = []

        try:
            result = await playwright_client.navigate(url)
            if result.get('error'):
                return urls

            # Extract links via JavaScript
            links_result = await playwright_client.evaluate("""
                () => {
                    const links = [];
                    const anchors = document.querySelectorAll('a[href]');

                    anchors.forEach(a => {
                        const href = a.href;
                        if (href && href.startsWith('http')) {
                            links.push(href);
                        }
                    });

                    return [...new Set(links)];
                }
            """)

            if links_result.get('result'):
                for link in links_result['result']:
                    if self._is_same_domain(link, domain):
                        urls.append(link)

        except Exception as e:
            logger.debug(f"Link extraction error for {url}: {e}")

        return urls

    def _is_valid_url(self, url: str, domain: str) -> bool:
        """Check if URL should be included in the map."""
        # Must be same domain
        if not self._is_same_domain(url, domain):
            return False

        # Skip patterns
        url_lower = url.lower()
        for pattern in self.skip_patterns:
            if re.search(pattern, url_lower):
                return False

        return True

    def _is_same_domain(self, url: str, domain: str) -> bool:
        """Check if URL belongs to the same domain."""
        try:
            parsed = urlparse(url)
            url_domain = parsed.netloc.lower()
            domain = domain.lower()

            # Handle www prefix
            url_domain = url_domain.replace('www.', '')
            domain = domain.replace('www.', '')

            return url_domain == domain
        except Exception:
            return False

    def _categorize_url(self, url: str) -> str:
        """Categorize URL based on path patterns."""
        url_lower = url.lower()

        for category, patterns in self.category_patterns.items():
            for pattern in patterns:
                if re.search(pattern, url_lower):
                    return category

        return 'other'


class AdaptiveCrawler:
    """
    Intelligent crawler that stops when it has enough information.

    Inspired by Crawl4AI's adaptive crawling with information foraging.
    """

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.min_content_threshold = config.get('min_content', 1000) if config else 1000
        self.max_pages = config.get('max_pages', 20) if config else 20
        self.relevance_threshold = config.get('relevance_threshold', 0.3) if config else 0.3

    async def crawl_for_info(
        self,
        playwright_client,
        start_url: str,
        target_info: str,
        max_pages: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Crawl adaptively, stopping when enough relevant info is found.

        Args:
            playwright_client: Browser client
            start_url: Starting URL
            target_info: Description of info being sought (e.g., "pricing information")
            max_pages: Maximum pages to visit

        Returns:
            {
                'content': str,  # Aggregated relevant content
                'pages_visited': int,
                'urls_visited': List[str],
                'stopped_reason': str
            }
        """
        max_pages = max_pages or self.max_pages

        visited: Set[str] = set()
        to_visit: List[str] = [start_url]
        collected_content: List[str] = []
        content_score = 0

        # Keywords from target_info for relevance scoring
        target_keywords = set(target_info.lower().split())

        while to_visit and len(visited) < max_pages:
            url = to_visit.pop(0)

            if url in visited:
                continue

            visited.add(url)

            try:
                # Navigate and extract content
                await playwright_client.navigate(url)
                text_result = await playwright_client.get_text()

                if text_result.get('error'):
                    continue

                text = text_result.get('text', '')

                # Score relevance
                relevance = self._score_relevance(text, target_keywords)

                if relevance >= self.relevance_threshold:
                    collected_content.append(f"\n--- From {url} ---\n{text[:2000]}")
                    content_score += relevance

                    # Check if we have enough
                    total_content = '\n'.join(collected_content)
                    if len(total_content) >= self.min_content_threshold and content_score > 2:
                        return {
                            'content': total_content,
                            'pages_visited': len(visited),
                            'urls_visited': list(visited),
                            'stopped_reason': 'sufficient_content',
                            'relevance_score': content_score
                        }

                # Find more URLs to visit
                links_result = await playwright_client.evaluate("""
                    () => Array.from(document.querySelectorAll('a[href]'))
                        .map(a => a.href)
                        .filter(h => h.startsWith('http'))
                        .slice(0, 20)
                """)

                if links_result.get('result'):
                    # Prioritize URLs that seem relevant
                    new_urls = links_result['result']
                    scored_urls = [
                        (u, self._score_url_relevance(u, target_keywords))
                        for u in new_urls
                        if u not in visited and u not in to_visit
                    ]
                    scored_urls.sort(key=lambda x: x[1], reverse=True)
                    to_visit.extend([u for u, s in scored_urls[:5]])

            except Exception as e:
                logger.debug(f"Adaptive crawl error for {url}: {e}")
                continue

        return {
            'content': '\n'.join(collected_content),
            'pages_visited': len(visited),
            'urls_visited': list(visited),
            'stopped_reason': 'max_pages_reached' if len(visited) >= max_pages else 'no_more_urls',
            'relevance_score': content_score
        }

    def _score_relevance(self, text: str, keywords: Set[str]) -> float:
        """Score text relevance to target keywords."""
        if not text:
            return 0

        text_lower = text.lower()
        text_words = set(text_lower.split())

        # Count keyword matches
        matches = len(keywords.intersection(text_words))

        # Normalize by keyword count
        if len(keywords) == 0:
            return 0

        return matches / len(keywords)

    def _score_url_relevance(self, url: str, keywords: Set[str]) -> float:
        """Score URL path relevance to target keywords."""
        url_lower = url.lower()

        score = 0
        for keyword in keywords:
            if keyword in url_lower:
                score += 1

        return score


# Convenience functions
async def map_site(playwright_client, url: str, max_urls: int = 500) -> Dict[str, Any]:
    """
    Quick site mapping (like Firecrawl's /map endpoint).

    Usage:
        urls = await map_site(browser, "https://example.com")
    """
    mapper = SiteMapper()
    return await mapper.map_site(playwright_client, url, max_urls=max_urls)


async def crawl_for(
    playwright_client,
    url: str,
    looking_for: str,
    max_pages: int = 10
) -> Dict[str, Any]:
    """
    Adaptive crawl looking for specific information.

    Usage:
        result = await crawl_for(browser, "https://example.com", "pricing information")
    """
    crawler = AdaptiveCrawler()
    return await crawler.crawl_for_info(playwright_client, url, looking_for, max_pages)
