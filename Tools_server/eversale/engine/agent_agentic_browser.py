#!/usr/bin/env python3
"""
Eversale Agentic Browser v2 - Playwright MCP-style approach.

Fast, deterministic workflows for known sites.
Element refs for precise actions.
Kimi K2 for complex analysis when needed.
"""

import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus


def _get_package_version() -> str:
    """Read version from package.json."""
    try:
        # CLI root is 2 levels up from engine/agent/
        cli_root = Path(__file__).parent.parent.parent
        package_json_path = cli_root / "package.json"
        if package_json_path.exists():
            with open(package_json_path, 'r') as f:
                package_data = json.load(f)
                return package_data.get('version', '0.0.0')
    except Exception:
        pass
    return '0.0.0'


VERSION = _get_package_version()

# Try to import Kimi client for smart analysis
try:
    from .kimi_k2_client import KimiK2Client
    KIMI_AVAILABLE = True
except ImportError:
    KIMI_AVAILABLE = False

# Try to import RedditHandler for API-based extraction (faster than browser)
try:
    from .reddit_handler import RedditHandler, find_icp_profile_urls
    REDDIT_HANDLER_AVAILABLE = True
except ImportError:
    try:
        # Fallback for different import paths
        from reddit_handler import RedditHandler, find_icp_profile_urls
        REDDIT_HANDLER_AVAILABLE = True
    except ImportError:
        REDDIT_HANDLER_AVAILABLE = False

# Try to import DeepSearchEngine for Google fallback
try:
    from .deep_search_engine import DeepSearchEngine
    DEEP_SEARCH_AVAILABLE = True
except ImportError:
    DEEP_SEARCH_AVAILABLE = False

# Try to import AGI reasoning for automatic smart execution
try:
    from .agi_reasoning import (
        AGIReasoning, get_agi_reasoning, ProactiveGuard,
        reason_before_action, verify_action_success, get_smart_correction
    )
    AGI_REASONING_AVAILABLE = True
except ImportError:
    AGI_REASONING_AVAILABLE = False
    get_agi_reasoning = None

# Try to import AGI Core (full cognitive architecture)
try:
    from .agi_core import (
        CognitiveEngine, get_cognitive_engine, think_before_act,
        get_historical_success_rate, WorkingMemory, EpisodicMemory
    )
    AGI_CORE_AVAILABLE = True
except ImportError:
    AGI_CORE_AVAILABLE = False
    get_cognitive_engine = None

# Subreddit targeting for common ICPs
ICP_SUBREDDITS = {
    # B2B / Agency keywords
    "lead generation": ["Entrepreneur", "startups", "smallbusiness", "marketing", "sales", "agency"],
    "agency": ["Entrepreneur", "marketing", "digitalmarketing", "SEO", "PPC", "agency"],
    "marketing": ["marketing", "digitalmarketing", "socialmedia", "content_marketing", "growthHacking"],
    "sales": ["sales", "B2B_Sales", "salesforce", "Entrepreneur", "startups"],
    "saas": ["SaaS", "startups", "Entrepreneur", "indiehackers", "microsaas"],
    "startup": ["startups", "Entrepreneur", "smallbusiness", "indiehackers", "venturecapital"],
    "entrepreneur": ["Entrepreneur", "startups", "smallbusiness", "sweatystartup", "EntrepreneurRideAlong"],
    "ecommerce": ["ecommerce", "shopify", "dropshipping", "FulfillmentByAmazon", "AmazonSeller"],
    "real estate": ["realestate", "RealEstateInvesting", "CommercialRealEstate", "realtors", "RealEstateTechnology"],
    "finance": ["FinancialCareers", "CFP", "personalfinance", "investing", "fintech"],
    "consulting": ["consulting", "BusinessConsulting", "Entrepreneur", "startups", "smallbusiness"],
    # Default fallback
    "default": ["Entrepreneur", "startups", "smallbusiness", "marketing", "sales"]
}

# Session storage
EVERSALE_HOME = Path(os.environ.get("EVERSALE_HOME", Path.home() / ".eversale"))
SESSION_DIR = EVERSALE_HOME / "sessions"
SESSION_DIR.mkdir(parents=True, exist_ok=True)

# Colors for terminal output
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    CYAN = "\033[36m"
    RED = "\033[31m"


def print_step(step: int, action: str, target: str, status: str = "running"):
    """Print action step."""
    icons = {"running": f"{Colors.YELLOW}>{Colors.RESET}",
             "success": f"{Colors.GREEN}+{Colors.RESET}",
             "error": f"{Colors.RED}x{Colors.RESET}"}
    icon = icons.get(status, "-")
    target_short = target[:55] + "..." if len(target) > 55 else target
    print(f"  {icon} [{step}] {Colors.CYAN}{action}{Colors.RESET} {Colors.DIM}{target_short}{Colors.RESET}")


