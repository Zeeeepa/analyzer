"""
Web Daemon Microservice - Isolated Web Operations Layer

Based on Reddit LocalLLaMA research on isolating web operations from LLM context.
The LLM only calls one tool: web_search_and_fetch. This daemon handles all complexity:
- Multiple collector backends with auto-fallback
- Caching with TTL to share fetches across tasks
- Rate limiting per domain
- Logging for replay/training

Architecture:
    LLM -> web_search_and_fetch -> WebDaemon -> [Collectors] -> Web
"""

import asyncio
import hashlib
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Set
from urllib.parse import urlparse

# Optional imports for different collectors
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from playwright.async_api import async_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


logger = logging.getLogger(__name__)


class CollectorType(Enum):
    """Available collector backends."""
    SIMPLE_HTTP = "simple_http"
    PLAYWRIGHT = "playwright"
    ALT_FRONTEND = "alt_frontend"
    AUTO = "auto"


class SearchEngine(Enum):
    """Supported search engines."""
    BING = "bing"
    GOOGLE = "google"
    DUCKDUCKGO = "duckduckgo"


@dataclass
class WebResult:
    """Result from a web fetch operation."""
    content: str
    url: str
    cached: bool
    collector_used: str
    timestamp: datetime = field(default_factory=datetime.now)
    error: Optional[str] = None
    status_code: Optional[int] = None

    @property
    def success(self) -> bool:
        """Whether the fetch was successful."""
        return self.error is None and self.content is not None


@dataclass
class SearchResult:
    """Single search result."""
    title: str
    url: str
    snippet: str
    rank: int


@dataclass
class CacheEntry:
    """Cache entry with TTL."""
    result: WebResult
    expires_at: datetime
    access_count: int = 0

    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        return datetime.now() > self.expires_at

    def touch(self) -> None:
        """Update access count."""
        self.access_count += 1


@dataclass
class RateLimitState:
    """Rate limiting state per domain."""
    domain: str
    requests: List[float] = field(default_factory=list)
    max_requests_per_minute: int = 10

    def can_request(self) -> bool:
        """Check if we can make a request to this domain."""
        now = time.time()
        # Remove requests older than 1 minute
        self.requests = [ts for ts in self.requests if now - ts < 60]
        return len(self.requests) < self.max_requests_per_minute

    def record_request(self) -> None:
        """Record a new request."""
        self.requests.append(time.time())

    def wait_time(self) -> float:
        """Calculate how long to wait before next request."""
        if self.can_request():
            return 0.0
        now = time.time()
        self.requests = [ts for ts in self.requests if now - ts < 60]
        if not self.requests:
            return 0.0
        # Wait until the oldest request expires
        oldest = min(self.requests)
        return max(0.0, 60 - (now - oldest))


