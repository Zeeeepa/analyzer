"""
Local LLM Planner - Uses the configured LLM for strategic planning when no external API key is available.

This is a fallback planner that generates multi-step execution plans using the local/remote LLM
(e.g., llama3.1:8b) instead of requiring a specialized API key like Kimi K2.
"""

import json
import hashlib
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from functools import lru_cache
from loguru import logger


@lru_cache(maxsize=100)
def _compile_site_pattern(pattern: str) -> re.Pattern:
    """Pre-compile regex patterns for site matching with caching."""
    return re.compile(pattern, re.IGNORECASE)


@dataclass
class LocalPlanStep:
    """A single step in the execution plan."""
    step_number: int
    action: str
    tool: str
    arguments: Dict[str, Any]
    expected_result: str
    fallback: Optional[str] = None


@dataclass
class LocalTaskPlan:
    """Complete execution plan."""
    task_id: str
    original_prompt: str
    summary: str
    steps: List[LocalPlanStep]
    estimated_iterations: int
    potential_blockers: List[str] = field(default_factory=list)
    success_criteria: str = ""


class LocalPlanner:
    """
    Generates execution plans using the configured LLM.

    This enables multi-step planning without requiring external API keys.
    Uses llama3.1:8b or similar models that support tool calling.
    """

    # Class-level cache for compiled prompt template
    _prompt_cache: Optional[str] = None

    # Core browser automation tools - organized by function
    CORE_TOOLS = {
        # === NAVIGATION ===
        "playwright_navigate": "Go to URL. ALWAYS START HERE. Args: {url: string}",

        # === PAGE INSPECTION - Choose based on page type ===
        "browser_snapshot": "BEST FOR: SPAs, dynamic pages (Facebook, Google, any React/Vue site). Returns clickable element refs with mmid. Use for interaction. Args: {}",
        "playwright_snapshot": "BEST FOR: Static pages, accessibility info. Returns text tree without refs. Use for reading content. Args: {}",
        "playwright_get_markdown": "BEST FOR: Reading articles, blog posts, documentation. Returns clean text. Args: {}",
        "playwright_get_content": "Get raw HTML. Use for debugging or specific HTML analysis. Args: {selector: string (optional)}",
        "playwright_screenshot": "Visual capture. Use when you need to SEE the page. Args: {}",

        # === DATA EXTRACTION - Choose based on what you need ===
        "playwright_extract_list": "BEST FOR: Lists, search results, tables. Auto-detects Amazon, eBay, HN, GitHub, Reddit, LinkedIn. 100% accurate CSS. Args: {limit: number (optional)}",
        "playwright_extract_structured": "BEST FOR: Custom fields with CSS selectors. Use @attr for attributes. Args: {field_selectors: {field: 'selector@attr'}}",
        "playwright_find_contacts": "BEST FOR: Emails, phones, contact info. Scans entire page. Args: {}",
        "playwright_batch_extract": "BEST FOR: Multiple URLs at once. Args: {urls: [string], fields: {}}",
        "playwright_evaluate": "Run JavaScript on page. BEST FOR: Complex extraction, custom logic. Args: {script: string}",

        # === INTERACTION ===
        "playwright_click": "Click element by CSS selector or text. Args: {selector: string}",
        "browser_click": "Click by mmid ref (from browser_snapshot). Use after browser_snapshot. Args: {ref: string}",
        "playwright_fill": "Type into input field. Auto-detects if Enter needed. Args: {selector: string, value: string}",
        "browser_type": "Type by mmid ref (from browser_snapshot). Args: {ref: string, text: string}",
        "playwright_select_dropdown": "Select dropdown option. Args: {selector: string, value: string}",
        "playwright_press_key": "Press keyboard key (Enter, Tab, Escape, etc). Args: {key: string}",
        "playwright_scroll": "Scroll page. Args: {direction: 'down'|'up'|'bottom'|'top'}",
        "playwright_hover": "Hover over element. Args: {selector: string}",

        # === WAITING ===
        "sleep": "Wait N seconds. Use after navigation or for dynamic content. Args: {seconds: number}",
        "playwright_wait_for": "Wait for element to appear. Args: {selector: string, timeout: number (optional)}",

        # === SITE-SPECIFIC TOOLS ===
        "extract_fb_ads_advertisers": "FACEBOOK ADS LIBRARY: Automated extraction. Args: {query: string, country: string (default US), limit: number}",

        # === FILE OUTPUT ===
        "write_file": "Save to file. USE THIS FOR FINAL OUTPUT. Args: {path: string, content: string}",
        "write_validated_csv": "Save CSV with validation. Args: {path: string, rows: list, required_fields: list (optional)}",
    }

    # Site-specific selectors for common sites (2024-2025 updated)
    SITE_SELECTORS = {
        "amazon": {
            "search": "#twotabsearchtextbox",
            "submit": "#nav-search-submit-button",
            "prime_filter": "span[data-csa-c-content-id='p_85/2470955011']",
            "star_filter_4plus": "span[data-csa-c-content-id='p_72/1248882011']",
            "results": "div[data-component-type='s-search-result']"
        },
        "youtube": {
            "search": "input[name='search_query']",
            "submit": "#search-icon-legacy",
            "filter_button": "#filter-button",
            "filter_thisweek": "a[title='This week'], ytd-search-filter-renderer:has-text('This week')"
        },
        "google": {"search": "input[name='q']", "submit": "input[name='btnK']"},
        "yelp": {
            "search": "#search_description, input[name='find_desc']",
            "location": "#search_location, input[name='find_loc']",
            "submit": "#header-search-submit, button[type='submit']",
            "open_now": "button:has-text('Open Now'), span:has-text('Open Now')"
        },
        "indeed": {
            "search": "#text-input-what, input[id*='what'], input[name='q']",
            "location": "#text-input-where, input[id*='where'], input[name='l']",
            "submit": "button.yosegi-InlineWhatWhere-primaryButton, button[type='submit']",
            "date_filter": "button:has-text('Date posted'), button[aria-label*='date']"
        },
        "saucedemo": {"username": "#user-name", "password": "#password", "login": "#login-button"},
        "guardian": {"search": "input[name='q']", "submit": "button[type='submit']"},
        "booking": {
            "destination": ":where(input[name='ss'], input[data-testid='destination-search-input'])",
            "checkin": "button[data-testid='date-display-field-start'], div[data-date]",
            "checkout": "button[data-testid='date-display-field-end']",
            "guests": "button[data-testid='occupancy-config']",
            "submit": "button[type='submit']",
            "star_filter": "div[data-filters-group='class'] input[value='4'], label:has-text('4 stars')"
        },
        "airbnb": {
            "search": "input[data-testid='structured-search-input-field-query'], input[name='query']",
            "checkin": "div[data-testid='structured-search-input-field-split-dates-0']",
            "checkout": "div[data-testid='structured-search-input-field-split-dates-1']",
            "guests": "div[data-testid='structured-search-input-field-guests-button']",
            "submit": "button[data-testid='structured-search-input-search-button']",
            "price_filter": "button:has-text('Price'), button[data-testid='category-bar-filter-button']"
        },
        "target": {
            "search": "input[data-test='@web/Search/SearchInput'], input#search",
            "submit": "button[data-test='@web/Search/SearchButton']",
            "first_result": "a[data-test='product-title'], div[data-test='@web/ProductCard/ProductCardVariantDefault']",
            "store_picker": "button:has-text('pickup'), button[data-test='shippingButton']"
        },
        "kayak": {
            "origin": "input[aria-label*='origin'], input[placeholder*='From']",
            "destination": "input[aria-label*='destination'], input[placeholder*='To']",
            "depart_date": "div[aria-label*='Depart'], input[aria-label*='Departure']",
            "return_date": "div[aria-label*='Return'], input[aria-label*='Return']",
            "submit": "button[aria-label='Search'], button:has-text('Search')"
        },
        "opentable": {
            "search": "input[data-test='location-picker-input'], input[aria-label*='Location']",
            "party_size": "select[data-test='party-size-picker'], button:has-text('party')",
            "date": "input[data-test='date-picker'], button:has-text('Today')",
            "time": "select[data-test='time-picker'], button:has-text('7:00')",
            "submit": "button[data-test='search-button'], button:has-text('Find a table')"
        }
    }

    PLANNING_PROMPT = """Create a JSON browser automation plan.

TASK: {task}

TOOLS:
{tools}

SITE SELECTORS (use these EXACT selectors - they are tested and working):

AMAZON (amazon.com):
- Search: #twotabsearchtextbox
- Submit: press_key Enter (NOT click)
- DO NOT try to click filter checkboxes - they have dynamic IDs
- After search, use playwright_get_markdown to extract results

YOUTUBE (youtube.com):
- Search: input[name='search_query']
- Submit: press_key Enter
- DO NOT click filter buttons - use playwright_get_markdown after search

AIRBNB (airbnb.com):
- IMPORTANT: Airbnb uses complex autocomplete. Just navigate to URL with search params:
  https://www.airbnb.com/s/Austin--TX/homes?adults=2&price_max=150
- Then use playwright_get_markdown to extract listings

INDEED (indeed.com):
- Navigate directly with search params: https://www.indeed.com/jobs?q=sales+development+representative&l=Seattle+WA
- Use playwright_get_markdown to extract job listings

YELP (yelp.com):
- Navigate with URL: https://www.yelp.com/search?find_desc=best+pizza&find_loc=Brooklyn+NY
- Use playwright_get_markdown to extract results

BOOKING.COM (booking.com):
- Navigate with params: https://www.booking.com/searchresults.html?ss=Miami&checkin=2024-12-20&checkout=2024-12-23
- Use playwright_get_markdown to extract hotels

TARGET (target.com):
- Search: input[data-test='@web/Search/SearchInput']
- Submit: press_key Enter
- Click first result: a[data-test='product-title']
- Use playwright_get_markdown to extract product info

KAYAK (kayak.com):
- Navigate with URL: https://www.kayak.com/flights/SEA-NYC/2024-12-20/2024-12-27
- Use playwright_get_markdown to extract flight options

OPENTABLE (opentable.com):
- Navigate with URL: https://www.opentable.com/s?covers=4&dateTime=2024-12-07T19%3A00&term=San+Francisco
- Use playwright_get_markdown to extract restaurants

FACEBOOK ADS LIBRARY (facebook.com/ads/library):
- USE extract_fb_ads_advertisers tool - it handles everything automatically
- Example: extract_fb_ads_advertisers with query="booked meetings", country="US", limit=5
- This is the ONLY reliable way to extract advertiser URLs from FB Ads Library

DIRECTORY/LISTING SITES (use category URLs, NOT homepage):
- clutch.co/agencies/digital-marketing (marketing agencies)
- clutch.co/agencies/web-development (dev agencies)
- g2.com/categories/crm (software by category)
- capterra.com/marketing-automation-software (software listings)
- goodfirms.co/web-development-companies (dev companies)
- yelp.com/search?find_desc=X&find_loc=Y (local business search)
- yellowpages.com/search?search_terms=X&geo_location_terms=Y

GOOGLE SEARCH (use direct URL to avoid CAPTCHA):
- For research tasks, prefer site-specific directories over Google
- If must use Google: site:clutch.co marketing agencies NYC

RULES:
1. Respond with ONLY valid JSON, no other text
2. For SINGLE page content: use playwright_get_markdown
3. For LIST extraction (multiple items like agencies, products, companies): use playwright_batch_extract
4. PREFER URL parameters over filling forms for complex sites (Airbnb, Indeed, Yelp, Booking, Kayak)
5. For simple search (Amazon, YouTube, Target): fill + press Enter
6. NEVER use playwright_evaluate - it does not exist
7. NEVER navigate to just homepage (e.g., clutch.co) - use category/search URLs
8. For "find X companies/agencies" tasks: use playwright_batch_extract to get structured list data
9. playwright_batch_extract returns list of items with title/link - PERFECT for CSV export

FORMAT:
{{"summary":"brief task","steps":[{{"step_number":1,"action":"navigate","tool":"playwright_navigate","arguments":{{"url":"https://example.com"}},"expected_result":"loaded"}},{{"step_number":2,"action":"extract content","tool":"playwright_get_markdown","arguments":{{}},"expected_result":"content extracted"}}],"potential_blockers":["popup"],"success_criteria":"done"}}

JSON ONLY:"""

    def __init__(self, ollama_client, model: str = None):
        """
        Initialize with an Ollama-compatible client.

        Args:
            ollama_client: Client with chat() method (Ollama or OpenAICompatibleClient)
            model: Model name to use for planning
        """
        self.client = ollama_client
        self.model = model
        # LRU cache for planning results (task_hash -> LocalTaskPlan)
        self._plan_cache: Dict[str, LocalTaskPlan] = {}
        self._plan_cache_order: List[str] = []
        self._max_cache_size = 50
        logger.info(f"LocalPlanner initialized with model: {model}")

    @property
    def planning_prompt(self) -> str:
        """Cached property for planning prompt template."""
        if LocalPlanner._prompt_cache is None:
            LocalPlanner._prompt_cache = self.PLANNING_PROMPT
        return LocalPlanner._prompt_cache

    # URL patterns for directory sites - auto-construct URLs from task keywords
    SITE_URL_PATTERNS = {
        'clutch.co': {
            'marketing': 'https://clutch.co/agencies/digital-marketing',
            'seo': 'https://clutch.co/agencies/seo',
            'web development': 'https://clutch.co/agencies/web-development',
            'software development': 'https://clutch.co/agencies/it-services/software-development',
            'app development': 'https://clutch.co/agencies/mobile-application-developers',
            'design': 'https://clutch.co/agencies/design',
            'advertising': 'https://clutch.co/agencies/advertising',
            'pr': 'https://clutch.co/agencies/pr-firms',
            'default': 'https://clutch.co/agencies/digital-marketing',
            '_selector': '[class*="provider-row"] a[href*="/profile/"], .directory-list a[href*="/profile/"], [data-provider-id] a'
        },
        'g2.com': {
            'crm': 'https://www.g2.com/categories/crm',
            'marketing': 'https://www.g2.com/categories/marketing-automation',
            'project management': 'https://www.g2.com/categories/project-management',
            'default': 'https://www.g2.com/categories/crm'
        },
        'capterra.com': {
            'marketing': 'https://www.capterra.com/marketing-automation-software/',
            'crm': 'https://www.capterra.com/customer-relationship-management-software/',
            'default': 'https://www.capterra.com/marketing-automation-software/'
        }
    }

    def _preprocess_task(self, task: str) -> str:
        """
        Preprocess task to add explicit URLs for directory sites.
        Transforms "find X on clutch.co" to include the actual category URL.
        """
        return preprocess_directory_task(task, self.SITE_URL_PATTERNS)

    @lru_cache(maxsize=50)
    def _get_task_hash(self, task: str, tools_tuple: tuple) -> str:
        """Generate a hash for task caching. Tools must be tuple for hashability."""
        content = f"{task}:{','.join(sorted(tools_tuple))}"
        return hashlib.md5(content.encode()).hexdigest()

    def _get_cached_plan(self, task_hash: str) -> Optional[LocalTaskPlan]:
        """Retrieve a cached plan and update LRU ordering."""
        if task_hash in self._plan_cache:
            # Move to end (most recently used)
            self._plan_cache_order.remove(task_hash)
            self._plan_cache_order.append(task_hash)
            logger.debug(f"[LOCAL_PLANNER] Cache hit for task hash: {task_hash[:8]}...")
            return self._plan_cache[task_hash]
        return None

    def _cache_plan(self, task_hash: str, plan: LocalTaskPlan) -> None:
        """Cache a plan with LRU eviction."""
        # Evict oldest if cache is full
        if len(self._plan_cache) >= self._max_cache_size:
            oldest = self._plan_cache_order.pop(0)
            del self._plan_cache[oldest]
            logger.debug(f"[LOCAL_PLANNER] Evicted oldest plan from cache")

        self._plan_cache[task_hash] = plan
        self._plan_cache_order.append(task_hash)
        logger.debug(f"[LOCAL_PLANNER] Cached plan for task hash: {task_hash[:8]}...")

    def decompose_multi_task_prompt(self, prompt: str) -> List[str]:
        """
        Decompose a multi-task prompt into individual task strings.

        Detects patterns like:
        - "Go to X... Go to Y... Go to Z..." (multiple "Go to" phrases)
        - ". Go to " patterns (sentence boundaries)
        - Long prompts with multiple distinct actions (length > 300)

        Args:
            prompt: The original user prompt

        Returns:
            List of individual task strings. Single-item list if only one task detected.
        """
        # DETECTION LOGIC
        # Count only "go to" that appear as standalone commands (start of sentence or after punctuation)
        # Match "go to" at start of string, after ". ", after "...", or after newline
        go_to_pattern = _compile_site_pattern(r'(?:^|\.\.\.?\s*|\.\s+|\n\s*)go to\s+\w')
        go_to_matches = go_to_pattern.findall(prompt.lower())
        go_to_count = len(go_to_matches)

        has_sentence_breaks = ". go to " in prompt.lower()
        is_long_prompt = len(prompt) > 300

        # If only one "go to" or short prompt, not multi-task
        if go_to_count <= 1 and not is_long_prompt:
            return [prompt]

        # SPLIT LOGIC
        tasks = []

        # Pattern 1: Split on ". Go to " (most common)
        if has_sentence_breaks:
            # Split on sentence boundaries before "Go to"
            split_pattern = _compile_site_pattern(r'\.\s+(?=Go to |go to )')
            parts = split_pattern.split(prompt)
            for part in parts:
                cleaned = part.strip().rstrip('.')
                # Filter noise - min 6 chars (like "Go to A") and must contain "go to"
                if cleaned and len(cleaned) >= 6 and "go to" in cleaned.lower():
                    tasks.append(cleaned)

        # Pattern 2: Split on "... Go to " (ellipsis separator)
        elif "... go to" in prompt.lower() or "...go to" in prompt.lower():
            ellipsis_pattern = _compile_site_pattern(r'\.\.\.\s*(?=Go to |go to )')
            parts = ellipsis_pattern.split(prompt)
            for part in parts:
                cleaned = part.strip().rstrip('.')
                if cleaned and len(cleaned) >= 6 and "go to" in cleaned.lower():
                    tasks.append(cleaned)

        # Pattern 3: Multiple "Go to" without clear separators - split on newlines or long gaps
        elif go_to_count > 1:
            # Try splitting on newlines first
            if '\n' in prompt:
                parts = [p.strip() for p in prompt.split('\n') if p.strip()]
                # Only use newline split if each part has "go to"
                newline_tasks = [p for p in parts if len(p) >= 6 and "go to" in p.lower()]
                if len(newline_tasks) >= 2:
                    tasks = newline_tasks
                else:
                    # Fallback to splitting on "Go to"
                    goto_pattern = _compile_site_pattern(r'(?=Go to |go to )')
                    parts = goto_pattern.split(prompt)
                    for part in parts:
                        cleaned = part.strip()
                        if cleaned and len(cleaned) >= 6 and ("go to" in cleaned.lower()):
                            tasks.append(cleaned)
            else:
                # Split on "Go to" but keep it in each task
                goto_pattern = _compile_site_pattern(r'(?=Go to |go to )')
                parts = goto_pattern.split(prompt)
                for part in parts:
                    cleaned = part.strip()
                    if cleaned and len(cleaned) >= 6 and ("go to" in cleaned.lower()):
                        tasks.append(cleaned)

        # Fallback: treat as single task if decomposition failed
        if not tasks:
            return [prompt]

        logger.debug(f"[LOCAL_PLANNER] Decomposed prompt into {len(tasks)} tasks: {[t[:50] for t in tasks]}")
        return tasks

    async def create_plan(
        self,
        task: str,
        available_tools: Optional[List[str]] = None
    ) -> Optional[LocalTaskPlan]:
        """
        Create an execution plan for a task.

        Args:
            task: The user's task description
            available_tools: List of available tool names (uses CORE_TOOLS if None)

        Returns:
            LocalTaskPlan with steps, or None if planning fails
        """
        # CACHE CHECK: See if we've planned this exact task before
        tools_tuple = tuple(sorted(available_tools)) if available_tools else tuple(sorted(self.CORE_TOOLS.keys()))
        task_hash = self._get_task_hash(task, tools_tuple)
        cached_plan = self._get_cached_plan(task_hash)
        if cached_plan:
            logger.info(f"[LOCAL_PLANNER] Returning cached plan for task: {task[:50]}...")
            return cached_plan

        # MULTI-TASK DETECTION: Check if this is a multi-task prompt first
        tasks = self.decompose_multi_task_prompt(task)
        if len(tasks) > 1:
            logger.debug(f"[LOCAL_PLANNER] Multi-task prompt detected with {len(tasks)} sub-tasks")
            # Return a special plan that indicates sequential execution needed
            multi_task_plan = LocalTaskPlan(
                task_id=hashlib.md5(task.encode()).hexdigest()[:12],
                original_prompt=task,
                summary=f"Multi-task prompt with {len(tasks)} sequential tasks",
                steps=[
                    LocalPlanStep(
                        step_number=i + 1,
                        action=f"Execute sub-task {i+1}",
                        tool="multi_task_executor",
                        arguments={"sub_task": sub_task, "task_index": i},
                        expected_result=f"Sub-task {i+1} completed",
                        fallback=None
                    )
                    for i, sub_task in enumerate(tasks)
                ],
                estimated_iterations=len(tasks),
                potential_blockers=["Each sub-task may have its own blockers"],
                success_criteria=f"All {len(tasks)} sub-tasks completed successfully"
            )
            self._cache_plan(task_hash, multi_task_plan)
            return multi_task_plan

        # FAST PATH: FB Ads Library - use reliable extract_fb_ads_advertisers tool
        lower = task.lower()
        if any(p in lower for p in ['facebook ads library', 'fb ads library', 'ads library']):
            # Extract search query from task - ONLY grab quoted text or short "for X" phrases
            query_pattern = _compile_site_pattern(r"['\"]([^'\"]+)['\"]")
            query_match = query_pattern.search(lower)  # First try quoted
            if query_match:
                search_query = query_match.group(1).strip()
            else:
                # Try "for X" but limit to 3 words max
                for_pattern = _compile_site_pattern(r"(?:for|search|find|advertising)\s+([a-z0-9\s]{2,30})(?:\s+(?:in|and|get|extract|-)|$)")
                for_match = for_pattern.search(lower)
                search_query = for_match.group(1).strip() if for_match else "marketing"
                # Clean up common suffixes
                suffix_pattern = _compile_site_pattern(r'\s*(in usa|and get|and extract|get me).*$')
                search_query = suffix_pattern.sub('', search_query).strip()

            # Extract limit from task
            limit_pattern = _compile_site_pattern(r"(\d+)\s*(?:advertiser|url|result|website|compan)")
            limit_match = limit_pattern.search(lower)
            limit = int(limit_match.group(1)) if limit_match else 5

            logger.debug(f"[LOCAL_PLANNER] Using FB Ads shortcut: query='{search_query}', limit={limit}")
            fb_ads_plan = LocalTaskPlan(
                task_id=hashlib.md5(task.encode()).hexdigest()[:8],
                original_prompt=task,
                summary=f"Extract {limit} advertisers from FB Ads Library for '{search_query}'",
                steps=[
                    LocalPlanStep(
                        step_number=1,
                        action="extract FB Ads advertisers",
                        tool="extract_fb_ads_advertisers",
                        arguments={"query": search_query, "country": "US", "limit": limit},
                        expected_result="List of advertiser Facebook page URLs"
                    )
                ],
                estimated_iterations=1,
                success_criteria=f"Return {limit} advertiser URLs from FB Ads Library"
            )
            self._cache_plan(task_hash, fb_ads_plan)
            return fb_ads_plan

        # Preprocess task to add URLs for directory sites
        task = self._preprocess_task(task)
        logger.debug(f"[LOCAL_PLANNER] create_plan called for: {task[:50]}...")

        # KIMI K2 FIRST: For complex multi-step tasks, use Kimi K2 directly
        # This gives much better plans than local 3B models
        lower_task = task.lower()
        is_complex = (
            len(task.split()) >= 8 or  # Longer prompts
            any(kw in lower_task for kw in [
                'and then', 'after that', 'multiple', 'all the', 'each',
                'find and', 'extract and', 'scrape', 'crawl', 'research',
                'step', 'first', 'second', 'third', 'finally',
                'save to', 'export', 'csv', 'compile', 'gather'
            ])
        )

        if is_complex:
            try:
                from .kimi_k2_client import get_kimi_client
                kimi = get_kimi_client()
                if kimi.is_available():
                    logger.debug(f"[LOCAL_PLANNER] Complex task detected - using Kimi K2 for better planning...")
                    import asyncio
                    tool_names = list(self.CORE_TOOLS.keys()) if available_tools is None else available_tools
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                    kimi_plan = loop.run_until_complete(kimi.plan_task(task, tool_names))
                    if kimi_plan and kimi_plan.steps:
                        logger.debug(f"[LOCAL_PLANNER] Kimi K2 created plan with {len(kimi_plan.steps)} steps")
                        steps = []
                        for s in kimi_plan.steps:
                            steps.append(LocalPlanStep(
                                step_number=s.step_number,
                                action=s.action,
                                tool=s.tool,
                                arguments=s.arguments,
                                expected_result=s.expected_result,
                                fallback=s.fallback
                            ))
                        return LocalTaskPlan(
                            task_id=kimi_plan.task_id,
                            original_prompt=task,
                            summary=kimi_plan.summary,
                            steps=steps,
                            estimated_iterations=kimi_plan.estimated_iterations,
                            potential_blockers=kimi_plan.potential_blockers,
                            success_criteria=kimi_plan.success_criteria
                        )
            except Exception as e:
                logger.debug(f"[LOCAL_PLANNER] Kimi K2 unavailable ({e}), falling back to local LLM...")

        # Build tools description
        if available_tools:
            tools_desc = "\n".join([
                f"- {name}: {self.CORE_TOOLS.get(name, 'Tool for browser automation')}"
                for name in available_tools if name.startswith("playwright")
            ][:15])  # Limit to 15 tools
        else:
            tools_desc = "\n".join([f"- {k}: {v}" for k, v in self.CORE_TOOLS.items()])

        prompt = self.planning_prompt.format(task=task, tools=tools_desc)

        try:
            # Call the LLM with timeout - SINGLE MODEL STRATEGY
            # Use 0000/ui-tars-1.5-7b:latest exclusively for high quality tool calling
            # Falls back to Kimi K2 if 0000/ui-tars-1.5-7b:latest fails
            FALLBACK_MODELS = [
                '0000/ui-tars-1.5-7b:latest',  # Best for tool calling - primary model
            ]
            models_to_try = [self.model] + [m for m in FALLBACK_MODELS if m != self.model]

            logger.debug(f"[LOCAL_PLANNER] Calling LLM with model: {self.model}")
            import asyncio

            response = None
            used_model = None

            # Timeout for each model attempt (seconds)
            MODEL_TIMEOUT = 25

            for model in models_to_try:
                try:
                    logger.debug(f"[LOCAL_PLANNER] Trying model: {model} (timeout: {MODEL_TIMEOUT}s)")

                    # Run LLM call with timeout using threading
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(
                            self.client.chat,
                            model=model,
                            messages=[{"role": "user", "content": prompt}],
                            options={"temperature": 0.2, "num_predict": 1500}
                        )
                        try:
                            response = future.result(timeout=MODEL_TIMEOUT)
                        except concurrent.futures.TimeoutError:
                            logger.debug(f"[LOCAL_PLANNER] ⏱ Model {model} timed out after {MODEL_TIMEOUT}s, trying next...")
                            response = None
                            continue

                    used_model = model
                    # Validate response has content
                    if isinstance(response, dict):
                        content = response.get("message", {}).get("content", "")
                    elif hasattr(response, 'message') and hasattr(response.message, 'content'):
                        content = response.message.content
                    else:
                        content = str(response)

                    if content and len(content) > 50 and '{' in content:
                        logger.debug(f"[LOCAL_PLANNER] ✓ Success with model: {model}")
                        break
                    else:
                        logger.debug(f"[LOCAL_PLANNER] Model {model} returned insufficient response, trying next...")
                        response = None
                except Exception as e:
                    logger.warning(f"[LOCAL PLANNER] Model {model} failed: {e}")
                    continue

            if not response:
                # KIMI K2 FALLBACK: When all local models fail, try Kimi K2 API
                logger.warning(f"[LOCAL PLANNER] All local models failed, trying Kimi K2 API fallback...")
                try:
                    from .kimi_k2_client import get_kimi_client, should_use_kimi_planning
                    kimi = get_kimi_client()
                    if kimi.is_available():
                        logger.debug(f"[LOCAL_PLANNER] 🚀 Escalating to Kimi K2 API...")
                        import asyncio
                        # Get available tools list
                        tool_names = list(self.CORE_TOOLS.keys()) if available_tools is None else available_tools
                        loop = asyncio.get_event_loop()
                        kimi_plan = loop.run_until_complete(kimi.plan_task(task, tool_names))
                        if kimi_plan and kimi_plan.steps:
                            logger.debug(f"[LOCAL_PLANNER] ✓ Kimi K2 created plan with {len(kimi_plan.steps)} steps")
                            # Convert to LocalTaskPlan format
                            steps = []
                            for s in kimi_plan.steps:
                                steps.append(LocalPlanStep(
                                    step_number=s.step_number,
                                    action=s.action,
                                    tool=s.tool,
                                    arguments=s.arguments,
                                    expected_result=s.expected_result,
                                    fallback=s.fallback
                                ))
                            return LocalTaskPlan(
                                task_id=kimi_plan.task_id,
                                task=task,
                                summary=kimi_plan.summary,
                                steps=steps,
                                blockers=kimi_plan.potential_blockers
                            )
                except Exception as e:
                    logger.warning(f"[LOCAL PLANNER] Kimi K2 fallback failed: {e}")

                logger.warning(f"[LOCAL PLANNER] All models including Kimi failed, skipping planning")
                return None

            logger.debug(f"[LOCAL_PLANNER] LLM response received: type={type(response)}")

            # Extract content
            if isinstance(response, dict):
                content = response.get("message", {}).get("content", "")
                if not content and "choices" in response:
                    content = response["choices"][0]["message"]["content"]
            elif hasattr(response, 'message') and hasattr(response.message, 'content'):
                # Handle Ollama ChatResponse object
                content = response.message.content
            else:
                content = str(response)

            logger.debug(f"[LOCAL_PLANNER] Content extracted, length: {len(content)}")
            if len(content) < 50:
                logger.warning(f"[LOCAL PLANNER] LLM response too short: {content}")

            # Parse JSON from response
            plan_data = self._extract_json(content)
            if not plan_data:
                logger.debug(f"[LOCAL_PLANNER] Could not extract JSON. Response: {content[:300]}")
                # KIMI K2 FALLBACK: When JSON parsing fails, try Kimi K2 API
                logger.debug(f"[LOCAL_PLANNER] 🚀 JSON parse failed - escalating to Kimi K2 API...")
                try:
                    from .kimi_k2_client import get_kimi_client
                    kimi = get_kimi_client()
                    if kimi.is_available():
                        tool_names = list(self.CORE_TOOLS.keys()) if available_tools is None else available_tools
                        # We're in async context, use await directly
                        kimi_plan = await kimi.plan_task(task, tool_names)
                        if kimi_plan and kimi_plan.steps:
                            logger.debug(f"[LOCAL_PLANNER] ✓ Kimi K2 created plan with {len(kimi_plan.steps)} steps")
                            steps = []
                            for s in kimi_plan.steps:
                                steps.append(LocalPlanStep(
                                    step_number=s.step_number,
                                    action=s.action,
                                    tool=s.tool,
                                    arguments=s.arguments,
                                    expected_result=s.expected_result,
                                    fallback=s.fallback
                                ))
                            return LocalTaskPlan(
                                task_id=kimi_plan.task_id,
                                original_prompt=task,
                                summary=kimi_plan.summary,
                                steps=steps,
                                potential_blockers=kimi_plan.potential_blockers
                            )
                except Exception as e:
                    logger.warning(f"[LOCAL PLANNER] Kimi K2 JSON fallback failed: {e}")
                return None

            logger.debug(f"[LOCAL_PLANNER] Parsed plan with {len(plan_data.get('steps', []))} steps")

            # Build plan
            task_id = hashlib.md5(task.encode()).hexdigest()[:12]
            steps = []

            for i, s in enumerate(plan_data.get("steps", [])):
                step = LocalPlanStep(
                    step_number=i + 1,
                    action=s.get("action", f"Step {i+1}"),
                    tool=s.get("tool", "playwright_snapshot"),
                    arguments=s.get("arguments", {}),
                    expected_result=s.get("expected_result", "Success"),
                    fallback=s.get("fallback")
                )
                steps.append(step)

            if not steps:
                logger.warning("No steps parsed from plan")
                return None

            # POST-PROCESSING: Ensure file writing step exists when task requires it
            task_lower = task.lower()
            save_keywords = ['save to', 'write to', 'export to', 'store to', 'output to']
            file_extensions = ['.txt', '.csv', '.json', '.md', '.log']

            needs_file_write = any(kw in task_lower for kw in save_keywords)
            if needs_file_write and any(ext in task_lower for ext in file_extensions):
                # Check if any step uses write_file
                has_write_step = any(s.tool in ['write_file', 'write_validated_csv'] for s in steps)
                if not has_write_step:
                    # Extract filename from task
                    filename_pattern = _compile_site_pattern(r'[\w_-]+\.(txt|csv|json|md|log)')
                    filename_match = filename_pattern.search(task)
                    filename = filename_match.group(0) if filename_match else 'output.txt'

                    # Add file writing step
                    write_step = LocalPlanStep(
                        step_number=len(steps) + 1,
                        action=f"Save extracted data to {filename}",
                        tool="write_file",
                        arguments={"path": filename, "content": "{last.content}"},
                        expected_result=f"Data saved to {filename}",
                        fallback=None
                    )
                    steps.append(write_step)
                    logger.debug(f"[LOCAL_PLANNER] Added write_file step for {filename}")

            plan = LocalTaskPlan(
                task_id=task_id,
                original_prompt=task,
                summary=plan_data.get("summary", task[:50]),
                steps=steps,
                estimated_iterations=len(steps),
                potential_blockers=plan_data.get("potential_blockers", []),
                success_criteria=plan_data.get("success_criteria", "Task completed")
            )

            logger.info(f"Created plan with {len(steps)} steps: {plan.summary}")
            self._cache_plan(task_hash, plan)
            return plan

        except Exception as e:
            logger.error(f"Planning failed: {e}")
            return None

    def _extract_json(self, text: str) -> Optional[Dict]:
        """Extract JSON from text that may contain other content."""
        # Try to find JSON block
        json_patterns = [
            r'```json\s*([\s\S]*?)\s*```',  # Markdown code block
            r'```\s*([\s\S]*?)\s*```',       # Generic code block
            r'(\{[\s\S]*\})',                # Raw JSON object
        ]

        for pattern in json_patterns:
            compiled_pattern = _compile_site_pattern(pattern)
            match = compiled_pattern.search(text)
            if match:
                json_str = match.group(1)
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    # Try to repair truncated JSON
                    repaired = self._repair_truncated_json(json_str)
                    if repaired:
                        logger.debug(f"[LOCAL_PLANNER] ✓ Repaired truncated JSON")
                        return repaired
                    continue

        # Try parsing the whole text as JSON
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Last attempt: try to repair
            repaired = self._repair_truncated_json(text)
            if repaired:
                logger.debug(f"[LOCAL_PLANNER] ✓ Repaired truncated JSON from raw text")
                return repaired
            return None

    def _repair_truncated_json(self, json_str: str) -> Optional[Dict]:
        """
        Attempt to repair truncated JSON by completing brackets and quotes.

        Common truncation patterns seen in forever mode:
        - URL cut off: "url": "https://news.ycombinator  -> complete URL and close structure
        - Mid-step: {"step_number": 1, "action": "nav  -> complete the step
        - Mid-array: [{"step": 1}, {"step  -> extract complete steps

        Strategy:
        1. Try smart completion of truncated strings/URLs
        2. Try extracting complete step objects from partial JSON
        3. Build minimal valid plan from whatever we can salvage
        """
        if not json_str or not json_str.strip():
            return None

        # Find where JSON starts
        start = json_str.find('{')
        if start == -1:
            return None

        json_str = json_str[start:]

        # STRATEGY 1: Try to complete truncated URL pattern
        # Pattern: "url": "https://news.ycombinator  (truncated mid-URL)
        url_pattern = _compile_site_pattern(r'"url"\s*:\s*"(https?://[^"]*?)$')
        url_truncation = url_pattern.search(json_str)
        if url_truncation:
            partial_url = url_truncation.group(1)
            # Complete common URLs
            url_completions = {
                'https://news.ycombinator': 'https://news.ycombinator.com',
                'http://news.ycombinator': 'http://news.ycombinator.com',
                'https://www.google': 'https://www.google.com',
                'https://www.facebook': 'https://www.facebook.com',
                'https://www.linkedin': 'https://www.linkedin.com',
            }

            # Find matching completion
            completed_url = None
            for prefix, full_url in url_completions.items():
                if partial_url.startswith(prefix[:len(partial_url)]):
                    completed_url = full_url
                    break

            if not completed_url:
                # Generic: just add .com if it looks like a domain
                if '.' not in partial_url.split('/')[-1]:
                    completed_url = partial_url + '.com'
                else:
                    completed_url = partial_url

            # Replace truncated URL and try to close structure
            json_str = json_str[:url_truncation.start(1)] + completed_url + '"'

        # STRATEGY 2: Check if we're in a string and close it
        in_string = False
        escape_next = False
        for c in json_str:
            if escape_next:
                escape_next = False
                continue
            if c == '\\':
                escape_next = True
                continue
            if c == '"':
                in_string = not in_string

        if in_string:
            json_str += '"'

        # Count brackets after potential string fix
        open_braces = json_str.count('{')
        close_braces = json_str.count('}')
        open_brackets = json_str.count('[')
        close_brackets = json_str.count(']')

        # Build proper closing sequence
        # We need to close in the right order: inner structures first
        repair = ''

        # If we're mid-object (after a key or in arguments), complete minimally
        # Check if last significant token is a colon (expecting value)
        stripped = json_str.rstrip()
        if stripped.endswith(':'):
            repair += '""'  # Add empty string value
        elif stripped.endswith(','):
            # Remove trailing comma before closing
            json_str = json_str.rstrip()[:-1]

        # Close structures in proper order
        missing_brackets = open_brackets - close_brackets
        missing_braces = open_braces - close_braces

        # Interleave closings based on nesting (approximate)
        # For plan JSON: steps array is inside root object
        # So close ] before final }
        if missing_brackets > 0 and missing_braces > 0:
            repair += ']' * missing_brackets
            repair += '}' * missing_braces
        else:
            repair += ']' * max(0, missing_brackets)
            repair += '}' * max(0, missing_braces)

        # Try to parse repaired JSON
        try:
            repaired_str = json_str + repair
            result = json.loads(repaired_str)

            # Validate it has expected structure
            if isinstance(result, dict):
                if 'steps' in result and isinstance(result['steps'], list) and len(result['steps']) > 0:
                    logger.debug(f"[LOCAL_PLANNER] ✓ Repaired JSON with {len(result['steps'])} steps")
                    return result
                elif 'summary' in result:
                    # Has summary but maybe steps got corrupted
                    pass
        except json.JSONDecodeError as e:
            # Log for debugging
            logger.debug(f"[LOCAL_PLANNER] JSON repair attempt 1 failed: {e}")

        # STRATEGY 3: Extract complete step objects from partial JSON
        try:
            steps_pattern = _compile_site_pattern(r'"steps"\s*:\s*\[(.*)')
            steps_match = steps_pattern.search(json_str)
            if steps_match:
                steps_str = steps_match.group(1)
                complete_steps = []
                depth = 0
                current_step = ''
                in_str = False
                esc = False

                for char in steps_str:
                    current_step += char

                    if esc:
                        esc = False
                        continue
                    if char == '\\' and in_str:
                        esc = True
                        continue
                    if char == '"':
                        in_str = not in_str
                        continue

                    if not in_str:
                        if char == '{':
                            depth += 1
                        elif char == '}':
                            depth -= 1
                            if depth == 0:
                                # Complete step object
                                step_str = current_step.strip().rstrip(',')
                                try:
                                    step = json.loads(step_str)
                                    # Validate step has required fields
                                    if 'action' in step or 'tool' in step:
                                        complete_steps.append(step)
                                except json.JSONDecodeError as e:
                                    logger.debug(f"[LOCAL_PLANNER] Skipping invalid step JSON during extraction: {str(e)[:100]}")
                                current_step = ''

                if complete_steps:
                    # Extract summary
                    summary_pattern = _compile_site_pattern(r'"summary"\s*:\s*"([^"]*)"')
                    summary_match = summary_pattern.search(json_str)
                    summary = summary_match.group(1) if summary_match else "Recovered plan"

                    logger.debug(f"[LOCAL_PLANNER] ✓ Extracted {len(complete_steps)} complete steps from truncated JSON")
                    return {
                        "summary": summary,
                        "steps": complete_steps,
                        "potential_blockers": []
                    }
        except Exception as e:
            logger.debug(f"[LOCAL_PLANNER] Step extraction failed: {e}")

        # STRATEGY 4: Build minimal plan if we can infer intent
        # If we see "navigate" and a partial URL, create a basic navigate plan
        try:
            if 'playwright_navigate' in json_str or '"navigate"' in json_str:
                url_extract_pattern = _compile_site_pattern(r'"url"\s*:\s*"([^"]*)')
                url_match = url_extract_pattern.search(json_str)
                if url_match:
                    url = url_match.group(1)
                    # Complete URL if truncated
                    if not url.endswith('.com') and '.' not in url.split('/')[-1]:
                        url += '.com'

                    logger.debug(f"[LOCAL_PLANNER] ✓ Built minimal navigate plan from truncated JSON")
                    return {
                        "summary": "Navigate and extract content",
                        "steps": [
                            {
                                "step_number": 1,
                                "action": "navigate",
                                "tool": "playwright_navigate",
                                "arguments": {"url": url}
                            },
                            {
                                "step_number": 2,
                                "action": "extract content",
                                "tool": "playwright_get_markdown",
                                "arguments": {}
                            }
                        ],
                        "potential_blockers": []
                    }
        except Exception as e:
            logger.debug(f"[LOCAL_PLANNER] Minimal plan building failed: {e}")

        return None


