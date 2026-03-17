"""
Parallel Orchestrator for Sub-Agent Execution

Enables running multiple browser workers concurrently for large-scale tasks.
Inspired by how Playwright MCP handles tasks, but with our enhancements:
- Parallel worker pool
- Result aggregation
- Session persistence
- Anti-bot handling
"""

import asyncio
import json
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from loguru import logger


@dataclass
class WorkerTask:
    """A single task for a worker to execute"""
    task_id: str
    prompt: str
    url: Optional[str] = None
    session_name: Optional[str] = None
    priority: int = 0
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class WorkerResult:
    """Result from a worker task"""
    task_id: str
    success: bool
    data: Any
    error: Optional[str] = None
    duration_ms: float = 0


class ParallelOrchestrator:
    """
    Manages parallel execution of browser tasks across multiple workers.

    Usage:
        orchestrator = ParallelOrchestrator(max_workers=5)

        # For "research 50 companies", decompose into individual tasks
        tasks = orchestrator.decompose_task(
            "research 50 companies from list",
            companies_list
        )

        # Execute in parallel
        results = await orchestrator.execute_parallel(tasks, worker_func)
    """

    def __init__(self, max_workers: int = 5):
        self.max_workers = max_workers
        self.semaphore = asyncio.Semaphore(max_workers)
        self.results: List[WorkerResult] = []
        self.active_workers = 0
        self.completed_count = 0
        self.failed_count = 0
        self._progress_callback: Optional[Callable] = None

    def set_progress_callback(self, callback: Callable[[int, int, int], None]):
        """Set callback for progress updates: (completed, failed, total)"""
        self._progress_callback = callback

    async def execute_parallel(
        self,
        tasks: List[WorkerTask],
        worker_func: Callable[[WorkerTask], Any],
        timeout_per_task: float = 120.0
    ) -> List[WorkerResult]:
        """
        Execute tasks in parallel using worker pool.

        Args:
            tasks: List of tasks to execute
            worker_func: Async function that takes a WorkerTask and returns result
            timeout_per_task: Timeout in seconds per task

        Returns:
            List of WorkerResults
        """
        self.results = []
        self.completed_count = 0
        self.failed_count = 0
        total = len(tasks)

        logger.info(f"[PARALLEL] Starting {total} tasks with {self.max_workers} workers")

        async def run_with_semaphore(task: WorkerTask) -> WorkerResult:
            async with self.semaphore:
                self.active_workers += 1
                start_time = asyncio.get_event_loop().time()

                try:
                    result = await asyncio.wait_for(
                        worker_func(task),
                        timeout=timeout_per_task
                    )
                    duration = (asyncio.get_event_loop().time() - start_time) * 1000

                    self.completed_count += 1
                    worker_result = WorkerResult(
                        task_id=task.task_id,
                        success=True,
                        data=result,
                        duration_ms=duration
                    )

                except asyncio.TimeoutError:
                    self.failed_count += 1
                    worker_result = WorkerResult(
                        task_id=task.task_id,
                        success=False,
                        data=None,
                        error=f"Timeout after {timeout_per_task}s"
                    )

                except Exception as e:
                    self.failed_count += 1
                    worker_result = WorkerResult(
                        task_id=task.task_id,
                        success=False,
                        data=None,
                        error=str(e)
                    )

                finally:
                    self.active_workers -= 1

                if self._progress_callback:
                    self._progress_callback(
                        self.completed_count,
                        self.failed_count,
                        total
                    )

                return worker_result

        # Execute all tasks concurrently with semaphore limiting
        # Using asyncio.gather for Python 3.10 compatibility (TaskGroup requires 3.11+)
        tasks_coros = [run_with_semaphore(task) for task in tasks]
        results = await asyncio.gather(*tasks_coros, return_exceptions=True)

        # Collect results and log any exceptions
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"[PARALLEL] Task failed with exception: {result}")
            elif isinstance(result, WorkerResult):
                self.results.append(result)

        logger.info(f"[PARALLEL] Completed: {self.completed_count}/{total}, Failed: {self.failed_count}")
        return self.results

    def decompose_task(
        self,
        master_prompt: str,
        items: List[Any],
        item_template: str = "Process item: {item}"
    ) -> List[WorkerTask]:
        """
        Decompose a large task into individual worker tasks.

        Args:
            master_prompt: The overall task description
            items: List of items to process
            item_template: Template for individual task prompts

        Returns:
            List of WorkerTasks
        """
        tasks = []
        for i, item in enumerate(items):
            task = WorkerTask(
                task_id=f"task_{i}",
                prompt=item_template.format(item=item),
                priority=0
            )
            tasks.append(task)

        logger.info(f"[PARALLEL] Decomposed into {len(tasks)} tasks")
        return tasks


