#!/usr/bin/env python3
"""
Test alternative search engines for LinkedIn URL extraction.
Validates that we can find real LinkedIn URLs without hardcoding them.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from agent.search_alternatives import quick_search, SearchAlternatives


async def test_duckduckgo_api():
    """Test DuckDuckGo API for LinkedIn searches."""
    print("\n" + "=" * 70)
    print("TEST 1: DuckDuckGo API - LinkedIn Company Search")
    print("=" * 70)

    query = "site:linkedin.com sdr lead generation agency"
    print(f"Query: {query}\n")

    results = await quick_search(query, num_results=5)

    if not results:
        print("FAILED: No results returned")
        return False

    print(f"SUCCESS: Found {len(results)} results\n")

    linkedin_urls = []
    for i, r in enumerate(results, 1):
        url = r.get('url', '')
        title = r.get('title', 'N/A')

        if 'linkedin.com' in url:
            linkedin_urls.append(url)
            print(f"{i}. {url}")
            print(f"   Title: {title[:70]}")
            print()

    if linkedin_urls:
        print(f"PASSED: Found {len(linkedin_urls)} LinkedIn URLs")
        return True
    else:
        print("FAILED: No LinkedIn URLs found in results")
        return False


async def test_serper_api():
    """Test Serper.dev API if available."""
    print("\n" + "=" * 70)
    print("TEST 2: Serper.dev API - LinkedIn Company Search")
    print("=" * 70)

    import os
    if not os.environ.get('SERPER_API_KEY'):
        print("SKIPPED: No SERPER_API_KEY environment variable set")
        print("Get a free API key at: https://serper.dev/\n")
        return None

    search = SearchAlternatives()
    result = await search.serper_search("site:linkedin.com sdr agency", num_results=5)

    if not result.get('success'):
        print(f"FAILED: {result.get('error')}")
        return False

    results_list = result.get('results', [])
    print(f"SUCCESS: Found {len(results_list)} results\n")

    linkedin_urls = []
    for i, r in enumerate(results_list, 1):
        url = r.get('url', '')
        title = r.get('title', 'N/A')

        if 'linkedin.com' in url:
            linkedin_urls.append(url)
            print(f"{i}. {url}")
            print(f"   Title: {title[:70]}")
            print()

    if linkedin_urls:
        print(f"PASSED: Found {len(linkedin_urls)} LinkedIn URLs")
        return True
    else:
        print("FAILED: No LinkedIn URLs found")
        return False


async def test_linkedin_profile_search():
    """Test finding LinkedIn profiles (not just companies)."""
    print("\n" + "=" * 70)
    print("TEST 3: DuckDuckGo API - LinkedIn Profile Search")
    print("=" * 70)

    query = "site:linkedin.com/in/ sales development representative"
    print(f"Query: {query}\n")

    results = await quick_search(query, num_results=5)

    if not results:
        print("FAILED: No results returned")
        return False

    print(f"SUCCESS: Found {len(results)} results\n")

    profile_urls = []
    for i, r in enumerate(results, 1):
        url = r.get('url', '')
        title = r.get('title', 'N/A')

        if 'linkedin.com/in/' in url:
            profile_urls.append(url)
            print(f"{i}. {url}")
            print(f"   Title: {title[:70]}")
            print()

    if profile_urls:
        print(f"PASSED: Found {len(profile_urls)} LinkedIn profile URLs")
        return True
    else:
        print("FAILED: No LinkedIn profile URLs found")
        return False


async def main():
    print("=" * 70)
    print("LINKEDIN SEARCH ALTERNATIVES TEST SUITE")
    print("=" * 70)
    print("\nThis test validates that we can find real LinkedIn URLs")
    print("using alternative search engines (no hardcoded URLs).\n")

    results = {
        "DuckDuckGo API (Companies)": await test_duckduckgo_api(),
        "Serper.dev API": await test_serper_api(),
        "DuckDuckGo API (Profiles)": await test_linkedin_profile_search(),
    }

    print("\n" + "=" * 70)
    print("FINAL RESULTS")
    print("=" * 70)

    for test_name, result in results.items():
        if result is True:
            status = "PASSED"
        elif result is False:
            status = "FAILED"
        else:
            status = "SKIPPED"

        print(f"{test_name}: {status}")

    passed = sum(1 for r in results.values() if r is True)
    failed = sum(1 for r in results.values() if r is False)
    skipped = sum(1 for r in results.values() if r is None)

    print(f"\nSummary: {passed} passed, {failed} failed, {skipped} skipped")
    print("=" * 70)

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
