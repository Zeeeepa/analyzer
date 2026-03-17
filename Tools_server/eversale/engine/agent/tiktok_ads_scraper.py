"""
TikTok Ads Library Deep Scraper - Forever Mode

Supports unlimited keywords, runs forever with anti-detection measures,
persists progress, and can resume from interruptions.

Supports two TikTok ad sources:
1. TikTok Ad Library (library.tiktok.com/ads/) - Official transparency tool
2. TikTok Creative Center Top Ads (ads.tiktok.com/business/creativecenter)

Usage:
    python3 tiktok_ads_scraper.py "keyword1, keyword2, keyword3" --deep
    python3 tiktok_ads_scraper.py keywords.txt --forever
    python3 tiktok_ads_scraper.py --resume  # Resume last session
"""

import os
import sys
import json
import random
import asyncio
import hashlib
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field, asdict

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from loguru import logger

# State file location
STATE_DIR = Path(__file__).parent / "memory" / "tiktok_ads_state"
RESULTS_DIR = Path(__file__).parent / "results" / "tiktok_ads"


@dataclass
class TikTokScraperState:
    """Persistent state for the TikTok Ads scraper."""
    session_id: str
    keywords: List[str]
    current_keyword_idx: int = 0
    total_ads_found: int = 0
    ads_by_keyword: Dict[str, int] = field(default_factory=dict)
    processed_ad_ids: List[str] = field(default_factory=list)
    errors: List[Dict] = field(default_factory=list)
    started_at: str = ""
    last_activity: str = ""
    status: str = "pending"  # pending, running, paused, completed
    source: str = "library"  # library or creative_center

    # Anti-detection settings
    min_delay_seconds: float = 3.0
    max_delay_seconds: float = 8.0
    scroll_pause_min: float = 0.5
    scroll_pause_max: float = 2.0
    keywords_before_long_pause: int = 5
    long_pause_minutes: int = 2

    @classmethod
    def create(cls, keywords: List[str], session_id: str = None, source: str = "library") -> "TikTokScraperState":
        """Create new scraper state."""
        if not session_id:
            session_id = hashlib.md5(
                f"{','.join(keywords)}_{datetime.now().isoformat()}".encode()
            ).hexdigest()[:12]

        return cls(
            session_id=session_id,
            keywords=keywords,
            started_at=datetime.now().isoformat(),
            last_activity=datetime.now().isoformat(),
            status="pending",
            source=source
        )

    @classmethod
    def load(cls, session_id: str = None) -> Optional["TikTokScraperState"]:
        """Load state from disk. If no session_id, load most recent."""
        STATE_DIR.mkdir(parents=True, exist_ok=True)

        if session_id:
            state_file = STATE_DIR / f"{session_id}.json"
        else:
            # Find most recent state file
            state_files = sorted(STATE_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            if not state_files:
                return None
            state_file = state_files[0]

        if not state_file.exists():
            return None

        try:
            with open(state_file) as f:
                data = json.load(f)
            return cls(**data)
        except Exception as e:
            logger.error(f"Failed to load state: {e}")
            return None

    def save(self):
        """Save state to disk."""
        logger.info(f"[TIKTOK_SCRAPER] Saving state for session {self.session_id}")
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        self.last_activity = datetime.now().isoformat()

        state_file = STATE_DIR / f"{self.session_id}.json"
        try:
            with open(state_file, 'w') as f:
                json.dump(asdict(self), f, indent=2)
            logger.info(f"[TIKTOK_SCRAPER] State saved to {state_file}")
        except Exception as e:
            logger.error(f"[TIKTOK_SCRAPER] Failed to save state: {e}")

    def mark_ad_processed(self, ad_id: str):
        """Mark an ad as processed to avoid duplicates."""
        if ad_id not in self.processed_ad_ids:
            self.processed_ad_ids.append(ad_id)
            self.total_ads_found += 1

    def is_ad_processed(self, ad_id: str) -> bool:
        """Check if ad was already processed."""
        return ad_id in self.processed_ad_ids

    def get_random_delay(self) -> float:
        """Get random delay for anti-detection."""
        return random.uniform(self.min_delay_seconds, self.max_delay_seconds)

    def get_scroll_pause(self) -> float:
        """Get random scroll pause for human-like behavior."""
        return random.uniform(self.scroll_pause_min, self.scroll_pause_max)

    def should_long_pause(self) -> bool:
        """Check if we should take a long pause (every N keywords)."""
        return (self.current_keyword_idx > 0 and
                self.current_keyword_idx % self.keywords_before_long_pause == 0)


class TikTokAdsDeepScraper:
    """
    Deep scraper for TikTok Ads with anti-detection and persistence.

    Features:
    - Processes unlimited keywords
    - Human-like scrolling and delays
    - Saves progress after each keyword
    - Can resume from interruptions
    - Deduplicates ads across keywords
    - Saves results incrementally
    - Supports both TikTok Ad Library and Creative Center
    """

    def __init__(self, mcp_client=None, browser=None, state: TikTokScraperState = None):
        """
        Initialize the scraper.

        Args:
            mcp_client: MCP client for tool calls (preferred)
            browser: PlaywrightDirect browser instance (legacy)
            state: Existing state to resume, or None for new session
        """
        self.mcp = mcp_client
        self.browser = browser
        self.state = state
        self.results_file = None
        self._stop_requested = False

    async def initialize_browser(self):
        """Initialize browser if not provided - via MCP client."""
        if self.mcp is None and self.browser is None:
            raise RuntimeError("No MCP client or browser available. Cannot initialize.")

    def request_stop(self):
        """Request graceful stop (will finish current keyword)."""
        self._stop_requested = True
        logger.info("Stop requested - will finish current keyword and save state")

    async def _call_tool(self, tool_name: str, args: dict) -> dict:
        """Call a tool through MCP or browser."""
        try:
            if self.mcp:
                result = await self.mcp.call_tool(tool_name, args)
                logger.debug(f"[TIKTOK_SCRAPER] Tool {tool_name} result: {type(result)}")
                return result
            elif self.browser:
                result = await self.browser.call_tool(tool_name, args)
                logger.debug(f"[TIKTOK_SCRAPER] Tool {tool_name} result: {type(result)}")
                return result
            else:
                raise RuntimeError("No MCP client or browser available")
        except Exception as e:
            logger.error(f"[TIKTOK_SCRAPER] Tool {tool_name} failed: {e}")
            raise

    async def _human_like_scroll(self, max_scrolls: int = 30):
        """Scroll the page in a human-like manner to load content."""
        await asyncio.sleep(2)

        for i in range(min(max_scrolls, 5)):
            scroll_pos = random.randint(500, 2000) * (i + 1)

            try:
                await self._call_tool('playwright_evaluate', {
                    'function': f'window.scrollTo(0, {scroll_pos})'
                })
            except Exception:
                break

            pause = self.state.get_scroll_pause() if self.state else random.uniform(0.5, 1.5)
            await asyncio.sleep(pause)

        try:
            await self._call_tool('playwright_evaluate', {
                'function': 'window.scrollTo(0, 0)'
            })
        except Exception:
            pass

        await asyncio.sleep(0.5)

    async def _extract_ads_from_page(self, max_ads: int = 100) -> List[Dict]:
        """Extract ads from current page using TikTok extraction tool."""
        logger.info(f"[TIKTOK_SCRAPER] Extracting ads from page (max: {max_ads})")
        result = await self._call_tool('playwright_extract_tiktok_ads', {'max_ads': max_ads})

        logger.debug(f"[TIKTOK_SCRAPER] Extraction result type: {type(result)}, keys: {result.keys() if isinstance(result, dict) else 'N/A'}")

        if isinstance(result, dict):
            success = result.get('success', False)
            ads = result.get('ads', result.get('advertisers', []))
            logger.info(f"[TIKTOK_SCRAPER] Extraction success: {success}, ads found: {len(ads)}")
            if success and ads:
                return ads
        return []

    async def _search_keyword_library(self, keyword: str) -> List[Dict]:
        """
        Search TikTok Ad Library for a single keyword.
        URL: https://library.tiktok.com/ads/
        """
        import urllib.parse

        # TikTok Ad Library URL with search
        search_url = f"https://library.tiktok.com/ads?region=US&search_value={urllib.parse.quote(keyword)}"

        logger.debug(f"_search_keyword_library called for: '{keyword}'")
        logger.debug(f"URL: {search_url}")

        delay = self.state.get_random_delay() if self.state else random.uniform(2, 5)
        logger.debug(f"Waiting {delay:.1f}s (anti-detection)...")
        await asyncio.sleep(delay)

        try:
            nav_result = await self._call_tool('playwright_navigate', {'url': search_url})
            logger.debug(f"Navigation result: {nav_result}")

            if not nav_result.get('success'):
                logger.debug(f"Navigation failed for keyword '{keyword}'")
                return []

            # TikTok Ad Library is a React app - needs time to load
            logger.debug("Waiting 3s for React app to load...")
            await asyncio.sleep(3)

            # Human-like scrolling to load more results
            logger.debug("Scrolling to load content...")
            await self._human_like_scroll(max_scrolls=40)

            # Extract ads
            logger.debug("Extracting ads...")
            ads = await self._extract_ads_from_page(max_ads=100)
            logger.debug(f"Extracted {len(ads)} ads")

            # Filter out already processed ads
            new_ads = []
            base_count = self.state.total_ads_found if self.state else 0
            for ad in ads:
                ad_id = ad.get('ad_id', '')
                if ad_id and self.state and not self.state.is_ad_processed(ad_id):
                    self.state.mark_ad_processed(ad_id)
                    ad['search_keyword'] = keyword
                    ad['extracted_at'] = datetime.now().isoformat()
                    ad['source'] = 'tiktok_ad_library'
                    new_ads.append(ad)

                    lead_num = base_count + len(new_ads)
                    advertiser = ad.get('advertiser', ad.get('advertiser_name', 'Unknown'))[:30]
                    print(f"  + Lead #{lead_num}: {advertiser}", flush=True)

            logger.info(f"Found {len(ads)} ads, {len(new_ads)} new for '{keyword}'")
            return new_ads

        except Exception as e:
            logger.error(f"Error searching '{keyword}': {e}")
            if self.state:
                self.state.errors.append({
                    'keyword': keyword,
                    'error': str(e),
                    'time': datetime.now().isoformat()
                })
            return []

    async def _search_keyword_creative_center(self, keyword: str) -> List[Dict]:
        """
        Search TikTok Creative Center Top Ads for a single keyword.
        URL: https://ads.tiktok.com/business/creativecenter/inspiration/topads/pad/en
        """
        import urllib.parse

        # TikTok Creative Center URL with search
        search_url = (
            f"https://ads.tiktok.com/business/creativecenter/inspiration/topads/pad/en"
            f"?period=30&region=US&keyword={urllib.parse.quote(keyword)}"
        )

        logger.debug(f"_search_keyword_creative_center for: '{keyword}'")
        logger.debug(f"URL: {search_url}")

        delay = self.state.get_random_delay() if self.state else random.uniform(2, 5)
        logger.debug(f"Waiting {delay:.1f}s (anti-detection)...")
        await asyncio.sleep(delay)

        try:
            nav_result = await self._call_tool('playwright_navigate', {'url': search_url})
            logger.debug(f"Navigation result: {nav_result}")

            if not nav_result.get('success'):
                logger.debug(f"Navigation failed for keyword '{keyword}'")
                return []

            # Creative Center needs time to load
            logger.debug("Waiting 3s for page to load...")
            await asyncio.sleep(3)

            # Scroll to load more content
            logger.debug("Scrolling to load content...")
            await self._human_like_scroll(max_scrolls=40)

            # Extract ads
            logger.debug("Extracting ads...")
            ads = await self._extract_ads_from_page(max_ads=100)
            logger.debug(f"Extracted {len(ads)} ads")

            # Filter out already processed ads
            new_ads = []
            base_count = self.state.total_ads_found if self.state else 0
            for ad in ads:
                ad_id = ad.get('ad_id', ad.get('video_id', ''))
                if ad_id and self.state and not self.state.is_ad_processed(ad_id):
                    self.state.mark_ad_processed(ad_id)
                    ad['search_keyword'] = keyword
                    ad['extracted_at'] = datetime.now().isoformat()
                    ad['source'] = 'tiktok_creative_center'
                    new_ads.append(ad)

                    lead_num = base_count + len(new_ads)
                    advertiser = ad.get('advertiser', ad.get('title', 'Unknown'))[:30]
                    print(f"  + Lead #{lead_num}: {advertiser}", flush=True)

            logger.info(f"Found {len(ads)} ads, {len(new_ads)} new for '{keyword}'")
            return new_ads

        except Exception as e:
            logger.error(f"Error searching '{keyword}': {e}")
            if self.state:
                self.state.errors.append({
                    'keyword': keyword,
                    'error': str(e),
                    'time': datetime.now().isoformat()
                })
            return []

    async def _search_keyword(self, keyword: str) -> List[Dict]:
        """Search using the configured source."""
        if self.state and self.state.source == "creative_center":
            return await self._search_keyword_creative_center(keyword)
        return await self._search_keyword_library(keyword)

    def _save_results(self, ads: List[Dict], keyword: str):
        """Save results to file incrementally."""
        logger.info(f"[TIKTOK_SCRAPER] _save_results called with {len(ads)} ads for '{keyword}'")
        if not ads:
            logger.warning(f"[TIKTOK_SCRAPER] No ads to save for '{keyword}'")
            return

        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        logger.debug(f"[TIKTOK_SCRAPER] Results dir: {RESULTS_DIR}")

        if self.results_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            session_id = self.state.session_id if self.state else "unknown"
            self.results_file = RESULTS_DIR / f"tiktok_ads_{session_id}_{timestamp}.jsonl"
            logger.info(f"[TIKTOK_SCRAPER] Created results file: {self.results_file}")

        try:
            with open(self.results_file, 'a') as f:
                for ad in ads:
                    f.write(json.dumps(ad, default=str) + '\n')
            logger.info(f"[TIKTOK_SCRAPER] Saved {len(ads)} ads to {self.results_file}")
        except Exception as e:
            logger.error(f"[TIKTOK_SCRAPER] Failed to save results: {e}")

    async def run_forever(
        self,
        keywords: List[str] = None,
        max_ads_per_keyword: int = 100,
        on_keyword_complete: callable = None
    ) -> Dict[str, Any]:
        """Run the scraper forever (or until stopped)."""
        if self.state is None:
            if keywords:
                self.state = TikTokScraperState.create(keywords)
            else:
                self.state = TikTokScraperState.load()
                if self.state is None:
                    raise ValueError("No keywords provided and no state to resume")
        elif keywords:
            self.state.keywords = keywords

        self.state.status = "running"
        self.state.save()

        await self.initialize_browser()

        all_ads = []
        keywords_processed = 0

        try:
            while not self._stop_requested:
                if self.state.current_keyword_idx >= len(self.state.keywords):
                    self.state.current_keyword_idx = 0
                    logger.info("Completed all keywords, starting over...")

                    pause_mins = self.state.long_pause_minutes
                    logger.info(f"Taking {pause_mins} minute break before next cycle...")
                    await asyncio.sleep(pause_mins * 60)

                keyword = self.state.keywords[self.state.current_keyword_idx]

                ads = await self._search_keyword(keyword)

                if ads:
                    all_ads.extend(ads)
                    self._save_results(ads, keyword)
                    self.state.ads_by_keyword[keyword] = (
                        self.state.ads_by_keyword.get(keyword, 0) + len(ads)
                    )

                self.state.current_keyword_idx += 1
                keywords_processed += 1
                self.state.save()

                if on_keyword_complete:
                    try:
                        on_keyword_complete(keyword, ads, self.state)
                    except Exception as e:
                        logger.warning(f"Callback error: {e}")

                if self.state.should_long_pause():
                    pause_mins = self.state.long_pause_minutes
                    logger.info(f"Taking {pause_mins} minute break (anti-detection)...")
                    await asyncio.sleep(pause_mins * 60)

        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        except Exception as e:
            logger.error(f"Scraper error: {e}")
            self.state.errors.append({
                'error': str(e),
                'time': datetime.now().isoformat()
            })
        finally:
            self.state.status = "paused" if self._stop_requested else "completed"
            self.state.save()

        return {
            'session_id': self.state.session_id,
            'keywords_processed': keywords_processed,
            'total_ads_found': self.state.total_ads_found,
            'unique_ads': len(self.state.processed_ad_ids),
            'results_file': str(self.results_file) if self.results_file else None,
            'status': self.state.status,
            'can_resume': self.state.current_keyword_idx < len(self.state.keywords)
        }

    async def run_single_pass(
        self,
        keywords: List[str],
        max_ads_per_keyword: int = 100
    ) -> Dict[str, Any]:
        """Run a single pass through all keywords."""
        logger.debug(f"run_single_pass starting with {len(keywords)} keywords")
        self.state = TikTokScraperState.create(keywords)
        self.state.status = "running"

        logger.debug(f"State created with session_id: {self.state.session_id}")

        await self.initialize_browser()
        logger.debug("Browser initialized")

        all_ads = []

        try:
            for i, keyword in enumerate(keywords):
                logger.debug(f"Processing keyword {i+1}/{len(keywords)}: '{keyword}'")
                if self._stop_requested:
                    logger.debug("Stop requested, breaking loop")
                    break

                self.state.current_keyword_idx = i
                ads = await self._search_keyword(keyword)
                logger.debug(f"Got {len(ads)} ads for '{keyword}'")

                if ads:
                    all_ads.extend(ads)
                    self._save_results(ads, keyword)
                    self.state.ads_by_keyword[keyword] = len(ads)

                self.state.save()

        except Exception as e:
            logger.error(f"[TIKTOK_SCRAPER] Error in run_single_pass: {e}")
            import traceback
            logger.error(traceback.format_exc())
        finally:
            self.state.status = "completed"
            self.state.save()
            logger.info(f"[TIKTOK_SCRAPER] run_single_pass completed with {len(all_ads)} total ads")

        return {
            'session_id': self.state.session_id,
            'keywords_processed': len(keywords),
            'total_ads': len(all_ads),
            'unique_ads': len(self.state.processed_ad_ids),
            'results_file': str(self.results_file) if self.results_file else None,
            'ads': all_ads
        }

    async def run_until_target(
        self,
        keywords: List[str],
        target_count: int,
        max_ads_per_keyword: int = 100,
        on_keyword_complete: callable = None
    ) -> Dict[str, Any]:
        """Run until we collect the target number of ads."""
        logger.debug(f"run_until_target: target={target_count}, keywords={len(keywords)}")

        if self.state is None:
            self.state = TikTokScraperState.create(keywords)
        self.state.status = "running"
        self.state.save()

        await self.initialize_browser()
        logger.debug("Browser initialized")

        all_ads = []
        cycles = 0
        max_cycles = 50

        try:
            while self.state.total_ads_found < target_count and not self._stop_requested:
                cycles += 1
                if cycles > max_cycles:
                    logger.debug(f"Max cycles ({max_cycles}) reached, stopping")
                    break

                logger.debug(f"Cycle {cycles}, collected {self.state.total_ads_found}/{target_count}")

                for i, keyword in enumerate(keywords):
                    if self.state.total_ads_found >= target_count:
                        logger.debug(f"Target reached ({self.state.total_ads_found}), stopping")
                        break

                    if self._stop_requested:
                        break

                    self.state.current_keyword_idx = i
                    ads = await self._search_keyword(keyword)

                    if ads:
                        all_ads.extend(ads)
                        self._save_results(ads, keyword)
                        self.state.ads_by_keyword[keyword] = (
                            self.state.ads_by_keyword.get(keyword, 0) + len(ads)
                        )

                    self.state.save()

                    if on_keyword_complete:
                        try:
                            on_keyword_complete(keyword, ads, self.state)
                        except Exception as e:
                            logger.warning(f"Callback error: {e}")

                if self.state.total_ads_found < target_count and not self._stop_requested:
                    pause = self.state.long_pause_minutes * 60
                    logger.debug(f"Cycle complete, waiting {self.state.long_pause_minutes}min before next cycle...")
                    await asyncio.sleep(pause)

        except Exception as e:
            logger.error(f"[TIKTOK_SCRAPER] Error in run_until_target: {e}")
            self.state.errors.append({
                'error': str(e),
                'time': datetime.now().isoformat()
            })
        finally:
            self.state.status = "completed" if self.state.total_ads_found >= target_count else "paused"
            self.state.save()

        return {
            'session_id': self.state.session_id,
            'keywords_processed': cycles * len(keywords),
            'total_ads_found': self.state.total_ads_found,
            'unique_ads': len(self.state.processed_ad_ids),
            'results_file': str(self.results_file) if self.results_file else None,
            'status': self.state.status,
            'target_reached': self.state.total_ads_found >= target_count,
            'ads': all_ads
        }


def detect_tiktok_ads_scraper_intent(prompt: str) -> dict:
    """
    Detect if prompt is requesting TikTok Ads scraping and extract parameters.

    Returns dict with:
        - is_tiktok_ads: bool - whether this is a TikTok ads scraper request
        - mode: 'forever' | 'target' | 'single_pass'
        - target_count: int or None - total ads to collect
        - per_keyword: int or None - ads per keyword
        - keywords: list of keywords
        - source: 'library' | 'creative_center'
    """
    import re
    prompt_lower = prompt.lower()

    result = {
        'is_tiktok_ads': False,
        'mode': 'single_pass',
        'target_count': None,
        'per_keyword': None,
        'keywords': [],
        'source': 'library'
    }

    # Check if this is TikTok Ads related
    tiktok_ads_indicators = [
        'tiktok ads', 'tiktok ad', 'tiktok ad library', 'tiktok ads library',
        'library.tiktok.com', 'tiktok creative center', 'tiktok top ads',
        'ads.tiktok.com', 'tiktok advertising'
    ]
    has_tiktok_ads = any(ind in prompt_lower for ind in tiktok_ads_indicators)

    if not has_tiktok_ads:
        return result

    # Determine source
    if 'creative center' in prompt_lower or 'top ads' in prompt_lower or 'ads.tiktok.com' in prompt_lower:
        result['source'] = 'creative_center'

    # Check for scraping/extraction intent
    scraping_indicators = [
        'deep', 'scrape', 'extract', 'collect', 'gather', 'find', 'get',
        'all', 'many', 'lots', 'bunch', 'ton',
        'forever', 'never stop', 'keep going', 'continuous', 'continuously',
        'unlimited', 'infinite', 'nonstop', 'non-stop', 'always',
        'leads', 'advertisers', 'ads', 'companies', 'businesses',
        r'\d+\s*(leads|ads|advertisers|per|each|total)'
    ]

    has_scraping_intent = any(
        (re.search(ind, prompt_lower) if '\\' in ind else ind in prompt_lower)
        for ind in scraping_indicators
    )

    if not has_scraping_intent:
        return result

    result['is_tiktok_ads'] = True

    # Detect mode and targets
    forever_patterns = [
        'forever', 'never stop', 'keep going', 'continuous', 'continuously',
        'unlimited', 'infinite', 'nonstop', 'non-stop', 'always on',
        'run indefinitely', '24/7', 'dont stop', "don't stop", 'do not stop'
    ]
    if any(p in prompt_lower for p in forever_patterns):
        result['mode'] = 'forever'

    # Target count patterns
    target_match = re.search(
        r'(?:get|collect|find|extract|scrape|gather)\s*(\d+)\s*(?:leads?|ads?|advertisers?|companies?|businesses?)?',
        prompt_lower
    )
    if target_match:
        result['target_count'] = int(target_match.group(1))
        result['mode'] = 'target'

    if not result['target_count']:
        target_match = re.search(r'(\d+)\s*(?:leads?|ads?|advertisers?)', prompt_lower)
        if target_match:
            result['target_count'] = int(target_match.group(1))
            result['mode'] = 'target'

    # Per-keyword patterns
    per_kw_match = re.search(
        r'(\d+)\s*(?:per|each|for each|for every)\s*(?:keyword|kw|search|term)',
        prompt_lower
    )
    if per_kw_match:
        result['per_keyword'] = int(per_kw_match.group(1))

    # Extract keywords - multiple patterns
    keywords = []

    # Pattern 1: "keywords: X, Y, Z"
    match = re.search(r'(?<!per\s)(?<!each\s)keywords?[:\s]+([^.]+?)(?:\.|$|(?=\s+(?:get|collect|from|in)))', prompt, re.I)
    if match:
        kw_text = match.group(1)
        kw_text = re.sub(r'\s+(get|collect|find|extract|per|each)\b.*', '', kw_text, flags=re.I)
        keywords = [k.strip() for k in kw_text.split(',') if k.strip()]
        if keywords and any('library' in k.lower() or 'ads' in k.lower() for k in keywords):
            keywords = []

    # Pattern 2: "search for X, Y, Z"
    if not keywords:
        match = re.search(r'search(?:ing)?\s+(?:for\s+)?["\']?([^"\']+?)["\']?(?:\s+(?:on|in|from)|$)', prompt, re.I)
        if match:
            keywords = [k.strip() for k in match.group(1).split(',') if k.strip()]

    # Pattern 3: "with keywords X, Y, Z"
    if not keywords:
        match = re.search(r'(?:with|using)\s+keywords?\s+([^.]+)', prompt, re.I)
        if match:
            keywords = [k.strip() for k in match.group(1).split(',') if k.strip()]

    # Pattern 4: Quoted strings
    if not keywords:
        keywords = re.findall(r'["\']([^"\']+)["\']', prompt)

    # Clean keywords
    bad_phrases = ['from tiktok', 'tiktok ads', 'per keyword', 'per kw', 'each keyword', 'from ads', 'from the']
    keywords = [
        k for k in keywords
        if not any(bp in k.lower() for bp in bad_phrases) and len(k) < 100
    ]

    result['keywords'] = keywords
    return result


async def integrate_with_brain(brain, prompt: str) -> Optional[str]:
    """
    Integration function for brain_enhanced_v2.py
    Handles various TikTok Ads scraping prompts naturally.

    Examples that work:
        - "Go deep on TikTok ads with keywords: booked meetings, sales automation"
        - "Get 1000 leads from TikTok Ads Library for: sales, marketing, growth"
        - "Scrape TikTok ads forever, never stop, keywords: AI tools, automation"
        - "Find 500 advertisers on TikTok Ad Library searching for SaaS"
        - "Collect 100 ads per keyword from TikTok creative center: cold email, outbound"
    """
    from rich.console import Console
    console = Console()

    logger.info(f"[TIKTOK_SCRAPER] integrate_with_brain called with prompt: {prompt[:100]}...")

    intent = detect_tiktok_ads_scraper_intent(prompt)

    if not intent['is_tiktok_ads']:
        return None

    keywords = intent['keywords']
    target_count = intent['target_count']
    per_keyword = intent['per_keyword']
    mode = intent['mode']
    source = intent['source']

    if not keywords:
        return "Please provide keywords to search. Examples:\n- 'Get 1000 leads from TikTok ads with keywords: booked meetings, sales automation'\n- 'Scrape TikTok Ad Library forever for: AI tools, chatbots, automation'"

    # Display settings
    source_name = "TikTok Ad Library" if source == "library" else "TikTok Creative Center"
    console.print(f"[cyan]TikTok Ads Scraper - {len(keywords)} keywords ({source_name})[/cyan]")
    console.print(f"[dim]Keywords: {', '.join(keywords[:5])}{'...' if len(keywords) > 5 else ''}[/dim]")

    mode_desc = {
        'forever': 'Forever mode (runs until stopped)',
        'target': f'Target mode (collecting {target_count} ads)',
        'single_pass': 'Single pass (one cycle through keywords)'
    }.get(mode, 'Single pass')
    console.print(f"[yellow]{mode_desc}[/yellow]")

    if per_keyword:
        console.print(f"[dim]Max {per_keyword} ads per keyword[/dim]")
    if target_count:
        console.print(f"[dim]Target: {target_count} total ads[/dim]")

    prompt_lower = prompt.lower()
    should_resume = 'resume' in prompt_lower

    mcp_client = brain.mcp if hasattr(brain, 'mcp') else None

    if mcp_client is None:
        return "Error: No MCP client available. Cannot run deep scraper."

    if should_resume:
        state = TikTokScraperState.load()
        if state:
            console.print(f"[green]Resuming session {state.session_id}[/green]")
        else:
            state = None
    else:
        state = None

    logger.info(f"[TIKTOK_SCRAPER] Creating scraper with MCP client: {type(mcp_client)}, mode={mode}, target={target_count}, per_kw={per_keyword}")
    scraper = TikTokAdsDeepScraper(mcp_client=mcp_client, state=state)

    # Set source
    if scraper.state:
        scraper.state.source = source

    def on_keyword_complete(keyword, ads, state):
        total = state.total_ads_found

        if target_count:
            pct = min(100, int(total / target_count * 100))
            progress_bar = "#" * (pct // 5) + "-" * (20 - pct // 5)
            console.print(f"[bold green]LEAD #{total}[/bold green] [cyan]|{progress_bar}| {pct}%[/cyan] ({total}/{target_count})")
        else:
            console.print(f"[bold green]LEAD #{total}[/bold green] [dim]'{keyword}' +{len(ads)} new[/dim]")

    console.print(f"[yellow]Press Ctrl+C to stop[/yellow]")

    try:
        if mode == 'forever':
            console.print(f"[cyan]Starting forever mode...[/cyan]")
            result = await scraper.run_forever(
                keywords=keywords,
                max_ads_per_keyword=per_keyword or 100,
                on_keyword_complete=on_keyword_complete
            )
        elif mode == 'target':
            console.print(f"[cyan]Starting target mode (goal: {target_count} ads)...[/cyan]")
            result = await scraper.run_until_target(
                keywords=keywords,
                target_count=target_count,
                max_ads_per_keyword=per_keyword or 100,
                on_keyword_complete=on_keyword_complete
            )
        else:
            console.print(f"[cyan]Starting single pass with {len(keywords)} keywords...[/cyan]")
            result = await scraper.run_single_pass(
                keywords=keywords,
                max_ads_per_keyword=per_keyword or 100
            )
        console.print(f"[green]Scraper completed![/green]")
    except Exception as e:
        console.print(f"[red]Scraper failed: {e}[/red]")
        import traceback
        console.print(f"[red]{traceback.format_exc()}[/red]")
        return f"Error running deep scraper: {e}"

    total_ads = result.get('total_ads_found', result.get('total_ads', 0))
    status = result.get('status', 'completed')

    lines = [
        f"## TikTok Ads Deep Scrape Results",
        f"",
        f"**Session ID:** {result['session_id']}",
        f"**Source:** {source_name}",
        f"**Keywords Processed:** {result['keywords_processed']}",
        f"**Total Ads Found:** {total_ads}",
        f"**Unique Ads:** {result['unique_ads']}",
        f"**Results File:** {result['results_file']}",
        f"**Status:** {status}",
    ]

    if result.get('can_resume'):
        lines.append(f"\nTo resume: say 'resume tiktok ads scraping'")

    ads = result.get('ads', [])
    if ads:
        lines.append(f"\n### Sample Ads ({min(3, len(ads))} of {len(ads)}):")
        for ad in ads[:3]:
            advertiser = ad.get('advertiser_name', ad.get('advertiser', ad.get('title', 'Unknown')))
            website = ad.get('website', ad.get('landing_url', 'N/A'))
            lines.append(f"- **{advertiser}** | {website}")

    return '\n'.join(lines)


# CLI interface
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="TikTok Ads Library Deep Scraper")
    parser.add_argument("keywords", nargs="?", help="Keywords (comma-separated) or file path")
    parser.add_argument("--deep", action="store_true", help="Single deep pass through keywords")
    parser.add_argument("--forever", action="store_true", help="Run forever, cycling through keywords")
    parser.add_argument("--resume", action="store_true", help="Resume last session")
    parser.add_argument("--max-per-keyword", type=int, default=100, help="Max ads per keyword")
    parser.add_argument("--source", choices=["library", "creative_center"], default="library",
                       help="TikTok ads source (library or creative_center)")

    args = parser.parse_args()

    async def main():
        keywords = []
        state = None

        if args.resume:
            state = TikTokScraperState.load()
            if state:
                print(f"Resuming session {state.session_id}")
                keywords = state.keywords
            else:
                print("No session to resume")
                return
        elif args.keywords:
            if Path(args.keywords).exists():
                with open(args.keywords) as f:
                    keywords = [line.strip() for line in f if line.strip()]
            else:
                keywords = [k.strip() for k in args.keywords.split(',') if k.strip()]

        if not keywords and not state:
            print("Please provide keywords or use --resume")
            return

        scraper = TikTokAdsDeepScraper(state=state)
        if scraper.state:
            scraper.state.source = args.source

        def on_complete(keyword, ads, state):
            print(f"[{state.current_keyword_idx}/{len(state.keywords)}] "
                  f"'{keyword}': {len(ads)} ads (total: {state.total_ads_found})")

        if args.forever:
            result = await scraper.run_forever(
                keywords=keywords,
                max_ads_per_keyword=args.max_per_keyword,
                on_keyword_complete=on_complete
            )
        else:
            result = await scraper.run_single_pass(
                keywords=keywords,
                max_ads_per_keyword=args.max_per_keyword
            )

        print(f"\n=== Results ===")
        print(f"Session ID: {result['session_id']}")
        print(f"Total ads: {result.get('total_ads_found', result.get('total_ads', 0))}")
        print(f"Unique ads: {result['unique_ads']}")
        print(f"Results file: {result['results_file']}")

    asyncio.run(main())