# Shared preprocessing so higher-level planners can reuse directory URL construction
def preprocess_directory_task(
    task: str,
    site_url_patterns: Optional[Dict[str, Dict[str, str]]] = None
) -> str:
    """
    Preprocess task to add explicit URLs and selectors for known directory sites.
    Used by both LocalPlanner and higher-level planners to avoid homepage navigation.
    """
    task_lower = task.lower()
    patterns_source = site_url_patterns or LocalPlanner.SITE_URL_PATTERNS

    # Check if task mentions a directory site without explicit URL
    # Optimized: early exit if URL already present
    if 'http' in task_lower:
        return task

    # Single pass through sites
    for site, patterns in patterns_source.items():
        if site not in task_lower:
            continue

        # Find matching category URL - prioritize specific keywords
        matched_url = None
        # Filter out special keys first
        category_patterns = {k: v for k, v in patterns.items() if k not in ['default', '_selector']}

        # Check for keyword matches (single pass)
        for keyword, url in category_patterns.items():
            if keyword in task_lower:
                matched_url = url
                break

        # Fallback to default if no specific match
        if matched_url is None:
            matched_url = patterns.get('default')

        # Get site-specific selector if available
        selector = patterns.get('_selector', '')
        selector_hint = f' Use selector: {selector}' if selector else ''

        # Prepend URL guidance to task
        logger.debug(f"[LOCAL_PLANNER] Auto-constructed URL: {matched_url}")
        if selector:
            logger.debug(f"[LOCAL_PLANNER] Using selector: {selector}")
        return f"Navigate to {matched_url} then {task}.{selector_hint}"

    return task


