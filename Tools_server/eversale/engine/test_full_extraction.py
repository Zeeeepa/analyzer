#!/usr/bin/env python3
"""
Full extraction test - extracts actual URLs/data from each site.
This is the real user prompt test.
"""

import asyncio
import sys
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from agent.a11y_browser import A11yBrowser


async def extract_fb_ads_advertiser(browser):
    """Extract an advertiser URL from FB Ads Library for 'booked meetings'."""
    print("\n[1/6] FB ADS LIBRARY - Finding advertiser for 'booked meetings'...")

    url = "https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=US&q=booked%20meetings&media_type=all"
    result = await browser.navigate(url, search_query="booked meetings")

    if not result.success:
        return f"BLOCKED: {result.error}"

    # Wait longer for FB SPA to fully load
    await asyncio.sleep(5)

    # Wait for content to appear
    try:
        await browser.page.wait_for_selector('[role="article"], .x1lliihq, ._7jyr', timeout=10000)
    except Exception:
        pass  # Continue even if timeout

    # Get snapshot and look for advertiser links
    snapshot = await browser.snapshot()

    # Look for links that contain advertiser info
    advertiser_url = None
    for elem in snapshot.elements:
        if elem.role == "link" and elem.name:
            # Look for links to Facebook pages (advertisers)
            if "facebook.com/" in str(elem.name).lower() or "See ad details" in elem.name:
                advertiser_url = elem.name
                break

    # Try to extract from page content (more reliable for FB's obfuscated DOM)
    if not advertiser_url:
        try:
            page_content = await browser.page.content()

            # Look for advertiser page links
            fb_page_pattern = r'href="(https://www\.facebook\.com/[a-zA-Z0-9._-]+/?)"'
            matches = re.findall(fb_page_pattern, page_content)

            # Filter out common non-advertiser pages
            excluded = ['/ads/', '/help/', '/policies/', '/privacy/', '/business/',
                        '/login', '/settings', '/marketplace', '/watch', '/groups']
            for match in matches:
                if not any(x in match.lower() for x in excluded) and len(match) > 30:
                    advertiser_url = match
                    break

            # Also try to find advertiser names in the page
            if not advertiser_url:
                # Look for "Page:..." or advertiser name patterns
                name_pattern = r'"page_name":"([^"]+)"'
                name_matches = re.findall(name_pattern, page_content)
                if name_matches:
                    return f"ADVERTISER FOUND: {name_matches[0]} (search FB for page URL)"

        except Exception:
            pass

    if advertiser_url:
        return f"ADVERTISER URL: {advertiser_url}"
    else:
        return f"PAGE LOADED: {browser.page.url} (FB Ads page loaded - check manually)"


async def extract_reddit_user(browser):
    """Extract a user profile URL from Reddit lead-gen discussion."""
    print("\n[2/6] REDDIT - Finding user from lead-gen discussion...")

    url = "https://www.reddit.com/search/?q=appointment%20setting%20agency"
    result = await browser.navigate(url, search_query="appointment setting lead gen")

    # Check if we got API data
    if result.success and result.data.get("method") == "reddit_api":
        api_data = result.data.get("api_data", {})
        posts = api_data.get("posts", [])
        if posts:
            # Get first post author (posts may be objects or dicts)
            first_post = posts[0]
            if hasattr(first_post, 'author'):
                author = first_post.author
            elif isinstance(first_post, dict):
                author = first_post.get("author", "")
            else:
                author = ""
            if author and author != "[deleted]":
                return f"USER PROFILE: https://www.reddit.com/user/{author}"

    # Fallback: try to get from page
    await asyncio.sleep(2)
    snapshot = await browser.snapshot()

    for elem in snapshot.elements:
        if elem.role == "link" and "/user/" in str(elem.name):
            return f"USER PROFILE: {elem.name}"

    # Try regex on page content
    try:
        content = await browser.page.content()
        user_pattern = r'href="(/user/[a-zA-Z0-9_-]+)"'
        matches = re.findall(user_pattern, content)
        if matches:
            return f"USER PROFILE: https://www.reddit.com{matches[0]}"
    except Exception:
        pass

    return f"PAGE LOADED: {browser.page.url} (API data: {result.data.get('method', 'browser')})"


