"""
Search Alternatives Module - Bypass Google CAPTCHA/Rate Limiting

Based on 2025 research from Reddit/GitHub:
- Serper.dev: 2500 free searches/month, 10x cheaper than SerpAPI
- DuckDuckGo: Free, no rate limits, good for fallback
- Alternative search when Playwright Google scraping fails

Sources:
- https://github.com/rebrowser/rebrowser-patches
- https://pypi.org/project/duckduckgo-search/
- https://serper.dev/
"""

import os
import asyncio
from typing import List, Dict, Any, Optional
from loguru import logger

# Try to import search libraries
# Note: Package renamed from duckduckgo-search to ddgs in 2025
try:
    from ddgs import DDGS
    DDGS_AVAILABLE = True
except ImportError:
    try:
        from duckduckgo_search import DDGS  # Fallback to old name
        DDGS_AVAILABLE = True
    except ImportError:
        DDGS_AVAILABLE = False
        DDGS = None

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    httpx = None


class SearchAlternatives:
    """
    Provides alternative search methods when Google blocks Playwright scraping.

    Priority order:
    1. Serper.dev API (if API key configured) - Best quality, 2500 free/month
    2. DuckDuckGo (always free) - Good fallback, no rate limits
    3. Direct scraping with date filter bypass (already in playwright_direct.py)
    """

    # Serper.dev API endpoint
    SERPER_API_URL = "https://google.serper.dev/search"

    def __init__(self, serper_api_key: Optional[str] = None):
        """
        Initialize search alternatives.

        Args:
            serper_api_key: Serper.dev API key (get free at serper.dev)
                           Can also be set via SERPER_API_KEY env var
        """
        self.serper_api_key = serper_api_key or os.environ.get("SERPER_API_KEY")

        # Track usage for logging
        self.serper_calls = 0
        self.ddg_calls = 0

    async def search(
        self,
        query: str,
        num_results: int = 10,
        date_filter: str = None  # 'month', 'year', 'week'
    ) -> Dict[str, Any]:
        """
        Search using best available method.

        Args:
            query: Search query
            num_results: Number of results to return
            date_filter: Optional date filter ('month', 'year', 'week')

        Returns:
            Dict with 'results' list and 'source' indicating which engine was used
        """
        # Try Serper first (best quality)
        if self.serper_api_key:
            result = await self.serper_search(query, num_results, date_filter)
            if result.get('success'):
                return result

        # Fall back to DuckDuckGo (always free)
        if DDGS_AVAILABLE:
            result = await self.duckduckgo_search(query, num_results)
            if result.get('success'):
                return result

        return {
            'success': False,
            'error': 'No search methods available',
            'results': []
        }

    async def serper_search(
        self,
        query: str,
        num_results: int = 10,
        date_filter: str = None
    ) -> Dict[str, Any]:
        """
        Search using Serper.dev API (Google results, 2500 free/month).

        Serper is 10x cheaper than SerpAPI and has better free tier.
        """
        if not self.serper_api_key:
            return {'success': False, 'error': 'No Serper API key', 'results': []}

        if not HTTPX_AVAILABLE:
            return {'success': False, 'error': 'httpx not installed', 'results': []}

        try:
            payload = {
                "q": query,
                "num": num_results
            }

            # Add date filter if specified
            if date_filter:
                date_map = {
                    'day': 'd',
                    'week': 'w',
                    'month': 'm',
                    'year': 'y'
                }
                if date_filter in date_map:
                    payload['tbs'] = f"qdr:{date_map[date_filter]}"

            headers = {
                "X-API-KEY": self.serper_api_key,
                "Content-Type": "application/json"
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.SERPER_API_URL,
                    json=payload,
                    headers=headers
                )

            if response.status_code == 200:
                data = response.json()
                self.serper_calls += 1

                # Parse organic results
                results = []
                for item in data.get('organic', []):
                    results.append({
                        'title': item.get('title', ''),
                        'url': item.get('link', ''),
                        'snippet': item.get('snippet', ''),
                        'position': item.get('position', 0)
                    })

                logger.info(f"Serper search returned {len(results)} results for: {query[:50]}")
                return {
                    'success': True,
                    'source': 'serper',
                    'results': results,
                    'total_calls': self.serper_calls
                }
            else:
                logger.warning(f"Serper API error: {response.status_code}")
                return {
                    'success': False,
                    'error': f"Serper API returned {response.status_code}",
                    'results': []
                }

        except Exception as e:
            logger.error(f"Serper search failed: {e}")
            return {'success': False, 'error': str(e), 'results': []}

    async def duckduckgo_search(
        self,
        query: str,
        num_results: int = 10
    ) -> Dict[str, Any]:
        """
        Search using DuckDuckGo (completely free, no rate limits).

        Uses duckduckgo-search library (MIT license).
        """
        if not DDGS_AVAILABLE:
            return {'success': False, 'error': 'duckduckgo-search not installed', 'results': []}

        try:
            # Run in executor since DDGS is sync
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None,
                self._ddg_search_sync,
                query,
                num_results
            )

            self.ddg_calls += 1
            logger.info(f"DuckDuckGo search returned {len(results)} results for: {query[:50]}")

            return {
                'success': True,
                'source': 'duckduckgo',
                'results': results,
                'total_calls': self.ddg_calls
            }

        except Exception as e:
            logger.error(f"DuckDuckGo search failed: {e}")
            return {'success': False, 'error': str(e), 'results': []}

    def _ddg_search_sync(self, query: str, num_results: int) -> List[Dict]:
        """Synchronous DuckDuckGo search helper."""
        results = []
        try:
            with DDGS() as ddgs:
                for i, r in enumerate(ddgs.text(query, max_results=num_results)):
                    results.append({
                        'title': r.get('title', ''),
                        'url': r.get('href', ''),
                        'snippet': r.get('body', ''),
                        'position': i + 1
                    })
        except Exception as e:
            logger.warning(f"DDG sync search error: {e}")
        return results


