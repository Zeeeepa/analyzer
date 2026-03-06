"""
Test FB Ads extraction at scale - verify we can get 50+ ads
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.playwright_direct import PlaywrightClient


async def test_fb_ads_scale():
    """Test extracting 50+ ads from FB Ads Library"""

    client = None
    try:
        print("Initializing Playwright client...")
        client = PlaywrightClient(headless=True, browser_type="firefox")  # Try Firefox for better compatibility

        # Explicitly connect browser first
        print("Connecting browser...")
        try:
            await client.connect()
            print(f"Browser connected! Page: {client.page}, Context: {client.context}")
            print(f"Connected flag: {client._connected}")
        except Exception as e:
            print(f"Connect failed with exception: {e}")
            import traceback
            traceback.print_exc()
            return

        # Ensure we have a page
        if not client.page:
            print("ERROR: Page is None after connect!")
            return

        # Navigate to FB Ads Library with broad search
        url = "https://www.facebook.com/ads/library/?active_status=all&ad_type=political_and_issue_ads&country=US&media_type=all&q=marketing"
        print(f"\nNavigating to: {url}")
        nav_result = await client.navigate(url)
        print(f"Navigation result: {nav_result}")
        print(f"Page after navigate: {client.page}")

        # Wait for initial load
        await asyncio.sleep(5)

        # Scroll multiple times to load more ads
        print("\nScrolling to load more ads...")
        for i in range(10):
            print(f"Scroll {i+1}/10...")
            await client.scroll("down")
            await asyncio.sleep(2)

        # Extract ads
        print("\nExtracting ads...")
        result = await client.extract_fb_ads_batch(max_ads=200)

        if result.get("success"):
            ads = result.get("ads", [])
            count = len(ads)

            print(f"\n{'='*60}")
            print(f"RESULTS: Extracted {count} ads")
            print(f"{'='*60}")

            if count >= 50:
                print(f"SUCCESS: Met target of 50+ ads")
            else:
                print(f"WARNING: Only got {count} ads (target: 50+)")

            # Show sample of landing URLs
            print(f"\nSample of landing URLs (first 10):")
            for i, ad in enumerate(ads[:10], 1):
                landing_url = ad.get("landing_page_url", "N/A")
                ad_text = ad.get("ad_text", "")[:50]
                print(f"{i}. {landing_url}")
                print(f"   Text: {ad_text}...")

            # Show distribution of ad types
            with_urls = sum(1 for ad in ads if ad.get("landing_page_url"))
            with_text = sum(1 for ad in ads if ad.get("ad_text"))

            print(f"\nAd content breakdown:")
            print(f"  - Ads with landing URLs: {with_urls}/{count}")
            print(f"  - Ads with text: {with_text}/{count}")

        else:
            error = result.get("error", "Unknown error")
            print(f"\nERROR: Extraction failed - {error}")

    except Exception as e:
        print(f"\nEXCEPTION: {str(e)}")
        import traceback
        traceback.print_exc()

    finally:
        if client:
            print("\nClosing browser...")
            await client.disconnect()


if __name__ == "__main__":
    asyncio.run(test_fb_ads_scale())