class SessionManager:
    """
    Manages persistent browser sessions for authenticated workflows.

    Stores cookies and localStorage per domain for reuse.
    """

    def __init__(self, storage_dir: str = "~/.eversale/sessions"):
        self.storage_dir = Path(storage_dir).expanduser()
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _get_session_path(self, session_name: str) -> Path:
        """Get path for a session's storage"""
        return self.storage_dir / session_name

    async def save_session(
        self,
        session_name: str,
        page,
        include_local_storage: bool = True
    ) -> Dict[str, Any]:
        """
        Save browser session (cookies + localStorage) for later use.

        Args:
            session_name: Name for this session (e.g., "linkedin", "google")
            page: Playwright page object
            include_local_storage: Whether to save localStorage

        Returns:
            Dict with save status
        """
        session_path = self._get_session_path(session_name)
        session_path.mkdir(parents=True, exist_ok=True)

        # Get cookies from browser context
        context = page.context
        cookies = await context.cookies()

        # Save cookies
        cookies_file = session_path / "cookies.json"
        with open(cookies_file, "w") as f:
            json.dump(cookies, f, indent=2)

        # Save localStorage if requested
        if include_local_storage:
            try:
                local_storage = await page.evaluate("""
                    () => {
                        const items = {};
                        for (let i = 0; i < localStorage.length; i++) {
                            const key = localStorage.key(i);
                            items[key] = localStorage.getItem(key);
                        }
                        return items;
                    }
                """)

                ls_file = session_path / "localStorage.json"
                with open(ls_file, "w") as f:
                    json.dump(local_storage, f, indent=2)
            except Exception as e:
                logger.warning(f"Could not save localStorage: {e}")

        logger.info(f"[SESSION] Saved session '{session_name}' with {len(cookies)} cookies")
        return {"success": True, "session_name": session_name, "cookies_count": len(cookies)}

    async def load_session(
        self,
        session_name: str,
        context,
        page=None
    ) -> Dict[str, Any]:
        """
        Load a saved session into browser context.

        Args:
            session_name: Name of the session to load
            context: Playwright browser context
            page: Optional page for localStorage restore

        Returns:
            Dict with load status
        """
        session_path = self._get_session_path(session_name)

        if not session_path.exists():
            return {"success": False, "error": f"Session '{session_name}' not found"}

        # Load cookies
        cookies_file = session_path / "cookies.json"
        if cookies_file.exists():
            with open(cookies_file) as f:
                cookies = json.load(f)
            await context.add_cookies(cookies)
            logger.info(f"[SESSION] Loaded {len(cookies)} cookies for '{session_name}'")
        else:
            cookies = []

        # Load localStorage if page provided
        ls_loaded = False
        if page:
            ls_file = session_path / "localStorage.json"
            if ls_file.exists():
                with open(ls_file) as f:
                    local_storage = json.load(f)

                await page.evaluate("""
                    (items) => {
                        for (const [key, value] of Object.entries(items)) {
                            localStorage.setItem(key, value);
                        }
                    }
                """, local_storage)
                ls_loaded = True
                logger.info(f"[SESSION] Loaded localStorage for '{session_name}'")

        return {
            "success": True,
            "session_name": session_name,
            "cookies_count": len(cookies),
            "local_storage_loaded": ls_loaded
        }

    def list_sessions(self) -> List[str]:
        """List all saved sessions"""
        if not self.storage_dir.exists():
            return []
        return [d.name for d in self.storage_dir.iterdir() if d.is_dir()]

    def delete_session(self, session_name: str) -> bool:
        """Delete a saved session"""
        session_path = self._get_session_path(session_name)
        if session_path.exists():
            import shutil
            shutil.rmtree(session_path)
            logger.info(f"[SESSION] Deleted session '{session_name}'")
            return True
        return False