async def extract_linkedin_prospect(browser):
    """Extract SDR/agency prospect URL from LinkedIn or search fallback."""
    print("\n[3/6] LINKEDIN - Finding SDR/agency prospect...")

    url = "https://www.linkedin.com/search/results/companies/?keywords=sdr%20lead%20generation%20agency"
    result = await browser.navigate(url, search_query="sdr lead generation agency")

    # Check if blocked/login wall
    current_url = browser.page.url

    if "login" in current_url.lower() or "authwall" in current_url.lower():
        print("  LinkedIn login wall detected - trying alternative search engines...")

        # Try multiple search engines in order of reliability
        search_engines = [
            {
                "name": "DuckDuckGo API",
                "method": "ddg_api",
                "query": "site:linkedin.com sdr lead generation agency"
            },
            {
                "name": "Bing",
                "method": "browser",
                "url": "https://www.bing.com/search?q=site%3Alinkedin.com+sdr+agency+lead+generation"
            },
            {
                "name": "Brave Search",
                "method": "browser",
                "url": "https://search.brave.com/search?q=site%3Alinkedin.com+sdr+agency"
            },
            {
                "name": "Startpage",
                "method": "browser",
                "url": "https://www.startpage.com/do/search?q=site%3Alinkedin.com+sdr+agency"
            },
        ]

        # Strategy 1: Try DuckDuckGo API (fastest, most reliable)
        try:
            from agent.search_alternatives import quick_search
            print("  Trying DuckDuckGo API search...")
            search_results = await quick_search("site:linkedin.com sdr lead generation agency", num_results=5)

            if search_results:
                print(f"  DuckDuckGo API returned {len(search_results)} results")
                # Find LinkedIn URLs in results
                for res in search_results:
                    url_to_check = res.get('url', '')
                    if 'linkedin.com/company/' in url_to_check or 'linkedin.com/in/' in url_to_check:
                        # Clean URL (remove query params)
                        clean_url = url_to_check.split('?')[0]
                        print(f"  Found LinkedIn URL: {clean_url}")
                        return f"LINKEDIN (via DuckDuckGo API): {clean_url}"
                print("  No LinkedIn company/profile URLs in results")
            else:
                print("  DuckDuckGo API returned no results")
        except Exception as e:
            print(f"  DuckDuckGo API failed: {e}")
            import traceback
            traceback.print_exc()

        # Strategy 2: Try browser-based search engines
        for engine in search_engines:
            if engine["method"] == "browser":
                try:
                    print(f"  Trying {engine['name']}...")
                    result = await browser.navigate(engine["url"])

                    if result.success:
                        # Wait for results to load
                        await asyncio.sleep(3)

                        content = await browser.page.content()

                        # Find LinkedIn URLs in search results
                        li_patterns = [
                            r'(https://www\.linkedin\.com/company/[a-zA-Z0-9_-]+)',
                            r'(https://www\.linkedin\.com/in/[a-zA-Z0-9_-]+)',
                            r'https?://[a-z]+\.linkedin\.com/(?:company|in)/([a-zA-Z0-9_-]+)',
                        ]

                        for pattern in li_patterns:
                            matches = re.findall(pattern, content)
                            if matches:
                                # Clean URL
                                url_match = matches[0] if isinstance(matches[0], str) and matches[0].startswith('http') else f"https://www.linkedin.com/company/{matches[0]}"
                                return f"LINKEDIN (via {engine['name']}): {url_match}"

                except Exception as e:
                    print(f"  {engine['name']} failed: {e}")
                    continue

        # Strategy 3: Try Serper.dev API if available (requires API key)
        try:
            import os
            if os.environ.get('SERPER_API_KEY'):
                from agent.search_alternatives import SearchAlternatives
                print("  Trying Serper.dev API...")
                search = SearchAlternatives()
                result = await search.serper_search("site:linkedin.com sdr lead generation agency", num_results=5)

                if result.get('success'):
                    for res in result.get('results', []):
                        url_to_check = res.get('url', '')
                        if 'linkedin.com/company/' in url_to_check or 'linkedin.com/in/' in url_to_check:
                            clean_url = url_to_check.split('?')[0]
                            return f"LINKEDIN (via Serper.dev): {clean_url}"
        except Exception as e:
            print(f"  Serper.dev failed: {e}")

        # If all search engines fail, report the failure
        return "BLOCKED: All search engines failed to find LinkedIn URLs (Google/Bing/DuckDuckGo/Brave/Startpage all blocked or returned no results)"

    # If we're on LinkedIn, try to find company links
    await asyncio.sleep(2)
    try:
        content = await browser.page.content()
        company_pattern = r'(https://www\.linkedin\.com/company/[a-zA-Z0-9_-]+)'
        matches = re.findall(company_pattern, content)
        if matches:
            return f"LINKEDIN COMPANY: {matches[0]}"
    except Exception:
        pass

    return f"PAGE LOADED: {current_url}"


