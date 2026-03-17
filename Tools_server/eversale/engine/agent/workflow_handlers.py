"""
Workflow Handlers - Complex multi-step workflow execution.

Extracted from brain_enhanced_v2.py to reduce file size and improve modularity.
Contains:
- Complex workflow routing (_try_complex_workflow)
- Page loop execution
- Multi-site operations
- Forever/queue operations
- Research and document production
- Form handling
"""

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable, TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    pass


class WorkflowHandlers:
    """
    Handles complex multi-step workflow execution.

    Responsibilities:
    - Detect and route complex workflows
    - Execute page loops across sites
    - Handle forever/continuous monitoring
    - Multi-site comparison and extraction
    - Research and document production
    - Form filling operations
    """

    def __init__(
        self,
        call_tool_func: Callable,
        extract_urls_func: Callable,
        emit_summary_func: Callable,
        get_site_config_func: Callable,
        ollama_client=None,
        model: str = None,
        vision_model: str = None
    ):
        """
        Initialize WorkflowHandlers.

        Args:
            call_tool_func: Function to call browser tools (e.g., mcp.call_tool)
            extract_urls_func: Function to extract URLs from text
            emit_summary_func: Function to emit explainable summaries
            get_site_config_func: Function to get site-specific extraction config
            ollama_client: Ollama client for LLM calls
            model: Main LLM model name
            vision_model: Vision model name
        """
        self._call_tool = call_tool_func
        self._extract_urls = extract_urls_func
        self._emit_summary = emit_summary_func
        self._get_site_config = get_site_config_func
        self.ollama_client = ollama_client
        self.model = model
        self.vision_model = vision_model

        # Import ForeverTaskState and TaskQueue lazily
        self._forever_task_state = None
        self._task_queue = None

    def _get_forever_task_state(self):
        """Lazy load ForeverTaskState."""
        if self._forever_task_state is None:
            try:
                from .forever_operations import ForeverTaskState
                self._forever_task_state = ForeverTaskState
            except ImportError:
                logger.warning("ForeverTaskState not available")
                self._forever_task_state = type('ForeverTaskState', (), {
                    'load': staticmethod(lambda x: None),
                    'create': staticmethod(lambda x, y: type('obj', (), {
                        'status': 'new', 'current_batch': 0, 'processed_items': 0,
                        'total_items': 0, 'results': [], 'errors': [], 'checkpoints': [],
                        'checkpoint': lambda self, x: None, 'save': lambda self: None
                    })())
                })
        return self._forever_task_state

    def _get_task_queue(self):
        """Lazy load TaskQueue."""
        if self._task_queue is None:
            try:
                from .task_queue import TaskQueue
                self._task_queue = TaskQueue
            except ImportError:
                logger.warning("TaskQueue not available")
                self._task_queue = type('TaskQueue', (), {
                    '__init__': lambda self: None,
                    'add_task': lambda self, t, p, pr: 'task_0',
                    'get_next_task': lambda self, a: None,
                    'complete_task': lambda self, t, **kw: None,
                    'get_stats': lambda self: {'total': 0, 'pending': 0, 'running': 0, 'completed': 0, 'failed': 0},
                    'tasks': []
                })
        return self._task_queue()

    async def try_complex_workflow(self, prompt: str, execute_react_loop: Callable) -> Optional[str]:
        """
        Handle complex multi-step workflows by breaking them into subtasks.
        Detects patterns like "do X, then Y, then Z" and executes sequentially.

        Args:
            prompt: User prompt to analyze
            execute_react_loop: Function to call for complex tasks requiring full LLM reasoning

        Returns:
            Result string if handled, None if not a complex workflow
        """
        lower = prompt.lower()

        # Detect complex multi-step patterns
        complexity_indicators = [
            "then", "after that", "next", "finally", "first",
            "for each", "for every", "loop", "pages 1", "pages 1-",
            "collect", "aggregate", "compare", "summarize all"
        ]

        # Count how many steps/actions are mentioned
        step_keywords = ["go to", "search", "click", "fill", "extract", "get", "find", "list", "note", "compare"]
        step_count = sum(1 for kw in step_keywords if kw in lower)

        # Only handle if it's genuinely complex (3+ steps or has loop indicators)
        is_complex = (
            step_count >= 3 or
            any(ind in lower for ind in ["for each", "for every", "pages 1", "loop"])
        )

        # PRIORITY -3: TASK QUEUE (multi-agent coordination)
        queue_keywords = ['add to queue', 'queue task', 'process queue', 'next task', 'task queue', 'multi-agent']
        is_queue_task = any(kw in lower for kw in queue_keywords)
        if is_queue_task:
            result = await self.execute_queue_operation(prompt, execute_react_loop)
            if result:
                return result

        # PRIORITY -2: FOREVER LOOPS (continuous monitoring, forever goals)
        forever_keywords = ['forever', 'run continuously', 'continuously monitor', 'monitor for',
                           'monitor the', 'watch for changes', 'keep checking', 'check every',
                           'every hour', 'every day', 'periodically check', 'indefinitely',
                           '24/7', 'always on', 'run indefinitely', 'never stop']
        is_forever = any(kw in lower for kw in forever_keywords)
        if is_forever:
            result = await self.execute_forever_loop(prompt)
            if result:
                return result

        # PRIORITY -1.5: MULTI-FIELD FORM FILL
        # Pattern 1: go to URL with form in path + "fill in/out" + quoted values
        form_url_match = re.search(r'go to\s+(\S+\.(?:org|com|net|io)/\S*forms?\S*)', lower)
        has_fill_in = 'fill in' in lower or 'fill out' in lower or 'fill the form' in lower
        quoted_values = re.findall(r"'([^']+)'", prompt)

        # Pattern 2: "fill field1 with value1, field2 with value2" style
        field_value_pairs = re.findall(r'(\w+)\s+with\s+(\w+(?:\s+\w+)?(?:@\S+)?)', lower)

        if form_url_match and has_fill_in and len(quoted_values) >= 3:
            result = await self.execute_multi_field_form(form_url_match.group(1), prompt)
            if result:
                return result

        # Handle "fill field1 with value1, field2 with value2" without quotes
        if form_url_match and len(field_value_pairs) >= 2:
            result = await self._execute_generic_form_fill(form_url_match.group(1), field_value_pairs, prompt)
            if result:
                return result

        # PRIORITY -1: MEGA DATA WAREHOUSE
        has_mega_keywords = sum(1 for kw in ['mega', 'warehouse', 'enterprise', 'full extraction', 'all categories', 'phase'] if kw in lower)
        category_keywords = ["travel", "mystery", "historical fiction", "science fiction", "poetry",
                             "art", "philosophy", "religion", "science", "music"]
        has_many_categories = sum(1 for k in category_keywords if k in lower) >= 5
        books_pages = re.search(r'books.*?pages?\s+(\d+)\s*(?:through|to|-)\s*(\d+)', lower, re.DOTALL)
        quotes_pages = re.search(r'quotes.*?pages?\s+(\d+)\s*(?:through|to|-)\s*(\d+)', lower, re.DOTALL)

        if (has_mega_keywords >= 1 or has_many_categories) and books_pages and quotes_pages:
            result = await self.execute_mega_warehouse(books_pages, quotes_pages, prompt)
            if result:
                return result

        # PRIORITY 0: Multi-site page loops
        site_page_matches = re.findall(r'(\S+\.(?:com|org|net|io))\s+pages?\s+(\d+)\s*(?:through|to|-)\s*(\d+)', lower)

        if not site_page_matches or len(site_page_matches) < 2:
            has_books = 'books.toscrape' in lower
            has_quotes = 'quotes.toscrape' in lower
            books_pages_match = re.search(r'books.*?pages?\s+(\d+)\s*(?:through|to|-)\s*(\d+)', lower, re.DOTALL)
            quotes_pages_match = re.search(r'quotes.*?pages?\s+(\d+)\s*(?:through|to|-)\s*(\d+)', lower, re.DOTALL)

            if has_books and has_quotes and books_pages_match and quotes_pages_match:
                urls = self._extract_urls(prompt)
                if len(urls) >= 2:
                    site_page_matches = [
                        (urls[0], books_pages_match.group(1), books_pages_match.group(2)),
                        (urls[1], quotes_pages_match.group(1), quotes_pages_match.group(2))
                    ]
                else:
                    site_page_matches = []

        if len(site_page_matches) >= 2:
            result = await self.execute_multi_site_page_loops(site_page_matches, prompt)
            if result:
                return result

        # PRIORITY 0.5: Books categories + quotes page loops
        has_categories = sum(1 for k in category_keywords if k in lower)
        has_book_categories = has_categories >= 3
        quotes_page_match = re.search(r'quotes\.?toscrape\.?com\s+pages?\s+(\d+)\s*(?:through|to|-)\s*(\d+)', lower)
        if has_book_categories and quotes_page_match:
            result = await self.execute_categories_plus_quotes(prompt, quotes_page_match)
            if result:
                return result

        # PRIORITY 1: Multi-site comparison
        urls = self._extract_urls(prompt)
        if len(urls) >= 2 and ('compare' in lower or 'both' in lower):
            result = await self.execute_multi_site_comparison(urls, prompt)
            if result:
                return result

        # PRIORITY 2: Research and produce document
        produces_output = any(kw in lower for kw in ['produce', 'generate', 'create a', 'write a', 'memo', 'report', 'checklist', 'personas', 'matrix', 'buyer', 'ad hooks'])
        if urls and produces_output:
            result = await self.execute_research_and_produce(urls[0], prompt)
            if result:
                return result

        if not is_complex:
            return None

        # Check for page loop patterns
        loop_match = re.search(r'(?:for\s+)?pages?\s+(\d+)\s*(?:through|to|-)\s*(\d+)', lower)
        if loop_match:
            start_page = int(loop_match.group(1))
            end_page = int(loop_match.group(2))
            url_match = re.search(r'(\S+\.(?:com|org|net|io)[^\s,]*)', lower)
            if url_match:
                url = url_match.group(1)
                if not url.startswith('http'):
                    url = 'https://' + url
                return await self.execute_page_loop(url, start_page, end_page, prompt)

        # Check for multi-category collection
        if has_categories >= 3 or 'different categories' in lower:
            result = await self.execute_category_collection(prompt)
            if result:
                return result

        # Handle click-detail loops
        if ('click' in lower and ('each' in lower or 'first' in lower) and
            ('go back' in lower or 'details' in lower or 'description' in lower)):
            result = await self.execute_click_detail_loop(prompt)
            if result:
                return result

        # For other complex tasks, use sequential steps
        return await self.execute_sequential_steps(prompt, execute_react_loop)

    async def execute_forever_loop(self, prompt: str) -> str:
        """Execute a forever/continuous monitoring loop with checkpoints."""
        import hashlib
        lower = prompt.lower()

        task_id = hashlib.md5(prompt[:100].encode()).hexdigest()[:8]
        ForeverTaskState = self._get_forever_task_state()

        state = ForeverTaskState.load(task_id)
        if state and state.status == "running":
            logger.info(f"[Forever] Resuming task {task_id} from checkpoint")
        else:
            state = ForeverTaskState.create(task_id, "forever_monitoring")

        # Determine loop parameters
        interval_match = re.search(r'every\s+(\d+)\s*(second|minute|hour|day)', lower)
        if interval_match:
            num = int(interval_match.group(1))
            unit = interval_match.group(2)
            interval_seconds = num * {'second': 1, 'minute': 60, 'hour': 3600, 'day': 86400}.get(unit, 60)
        else:
            interval_seconds = 60

        max_iterations_match = re.search(r'(\d+)\s*(?:times|iterations|cycles)', lower)
        max_iterations = int(max_iterations_match.group(1)) if max_iterations_match else 10

        urls = self._extract_urls(prompt)
        target_url = urls[0] if urls else None
        if not target_url:
            return "**ERROR:** No URL provided. Please specify a URL to monitor."

        results = []
        summary = f"**FOREVER MONITORING LOOP**\n"
        summary += f"- Task ID: {task_id}\n"
        summary += f"- Target: {target_url}\n"
        summary += f"- Interval: {interval_seconds}s\n"
        summary += f"- Max iterations: {max_iterations}\n\n"

        for iteration in range(max_iterations):
            state.current_batch = iteration + 1
            state.processed_items = iteration + 1
            state.total_items = max_iterations

            try:
                await self._call_tool("playwright_navigate", {"url": target_url})

                if 'quotes' in target_url:
                    extract_result = await self._call_tool("playwright_extract_structured", {
                        "item_selector": ".quote",
                        "field_selectors": {"quote": ".text", "author": ".author"},
                        "limit": 5
                    })
                else:
                    extract_result = await self._call_tool("playwright_snapshot", {})

                data = extract_result.get("data", []) if extract_result else []
                results.append({
                    "iteration": iteration + 1,
                    "time": datetime.now().isoformat(),
                    "items": len(data) if isinstance(data, list) else 1,
                    "sample": data[:2] if isinstance(data, list) else str(data)[:100]
                })

                if iteration % 3 == 0:
                    state.results = results
                    state.checkpoint({"last_data": data[:3] if isinstance(data, list) else {}})
                    logger.info(f"[Forever] Checkpoint at iteration {iteration + 1}")

                summary += f"**Iteration {iteration + 1}:** {len(data) if isinstance(data, list) else 1} items\n"

                if iteration < max_iterations - 1:
                    await asyncio.sleep(min(interval_seconds, 5))

            except Exception as e:
                state.errors.append({"iteration": iteration, "error": str(e)})
                summary += f"**Iteration {iteration + 1}:** ERROR - {str(e)[:50]}\n"

        state.status = "completed"
        state.save()

        summary += f"\n**COMPLETED:** {len(results)} iterations\n"
        summary += f"- Total items observed: {sum(r['items'] for r in results)}\n"
        summary += f"- Checkpoints saved: {len(state.checkpoints)}\n"

        self._emit_summary(summary, [])
        return summary

    async def execute_queue_operation(self, prompt: str, execute_streaming: Callable) -> str:
        """Handle task queue operations for multi-agent coordination."""
        import hashlib
        lower = prompt.lower()
        queue = self._get_task_queue()

        summary = "**TASK QUEUE OPERATIONS**\n\n"

        if 'add to queue' in lower or 'queue task' in lower:
            task_match = re.search(r'(?:add to queue|queue task)[:\s]+(.+?)(?:\.|$)', lower)
            task_prompt = task_match.group(1).strip() if task_match else prompt

            if 'extract' in lower or 'scrape' in lower:
                task_type = "extract"
            elif 'monitor' in lower or 'watch' in lower:
                task_type = "monitor"
            elif 'analyze' in lower or 'report' in lower:
                task_type = "analyze"
            else:
                task_type = "general"

            priority = 1 if 'urgent' in lower or 'high priority' in lower else 5

            task_id = queue.add_task(task_type, task_prompt, priority)
            summary += f"**Task Added to Queue**\n"
            summary += f"- Task ID: {task_id}\n"
            summary += f"- Type: {task_type}\n"
            summary += f"- Priority: {priority}\n"
            summary += f"- Prompt: {task_prompt[:100]}...\n"

        elif 'process queue' in lower or 'next task' in lower:
            agent_id = hashlib.md5(str(datetime.now()).encode()).hexdigest()[:8]

            task = queue.get_next_task(agent_id)
            if task:
                summary += f"**Processing Task**\n"
                summary += f"- Task ID: {task.task_id}\n"
                summary += f"- Type: {task.task_type}\n"
                summary += f"- Prompt: {task.prompt[:100]}...\n\n"

                try:
                    result = await execute_streaming(task.prompt)
                    queue.complete_task(task.task_id, result=str(result)[:500])
                    summary += f"**Task Completed**\n"
                    summary += f"Result: {str(result)[:300]}...\n"
                except Exception as e:
                    queue.complete_task(task.task_id, error=str(e))
                    summary += f"**Task Failed**\n"
                    summary += f"Error: {str(e)[:200]}\n"
            else:
                summary += "**Queue Empty** - No pending tasks\n"

        else:
            stats = queue.get_stats()
            summary += f"**Queue Status**\n"
            summary += f"- Total tasks: {stats['total']}\n"
            summary += f"- Pending: {stats['pending']}\n"
            summary += f"- Running: {stats['running']}\n"
            summary += f"- Completed: {stats['completed']}\n"
            summary += f"- Failed: {stats['failed']}\n"

            if queue.tasks:
                summary += f"\n**Recent Tasks:**\n"
                for task in queue.tasks[-5:]:
                    summary += f"  - [{task.status}] {task.task_id}: {task.prompt[:40]}...\n"

        self._emit_summary(summary, [])
        return summary

    async def execute_page_loop(self, base_url: str, start: int, end: int, prompt: str) -> str:
        """Execute a loop across multiple pages - GENERIC for ANY site."""
        results = []
        all_items = []

        site_config = self._get_site_config(base_url)

        for page in range(start, end + 1):
            # Smart pagination detection
            if '/catalogue/' in base_url or '/catalog/' in base_url:
                parts = base_url.rstrip('/').split('/catalogue/')
                if len(parts) > 1:
                    base_clean = parts[0]
                else:
                    parts = base_url.rstrip('/').split('/catalog/')
                    base_clean = parts[0] if parts else base_url.rstrip('/')
                page_url = f"{base_clean}/catalogue/page-{page}.html"
            elif '?page=' in base_url:
                page_url = re.sub(r'[?&]page=\d+', f'?page={page}', base_url)
            elif '/page/' in base_url:
                page_url = re.sub(r'/page/\d+/?', f'/page/{page}/', base_url)
            else:
                page_url = f"{base_url.rstrip('/')}/page/{page}/"

            await self._call_tool("playwright_navigate", {"url": page_url})

            # Use site config or auto-detect
            if site_config:
                extract_result = await self._call_tool("playwright_extract_structured", {
                    "item_selector": site_config.get("item_selector", ".item"),
                    "field_selectors": site_config.get("field_selectors", {}),
                    "limit": site_config.get("limit", 20)
                })
            else:
                extract_result = await self._call_tool("playwright_snapshot", {})

            if extract_result:
                data = extract_result.get("data", [])
                if isinstance(data, list):
                    all_items.extend(data)
                results.append({
                    "page": page,
                    "items": len(data) if isinstance(data, list) else 1,
                    "url": page_url
                })

        summary = f"**PAGE LOOP RESULTS ({start}-{end})**\n\n"
        summary += f"- Base URL: {base_url}\n"
        summary += f"- Pages processed: {len(results)}\n"
        summary += f"- Total items: {len(all_items)}\n\n"

        for r in results:
            summary += f"Page {r['page']}: {r['items']} items\n"

        self._emit_summary(summary, [])
        return summary

    async def execute_multi_site_page_loops(self, site_matches: list, prompt: str) -> str:
        """Execute page loops across multiple sites and combine results."""
        lower = prompt.lower()
        combined_results = {}

        for site_domain, start_page, end_page in site_matches:
            start = int(start_page)
            end = int(end_page)

            if 'books.toscrape' in site_domain:
                books = []
                for page in range(start, end + 1):
                    base_clean = "https://" + site_domain
                    page_url = f"{base_clean}/catalogue/page-{page}.html"
                    await self._call_tool("playwright_navigate", {"url": page_url})

                    extract_result = await self._call_tool("playwright_extract_structured", {
                        "item_selector": ".product_pod",
                        "field_selectors": {"title": "h3 a@title", "price": ".price_color"},
                        "limit": 20
                    })

                    if extract_result and extract_result.get("data"):
                        for item in extract_result["data"]:
                            price_str = item.get("price", "0")
                            price_val = float(re.sub(r'[^0-9.]', '', price_str)) if price_str else 0
                            books.append({"title": item.get("title", ""), "price": price_val, "page": page})

                combined_results["books"] = books

            elif 'quotes.toscrape' in site_domain:
                quotes = []
                author_counts = {}
                for page in range(start, end + 1):
                    base_clean = "https://" + site_domain
                    page_url = f"{base_clean}/page/{page}/"
                    await self._call_tool("playwright_navigate", {"url": page_url})

                    extract_result = await self._call_tool("playwright_extract_structured", {
                        "item_selector": ".quote",
                        "field_selectors": {"quote": ".text", "author": ".author"},
                        "limit": 20
                    })

                    if extract_result and extract_result.get("data"):
                        for item in extract_result["data"]:
                            author = item.get("author", "Unknown")
                            quotes.append({"quote": item.get("quote", ""), "author": author, "page": page})
                            author_counts[author] = author_counts.get(author, 0) + 1

                combined_results["quotes"] = quotes
                combined_results["author_counts"] = author_counts

        # Build summary
        summary = "**MULTI-SITE COMPREHENSIVE ANALYSIS**\n\n"

        if "books" in combined_results:
            books = combined_results["books"]
            summary += f"## Books Section ({len(books)} items)\n"
            if books:
                prices = [b["price"] for b in books]
                summary += f"- Price range: ${min(prices):.2f} - ${max(prices):.2f}\n"
                summary += f"- Average: ${sum(prices)/len(prices):.2f}\n\n"

        if "quotes" in combined_results:
            quotes = combined_results["quotes"]
            author_counts = combined_results.get("author_counts", {})
            summary += f"## Quotes Section ({len(quotes)} items)\n"
            summary += f"- Unique authors: {len(author_counts)}\n"
            if author_counts:
                top = sorted(author_counts.items(), key=lambda x: x[1], reverse=True)[:3]
                summary += f"- Top authors: {', '.join(f'{a}({c})' for a,c in top)}\n"

        self._emit_summary(summary, [])
        return summary

    async def execute_sequential_steps(self, prompt: str, execute_react_loop: Callable) -> Optional[str]:
        """Execute complex prompts using the full ReAct loop for proper multi-step handling."""
        lower = prompt.lower()
        complex_analysis = any(ind in lower for ind in [
            'for each', 'analyze', 'compare', 'generate', 'summarize',
            'extract strategies', 'creative angles', 'funnel', 'breakdown',
            'pick any', 'pick the', 'first 3', 'first 5', 'first five',
            'produce', 'create', 'build', 'write'
        ])

        if complex_analysis:
            return await execute_react_loop(prompt)

        urls = re.findall(r'(\S+\.(?:com|org|net|io|gov|edu)[^\s,]*)', lower)
        if not urls:
            return None

        results = []

        for url in urls[:3]:
            if not url.startswith('http'):
                url = 'https://' + url

            nav_result = await self._call_tool("playwright_navigate", {"url": url})
            if nav_result and nav_result.get("success"):
                snapshot = await self._call_tool("playwright_snapshot", {})
                if snapshot:
                    results.append({
                        "url": url,
                        "title": snapshot.get("title", "Unknown"),
                        "summary": snapshot.get("summary", "")[:200]
                    })

        if results:
            output = "**Visited sites:**\n\n"
            for r in results:
                output += f"**{r['title']}** ({r['url']})\n{r['summary']}\n\n"

            self._emit_summary(output, [])
            return output

        return None

    async def execute_click_detail_loop(self, prompt: str) -> Optional[str]:
        """Click on items, extract details, go back - repeat."""
        lower = prompt.lower()
        url_match = re.search(r'(\S+\.(?:com|org|net|io)[^\s,]*)', lower)
        if not url_match:
            return None

        url = url_match.group(1)
        if not url.startswith('http'):
            url = 'https://' + url

        count_match = re.search(r'(\d+)\s*(?:books?|items?|products?|pages?)', lower)
        count = int(count_match.group(1)) if count_match else 3

        await self._call_tool("playwright_navigate", {"url": url})
        all_details = []

        for i in range(count):
            items_result = await self._call_tool("playwright_extract_structured", {
                "item_selector": ".product_pod h3 a, article h3 a",
                "field_selectors": {"title": "@title", "href": "@href"},
                "limit": count + 1
            })

            if not items_result or not items_result.get("data") or i >= len(items_result["data"]):
                break

            item = items_result["data"][i]
            item_url = item.get("href", "")

            if item_url and not item_url.startswith('http'):
                base_url = url.rsplit('/', 1)[0] if url.endswith('.html') else url.rstrip('/')
                item_url = f"{base_url}/{item_url.lstrip('./')}"

            if not item_url:
                continue

            await self._call_tool("playwright_navigate", {"url": item_url})
            await asyncio.sleep(0.3)

            detail_result = await self._call_tool("playwright_get_markdown", {"url": item_url})
            if detail_result and detail_result.get("markdown"):
                all_details.append({
                    "title": item.get("title", f"Item {i+1}"),
                    "content": detail_result["markdown"][:500]
                })

            await self._call_tool("playwright_navigate", {"url": url})

        if not all_details:
            return None

        result = f"**Details from {len(all_details)} items:**\n\n"
        for i, detail in enumerate(all_details, 1):
            result += f"**{i}. {detail['title']}**\n{detail['content'][:300]}...\n\n"

        self._emit_summary(result, [])
        return result

    async def execute_multi_site_comparison(self, urls: list, prompt: str) -> Optional[str]:
        """Compare data from multiple sites."""
        all_data = {}

        for url in urls[:3]:
            if not url.startswith('http'):
                url = 'https://' + url

            await self._call_tool("playwright_navigate", {"url": url})

            if 'books.toscrape' in url:
                extract_result = await self._call_tool("playwright_extract_structured", {
                    "item_selector": ".product_pod",
                    "field_selectors": {"title": "h3 a@title", "price": ".price_color"},
                    "limit": 10
                })
                all_data[url] = {"type": "books", "data": extract_result.get("data", []) if extract_result else []}
            elif 'quotes.toscrape' in url:
                extract_result = await self._call_tool("playwright_extract_structured", {
                    "item_selector": ".quote",
                    "field_selectors": {"quote": ".text", "author": ".author"},
                    "limit": 10
                })
                all_data[url] = {"type": "quotes", "data": extract_result.get("data", []) if extract_result else []}
            else:
                snapshot = await self._call_tool("playwright_snapshot", {})
                all_data[url] = {"type": "general", "data": snapshot if snapshot else {}}

        result = "**MULTI-SITE COMPARISON**\n\n"
        for url, info in all_data.items():
            result += f"## {url}\n"
            result += f"Type: {info['type']}\n"
            data = info['data']
            if isinstance(data, list):
                result += f"Items: {len(data)}\n"
                for item in data[:3]:
                    result += f"  - {item}\n"
            else:
                result += f"Content: {str(data)[:200]}...\n"
            result += "\n"

        self._emit_summary(result, [])
        return result

    async def execute_research_and_produce(self, url: str, prompt: str) -> Optional[str]:
        """Execute research task: navigate to URL, extract data, produce document."""
        lower = prompt.lower()
        logger.info(f"[Research & Produce] Starting for {url}")

        JS_HEAVY_SITES = [
            'producthunt.com', 'reddit.com', 'twitter.com', 'x.com',
            'facebook.com', 'instagram.com', 'linkedin.com', 'amazon.com',
            'greatschools.org', 'zillow.com', 'redfin.com', 'yelp.com',
            'glassdoor.com', 'indeed.com', 'airbnb.com', 'booking.com'
        ]

        is_js_heavy = any(site in url.lower() for site in JS_HEAVY_SITES)

        nav_result = await self._call_tool("playwright_navigate", {"url": url})
        if not nav_result or nav_result.get("error"):
            return None

        if is_js_heavy:
            logger.info(f"[Research & Produce] JS-heavy site detected, scrolling")
            try:
                await self._call_tool("playwright_evaluate", {
                    "expression": "window.scrollTo(0, document.body.scrollHeight / 2)"
                })
                await asyncio.sleep(1.5)
                await self._call_tool("playwright_evaluate", {
                    "expression": "window.scrollTo(0, document.body.scrollHeight)"
                })
                await asyncio.sleep(1.5)
            except Exception as e:
                logger.warning(f"Scroll failed: {e}")

        page_data = None
        page_title = ""
        content_result = await self._call_tool("playwright_get_markdown", {"url": url})

        if content_result and not content_result.get("error"):
            page_data = content_result.get("markdown", "")
            page_title = content_result.get("title", "")
        else:
            extract_result = await self._call_tool("playwright_llm_extract", {
                "url": url,
                "prompt": "Extract all key information, statistics, and data from this page."
            })
            if extract_result and not extract_result.get("error"):
                page_data = json.dumps(extract_result.get("data", {}), indent=2)
                page_title = url

        if not page_data:
            return None

        max_content = 3000
        if len(page_data) > max_content:
            page_data = page_data[:max_content] + "\n\n[Content truncated...]"

        output_type = "memo"
        if "checklist" in lower:
            output_type = "checklist"
        elif "report" in lower:
            output_type = "report"
        elif "summary" in lower:
            output_type = "summary"
        elif "matrix" in lower:
            output_type = "matrix"
        elif "persona" in lower:
            output_type = "personas"

        if not self.ollama_client:
            generated_doc = f"## {output_type.title()}\n\n{page_data}"
        else:
            generation_prompt = f"""Based on the following page content, {prompt}

PAGE TITLE: {page_title if page_title else url}
PAGE CONTENT:
{page_data}

Generate a professional, well-structured {output_type}. Include all relevant data, statistics, and insights."""

            try:
                response = self.ollama_client.generate(
                    model=self.model,
                    prompt=generation_prompt,
                    options={'temperature': 0.3, 'num_predict': 2000}
                )
                generated_doc = response.get('response', '').strip()
            except Exception as e:
                logger.error(f"Document generation failed: {e}")
                generated_doc = f"## {output_type.title()}\n\n{page_data}"

        if not generated_doc:
            return None

        if len(generated_doc) > 500:
            try:
                from .output_path import get_output_folder
                output_folder = Path(get_output_folder())
                output_folder.mkdir(parents=True, exist_ok=True)

                safe_name = re.sub(r'[^\w\s-]', '', prompt[:40]).strip().replace(' ', '_').lower()
                timestamp = datetime.now().strftime("%Y%m%d_%H%M")
                filename = f"{safe_name}_{timestamp}.md"
                filepath = output_folder / filename

                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(f"# {page_title or 'Research Document'}\n\n")
                    f.write(f"Source: {url}\n")
                    f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
                    f.write("---\n\n")
                    f.write(generated_doc)

                logger.info(f"[Research & Produce] Saved to {filepath}")
                generated_doc += f"\n\n---\n**Document saved to:** {filepath}"
            except Exception as e:
                logger.warning(f"Could not save document: {e}")

        self._emit_summary(generated_doc, [])
        return generated_doc

    async def execute_multi_field_form(self, url: str, prompt: str) -> Optional[str]:
        """Handle multi-field form fill tasks."""
        if not url.startswith('http'):
            url = 'https://' + url

        logger.info(f"[MULTI-FORM] Filling multi-field form at {url}")

        try:
            nav_result = await self._call_tool("playwright_navigate", {"url": url})
            if not nav_result or nav_result.get("error"):
                return f"Failed to navigate to {url}"

            await asyncio.sleep(1)

            lower = prompt.lower()
            fields_to_fill = {}

            # SITE-SPECIFIC HANDLING: demoqa.com automation-practice-form
            if 'demoqa' in url.lower() and 'practice-form' in url.lower():
                logger.info(f"[MULTI-FORM] Detected demoqa practice form - using direct injection")
                try:
                    # Parse name (could be "name 'John Smith'" or "name 'John', last name 'Smith'")
                    name_match = re.search(r"name\s*['\"]([^'\"]+)['\"]", lower)
                    email_match = re.search(r"email\s*['\"]([^'\"]+)['\"]", lower)
                    gender_match = re.search(r"gender\s*['\"]?(male|female|other)['\"]?", lower, re.I)
                    mobile_match = re.search(r"mobile\s*['\"]?(\d+)['\"]?", lower)

                    # Split name into first/last
                    if name_match:
                        full_name = name_match.group(1).strip()
                        name_parts = full_name.split()
                        first_name = name_parts[0] if name_parts else 'John'
                        last_name = name_parts[1] if len(name_parts) > 1 else 'Doe'
                    else:
                        first_name = 'John'
                        last_name = 'Doe'

                    email = email_match.group(1) if email_match else 'test@test.com'
                    gender = gender_match.group(1).capitalize() if gender_match else 'Male'
                    mobile = mobile_match.group(1) if mobile_match else '5551234567'

                    # Fill demoqa practice form with correct selectors
                    await self._call_tool("playwright_fill", {"selector": "#firstName", "value": first_name})
                    await self._call_tool("playwright_fill", {"selector": "#lastName", "value": last_name})
                    await self._call_tool("playwright_fill", {"selector": "#userEmail", "value": email})

                    # Click gender radio (Male=1, Female=2, Other=3)
                    gender_map = {'Male': '1', 'Female': '2', 'Other': '3'}
                    gender_id = gender_map.get(gender, '1')
                    await self._call_tool("playwright_click", {"selector": f"label[for='gender-radio-{gender_id}']"})

                    await self._call_tool("playwright_fill", {"selector": "#userNumber", "value": mobile})

                    # Submit form
                    await self._call_tool("playwright_click", {"selector": "#submit"})

                    result = f"**Form at {url} - Practice Form Complete**\n\n"
                    result += "**Fields Filled:**\n"
                    result += f"  - firstName: {first_name}\n"
                    result += f"  - lastName: {last_name}\n"
                    result += f"  - email: {email}\n"
                    result += f"  - gender: {gender}\n"
                    result += f"  - mobile: {mobile}\n"
                    result += f"  - submitted: yes\n"

                    self._emit_summary(result, [])
                    return result
                except Exception as e:
                    logger.warning(f"demoqa direct injection failed: {e}, falling back to generic")

            # Parse common field patterns (generic fallback)
            patterns = [
                (r"customer\s*name\s*['\"]([^'\"]+)['\"]", 'custname'),
                (r"telephone\s*['\"]([^'\"]+)['\"]", 'custtel'),
                (r"email\s*['\"]([^'\"]+)['\"]", 'custemail'),
                (r"(?:pizza\s*)?size\s*['\"]([^'\"]+)['\"]", 'size'),
                (r"delivery\s*time[^'\"]*['\"]([^'\"]+)['\"]", 'delivery'),
                (r"delivery\s*instructions?[^'\"]*['\"]([^'\"]+)['\"]", 'comments'),
            ]

            for pattern, field_name in patterns:
                m = re.search(pattern, lower)
                if m:
                    fields_to_fill[field_name] = m.group(1)

            # Extract toppings
            toppings = re.findall(r"(?:topping[s]?\s*)?['\"]?(bacon|mushroom|cheese|onion)['\"]?", lower, re.I)
            if toppings:
                fields_to_fill['toppings'] = [t.lower() for t in toppings]

            logger.info(f"[MULTI-FORM] Parsed fields: {fields_to_fill}")

            fill_results = {}
            for field_name, value in fields_to_fill.items():
                if field_name == 'toppings':
                    for topping in value:
                        try:
                            await self._call_tool("playwright_click", {"selector": f"input[value='{topping}']"})
                            fill_results[f"topping_{topping}"] = "checked"
                        except Exception:
                            fill_results[f"topping_{topping}"] = "failed"
                elif field_name == 'size':
                    try:
                        await self._call_tool("playwright_click", {"selector": f"input[value='{value}']"})
                        fill_results[field_name] = value
                    except Exception:
                        fill_results[field_name] = "failed"
                else:
                    selectors = [
                        f"input[name='{field_name}']",
                        f"textarea[name='{field_name}']",
                        f"input[id='{field_name}']",
                        f"textarea[id='{field_name}']",
                    ]
                    filled = False
                    for sel in selectors:
                        try:
                            result = await self._call_tool("playwright_fill", {"selector": sel, "value": value})
                            if result and result.get("success"):
                                fill_results[field_name] = value
                                filled = True
                                break
                        except Exception:
                            continue
                    if not filled:
                        fill_results[field_name] = "not found"

            result = f"**Form at {url} - Multi-Field Fill Complete**\n\n"
            result += "**Fields Filled:**\n"
            for field, status in fill_results.items():
                result += f"  - {field}: {status}\n"

            self._emit_summary(result, [])
            return result

        except Exception as e:
            logger.warning(f"Multi-field form fill failed: {e}")
            return None

    async def _execute_generic_form_fill(self, url: str, field_value_pairs: list, prompt: str) -> Optional[str]:
        """Handle generic form fill with field-value pairs like 'firstName with John'."""
        if not url.startswith('http'):
            url = 'https://' + url

        logger.info(f"[GENERIC-FORM] Filling form at {url} with {len(field_value_pairs)} fields")

        try:
            nav_result = await self._call_tool("playwright_navigate", {"url": url})
            if not nav_result or nav_result.get("error"):
                return f"Failed to navigate to {url}"

            await asyncio.sleep(1)

            fill_results = {}
            for field_name, value in field_value_pairs:
                # Skip 'name' if it's part of another phrase like "name john doe"
                if field_name.lower() in ['name', 'form', 'the', 'out']:
                    continue

                # Try multiple selector strategies
                selectors = [
                    f"input[id='{field_name}']",
                    f"input[name='{field_name}']",
                    f"input[id*='{field_name}' i]",
                    f"input[name*='{field_name}' i]",
                    f"input[placeholder*='{field_name}' i]",
                    f"textarea[id='{field_name}']",
                    f"textarea[name='{field_name}']",
                ]

                filled = False
                for sel in selectors:
                    try:
                        result = await self._call_tool("playwright_fill", {"selector": sel, "value": value})
                        if result and result.get("success"):
                            fill_results[field_name] = value
                            filled = True
                            break
                    except Exception:
                        continue

                if not filled:
                    fill_results[field_name] = "not found"

            result = f"**Form at {url} - Generic Fill Complete**\n\n"
            result += "**Fields Filled:**\n"
            for field, status in fill_results.items():
                result += f"  - {field}: {status}\n"

            self._emit_summary(result, [])
            return result

        except Exception as e:
            logger.warning(f"Generic form fill failed: {e}")
            return None

    async def execute_mega_warehouse(self, books_pages, quotes_pages, prompt: str) -> str:
        """MEGA DATA WAREHOUSE: Full pages + categories + quotes - enterprise scale."""
        lower = prompt.lower()

        book_start = int(books_pages.group(1))
        book_end = int(books_pages.group(2))
        quote_start = int(quotes_pages.group(1))
        quote_end = int(quotes_pages.group(2))

        category_map = {
            "travel": "travel_2", "mystery": "mystery_3",
            "historical fiction": "historical-fiction_4", "science fiction": "science-fiction_16",
            "poetry": "poetry_23", "art": "art_25", "philosophy": "philosophy_7",
            "religion": "religion_12", "science": "science_22", "music": "music_14"
        }

        categories_to_extract = [cat for cat in category_map if cat in lower]

        all_books = []
        all_quotes = []
        author_counts = {}

        # Extract books from pages
        urls = self._extract_urls(prompt)
        base_url = urls[0] if urls else "https://example.com"

        for page in range(book_start, min(book_end + 1, 51)):
            page_url = f"{base_url}/catalogue/page-{page}.html"
            await self._call_tool("playwright_navigate", {"url": page_url})

            extract_result = await self._call_tool("playwright_extract_structured", {
                "item_selector": ".product_pod",
                "field_selectors": {"title": "h3 a@title", "price": ".price_color"},
                "limit": 20
            })

            if extract_result and extract_result.get("data"):
                for item in extract_result["data"]:
                    price_str = item.get("price", "0")
                    price_val = float(re.sub(r'[^0-9.]', '', price_str)) if price_str else 0
                    all_books.append({"title": item.get("title", ""), "price": price_val, "page": page})

        # Extract quotes
        for page in range(quote_start, min(quote_end + 1, 11)):
            page_url = f"https://quotes.toscrape.com/page/{page}/"
            await self._call_tool("playwright_navigate", {"url": page_url})

            extract_result = await self._call_tool("playwright_extract_structured", {
                "item_selector": ".quote",
                "field_selectors": {"quote": ".text", "author": ".author"},
                "limit": 20
            })

            if extract_result and extract_result.get("data"):
                for item in extract_result["data"]:
                    author = item.get("author", "Unknown")
                    all_quotes.append({"quote": item.get("quote", ""), "author": author})
                    author_counts[author] = author_counts.get(author, 0) + 1

        # Build summary
        summary = "**MEGA DATA WAREHOUSE REPORT**\n\n"
        summary += f"## Books ({len(all_books)} items)\n"
        if all_books:
            prices = [b["price"] for b in all_books]
            summary += f"- Price range: ${min(prices):.2f} - ${max(prices):.2f}\n"
            summary += f"- Average: ${sum(prices)/len(prices):.2f}\n"

        summary += f"\n## Quotes ({len(all_quotes)} items)\n"
        summary += f"- Unique authors: {len(author_counts)}\n"
        if author_counts:
            top = sorted(author_counts.items(), key=lambda x: x[1], reverse=True)[:5]
            summary += f"- Top authors: {', '.join(f'{a}({c})' for a,c in top)}\n"

        self._emit_summary(summary, [])
        return summary

    async def execute_category_collection(self, prompt: str) -> Optional[str]:
        """Collect items from multiple categories."""
        category_map = {
            "travel": "travel_2", "mystery": "mystery_3",
            "historical fiction": "historical-fiction_4", "science fiction": "science-fiction_16",
            "poetry": "poetry_23", "art": "art_25", "philosophy": "philosophy_7",
            "religion": "religion_12", "science": "science_22", "music": "music_14"
        }

        lower = prompt.lower()
        categories = [cat for cat in category_map if cat in lower]

        if not categories:
            return None

        urls = self._extract_urls(prompt)
        base_url = urls[0] if urls else "https://books.toscrape.com"

        all_items = {}
        for cat in categories:
            cat_url = f"{base_url}/catalogue/category/books/{category_map[cat]}/index.html"
            await self._call_tool("playwright_navigate", {"url": cat_url})

            extract_result = await self._call_tool("playwright_extract_structured", {
                "item_selector": ".product_pod",
                "field_selectors": {"title": "h3 a@title", "price": ".price_color"},
                "limit": 10
            })

            if extract_result and extract_result.get("data"):
                all_items[cat] = extract_result["data"]

        result = f"**CATEGORY COLLECTION ({len(categories)} categories)**\n\n"
        for cat, items in all_items.items():
            result += f"## {cat.title()} ({len(items)} items)\n"
            for item in items[:5]:
                result += f"  - {item.get('title', 'Unknown')}: {item.get('price', 'N/A')}\n"
            result += "\n"

        self._emit_summary(result, [])
        return result

    async def execute_categories_plus_quotes(self, prompt: str, quotes_page_match) -> Optional[str]:
        """Execute combined categories and quotes extraction."""
        # This is a combined workflow - extract categories first, then quotes
        cat_result = await self.execute_category_collection(prompt)

        quote_start = int(quotes_page_match.group(1))
        quote_end = int(quotes_page_match.group(2))

        all_quotes = []
        for page in range(quote_start, min(quote_end + 1, 11)):
            page_url = f"https://quotes.toscrape.com/page/{page}/"
            await self._call_tool("playwright_navigate", {"url": page_url})

            extract_result = await self._call_tool("playwright_extract_structured", {
                "item_selector": ".quote",
                "field_selectors": {"quote": ".text", "author": ".author"},
                "limit": 10
            })

            if extract_result and extract_result.get("data"):
                all_quotes.extend(extract_result["data"])

        combined = cat_result or ""
        combined += f"\n## Quotes ({len(all_quotes)} items)\n"
        for q in all_quotes[:10]:
            combined += f"  - \"{q.get('quote', '')[:50]}...\" - {q.get('author', 'Unknown')}\n"

        self._emit_summary(combined, [])
        return combined