class BaseCollector(ABC):
    """Base class for all web collectors."""

    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(f"{__name__}.{name}")

    @abstractmethod
    async def fetch(self, url: str) -> WebResult:
        """Fetch content from URL."""
        pass

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Check if this collector can handle the given URL."""
        pass

    def _clean_content(self, html: str) -> str:
        """Convert HTML to clean markdown-like text.

        This is a simple implementation. In production, you'd use
        libraries like html2text, trafilatura, or readability.
        """
        # Simple text extraction (replace with proper HTML->markdown library)
        import re

        # Remove script and style tags
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)

        # Remove HTML tags
        text = re.sub(r'<[^>]+>', ' ', text)

        # Decode common HTML entities
        text = text.replace('&nbsp;', ' ')
        text = text.replace('&lt;', '<')
        text = text.replace('&gt;', '>')
        text = text.replace('&amp;', '&')
        text = text.replace('&quot;', '"')

        # Clean up whitespace
        text = re.sub(r'\n\s*\n+', '\n\n', text)
        text = re.sub(r' +', ' ', text)

        return text.strip()


class SimpleHttpCollector(BaseCollector):
    """Simple HTTP collector using requests library."""

    def __init__(self):
        super().__init__("simple_http")
        if not HAS_REQUESTS:
            raise ImportError("requests library not available")
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    async def fetch(self, url: str) -> WebResult:
        """Fetch content using requests."""
        try:
            # Run requests in thread pool since it's blocking
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.session.get(url, timeout=30)
            )
            response.raise_for_status()

            content = self._clean_content(response.text)

            return WebResult(
                content=content,
                url=url,
                cached=False,
                collector_used=self.name,
                status_code=response.status_code
            )
        except Exception as e:
            self.logger.error(f"Failed to fetch {url}: {e}")
            return WebResult(
                content="",
                url=url,
                cached=False,
                collector_used=self.name,
                error=str(e)
            )

    def can_handle(self, url: str) -> bool:
        """Can handle most URLs."""
        return HAS_REQUESTS


class PlaywrightCollector(BaseCollector):
    """Playwright collector for JS-heavy pages."""

    def __init__(self):
        super().__init__("playwright")
        if not HAS_PLAYWRIGHT:
            raise ImportError("playwright library not available")
        self._playwright = None
        self._browser = None

    async def _ensure_browser(self):
        """Ensure browser is initialized."""
        if self._browser is None:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True)

    async def fetch(self, url: str) -> WebResult:
        """Fetch content using Playwright."""
        try:
            await self._ensure_browser()

            page = await self._browser.new_page()
            await page.goto(url, wait_until="networkidle", timeout=30000)

            # Get text content
            content = await page.content()
            await page.close()

            content = self._clean_content(content)

            return WebResult(
                content=content,
                url=url,
                cached=False,
                collector_used=self.name,
                status_code=200
            )
        except Exception as e:
            self.logger.error(f"Failed to fetch {url} with Playwright: {e}")
            return WebResult(
                content="",
                url=url,
                cached=False,
                collector_used=self.name,
                error=str(e)
            )

    def can_handle(self, url: str) -> bool:
        """Can handle any URL if Playwright is available."""
        return HAS_PLAYWRIGHT

    async def close(self):
        """Clean up browser resources."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()


class AltFrontendCollector(BaseCollector):
    """Collector that uses alternative frontends for blocked sites."""

    # Mapping of domains to alternative frontends
    ALT_FRONTENDS = {
        'reddit.com': ['redlib.tux.pizza', 'libreddit.spike.codes'],
        'www.reddit.com': ['redlib.tux.pizza', 'libreddit.spike.codes'],
        'twitter.com': ['nitter.net', 'nitter.1d4.us'],
        'x.com': ['nitter.net', 'nitter.1d4.us'],
        'youtube.com': ['invidious.snopyta.org', 'yewtu.be'],
        'www.youtube.com': ['invidious.snopyta.org', 'yewtu.be'],
        'medium.com': ['scribe.rip'],
    }

    def __init__(self):
        super().__init__("alt_frontend")
        if not HAS_REQUESTS:
            raise ImportError("requests library not available")
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    def _get_alt_url(self, url: str) -> Optional[str]:
        """Convert URL to alternative frontend."""
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        if domain in self.ALT_FRONTENDS:
            # Try first alternative
            alt_domain = self.ALT_FRONTENDS[domain][0]
            alt_url = url.replace(domain, alt_domain)
            return alt_url

        return None

    async def fetch(self, url: str) -> WebResult:
        """Fetch content using alternative frontend."""
        alt_url = self._get_alt_url(url)

        if not alt_url:
            return WebResult(
                content="",
                url=url,
                cached=False,
                collector_used=self.name,
                error="No alternative frontend available"
            )

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.session.get(alt_url, timeout=30)
            )
            response.raise_for_status()

            content = self._clean_content(response.text)

            return WebResult(
                content=content,
                url=url,  # Return original URL
                cached=False,
                collector_used=self.name,
                status_code=response.status_code
            )
        except Exception as e:
            self.logger.error(f"Failed to fetch {alt_url}: {e}")
            return WebResult(
                content="",
                url=url,
                cached=False,
                collector_used=self.name,
                error=str(e)
            )

    def can_handle(self, url: str) -> bool:
        """Can handle URLs with known alternative frontends."""
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        return domain in self.ALT_FRONTENDS and HAS_REQUESTS