# Singleton instance for easy access
_search_instance = None

def get_search_alternatives(serper_api_key: Optional[str] = None) -> SearchAlternatives:
    """Get or create singleton SearchAlternatives instance."""
    global _search_instance
    if _search_instance is None:
        _search_instance = SearchAlternatives(serper_api_key)
    return _search_instance


async def quick_search(query: str, num_results: int = 10) -> List[Dict]:
    """
    Quick search function - returns list of results or empty list.

    Usage:
        from agent.search_alternatives import quick_search
        results = await quick_search("lead generation agency founder")
        for r in results:
            print(r['title'], r['url'])
    """
    search = get_search_alternatives()
    result = await search.search(query, num_results)
    return result.get('results', [])


# Test function
async def _test():
    """Test search alternatives."""
    print("Testing search alternatives...")

    search = SearchAlternatives()

    # Test DuckDuckGo (always available)
    print("\n1. Testing DuckDuckGo:")
    result = await search.duckduckgo_search("small lead generation agency founder", 5)
    print(f"   Success: {result.get('success')}")
    print(f"   Results: {len(result.get('results', []))}")
    for r in result.get('results', [])[:3]:
        print(f"   - {r['title'][:50]}...")
        print(f"     {r['url']}")

    # Test Serper (only if API key set)
    if os.environ.get("SERPER_API_KEY"):
        print("\n2. Testing Serper.dev:")
        result = await search.serper_search("boutique cold email agency USA", 5)
        print(f"   Success: {result.get('success')}")
        print(f"   Results: {len(result.get('results', []))}")
    else:
        print("\n2. Serper: Skipped (no SERPER_API_KEY set)")
        print("   Get free API key at: https://serper.dev/")


if __name__ == "__main__":
    asyncio.run(_test())
