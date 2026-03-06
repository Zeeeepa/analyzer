"""
Cloudflare Challenge Handler - Auto-solve or find alternatives

When a site blocks us with Cloudflare:
1. Wait for JS challenge to auto-complete (10-15s)
2. Try stealth mode refresh
3. Try captcha solver (vision-based)
4. Find alternative data source

Alternative data sources:
- Crunchbase blocked -> Use LinkedIn, Tracxn, or direct company sites
- Google blocked -> Use DuckDuckGo, Serper
- LinkedIn blocked -> Use company websites directly
"""

import asyncio
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from enum import Enum
from loguru import logger


class BlockedSite(Enum):
    """Sites that commonly block with Cloudflare."""
    CRUNCHBASE = "crunchbase"
    LINKEDIN = "linkedin"
    GOOGLE = "google"
    GLASSDOOR = "glassdoor"
    INDEED = "indeed"
    ZILLOW = "zillow"
    REDDIT = "reddit"  # Added - Reddit aggressively blocks automation
    UNKNOWN = "unknown"


@dataclass
class AlternativeSource:
    """An alternative data source."""
    name: str
    url_template: str  # {query} placeholder
    extractor: str  # Which extraction method to use
    priority: int  # Lower = try first


# Alternative sources for blocked sites
ALTERNATIVES = {
    BlockedSite.CRUNCHBASE: [
        AlternativeSource(
            name="LinkedIn Company Search",
            url_template="https://www.linkedin.com/search/results/companies/?keywords={query}",
            extractor="linkedin_company",
            priority=1
        ),
        AlternativeSource(
            name="Google Search (Company Info)",
            url_template="https://www.google.com/search?q={query}+company+funding+series",
            extractor="google_search",
            priority=2
        ),
        AlternativeSource(
            name="DuckDuckGo Search",
            url_template="https://duckduckgo.com/?q={query}+funding+investors",
            extractor="duckduckgo",
            priority=3
        ),
    ],
    BlockedSite.LINKEDIN: [
        AlternativeSource(
            name="Google Search (LinkedIn Profile)",
            url_template="https://www.google.com/search?q=site:linkedin.com+{query}",
            extractor="google_search",
            priority=1
        ),
        AlternativeSource(
            name="Company Website Direct",
            url_template="https://www.google.com/search?q={query}+official+website",
            extractor="company_direct",
            priority=2
        ),
    ],
    BlockedSite.GOOGLE: [
        AlternativeSource(
            name="DuckDuckGo",
            url_template="https://duckduckgo.com/?q={query}",
            extractor="duckduckgo",
            priority=1
        ),
        AlternativeSource(
            name="Bing",
            url_template="https://www.bing.com/search?q={query}",
            extractor="bing",
            priority=2
        ),
    ],
    BlockedSite.GLASSDOOR: [
        AlternativeSource(
            name="Indeed",
            url_template="https://www.indeed.com/cmp/{query}/reviews",
            extractor="indeed_reviews",
            priority=1
        ),
        AlternativeSource(
            name="LinkedIn Company",
            url_template="https://www.linkedin.com/company/{query}",
            extractor="linkedin_company",
            priority=2
        ),
    ],
    BlockedSite.REDDIT: [
        AlternativeSource(
            name="Reddit JSON API",
            url_template="https://www.reddit.com/search.json?q={query}&limit=25",
            extractor="reddit_json",  # Uses reddit_handler.py
            priority=1
        ),
        AlternativeSource(
            name="Reddit RSS Feed",
            url_template="https://www.reddit.com/search.rss?q={query}&limit=25",
            extractor="reddit_rss",  # Uses reddit_handler.py
            priority=2
        ),
        AlternativeSource(
            name="PullPush Archive",
            url_template="https://api.pullpush.io/reddit/search/submission/?q={query}&size=25",
            extractor="pullpush",  # Historical Reddit data
            priority=3
        ),
    ],
}


