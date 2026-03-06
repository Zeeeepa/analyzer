"""
Lead Generation Workflows - SDR and lead extraction automation.

Extracted workflow handlers for:
- SDR lead finding (Workflow D)
- Facebook Ads Library extraction
- Reddit warm signals extraction
- Batch URL extraction
- Contact enrichment
- CSV output formatting

This module consolidates all lead generation functionality from brain_enhanced_v2.py
to improve maintainability and reduce file size.
"""

import asyncio
import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, TYPE_CHECKING
from dataclasses import dataclass, field
from loguru import logger

# Import fast workflow browser
try:
    from .agentic_browser import AgenticBrowser
    AGENTIC_BROWSER_AVAILABLE = True
except ImportError:
    AGENTIC_BROWSER_AVAILABLE = False
    logger.debug("AgenticBrowser not available, using fallback methods")

if TYPE_CHECKING:
    pass

# Output directory for lead files
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)


@dataclass
class LeadResult:
    """Result from lead extraction operations."""
    success: bool
    leads: List[Dict] = field(default_factory=list)
    total_count: int = 0
    source: str = ""
    output_file: str = ""
    error: str = ""
    metadata: Dict = field(default_factory=dict)


@dataclass
class Lead:
    """Represents a single lead/prospect."""
    name: str = ""
    email: str = ""
    phone: str = ""
    company: str = ""
    title: str = ""
    website: str = ""
    linkedin: str = ""
    source: str = ""
    source_url: str = ""
    warm_signal: str = ""
    extracted_at: str = ""

    def to_dict(self) -> Dict:
        """Convert to dictionary for CSV/JSON export."""
        return {
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "company": self.company,
            "title": self.title,
            "website": self.website,
            "linkedin": self.linkedin,
            "source": self.source,
            "source_url": self.source_url,
            "warm_signal": self.warm_signal,
            "extracted_at": self.extracted_at or datetime.now().isoformat()
        }