class AgenticBrowser:
    """
    Playwright MCP-style browser automation.

    Hybrid approach:
    - Deterministic workflows for extraction (FAST)
    - Kimi for ICP analysis in parallel (SMART)
    - Best of both worlds
    """

    def __init__(self, headless: bool = True, debug: bool = False, use_kimi: bool = True):
        self.headless = headless
        self.debug = debug
        self.use_kimi = use_kimi and KIMI_AVAILABLE
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.step = 0
        self.results = []
        self.element_refs = {}  # ref_id -> selector mapping
        self.kimi = None

        # Initialize Kimi client if available and enabled
        if self.use_kimi:
            try:
                self.kimi = KimiK2Client()
            except Exception:
                self.kimi = None
                self.use_kimi = False

    async def analyze_icp_fit(self, lead: Dict, icp_description: str) -> Dict:
        """Use Kimi to analyze if a lead matches ICP. Returns lead with score."""
        if not self.kimi:
            # Fallback to keyword-based scoring
            lead['icp_score'] = 70 if lead.get('has_icp_signal') else 30
            return lead

        prompt = f"""Analyze if this person is a good prospect for: {icp_description}

Lead info:
- Username: {lead.get('username', '')}
- Post title: {lead.get('title', '')}
- Content: {lead.get('content', '')}
- Subreddit: {lead.get('subreddit', '')}

Return ONLY a JSON object: {{"score": 0-100, "reason": "one sentence why"}}
Score 80+ = hot lead, 50-79 = warm, <50 = not a fit"""

        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(self.kimi.chat, prompt),
                timeout=5.0  # 5 second timeout per lead
            )
            # Parse JSON from response
            import json
            match = re.search(r'\{[^}]+\}', response)
            if match:
                result = json.loads(match.group())
                lead['icp_score'] = result.get('score', 50)
                lead['icp_reason'] = result.get('reason', '')
        except Exception:
            lead['icp_score'] = 70 if lead.get('has_icp_signal') else 30

        return lead

    async def analyze_leads_parallel(self, leads: List[Dict], icp: str) -> List[Dict]:
        """Analyze multiple leads in parallel with Kimi."""
        if not leads:
            return leads

        # Analyze all leads in parallel (fast!)
        tasks = [self.analyze_icp_fit(lead, icp) for lead in leads]
        analyzed = await asyncio.gather(*tasks)

        # Sort by ICP score
        analyzed.sort(key=lambda x: x.get('icp_score', 0), reverse=True)
        return analyzed

    # =========================================================================
    # SETUP
    # =========================================================================

    async def setup(self):
        """Initialize browser."""
        from playwright.async_api import async_playwright

        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=['--disable-blink-features=AutomationControlled']
        )

        # Load session
        session_file = SESSION_DIR / "default.json"
        storage = str(session_file) if session_file.exists() else None

        self.context = await self.browser.new_context(
            storage_state=storage,
            viewport={'width': 1280, 'height': 800},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )

        await self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        self.page = await self.context.new_page()

    async def close(self):
        """Save session and cleanup."""
        try:
            await self.context.storage_state(path=str(SESSION_DIR / "default.json"))
        except:
            pass
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    # =========================================================================
    # BROWSER ACTIONS - Playwright MCP style with refs
    # =========================================================================

    async def navigate(self, url: str) -> Dict:
        """Navigate to URL."""
        if not url.startswith('http'):
            url = 'https://' + url
        await self.page.goto(url, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(1.5)
        return {"action": "navigate", "url": url}

    async def click_ref(self, ref: str) -> Dict:
        """Click element by ref (like Playwright MCP)."""
        if ref in self.element_refs:
            selector = self.element_refs[ref]
            try:
                await self.page.click(selector, timeout=5000)
                await asyncio.sleep(0.5)
                return {"action": "click", "ref": ref, "status": "ok"}
            except Exception as e:
                return {"action": "click", "ref": ref, "error": str(e)}
        return {"action": "click", "ref": ref, "error": "ref not found"}

    async def click_text(self, text: str) -> Dict:
        """Click element by text content."""
        try:
            # Try exact text first
            await self.page.get_by_text(text, exact=True).first.click(timeout=3000)
            return {"action": "click", "text": text, "status": "ok"}
        except:
            pass
        try:
            # Try partial text
            await self.page.get_by_text(text, exact=False).first.click(timeout=3000)
            return {"action": "click", "text": text, "status": "ok"}
        except:
            pass
        try:
            # Try button role
            await self.page.get_by_role("button", name=text).first.click(timeout=3000)
            return {"action": "click", "text": text, "method": "button"}
        except:
            pass
        try:
            # Try link role
            await self.page.get_by_role("link", name=text).first.click(timeout=3000)
            return {"action": "click", "text": text, "method": "link"}
        except Exception as e:
            return {"action": "click", "text": text, "error": str(e)}

    async def type_ref(self, ref: str, text: str) -> Dict:
        """Type into element by ref."""
        if ref in self.element_refs:
            selector = self.element_refs[ref]
            try:
                el = self.page.locator(selector).first
                await el.clear()
                await el.type(text)
                return {"action": "type", "ref": ref, "text": text}
            except Exception as e:
                return {"action": "type", "ref": ref, "error": str(e)}
        return {"action": "type", "ref": ref, "error": "ref not found"}

    async def type_placeholder(self, placeholder: str, text: str) -> Dict:
        """Type into input by placeholder."""
        try:
            el = self.page.get_by_placeholder(placeholder, exact=False).first
            await el.clear()
            await el.type(text)
            return {"action": "type", "placeholder": placeholder, "text": text}
        except Exception as e:
            return {"action": "type", "placeholder": placeholder, "error": str(e)}

    async def type_role(self, role: str, text: str) -> Dict:
        """Type into element by role (searchbox, textbox, etc)."""
        try:
            el = self.page.get_by_role(role).first
            await el.clear()
            await el.type(text)
            return {"action": "type", "role": role, "text": text}
        except Exception as e:
            return {"action": "type", "role": role, "error": str(e)}

    async def press_key(self, key: str) -> Dict:
        """Press keyboard key."""
        await self.page.keyboard.press(key)
        return {"action": "press", "key": key}

    async def scroll(self, direction: str = "down", amount: int = 500) -> Dict:
        """Scroll page."""
        if direction == "down":
            await self.page.evaluate(f"window.scrollBy(0, {amount})")
        elif direction == "up":
            await self.page.evaluate(f"window.scrollBy(0, -{amount})")
        return {"action": "scroll", "direction": direction}

    async def wait(self, seconds: float = 1) -> Dict:
        """Wait for specified time."""
        await asyncio.sleep(seconds)
        return {"action": "wait", "seconds": seconds}

    async def select_option(self, selector: str, value: str) -> Dict:
        """Select dropdown option."""
        try:
            await self.page.select_option(selector, value)
            return {"action": "select", "value": value}
        except Exception as e:
            return {"action": "select", "error": str(e)}

    # =========================================================================
    # SNAPSHOT - Get page state with element refs (like Playwright MCP)
    # =========================================================================

    async def get_snapshot(self) -> str:
        """
        Get page snapshot with element refs.
        Returns text representation like Playwright MCP's browser_snapshot.
        """
        self.element_refs = {}

        title = await self.page.title()
        url = self.page.url

        # Extract elements with refs
        elements = await self.page.evaluate("""() => {
            const results = [];
            let refId = 1;

            // Buttons
            document.querySelectorAll('button, [role="button"], input[type="submit"]').forEach(el => {
                const text = (el.innerText || el.value || el.getAttribute('aria-label') || '').trim();
                if (text && text.length < 100) {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        results.push({
                            ref: 'b' + refId++,
                            type: 'button',
                            text: text.substring(0, 50),
                            selector: el.id ? '#' + el.id : null
                        });
                    }
                }
            });

            // Links
            document.querySelectorAll('a[href]').forEach(el => {
                const text = (el.innerText || '').trim();
                if (text && text.length > 1 && text.length < 100) {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        results.push({
                            ref: 'a' + refId++,
                            type: 'link',
                            text: text.substring(0, 50),
                            href: el.href
                        });
                    }
                }
            });

            // Inputs
            document.querySelectorAll('input:not([type="hidden"]), textarea').forEach(el => {
                const rect = el.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) {
                    results.push({
                        ref: 'i' + refId++,
                        type: 'input',
                        placeholder: el.placeholder || el.name || el.type || 'text',
                        value: (el.value || '').substring(0, 30)
                    });
                }
            });

            // Dropdowns
            document.querySelectorAll('select, [role="combobox"], [role="listbox"]').forEach(el => {
                const rect = el.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) {
                    results.push({
                        ref: 'd' + refId++,
                        type: 'dropdown',
                        label: el.getAttribute('aria-label') || el.name || 'select'
                    });
                }
            });

            return results.slice(0, 40);
        }""")

        # Build ref map and text output
        lines = [f"Page: {title}", f"URL: {url}", "", "Elements:"]

        for el in elements:
            ref = el['ref']
            if el['type'] == 'button':
                lines.append(f"  [{ref}] button \"{el['text']}\"")
            elif el['type'] == 'link':
                lines.append(f"  [{ref}] link \"{el['text']}\"")
            elif el['type'] == 'input':
                val = f" = \"{el['value']}\"" if el.get('value') else ""
                lines.append(f"  [{ref}] input ({el['placeholder']}){val}")
            elif el['type'] == 'dropdown':
                lines.append(f"  [{ref}] dropdown ({el['label']})")

        return "\n".join(lines)

    # =========================================================================
    # SITE WORKFLOWS - Deterministic steps for known sites (FAST)
    # =========================================================================

    async def workflow_fb_ads(self, query: str) -> Dict:
        """
        FB Ads Library workflow - deterministic, no LLM needed.
        Returns advertiser URL.
        """
        self.step = 0

        # Step 1: Navigate directly with search query in URL (faster)
        self.step += 1
        print_step(self.step, "navigate", f"FB Ads Library: {query}", "running")
        search_url = f"https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=US&q={quote_plus(query)}&media_type=all"
        await self.navigate(search_url)
        print_step(self.step, "navigate", f"FB Ads Library: {query}", "success")

        # Step 2: Wait for results to load
        self.step += 1
        print_step(self.step, "wait", "results loading", "running")
        await asyncio.sleep(4)  # Give FB time to load ads
        print_step(self.step, "wait", "results loading", "success")

        # Step 3: Close any dialogs/panels that might be open
        self.step += 1
        print_step(self.step, "press", "Escape (close dialogs)", "running")
        await self.press_key("Escape")
        await asyncio.sleep(0.5)
        print_step(self.step, "press", "Escape (close dialogs)", "success")

        # Step 4: Scroll to load more results
        self.step += 1
        print_step(self.step, "scroll", "down to load ads", "running")
        await self.scroll("down", 600)
        await asyncio.sleep(2)
        print_step(self.step, "scroll", "down to load ads", "success")

        # Step 5: Extract first advertiser
        self.step += 1
        print_step(self.step, "extract", "advertiser URL", "running")

        advertiser = await self.page.evaluate("""() => {
            // Helper: find ad card container by going up the DOM
            function findAdCard(element) {
                let current = element;
                let depth = 0;
                while (current && depth < 30) {
                    // FB ad cards typically have specific aria labels or data attributes
                    if (current.getAttribute && current.getAttribute('aria-labelledby')) return current;
                    // Also check for common FB card patterns - look for containers with multiple links
                    const links = current.querySelectorAll ? current.querySelectorAll('a') : [];
                    const hasMultipleLinks = links.length >= 3;
                    const hasFbPageLink = Array.from(links).some(l => l.href && l.href.match(/facebook\\.com\\/\\d{8,}/));
                    if (hasMultipleLinks && hasFbPageLink && current.offsetHeight > 200) return current;
                    current = current.parentElement;
                    depth++;
                }
                return null;
            }

            // Helper: extract advertiser name from ad card
            function getAdvertiserName(card) {
                if (!card) return 'Unknown';

                // Method 1: Link to FB page with text (most reliable)
                const fbLinks = card.querySelectorAll('a[href*="facebook.com/"]');
                for (const link of fbLinks) {
                    const match = link.href.match(/facebook\\.com\\/(\\d{8,})/);
                    if (match) {
                        const text = link.innerText?.trim();
                        if (text && text.length > 2 && text.length < 80 && !text.includes('See all')) {
                            return text;
                        }
                    }
                }

                // Method 2: Profile image alt text
                const imgs = card.querySelectorAll('img[alt]');
                for (const img of imgs) {
                    const alt = img.alt?.trim();
                    if (alt && alt.length > 2 && alt.length < 80 &&
                        !alt.includes('profile') && !alt.includes('Photo')) {
                        return alt;
                    }
                }

                // Method 3: First strong/bold text (often the page name)
                const strong = card.querySelector('strong, [style*="font-weight: bold"], [style*="font-weight:bold"]');
                if (strong && strong.innerText?.trim().length > 2) {
                    return strong.innerText.trim().substring(0, 60);
                }

                return 'Unknown';
            }

            // Priority: Find ads with EXTERNAL URLs (landing pages) - these have contact forms/emails
            // Look for l.facebook.com redirect links which contain the actual destination URL
            // Store all found landing URLs - we'll pick the best one
            const foundLandingUrls = [];

            const redirectLinks = document.querySelectorAll('a[href*="l.facebook.com/l.php"]');
            for (const link of redirectLinks) {
                const href = link.href;
                // Extract the actual URL from the redirect
                const urlMatch = href.match(/[?&]u=([^&]+)/);
                if (urlMatch) {
                    let targetUrl = decodeURIComponent(urlMatch[1]);
                    // Skip social media URLs - we want actual landing pages
                    if (targetUrl.match(/facebook\.com|instagram\.com|fb\.com|ig\.me|fb\.me|messenger\.com/i)) continue;

                    // Find the ad card and extract advertiser name
                    const adCard = findAdCard(link);
                    const name = getAdvertiserName(adCard);

                    // Extract clean domain for display
                    let domain = '';
                    try {
                        domain = new URL(targetUrl).hostname.replace('www.', '');
                    } catch(e) {}

                    foundLandingUrls.push({
                        name: name,
                        url: targetUrl,
                        domain: domain,
                        type: 'landing_page'
                    });
                }
            }

            // Return the first valid landing URL found
            if (foundLandingUrls.length > 0) {
                return foundLandingUrls[0];
            }

            // Fallback: Look for advertiser FB page links if no external URL found
            const allLinks = document.querySelectorAll('a[href*="facebook.com/"]');
            for (const link of allLinks) {
                const href = link.href;
                // Match facebook.com/{numeric_page_id}/ pattern
                const match = href.match(/facebook\\.com\\/(\\d{10,})\\/?$/);
                if (match) {
                    const text = link.innerText?.trim() || '';
                    if (text && text.length > 3 && text.length < 100 &&
                        !text.includes('Sponsored') && !text.includes('See all')) {
                        return {
                            name: text,
                            url: 'https://www.facebook.com/' + match[1],
                            type: 'fb_page'
                        };
                    }
                }
            }

            // Last resort: any FB page link with name
            for (const link of allLinks) {
                const href = link.href;
                const match = href.match(/facebook\\.com\\/(\\d{8,})/);
                if (match) {
                    if (href.includes('/ads/library/?') || href.includes('/help')) continue;
                    const text = link.innerText?.trim() || '';
                    if (text && text.length > 3 && text.length < 100) {
                        return {
                            name: text,
                            url: 'https://www.facebook.com/' + match[1],
                            type: 'fb_page'
                        };
                    }
                    const img = link.querySelector('img');
                    if (img && img.alt && img.alt.length > 3) {
                        return {
                            name: img.alt,
                            url: 'https://www.facebook.com/' + match[1],
                            type: 'fb_page'
                        };
                    }
                }
            }

            return null;
        }""")

        if advertiser:
            url_type = advertiser.get('type', 'unknown')
            domain = advertiser.get('domain', '')
            display = f"{advertiser['name']}"
            if domain:
                display += f" ({domain})"
            print_step(self.step, "extract", display[:45], "success")
            self.results.append(advertiser)

            # Format result based on type
            if url_type == 'landing_page':
                result_msg = f"Advertiser: {advertiser['name']} | Landing Page: {advertiser['url']}"
            else:
                result_msg = f"Advertiser: {advertiser['name']} | FB Page: {advertiser['url']}"

            return {
                "status": "complete",
                "result": result_msg,
                "steps": self.step,
                "url": advertiser['url'],
                "data": advertiser
            }

        # If no specific advertiser found, get current URL
        current_url = self.page.url
        print_step(self.step, "extract", "search results page", "success")
        return {
            "status": "complete",
            "result": f"Search results for '{query}' | URL: {current_url}",
            "steps": self.step,
            "url": current_url
        }

    def _get_target_subreddits(self, topic: str) -> List[str]:
        """Get relevant subreddits for the topic."""
        topic_lower = topic.lower()
        for keyword, subs in ICP_SUBREDDITS.items():
            if keyword in topic_lower:
                return subs
        return ICP_SUBREDDITS["default"]

    async def workflow_reddit_icp(self, icp_description: str, max_leads: int = 20) -> Dict:
        """
        ICP-focused Reddit extraction (SMARTEST).
        Uses find_icp_profile_urls for ICP-scored leads with profile URLs.

        Best for: "find agency owners", "find SaaS founders", etc.
        Returns pre-scored leads based on ICP match signals.
        """
        if not REDDIT_HANDLER_AVAILABLE:
            return None

        self.step = 0

        try:
            self.step += 1
            print_step(self.step, "icp", f"ICP search: {icp_description[:40]}", "running")

            # Use the ICP profile URL extraction
            result = await find_icp_profile_urls(
                icp_description=icp_description,
                target_count=max_leads,
                deep_scan=False,  # Fast mode
                min_score=20
            )

            if result.get("success") and result.get("matches"):
                matches = result["matches"]
                print_step(self.step, "icp", f"{len(matches)} ICP matches found", "success")

                # Format leads from matches
                leads = []
                for match in matches:
                    leads.append({
                        "username": match["username"],
                        "url": match["profile_url"],
                        "subreddit": match.get("source", "").replace("r/", ""),
                        "icp_score": match.get("score", 0),
                        "total_score": match.get("score", 0),
                        "comment_count": 1,
                        "has_icp_signal": match.get("score", 0) >= 50,
                        "warm_signal": ", ".join(match.get("signals", [])[:2]),
                        "source": "icp_extraction"
                    })

                icp_count = sum(1 for l in leads if l.get("has_icp_signal"))

                self.step += 1
                print_step(self.step, "complete", f"{len(leads)} leads ({icp_count} high ICP)", "success")

                return {
                    "status": "complete",
                    "result": f"Found {len(leads)} ICP-matched users ({icp_count} high score)",
                    "steps": self.step,
                    "url": leads[0]["url"] if leads else "",
                    "data": leads,
                    "leads": leads,
                    "icp_count": icp_count,
                    "metadata": result.get("metadata", {}),
                    "source": "icp_extraction"
                }

        except Exception as e:
            print_step(self.step, "icp", f"ICP search failed: {str(e)[:30]}", "error")

        return None

    async def workflow_reddit_api(self, topic: str, max_leads: int = 10) -> Dict:
        """
        Reddit extraction via JSON API (FASTEST) with PARALLEL processing.

        Uses all available tricks:
        1. JSON API - Primary, fastest
        2. find_commenters - Gets engaged users from comments
        3. find_users_by_interest - Cross-subreddit aggregation
        4. PullPush - Historical data fallback
        5. find_icp_profile_urls - ICP-based extraction

        All subreddits searched IN PARALLEL for maximum speed.
        """
        if not REDDIT_HANDLER_AVAILABLE:
            return None

        self.step = 0
        target_subs = self._get_target_subreddits(topic)

        # ICP keywords for filtering warm leads
        ICP_SIGNALS = [
            'looking for', 'need help', 'anyone know', 'recommend', 'suggestions',
            'struggling with', 'how do i', 'how to', 'best way', 'advice',
            'my business', 'my company', 'our team', 'we need', 'i need',
            'agency', 'startup', 'founder', 'ceo', 'owner', 'entrepreneur',
            'client', 'customer', 'leads', 'sales', 'marketing', 'growth',
            'revenue', 'mrr', 'arr', 'churn', 'conversion', 'roi'
        ]

        try:
            handler = RedditHandler()

            # =====================================================================
            # STRATEGY 1: Parallel subreddit search (FAST)
            # =====================================================================
            self.step += 1
            print_step(self.step, "parallel", f"searching {len(target_subs[:4])} subreddits", "running")

            async def search_subreddit(sub: str) -> List[Dict]:
                """Search single subreddit - runs in parallel."""
                leads = []
                try:
                    result = await handler.find_commenters(
                        subreddit=sub,
                        query=topic,
                        max_posts=5,
                        max_comments_per_post=30,
                        min_score=1
                    )

                    if result.get("success") and result.get("commenters"):
                        for commenter in result["commenters"][:max_leads]:
                            has_icp = False
                            warm_text = ""
                            if commenter.get("sample_comments"):
                                sample_text = " ".join(c.get("body", "") for c in commenter["sample_comments"])
                                has_icp = any(s in sample_text.lower() for s in ICP_SIGNALS)
                                warm_text = commenter["sample_comments"][0].get("body", "")[:80]

                            leads.append({
                                "username": commenter["username"],
                                "url": commenter["profile_url"],
                                "subreddit": sub,
                                "total_score": commenter.get("total_score", 0),
                                "comment_count": commenter.get("comment_count", 0),
                                "has_icp_signal": has_icp,
                                "warm_signal": warm_text,
                                "source": "json_api"
                            })
                except Exception:
                    pass
                return leads

            # Run all subreddit searches IN PARALLEL
            tasks = [search_subreddit(sub) for sub in target_subs[:4]]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            all_leads = []
            for result in results:
                if isinstance(result, list):
                    all_leads.extend(result)

            subs_with_results = sum(1 for r in results if isinstance(r, list) and len(r) > 0)
            print_step(self.step, "parallel", f"{subs_with_results} subs, {len(all_leads)} users", "success")

            # =====================================================================
            # STRATEGY 2: find_users_by_interest for cross-subreddit aggregation
            # =====================================================================
            if len(all_leads) < max_leads:
                self.step += 1
                print_step(self.step, "aggregate", "cross-subreddit search", "running")
                try:
                    # Extract keywords from topic
                    keywords = [w for w in topic.lower().split() if len(w) > 3][:3]
                    if not keywords:
                        keywords = [topic]

                    interested = await handler.find_users_by_interest(
                        topic_keywords=keywords,
                        subreddits=target_subs[:3],
                        min_engagement=3,
                        max_posts_per_search=3
                    )

                    for user in interested[:max_leads]:
                        if not any(l["username"] == user["username"] for l in all_leads):
                            has_icp = any(s in str(user.get("sample_comments", [])).lower() for s in ICP_SIGNALS)
                            all_leads.append({
                                "username": user["username"],
                                "url": user["profile_url"],
                                "subreddit": ", ".join(user.get("subreddits", [])[:2]),
                                "total_score": user.get("total_score", 0),
                                "comment_count": user.get("comment_count", 0),
                                "has_icp_signal": has_icp,
                                "warm_signal": user.get("sample_comments", [{}])[0].get("body", "")[:80] if user.get("sample_comments") else "",
                                "source": "cross_subreddit"
                            })

                    print_step(self.step, "aggregate", f"+{len(interested)} users", "success")
                except Exception as e:
                    print_step(self.step, "aggregate", str(e)[:30], "error")

            # =====================================================================
            # STRATEGY 3: PullPush for historical data (if still need more)
            # =====================================================================
            if len(all_leads) < max_leads // 2:
                self.step += 1
                print_step(self.step, "pullpush", "historical archive", "running")
                try:
                    import time
                    # Search last 14 days
                    after_ts = int(time.time()) - (14 * 24 * 60 * 60)

                    for sub in target_subs[:2]:
                        pp_result = await handler.search_pullpush(
                            query=topic,
                            subreddit=sub,
                            after=after_ts,
                            limit=30,
                            content_type="submission"
                        )

                        if pp_result.get("success"):
                            for item in pp_result.get("items", []):
                                author = item.author if hasattr(item, 'author') else item.get('author', '')
                                if not author or author in ['[deleted]', 'AutoModerator']:
                                    continue
                                if any(l["username"] == author for l in all_leads):
                                    continue

                                title = item.title if hasattr(item, 'title') else item.get('title', '')
                                has_icp = any(s in title.lower() for s in ICP_SIGNALS)

                                all_leads.append({
                                    "username": author,
                                    "url": f"https://www.reddit.com/user/{author}",
                                    "subreddit": sub,
                                    "total_score": item.score if hasattr(item, 'score') else item.get('score', 0),
                                    "comment_count": 0,
                                    "has_icp_signal": has_icp,
                                    "warm_signal": title[:80],
                                    "source": "pullpush"
                                })

                    print_step(self.step, "pullpush", f"total {len(all_leads)} users", "success")
                except Exception as e:
                    print_step(self.step, "pullpush", str(e)[:30], "error")

            # =====================================================================
            # Final processing: sort, dedupe, return
            # =====================================================================
            if all_leads:
                # Sort by ICP signal first, then by engagement score
                all_leads.sort(key=lambda x: (
                    x.get("has_icp_signal", False),
                    x.get("total_score", 0) * max(x.get("comment_count", 1), 1)
                ), reverse=True)

                # Dedupe by username
                seen = set()
                unique_leads = []
                for lead in all_leads:
                    if lead["username"] not in seen:
                        seen.add(lead["username"])
                        unique_leads.append(lead)

                icp_count = sum(1 for l in unique_leads if l.get("has_icp_signal"))

                # Collect sources used
                sources = list(set(l.get("source", "unknown") for l in unique_leads))

                self.step += 1
                print_step(self.step, "complete", f"{len(unique_leads)} leads ({icp_count} ICP)", "success")

                return {
                    "status": "complete",
                    "result": f"Found {len(unique_leads)} engaged users ({icp_count} with ICP signals)",
                    "steps": self.step,
                    "url": unique_leads[0]["url"] if unique_leads else "",
                    "data": unique_leads[:max_leads],
                    "leads": unique_leads[:max_leads],
                    "icp_count": icp_count,
                    "sources": sources,
                    "source": "multi_strategy"
                }

            await handler.close()

        except Exception as e:
            print_step(self.step, "api", f"API failed: {str(e)[:30]}", "error")

        return None  # Signal to use browser fallback

    async def workflow_reddit(self, topic: str, max_leads: int = 5) -> Dict:
        """
        Reddit workflow - find WARM leads who posted/commented about topic in last 7-14 days.

        Strategy (tries in order, uses first that works):
        1. ICP extraction for ICP-focused queries (smartest)
        2. Multi-strategy API with parallel processing (fastest)
        3. Browser fallback (most reliable)

        Returns users who are actually engaged (not just random usernames):
        - Posted about the topic recently
        - Shows ICP signals (asking questions, sharing problems, looking for solutions)
        - Includes what they said as warm signal
        """
        if not REDDIT_HANDLER_AVAILABLE:
            # Skip to browser fallback if no handler available
            pass
        else:
            # Check if this is an ICP-focused query (looking for specific persona)
            icp_keywords = ['agency', 'founder', 'owner', 'ceo', 'startup', 'saas',
                           'consultant', 'entrepreneur', 'business owner', 'coach']
            topic_lower = topic.lower()
            is_icp_query = any(kw in topic_lower for kw in icp_keywords)

            # SMART PATH: Try ICP extraction for persona-focused queries
            if is_icp_query:
                icp_result = await self.workflow_reddit_icp(topic, max_leads * 2)
                if icp_result and icp_result.get("leads"):
                    return icp_result

            # FAST PATH: Try multi-strategy API with parallel processing
            api_result = await self.workflow_reddit_api(topic, max_leads)
            if api_result:
                return api_result

        # FALLBACK: Browser-based extraction
        self.step = 0
        all_leads = []

        # Get targeted subreddits for this topic
        target_subs = self._get_target_subreddits(topic)
        subreddit_filter = "+".join(target_subs[:3])  # Use top 3 relevant subreddits

        # Step 1: Navigate to targeted subreddit search
        self.step += 1
        print_step(self.step, "navigate", f"r/{subreddit_filter}: {topic}", "running")
        # Search within targeted subreddits, sorted by new
        search_url = f"https://www.reddit.com/r/{subreddit_filter}/search/?q={quote_plus(topic)}&restrict_sr=1&sort=new&t=month"
        await self.navigate(search_url)
        await asyncio.sleep(3)
        print_step(self.step, "navigate", f"r/{subreddit_filter}: {topic}", "success")

        # Step 2: Scroll to load more posts
        self.step += 1
        print_step(self.step, "scroll", "loading posts", "running")
        for _ in range(3):
            await self.scroll("down", 800)
            await asyncio.sleep(1)
        print_step(self.step, "scroll", "loading posts", "success")

        # Step 3: Extract warm leads with context
        self.step += 1
        print_step(self.step, "extract", "warm leads (7-14 days)", "running")

        leads = await self.page.evaluate("""(maxLeads) => {
            const results = [];
            const now = Date.now();
            const DAY_MS = 24 * 60 * 60 * 1000;
            const MAX_AGE_DAYS = 14;  // Only last 14 days

            // Skip these generic/bot accounts
            const SKIP_USERS = ['AutoModerator', 'reddit', 'deleted', '[deleted]',
                               'RemindMeBot', 'WikiSummarizerBot', 'sneakpeekbot'];

            // ICP signal keywords (shows they might be a prospect)
            const ICP_SIGNALS = [
                'looking for', 'need help', 'anyone know', 'recommend', 'suggestions',
                'struggling with', 'how do i', 'how to', 'best way', 'advice',
                'my business', 'my company', 'our team', 'we need', 'i need',
                'agency', 'startup', 'founder', 'ceo', 'owner', 'entrepreneur',
                'client', 'customer', 'leads', 'sales', 'marketing', 'growth'
            ];

            // Find all posts/cards on the page
            const posts = document.querySelectorAll('[data-testid="post-container"], .thing, article, [class*="Post"]');

            for (const post of posts) {
                if (results.length >= maxLeads) break;

                // Get timestamp
                const timeEl = post.querySelector('time, [datetime], .live-timestamp, [data-testid="post-timestamp"]');
                let postAge = null;
                let timeText = '';

                if (timeEl) {
                    const datetime = timeEl.getAttribute('datetime') || timeEl.getAttribute('title');
                    if (datetime) {
                        const postDate = new Date(datetime);
                        postAge = (now - postDate.getTime()) / DAY_MS;
                        timeText = timeEl.textContent?.trim() || '';
                    } else {
                        // Parse relative time like "2 days ago", "1 week ago"
                        timeText = timeEl.textContent?.trim() || '';
                        const daysMatch = timeText.match(/(\\d+)\\s*d(?:ay)?/i);
                        const hoursMatch = timeText.match(/(\\d+)\\s*h(?:our)?/i);
                        const weeksMatch = timeText.match(/(\\d+)\\s*w(?:eek)?/i);

                        if (hoursMatch) postAge = parseInt(hoursMatch[1]) / 24;
                        else if (daysMatch) postAge = parseInt(daysMatch[1]);
                        else if (weeksMatch) postAge = parseInt(weeksMatch[1]) * 7;
                    }
                }

                // Skip if too old (> 14 days)
                if (postAge !== null && postAge > MAX_AGE_DAYS) continue;

                // Get username
                const userLink = post.querySelector('a[href*="/user/"], a[href*="/u/"]');
                if (!userLink) continue;

                const userMatch = userLink.href.match(/\\/u(?:ser)?\\/([^\\/?]+)/);
                if (!userMatch) continue;

                const username = userMatch[1];
                if (SKIP_USERS.includes(username)) continue;
                if (results.some(r => r.username === username)) continue;  // Dedupe

                // Get post title and content
                const titleEl = post.querySelector('h3, [data-testid="post-title"], .title a');
                const title = titleEl?.textContent?.trim() || '';

                const contentEl = post.querySelector('[data-testid="post-rtjson-content"], .usertext-body, .md');
                const content = contentEl?.textContent?.trim().substring(0, 200) || '';

                const fullText = (title + ' ' + content).toLowerCase();

                // Check for ICP signals
                const hasICPSignal = ICP_SIGNALS.some(signal => fullText.includes(signal));

                // Get subreddit
                const subLink = post.querySelector('a[href*="/r/"]');
                const subMatch = subLink?.href?.match(/\\/r\\/([^\\/?]+)/);
                const subreddit = subMatch ? subMatch[1] : '';

                results.push({
                    username: username,
                    url: 'https://www.reddit.com/user/' + username,
                    title: title.substring(0, 100),
                    content: content.substring(0, 150),
                    subreddit: subreddit,
                    posted_ago: timeText || (postAge ? Math.round(postAge) + ' days ago' : 'recent'),
                    days_ago: postAge ? Math.round(postAge) : null,
                    has_icp_signal: hasICPSignal,
                    warm_signal: hasICPSignal ? 'ICP match - ' + title.substring(0, 50) : title.substring(0, 50)
                });
            }

            // Sort by ICP signal first, then by recency
            results.sort((a, b) => {
                if (a.has_icp_signal && !b.has_icp_signal) return -1;
                if (!a.has_icp_signal && b.has_icp_signal) return 1;
                return (a.days_ago || 999) - (b.days_ago || 999);
            });

            return results;
        }""", max_leads)

        if leads and len(leads) > 0:
            # Count ICP matches
            icp_count = sum(1 for l in leads if l.get('has_icp_signal'))
            print_step(self.step, "extract", f"{len(leads)} warm leads ({icp_count} ICP)", "success")

            # Build summary
            lead_summaries = []
            for lead in leads[:5]:  # Top 5
                signal = "[ICP] " if lead.get('has_icp_signal') else ""
                lead_summaries.append(
                    f"u/{lead['username']} ({lead.get('posted_ago', 'recent')}) - {signal}{lead.get('title', '')[:40]}"
                )

            return {
                "status": "complete",
                "result": f"Found {len(leads)} warm leads ({icp_count} with ICP signals)",
                "steps": self.step,
                "url": leads[0]['url'] if leads else self.page.url,
                "data": leads,
                "leads": leads,
                "summary": "\n".join(lead_summaries)
            }

        # Fallback: try old.reddit.com with targeted subreddits
        self.step += 1
        print_step(self.step, "navigate", "old.reddit.com (fallback)", "running")
        try:
            # Use targeted subreddits in old reddit too
            old_url = f"https://old.reddit.com/r/{subreddit_filter}/search?q={quote_plus(topic)}&restrict_sr=on&sort=new&t=month"
            await self.navigate(old_url)
            await asyncio.sleep(2)
            print_step(self.step, "navigate", "old.reddit.com", "success")

            # Extract from old reddit format with ICP filtering
            leads = await self.page.evaluate("""(maxLeads) => {
                const results = [];
                const posts = document.querySelectorAll('.search-result, .thing, .link');

                // ICP signal keywords
                const ICP_SIGNALS = [
                    'looking for', 'need help', 'anyone know', 'recommend', 'suggestions',
                    'struggling with', 'how do i', 'how to', 'best way', 'advice',
                    'my business', 'my company', 'our team', 'we need', 'i need',
                    'agency', 'startup', 'founder', 'ceo', 'owner', 'entrepreneur',
                    'client', 'customer', 'leads', 'sales', 'marketing', 'growth'
                ];

                for (const post of posts) {
                    if (results.length >= maxLeads) break;

                    const userLink = post.querySelector('a.author, a[href*="/user/"]');
                    if (!userLink) continue;

                    const username = userLink.textContent?.trim() || userLink.href?.match(/\\/user\\/([^\\/?]+)/)?.[1];
                    if (!username || ['AutoModerator', 'deleted', '[deleted]'].includes(username)) continue;
                    if (results.some(r => r.username === username)) continue;

                    const titleEl = post.querySelector('a.title, a.search-title, p.title a');
                    const title = titleEl?.textContent?.trim() || '';

                    // Get subreddit
                    const subLink = post.querySelector('a.subreddit, a[href*="/r/"]');
                    const subMatch = subLink?.href?.match(/\\/r\\/([^\\/?]+)/);
                    const subreddit = subMatch ? subMatch[1] : '';

                    const timeEl = post.querySelector('time, .live-timestamp');
                    const timeText = timeEl?.textContent?.trim() || timeEl?.getAttribute('title') || '';

                    // Check ICP signal
                    const fullText = title.toLowerCase();
                    const hasICPSignal = ICP_SIGNALS.some(s => fullText.includes(s));

                    results.push({
                        username: username,
                        url: 'https://www.reddit.com/user/' + username,
                        title: title.substring(0, 100),
                        subreddit: subreddit,
                        posted_ago: timeText || 'recent',
                        has_icp_signal: hasICPSignal,
                        warm_signal: hasICPSignal ? 'ICP: ' + title.substring(0, 50) : title.substring(0, 50)
                    });
                }

                // Sort by ICP signal first
                results.sort((a, b) => {
                    if (a.has_icp_signal && !b.has_icp_signal) return -1;
                    if (!a.has_icp_signal && b.has_icp_signal) return 1;
                    return 0;
                });

                return results;
            }""", max_leads)

            if leads and len(leads) > 0:
                icp_count = sum(1 for l in leads if l.get('has_icp_signal'))
                print_step(self.step, "extract", f"{len(leads)} leads ({icp_count} ICP)", "success")
                return {
                    "status": "complete",
                    "result": f"Found {len(leads)} warm leads ({icp_count} with ICP signals)",
                    "steps": self.step,
                    "url": leads[0]['url'],
                    "data": leads,
                    "leads": leads,
                    "icp_count": icp_count
                }
        except Exception as e:
            print_step(self.step, "navigate", "old.reddit.com", "error")

        return {
            "status": "partial",
            "result": "Reddit search completed but no leads matched criteria",
            "steps": self.step,
            "url": self.page.url,
            "data": [],
            "leads": []
        }

    async def workflow_google_maps(self, query: str, max_leads: int = 20) -> Dict:
        """
        Google Maps business search workflow.

        Tricks used:
        - Feed panel scrolling for more results
        - aria-label extraction for clean business names
        - Place URL parsing for business details
        """
        self.step = 0

        # Step 1: Navigate
        self.step += 1
        print_step(self.step, "navigate", "Google Maps", "running")
        await self.navigate(f"https://www.google.com/maps/search/{quote_plus(query)}")
        await asyncio.sleep(3)
        print_step(self.step, "navigate", "Google Maps", "success")

        # Step 2: Scroll results panel for more businesses
        self.step += 1
        print_step(self.step, "scroll", "loading businesses", "running")
        for _ in range(3):
            # Scroll the results feed panel
            await self.page.evaluate("""() => {
                const panel = document.querySelector('[role="feed"]');
                if (panel) panel.scrollTop += 800;
            }""")
            await asyncio.sleep(1)
        print_step(self.step, "scroll", "loading businesses", "success")

        # Step 3: Extract businesses
        self.step += 1
        print_step(self.step, "extract", "businesses", "running")

        businesses = await self.page.evaluate("""(maxLeads) => {
            const results = [];
            const seen = new Set();

            document.querySelectorAll('a[href*="/maps/place/"]').forEach(a => {
                if (results.length >= maxLeads) return;

                const name = a.getAttribute('aria-label') || a.innerText?.trim() || '';
                const href = a.href;

                // Skip empty or duplicates
                if (!name || name.length < 2 || seen.has(name)) return;
                seen.add(name);

                // Extract place ID from URL if available
                const placeMatch = href.match(/place\\/([^\\/]+)/);
                const placeId = placeMatch ? placeMatch[1] : '';

                results.push({
                    name: name.substring(0, 100),
                    url: href,
                    place_id: placeId,
                    source: 'google_maps'
                });
            });

            return results;
        }""", max_leads)

        if businesses and len(businesses) > 0:
            print_step(self.step, "extract", f"{len(businesses)} businesses", "success")
            return {
                "status": "complete",
                "result": f"Found {len(businesses)} businesses",
                "steps": self.step,
                "data": businesses,
                "leads": businesses,
                "url": self.page.url
            }

        return {
            "status": "no_results",
            "result": "No businesses found",
            "steps": self.step,
            "url": self.page.url
        }

    async def workflow_linkedin_search(self, query: str) -> Dict:
        """LinkedIn people search workflow."""
        self.step = 0

        # Step 1: Navigate
        self.step += 1
        print_step(self.step, "navigate", "LinkedIn", "running")
        await self.navigate(f"https://www.linkedin.com/search/results/people/?keywords={quote_plus(query)}")
        print_step(self.step, "navigate", "LinkedIn", "success")

        await asyncio.sleep(2)

        # Step 2: Extract profiles
        self.step += 1
        print_step(self.step, "extract", "profiles", "running")

        profiles = await self.page.evaluate("""() => {
            const results = [];
            const cards = document.querySelectorAll('.entity-result__item, .search-result__wrapper');
            cards.forEach(card => {
                const link = card.querySelector('a[href*="/in/"]');
                const name = card.querySelector('.entity-result__title-text, .actor-name');
                if (link && name) {
                    results.push({
                        name: name.innerText?.trim(),
                        url: link.href.split('?')[0]
                    });
                }
            });
            return results.slice(0, 10);
        }""")

        if profiles and len(profiles) > 0:
            print_step(self.step, "extract", f"{len(profiles)} profiles", "success")
            return {
                "status": "complete",
                "result": f"Found {len(profiles)} profiles",
                "steps": self.step,
                "data": profiles,
                "url": self.page.url
            }

        # LinkedIn blocked - fallback to Google search
        if DEEP_SEARCH_AVAILABLE:
            self.step += 1
            print_step(self.step, "fallback", "Google search for LinkedIn profiles", "running")

            try:
                engine = DeepSearchEngine(self)
                google_query = f"site:linkedin.com/in {query}"
                google_search_url = f"https://www.google.com/search?q={quote_plus(google_query)}"

                # Search Google for LinkedIn profiles
                serp_hits = await engine.search_once(google_query, limit=10)

                # Extract LinkedIn profile URLs from Google results
                linkedin_profiles = []
                for hit in serp_hits:
                    url = hit.get("url", "")
                    title = hit.get("title", "")
                    # Only include actual profile URLs (not company pages or other LinkedIn pages)
                    if "linkedin.com/in/" in url:
                        linkedin_profiles.append({
                            "name": title.replace(" - LinkedIn", "").replace(" | LinkedIn", "").strip(),
                            "url": url.split("?")[0],  # Remove query parameters
                            "source": "google"
                        })

                if linkedin_profiles:
                    print_step(self.step, "fallback", f"Found {len(linkedin_profiles)} profiles via Google", "success")
                    return {
                        "status": "complete",
                        "result": f"LinkedIn blocked - found {len(linkedin_profiles)} profiles via Google",
                        "steps": self.step,
                        "data": linkedin_profiles,
                        "google_search_url": google_search_url,
                        "fallback_used": True,
                        "url": self.page.url
                    }
                else:
                    print_step(self.step, "fallback", "No profiles found in Google results", "error")
                    return {
                        "status": "no_results",
                        "result": f"LinkedIn blocked and no profiles found via Google fallback. Try: {google_search_url}",
                        "steps": self.step,
                        "google_search_url": google_search_url,
                        "fallback_used": True,
                        "url": self.page.url
                    }
            except Exception as e:
                print_step(self.step, "fallback", f"Google search failed: {str(e)}", "error")
                return {
                    "status": "error",
                    "result": f"LinkedIn blocked and Google fallback failed: {str(e)}",
                    "steps": self.step,
                    "url": self.page.url
                }
        else:
            # DeepSearchEngine not available - use inline Google fallback
            self.step += 1
            print_step(self.step, "fallback", "Google search for LinkedIn profiles", "running")

            try:
                # Navigate to Google and search for LinkedIn profiles
                google_query = f"site:linkedin.com/in {query}"
                google_search_url = f"https://www.google.com/search?q={quote_plus(google_query)}"
                await self.page.goto(google_search_url, wait_until='domcontentloaded', timeout=15000)
                await asyncio.sleep(2)

                # Extract LinkedIn URLs from Google results
                profiles = await self.page.evaluate("""
                    () => {
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
                                    if (name.length > 2 && name.length < 100 && !name.toLowerCase().includes('cached')) {
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

                        return results.slice(0, 10);
                    }
                """)

                if profiles and len(profiles) > 0:
                    print_step(self.step, "fallback", f"Found {len(profiles)} profiles via Google", "success")
                    return {
                        "status": "complete",
                        "result": f"LinkedIn blocked - found {len(profiles)} profiles via Google",
                        "steps": self.step,
                        "data": profiles,
                        "google_search_url": google_search_url,
                        "fallback_used": True,
                        "url": self.page.url
                    }
                else:
                    print_step(self.step, "fallback", "No profiles found in Google results", "warning")
                    return {
                        "status": "no_results",
                        "result": f"LinkedIn blocked - Google fallback found no profiles. Search URL: {google_search_url}",
                        "steps": self.step,
                        "google_search_url": google_search_url,
                        "fallback_used": True,
                        "url": self.page.url
                    }
            except Exception as e:
                print_step(self.step, "fallback", f"Google fallback failed: {str(e)[:40]}", "error")
                return {
                    "status": "error",
                    "result": f"LinkedIn blocked and Google fallback failed: {str(e)}",
                    "steps": self.step,
                    "url": self.page.url
                }

    # =========================================================================
    # TASK ROUTER - Match task to workflow or use LLM
    # =========================================================================

    def _extract_requested_count(self, prompt: str) -> Optional[int]:
        """
        Extract the exact count requested by user from the prompt.

        Examples:
        - "find 1 reddit user" -> 1
        - "get 5 advertisers" -> 5
        - "find 10 leads" -> 10
        - "find a reddit user" -> 1 (a/an = 1)

        Returns None if no specific count requested (use default).
        """
        prompt_lower = prompt.lower()

        # Pattern: "find/get/search N thing(s)" - explicit number
        count_patterns = [
            r'(?:find|get|search|show|give|extract|scrape)\s+(\d+)\s+',
            r'(\d+)\s+(?:reddit|linkedin|fb|facebook|advertiser|user|lead|profile|person|people)',
            r'(?:top|first|best)\s+(\d+)\s+',
        ]

        for pattern in count_patterns:
            match = re.search(pattern, prompt_lower)
            if match:
                return int(match.group(1))

        # Pattern: "a/an thing" = 1
        if re.search(r'\b(?:a|an|one|1)\s+(?:reddit|linkedin|fb|facebook|advertiser|user|lead|profile)', prompt_lower):
            return 1

        # No specific count found - return None to use default
        return None

    def _parse_task(self, prompt: str) -> Dict:
        """Parse task to determine workflow."""
        prompt_lower = prompt.lower()

        # Extract requested count from prompt
        requested_count = self._extract_requested_count(prompt)

        # =====================================================================
        # NAVIGATION COMMANDS - Check FIRST (highest priority)
        # These are explicit navigation requests that should never be routed
        # to extraction workflows even if prompt contains extraction keywords
        # =====================================================================

        # Zoho Mail - navigate to login (MUST be before Reddit/other checks)
        if 'zoho' in prompt_lower and ('mail' in prompt_lower or 'zoho mail' in prompt_lower):
            return {"workflow": "navigate", "url": "mail.zoho.com"}

        # Gmail - navigate to login
        if 'gmail' in prompt_lower and 'go to' in prompt_lower:
            return {"workflow": "navigate", "url": "mail.google.com"}

        # Outlook/Hotmail - navigate to login
        if ('outlook' in prompt_lower or 'hotmail' in prompt_lower) and 'go to' in prompt_lower:
            return {"workflow": "navigate", "url": "outlook.live.com"}

        # Yahoo Mail - navigate to login
        if 'yahoo' in prompt_lower and 'mail' in prompt_lower and 'go to' in prompt_lower:
            return {"workflow": "navigate", "url": "mail.yahoo.com"}

        # Generic "go to [service]" navigation (explicit URL requests)
        go_to_match = re.search(r'go\s+to\s+(\S+)', prompt_lower)
        if go_to_match:
            target = go_to_match.group(1).strip()
            # If target looks like a URL or service name (contains dot or is known service)
            if '.' in target or target in ['gmail', 'zoho', 'yahoo', 'outlook']:
                return {"workflow": "navigate", "url": target}

        # =====================================================================
        # EXTRACTION WORKFLOWS - Check after navigation commands
        # =====================================================================

        # FB Ads Library / Meta Ads Library
        if 'fb ads' in prompt_lower or 'facebook ads' in prompt_lower or 'meta' in prompt_lower and 'ads' in prompt_lower:
            # Extract search query - look for quoted text or "search for X" / "for X"
            match = re.search(r'["\']([^"\']+)["\']', prompt_lower)
            if match:
                query = match.group(1).strip()
            else:
                # Try "search for X" or "for X"
                match = re.search(r'(?:search\s+)?for\s+([^,;]+?)(?:,|;|open|click|and\s+output|$)', prompt_lower)
                if match:
                    query = match.group(1).strip()
                else:
                    query = "booked meetings"  # Default
            return {"workflow": "fb_ads", "query": query, "count": requested_count}

        # Reddit
        if 'reddit' in prompt_lower:
            # Extract topic - look for "lead-gen", "appointment", etc.
            topic_keywords = ['lead-gen', 'lead gen', 'appointment', 'sales', 'marketing', 'sdr', 'outreach']
            found_topics = [kw for kw in topic_keywords if kw in prompt_lower]
            if found_topics:
                topic = ' '.join(found_topics[:2])  # Use first 2 keywords
            else:
                topic = "lead generation"
            return {"workflow": "reddit", "topic": topic, "count": requested_count}

        # LinkedIn
        if 'linkedin' in prompt_lower:
            # Extract what to find - SDR, sales manager, etc.
            match = re.search(r'find\s+(?:an?\s+)?([^,;]+?)(?:\s+(?:profile|url)|,|;|or|$)', prompt_lower)
            if match:
                query = match.group(1).strip()
            else:
                query = "SDR lead generation"
            return {"workflow": "linkedin", "query": query, "count": requested_count}

        # Google Maps
        if 'google maps' in prompt_lower or 'maps.google' in prompt_lower:
            # Extract query - look for "find X" or "X listing"
            match = re.search(r'find\s+(?:a\s+)?([^,;]+?)(?:\s+listing|\s+url|,|;|$)', prompt_lower)
            if match:
                query = match.group(1).strip()
            else:
                query = "lead generation agency"
            return {"workflow": "google_maps", "query": query, "count": requested_count}

        # Gmail (extraction/non-navigation case - just mentions gmail without "go to")
        if 'gmail' in prompt_lower:
            return {"workflow": "navigate", "url": "mail.google.com"}

        return {"workflow": "llm", "prompt": prompt}

    async def run(self, prompt: str) -> Dict:
        """Run task - routes to workflow or LLM with automatic AGI cognitive architecture."""
        # Print header
        print()
        print(f"{Colors.BOLD}{Colors.GREEN}EVERSALE{Colors.RESET} {Colors.DIM}v{VERSION}{Colors.RESET}")
        print(f"{Colors.DIM}{'='*50}{Colors.RESET}")

        # Initialize AGI Core (full cognitive architecture)
        cognitive = None
        agi = None

        if AGI_CORE_AVAILABLE and get_cognitive_engine:
            try:
                cognitive = get_cognitive_engine()

                # Get historical success rate for this type of task
                success_rate = get_historical_success_rate(prompt)
                if success_rate < 0.5 and success_rate > 0:
                    print(f"{Colors.YELLOW}* Similar tasks succeeded {success_rate:.0%} - will adapt strategy{Colors.RESET}")

                # Pre-cognition: Think about the task before starting
                if self.page:
                    page_state = {"url": self.page.url, "text": ""}
                    try:
                        page_state["text"] = await self.page.content()
                    except:
                        pass
                    reasoning = await think_before_act(prompt, page_state)
                    if reasoning.get("action"):
                        print(f"{Colors.DIM}* Strategy: {reasoning.get('reason', '')[:40]}{Colors.RESET}")
                    if reasoning.get("confidence", 1) < 0.5:
                        print(f"{Colors.YELLOW}* Low confidence - will use fallbacks{Colors.RESET}")

            except Exception as e:
                logger.debug(f"AGI Core init failed: {e}")

        # Fallback to simpler AGI reasoning if core unavailable
        if not cognitive and AGI_REASONING_AVAILABLE and get_agi_reasoning:
            try:
                agi = get_agi_reasoning()
                intent = await agi.understand_intent(prompt, {
                    'url': self.page.url if self.page else '',
                })
                if intent and intent.get('actual_goal'):
                    print(f"{Colors.DIM}* Goal: {intent.get('actual_goal')[:50]}{Colors.RESET}")
            except Exception as e:
                pass

        # Check for multi-task
        tasks = self._split_tasks(prompt)

        if len(tasks) > 1:
            print(f"{Colors.CYAN}Multi-task mode:{Colors.RESET} {len(tasks)} tasks")
            print(f"{Colors.DIM}{'='*50}{Colors.RESET}")

            all_results = []
            for i, task in enumerate(tasks, 1):
                print()
                print(f"{Colors.BOLD}[Task {i}/{len(tasks)}]{Colors.RESET} {task[:60]}...")
                print(f"{Colors.DIM}{'-'*50}{Colors.RESET}")

                result = await self._run_single_with_retry(task, agi, cognitive)
                all_results.append(result)

                print()
                print(f"  {Colors.GREEN}Result:{Colors.RESET} {result.get('result', '')[:60]}")
                if result.get('url'):
                    print(f"  {Colors.GREEN}URL:{Colors.RESET} {result.get('url')}")

            print()
            print(f"{Colors.DIM}{'='*50}{Colors.RESET}")
            print(f"{Colors.GREEN}{Colors.BOLD}+ All tasks complete{Colors.RESET}")
            return {"tasks": all_results, "status": "complete"}

        # Single task
        print(f"{Colors.DIM}Task: {prompt[:60]}...{Colors.RESET}" if len(prompt) > 60 else f"{Colors.DIM}Task: {prompt}{Colors.RESET}")
        print(f"{Colors.DIM}{'='*50}{Colors.RESET}")

        result = await self._run_single_with_retry(prompt, agi, cognitive)

        print()
        print(f"{Colors.GREEN}{Colors.BOLD}+ Complete{Colors.RESET}")
        print(f"{Colors.DIM}{'~'*50}{Colors.RESET}")
        print(f"  {result.get('result', '')}")
        print(f"{Colors.DIM}{'~'*50}{Colors.RESET}")
        print(f"  {Colors.GREEN}{result.get('steps', 0)} steps{Colors.RESET}")

        return result

    async def _run_single_with_retry(self, prompt: str, agi=None, cognitive=None, max_retries: int = 2) -> Dict:
        """
        Run single task with automatic AGI-powered retry on failure.

        Uses full cognitive architecture when available:
        1. Perceive current state
        2. Reason about best approach
        3. Execute with monitoring
        4. Verify outcome
        5. Learn from result

        Falls back to simpler AGI reasoning if cognitive engine unavailable.
        """
        last_error = None
        all_actions = []
        original_prompt = prompt

        # Get cognitive engine if available
        if not cognitive and AGI_CORE_AVAILABLE and get_cognitive_engine:
            try:
                cognitive = get_cognitive_engine()
            except:
                pass

        for attempt in range(max_retries + 1):
            # Cognitive pre-check: detect loops and low-confidence situations
            if cognitive and attempt > 0:
                meta = await cognitive.metacognize()
                if meta.get("in_loop"):
                    print(f"{Colors.YELLOW}* Loop detected - forcing strategy change{Colors.RESET}")
                    # Get completely different approach
                    if self.page:
                        page_state = {"url": self.page.url, "text": ""}
                        try:
                            page_state["text"] = (await self.page.content())[:2000]
                        except:
                            pass
                        reasoning = await think_before_act(original_prompt, page_state)
                        if reasoning.get("strategy"):
                            prompt = f"Using fallback: {reasoning['strategy']}"
                            print(f"{Colors.CYAN}* New strategy: {prompt[:50]}...{Colors.RESET}")

            try:
                result = await self._run_single(prompt)

                # Check if result indicates success
                if result and result.get('status') != 'error':
                    # Record success for learning
                    if agi:
                        agi.record_action(prompt, result.get('result', ''), True)

                    # Cognitive learning: record successful episode
                    if cognitive:
                        all_actions.append({"action": prompt, "success": True})
                        await cognitive.learn(
                            original_prompt,
                            all_actions,
                            result.get('result', 'success'),
                            True
                        )
                        print(f"{Colors.DIM}* Learned: success pattern recorded{Colors.RESET}")

                    return result

                # Task returned but with error status
                last_error = result.get('error', 'Unknown error')
                all_actions.append({"action": prompt, "success": False, "error": last_error})

            except Exception as e:
                last_error = str(e)
                all_actions.append({"action": prompt, "success": False, "error": last_error})

            # If we have AGI and more retries, get smart correction
            if (agi or cognitive) and attempt < max_retries:
                print(f"{Colors.YELLOW}* Analyzing failure (attempt {attempt + 1}/{max_retries + 1})...{Colors.RESET}")

                # Try cognitive reasoning first (has memory of what worked before)
                if cognitive:
                    try:
                        page_state = {"url": self.page.url if self.page else "", "text": ""}
                        perception = await cognitive.perceive(page_state)
                        reasoning = await cognitive.reason(original_prompt, perception)

                        if reasoning.get("action") == "use_fallback":
                            new_approach = reasoning.get("strategy", "")
                            if new_approach:
                                print(f"{Colors.CYAN}* Cognitive fallback: {new_approach[:50]}...{Colors.RESET}")
                                prompt = new_approach
                                await asyncio.sleep(1)
                                continue
                    except Exception as e:
                        logger.debug(f"Cognitive reasoning failed: {e}")

                # Fall back to simpler AGI reasoning
                if agi:
                    try:
                        correction = await agi.get_correction(
                            action=prompt,
                            error=last_error,
                            current_state={'url': self.page.url if self.page else '', 'attempt': attempt + 1}
                        )

                        if correction and correction.get('new_action'):
                            new_approach = correction.get('new_action')
                            print(f"{Colors.CYAN}* Correction: {new_approach[:50]}...{Colors.RESET}")
                            prompt = new_approach
                        elif correction and not correction.get('should_retry', True):
                            break
                    except Exception:
                        pass

                await asyncio.sleep(1)

        # All retries exhausted - record failure for learning
        if agi:
            agi.record_action(prompt, last_error, False)

        if cognitive:
            await cognitive.learn(original_prompt, all_actions, f"Failed: {last_error}", False)
            print(f"{Colors.DIM}* Learned: failure pattern recorded for future avoidance{Colors.RESET}")

        return {"status": "error", "error": last_error, "result": f"Failed after {max_retries + 1} attempts: {last_error}"}

    def _split_tasks(self, prompt: str) -> List[str]:
        """Split multi-task prompt into individual tasks."""
        # Site keywords to identify valid tasks
        site_keywords = ['facebook', 'fb ads', 'meta', 'reddit', 'linkedin', 'google maps', 'gmail', 'zoho', 'twitter', 'youtube']

        def is_valid_task(text: str) -> bool:
            """Check if text looks like a valid task (contains site keyword)."""
            text_lower = text.lower()
            return any(kw in text_lower for kw in site_keywords)

        # Try numbered parentheses format: (1) task; (2) task; (3) task
        numbered_paren = re.split(r'\s*\(\d+\)\s*', prompt)
        numbered_paren = [p.strip().rstrip(';').strip() for p in numbered_paren if p.strip()]
        # Filter to only valid tasks (removes preambles like "Go to public sites only:")
        valid_tasks = [p for p in numbered_paren if is_valid_task(p)]
        if len(valid_tasks) > 1:
            return valid_tasks

        # Try numbered period format: 1. task 2. task 3. task
        numbered_period = re.split(r'\s*\d+\.\s+', prompt)
        numbered_period = [p.strip().rstrip(';').strip() for p in numbered_period if p.strip()]
        valid_tasks = [p for p in numbered_period if is_valid_task(p)]
        if len(valid_tasks) > 1:
            return valid_tasks

        # Try semicolon-separated with site keywords
        if ';' in prompt:
            semi_parts = prompt.split(';')
            valid_parts = [p.strip() for p in semi_parts if p.strip() and is_valid_task(p)]
            if len(valid_parts) > 1:
                return valid_parts

        # Try "Go to" pattern
        go_to_parts = re.split(r'(?=Go to )', prompt, flags=re.IGNORECASE)
        go_to_parts = [p.strip() for p in go_to_parts if p.strip()]
        if len(go_to_parts) > 1:
            return go_to_parts

        # Single task
        return [prompt]

    async def _run_single(self, prompt: str) -> Dict:
        """Run single task."""
        task = self._parse_task(prompt)
        workflow = task.get("workflow")
        requested_count = task.get("count")  # User-requested count (None = use default)

        if workflow == "fb_ads":
            result = await self.workflow_fb_ads(task["query"])
            # Limit results to requested count if specified
            if result and requested_count and result.get("data"):
                result["data"] = result["data"][:requested_count]
                result["leads"] = result.get("leads", [])[:requested_count]
                result["result"] = f"Found {len(result['data'])} advertisers"
            return result
        elif workflow == "reddit":
            # Pass count directly to workflow
            max_leads = requested_count if requested_count else 5
            return await self.workflow_reddit(task["topic"], max_leads=max_leads)
        elif workflow == "linkedin":
            result = await self.workflow_linkedin_search(task["query"])
            # Limit results to requested count if specified
            if result and requested_count and result.get("profiles"):
                result["profiles"] = result["profiles"][:requested_count]
                result["result"] = f"Found {len(result['profiles'])} LinkedIn profiles"
            return result
        elif workflow == "google_maps":
            result = await self.workflow_google_maps(task["query"])
            # Limit results to requested count if specified
            if result and requested_count and result.get("data"):
                result["data"] = result["data"][:requested_count]
                result["leads"] = result.get("leads", [])[:requested_count]
                result["result"] = f"Found {len(result['data'])} businesses"
            return result
        elif workflow == "navigate":
            url = task["url"]
            if not url.startswith("http"):
                url = "https://" + url
            if "." not in url:
                url = url + ".com"
            self.step = 1
            print_step(1, "navigate", url, "running")
            await self.navigate(url)
            print_step(1, "navigate", url, "success")
            return {"status": "complete", "result": f"Navigated to {url}", "steps": 1, "url": self.page.url}
        else:
            # LLM fallback
            return await self._run_with_llm(prompt)

    async def _run_with_llm(self, prompt: str) -> Dict:
        """Fallback to LLM for unknown tasks."""
        import aiohttp

        license_file = EVERSALE_HOME / "license.key"
        if not license_file.exists():
            return {"status": "error", "error": "No license key"}

        license_key = license_file.read_text().strip()

        # Simple LLM loop
        max_steps = 15

        for step in range(1, max_steps + 1):
            self.step = step
            snapshot = await self.get_snapshot()

            system = """You control a browser. Reply with ONE action:
- navigate URL
- click "button text"
- type "placeholder" "text"
- press Enter
- scroll down
- done "result"

Example: click "Search"
Example: type "Search" "hello"
Example: done "Found result at URL"
"""

            user_msg = f"Task: {prompt}\n\nPage state:\n{snapshot[:1500]}\n\nNext action?"

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        "https://eversale.io/api/llm/v1/chat/completions",
                        json={"model": "qwen3:8b", "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user_msg}
                        ], "max_tokens": 150, "temperature": 0.1},
                        headers={"Authorization": f"Bearer {license_key}"},
                        timeout=aiohttp.ClientTimeout(total=20)
                    ) as resp:
                        if resp.status != 200:
                            continue
                        data = await resp.json()
                        content = data['choices'][0]['message'].get('content', '').strip()
                        reasoning = data['choices'][0]['message'].get('reasoning', '')

                        # Extract action
                        response = content or reasoning
                        response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL).strip()

                        # Parse action
                        action_match = re.match(r'(\w+)\s*(.*)', response)
                        if not action_match:
                            continue

                        action = action_match.group(1).lower()
                        params = action_match.group(2).strip()

                        print_step(step, action, params[:40], "running")

                        if action == "navigate":
                            await self.navigate(params)
                        elif action == "click":
                            text = params.strip('"\'')
                            await self.click_text(text)
                        elif action == "type":
                            match = re.match(r'"([^"]+)"\s+"([^"]+)"', params)
                            if match:
                                await self.type_placeholder(match.group(1), match.group(2))
                        elif action == "press":
                            await self.press_key(params or "Enter")
                        elif action == "scroll":
                            await self.scroll(params or "down")
                        elif action == "done":
                            print_step(step, action, params[:40], "success")
                            return {
                                "status": "complete",
                                "result": params,
                                "steps": step,
                                "url": self.page.url
                            }

                        print_step(step, action, params[:40], "success")
                        await asyncio.sleep(0.3)

            except Exception as e:
                if self.debug:
                    print(f"  {Colors.RED}Error: {e}{Colors.RESET}")
                continue

        return {"status": "max_steps", "steps": max_steps, "url": self.page.url}


# =============================================================================
# MAIN
# =============================================================================

async def run(prompt: str, headless: bool = True) -> Dict:
    """Main entry point."""
    browser = AgenticBrowser(headless=headless)
    try:
        await browser.setup()
        return await browser.run(prompt)
    finally:
        await browser.close()


async def main():
    """CLI entry."""
    # Check env var first (avoids Windows shell escaping issues), then fall back to sys.argv
    # Use pop() to clear env var and prevent leaking to subprocesses (Chromium, etc.)
    prompt = os.environ.pop("EVERSALE_PROMPT", "").strip()
    if not prompt and len(sys.argv) >= 2:
        prompt = ' '.join(sys.argv[1:])

    if not prompt:
        print(f"Eversale Browser Agent v{VERSION}")
        print("")
        print("Usage:")
        print('  eversale "go to FB Ads Library and search for booked meetings"')
        print('  eversale "find sales managers on LinkedIn"')
        sys.exit(1)
    result = await run(prompt)
    print(json.dumps(result, indent=2, default=str))


if __name__ == '__main__':
    asyncio.run(main())