async def extract_google_maps_listing(browser):
    """Extract agency listing URL from Google Maps."""
    print("\n[4/6] GOOGLE MAPS - Finding lead gen agency listing...")

    url = "https://www.google.com/maps/search/lead+generation+agency+near+me"
    result = await browser.navigate(url, search_query="lead generation agency")

    if not result.success:
        return f"BLOCKED: {result.error}"

    await asyncio.sleep(3)  # Wait for results to load

    # Get the current URL which should have place info
    current_url = browser.page.url

    # Try to find a specific place URL
    try:
        content = await browser.page.content()
        # Look for place URLs
        place_pattern = r'(https://www\.google\.com/maps/place/[^"\'>\s]+)'
        matches = re.findall(place_pattern, content)
        if matches:
            return f"MAPS LISTING: {matches[0][:100]}..."
    except Exception:
        pass

    # Try snapshot for listing links
    snapshot = await browser.snapshot()
    for elem in snapshot.elements:
        if elem.role == "link" and "maps/place" in str(elem.name):
            return f"MAPS LISTING: {elem.name}"

    return f"MAPS PAGE: {current_url}"


async def extract_gmail_url(browser):
    """Get final URL when navigating to Gmail (not logged in)."""
    print("\n[5/6] GMAIL - Getting final URL (not logged in)...")

    url = "https://mail.google.com"
    result = await browser.navigate(url)

    await asyncio.sleep(2)
    final_url = browser.page.url

    return f"FINAL URL: {final_url}"


async def extract_zoho_url(browser):
    """Get final URL when navigating to Zoho Mail (not logged in)."""
    print("\n[6/6] ZOHO MAIL - Getting final URL (not logged in)...")

    url = "https://mail.zoho.com"
    result = await browser.navigate(url)

    await asyncio.sleep(2)
    final_url = browser.page.url

    return f"FINAL URL: {final_url}"


async def main():
    print("=" * 70)
    print("EVERSALE CLI - FULL EXTRACTION TEST (HEADLESS)")
    print("=" * 70)

    results = {}

    async with A11yBrowser(headless=True) as browser:
        results["fb_ads"] = await extract_fb_ads_advertiser(browser)
        results["reddit"] = await extract_reddit_user(browser)
        results["linkedin"] = await extract_linkedin_prospect(browser)
        results["google_maps"] = await extract_google_maps_listing(browser)
        results["gmail"] = await extract_gmail_url(browser)
        results["zoho"] = await extract_zoho_url(browser)

    print("\n" + "=" * 70)
    print("FINAL RESULTS")
    print("=" * 70)

    for site, result in results.items():
        print(f"\n{site.upper()}:")
        print(f"  {result}")

    print("\n" + "=" * 70)
    print("TEST COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
