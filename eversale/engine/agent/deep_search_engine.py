"""
Deep Search Engine - Exa-inspired multi-query search with summaries.

Provides:
- Query expansion heuristics
- SERP extraction from Google
- Result ranking/deduplication
- Optional summarization of top sources
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from urllib.parse import quote_plus

from loguru import logger

if TYPE_CHECKING:
    from .playwright_direct import PlaywrightClient


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


@dataclass
class SearchHit:
    """Structured search result."""

    title: str
    url: str
    snippet: str = ""
    position: int = 0
    source_query: str = ""
    variant_index: int = 0
    score: float = 0.0
    summary: Optional[str] = None
    key_facts: List[str] = field(default_factory=list)


class QueryExpander:
    """Heuristic-based query expansion, inspired by Exa's deep search."""

    @staticmethod
    def expand(query: str, context: str = "", max_variants: int = 3) -> List[str]:
        terms = query.strip()
        if not terms:
            return []

        variants: List[str] = [terms]
        lowered = terms.lower()

        # Context-aware variants
        if context:
            context = context.strip()
            variants.append(f"{terms} {context}")

        if "pricing" not in lowered:
            variants.append(f"{terms} pricing")
        if "news" not in lowered:
            variants.append(f"{terms} latest news")
        variants.append(f"{terms} overview")
        variants.append(f"{terms} competitors")

        # Deduplicate while preserving order
        seen = set()
        ordered: List[str] = []
        for v in variants:
            key = v.strip().lower()
            if key and key not in seen:
                ordered.append(v.strip())
                seen.add(key)

        return ordered[:max_variants]


class DeepSearchEngine:
    """High-signal search helper powered by the local Playwright browser."""

    def __init__(self, browser: "PlaywrightClient"):
        self.browser = browser

    async def search_once(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Run a single Google search and return structured hits."""
        if not query.strip():
            return []

        encoded = quote_plus(query)
        url = f"https://www.google.com/search?q={encoded}&num={min(max(limit * 2, 10), 20)}&hl=en"
        await self.browser.navigate(url)

        hits: List[Dict[str, Any]] = []
        try:
            await self.browser.page.wait_for_selector("div#search", timeout=5000)
        except Exception:
            logger.debug("Search results container not detected - continuing")

        try:
            serp_data = await self.browser.page.evaluate(
                """() => Array.from(document.querySelectorAll('div#search div.g'))
                    .map((el, idx) => {
                        const link = el.querySelector('a');
                        const titleEl = el.querySelector('h3');
                        const snippetEl = el.querySelector('.VwiC3b, .yXK7lf');
                        if (!link || !titleEl) return null;
                        return {
                            title: titleEl.innerText || '',
                            url: link.href || '',
                            snippet: snippetEl ? snippetEl.innerText : '',
                            position: idx + 1
                        };
                    }).filter(Boolean);"""
            )

            for item in serp_data:
                url_value = item.get("url", "")
                if not url_value or "google." in url_value and "/url?" in url_value:
                    continue
                if url_value.startswith("/"):
                    url_value = f"https://www.google.com{url_value}"
                hits.append(
                    {
                        "title": item.get("title", "").strip(),
                        "url": url_value.strip(),
                        "snippet": item.get("snippet", "").strip(),
                        "position": int(item.get("position", len(hits) + 1)),
                        "captured_at": _now_iso(),
                    }
                )
        except Exception as exc:
            logger.warning(f"SERP extraction failed: {exc}")

        cleaned = []
        seen_urls = set()
        for h in hits:
            url_value = h["url"]
            if not url_value:
                continue
            # Skip Google internal redirects and translation pages
            if "googleusercontent" in url_value or "google.com/sorry" in url_value:
                continue
            normalized = re.sub(r"#.*$", "", url_value)
            if normalized in seen_urls:
                continue
            seen_urls.add(normalized)
            cleaned.append(h)
            if len(cleaned) >= limit:
                break
        return cleaned

    async def deep_search(
        self,
        query: str,
        context: str = "",
        max_queries: int = 3,
        results_per_query: int = 5,
        summarize_top: int = 3,
    ) -> Dict[str, Any]:
        """Run multi-query search with summarization."""
        variants = QueryExpander.expand(query, context=context, max_variants=max_queries)
        if not variants:
            return {"error": "No valid queries provided"}

        aggregated: List[SearchHit] = []
        for idx, variant in enumerate(variants):
            serp_hits = await self.search_once(variant, limit=results_per_query)
            for position, raw in enumerate(serp_hits):
                score = self._score_hit(raw, idx, position)
                aggregated.append(
                    SearchHit(
                        title=raw.get("title", ""),
                        url=raw.get("url", ""),
                        snippet=raw.get("snippet", ""),
                        position=raw.get("position", position + 1),
                        source_query=variant,
                        variant_index=idx,
                        score=score,
                    )
                )

        ranked = self._deduplicate(aggregated)
        if not ranked:
            return {
                "error": "Search returned no usable results",
                "query": query,
                "variants": variants,
                "results": [],
            }

        # Summarize top sources for richer context
        for hit in ranked[: max(1, summarize_top)]:
            summary = await self._summarize_url(hit.url)
            if summary:
                hit.summary = summary.get("summary")
                hit.key_facts = summary.get("key_facts", [])

        serialized = [
            {
                "title": h.title,
                "url": h.url,
                "snippet": h.snippet,
                "position": h.position,
                "score": round(h.score, 3),
                "source_query": h.source_query,
                "summary": h.summary,
                "key_facts": h.key_facts,
            }
            for h in ranked
        ]

        return {
            "success": True,
            "query": query,
            "variants": variants,
            "result_count": len(serialized),
            "results": serialized,
            "generated_at": _now_iso(),
        }

    def _score_hit(self, hit: Dict[str, Any], variant_idx: int, position: int) -> float:
        """Score a search hit based on ranking position and variant priority."""
        base = 1.0 / (position + 1)
        variant_weight = max(0.1, 1.0 - (variant_idx * 0.15))
        snippet_bonus = 0.1 if len(hit.get("snippet") or "") > 120 else 0.0
        return round(base * variant_weight + snippet_bonus, 4)

    def _deduplicate(self, hits: List[SearchHit]) -> List[SearchHit]:
        """Deduplicate hits by URL, keeping the highest scoring entry."""
        unique: Dict[str, SearchHit] = {}
        for hit in hits:
            normalized = re.sub(r"#.*$", "", hit.url)
            existing = unique.get(normalized)
            if not existing or hit.score > existing.score:
                unique[normalized] = hit
        return sorted(unique.values(), key=lambda h: h.score, reverse=True)

    async def _summarize_url(self, url: str) -> Optional[Dict[str, Any]]:
        """Convert page to markdown and summarize it."""
        try:
            md = await self.browser.get_markdown(url)
            if not md or md.get("error"):
                return None
            content = md.get("markdown") or ""
            if not content.strip():
                return None

            from .llm_extractor import LLMExtractor  # Local import to avoid heavy startup

            extractor = LLMExtractor()
            summary = await extractor.summarize(content, style="bullets", max_length=600)
            if not summary.get("success"):
                return None
            data = summary.get("data") or {}
            output = {
                "summary": data.get("summary") or data.get("data") or "",
                "main_topic": data.get("main_topic"),
                "key_facts": data.get("key_facts") or [],
            }
            return output
        except Exception as exc:
            logger.debug(f"Failed to summarize {url}: {exc}")
            return None