class LeadWorkflows:
    """
    Handles lead generation workflow execution.

    Responsibilities:
    - Execute SDR lead finding workflows
    - Extract leads from Facebook Ads Library
    - Extract warm signals from Reddit
    - Batch extract contacts from multiple URLs
    - Enrich contact data
    - Format and export leads to CSV
    """

    def __init__(
        self,
        call_tool_func: Callable,
        emit_summary_func: Callable = None,
        ollama_client = None,
        model: str = None
    ):
        """
        Initialize LeadWorkflows.

        Args:
            call_tool_func: Function to call browser tools (e.g., mcp.call_tool)
            emit_summary_func: Function to emit progress summaries
            ollama_client: Ollama client for LLM calls
            model: LLM model name
        """
        self._call_tool = call_tool_func
        self._emit_summary = emit_summary_func or (lambda msg, issues: logger.info(msg))
        self.ollama_client = ollama_client
        self.model = model

    # =============== SDR WORKFLOW (D) ===============

    async def execute_sdr_workflow(
        self,
        prompt: str,
        target_industry: str = None,
        target_company: str = None,
        lead_count: int = 10
    ) -> LeadResult:
        """
        Execute SDR lead finding workflow (Workflow D).

        Finds leads through:
        1. Company research
        2. Contact extraction
        3. Lead qualification
        4. CSV export

        Args:
            prompt: User prompt describing lead requirements
            target_industry: Industry to target
            target_company: Specific company to research
            lead_count: Number of leads to find

        Returns:
            LeadResult with extracted leads
        """
        lower = prompt.lower()
        all_leads = []

        logger.info(f"[SDR] Starting workflow - target: {lead_count} leads")

        # Detect data sources from prompt
        sources = self._detect_lead_sources(lower)

        if not sources:
            sources = ["google"]  # Default to Google search

        for source in sources:
            try:
                if source == "fb_ads":
                    # Extract search term from prompt
                    search_term = self._extract_search_term(prompt)
                    result = await self.execute_fb_ads_extraction(search_term, lead_count)
                    if result.success:
                        all_leads.extend(result.leads)

                elif source == "reddit":
                    subreddit = self._extract_subreddit(prompt)
                    result = await self.execute_reddit_extraction(subreddit, lead_count)
                    if result.success:
                        all_leads.extend(result.leads)

                elif source == "linkedin":
                    result = await self._search_linkedin(prompt, lead_count)
                    all_leads.extend(result)

                elif source == "google":
                    result = await self._search_google_for_leads(prompt, lead_count)
                    all_leads.extend(result)

            except Exception as e:
                logger.warning(f"[SDR] Source {source} failed: {e}")
                continue

        # Deduplicate leads
        unique_leads = self._deduplicate_leads(all_leads)

        # Export to CSV
        output_file = ""
        if unique_leads:
            output_file = self._build_leads_csv(unique_leads, "sdr_leads")

        summary = f"**SDR WORKFLOW COMPLETE**\n\n"
        summary += f"- Sources searched: {', '.join(sources)}\n"
        summary += f"- Leads found: {len(unique_leads)}\n"
        if output_file:
            summary += f"- Output file: {output_file}\n"

        self._emit_summary(summary, [])

        return LeadResult(
            success=len(unique_leads) > 0,
            leads=unique_leads,
            total_count=len(unique_leads),
            source="sdr_workflow",
            output_file=output_file
        )

    def _detect_lead_sources(self, prompt_lower: str) -> List[str]:
        """Detect which lead sources to use from prompt."""
        sources = []

        if any(kw in prompt_lower for kw in ["facebook ads", "fb ads", "ads library"]):
            sources.append("fb_ads")
        if any(kw in prompt_lower for kw in ["reddit", "subreddit", "r/"]):
            sources.append("reddit")
        if any(kw in prompt_lower for kw in ["linkedin", "li "]):
            sources.append("linkedin")
        if any(kw in prompt_lower for kw in ["google", "search", "find"]):
            sources.append("google")

        return sources

    def _extract_search_term(self, prompt: str) -> str:
        """Extract search term from prompt."""
        # Look for quoted terms first
        quoted = re.findall(r"['\"]([^'\"]+)['\"]", prompt)
        if quoted:
            return quoted[0]

        # Look for "for X" pattern
        for_match = re.search(r"for\s+['\"]?([^'\"]+?)['\"]?\s*(?:$|and|or|,)", prompt, re.I)
        if for_match:
            return for_match.group(1).strip()

        # Look for key product/industry terms
        keywords = re.findall(r"\b(crm|saas|software|agency|marketing|sales|automation)\b", prompt, re.I)
        if keywords:
            return " ".join(keywords[:2])

        return "business"

    def _extract_subreddit(self, prompt: str) -> str:
        """Extract subreddit name from prompt."""
        match = re.search(r"r/(\w+)", prompt)
        if match:
            return match.group(1)
        match = re.search(r"subreddit\s+['\"]?(\w+)", prompt, re.I)
        if match:
            return match.group(1)
        return "entrepreneur"  # Default subreddit

    # =============== FACEBOOK ADS EXTRACTION ===============

    async def execute_fb_ads_extraction(
        self,
        search_term: str,
        max_ads: int = 20
    ) -> LeadResult:
        """
        Extract advertisers from Facebook Ads Library.

        Args:
            search_term: Term to search in Ads Library
            max_ads: Maximum number of ads to extract

        Returns:
            LeadResult with extracted advertiser leads
        """
        logger.info(f"[FB_ADS] Extracting ads for: {search_term}")

        # FAST PATH: Use AgenticBrowser deterministic workflow
        if AGENTIC_BROWSER_AVAILABLE:
            try:
                browser = AgenticBrowser(headless=True, debug=False)
                await browser.setup()
                try:
                    result = await browser.workflow_fb_ads(search_term)
                    if result.get("status") == "complete" and result.get("data"):
                        lead = Lead(
                            name=result["data"].get("name", ""),
                            company=result["data"].get("name", ""),
                            website=result["data"].get("url", ""),
                            source="facebook_ads",
                        )
                        leads = [lead.__dict__]
                        output_file = self._build_leads_csv(leads, f"fb_ads_{search_term.replace(' ', '_')}")
                        logger.info(f"[FB_ADS] Fast workflow extracted: {result['data'].get('name')}")
                        return LeadResult(
                            success=True,
                            leads=leads,
                            total_count=1,
                            source="facebook_ads",
                            output_file=output_file,
                            metadata={"search_term": search_term, "landing_page": result["data"].get("url", "")}
                        )
                finally:
                    await browser.close()
            except Exception as e:
                logger.debug(f"[FB_ADS] Fast workflow failed, using fallback: {e}")

        try:
            # Navigate to FB Ads Library
            url = f"https://www.facebook.com/ads/library/?active_status=active&ad_type=all&q={search_term}&media_type=all"
            nav_result = await self._call_tool("playwright_navigate", {"url": url})

            if not nav_result or nav_result.get("error"):
                return LeadResult(success=False, error="Failed to navigate to FB Ads Library")

            # Wait for content to load
            await asyncio.sleep(2)

            # Try dedicated FB ads extraction tool first
            try:
                fb_result = await self._call_tool("playwright_extract_fb_ads", {
                    "limit": max_ads
                })

                if fb_result and fb_result.get("ads"):
                    leads = self._convert_fb_ads_to_leads(fb_result["ads"])
                    output_file = self._build_leads_csv(leads, f"fb_ads_{search_term.replace(' ', '_')}")

                    return LeadResult(
                        success=True,
                        leads=leads,
                        total_count=len(leads),
                        source="facebook_ads",
                        output_file=output_file,
                        metadata={"search_term": search_term}
                    )
            except Exception as e:
                logger.debug(f"FB ads tool not available, using fallback: {e}")

            # Fallback: Extract using structured extraction
            extract_result = await self._call_tool("playwright_extract_structured", {
                "item_selector": "[data-testid='ad_library_card'], .x1iorvi4",
                "field_selectors": {
                    "advertiser": ".x1heor9g, [role='heading']",
                    "page_name": "a[role='link']",
                    "started": ".x1fgtraw",
                    "ad_text": ".x1iorvi4 span"
                },
                "limit": max_ads
            })

            if extract_result and extract_result.get("data"):
                leads = self._convert_fb_ads_to_leads(extract_result["data"])
            else:
                # Ultra fallback: get markdown and parse
                md_result = await self._call_tool("playwright_get_markdown", {})
                leads = self._parse_fb_ads_from_markdown(md_result.get("markdown", "") if md_result else "")

            if leads:
                output_file = self._build_leads_csv(leads, f"fb_ads_{search_term.replace(' ', '_')}")

                return LeadResult(
                    success=True,
                    leads=leads,
                    total_count=len(leads),
                    source="facebook_ads",
                    output_file=output_file,
                    metadata={"search_term": search_term}
                )

            return LeadResult(
                success=False,
                error="No ads found or extraction failed"
            )

        except Exception as e:
            logger.error(f"[FB_ADS] Extraction failed: {e}")
            return LeadResult(success=False, error=str(e))

    def _convert_fb_ads_to_leads(self, ads: List[Dict]) -> List[Dict]:
        """Convert FB Ads data to lead format."""
        leads = []
        for ad in ads:
            lead = Lead(
                name=ad.get("page_name", ad.get("advertiser", "")),
                company=ad.get("advertiser", ad.get("page_name", "")),
                website=ad.get("website", ""),
                source="facebook_ads",
                source_url=ad.get("page_url", ""),
                warm_signal=f"Active advertiser - {ad.get('ad_text', '')[:100]}",
                extracted_at=datetime.now().isoformat()
            )
            leads.append(lead.to_dict())
        return leads

    def _parse_fb_ads_from_markdown(self, markdown: str) -> List[Dict]:
        """Parse advertiser info from page markdown."""
        leads = []
        # Look for advertiser patterns
        patterns = [
            r"(?:Page|Advertiser)[:\s]+([^\n]+)",
            r"\*\*([^*]+)\*\*\s+(?:is\s+)?running",
            r"See\s+ads\s+from\s+([^\n]+)"
        ]

        for pattern in patterns:
            matches = re.findall(pattern, markdown, re.I)
            for match in matches[:20]:  # Limit to 20
                if match and len(match) > 2:
                    lead = Lead(
                        company=match.strip(),
                        source="facebook_ads",
                        warm_signal="Active advertiser",
                        extracted_at=datetime.now().isoformat()
                    )
                    leads.append(lead.to_dict())

        return leads

    # =============== TIKTOK ADS EXTRACTION ===============

    async def execute_tiktok_ads_extraction(
        self,
        search_term: str = "marketing",
        max_ads: int = 20,
        source: str = "library"  # "library" or "creative_center"
    ) -> LeadResult:
        """
        Extract leads from TikTok Ads Library or Creative Center.

        Args:
            search_term: Keyword to search for
            max_ads: Maximum ads to extract
            source: "library" for TikTok Ad Library, "creative_center" for Creative Center Top Ads

        Returns:
            LeadResult with extracted advertiser leads
        """
        logger.info(f"[TIKTOK_ADS] Extracting ads for: {search_term} (source: {source})")

        try:
            import urllib.parse

            # Build URL based on source
            if source == "creative_center":
                url = f"https://ads.tiktok.com/business/creativecenter/inspiration/topads/pad/en?period=30&region=US&keyword={urllib.parse.quote(search_term)}"
            else:
                url = f"https://library.tiktok.com/ads?region=US&search_value={urllib.parse.quote(search_term)}"

            nav_result = await self._call_tool("playwright_navigate", {"url": url})

            if not nav_result or nav_result.get("error"):
                return LeadResult(success=False, error="Failed to navigate to TikTok Ads")

            # Wait for React app to load
            await asyncio.sleep(3)

            # Try dedicated TikTok ads extraction tool
            try:
                tiktok_result = await self._call_tool("playwright_extract_tiktok_ads", {
                    "max_ads": max_ads
                })

                if tiktok_result and tiktok_result.get("ads"):
                    leads = self._convert_tiktok_ads_to_leads(tiktok_result["ads"])
                    output_file = self._build_leads_csv(leads, f"tiktok_ads_{search_term.replace(' ', '_')}")

                    return LeadResult(
                        success=True,
                        leads=leads,
                        total_count=len(leads),
                        source="tiktok_ads",
                        output_file=output_file,
                        metadata={"search_term": search_term, "source": source}
                    )
            except Exception as e:
                logger.debug(f"TikTok ads tool not available, using fallback: {e}")

            # Fallback: Extract using markdown
            md_result = await self._call_tool("playwright_get_markdown", {})
            leads = self._parse_tiktok_ads_from_markdown(md_result.get("markdown", "") if md_result else "")

            if leads:
                output_file = self._build_leads_csv(leads, f"tiktok_ads_{search_term.replace(' ', '_')}")

                return LeadResult(
                    success=True,
                    leads=leads,
                    total_count=len(leads),
                    source="tiktok_ads",
                    output_file=output_file,
                    metadata={"search_term": search_term, "source": source}
                )

            return LeadResult(
                success=False,
                error="No ads found or extraction failed"
            )

        except Exception as e:
            logger.error(f"[TIKTOK_ADS] Extraction failed: {e}")
            return LeadResult(success=False, error=str(e))

    def _convert_tiktok_ads_to_leads(self, ads: List[Dict]) -> List[Dict]:
        """Convert TikTok Ads data to lead format."""
        leads = []
        for ad in ads:
            # Get engagement metrics for warm signal
            likes = ad.get("likes", 0)
            views = ad.get("views", 0)
            engagement_str = f"{likes:,} likes" if likes else ""
            if views:
                engagement_str = f"{views:,} views, {engagement_str}" if engagement_str else f"{views:,} views"

            lead = Lead(
                name=ad.get("advertiser", ad.get("title", "")),
                company=ad.get("advertiser", ad.get("title", "")),
                website=ad.get("landing_url", ad.get("website_domain", "")),
                source="tiktok_ads",
                source_url=f"https://library.tiktok.com/ads",
                warm_signal=f"Active TikTok advertiser - {engagement_str}" if engagement_str else "Active TikTok advertiser",
                extracted_at=datetime.now().isoformat()
            )
            leads.append(lead.to_dict())
        return leads

    def _parse_tiktok_ads_from_markdown(self, markdown: str) -> List[Dict]:
        """Parse advertiser info from TikTok page markdown."""
        leads = []
        # Look for advertiser patterns
        patterns = [
            r"(?:Brand|Advertiser|by)[:\s]+([^\n]+)",
            r"\*\*([^*]+)\*\*",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, markdown, re.I)
            for match in matches[:20]:
                if match and len(match) > 2 and len(match) < 100:
                    lead = Lead(
                        company=match.strip(),
                        source="tiktok_ads",
                        warm_signal="Active TikTok advertiser",
                        extracted_at=datetime.now().isoformat()
                    )
                    leads.append(lead.to_dict())

        return leads

    # =============== REDDIT EXTRACTION ===============

    async def execute_reddit_extraction(
        self,
        subreddit: str = "entrepreneur",
        max_posts: int = 20
    ) -> LeadResult:
        """
        Extract warm signals from Reddit posts.

        Looks for:
        - Users asking for solutions
        - Businesses sharing problems
        - Decision makers posting

        Args:
            subreddit: Subreddit to search
            max_posts: Maximum posts to extract

        Returns:
            LeadResult with warm signal leads
        """
        logger.info(f"[REDDIT] Extracting from r/{subreddit}")

        # FAST PATH: Use AgenticBrowser deterministic workflow
        if AGENTIC_BROWSER_AVAILABLE:
            try:
                browser = AgenticBrowser(headless=True, debug=False)
                await browser.setup()
                try:
                    # Use subreddit as search topic
                    result = await browser.workflow_reddit(subreddit)
                    if result.get("status") == "complete" and result.get("data"):
                        lead = Lead(
                            name=result["data"].get("username", ""),
                            source="reddit",
                            source_url=result["data"].get("url", ""),
                            warm_signal=f"Active Reddit user in r/{subreddit}",
                            extracted_at=datetime.now().isoformat()
                        )
                        leads = [lead.to_dict()]
                        output_file = self._build_leads_csv(leads, f"reddit_{subreddit}")
                        logger.info(f"[REDDIT] Fast workflow found: u/{result['data'].get('username')}")
                        return LeadResult(
                            success=True,
                            leads=leads,
                            total_count=1,
                            source="reddit",
                            output_file=output_file,
                            metadata={"subreddit": subreddit, "user_url": result["data"].get("url", "")}
                        )
                finally:
                    await browser.close()
            except Exception as e:
                logger.debug(f"[REDDIT] Fast workflow failed, using fallback: {e}")

        try:
            # Navigate to subreddit
            url = f"https://www.reddit.com/r/{subreddit}/new/"
            nav_result = await self._call_tool("playwright_navigate", {"url": url})

            if not nav_result or nav_result.get("error"):
                return LeadResult(success=False, error=f"Failed to navigate to r/{subreddit}")

            await asyncio.sleep(2)

            # Try dedicated Reddit extraction tool
            try:
                reddit_result = await self._call_tool("playwright_extract_reddit", {
                    "limit": max_posts
                })

                if reddit_result and reddit_result.get("posts"):
                    leads = self._convert_reddit_posts_to_leads(reddit_result["posts"])
                    output_file = self._build_leads_csv(leads, f"reddit_{subreddit}")

                    return LeadResult(
                        success=True,
                        leads=leads,
                        total_count=len(leads),
                        source="reddit",
                        output_file=output_file,
                        metadata={"subreddit": subreddit}
                    )
            except Exception as e:
                logger.debug(f"Reddit tool not available, using fallback: {e}")

            # Fallback: structured extraction
            extract_result = await self._call_tool("playwright_extract_structured", {
                "item_selector": "shreddit-post, [data-testid='post-container']",
                "field_selectors": {
                    "title": "[slot='title'], h3",
                    "author": "[data-testid='post_author_link']",
                    "subreddit": "[data-testid='subreddit-name']",
                    "score": "[score]",
                    "comments": "[data-testid='comment-count']"
                },
                "limit": max_posts
            })

            leads = []
            if extract_result and extract_result.get("data"):
                leads = self._convert_reddit_posts_to_leads(extract_result["data"])
            else:
                # Ultra fallback: markdown parsing
                md_result = await self._call_tool("playwright_get_markdown", {})
                leads = self._parse_reddit_from_markdown(md_result.get("markdown", "") if md_result else "")

            if leads:
                output_file = self._build_leads_csv(leads, f"reddit_{subreddit}")

                return LeadResult(
                    success=True,
                    leads=leads,
                    total_count=len(leads),
                    source="reddit",
                    output_file=output_file,
                    metadata={"subreddit": subreddit}
                )

            return LeadResult(success=False, error="No posts found")

        except Exception as e:
            logger.error(f"[REDDIT] Extraction failed: {e}")
            return LeadResult(success=False, error=str(e))

    def _convert_reddit_posts_to_leads(self, posts: List[Dict]) -> List[Dict]:
        """Convert Reddit posts to warm signal leads."""
        leads = []

        # Keywords indicating buying intent or decision-making power
        intent_keywords = [
            "looking for", "need", "recommend", "help", "advice",
            "best", "solution", "tool", "software", "service",
            "budget", "business", "company", "agency", "founder", "ceo"
        ]

        for post in posts:
            title = post.get("title", "").lower()

            # Score warm signal strength
            warm_signals = []
            for kw in intent_keywords:
                if kw in title:
                    warm_signals.append(kw)

            if warm_signals:
                lead = Lead(
                    name=post.get("author", ""),
                    source="reddit",
                    source_url=f"https://reddit.com{post.get('permalink', '')}",
                    warm_signal=f"Intent: {', '.join(warm_signals[:3])} - {post.get('title', '')[:80]}",
                    extracted_at=datetime.now().isoformat()
                )
                leads.append(lead.to_dict())

        return leads

    def _parse_reddit_from_markdown(self, markdown: str) -> List[Dict]:
        """Parse Reddit posts from markdown."""
        leads = []

        # Look for post patterns
        patterns = [
            r"Posted by u/([^\s]+).*?([^\n]+)",
            r"\[([^\]]+)\]\((/r/[^\)]+)\)"
        ]

        for pattern in patterns:
            matches = re.findall(pattern, markdown, re.I)
            for match in matches[:20]:
                if len(match) >= 2:
                    lead = Lead(
                        name=match[0] if match[0].startswith("u/") else "",
                        source="reddit",
                        warm_signal=match[1] if len(match[1]) > 10 else match[0],
                        extracted_at=datetime.now().isoformat()
                    )
                    leads.append(lead.to_dict())

        return leads

    # =============== BATCH EXTRACTION ===============

    async def execute_batch_extraction(
        self,
        urls: List[str],
        batch_size: int = 5
    ) -> LeadResult:
        """
        Extract contacts from multiple URLs in parallel batches.

        Args:
            urls: List of URLs to extract from
            batch_size: Number of URLs to process in parallel

        Returns:
            LeadResult with all extracted contacts
        """
        logger.info(f"[BATCH] Extracting contacts from {len(urls)} URLs")

        all_leads = []
        errors = []

        for i in range(0, len(urls), batch_size):
            batch = urls[i:i + batch_size]
            logger.info(f"[BATCH] Processing batch {i // batch_size + 1}")

            # Process batch in parallel
            tasks = [self._extract_contacts_from_url(url) for url in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            for url, result in zip(batch, batch_results):
                if isinstance(result, Exception):
                    errors.append({"url": url, "error": str(result)})
                elif result:
                    all_leads.extend(result)

        # Deduplicate
        unique_leads = self._deduplicate_leads(all_leads)

        # Export
        output_file = ""
        if unique_leads:
            output_file = self._build_leads_csv(unique_leads, "batch_extract")

        summary = f"**BATCH EXTRACTION COMPLETE**\n\n"
        summary += f"- URLs processed: {len(urls)}\n"
        summary += f"- Contacts found: {len(unique_leads)}\n"
        summary += f"- Errors: {len(errors)}\n"
        if output_file:
            summary += f"- Output file: {output_file}\n"

        self._emit_summary(summary, [])

        return LeadResult(
            success=len(unique_leads) > 0,
            leads=unique_leads,
            total_count=len(unique_leads),
            source="batch_extract",
            output_file=output_file,
            metadata={"urls_processed": len(urls), "errors": len(errors)}
        )

    async def _extract_contacts_from_url(self, url: str) -> List[Dict]:
        """Extract contacts from a single URL."""
        try:
            # Try fast extraction tool first
            try:
                result = await self._call_tool("playwright_extract_page_fast", {"url": url})
                if result and result.get("contacts"):
                    return self._convert_contacts_to_leads(result["contacts"], url)
            except Exception:
                pass

            # Navigate and extract manually
            nav_result = await self._call_tool("playwright_navigate", {"url": url})
            if not nav_result or nav_result.get("error"):
                return []

            # Find contacts on page
            contacts = await self._call_tool("playwright_find_contacts", {})
            if contacts and (contacts.get("emails") or contacts.get("phones")):
                return self._convert_contacts_to_leads(contacts, url)

            return []

        except Exception as e:
            logger.warning(f"[BATCH] Failed to extract from {url}: {e}")
            return []

    def _convert_contacts_to_leads(self, contacts: Dict, source_url: str) -> List[Dict]:
        """Convert extracted contacts to lead format."""
        leads = []

        emails = contacts.get("emails", [])
        phones = contacts.get("phones", [])
        names = contacts.get("names", [])

        # Pair emails with names if available
        for i, email in enumerate(emails):
            lead = Lead(
                name=names[i] if i < len(names) else "",
                email=email,
                phone=phones[i] if i < len(phones) else "",
                website=source_url,
                source="web_extract",
                source_url=source_url,
                extracted_at=datetime.now().isoformat()
            )
            leads.append(lead.to_dict())

        return leads

    # =============== CONTACT ENRICHMENT ===============

    async def execute_contact_enrichment(
        self,
        leads: List[Dict]
    ) -> LeadResult:
        """
        Enrich leads with additional data.

        Looks up:
        - Company info from domain
        - LinkedIn profiles
        - Contact details

        Args:
            leads: List of lead dictionaries to enrich

        Returns:
            LeadResult with enriched leads
        """
        logger.info(f"[ENRICH] Enriching {len(leads)} leads")

        enriched = []

        for lead in leads:
            try:
                enriched_lead = await self._enrich_single_lead(lead)
                enriched.append(enriched_lead)
            except Exception as e:
                logger.warning(f"[ENRICH] Failed to enrich lead: {e}")
                enriched.append(lead)  # Keep original

        # Export enriched data
        output_file = self._build_leads_csv(enriched, "enriched_leads")

        return LeadResult(
            success=True,
            leads=enriched,
            total_count=len(enriched),
            source="enrichment",
            output_file=output_file
        )

    async def _enrich_single_lead(self, lead: Dict) -> Dict:
        """Enrich a single lead with additional data."""
        enriched = lead.copy()

        # Extract domain from email or website
        domain = None
        if lead.get("email"):
            domain = lead["email"].split("@")[-1]
        elif lead.get("website"):
            domain = re.sub(r"https?://(?:www\.)?", "", lead["website"]).split("/")[0]

        if domain:
            # Look up company info
            try:
                company_url = f"https://{domain}"
                nav_result = await self._call_tool("playwright_navigate", {"url": company_url})

                if nav_result and nav_result.get("success"):
                    snapshot = await self._call_tool("playwright_snapshot", {})
                    if snapshot:
                        enriched["company"] = enriched.get("company") or snapshot.get("title", "")

                    # Try to find LinkedIn
                    md_result = await self._call_tool("playwright_get_markdown", {})
                    if md_result:
                        linkedin_match = re.search(r"linkedin\.com/company/([^/\s\"']+)", md_result.get("markdown", ""))
                        if linkedin_match:
                            enriched["linkedin"] = f"https://linkedin.com/company/{linkedin_match.group(1)}"

            except Exception as e:
                logger.debug(f"Company lookup failed: {e}")

        return enriched

    # =============== CSV OUTPUT ===============

    def _build_leads_csv(
        self,
        leads: List[Dict],
        prefix: str = "leads"
    ) -> str:
        """
        Build and save leads to CSV file.

        Args:
            leads: List of lead dictionaries
            prefix: Filename prefix

        Returns:
            Path to created CSV file
        """
        if not leads:
            return ""

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{prefix}_{timestamp}.csv"
        filepath = OUTPUT_DIR / filename

        # Determine all fields
        all_fields = set()
        for lead in leads:
            all_fields.update(lead.keys())

        # Prioritize common fields
        priority_fields = [
            "name", "email", "phone", "company", "title",
            "website", "linkedin", "source", "source_url",
            "warm_signal", "extracted_at"
        ]

        ordered_fields = [f for f in priority_fields if f in all_fields]
        ordered_fields.extend([f for f in sorted(all_fields) if f not in ordered_fields])

        try:
            with open(filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=ordered_fields, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(leads)

            logger.info(f"[CSV] Saved {len(leads)} leads to {filepath}")
            return str(filepath)

        except Exception as e:
            logger.error(f"[CSV] Failed to save: {e}")
            return ""

    def _deduplicate_leads(self, leads: List[Dict]) -> List[Dict]:
        """Remove duplicate leads based on email or company+name."""
        seen = set()
        unique = []

        for lead in leads:
            # Create dedup key
            key = None
            if lead.get("email"):
                key = lead["email"].lower()
            elif lead.get("company") and lead.get("name"):
                key = f"{lead['company'].lower()}|{lead['name'].lower()}"
            elif lead.get("company"):
                key = lead["company"].lower()
            elif lead.get("name"):
                key = lead["name"].lower()

            if key and key not in seen:
                seen.add(key)
                unique.append(lead)
            elif not key:
                unique.append(lead)  # Keep leads without dedup key

        return unique

    # =============== SEARCH HELPERS ===============

    async def _search_linkedin(self, prompt: str, limit: int) -> List[Dict]:
        """
        Search LinkedIn for leads with Google fallback.

        Strategy:
        1. Try direct LinkedIn access
        2. If blocked/requires login, search Google for: "site:linkedin.com/in [query]"
        3. Extract LinkedIn profile URLs from Google results
        """
        leads = []

        try:
            # Construct search URL
            search_term = self._extract_search_term(prompt)
            url = f"https://www.linkedin.com/search/results/people/?keywords={search_term}"

            nav_result = await self._call_tool("playwright_navigate", {"url": url})
            if not nav_result or nav_result.get("error"):
                return []

            await asyncio.sleep(2)

            # Check for login wall
            snapshot = await self._call_tool("playwright_snapshot", {})
            if snapshot and "sign in" in snapshot.get("summary", "").lower():
                logger.info("[LinkedIn] Login required - trying Google fallback")

                # Fallback: Search Google for LinkedIn profiles
                google_query = f"site:linkedin.com/in {search_term}"
                google_url = f"https://www.google.com/search?q={google_query}"

                google_nav = await self._call_tool("playwright_navigate", {"url": google_url})
                if google_nav and not google_nav.get("error"):
                    await asyncio.sleep(2)

                    # Get page markdown to extract LinkedIn URLs
                    md_result = await self._call_tool("playwright_get_markdown", {})
                    if md_result and md_result.get("markdown"):
                        import re
                        markdown = md_result["markdown"]

                        # Extract LinkedIn profile URLs from markdown
                        profile_urls = re.findall(r'https://(?:www\.)?linkedin\.com/in/([^/\s\)]+)', markdown)
                        seen = set()

                        for profile_id in profile_urls[:limit]:
                            if profile_id not in seen:
                                seen.add(profile_id)
                                lead = Lead(
                                    name=profile_id.replace('-', ' ').title(),  # Best effort name from URL
                                    linkedin=f"https://www.linkedin.com/in/{profile_id}",
                                    source="linkedin_google_fallback",
                                    extracted_at=datetime.now().isoformat()
                                )
                                leads.append(lead.to_dict())

                        if leads:
                            logger.info(f"[LinkedIn] Google fallback found {len(leads)} profiles")
                            return leads

                logger.warning("[LinkedIn] Google fallback found no results")
                return []

            # Extract profiles (direct LinkedIn access worked)
            extract_result = await self._call_tool("playwright_extract_structured", {
                "item_selector": ".entity-result",
                "field_selectors": {
                    "name": ".entity-result__title-text a",
                    "title": ".entity-result__primary-subtitle",
                    "location": ".entity-result__secondary-subtitle",
                    "profile_url": ".entity-result__title-text a@href"
                },
                "limit": limit
            })

            if extract_result and extract_result.get("data"):
                for item in extract_result["data"]:
                    lead = Lead(
                        name=item.get("name", ""),
                        title=item.get("title", ""),
                        linkedin=item.get("profile_url", ""),
                        source="linkedin",
                        extracted_at=datetime.now().isoformat()
                    )
                    leads.append(lead.to_dict())

        except Exception as e:
            logger.warning(f"[LinkedIn] Search failed: {e}")

        return leads

    async def _search_google_for_leads(self, prompt: str, limit: int) -> List[Dict]:
        """Search Google for leads."""
        leads = []

        try:
            search_term = self._extract_search_term(prompt)
            # Add lead-finding modifiers
            query = f'{search_term} "contact" OR "email" OR "about us"'
            url = f"https://www.google.com/search?q={query}"

            nav_result = await self._call_tool("playwright_navigate", {"url": url})
            if not nav_result or nav_result.get("error"):
                return []

            await asyncio.sleep(1)

            # Extract search results
            extract_result = await self._call_tool("playwright_extract_structured", {
                "item_selector": ".g, [data-sokoban-container]",
                "field_selectors": {
                    "title": "h3",
                    "url": "a@href",
                    "snippet": ".VwiC3b, [data-sncf]"
                },
                "limit": limit
            })

            if extract_result and extract_result.get("data"):
                for item in extract_result["data"][:limit]:
                    url = item.get("url", "")
                    if url and not any(skip in url for skip in ["google.com", "youtube.com", "facebook.com"]):
                        lead = Lead(
                            company=item.get("title", ""),
                            website=url,
                            source="google",
                            source_url=url,
                            warm_signal=item.get("snippet", "")[:100],
                            extracted_at=datetime.now().isoformat()
                        )
                        leads.append(lead.to_dict())

        except Exception as e:
            logger.warning(f"[Google] Search failed: {e}")

        return leads


# Convenience function for creating LeadWorkflows instance
def get_lead_workflows(call_tool_func: Callable, **kwargs) -> LeadWorkflows:
    """Create a LeadWorkflows instance with the given tool caller."""
    return LeadWorkflows(call_tool_func, **kwargs)
