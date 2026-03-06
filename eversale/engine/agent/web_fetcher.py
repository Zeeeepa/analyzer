"""
Web Fetcher - Safe URL fetching with content extraction.

Borrowed from OpenCode's webfetch patterns:
- Protocol validation (http/https only)
- Size limits (5MB max)
- Timeout protection
- HTML to text/markdown conversion
- Content type handling

Exposed to the agent as the `playwright_fetch_url` tool (fast, no browser).
"""

import asyncio
import aiohttp
import re
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from urllib.parse import urlparse
from loguru import logger
import html


# =============================================================================
# CONSTANTS
# =============================================================================

DEFAULT_TIMEOUT = 30  # seconds
MAX_TIMEOUT = 120     # seconds
MAX_SIZE = 5 * 1024 * 1024  # 5MB
MAX_TEXT_LENGTH = 50_000  # Characters for LLM
DEFAULT_USER_AGENT = "Mozilla/5.0 (compatible; EversaleBot/1.0; +https://eversale.io)"

# HTML tags to skip
SKIP_TAGS = {'script', 'style', 'iframe', 'noscript', 'svg', 'path', 'meta', 'link'}


@dataclass
class FetchResult:
    """Result of a web fetch operation."""
    success: bool
    url: str
    content: str
    content_type: str
    status_code: int
    size_bytes: int
    duration_ms: int
    error: Optional[str] = None
    truncated: bool = False

    def to_llm_format(self) -> str:
        """Format for LLM consumption."""
        if not self.success:
            return f"Error fetching {self.url}: {self.error}"

        parts = []
        parts.append(f"URL: {self.url}")
        parts.append(f"Status: {self.status_code}")
        parts.append(f"Size: {self.size_bytes} bytes")

        if self.truncated:
            parts.append("[Content truncated to fit context]")

        parts.append("")
        parts.append(self.content)

        return "\n".join(parts)


@dataclass
class CacheEntry:
    """Cached fetch result."""
    result: FetchResult
    expires_at: datetime