class CollectorRegistry:
    """Registry of collectors with auto-fallback logic."""

    def __init__(self):
        self.collectors: List[BaseCollector] = []
        self._initialize_collectors()

    def _initialize_collectors(self):
        """Initialize available collectors."""
        # Try to initialize collectors in order of preference
        collectors_to_try = [
            (SimpleHttpCollector, "simple_http"),
            (AltFrontendCollector, "alt_frontend"),
            (PlaywrightCollector, "playwright"),
        ]

        for collector_class, name in collectors_to_try:
            try:
                collector = collector_class()
                self.collectors.append(collector)
                logger.info(f"Initialized collector: {name}")
            except ImportError as e:
                logger.warning(f"Collector {name} not available: {e}")
            except Exception as e:
                logger.error(f"Failed to initialize collector {name}: {e}")

    def get_collectors_for_url(self, url: str) -> List[BaseCollector]:
        """Get collectors that can handle this URL, ordered by preference."""
        collectors = [c for c in self.collectors if c.can_handle(url)]

        # Prioritize alt_frontend for known problematic sites
        alt_frontend = next((c for c in collectors if c.name == "alt_frontend"), None)
        if alt_frontend:
            parsed = urlparse(url)
            if parsed.netloc.lower() in AltFrontendCollector.ALT_FRONTENDS:
                # Move alt_frontend to front
                collectors = [alt_frontend] + [c for c in collectors if c != alt_frontend]

        return collectors

    async def fetch_with_fallback(self, url: str, preferred_collector: Optional[str] = None) -> WebResult:
        """Fetch URL with automatic fallback to other collectors."""
        collectors = self.get_collectors_for_url(url)

        if not collectors:
            return WebResult(
                content="",
                url=url,
                cached=False,
                collector_used="none",
                error="No collectors available"
            )

        # If preferred collector specified, try it first
        if preferred_collector:
            preferred = next((c for c in collectors if c.name == preferred_collector), None)
            if preferred:
                collectors = [preferred] + [c for c in collectors if c != preferred]

        # Try each collector until one succeeds
        errors = []
        for collector in collectors:
            logger.info(f"Trying collector {collector.name} for {url}")
            result = await collector.fetch(url)

            if result.success:
                logger.info(f"Successfully fetched {url} with {collector.name}")
                return result

            errors.append(f"{collector.name}: {result.error}")
            logger.warning(f"Collector {collector.name} failed: {result.error}")

        # All collectors failed
        return WebResult(
            content="",
            url=url,
            cached=False,
            collector_used="none",
            error=f"All collectors failed: {'; '.join(errors)}"
        )

    async def close(self):
        """Clean up all collectors."""
        for collector in self.collectors:
            if hasattr(collector, 'close'):
                await collector.close()


class WebCache:
    """Cache for web results with TTL."""

    def __init__(self, default_ttl_minutes: int = 15):
        self.default_ttl = timedelta(minutes=default_ttl_minutes)
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = asyncio.Lock()

    def _get_cache_key(self, url: str) -> str:
        """Generate cache key from URL."""
        return hashlib.sha256(url.encode()).hexdigest()

    async def get(self, url: str) -> Optional[WebResult]:
        """Get cached result if available and not expired."""
        async with self._lock:
            key = self._get_cache_key(url)
            entry = self._cache.get(key)

            if entry is None:
                return None

            if entry.is_expired():
                del self._cache[key]
                logger.debug(f"Cache expired for {url}")
                return None

            entry.touch()
            logger.info(f"Cache hit for {url} (accessed {entry.access_count} times)")

            # Return a copy with cached flag set
            result = entry.result
            result.cached = True
            return result

    async def set(self, url: str, result: WebResult, ttl: Optional[timedelta] = None) -> None:
        """Store result in cache."""
        async with self._lock:
            key = self._get_cache_key(url)
            ttl = ttl or self.default_ttl
            expires_at = datetime.now() + ttl

            self._cache[key] = CacheEntry(
                result=result,
                expires_at=expires_at
            )

            logger.debug(f"Cached {url} until {expires_at}")

    async def clear_expired(self) -> int:
        """Clear expired entries. Returns number of entries removed."""
        async with self._lock:
            before = len(self._cache)
            self._cache = {
                k: v for k, v in self._cache.items()
                if not v.is_expired()
            }
            removed = before - len(self._cache)
            if removed > 0:
                logger.info(f"Cleared {removed} expired cache entries")
            return removed

    async def stats(self) -> Dict:
        """Get cache statistics."""
        async with self._lock:
            total = len(self._cache)
            expired = sum(1 for e in self._cache.values() if e.is_expired())
            total_accesses = sum(e.access_count for e in self._cache.values())

            return {
                'total_entries': total,
                'expired_entries': expired,
                'active_entries': total - expired,
                'total_accesses': total_accesses
            }


