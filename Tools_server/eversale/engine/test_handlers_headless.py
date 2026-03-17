#!/usr/bin/env python3
"""
Test script to verify a11y_browser handlers work correctly in headless mode.
Tests: stealth, reddit_handler, challenge_handler, captcha detection
"""

import asyncio
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from agent.a11y_browser import (
    A11yBrowser,
    STEALTH_AVAILABLE,
    CHALLENGE_HANDLER_AVAILABLE,
    REDDIT_HANDLER_AVAILABLE,
    CAPTCHA_SOLVER_AVAILABLE,
)

# Test URLs
TEST_SITES = [
    {
        "name": "FB Ads Library",
        "url": "https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=US&q=booked%20meetings&media_type=all",
        "expect": "success or login redirect",
    },
    {
        "name": "Reddit Search",
        "url": "https://www.reddit.com/search/?q=lead%20generation%20agency",
        "expect": "API fallback if blocked",
    },
    {
        "name": "LinkedIn Search",
        "url": "https://www.linkedin.com/search/results/companies/?keywords=sdr%20agency",
        "expect": "login redirect or Google fallback",
    },
    {
        "name": "Google Maps",
        "url": "https://www.google.com/maps/search/lead+generation+agency",
        "expect": "success with stealth",
    },
    {
        "name": "Gmail",
        "url": "https://mail.google.com",
        "expect": "login redirect",
    },
    {
        "name": "Zoho Mail",
        "url": "https://mail.zoho.com",
        "expect": "login or product page redirect",
    },
]


async def test_handlers():
    """Test all handlers in headless mode."""
    print("=" * 60)
    print("EVERSALE A11Y_BROWSER HANDLER TEST (HEADLESS)")
    print("=" * 60)
    print()

    # Check handler availability
    print("Handler Status:")
    print(f"  STEALTH_AVAILABLE: {STEALTH_AVAILABLE}")
    print(f"  CHALLENGE_HANDLER_AVAILABLE: {CHALLENGE_HANDLER_AVAILABLE}")
    print(f"  REDDIT_HANDLER_AVAILABLE: {REDDIT_HANDLER_AVAILABLE}")
    print(f"  CAPTCHA_SOLVER_AVAILABLE: {CAPTCHA_SOLVER_AVAILABLE}")
    print()

    if not all([STEALTH_AVAILABLE, CHALLENGE_HANDLER_AVAILABLE, REDDIT_HANDLER_AVAILABLE]):
        print("ERROR: Not all handlers available!")
        return False

    results = []

    async with A11yBrowser(headless=True) as browser:
        print("Browser launched in headless mode with stealth")
        print()

        for site in TEST_SITES:
            print(f"Testing: {site['name']}")
            print(f"  URL: {site['url']}")

            try:
                result = await browser.navigate(
                    site["url"],
                    auto_handle_blocks=True,
                    search_query=site.get("query", "lead generation")
                )

                if result.success:
                    method = result.data.get("method", "direct")
                    final_url = result.data.get("url", "")
                    print(f"  SUCCESS via: {method}")
                    print(f"  Final URL: {final_url[:80]}...")
                    results.append({"site": site["name"], "status": "SUCCESS", "method": method})
                else:
                    error = result.error or "Unknown error"
                    print(f"  BLOCKED: {error}")

                    # Check if data has alternative info
                    if result.data:
                        if result.data.get("method") == "reddit_api":
                            print(f"  (Data fetched via API)")
                            results.append({"site": site["name"], "status": "API_FALLBACK", "method": "reddit_api"})
                        elif result.data.get("alternatives_tried"):
                            print(f"  (Alternatives were tried)")
                            results.append({"site": site["name"], "status": "BLOCKED_AFTER_RETRY", "method": "none"})
                        else:
                            results.append({"site": site["name"], "status": "BLOCKED", "method": "none"})
                    else:
                        results.append({"site": site["name"], "status": "BLOCKED", "method": "none"})

            except Exception as e:
                print(f"  ERROR: {e}")
                results.append({"site": site["name"], "status": "ERROR", "method": str(e)})

            print()

            # Small delay between sites
            await asyncio.sleep(1)

    # Summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)

    success_count = sum(1 for r in results if r["status"] in ["SUCCESS", "API_FALLBACK"])
    print(f"Success: {success_count}/{len(results)}")
    print()

    for r in results:
        status_icon = "[OK]" if r["status"] in ["SUCCESS", "API_FALLBACK"] else "[X]"
        print(f"  {status_icon} {r['site']}: {r['status']} ({r['method']})")

    return success_count >= 3  # At least half should work


if __name__ == "__main__":
    success = asyncio.run(test_handlers())
    sys.exit(0 if success else 1)