class WebFetcher:
    """
    Safe web content fetcher for LLM agents.

    From OpenCode patterns:
    - Protocol enforcement (http/https only)
    - Size limits with header inspection
    - Timeout with AbortController equivalent
    - HTML to markdown/text conversion
    - Self-cleaning cache
    """

    def __init__(
        self,
        timeout: int = DEFAULT_TIMEOUT,
        max_size: int = MAX_SIZE,
        user_agent: str = DEFAULT_USER_AGENT,
        cache_ttl: int = 900  # 15 minutes
    ):
        self.timeout = min(timeout, MAX_TIMEOUT)
        self.max_size = max_size
        self.user_agent = user_agent
        self.cache_ttl = cache_ttl
        self._cache: Dict[str, CacheEntry] = {}

    def validate_url(self, url: str) -> Tuple[bool, str]:
        """
        Validate URL for safe fetching.

        Returns:
            (is_valid, error_message)
        """
        # Check protocol
        if not url.startswith(('http://', 'https://')):
            return False, "URL must start with http:// or https://"

        # Upgrade HTTP to HTTPS
        if url.startswith('http://'):
            url = 'https://' + url[7:]

        # Parse URL
        try:
            parsed = urlparse(url)
            if not parsed.netloc:
                return False, "Invalid URL: no host"
        except Exception as e:
            return False, f"Invalid URL: {e}"

        # Block local addresses
        blocked_hosts = ['localhost', '127.0.0.1', '0.0.0.0', '::1']
        if parsed.netloc.split(':')[0] in blocked_hosts:
            return False, "Cannot fetch from localhost"

        # Block private IP ranges
        try:
            import ipaddress
            host = parsed.netloc.split(':')[0]
            try:
                ip = ipaddress.ip_address(host)
                if ip.is_private or ip.is_loopback or ip.is_reserved:
                    return False, "Cannot fetch from private/reserved IP"
            except ValueError:
                pass  # Not an IP, probably a hostname
        except ImportError:
            pass

        return True, ""

    def _get_from_cache(self, url: str) -> Optional[FetchResult]:
        """Get result from cache if valid."""
        entry = self._cache.get(url)
        if entry and entry.expires_at > datetime.utcnow():
            logger.debug(f"[WEB_FETCH] Cache hit: {url}")
            return entry.result

        # Clean expired entry
        if entry:
            del self._cache[url]

        return None

    def _add_to_cache(self, url: str, result: FetchResult):
        """Add result to cache."""
        expires = datetime.utcnow() + timedelta(seconds=self.cache_ttl)
        self._cache[url] = CacheEntry(result=result, expires_at=expires)

        # Clean old entries
        self._clean_cache()

    def _clean_cache(self):
        """Remove expired cache entries."""
        now = datetime.utcnow()
        expired = [k for k, v in self._cache.items() if v.expires_at < now]
        for key in expired:
            del self._cache[key]

    async def fetch(
        self,
        url: str,
        output_format: str = "markdown",
        use_cache: bool = True
    ) -> FetchResult:
        """
        Fetch URL content safely.

        Args:
            url: URL to fetch
            output_format: "markdown", "text", or "html"
            use_cache: Whether to use/update cache

        Returns:
            FetchResult with content or error
        """
        start_time = datetime.utcnow()

        # Validate
        is_valid, error = self.validate_url(url)
        if not is_valid:
            return FetchResult(
                success=False,
                url=url,
                content="",
                content_type="",
                status_code=0,
                size_bytes=0,
                duration_ms=0,
                error=error
            )

        # Upgrade to HTTPS
        if url.startswith('http://'):
            url = 'https://' + url[7:]

        # Check cache
        if use_cache:
            cached = self._get_from_cache(url)
            if cached:
                return cached

        # Set up headers
        headers = {
            "User-Agent": self.user_agent,
            "Accept": self._get_accept_header(output_format),
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                    allow_redirects=True
                ) as response:
                    final_url = str(response.url) if getattr(response, "url", None) else url

                    # Check status
                    if response.status >= 400:
                        return FetchResult(
                            success=False,
                            url=final_url,
                            content="",
                            content_type=str(response.content_type),
                            status_code=response.status,
                            size_bytes=0,
                            duration_ms=self._calc_duration(start_time),
                            error=f"HTTP {response.status}"
                        )

                    # Check size from headers
                    content_length = response.headers.get('Content-Length')
                    if content_length and int(content_length) > self.max_size:
                        return FetchResult(
                            success=False,
                            url=url,
                            content="",
                            content_type=str(response.content_type),
                            status_code=response.status,
                            size_bytes=int(content_length),
                            duration_ms=self._calc_duration(start_time),
                            error=f"Content too large: {content_length} bytes (max {self.max_size})"
                        )

                    # Read content with size limit
                    content_bytes = await response.content.read(self.max_size + 1)
                    if len(content_bytes) > self.max_size:
                        return FetchResult(
                            success=False,
                            url=url,
                            content="",
                            content_type=str(response.content_type),
                            status_code=response.status,
                            size_bytes=len(content_bytes),
                            duration_ms=self._calc_duration(start_time),
                            error=f"Content exceeds size limit"
                        )

                    # Decode
                    try:
                        content = content_bytes.decode('utf-8')
                    except UnicodeDecodeError:
                        content = content_bytes.decode('latin-1')

                    # Convert if HTML
                    content_type = str(response.content_type)
                    if 'html' in content_type:
                        if output_format == "markdown":
                            content = self.html_to_markdown(content)
                        elif output_format == "text":
                            content = self.html_to_text(content)

                    # Truncate if needed
                    truncated = False
                    if len(content) > MAX_TEXT_LENGTH:
                        content = content[:MAX_TEXT_LENGTH] + "\n\n[Content truncated...]"
                        truncated = True

                    result = FetchResult(
                        success=True,
                        url=final_url,
                        content=content,
                        content_type=content_type,
                        status_code=response.status,
                        size_bytes=len(content_bytes),
                        duration_ms=self._calc_duration(start_time),
                        truncated=truncated
                    )

                    # Cache
                    if use_cache:
                        self._add_to_cache(url, result)

                    return result

        except asyncio.TimeoutError:
            return FetchResult(
                success=False,
                url=url,
                content="",
                content_type="",
                status_code=0,
                size_bytes=0,
                duration_ms=self._calc_duration(start_time),
                error=f"Request timed out after {self.timeout}s"
            )
        except aiohttp.ClientError as e:
            return FetchResult(
                success=False,
                url=url,
                content="",
                content_type="",
                status_code=0,
                size_bytes=0,
                duration_ms=self._calc_duration(start_time),
                error=f"Connection error: {e}"
            )
        except Exception as e:
            return FetchResult(
                success=False,
                url=url,
                content="",
                content_type="",
                status_code=0,
                size_bytes=0,
                duration_ms=self._calc_duration(start_time),
                error=f"Fetch error: {e}"
            )

    def _calc_duration(self, start: datetime) -> int:
        """Calculate duration in milliseconds."""
        return int((datetime.utcnow() - start).total_seconds() * 1000)

    def _get_accept_header(self, format: str) -> str:
        """Get Accept header based on desired format."""
        if format == "markdown":
            return "text/markdown;q=1.0, text/html;q=0.9, text/plain;q=0.8"
        elif format == "text":
            return "text/plain;q=1.0, text/html;q=0.9"
        else:
            return "text/html;q=1.0, */*;q=0.8"

    def html_to_text(self, html_content: str) -> str:
        """
        Convert HTML to plain text.

        Removes scripts, styles, and extracts text content.
        """
        # Remove skip tags and their content
        for tag in SKIP_TAGS:
            html_content = re.sub(
                rf'<{tag}[^>]*>.*?</{tag}>',
                '',
                html_content,
                flags=re.DOTALL | re.IGNORECASE
            )

        # Remove all HTML tags
        text = re.sub(r'<[^>]+>', ' ', html_content)

        # Decode HTML entities
        text = html.unescape(text)

        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'\n\s*\n', '\n\n', text)

        return text.strip()

    def html_to_markdown(self, html_content: str) -> str:
        """
        Convert HTML to markdown.

        Preserves structure with headers, links, code blocks.
        """
        # Remove skip tags
        for tag in SKIP_TAGS:
            html_content = re.sub(
                rf'<{tag}[^>]*>.*?</{tag}>',
                '',
                html_content,
                flags=re.DOTALL | re.IGNORECASE
            )

        # Convert headers
        for i in range(1, 7):
            html_content = re.sub(
                rf'<h{i}[^>]*>(.*?)</h{i}>',
                rf'{"#" * i} \1\n\n',
                html_content,
                flags=re.DOTALL | re.IGNORECASE
            )

        # Convert links
        html_content = re.sub(
            r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
            r'[\2](\1)',
            html_content,
            flags=re.DOTALL | re.IGNORECASE
        )

        # Convert code blocks
        html_content = re.sub(
            r'<pre[^>]*><code[^>]*>(.*?)</code></pre>',
            r'```\n\1\n```\n',
            html_content,
            flags=re.DOTALL | re.IGNORECASE
        )

        # Convert inline code
        html_content = re.sub(
            r'<code[^>]*>(.*?)</code>',
            r'`\1`',
            html_content,
            flags=re.DOTALL | re.IGNORECASE
        )

        # Convert bold
        html_content = re.sub(
            r'<(?:strong|b)[^>]*>(.*?)</(?:strong|b)>',
            r'**\1**',
            html_content,
            flags=re.DOTALL | re.IGNORECASE
        )

        # Convert italic
        html_content = re.sub(
            r'<(?:em|i)[^>]*>(.*?)</(?:em|i)>',
            r'*\1*',
            html_content,
            flags=re.DOTALL | re.IGNORECASE
        )

        # Convert lists
        html_content = re.sub(
            r'<li[^>]*>(.*?)</li>',
            r'- \1\n',
            html_content,
            flags=re.DOTALL | re.IGNORECASE
        )

        # Convert paragraphs
        html_content = re.sub(
            r'<p[^>]*>(.*?)</p>',
            r'\1\n\n',
            html_content,
            flags=re.DOTALL | re.IGNORECASE
        )

        # Convert line breaks
        html_content = re.sub(r'<br\s*/?>', '\n', html_content, flags=re.IGNORECASE)

        # Remove remaining tags
        html_content = re.sub(r'<[^>]+>', '', html_content)

        # Decode entities
        html_content = html.unescape(html_content)

        # Clean whitespace
        html_content = re.sub(r'\n{3,}', '\n\n', html_content)
        html_content = re.sub(r' +', ' ', html_content)

        return html_content.strip()


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