class DirectExtractor:
    """
    Direct DOM extraction without LLM interpretation.

    Extracts data using CSS selectors directly from the page,
    avoiding LLM hallucination issues.
    """

    def __init__(self, page):
        self.page = page

    async def extract_list(
        self,
        item_selector: str,
        fields: Dict[str, str],
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Extract a list of items from the page using CSS selectors.

        Args:
            item_selector: CSS selector for each list item (e.g., '.athing')
            fields: Dict mapping field names to sub-selectors
                   e.g., {"title": ".titleline a", "url": ".titleline a@href"}
                   Use @attr to get attribute instead of text
            limit: Max number of items to extract

        Returns:
            List of dicts with extracted data
        """
        results = []

        # Get all matching items
        items = await self.page.query_selector_all(item_selector)

        if limit:
            items = items[:limit]

        for i, item in enumerate(items):
            row = {"_index": i + 1}

            for field_name, selector_spec in fields.items():
                try:
                    # Check if we need to extract an attribute
                    if "@" in selector_spec:
                        selector, attr = selector_spec.rsplit("@", 1)
                        element = await item.query_selector(selector) if selector else item
                        if element:
                            row[field_name] = await element.get_attribute(attr)
                    else:
                        element = await item.query_selector(selector_spec)
                        if element:
                            row[field_name] = await element.inner_text()
                except Exception as e:
                    logger.debug(f"Could not extract {field_name}: {e}")
                    row[field_name] = None

            results.append(row)

        logger.info(f"[EXTRACT] Extracted {len(results)} items using CSS selectors")
        return results

    async def extract_table(
        self,
        table_selector: str = "table",
        header_selector: str = "thead th",
        row_selector: str = "tbody tr",
        cell_selector: str = "td"
    ) -> List[Dict[str, Any]]:
        """
        Extract data from an HTML table.

        Returns list of dicts with header names as keys.
        """
        results = []

        # Get headers
        headers = []
        header_elements = await self.page.query_selector_all(f"{table_selector} {header_selector}")
        for h in header_elements:
            headers.append(await h.inner_text())

        # Get rows
        rows = await self.page.query_selector_all(f"{table_selector} {row_selector}")

        for row in rows:
            cells = await row.query_selector_all(cell_selector)
            row_data = {}

            for i, cell in enumerate(cells):
                key = headers[i] if i < len(headers) else f"col_{i}"
                row_data[key] = await cell.inner_text()

            results.append(row_data)

        return results


class AntiBotHandler:
    """
    Anti-bot detection and handling.

    Features:
    - Rate limiting per domain
    - Random delays
    - CAPTCHA detection
    - Exponential backoff
    """

    def __init__(self):
        self.domain_requests: Dict[str, List[float]] = {}  # domain -> list of request timestamps
        self.rate_limits: Dict[str, int] = {}  # domain -> max requests per minute
        self.default_rate_limit = 30  # requests per minute
        self.delay_range = (100, 500)  # ms
        self.backoff_multiplier = 2.0
        self.max_retries = 3

    def set_rate_limit(self, domain: str, requests_per_minute: int):
        """Set rate limit for a specific domain"""
        self.rate_limits[domain] = requests_per_minute

    async def pre_request(self, url: str) -> Dict[str, Any]:
        """
        Call before making a request. Handles rate limiting and delays.

        Returns:
            Dict with status and any warnings
        """
        from urllib.parse import urlparse
        import time

        domain = urlparse(url).netloc
        current_time = time.time()

        # Initialize domain tracking
        if domain not in self.domain_requests:
            self.domain_requests[domain] = []

        # Clean old requests (older than 1 minute)
        self.domain_requests[domain] = [
            t for t in self.domain_requests[domain]
            if current_time - t < 60
        ]

        # Check rate limit
        rate_limit = self.rate_limits.get(domain, self.default_rate_limit)
        if len(self.domain_requests[domain]) >= rate_limit:
            wait_time = 60 - (current_time - self.domain_requests[domain][0])
            logger.warning(f"[ANTIBOT] Rate limit reached for {domain}, waiting {wait_time:.1f}s")
            await asyncio.sleep(wait_time)

        # Random delay
        delay_ms = asyncio.get_event_loop().run_in_executor(
            None, lambda: __import__('random').randint(*self.delay_range)
        )
        await asyncio.sleep((await delay_ms) / 1000)

        # Record request
        self.domain_requests[domain].append(time.time())

        return {"status": "ok", "domain": domain}

    async def check_captcha(self, page) -> Dict[str, Any]:
        """
        Check if page has a CAPTCHA.

        Returns:
            Dict with captcha_detected bool and type
        """
        captcha_indicators = [
            # reCAPTCHA
            'iframe[src*="recaptcha"]',
            '.g-recaptcha',
            '#recaptcha',
            # hCaptcha
            'iframe[src*="hcaptcha"]',
            '.h-captcha',
            # Cloudflare
            '#challenge-running',
            '.cf-browser-verification',
            # Generic
            '[class*="captcha"]',
            '[id*="captcha"]',
        ]

        for indicator in captcha_indicators:
            try:
                element = await page.query_selector(indicator)
                if element:
                    logger.warning(f"[ANTIBOT] CAPTCHA detected: {indicator}")
                    return {
                        "captcha_detected": True,
                        "indicator": indicator,
                        "action": "manual_solve_required"
                    }
            except:
                pass

        return {"captcha_detected": False}

    async def handle_error_with_backoff(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute function with exponential backoff on errors.
        """
        last_error = None

        for attempt in range(self.max_retries):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_error = e
                wait_time = (self.backoff_multiplier ** attempt)
                logger.warning(f"[ANTIBOT] Attempt {attempt + 1} failed, waiting {wait_time}s: {e}")
                await asyncio.sleep(wait_time)

        raise last_error


# Export all classes
__all__ = [
    'ParallelOrchestrator',
    'WorkerTask',
    'WorkerResult',
    'SessionManager',
    'DirectExtractor',
    'AntiBotHandler'
]
