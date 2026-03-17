"""
Web Shortcuts Module

Fast-path handlers for common web tasks. Extracted from brain_enhanced_v2.py
to reduce file size while maintaining functionality.

This module provides quick shortcuts for:
- Simple questions (math, greetings)
- Search queries (Google, DuckDuckGo)
- Wikipedia lookups
- Site mapping (Firecrawl-style)
- Q&A extraction
- Entity/contact extraction
- General content extraction
"""

import re
import json
import urllib.parse
from typing import Optional, List, Dict, Any, Callable, Awaitable
from loguru import logger


class WebShortcuts:
    """Fast-path web task handler."""

    def __init__(
        self,
        ollama_client,
        fast_model: str,
        browser,
        call_direct_tool: Callable[..., Awaitable],
        extract_urls: Callable[[str], List[str]],
        strip_urls: Callable[[str, List[str]], str],
        shorten_text: Callable[[str, int], str],
        format_extract_output: Callable[[Any, str], str],
        get_site_selectors: Callable[[str], Optional[Dict]],
        summarize_markdown: Callable[[str], Awaitable[Optional[str]]],
        emit_summary: Callable[[str, List[str]], None],
        take_screenshot: Callable[[], Awaitable[bytes]],
        vision_analyze: Callable[[bytes], Awaitable[Dict]],
        vision_model: str,
        stats: Dict,
        describe_mode: bool = False,
    ):
        self.ollama_client = ollama_client
        self.fast_model = fast_model
        self.browser = browser
        self._call_direct_tool = call_direct_tool
        self._extract_urls = extract_urls
        self._strip_urls = strip_urls
        self._shorten_text = shorten_text
        self._format_extract_output = format_extract_output
        self._get_site_selectors = get_site_selectors
        self._summarize_markdown = summarize_markdown
        self._emit_explainable_summary = emit_summary
        self._take_screenshot = take_screenshot
        self._vision_analyze = vision_analyze
        self.vision_model = vision_model
        self.stats = stats
        self.describe_mode = describe_mode

    async def try_shortcuts(self, prompt: str) -> Optional[str]:
        """
        Fast-path for web tasks where the new reader/crawler tools are optimal.
        Triggered when the prompt clearly references a URL with a simple ask.
        """
        lower = prompt.lower()

        # SKIP SHORTCUTS: Multi-step tasks require full ReAct loop
        if self._is_multi_step_task(lower):
            logger.debug(f"Multi-step task detected, skipping shortcuts: {prompt[:50]}...")
            return None

        # FAST PATH 1: Simple questions that don't need browser at all
        urls = self._extract_urls(prompt)

        # FAST PATH 1a: Direct math calculation
        result = self._try_math_calculation(lower, urls)
        if result:
            return result

        # FAST PATH 1b: Simple greetings/jokes
        result = await self._try_simple_response(prompt, lower, urls)
        if result:
            return result

        # FAST PATH 2: Detect invalid URLs early
        result = self._validate_urls(prompt, lower, urls)
        if result:
            return result

        # FAST PATH 3: Search queries
        result = await self._try_search(prompt, lower)
        if result:
            return result

        # FAST PATH 4: Wikipedia
        result = await self._try_wikipedia(prompt, lower, urls)
        if result:
            return result

        # For remaining shortcuts, we need URLs
        if not urls or not self.browser:
            return None

        primary_url = urls[0]
        text_without_urls = self._strip_urls(prompt, urls)
        has_question = "?" in prompt or any(q in lower for q in ["what is", "what are", "who is", "answer"])

        # Site mapping
        result = await self._try_site_map(lower, primary_url)
        if result:
            return result

        # Adaptive crawl
        result = await self._try_crawl(lower, primary_url, text_without_urls)
        if result:
            return result

        # Q&A from page
        if has_question:
            result = await self._try_qa(primary_url, text_without_urls, prompt)
            if result:
                return result

        # Entity extraction
        result = await self._try_entity_extraction(lower, primary_url)
        if result:
            return result

        # General extraction
        result = await self._try_extraction(lower, primary_url, text_without_urls, prompt)
        if result:
            return result

        # Default: markdown summary
        result = await self._try_markdown_summary(lower, primary_url, prompt)
        if result:
            return result

        return None

    def _is_multi_step_task(self, lower: str) -> bool:
        """Detect multi-step tasks that need full ReAct loop."""
        multi_step_indicators = [
            "click on", "click the", "click ", " then ", " after ", " and then ",
            "fill in", "fill out", "fill the", "fill ", " fill", "type in", "enter the",
            "submit", "press the", "select the", "choose the",
            ", then", ", after", ", and ", ", click", ", fill",
            "first ", "second ", "next ", "finally ",
            "login", "log in", "sign in", "sign up",
            " – ", " — ", "–", "—", "\n-", "\n•",
            "produce ", "generate ", "create a", "write a", "memo", "report",
            "summarize", "analyze", "compare", "checklist", "persona", "matrix",
            "buyer", "for each", "pick any", "top 5", "top 3",
            "pages 1", "page 1 through", "page 1-", "pages 1-",
            # Form field names that indicate form filling
            "firstname", "lastname", "username", "password", "useremail", "usernumber",
        ]
        return any(indicator in lower for indicator in multi_step_indicators)

    def _try_math_calculation(self, lower: str, urls: List[str]) -> Optional[str]:
        """Direct math calculation."""
        math_match = re.search(r'(?:what\s+is\s+)?(\d+(?:\s*[\+\-\*\/\%\^]\s*\d+)+)\s*\??', lower)
        if math_match and not urls:
            try:
                expr = math_match.group(1).replace('^', '**')
                result = eval(expr, {"__builtins__": {}}, {})
                answer = f"The answer is {result}."
                self._emit_explainable_summary(answer, [])
                return answer
            except Exception as e:
                logger.debug(f"Math eval failed: {e}")
        return None

    async def _try_simple_response(self, prompt: str, lower: str, urls: List[str]) -> Optional[str]:
        """Handle simple questions that don't need web."""
        simple_triggers = ["joke", "tell me a joke", "hello", "hi there", "hey"]
        is_simple_no_web = (
            not urls and
            len(prompt.split()) < 8 and
            any(t in lower for t in simple_triggers)
        )
        if is_simple_no_web:
            try:
                response = self.ollama_client.generate(
                    model=self.fast_model,
                    prompt=f"Answer briefly: {prompt}",
                    options={'temperature': 0.7, 'num_predict': 100}
                )
                answer = response.get('response', '').strip()
                if answer:
                    self._emit_explainable_summary(answer, [])
                    return answer
            except Exception as e:
                logger.debug(f"Direct answer failed: {e}")
        return None

    def _validate_urls(self, prompt: str, lower: str, urls: List[str]) -> Optional[str]:
        """Validate URLs and return error if invalid.

        Note: Removed overly strict bracket check that was causing false positives
        for legitimate URLs like amazon.com.
        """
        # Only reject truly malformed URLs (e.g. containing literal brackets in domain)
        if urls:
            for url in urls:
                # Skip empty URLs
                if not url or not url.strip():
                    continue
                # Only reject URLs with brackets in the domain part (not path/query)
                try:
                    from urllib.parse import urlparse
                    parsed = urlparse(url)
                    if parsed.netloc and re.search(r'[\[\]\{\}]', parsed.netloc):
                        error_msg = f"Invalid URL detected: {url}"
                        self._emit_explainable_summary(error_msg, [])
                        return error_msg
                except:
                    pass
        return None

    async def _try_search(self, prompt: str, lower: str) -> Optional[str]:
        """Handle search queries."""
        # Pattern matching for search queries
        search_match = re.match(r'^search\s+(?:google|bing|duckduckgo)\s+for\s+["\']?(.+?)["\']?(?:\s+and\s+(.*))?$', lower, re.IGNORECASE)
        if not search_match:
            search_match = re.match(r'^search\s+for\s+["\']?(.+?)["\']?(?:\s+and\s+(.*))?$', lower, re.IGNORECASE)
        if not search_match:
            search_match = re.match(r'^(?:google|bing)\s+(?:for\s+)?["\']?(.+?)["\']?(?:\s+and\s+(.*))?$', lower, re.IGNORECASE)

        # Also handle implicit search questions
        if not search_match:
            question_patterns = [
                r'^what\s+is\s+(?:the\s+)?(?:current\s+)?(.+?)(?:\?|$)',
                r'^(?:tell\s+me|find\s+out)\s+(?:about\s+)?(.+?)(?:\?|$)',
                r'^how\s+(?:much|many)\s+(.+?)(?:\?|$)',
                r'^(?:when|where|who)\s+(?:is|was|are|were)?\s*(.+?)(?:\?|$)',
            ]
            for pat in question_patterns:
                m = re.match(pat, lower, re.IGNORECASE)
                if m:
                    urls_in_prompt = self._extract_urls(prompt)
                    if not urls_in_prompt:
                        search_match = m
                        break

        if not search_match:
            return None

        groups = search_match.groups()
        query = groups[0]
        search_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"

        await self._call_direct_tool("playwright_navigate", {"url": search_url})
        result = await self._call_direct_tool(
            "playwright_extract_structured",
            {
                "item_selector": ".result",
                "field_selectors": {
                    "title": ".result__a",
                    "snippet": ".result__snippet",
                    "url": ".result__url"
                },
                "limit": 8
            }
        )
        if result and not result.get("error") and result.get("data"):
            data = result.get("data")
            formatted = []
            for item in data[:5]:
                title = item.get("title", "").strip()
                snippet = item.get("snippet", "").strip()
                url = item.get("url", "").strip()
                if title:
                    formatted.append(f"**{title}**\n{snippet}\n{url}")
            summary = f"Search results for '{query}':\n\n" + "\n\n".join(formatted)
            self._emit_explainable_summary(summary, [])
            return summary

        # Fallback to LLM extraction
        result = await self._call_direct_tool(
            "playwright_llm_extract",
            {"url": search_url, "prompt": f"Extract search results for: {query}"}
        )
        if result and not result.get("error"):
            data = result.get("data") or result
            summary = self._format_extract_output(data, title=f"Search results for '{query}'")
            self._emit_explainable_summary(summary, [])
            return summary
        return None

    async def _try_wikipedia(self, prompt: str, lower: str, urls: List[str]) -> Optional[str]:
        """Handle Wikipedia requests."""
        if 'wikipedia' not in lower or not self.browser:
            return None

        primary_url = urls[0] if urls else None
        topic = None

        # Extract topic patterns
        wiki_match = re.search(r"(?:summary|article|about)\s+(?:of\s+)?['\"]?([^'\"?]+)['\"]?", prompt, re.IGNORECASE)
        if wiki_match:
            topic = wiki_match.group(1).strip().rstrip('.')
        if not topic:
            quote_match = re.search(r"['\"]([^'\"]+)['\"]", prompt)
            if quote_match:
                topic = quote_match.group(1).strip()
        if not topic:
            get_match = re.search(r"(?:get|find|show|what is)\s+(?:the\s+)?(.+?)(?:\?|$)", prompt, re.IGNORECASE)
            if get_match:
                topic = get_match.group(1).strip().rstrip('.')

        if topic:
            topic = re.sub(r'\s+', ' ', topic).strip()
            wiki_url = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(topic.replace(' ', '_'))}"
        elif primary_url and 'wikipedia.org' in primary_url:
            wiki_url = primary_url
        else:
            wiki_url = "https://en.wikipedia.org"

        result = await self._call_direct_tool("playwright_get_markdown", {"url": wiki_url})
        if result and not result.get("error"):
            markdown = result.get("markdown", "")
            title = result.get("title", topic or "Wikipedia Article")
            paragraphs = [p.strip() for p in markdown.split('\n\n') if p.strip() and len(p.strip()) > 100]
            summary_text = paragraphs[0] if paragraphs else markdown[:1000]
            summary = f"**{title}**\n\n{self._shorten_text(summary_text, 800)}"
            self._emit_explainable_summary(summary, [])
            return summary
        return None

    async def _try_site_map(self, lower: str, primary_url: str) -> Optional[str]:
        """Handle site mapping requests."""
        map_triggers = ["site map", "sitemap", "map the site", "map this site", "list urls", "all urls", "pages on"]
        if not any(t in lower for t in map_triggers):
            return None

        result = await self._call_direct_tool("playwright_map_site", {"url": primary_url, "max_urls": 200})
        if result and not result.get("error"):
            sample = result.get("urls", [])[:8]
            categories = result.get("categorized") or {}
            cat_info = ", ".join(f"{k}:{len(v)}" for k, v in categories.items())
            summary = f"Mapped {result.get('count', len(sample))} URLs for {result.get('base_url', primary_url)} (sitemap: {'found' if result.get('sitemap_found') else 'not found'})."
            if cat_info:
                summary += f" Categories: {cat_info}."
            if sample:
                summary += "\n- " + "\n- ".join(sample)
            self._emit_explainable_summary(summary, [])
            return summary
        return None

    async def _try_crawl(self, lower: str, primary_url: str, text_without_urls: str) -> Optional[str]:
        """Handle crawl requests."""
        crawl_keywords = ["crawl", "sitewide", "across site", "across pages", "entire site"]
        info_hints = ["pricing", "price", "plan", "contact", "contacts", "email", "phone", "faq", "docs", "documentation", "support", "careers", "jobs", "team", "about"]
        wants_crawl = any(k in lower for k in crawl_keywords) or (any(k in lower for k in info_hints) and "site" in lower)

        if not wants_crawl:
            return None

        looking_for = text_without_urls.strip() or "information requested in the prompt"
        result = await self._call_direct_tool(
            "playwright_crawl_for",
            {"url": primary_url, "looking_for": looking_for, "max_pages": 10}
        )
        if result and not result.get("error"):
            content = self._shorten_text(result.get("content", ""), 1200)
            summary = f"Adaptive crawl visited {result.get('pages_visited')} pages (reason: {result.get('stopped_reason', 'complete')})."
            if content:
                summary += f"\n\nKey content:\n{content}"
            self._emit_explainable_summary(summary, [])
            return summary
        return None

    async def _try_qa(self, primary_url: str, text_without_urls: str, prompt: str) -> Optional[str]:
        """Handle Q&A extraction."""
        question_text = text_without_urls.strip() or prompt.strip()
        result = await self._call_direct_tool(
            "playwright_answer_question",
            {"url": primary_url, "question": question_text}
        )
        if result and not result.get("error"):
            data = result.get("data") or result
            answer = data.get("answer") if isinstance(data, dict) else None
            confidence = data.get("confidence") if isinstance(data, dict) else None
            summary = answer or json.dumps(data)[:800]

            # Vision fallback for describe-mode
            if self.describe_mode and (
                not answer or
                "not found" in str(answer).lower() or
                confidence == "low"
            ):
                try:
                    await self._call_direct_tool("playwright_navigate", {"url": primary_url})
                    screenshot = await self._take_screenshot()
                    if screenshot and self.vision_model:
                        vision_result = await self._vision_analyze(screenshot)
                        self.stats['vision_calls'] += 1
                        if vision_result and vision_result.get('raw_summary'):
                            summary = vision_result['raw_summary']
                            confidence = "high (visual)"
                except Exception as e:
                    logger.debug(f"Vision fallback failed: {e}")

            if confidence:
                summary = f"{summary}\nConfidence: {confidence}"
            self._emit_explainable_summary(summary, [])
            return summary
        return None

    async def _try_entity_extraction(self, lower: str, primary_url: str) -> Optional[str]:
        """Handle entity/contact extraction."""
        import re

        # Skip if this is a form fill prompt (contains field names like "userEmail", "firstName", etc)
        form_fill_keywords = ['fill', 'type', 'enter', 'input', 'firstname', 'lastname', 'useremail', 'usernumber', 'username', 'password']
        if any(kw in lower for kw in form_fill_keywords):
            return None

        # Use word boundary matching to avoid matching "email" inside "userEmail"
        entity_triggers = ["email", "emails", "phone", "contact", "contacts", "contact info", "contact information"]
        has_trigger = any(re.search(rf'\b{re.escape(t)}\b', lower) for t in entity_triggers)
        if not has_trigger:
            return None

        entity_types = []
        if re.search(r'\bemail\b', lower) or re.search(r'\bemails\b', lower) or re.search(r'\bcontact\b', lower):
            entity_types.append("email")
        if re.search(r'\bphone\b', lower) or re.search(r'\bcontact\b', lower):
            entity_types.append("phone")
        if re.search(r'\bcompany\b', lower) or re.search(r'\bcontact\b', lower):
            entity_types.append("company")
        if not entity_types:
            entity_types = ["company", "email", "phone"]

        result = await self._call_direct_tool(
            "playwright_extract_entities",
            {"url": primary_url, "entity_types": list(dict.fromkeys(entity_types))}
        )
        if result and not result.get("error"):
            data = result.get("data") or result
            summary = self._format_extract_output(data, title="Entities")
            self._emit_explainable_summary(summary, [])
            return summary
        return None

    async def _try_extraction(self, lower: str, primary_url: str, text_without_urls: str, prompt: str) -> Optional[str]:
        """Handle general extraction requests."""
        extract_triggers = ["extract", "pull", "list", "scrape"]
        wants_extract = any(t in lower for t in extract_triggers)

        if not wants_extract:
            return None

        # Try CSS selector extraction for known sites
        site_selectors = self._get_site_selectors(primary_url)
        if site_selectors:
            await self._call_direct_tool("playwright_navigate", {"url": primary_url})
            result = await self._call_direct_tool("playwright_extract_structured", site_selectors)
            if result and not result.get("error") and result.get("data"):
                data = result.get("data")
                summary = self._format_extract_output(data, title="Extracted data (CSS)")
                self._emit_explainable_summary(summary, [])
                return summary

        # Try fast extraction
        extraction_prompt = text_without_urls.strip() or prompt.strip()
        result = await self._call_direct_tool(
            "playwright_fast_extract",
            {"url": primary_url, "prompt": extraction_prompt}
        )
        if result and not result.get("error") and result.get("data"):
            data = result.get("data")
            method = result.get("method", "unknown")
            time_ms = result.get("time_ms", 0)
            title = f"Extracted data ({method}, {time_ms}ms)"
            summary = self._format_extract_output(data, title=title)
            self._emit_explainable_summary(summary, [])
            return summary

        # Fallback to LLM extraction
        result = await self._call_direct_tool(
            "playwright_llm_extract",
            {"url": primary_url, "prompt": extraction_prompt}
        )
        if result and not result.get("error"):
            data = result.get("data") or result
            summary = self._format_extract_output(data, title="Extracted data")
            self._emit_explainable_summary(summary, [])
            return summary
        return None

    async def _try_markdown_summary(self, lower: str, primary_url: str, prompt: str) -> Optional[str]:
        """Default: clean markdown + short summary."""
        summary_triggers = ["summarize", "summary", "markdown", "what does this page say", "read this", "article", "content"]
        nav_triggers = ["navigate", "go to", "visit", "open", "browse", "what you see", "tell me", "show me", "list", "find", "get"]
        extract_triggers = ["extract", "pull", "list", "scrape"]

        is_nav_request = any(t in lower for t in nav_triggers)
        is_simple_ask = len(prompt.split()) <= 12
        wants_extract = any(t in lower for t in extract_triggers)

        if not (wants_extract or any(t in lower for t in summary_triggers) or is_nav_request or is_simple_ask):
            return None

        result = await self._call_direct_tool("playwright_get_markdown", {"url": primary_url})
        if result and not result.get("error"):
            markdown = result.get("markdown", "")
            title = result.get("title") or result.get("url", primary_url)
            short_summary = await self._summarize_markdown(markdown)
            if short_summary:
                summary = f"{title}\n{short_summary}"
            else:
                summary = f"{title}\n\n{self._shorten_text(markdown, 1200)}"
            self._emit_explainable_summary(summary, [])
            return summary
        return None
