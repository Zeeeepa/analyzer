#!/usr/bin/env python3
"""
Eversale Fast Extract - Playwright MCP equivalent.

Clean, simple, works. ~500 lines.

Features:
- Fast extraction (navigate -> wait -> extract)
- Stealth browser (anti-detection)
- Session persistence (stay logged in)
- Basic retry on failure
- JSON output

Usage:
    eversale "fb ads booked meetings"
    eversale "linkedin sales managers"
    eversale "google maps plumbers chicago"
"""

import asyncio
import sys
import os
import re
import json
from pathlib import Path
from urllib.parse import quote_plus
from typing import Optional, List, Dict, Any

# Session storage
EVERSALE_HOME = Path(os.environ.get("EVERSALE_HOME", Path.home() / ".eversale"))
SESSION_DIR = EVERSALE_HOME / "sessions"
SESSION_DIR.mkdir(parents=True, exist_ok=True)


class StealthBrowser:
    """Stealth browser with session persistence."""

    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    async def setup(self):
        """Initialize stealth browser with saved session."""
        from playwright.async_api import async_playwright

        self.playwright = await async_playwright().start()

        # Stealth browser config
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-first-run',
                '--no-default-browser-check',
            ]
        )

        # Load saved session if exists
        session_file = SESSION_DIR / "default.json"
        storage_state = None
        if session_file.exists():
            try:
                storage_state = str(session_file)
            except:
                pass

        # Stealth context config
        self.context = await self.browser.new_context(
            storage_state=storage_state,
            viewport={'width': 1280, 'height': 800},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='en-US',
            timezone_id='America/New_York',
        )

        # Anti-detection scripts
        await self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            window.chrome = { runtime: {} };
        """)

        self.page = await self.context.new_page()

    async def save_session(self):
        """Save session for next time."""
        try:
            session_file = SESSION_DIR / "default.json"
            await self.context.storage_state(path=str(session_file))
        except:
            pass

    async def close(self):
        """Cleanup."""
        await self.save_session()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def goto(self, url: str, wait: float = 2.0, scroll: bool = False):
        """Navigate with wait and optional scroll."""
        await self.page.goto(url, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(wait)

        if scroll:
            await self.page.evaluate("window.scrollBy(0, 1500)")
            await asyncio.sleep(0.5)
            await self.page.evaluate("window.scrollBy(0, 1500)")
            await asyncio.sleep(0.3)

    async def extract(self, js_code: str) -> Any:
        """Run extraction JavaScript."""
        return await self.page.evaluate(js_code)


# =============================================================================
# SITE EXTRACTORS - One function per site, clean and simple
# =============================================================================

async def extract_fb_ads(browser: StealthBrowser, query: str) -> List[Dict]:
    """Extract FB Ads Library advertisers."""
    url = f'https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=US&media_type=all&q={quote_plus(query)}&search_type=keyword_unordered'

    print(f"[*] FB Ads Library: '{query}'")
    await browser.goto(url, wait=3.0, scroll=True)

    results = await browser.extract("""() => {
        const seen = new Set();
        const results = [];

        document.querySelectorAll('a[href*="facebook.com"]').forEach(a => {
            const href = a.href || '';
            const text = (a.innerText || '').trim();
            const match = href.match(/facebook\\.com\\/(\\d{10,})/);

            if (match && text && text.length > 2 && text.length < 100) {
                const pageId = match[1];
                if (!seen.has(pageId)) {
                    seen.add(pageId);
                    results.push({
                        name: text.substring(0, 80),
                        url: 'https://www.facebook.com/' + pageId + '/',
                        page_id: pageId
                    });
                }
            }
        });

        return results;
    }""")

    # Filter UI elements
    skip = {'meta ad library', 'ad library', 'facebook', 'see ad details', 'log in', 'sign up'}
    return [r for r in results if r['name'].lower() not in skip]


async def extract_linkedin(browser: StealthBrowser, query: str) -> List[Dict]:
    """
    Extract LinkedIn profiles with Google fallback.

    Strategy:
    1. Try direct LinkedIn access first
    2. If blocked/requires login, search Google for: "site:linkedin.com/in [query]"
    3. Extract LinkedIn profile URLs from Google search results
    """
    url = f'https://www.linkedin.com/search/results/all/?keywords={quote_plus(query)}'

    print(f"[*] LinkedIn: '{query}'")
    await browser.goto(url, wait=2.0, scroll=True)

    # Try direct extraction first
    results = await browser.extract("""() => {
        const results = [];
        const seen = new Set();

        document.querySelectorAll('a[href*="/in/"]').forEach(a => {
            const href = a.href || '';
            const text = (a.innerText || '').trim();
            const match = href.match(/linkedin\\.com\\/in\\/([^\\/\\?]+)/);

            if (match && text && text.length > 2 && !seen.has(match[1])) {
                seen.add(match[1]);
                results.push({
                    name: text.substring(0, 80),
                    url: href.split('?')[0],
                    profile_id: match[1]
                });
            }
        });

        return results.slice(0, 20);
    }""")

    # Check if blocked or no results (login wall)
    if results and len(results) > 0:
        return results

    # Check for login wall
    page_text = await browser.extract("""() => document.body.innerText.toLowerCase()""")
    if 'sign in' in page_text or 'join now' in page_text or len(results) == 0:
        print(f"[*] LinkedIn blocked/requires login - trying Google fallback")

        # Fallback: Google search for LinkedIn profiles
        google_query = f'site:linkedin.com/in {query}'
        google_url = f'https://www.google.com/search?q={quote_plus(google_query)}'

        await browser.goto(google_url, wait=2.0, scroll=True)

        # Extract LinkedIn URLs from Google results
        google_results = await browser.extract("""() => {
            const results = [];
            const seen = new Set();

            // Get all links from Google search results
            document.querySelectorAll('a[href]').forEach(a => {
                const href = a.href || '';
                const text = (a.innerText || '').trim();

                // Only include actual LinkedIn profile URLs
                if (href.includes('linkedin.com/in/')) {
                    const match = href.match(/linkedin\\.com\\/in\\/([^\\/\\?&]+)/);
                    if (match && !seen.has(match[1])) {
                        seen.add(match[1]);

                        // Clean up name from Google result
                        let name = text.replace(' - LinkedIn', '').replace(' | LinkedIn', '').trim();

                        // Skip if name is too short or looks like UI text
                        if (name.length > 2 && !name.toLowerCase().includes('cached')) {
                            results.push({
                                name: name.substring(0, 80),
                                url: 'https://www.linkedin.com/in/' + match[1],
                                profile_id: match[1],
                                source: 'google_fallback'
                            });
                        }
                    }
                }
            });

            return results.slice(0, 20);
        }""")

        if google_results and len(google_results) > 0:
            print(f"[*] Google fallback found {len(google_results)} profiles")
            return google_results
        else:
            print(f"[!] Google fallback found no results")
            return []

    return results


async def extract_google_maps(browser: StealthBrowser, query: str) -> List[Dict]:
    """Extract Google Maps businesses."""
    url = f'https://www.google.com/maps/search/{quote_plus(query)}'

    print(f"[*] Google Maps: '{query}'")
    await browser.goto(url, wait=3.0)

    # Scroll results panel
    await browser.extract("""() => {
        const panel = document.querySelector('[role="feed"]');
        if (panel) { panel.scrollTop += 1000; }
    }""")
    await asyncio.sleep(1)

    return await browser.extract("""() => {
        const results = [];

        document.querySelectorAll('a[href*="/maps/place/"]').forEach(a => {
            const text = a.getAttribute('aria-label') || a.innerText || '';
            if (text && text.length > 2) {
                results.push({
                    name: text.substring(0, 100),
                    url: a.href
                });
            }
        });

        return results.slice(0, 20);
    }""")


async def extract_indeed(browser: StealthBrowser, query: str) -> List[Dict]:
    """Extract Indeed job listings."""
    url = f'https://www.indeed.com/jobs?q={quote_plus(query)}'

    print(f"[*] Indeed: '{query}'")
    await browser.goto(url, wait=2.0)

    return await browser.extract("""() => {
        const results = [];

        document.querySelectorAll('[data-jk]').forEach(card => {
            const title = card.querySelector('h2')?.innerText || '';
            const company = card.querySelector('[data-testid="company-name"]')?.innerText || '';
            const link = card.querySelector('a')?.href || '';

            if (title) {
                results.push({
                    title: title.substring(0, 100),
                    company: company.substring(0, 50),
                    url: link
                });
            }
        });

        return results.slice(0, 20);
    }""")


async def extract_amazon(browser: StealthBrowser, query: str) -> List[Dict]:
    """Extract Amazon products."""
    url = f'https://www.amazon.com/s?k={quote_plus(query)}'

    print(f"[*] Amazon: '{query}'")
    await browser.goto(url, wait=2.0)

    return await browser.extract("""() => {
        const results = [];

        document.querySelectorAll('[data-asin]:not([data-asin=""])').forEach(item => {
            const title = item.querySelector('h2')?.innerText || '';
            const price = item.querySelector('.a-price .a-offscreen')?.innerText || '';
            const link = item.querySelector('h2 a')?.href || '';
            const asin = item.getAttribute('data-asin');

            if (title && asin) {
                results.push({
                    title: title.substring(0, 100),
                    price: price,
                    url: link,
                    asin: asin
                });
            }
        });

        return results.slice(0, 20);
    }""")


async def extract_reddit(browser: StealthBrowser, query: str) -> List[Dict]:
    """Extract Reddit posts/users."""
    url = f'https://www.reddit.com/search/?q={quote_plus(query)}'

    print(f"[*] Reddit: '{query}'")
    await browser.goto(url, wait=2.0, scroll=True)

    return await browser.extract("""() => {
        const results = [];

        document.querySelectorAll('a[href*="/r/"]').forEach(a => {
            const href = a.href || '';
            const text = (a.innerText || '').trim();

            if (text && text.length > 5 && href.includes('/comments/')) {
                results.push({
                    title: text.substring(0, 100),
                    url: href
                });
            }
        });

        return results.slice(0, 20);
    }""")


async def extract_twitter(browser: StealthBrowser, query: str) -> List[Dict]:
    """Extract Twitter/X posts."""
    url = f'https://twitter.com/search?q={quote_plus(query)}&f=live'

    print(f"[*] Twitter: '{query}'")
    await browser.goto(url, wait=3.0, scroll=True)

    return await browser.extract("""() => {
        const results = [];

        document.querySelectorAll('article').forEach(tweet => {
            const text = tweet.querySelector('[data-testid="tweetText"]')?.innerText || '';
            const user = tweet.querySelector('a[href*="/status/"]')?.href || '';

            if (text) {
                results.push({
                    text: text.substring(0, 200),
                    url: user
                });
            }
        });

        return results.slice(0, 20);
    }""")


async def extract_youtube(browser: StealthBrowser, query: str) -> List[Dict]:
    """Extract YouTube videos."""
    url = f'https://www.youtube.com/results?search_query={quote_plus(query)}'

    print(f"[*] YouTube: '{query}'")
    await browser.goto(url, wait=2.0)

    return await browser.extract("""() => {
        const results = [];

        document.querySelectorAll('ytd-video-renderer').forEach(vid => {
            const title = vid.querySelector('#video-title')?.innerText || '';
            const channel = vid.querySelector('#channel-name')?.innerText || '';
            const link = vid.querySelector('a#thumbnail')?.href || '';

            if (title) {
                results.push({
                    title: title.substring(0, 100),
                    channel: channel.substring(0, 50),
                    url: link
                });
            }
        });

        return results.slice(0, 20);
    }""")


async def extract_generic(browser: StealthBrowser, url: str) -> List[Dict]:
    """Generic extraction - get all links with text."""
    print(f"[*] Generic: {url}")
    await browser.goto(url, wait=2.0)

    return await browser.extract("""() => {
        const results = [];

        document.querySelectorAll('a[href]').forEach(a => {
            const text = (a.innerText || '').trim();
            const href = a.href;

            if (text && text.length > 3 && text.length < 100 && href.startsWith('http')) {
                results.push({
                    text: text,
                    url: href
                });
            }
        });

        return results.slice(0, 30);
    }""")


# =============================================================================
# QUERY PARSER - Determine site and search term
# =============================================================================

def parse_query(prompt: str) -> tuple:
    """Parse prompt into (site, query)."""

    # Handle JSON-wrapped prompts
    try:
        parsed = json.loads(prompt)
        if isinstance(parsed, dict) and 'prompt' in parsed:
            prompt = parsed['prompt']
    except:
        pass

    prompt_lower = prompt.lower().strip()

    # Detect site
    sites = [
        (['fb ads', 'facebook ads', 'ads library', 'meta ads'], 'fb_ads'),
        (['linkedin', 'linked in'], 'linkedin'),
        (['google maps', 'gmaps', 'local business'], 'google_maps'),
        (['indeed', 'job search', 'jobs'], 'indeed'),
        (['amazon', 'amzn'], 'amazon'),
        (['reddit', 'subreddit'], 'reddit'),
        (['twitter', 'x.com', 'tweet'], 'twitter'),
        (['youtube', 'yt '], 'youtube'),
    ]

    site = 'fb_ads'  # Default
    for triggers, site_name in sites:
        if any(t in prompt_lower for t in triggers):
            site = site_name
            break

    # Extract query - try patterns in order
    query = None

    # Pattern 1: Quoted "X" or 'X'
    m = re.search(r'["\'\u201c\u201d]([^"\'\u201c\u201d]+)["\'\u201c\u201d]', prompt)
    if m:
        query = m.group(1).strip()

    # Pattern 2: "for X" at end
    if not query:
        m = re.search(r'\bfor\s+(.+)$', prompt, re.I)
        if m:
            query = m.group(1).strip()

    # Pattern 3: After colon
    if not query:
        m = re.search(r':\s*(.+)$', prompt)
        if m:
            query = m.group(1).strip()

    # Pattern 4: Remove site keywords, use remainder
    if not query:
        remainder = prompt_lower
        for triggers, _ in sites:
            for t in triggers:
                remainder = remainder.replace(t, ' ')
        for word in ['find', 'search', 'extract', 'get', 'show', 'from', 'on', 'the', 'advertisers', 'companies']:
            remainder = re.sub(rf'\b{word}\b', ' ', remainder)
        remainder = ' '.join(remainder.split()).strip()
        if remainder:
            query = remainder

    return site, query or 'business'


# =============================================================================
# MAIN - Simple entry point
# =============================================================================

async def run(prompt: str) -> List[Dict]:
    """Main extraction function."""
    site, query = parse_query(prompt)

    print(f"\n{'='*50}")
    print(f"EVERSALE EXTRACT")
    print(f"{'='*50}")

    browser = StealthBrowser()
    results = []

    try:
        await browser.setup()

        # Route to extractor
        extractors = {
            'fb_ads': extract_fb_ads,
            'linkedin': extract_linkedin,
            'google_maps': extract_google_maps,
            'indeed': extract_indeed,
            'amazon': extract_amazon,
            'reddit': extract_reddit,
            'twitter': extract_twitter,
            'youtube': extract_youtube,
        }

        extractor = extractors.get(site, extract_fb_ads)

        # Try up to 2 times on failure
        for attempt in range(2):
            try:
                results = await extractor(browser, query)
                if results:
                    break
            except Exception as e:
                if attempt == 0:
                    print(f"[!] Retry: {e}")
                    await asyncio.sleep(1)
                else:
                    print(f"[!] Failed: {e}")

    finally:
        await browser.close()

    return results


async def main():
    """CLI entry point."""
    # Check env var first (avoids Windows shell escaping issues), then fall back to sys.argv
    # Use pop() to clear env var and prevent leaking to subprocesses (Chromium, etc.)
    prompt = os.environ.pop("EVERSALE_PROMPT", "").strip()
    if not prompt and len(sys.argv) >= 2:
        prompt = ' '.join(sys.argv[1:])

    if not prompt:
        print("Usage: eversale \"fb ads booked meetings\"")
        print("       eversale \"linkedin sales managers\"")
        sys.exit(1)
    results = await run(prompt)

    # Output
    print(f"\n{'='*50}")
    print(f"RESULTS: {len(results)} found")
    print(f"{'='*50}\n")

    for i, r in enumerate(results[:15], 1):
        name = r.get('name') or r.get('title') or r.get('text', '')
        url = r.get('url', '')
        print(f"{i}. {name}")
        if url:
            print(f"   {url}")
        print()

    if len(results) > 15:
        print(f"... and {len(results) - 15} more\n")

    # JSON output
    print(f"{'='*50}")
    print("JSON:")
    print(f"{'='*50}")
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    asyncio.run(main())