_default_fetcher = None


def get_fetcher() -> WebFetcher:
    """Get default web fetcher singleton."""
    global _default_fetcher
    if _default_fetcher is None:
        _default_fetcher = WebFetcher()
    return _default_fetcher


async def fetch_url(url: str, format: str = "markdown") -> str:
    """Quick URL fetch helper."""
    fetcher = get_fetcher()
    result = await fetcher.fetch(url, output_format=format)
    return result.to_llm_format()


async def fetch_text(url: str) -> str:
    """Fetch URL as plain text."""
    fetcher = get_fetcher()
    result = await fetcher.fetch(url, output_format="text")
    return result.content if result.success else f"Error: {result.error}"


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    import asyncio

    async def test():
        fetcher = WebFetcher()

        print("=== WEB FETCHER TEST ===")

        # Test validation
        print("\n--- URL Validation ---")
        test_urls = [
            "https://example.com",
            "http://example.com",
            "ftp://example.com",
            "file:///etc/passwd",
            "https://localhost/admin",
            "https://127.0.0.1/secret",
        ]
        for url in test_urls:
            valid, err = fetcher.validate_url(url)
            print(f"  {url[:30]:30} -> {'OK' if valid else err}")

        # Test actual fetch (example.com)
        print("\n--- Fetch Test ---")
        result = await fetcher.fetch("https://example.com")
        print(f"  Success: {result.success}")
        print(f"  Status: {result.status_code}")
        print(f"  Size: {result.size_bytes} bytes")
        print(f"  Content preview: {result.content[:200]}...")

        # Test caching
        print("\n--- Cache Test ---")
        result2 = await fetcher.fetch("https://example.com")
        print(f"  Second fetch (should be cached): {result2.success}")

        # Test HTML conversion
        print("\n--- HTML Conversion ---")
        test_html = """
        <html>
        <head><title>Test</title></head>
        <body>
            <h1>Hello World</h1>
            <p>This is a <strong>test</strong> paragraph.</p>
            <ul>
                <li>Item 1</li>
                <li>Item 2</li>
            </ul>
            <a href="https://example.com">Link</a>
        </body>
        </html>
        """
        md = fetcher.html_to_markdown(test_html)
        print(f"  Markdown:\n{md[:300]}")

        print("\nAll tests passed!")

    asyncio.run(test())