# Execution state for compatibility with strategic planner interface
@dataclass
class LocalExecutionState:
    """Execution state compatible with strategic planner interface."""
    plan: LocalTaskPlan
    current_step: int = 0
    completed_steps: List[int] = field(default_factory=list)
    failed_steps: List[int] = field(default_factory=list)
    consecutive_failures: int = 0
    goal_verified: bool = False  # NEW: Track whether the original goal was verified

    @property
    def is_complete(self) -> bool:
        # Only mark complete if ALL steps executed (not just current_step incremented)
        # AND goal has been verified
        all_steps_executed = len(self.completed_steps) >= len(self.plan.steps)
        return all_steps_executed and self.goal_verified

    @property
    def all_steps_attempted(self) -> bool:
        """Check if we've attempted all planned steps."""
        return self.current_step >= len(self.plan.steps)

    def next_step(self) -> Optional[LocalPlanStep]:
        if self.current_step >= len(self.plan.steps):
            return None
        step = self.plan.steps[self.current_step]
        self.current_step += 1
        return step

    def mark_success(self, step_num: int):
        if step_num not in self.completed_steps:
            self.completed_steps.append(step_num)
        self.consecutive_failures = 0

    def mark_failure(self, step_num: int):
        if step_num not in self.failed_steps:
            self.failed_steps.append(step_num)
        self.consecutive_failures += 1

    def verify_goal_completion(self) -> None:
        """Mark that the original goal has been verified as complete."""
        self.goal_verified = True

    def get_completion_status(self) -> str:
        """Get human-readable completion status."""
        total = len(self.plan.steps)
        completed = len(self.completed_steps)
        failed = len(self.failed_steps)
        return f"{completed}/{total} steps completed, {failed} failed"


async def create_local_plan(
    ollama_client,
    task: str,
    model: str = None,
    available_tools: Optional[List[str]] = None
) -> Optional[LocalExecutionState]:
    """
    Convenience function to create a plan and return execution state.

    Args:
        ollama_client: Ollama-compatible client
        task: Task description
        model: Model to use
        available_tools: List of available tools

    Returns:
        LocalExecutionState ready for execution
    """
    logger.debug(f"[LOCAL PLANNER] Creating plan for: {task[:50]}...")
    planner = LocalPlanner(ollama_client, model)
    plan = await planner.create_plan(task, available_tools)

    if plan:
        logger.info(f"[LOCAL PLANNER] Plan created successfully with {len(plan.steps)} steps")
        return LocalExecutionState(plan=plan)
    logger.warning("[LOCAL PLANNER] Failed to create plan")
    return None
