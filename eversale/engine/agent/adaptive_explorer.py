"""
Adaptive Explorer - Runs exploratory scans when resources are stable.
"""

import asyncio
from datetime import datetime, timedelta
from typing import List, Optional


class AdaptiveExplorer:
    def __init__(self, interval: int = 6):
        self.interval = interval
        self.iteration = 0
        self.last_run = datetime.min
        self.cooldown = timedelta(minutes=10)

    async def consider(self, brain, survival, awareness) -> Optional[str]:
        self.iteration += 1
        if self.iteration % self.interval != 0:
            return None
        if datetime.utcnow() - self.last_run < self.cooldown:
            return None
        if survival.emergency_flags:
            return None
        if not awareness.long_term_goals:
            return None

        self.last_run = datetime.utcnow()

        goal = awareness.long_term_goals[-1]
        prompt = f"Survey for new updates related to '{goal}' and report anomalies."
        domain = brain._extract_domain(goal)
        target_url = f"https://{domain}" if domain else "https://example.com"
        try:
            result = await brain.mcp.call_tool(
                "playwright_crawl_for",
                {"url": target_url, "looking_for": goal, "max_pages": 5}
            )
            summary = f"Exploration result: visited {result.get('pages_visited', 0)} pages."
            if result.get('relevance_score'):
                summary += f" Score {result['relevance_score']:.2f}"
            await asyncio.sleep(0.5)
            return summary
        except Exception as e:
            return f"Exploration failed: {e}"