class RateLimiter:
    """Rate limiter per domain."""

    def __init__(self):
        self._limits: Dict[str, RateLimitState] = {}
        self._lock = asyncio.Lock()

    def _get_domain(self, url: str) -> str:
        """Extract domain from URL."""
        parsed = urlparse(url)
        return parsed.netloc.lower()

    async def wait_if_needed(self, url: str) -> float:
        """Wait if rate limit exceeded. Returns wait time."""
        domain = self._get_domain(url)

        async with self._lock:
            if domain not in self._limits:
                self._limits[domain] = RateLimitState(domain=domain)

            limit_state = self._limits[domain]

            if not limit_state.can_request():
                wait_time = limit_state.wait_time()
                if wait_time > 0:
                    logger.info(f"Rate limit for {domain}, waiting {wait_time:.1f}s")
                    await asyncio.sleep(wait_time)
                    return wait_time

            limit_state.record_request()
            return 0.0


class WebDaemon:
    """
    Isolated web microservice - LLM never touches raw HTTP.

    Provides a single entry point for all web operations with:
    - Multiple collector backends with auto-fallback
    - Caching with TTL to share fetches across tasks
    - Rate limiting per domain
    - Logging for replay/training

    Usage:
        daemon = WebDaemon()
        result = await daemon.fetch("https://example.com")
        results = await daemon.search("python async", engine="bing")
    """

    def __init__(
        self,
        cache_ttl_minutes: int = 15,
        enable_logging: bool = True,
        log_file: Optional[str] = None
    ):
        self.cache = WebCache(default_ttl_minutes=cache_ttl_minutes)
        self.registry = CollectorRegistry()
        self.rate_limiter = RateLimiter()
        self.enable_logging = enable_logging
        self.log_file = log_file

        # Set up logging
        if enable_logging:
            self._setup_logging()

        # Background task for cache cleanup
        self._cleanup_task: Optional[asyncio.Task] = None

    def _setup_logging(self):
        """Set up logging for replay/training."""
        if self.log_file:
            handler = logging.FileHandler(self.log_file)
            handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            ))
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)

    async def fetch(
        self,
        url: str,
        collector: str = "auto",
        force_refresh: bool = False
    ) -> WebResult:
        """
        Fetch content from URL.

        Args:
            url: URL to fetch
            collector: Collector to use ("auto", "simple_http", "playwright", "alt_frontend")
            force_refresh: Skip cache and fetch fresh content

        Returns:
            WebResult with content and metadata
        """
        # Check cache first
        if not force_refresh:
            cached = await self.cache.get(url)
            if cached:
                logger.info(f"Returning cached result for {url}")
                return cached

        # Rate limiting
        await self.rate_limiter.wait_if_needed(url)

        # Fetch with collector
        preferred_collector = None if collector == "auto" else collector
        result = await self.registry.fetch_with_fallback(url, preferred_collector)

        # Cache successful results
        if result.success:
            await self.cache.set(url, result)

        # Log for replay/training
        if self.enable_logging:
            logger.info(
                f"Fetch completed: url={url}, "
                f"collector={result.collector_used}, "
                f"cached={result.cached}, "
                f"success={result.success}, "
                f"content_length={len(result.content) if result.content else 0}"
            )

        return result

    async def search(
        self,
        query: str,
        engine: str = "bing",
        max_results: int = 10
    ) -> List[SearchResult]:
        """
        Search the web.

        Args:
            query: Search query
            engine: Search engine to use ("bing", "google", "duckduckgo")
            max_results: Maximum number of results to return

        Returns:
            List of SearchResult objects

        Note:
            This is a placeholder. In production, you'd integrate with
            actual search APIs (Bing API, Google Custom Search, etc.)
        """
        logger.info(f"Search: query='{query}', engine={engine}, max_results={max_results}")

        # Placeholder implementation
        # In production, integrate with actual search APIs
        results = [
            SearchResult(
                title=f"Result {i+1} for {query}",
                url=f"https://example.com/result{i+1}",
                snippet=f"This is a placeholder result {i+1} for query: {query}",
                rank=i+1
            )
            for i in range(min(3, max_results))
        ]

        logger.warning(
            "Search is using placeholder implementation. "
            "Integrate with actual search API (Bing, Google, etc.)"
        )

        return results

    async def web_search_and_fetch(
        self,
        query: str,
        engine: str = "bing",
        max_results: int = 5,
        fetch_top_n: int = 3
    ) -> Dict:
        """
        Single entry point: Search and fetch top results.

        This is the main function the LLM should call for web operations.

        Args:
            query: Search query
            engine: Search engine to use
            max_results: Maximum search results
            fetch_top_n: How many top results to fetch content for

        Returns:
            Dictionary with search results and fetched content
        """
        logger.info(
            f"web_search_and_fetch: query='{query}', "
            f"engine={engine}, max_results={max_results}, fetch_top_n={fetch_top_n}"
        )

        # Search
        search_results = await self.search(query, engine, max_results)

        # Fetch top N results
        fetch_tasks = []
        for result in search_results[:fetch_top_n]:
            fetch_tasks.append(self.fetch(result.url))

        fetched_results = await asyncio.gather(*fetch_tasks, return_exceptions=True)

        # Combine results
        combined_results = []
        for search_result, fetch_result in zip(search_results[:fetch_top_n], fetched_results):
            if isinstance(fetch_result, Exception):
                content = f"Error fetching: {fetch_result}"
                success = False
            else:
                content = fetch_result.content
                success = fetch_result.success

            combined_results.append({
                'title': search_result.title,
                'url': search_result.url,
                'snippet': search_result.snippet,
                'rank': search_result.rank,
                'content': content,
                'success': success,
                'cached': fetch_result.cached if not isinstance(fetch_result, Exception) else False
            })

        return {
            'query': query,
            'engine': engine,
            'total_results': len(search_results),
            'fetched_count': len(combined_results),
            'results': combined_results
        }

    async def start_background_tasks(self):
        """Start background maintenance tasks."""
        self._cleanup_task = asyncio.create_task(self._periodic_cache_cleanup())
        logger.info("Started background tasks")

    async def _periodic_cache_cleanup(self):
        """Periodically clean up expired cache entries."""
        while True:
            try:
                await asyncio.sleep(300)  # Every 5 minutes
                await self.cache.clear_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cache cleanup: {e}")

    async def get_stats(self) -> Dict:
        """Get daemon statistics."""
        cache_stats = await self.cache.stats()

        return {
            'cache': cache_stats,
            'collectors': [c.name for c in self.registry.collectors]
        }

    async def close(self):
        """Clean up resources."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        await self.registry.close()
        logger.info("WebDaemon closed")


# Example usage
async def main():
    """Example usage of WebDaemon."""
    daemon = WebDaemon(cache_ttl_minutes=15, enable_logging=True)

    try:
        await daemon.start_background_tasks()

        # Example 1: Direct fetch
        print("Example 1: Direct fetch")
        result = await daemon.fetch("https://example.com")
        print(f"Success: {result.success}")
        print(f"Collector: {result.collector_used}")
        print(f"Content length: {len(result.content)}")
        print()

        # Example 2: Search and fetch
        print("Example 2: Search and fetch")
        search_results = await daemon.web_search_and_fetch(
            query="python async programming",
            fetch_top_n=2
        )
        print(f"Query: {search_results['query']}")
        print(f"Fetched: {search_results['fetched_count']} results")
        for result in search_results['results']:
            print(f"  - {result['title']}: {result['success']}")
        print()

        # Example 3: Stats
        print("Example 3: Stats")
        stats = await daemon.get_stats()
        print(f"Cache entries: {stats['cache']['active_entries']}")
        print(f"Collectors: {', '.join(stats['collectors'])}")

    finally:
        await daemon.close()


if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Run example
    asyncio.run(main())