class ChallengeHandler:
    """
    Handles Cloudflare challenges and finds alternatives.

    Strategy:
    1. Detect challenge type
    2. Try to bypass/solve
    3. If failed, find alternative source
    4. Execute on alternative
    """

    def __init__(self, mcp_client=None, captcha_solver=None):
        self.mcp = mcp_client
        self.captcha_solver = captcha_solver
        self.bypass_attempts = 0
        self.alternative_successes = 0

    def detect_blocked_site(self, url: str) -> BlockedSite:
        """Detect which site is blocked based on URL."""
        url_lower = url.lower()

        if "crunchbase.com" in url_lower:
            return BlockedSite.CRUNCHBASE
        elif "linkedin.com" in url_lower:
            return BlockedSite.LINKEDIN
        elif "google.com" in url_lower:
            return BlockedSite.GOOGLE
        elif "glassdoor.com" in url_lower:
            return BlockedSite.GLASSDOOR
        elif "reddit.com" in url_lower:
            return BlockedSite.REDDIT
        elif "indeed.com" in url_lower:
            return BlockedSite.INDEED
        elif "zillow.com" in url_lower:
            return BlockedSite.ZILLOW

        return BlockedSite.UNKNOWN

    async def try_bypass_cloudflare(self, page) -> bool:
        """
        Try to bypass Cloudflare challenge.

        Returns:
            True if bypassed, False if still blocked
        """
        self.bypass_attempts += 1
        logger.debug("Attempting challenge bypass...")

        # Strategy 1: Wait for JS challenge (most Turnstile challenges auto-complete)
        logger.debug("Strategy 1: Waiting for challenge to auto-complete...")
        for i in range(3):
            await asyncio.sleep(5)

            # Check if challenge is gone
            content = await page.content()
            if not self._is_cloudflare_page(content):
                logger.debug(f"Challenge bypassed via JS wait (attempt {i+1})")
                return True

        # Strategy 2: Refresh with different headers
        logger.debug("Strategy 2: Refreshing...")
        try:
            await page.reload(wait_until="networkidle")
            await asyncio.sleep(3)

            content = await page.content()
            if not self._is_cloudflare_page(content):
                logger.debug("Challenge bypassed via refresh")
                return True
        except Exception as e:
            logger.debug(f"Refresh strategy failed: {e}")

        # Strategy 3: Try captcha solver if available
        if self.captcha_solver:
            logger.debug("Strategy 3: Using solver...")
            try:
                result = await self.captcha_solver.solve_cloudflare(page)
                if result.get("success"):
                    logger.debug("Challenge bypassed via solver")
                    return True
            except Exception as e:
                logger.debug(f"Solver failed: {e}")

        logger.warning("All Cloudflare bypass strategies failed")
        return False

    def _is_cloudflare_page(self, content: str) -> bool:
        """Check if page is a Cloudflare challenge."""
        indicators = [
            "Just a moment...",
            "Checking your browser",
            "challenge-running",
            "cf-browser-verification",
            "Cloudflare Ray ID",
            "_cf_chl_opt",
            "cf-turnstile",
        ]
        content_lower = content.lower()
        return any(ind.lower() in content_lower for ind in indicators)

    def get_alternatives(self, blocked_site: BlockedSite) -> List[AlternativeSource]:
        """Get alternative sources for a blocked site."""
        return sorted(
            ALTERNATIVES.get(blocked_site, []),
            key=lambda x: x.priority
        )

    async def try_alternative(
        self,
        blocked_site: BlockedSite,
        query: str,
        mcp_client
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Try alternative data sources when main site is blocked.

        Args:
            blocked_site: Which site was blocked
            query: What we were searching for
            mcp_client: MCP client for browser control

        Returns:
            (success, result_data)
        """
        alternatives = self.get_alternatives(blocked_site)

        if not alternatives:
            logger.warning(f"No alternatives configured for {blocked_site.value}")
            return False, {"error": "No alternatives available"}

        for alt in alternatives:
            logger.info(f"Trying alternative: {alt.name}")

            try:
                # Build URL with query
                url = alt.url_template.format(query=query.replace(" ", "+"))

                # Navigate to alternative
                await mcp_client.call_tool("playwright_navigate", {"url": url})
                await asyncio.sleep(2)

                # Check if this one is also blocked
                snapshot = await mcp_client.call_tool("playwright_snapshot", {})
                if snapshot.get("cloudflare_blocked"):
                    logger.warning(f"{alt.name} also blocked, trying next...")
                    continue

                # Extract data based on extractor type
                if alt.extractor == "linkedin_company":
                    result = await mcp_client.call_tool("playwright_batch_extract", {
                        "selector": "li.reusable-search__result-container",
                        "fields": ["name", "description", "followers"]
                    })
                elif alt.extractor == "google_search":
                    result = await mcp_client.call_tool("playwright_get_markdown", {})
                elif alt.extractor == "duckduckgo":
                    result = await mcp_client.call_tool("playwright_get_markdown", {})
                else:
                    result = await mcp_client.call_tool("playwright_snapshot", {})

                if result and not result.get("error"):
                    self.alternative_successes += 1
                    logger.info(f"Successfully got data from {alt.name}")
                    return True, {
                        "source": alt.name,
                        "data": result,
                        "original_blocked": blocked_site.value
                    }

            except Exception as e:
                logger.warning(f"Alternative {alt.name} failed: {e}")
                continue

        return False, {"error": "All alternatives failed"}

    async def handle_blocked_request(
        self,
        url: str,
        query: str,
        page,
        mcp_client
    ) -> Dict[str, Any]:
        """
        Main entry point - handle a blocked request.

        1. Try to bypass Cloudflare
        2. If failed, try alternatives

        Args:
            url: The blocked URL
            query: What we were searching for
            page: Playwright page object
            mcp_client: MCP client

        Returns:
            Result dict with data or error
        """
        # First, try to bypass
        bypassed = await self.try_bypass_cloudflare(page)

        if bypassed:
            return {
                "success": True,
                "bypassed": True,
                "message": "Cloudflare challenge bypassed"
            }

        # If bypass failed, try alternatives
        blocked_site = self.detect_blocked_site(url)

        if blocked_site == BlockedSite.UNKNOWN:
            return {
                "success": False,
                "error": "Site blocked by Cloudflare - no alternatives available",
                "url": url
            }

        success, result = await self.try_alternative(blocked_site, query, mcp_client)

        if success:
            return {
                "success": True,
                "alternative_used": True,
                **result
            }

        return {
            "success": False,
            "error": f"Cloudflare blocked and all alternatives failed for {blocked_site.value}",
            "url": url
        }


# Singleton instance
_handler_instance = None


def get_challenge_handler(mcp_client=None, captcha_solver=None) -> ChallengeHandler:
    """Get or create the challenge handler singleton."""
    global _handler_instance
    if _handler_instance is None:
        _handler_instance = ChallengeHandler(mcp_client, captcha_solver)
    return _handler_instance


async def handle_cloudflare_block(
    url: str,
    query: str,
    page,
    mcp_client
) -> Dict[str, Any]:
    """
    Convenience function to handle Cloudflare blocks.

    Usage:
        result = await handle_cloudflare_block(
            url="https://crunchbase.com/search?q=saas",
            query="saas companies funding",
            page=browser_page,
            mcp_client=mcp
        )
    """
    handler = get_challenge_handler(mcp_client)
    return await handler.handle_blocked_request(url, query, page, mcp_client)
