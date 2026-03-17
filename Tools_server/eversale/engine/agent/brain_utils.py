"""
Brain Utilities - Standalone utility functions and mixins for brain_enhanced_v2.py

Provides:
1. Standalone functions: _extract_urls, _strip_urls
2. BrainUtilsMixin: _summarize_markdown
"""

import re
import json
from typing import List, Optional
from loguru import logger


# ============================================================================
# Standalone Utility Functions
# ============================================================================

def _extract_urls(text: str) -> List[str]:
    """Extract URLs or bare domains from text."""
    if not text:
        return []
    pattern = r'(https?://[^\s\'"]+|www\.[^\s\'"]+|\b[a-zA-Z0-9.-]+\.[a-z]{2,}(?:/[^\s\'"]*)?)'
    urls = []
    for match in re.findall(pattern, text):
        url = match.strip()
        # Strip trailing punctuation, but preserve balanced parentheses (for Wikipedia URLs)
        while url and url[-1] in '.,;]':
            url = url[:-1]
        # Only strip trailing ) if unbalanced (more closing than opening)
        while url and url[-1] == ')' and url.count(')') > url.count('('):
            url = url[:-1]
        if not url:
            continue
        if not url.startswith('http://') and not url.startswith('https://'):
            url = 'https://' + url.lstrip('/')
        if url not in urls:
            urls.append(url)
    return urls


def _strip_urls(text: str, urls: List[str]) -> str:
    """Remove URL strings from text to isolate the user's ask."""
    cleaned = text
    for u in urls:
        cleaned = cleaned.replace(u, "")
        bare = u.replace("https://", "").replace("http://", "")
        cleaned = cleaned.replace(bare, "")
    # Clean up orphaned navigation phrases after URL removal
    cleaned = re.sub(r'\b(go to|visit|navigate to|open|browse to)\s+and\b', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\b(go to|visit|navigate to|open|browse to)\s*$', '', cleaned, flags=re.IGNORECASE)
    return re.sub(r'\s+', ' ', cleaned).strip()


# Public aliases (for imports without underscore prefix)
extract_urls = _extract_urls
strip_urls = _strip_urls


# ============================================================================
# Brain Utils Mixin
# ============================================================================

class BrainUtilsMixin:
    """Mixin providing utility methods for brain operations."""

    async def _summarize_markdown(self, markdown: str) -> Optional[str]:
        """Summarize markdown content using fast model directly."""
        if not markdown:
            return None
        try:
            import ollama

            # Truncate content to reduce LLM processing time
            content = markdown[:3000] if len(markdown) > 3000 else markdown

            # Use fast model with simple prompt (no JSON, faster response)
            prompt = f"""Summarize this webpage in 2-3 sentences. Focus on the main topic and key facts.

Content:
{content}

Summary:"""

            response = self.ollama_client.generate(
                model=self.fast_model,
                prompt=prompt,
                options={'temperature': 0.3, 'num_predict': 200}
            )
            summary = response.get('response', '').strip()
            if summary:
                # Clean up any thinking tags from the response
                summary = re.sub(r'<think>.*?</think>', '', summary, flags=re.DOTALL).strip()
                return summary
        except Exception as e:
            logger.debug(f"Fast summary failed: {e}")

        # Fallback to LLM extractor if fast model fails
        try:
            from .llm_extractor import LLMExtractor
            extractor = LLMExtractor(self.config.get('llm', {}))
            result = await extractor.summarize(markdown, style="concise", max_length=400)
            if result.get('success') and result.get('data'):
                data = result['data']
                if isinstance(data, dict):
                    return data.get('summary', str(data)[:400])
                return self._shorten_text(data, 400)
        except Exception as e:
            logger.debug(f"Markdown summary fallback failed: {e}")
        return None
