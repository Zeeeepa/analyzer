"""
Resource Economy - Estimates cost of tool calls and guides decisions during scarcity.
"""

from typing import Dict, Tuple


TOOL_COSTS: Dict[str, float] = {
    "playwright_get_markdown": 1.0,
    "playwright_map_site": 2.5,
    "playwright_crawl_for": 2.0,
    "playwright_llm_extract": 2.5,
    "playwright_extract_entities": 1.5,
    "playwright_answer_question": 1.2,
    "playwright_snapshot": 1.0,
    "playwright_screenshot": 0.8,
    "playwright_navigate": 1.8,
}


class ResourceEconomy:
    def __init__(self):
        self.history = []

    def estimate(self, tool_name: str, args: dict = None) -> Tuple[float, str]:
        cost = TOOL_COSTS.get(tool_name, 1.0)
        reason = f"{tool_name} estimated cost {cost:.1f}"
        if args:
            reason += f" ({len(args)} params)"
        self.history.append(tool_name)
        return cost, reason

    def cheapest_options(self, limit: int = 3):
        unique = []
        for tool in self.history[::-1]:
            if tool not in unique:
                unique.append(tool)
            if len(unique) >= limit:
                break
        return unique

    def budget_hint(self, threshold: float) -> str:
        options = [(tool, TOOL_COSTS.get(tool, 1.0)) for tool in TOOL_COSTS]
        affordable = [name for name, cost in options if cost <= threshold]
        return f"Lower-cost tools: {', '.join(affordable[:4])}" if affordable else "No low-cost fallback identified."
