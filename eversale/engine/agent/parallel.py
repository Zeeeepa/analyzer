"""
Parallel Execution - Run multiple actions concurrently.

Features:
1. Parallel research for multiple companies
2. Batch lead enrichment
3. Concurrent page scraping
"""

import asyncio
from typing import List, Dict, Any, Callable, Optional
from dataclasses import dataclass
from datetime import datetime
from loguru import logger

from .executors.base import ActionResult, ActionStatus
from .executors.sdr import D1_ResearchCompany, D7_QualifyLead


@dataclass
class BatchResult:
    """Result of a batch operation."""
    total: int
    successful: int
    failed: int
    duration_ms: int
    results: List[ActionResult]
    errors: List[str]


async def parallel_research(
    companies: List[str],
    browser,
    max_concurrent: int = 3
) -> BatchResult:
    """Research multiple companies in parallel."""
    start = datetime.now()
    results = []
    errors = []

    # Use semaphore to limit concurrency
    semaphore = asyncio.Semaphore(max_concurrent)

    async def research_one(company: str) -> ActionResult:
        async with semaphore:
            executor = D1_ResearchCompany(browser=browser)
            return await executor.execute({"company": company})

    # Run all in parallel
    tasks = [research_one(company) for company in companies]
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    # Process results
    for i, result in enumerate(raw_results):
        if isinstance(result, Exception):
            errors.append(f"{companies[i]}: {str(result)}")
            results.append(ActionResult(
                status=ActionStatus.FAILED,
                action_id=f"research_{i}",
                capability="D1",
                action="research_company",
                error=str(result)
            ))
        else:
            results.append(result)

    successful = sum(1 for r in results if r.status == ActionStatus.SUCCESS)

    return BatchResult(
        total=len(companies),
        successful=successful,
        failed=len(companies) - successful,
        duration_ms=int((datetime.now() - start).total_seconds() * 1000),
        results=results,
        errors=errors
    )


async def parallel_qualify(
    leads: List[Dict],
    browser=None,
    max_concurrent: int = 5
) -> BatchResult:
    """Qualify multiple leads in parallel."""
    start = datetime.now()
    results = []
    errors = []

    semaphore = asyncio.Semaphore(max_concurrent)

    async def qualify_one(lead: Dict) -> ActionResult:
        async with semaphore:
            executor = D7_QualifyLead(browser=browser)
            return await executor.execute({"lead": lead})

    tasks = [qualify_one(lead) for lead in leads]
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    for i, result in enumerate(raw_results):
        if isinstance(result, Exception):
            errors.append(f"Lead {i}: {str(result)}")
            results.append(ActionResult(
                status=ActionStatus.FAILED,
                action_id=f"qualify_{i}",
                capability="D7",
                action="qualify_lead",
                error=str(result)
            ))
        else:
            results.append(result)

    successful = sum(1 for r in results if r.status == ActionStatus.SUCCESS)

    return BatchResult(
        total=len(leads),
        successful=successful,
        failed=len(leads) - successful,
        duration_ms=int((datetime.now() - start).total_seconds() * 1000),
        results=results,
        errors=errors
    )


async def parallel_scrape_pages(
    urls: List[str],
    browser,
    max_concurrent: int = 3
) -> BatchResult:
    """Scrape multiple pages in parallel."""
    start = datetime.now()
    results = []
    errors = []

    # Need to create new pages for true parallelism
    # For now, use semaphore with single browser
    semaphore = asyncio.Semaphore(max_concurrent)

    async def scrape_one(url: str) -> Dict:
        async with semaphore:
            try:
                await browser.navigate(url)
                await asyncio.sleep(1)  # Let page load
                data = await browser.extract_page_data_fast()
                return {"url": url, "data": data, "success": True}
            except Exception as e:
                return {"url": url, "error": str(e), "success": False}

    tasks = [scrape_one(url) for url in urls]
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    successful = 0
    for i, result in enumerate(raw_results):
        if isinstance(result, Exception):
            errors.append(f"{urls[i]}: {str(result)}")
        elif result.get("success"):
            successful += 1
            results.append(ActionResult(
                status=ActionStatus.SUCCESS,
                action_id=f"scrape_{i}",
                capability="scrape",
                action="extract_page",
                data=result.get("data", {})
            ))
        else:
            errors.append(f"{urls[i]}: {result.get('error', 'Unknown error')}")

    return BatchResult(
        total=len(urls),
        successful=successful,
        failed=len(urls) - successful,
        duration_ms=int((datetime.now() - start).total_seconds() * 1000),
        results=results,
        errors=errors
    )


class BatchProcessor:
    """High-level batch processor with progress callbacks."""

    def __init__(self, browser=None):
        self.browser = browser
        self.progress_callback: Optional[Callable] = None

    def on_progress(self, callback: Callable):
        """Set progress callback."""
        self.progress_callback = callback

    async def research_companies(
        self,
        companies: List[str],
        max_concurrent: int = 3
    ) -> BatchResult:
        """Research multiple companies with progress updates."""
        result = await parallel_research(companies, self.browser, max_concurrent)

        if self.progress_callback:
            self.progress_callback({
                "action": "research",
                "total": result.total,
                "completed": result.successful + result.failed,
                "successful": result.successful,
            })

        return result

    async def enrich_leads(
        self,
        leads: List[Dict],
        max_concurrent: int = 3
    ) -> List[Dict]:
        """Enrich leads with website data."""
        # Get websites from leads
        leads_with_websites = [
            lead for lead in leads
            if lead.get("website")
        ]

        if not leads_with_websites:
            return leads

        # Scrape websites
        urls = [lead["website"] for lead in leads_with_websites]
        batch_result = await parallel_scrape_pages(urls, self.browser, max_concurrent)

        # Merge data back into leads
        url_to_data = {}
        for result in batch_result.results:
            if result.status == ActionStatus.SUCCESS:
                url = result.data.get("url")
                if url:
                    url_to_data[url] = result.data

        for lead in leads_with_websites:
            website = lead.get("website")
            if website in url_to_data:
                data = url_to_data[website]
                lead["emails"] = data.get("emails", [])
                lead["phones"] = data.get("phones", [])
                lead["tech_stack"] = data.get("techStack", [])
                lead["social"] = data.get("socialProfiles", {})
                lead["enriched"] = True

        return leads

    async def qualify_and_sort(
        self,
        leads: List[Dict]
    ) -> List[Dict]:
        """Qualify leads and sort by score."""
        batch_result = await parallel_qualify(leads, self.browser)

        # Add scores to leads
        for i, result in enumerate(batch_result.results):
            if result.status == ActionStatus.SUCCESS and i < len(leads):
                leads[i]["score"] = result.data.get("score", 0)
                leads[i]["qualification"] = result.data.get("qualification", "UNKNOWN")
                leads[i]["reasons"] = result.data.get("reasons", [])

        # Sort by score descending
        leads.sort(key=lambda x: x.get("score", 0), reverse=True)

        return leads


# Convenience functions
async def research_batch(companies: List[str], browser, max_concurrent: int = 3) -> BatchResult:
    """Quick batch research."""
    return await parallel_research(companies, browser, max_concurrent)


async def enrich_batch(leads: List[Dict], browser, max_concurrent: int = 3) -> List[Dict]:
    """Quick batch enrichment."""
    processor = BatchProcessor(browser)
    return await processor.enrich_leads(leads, max_concurrent)
