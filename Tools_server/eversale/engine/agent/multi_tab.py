"""
Multi-Tab Browser Context - Parallel page operations.

Features:
1. Manage multiple browser tabs/pages
2. Parallel data extraction
3. Context switching without navigation overhead
4. Tab pooling for efficiency
5. Resource cleanup
"""

import asyncio
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from loguru import logger


@dataclass
class Tab:
    """Represents a browser tab."""
    id: str
    page: Any  # Playwright page object
    url: str = ""
    title: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    last_used: datetime = field(default_factory=datetime.now)
    is_busy: bool = False
    data: Dict[str, Any] = field(default_factory=dict)


class TabManager:
    """
    Manage multiple browser tabs for parallel operations.

    Usage:
        manager = TabManager(browser_context)
        await manager.initialize(pool_size=3)

        # Parallel extraction
        results = await manager.parallel_extract([
            "https://site1.com",
            "https://site2.com",
            "https://site3.com"
        ], extract_fn)

        # Or manual tab control
        tab = await manager.get_tab()
        await tab.page.goto("https://example.com")
        manager.release_tab(tab)
    """

    def __init__(self, browser_context=None, browser=None):
        """
        Initialize with browser context or browser instance.

        Args:
            browser_context: Playwright browser context
            browser: Alternative - browser instance with .context
        """
        self.context = browser_context
        self.browser = browser
        self.tabs: Dict[str, Tab] = {}
        self.tab_pool: List[str] = []  # Available tab IDs
        self.max_tabs = 5
        self._lock = asyncio.Lock()

    async def initialize(self, pool_size: int = 3) -> bool:
        """
        Pre-create tab pool for efficiency.

        Args:
            pool_size: Number of tabs to pre-create

        Returns:
            True if successful
        """
        try:
            # Get context from browser if needed
            if not self.context and self.browser:
                if hasattr(self.browser, 'context'):
                    self.context = self.browser.context
                elif hasattr(self.browser, 'page'):
                    self.context = self.browser.page.context

            if not self.context:
                logger.warning("No browser context available for multi-tab")
                return False

            # Create initial tab pool
            for i in range(min(pool_size, self.max_tabs)):
                await self._create_tab()

            logger.info(f"Tab pool initialized with {len(self.tabs)} tabs")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize tab pool: {e}")
            return False

    async def _create_tab(self) -> Optional[Tab]:
        """Create a new tab."""
        try:
            page = await self.context.new_page()
            tab_id = f"tab_{len(self.tabs)}_{datetime.now().timestamp()}"

            tab = Tab(
                id=tab_id,
                page=page
            )

            self.tabs[tab_id] = tab
            self.tab_pool.append(tab_id)

            return tab

        except Exception as e:
            logger.error(f"Failed to create tab: {e}")
            return None

    async def get_tab(self, timeout: float = 30.0) -> Optional[Tab]:
        """
        Get an available tab from the pool.

        Args:
            timeout: Max seconds to wait for available tab

        Returns:
            Tab object or None
        """
        start_time = datetime.now()

        while True:
            async with self._lock:
                # Try to get from pool
                if self.tab_pool:
                    tab_id = self.tab_pool.pop(0)
                    tab = self.tabs.get(tab_id)
                    if tab:
                        tab.is_busy = True
                        tab.last_used = datetime.now()
                        return tab

                # Try to create new tab if under limit
                if len(self.tabs) < self.max_tabs:
                    tab = await self._create_tab()
                    if tab:
                        self.tab_pool.remove(tab.id)  # Remove from pool
                        tab.is_busy = True
                        return tab

            # Check timeout
            elapsed = (datetime.now() - start_time).total_seconds()
            if elapsed > timeout:
                logger.warning("Timeout waiting for available tab")
                return None

            await asyncio.sleep(0.1)

    def release_tab(self, tab: Tab):
        """Return tab to the pool."""
        tab.is_busy = False
        tab.last_used = datetime.now()

        if tab.id not in self.tab_pool:
            self.tab_pool.append(tab.id)

    async def close_tab(self, tab: Tab):
        """Close and remove a tab."""
        try:
            await tab.page.close()
        except:
            pass

        if tab.id in self.tabs:
            del self.tabs[tab.id]

        if tab.id in self.tab_pool:
            self.tab_pool.remove(tab.id)

    async def parallel_navigate(
        self,
        urls: List[str],
        wait_until: str = "domcontentloaded"
    ) -> Dict[str, Any]:
        """
        Navigate to multiple URLs in parallel.

        Args:
            urls: List of URLs
            wait_until: Playwright wait condition

        Returns:
            Dict with results per URL
        """
        results = {}
        semaphore = asyncio.Semaphore(len(self.tabs) or 3)

        async def navigate_one(url: str):
            async with semaphore:
                tab = await self.get_tab()
                if not tab:
                    return url, {"success": False, "error": "No tab available"}

                try:
                    await tab.page.goto(url, wait_until=wait_until, timeout=30000)
                    tab.url = url
                    tab.title = await tab.page.title()

                    return url, {
                        "success": True,
                        "title": tab.title,
                        "tab_id": tab.id
                    }

                except Exception as e:
                    return url, {"success": False, "error": str(e)}

                finally:
                    self.release_tab(tab)

        tasks = [navigate_one(url) for url in urls]
        completed = await asyncio.gather(*tasks, return_exceptions=True)

        for result in completed:
            if isinstance(result, tuple):
                url, data = result
                results[url] = data
            elif isinstance(result, Exception):
                results[str(result)] = {"success": False, "error": str(result)}

        return results

    async def parallel_extract(
        self,
        urls: List[str],
        extract_fn: Callable,
        max_concurrent: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Extract data from multiple URLs in parallel.

        Args:
            urls: List of URLs to extract from
            extract_fn: Async function(page) -> data
            max_concurrent: Max parallel operations

        Returns:
            List of extraction results
        """
        results = []
        semaphore = asyncio.Semaphore(min(max_concurrent, len(self.tabs) or 3))

        async def extract_one(url: str) -> Dict:
            async with semaphore:
                tab = await self.get_tab()
                if not tab:
                    return {"url": url, "success": False, "error": "No tab available"}

                try:
                    # Navigate
                    await tab.page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    await asyncio.sleep(1)  # Let JS render

                    # Extract
                    data = await extract_fn(tab.page)

                    return {
                        "url": url,
                        "success": True,
                        "data": data
                    }

                except Exception as e:
                    return {
                        "url": url,
                        "success": False,
                        "error": str(e)
                    }

                finally:
                    self.release_tab(tab)

        tasks = [extract_one(url) for url in urls]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in raw_results:
            if isinstance(result, dict):
                results.append(result)
            elif isinstance(result, Exception):
                results.append({"success": False, "error": str(result)})

        return results

    async def parallel_action(
        self,
        actions: List[Dict[str, Any]],
        action_fn: Callable,
        max_concurrent: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Execute actions in parallel across tabs.

        Args:
            actions: List of action configs
            action_fn: Async function(page, action) -> result
            max_concurrent: Max parallel operations

        Returns:
            List of results
        """
        results = []
        semaphore = asyncio.Semaphore(min(max_concurrent, len(self.tabs) or 3))

        async def execute_one(action: Dict) -> Dict:
            async with semaphore:
                tab = await self.get_tab()
                if not tab:
                    return {"action": action, "success": False, "error": "No tab available"}

                try:
                    result = await action_fn(tab.page, action)
                    return {
                        "action": action,
                        "success": True,
                        "result": result
                    }

                except Exception as e:
                    return {
                        "action": action,
                        "success": False,
                        "error": str(e)
                    }

                finally:
                    self.release_tab(tab)

        tasks = [execute_one(action) for action in actions]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in raw_results:
            if isinstance(result, dict):
                results.append(result)
            elif isinstance(result, Exception):
                results.append({"success": False, "error": str(result)})

        return results

    async def extract_contacts_parallel(
        self,
        urls: List[str],
        max_concurrent: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Extract contacts from multiple pages in parallel.

        Optimized for lead generation workflow.
        """
        async def extract_contacts(page) -> Dict:
            """Extract emails, phones, socials from page."""
            return await page.evaluate("""
                () => {
                    const result = {
                        emails: [],
                        phones: [],
                        socialProfiles: {}
                    };

                    // Get page text
                    const text = document.body?.innerText || '';

                    // Extract emails
                    const emailPattern = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}/g;
                    const emails = text.match(emailPattern) || [];
                    result.emails = [...new Set(emails)].slice(0, 10);

                    // Extract phones
                    const phonePattern = /(?:\\+?1[-.]?)?\\(?\\d{3}\\)?[-.]?\\d{3}[-.]?\\d{4}/g;
                    const phones = text.match(phonePattern) || [];
                    result.phones = [...new Set(phones)].slice(0, 5);

                    // Extract social profiles from links
                    const links = document.querySelectorAll('a[href]');
                    links.forEach(link => {
                        const href = link.href;
                        if (href.includes('linkedin.com')) {
                            result.socialProfiles.linkedin = href;
                        } else if (href.includes('twitter.com') || href.includes('x.com')) {
                            result.socialProfiles.twitter = href;
                        } else if (href.includes('facebook.com')) {
                            result.socialProfiles.facebook = href;
                        }
                    });

                    return result;
                }
            """)

        return await self.parallel_extract(urls, extract_contacts, max_concurrent)

    def get_status(self) -> Dict[str, Any]:
        """Get manager status."""
        return {
            "total_tabs": len(self.tabs),
            "available_tabs": len(self.tab_pool),
            "busy_tabs": len(self.tabs) - len(self.tab_pool),
            "max_tabs": self.max_tabs,
            "tabs": [
                {
                    "id": t.id,
                    "url": t.url,
                    "is_busy": t.is_busy,
                    "last_used": t.last_used.isoformat()
                }
                for t in self.tabs.values()
            ]
        }

    async def cleanup(self):
        """Close all tabs and cleanup."""
        for tab in list(self.tabs.values()):
            try:
                await tab.page.close()
            except:
                pass

        self.tabs.clear()
        self.tab_pool.clear()
        logger.info("Tab manager cleaned up")

    async def cleanup_idle(self, max_idle_seconds: int = 300):
        """Close tabs idle for too long."""
        now = datetime.now()
        to_close = []

        for tab in self.tabs.values():
            if not tab.is_busy:
                idle_time = (now - tab.last_used).total_seconds()
                if idle_time > max_idle_seconds:
                    to_close.append(tab)

        for tab in to_close:
            await self.close_tab(tab)

        if to_close:
            logger.info(f"Cleaned up {len(to_close)} idle tabs")


class TabContext:
    """
    Context manager for tab operations.

    Usage:
        async with TabContext(manager) as tab:
            await tab.page.goto("https://example.com")
            data = await tab.page.content()
    """

    def __init__(self, manager: TabManager):
        self.manager = manager
        self.tab: Optional[Tab] = None

    async def __aenter__(self) -> Tab:
        self.tab = await self.manager.get_tab()
        if not self.tab:
            raise RuntimeError("No tab available")
        return self.tab

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.tab:
            self.manager.release_tab(self.tab)


# Convenience functions
async def parallel_scrape(
    browser,
    urls: List[str],
    extract_fn: Callable = None
) -> List[Dict]:
    """
    Quick parallel scrape with auto-cleanup.

    Args:
        browser: Browser instance
        urls: URLs to scrape
        extract_fn: Optional custom extraction function

    Returns:
        List of results
    """
    manager = TabManager(browser=browser)
    await manager.initialize(pool_size=min(len(urls), 3))

    try:
        if extract_fn:
            return await manager.parallel_extract(urls, extract_fn)
        else:
            return await manager.extract_contacts_parallel(urls)
    finally:
        await manager.cleanup()


async def parallel_research(
    browser,
    companies: List[str],
    max_concurrent: int = 3
) -> List[Dict]:
    """
    Research multiple companies in parallel.

    Returns company data for each.
    """
    manager = TabManager(browser=browser)
    await manager.initialize(pool_size=max_concurrent)

    async def research_one(page, action: Dict) -> Dict:
        company = action["company"]

        # Search Google
        await page.goto(f"https://www.google.com/search?q={company.replace(' ', '+')}")
        await asyncio.sleep(1)

        # Extract info
        data = await page.evaluate("""
            () => {
                const info = {};
                const panel = document.querySelector('.kp-wholepage');
                if (panel) {
                    info.description = panel.querySelector('.kno-rdesc span')?.textContent || '';
                    info.website = panel.querySelector('a[href*="http"]')?.href || '';
                }
                return info;
            }
        """)

        return {"company": company, **data}

    try:
        actions = [{"company": c} for c in companies]
        return await manager.parallel_action(actions, research_one, max_concurrent)
    finally:
        await manager.cleanup()
