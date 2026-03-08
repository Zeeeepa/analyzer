"""
Deterministic State Machine Workflows for Common Tasks

This module implements predefined workflows for common browser automation tasks.
Instead of using LLM planning for every task, we match user prompts to known
workflows and execute them deterministically.

Philosophy: Make it work first. Known patterns should be fast and reliable.
Complex LLM planning is for unknown tasks only.

Features:
- Prompt-based workflow matching: Keywords in user prompts trigger workflows
- URL-based workflow auto-selection: Automatically detect workflow from current page URL
  (e.g., facebook.com/ads/library -> fb_ads_library workflow)
- Fallback to user-specified workflow if no match found
"""

import re
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum


class ErrorStrategy(Enum):
    """What to do when a step fails"""
    RETRY = "retry"  # Retry the step (default)
    SKIP = "skip"    # Skip to next step
    ABORT = "abort"  # Abort entire workflow


@dataclass
class WorkflowStep:
    """A single step in a workflow"""
    tool: str
    args: Dict[str, Any]
    wait_for: Optional[str] = None  # DOM selector or condition to wait for
    on_error: ErrorStrategy = ErrorStrategy.RETRY
    max_retries: int = 2
    description: str = ""  # Human-readable description for logging


@dataclass
class Workflow:
    """A complete workflow definition"""
    name: str
    steps: List[WorkflowStep]
    required_params: List[str]  # Parameters that must be provided
    description: str = ""


# FB Ads Library Workflow
FB_ADS_WORKFLOW = Workflow(
    name="fb_ads_library",
    description="Search Facebook Ads Library and extract advertiser URLs",
    required_params=["search_query"],
    steps=[
        WorkflowStep(
            tool="navigate",
            args={"url": "https://www.facebook.com/ads/library"},
            wait_for="input[placeholder*='Search']",
            description="Navigate to Facebook Ads Library"
        ),
        WorkflowStep(
            tool="type",
            args={
                "selector": "input[placeholder*='Search']",
                "text": "{search_query}"
            },
            description="Enter search query"
        ),
        WorkflowStep(
            tool="click",
            args={"selector": "button[type='submit'], button:has-text('Search')"},
            wait_for="div[role='article'], .ad-card",
            description="Submit search"
        ),
        WorkflowStep(
            tool="wait",
            args={"time": 3},
            description="Wait for results to load"
        ),
        WorkflowStep(
            tool="extract_fb_ads_batch",
            args={"max_ads": 100},
            description="Extract advertiser names, Facebook pages, and landing URLs"
        )
    ]
)


# LinkedIn Search Workflow
LINKEDIN_SEARCH_WORKFLOW = Workflow(
    name="linkedin_search",
    description="Search LinkedIn and extract profile information",
    required_params=["search_query"],
    steps=[
        WorkflowStep(
            tool="navigate",
            args={"url": "https://www.linkedin.com/search/results/people/?keywords={search_query}"},
            wait_for="div.search-results-container, main.search-results",
            description="Navigate to LinkedIn search results"
        ),
        WorkflowStep(
            tool="wait",
            args={"time": 2},
            description="Wait for results to render"
        ),
        WorkflowStep(
            tool="scroll",
            args={"direction": "down", "amount": 3},
            description="Scroll to load more results"
        ),
        WorkflowStep(
            tool="extract",
            args={
                "selector": "li.reusable-search__result-container",
                "fields": ["name", "headline", "location", "profile_url"]
            },
            description="Extract profile data"
        )
    ]
)


# Reddit Search Workflow
REDDIT_SEARCH_WORKFLOW = Workflow(
    name="reddit_search",
    description="Search Reddit and extract posts/users",
    required_params=["search_query"],
    steps=[
        WorkflowStep(
            tool="navigate",
            args={"url": "https://www.reddit.com/search/?q={search_query}"},
            wait_for="div[data-testid='post-container'], shreddit-post",
            description="Navigate to Reddit search"
        ),
        WorkflowStep(
            tool="wait",
            args={"time": 1.5},
            description="Wait for posts to load"
        ),
        WorkflowStep(
            tool="extract",
            args={
                "selector": "shreddit-post, div[data-testid='post-container']",
                "fields": ["title", "author", "subreddit", "upvotes", "url", "content"]
            },
            description="Extract post data"
        )
    ]
)


# Google Maps Business Search Workflow
GOOGLE_MAPS_WORKFLOW = Workflow(
    name="google_maps_search",
    description="Search Google Maps for businesses and extract their URLs",
    required_params=["search_query"],
    steps=[
        WorkflowStep(
            tool="navigate",
            args={"url": "https://www.google.com/maps/search/{search_query}"},
            wait_for="div[role='article'], div[role='feed']",
            description="Navigate to Google Maps search"
        ),
        WorkflowStep(
            tool="wait",
            args={"time": 3},
            description="Wait for map and results to load"
        ),
        WorkflowStep(
            tool="scroll",
            args={"direction": "down", "amount": 800},
            description="Scroll results panel to load more businesses",
            on_error=ErrorStrategy.SKIP
        ),
        WorkflowStep(
            tool="extract_list_auto",
            args={"limit": 20},
            description="Extract business data with URLs using site selectors"
        )
    ]
)


# Gmail Workflow
GMAIL_WORKFLOW = Workflow(
    name="gmail_open",
    description="Open Gmail inbox",
    required_params=[],
    steps=[
        WorkflowStep(
            tool="navigate",
            args={"url": "https://mail.google.com/mail/u/0/#inbox"},
            wait_for="div[role='main'], .AO",
            description="Navigate to Gmail inbox"
        ),
        WorkflowStep(
            tool="wait",
            args={"time": 2},
            description="Wait for inbox to load"
        )
    ]
)


# Generic Navigation Workflow
GENERIC_NAVIGATION_WORKFLOW = Workflow(
    name="navigate_to_url",
    description="Navigate to a specific URL",
    required_params=["url"],
    steps=[
        WorkflowStep(
            tool="navigate",
            args={"url": "{url}"},
            description="Navigate to URL"
        ),
        WorkflowStep(
            tool="wait",
            args={"time": 1},
            description="Wait for page load"
        )
    ]
)


# All available workflows
WORKFLOWS = [
    FB_ADS_WORKFLOW,
    LINKEDIN_SEARCH_WORKFLOW,
    REDDIT_SEARCH_WORKFLOW,
    GOOGLE_MAPS_WORKFLOW,
    GMAIL_WORKFLOW,
    GENERIC_NAVIGATION_WORKFLOW
]


def match_workflow_from_url(current_url: str) -> Optional[Workflow]:
    """
    Auto-select workflow based on current page URL.

    This enables intelligent workflow selection when user is already on a platform.
    For example, if user is on facebook.com/ads/library, automatically use fb_ads workflow.

    Args:
        current_url: Current browser page URL

    Returns:
        Matching workflow or None if no match
    """
    if not current_url:
        return None

    url_lower = current_url.lower()

    # Facebook Ads Library
    if "facebook.com/ads/library" in url_lower or "facebook.com/ads-library" in url_lower:
        return FB_ADS_WORKFLOW

    # TikTok Ads (if workflow exists, currently not defined)
    # if "tiktok.com/business-suite/ad-library" in url_lower or "tiktok.com/ads" in url_lower:
    #     return TIKTOK_ADS_WORKFLOW

    # LinkedIn Search
    if "linkedin.com/search" in url_lower:
        return LINKEDIN_SEARCH_WORKFLOW

    # Reddit Search
    if "reddit.com/search" in url_lower or "reddit.com/r/" in url_lower:
        return REDDIT_SEARCH_WORKFLOW

    # Google Maps
    if "google.com/maps" in url_lower:
        return GOOGLE_MAPS_WORKFLOW

    # Gmail
    if "mail.google.com" in url_lower:
        return GMAIL_WORKFLOW

    return None


def match_workflow(prompt: str, current_url: Optional[str] = None) -> Optional[Workflow]:
    """
    Match a user prompt to a known workflow using keyword matching.

    Enhanced with URL-based auto-selection - if user is already on a platform page,
    automatically select the appropriate workflow without requiring keywords.

    Simple and fast. No LLM needed for pattern recognition.

    Args:
        prompt: User's natural language prompt
        current_url: Optional current browser URL for auto-detection

    Returns:
        Matching workflow or None if no match
    """
    # First, try URL-based auto-selection if current_url provided
    if current_url:
        url_workflow = match_workflow_from_url(current_url)
        if url_workflow:
            return url_workflow

    # Fall back to prompt-based matching with flexible regex patterns
    prompt_lower = prompt.lower()

    # PRIORITY 1: Navigation patterns - check FIRST to prevent misrouting
    # Generic "go to" navigation for services/sites (not search/extract commands)
    # This prevents "navigate to LinkedIn" from being routed to LinkedIn search
    go_to_pattern = r"(?:go\s+to|navigate\s+to|open|visit)\s+(?!.*(?:and\s+)?(?:search|find|extract|scrape|get|collect))"
    if re.search(go_to_pattern, prompt_lower):
        # Exception: Gmail workflow handles "go to gmail" specifically
        if 'gmail' in prompt_lower and re.search(r"(?:go\s+to|open)\s+gmail", prompt_lower):
            pass  # Will be handled by Gmail pattern below
        else:
            return GENERIC_NAVIGATION_WORKFLOW

    # PRIORITY 2: Specific platform workflows (FB Ads, LinkedIn search, etc.)
    # FB Ads patterns - matches: "facebook ads for X", "search fb ads", "meta ads library", etc.
    fb_patterns = [
        r"facebook\s*ads?",           # "facebook ad", "facebook ads"
        r"fb\s*ads?",                 # "fb ad", "fb ads"
        r"ads?\s*library",            # "ads library", "ad library"
        r"meta\s*ads?",               # "meta ad", "meta ads"
        r"(?:search|find|get).*(?:facebook|fb|meta).*(?:ads?|advertisers?)",
    ]
    if any(re.search(p, prompt_lower) for p in fb_patterns):
        return FB_ADS_WORKFLOW

    # LinkedIn patterns - MORE SPECIFIC: only match actual search/find commands
    # NOT just any mention of LinkedIn (that goes to navigation)
    linkedin_patterns = [
        r"(?:search|find|look|get)\s+(?:on\s+)?linked\s*in",  # "search linkedin", "find on linkedin"
        r"linked\s*in\s+(?:search|for)\s+",  # "linkedin search for", "linkedin for"
        r"linked\s*in.*(?:people|profiles?|companies|leads?)",  # "linkedin people", etc.
    ]
    if any(re.search(p, prompt_lower) for p in linkedin_patterns):
        return LINKEDIN_SEARCH_WORKFLOW

    # Reddit patterns - MORE SPECIFIC: only match actual search/find commands
    reddit_patterns = [
        r"(?:search|find|look|get)\s+(?:on\s+)?reddit",  # "search reddit", "find on reddit"
        r"reddit\s+(?:search|for)\s+",  # "reddit search for", "reddit for"
        r"reddit.*(?:posts?|users?|leads?|discussions?|threads?)",  # "reddit posts", etc.
        r"r/\w+",                     # Subreddit reference like "r/sales"
    ]
    if any(re.search(p, prompt_lower) for p in reddit_patterns):
        return REDDIT_SEARCH_WORKFLOW

    # Google Maps patterns - matches: "google maps", "find businesses", "local search", etc.
    maps_patterns = [
        r"google\s*maps?",            # "google map", "google maps"
        r"maps?\s*search",            # "map search", "maps search"
        r"(?:find|search|get|look).*(?:businesses?|companies|stores?|shops?|restaurants?).*(?:near|local|in\s+\w+)",
        r"(?:local|nearby)\s*(?:businesses?|companies|stores?|shops?|restaurants?)",  # Added restaurants
        r"(?:businesses?|companies).*(?:near\s*me|in\s+\w+|local)",
        r"(?:restaurants?|cafes?|coffee\s*shops?|stores?)\s+(?:in|near)\s+\w+",  # "restaurants in NYC"
    ]
    if any(re.search(p, prompt_lower) for p in maps_patterns):
        return GOOGLE_MAPS_WORKFLOW

    # Gmail patterns - matches: "open gmail", "check email", "gmail inbox", etc.
    gmail_patterns = [
        r"gmail",                     # Any mention of Gmail
        r"open\s*(?:my\s*)?email",    # "open email", "open my email"
        r"check\s*(?:my\s*)?email",   # "check email", "check my email"
        r"(?:read|view)\s*(?:my\s*)?emails?",
    ]
    if any(re.search(p, prompt_lower) for p in gmail_patterns):
        return GMAIL_WORKFLOW

    # Generic navigation - match explicit URLs
    url_pattern = r'https?://[^\s]+'
    if re.search(url_pattern, prompt):
        return GENERIC_NAVIGATION_WORKFLOW

    # No workflow matched
    return None


def extract_params(prompt: str, workflow: Workflow) -> Dict[str, str]:
    """
    Extract parameters from the prompt for the workflow.

    Args:
        prompt: User's prompt
        workflow: Matched workflow

    Returns:
        Dictionary of extracted parameters
    """
    params = {}
    prompt_lower = prompt.lower()
    query = None

    # Extract search query (most common parameter)
    if "search_query" in workflow.required_params:
        # 1. Try quoted text first (e.g., "booked meetings")
        quoted_match = re.search(r'["\']([^"\']+)["\']', prompt)
        if quoted_match:
            query = quoted_match.group(1).strip()

        # 2. Try to extract topic/query from common patterns
        if not query:
            # Pattern: "discussing X" or "about X"
            topic_match = re.search(r'(?:discussing|about|regarding)\s+([a-zA-Z0-9\s\-]+?)(?:\s*\.|$|,|\s+or\s+)', prompt, re.I)
            if topic_match:
                query = topic_match.group(1).strip()

        # 3. Pattern: "for 'X'" or "URLs for X"
        if not query:
            for_match = re.search(r'(?:urls?\s+)?for\s+[\'"]?([a-zA-Z0-9\s\-]+?)[\'"]?(?:\s*\.|$|,)', prompt, re.I)
            if for_match:
                query = for_match.group(1).strip()

        # 4. Remove common prefixes as fallback
        if not query:
            for prefix in [
                "search facebook ads for ",
                "search fb ads for ",
                "find on linkedin ",
                "search linkedin for ",
                "search reddit for ",
                "find on reddit ",
                "google maps ",
                "find businesses ",
                "go to reddit and output ",
                "go to linkedin and output ",
                "go to google maps and output ",
            ]:
                if prompt_lower.startswith(prefix):
                    query = prompt[len(prefix):].strip()
                    break

        # 5. Extract from after platform mention + action
        if not query:
            platform_patterns = [
                r'(?:reddit|linkedin|fb\s*ads|google\s*maps?)\s+(?:and\s+)?(?:output|find|get|search).*?(?:discussing|about|for)\s+([a-zA-Z0-9\s\-]+?)(?:\s*\.|$|,)',
                r'(?:reddit|linkedin|fb\s*ads|google\s*maps?)\s+(?:and\s+)?(?:output|find|get|search)\s+\d+\s+(?:user\s+)?(?:profile\s+)?(?:urls?\s+)?(?:discussing|about|for)\s+([a-zA-Z0-9\s\-]+?)(?:\s*\.|$|,)',
            ]
            for pattern in platform_patterns:
                match = re.search(pattern, prompt_lower)
                if match:
                    query = match.group(1).strip()
                    break

        # Clean up query
        if query:
            query = query.strip('"').strip("'").strip()
            # Remove common trailing words
            query = re.sub(r'\s+(urls?|profiles?|advertiser|listing)s?\s*$', '', query, flags=re.I)
            # Remove leading/trailing numbers and common words
            query = re.sub(r'^(\d+\s+(?:user\s+)?(?:profile\s+)?(?:urls?\s+)?)+', '', query, flags=re.I).strip()

        # Use default if no query extracted
        if not query or query == prompt:
            # Use a sensible default based on workflow type
            if workflow.name == "reddit_search":
                query = "lead generation"
            elif workflow.name == "linkedin_search":
                query = "sales lead generation"
            elif workflow.name == "google_maps_search":
                query = "lead generation agency"
            elif workflow.name == "fb_ads_library":
                query = "booked meetings"
            else:
                query = "marketing"

        params["search_query"] = query

    # Extract URL for navigation workflow
    if "url" in workflow.required_params:
        url_pattern = r'(https?://[^\s]+)'
        match = re.search(url_pattern, prompt)
        if match:
            params["url"] = match.group(1)
        else:
            # Fallback: try to extract domain-like patterns
            # "go to example.com" -> "https://example.com"
            for word in prompt.split():
                if '.' in word and not word.startswith('.'):
                    url = word if word.startswith('http') else f'https://{word}'
                    params["url"] = url
                    break

    return params


def substitute_params(args: Dict[str, Any], params: Dict[str, str]) -> Dict[str, Any]:
    """
    Substitute parameter placeholders in workflow step arguments.

    Args:
        args: Step arguments with placeholders like {search_query}
        params: Actual parameter values

    Returns:
        Arguments with substituted values
    """
    result = {}
    for key, value in args.items():
        if isinstance(value, str):
            # Replace all {param} placeholders
            substituted = value
            for param_name, param_value in params.items():
                placeholder = f"{{{param_name}}}"
                substituted = substituted.replace(placeholder, param_value)
            result[key] = substituted
        else:
            result[key] = value
    return result


async def execute_workflow(
    workflow: Workflow,
    params: Dict[str, str],
    browser,  # Browser instance with tool methods
    logger=None
) -> Dict[str, Any]:
    """
    Execute a workflow deterministically.

    Args:
        workflow: The workflow to execute
        params: Parameters for the workflow
        browser: Browser instance with tool methods (navigate, click, extract, etc.)
        logger: Optional logger for progress updates

    Returns:
        Dictionary with execution results
    """
    results = {
        "workflow": workflow.name,
        "success": False,
        "steps_completed": 0,
        "steps_total": len(workflow.steps),
        "data": None,
        "url": None,  # Track the final URL
        "error": None
    }

    def log(message: str):
        if logger:
            logger.info(f"[Workflow:{workflow.name}] {message}")

    # Validate required parameters
    missing_params = [p for p in workflow.required_params if p not in params]
    if missing_params:
        results["error"] = f"Missing required parameters: {missing_params}"
        log(f"ERROR: {results['error']}")
        return results

    log(f"Starting workflow with params: {params}")

    # Execute each step
    for i, step in enumerate(workflow.steps, 1):
        log(f"Step {i}/{len(workflow.steps)}: {step.description}")

        # Substitute parameters in arguments
        step_args = substitute_params(step.args, params)

        # Execute step with retry logic
        retries = 0
        while retries <= step.max_retries:
            try:
                # Get the tool method from browser
                tool_method = getattr(browser, step.tool, None)
                if not tool_method:
                    raise Exception(f"Tool '{step.tool}' not found on browser instance")

                # Execute the tool
                result = await tool_method(**step_args)

                # Store data from extract steps
                if step.tool == "extract":
                    results["data"] = result

                # Wait for condition if specified
                if step.wait_for:
                    log(f"Waiting for: {step.wait_for}")
                    await browser.wait_for_selector(step.wait_for, timeout=10000)

                # Step succeeded
                results["steps_completed"] = i
                log(f"Step {i} completed successfully")
                break

            except Exception as e:
                retries += 1
                log(f"Step {i} failed (attempt {retries}/{step.max_retries + 1}): {str(e)}")

                if retries > step.max_retries:
                    # Max retries exceeded, apply error strategy
                    if step.on_error == ErrorStrategy.ABORT:
                        results["error"] = f"Step {i} failed after {step.max_retries} retries: {str(e)}"
                        log(f"ABORTING: {results['error']}")
                        return results
                    elif step.on_error == ErrorStrategy.SKIP:
                        log(f"SKIPPING step {i} after {step.max_retries} retries")
                        results["steps_completed"] = i
                        break
                    else:  # RETRY is default, but we've exhausted retries
                        results["error"] = f"Step {i} failed after {step.max_retries} retries: {str(e)}"
                        log(f"ABORTING: {results['error']}")
                        return results

                # Wait before retry
                if retries <= step.max_retries:
                    import asyncio
                    await asyncio.sleep(1 * retries)  # Progressive backoff

    # All steps completed
    results["success"] = True

    # Capture final URL from browser
    try:
        # Try to get URL from browser's _last_url attribute (BrowserToolAdapter)
        if hasattr(browser, '_last_url') and browser._last_url:
            results["url"] = browser._last_url
            log(f"Captured URL: {browser._last_url}")
        # Fallback: try to get current page URL via get_page_info or similar
        elif hasattr(browser, 'mcp'):
            try:
                page_info = await browser.mcp.call_tool('playwright_get_page_info', {})
                if page_info and 'url' in page_info:
                    results["url"] = page_info['url']
                    log(f"Captured URL via page_info: {page_info['url']}")
            except Exception:
                pass
    except Exception as e:
        log(f"Could not capture URL: {e}")

    log(f"Workflow completed successfully")
    return results


def get_workflow_by_name(name: str) -> Optional[Workflow]:
    """Get a workflow by its name"""
    for workflow in WORKFLOWS:
        if workflow.name == name:
            return workflow
    return None


def list_workflows() -> List[Dict[str, str]]:
    """
    List all available workflows with their descriptions.

    Returns:
        List of workflow info dictionaries
    """
    return [
        {
            "name": w.name,
            "description": w.description,
            "required_params": w.required_params
        }
        for w in WORKFLOWS
    ]


# Example usage for testing
if __name__ == "__main__":
    # Test workflow matching with natural language prompts
    test_prompts = [
        # FB Ads variations
        "Search Facebook ads for Nike shoes",
        "Find me advertisers on FB ads library",
        "meta ads for booked meetings",
        # LinkedIn variations
        "Find on LinkedIn software engineers in SF",
        "Search for SDRs on LinkedIn",
        "LinkedIn people who sell SaaS",
        # Reddit variations
        "Search Reddit for cryptocurrency discussions",
        "Find me leads on Reddit",
        "Look at r/sales for discussions",
        "Reddit users talking about lead gen",
        # Google Maps variations
        "Google Maps coffee shops in Seattle",
        "Find businesses near me",
        "Local restaurants in NYC",
        "Get companies near downtown",
        # Gmail variations
        "Open Gmail",
        "Check my email",
        "Read emails",
        # Navigation
        "Go to https://example.com"
    ]

    print("Testing prompt-based workflow matching:\n")
    for prompt in test_prompts:
        workflow = match_workflow(prompt)
        if workflow:
            params = extract_params(prompt, workflow)
            print(f"Prompt: {prompt}")
            print(f"  -> Workflow: {workflow.name}")
            print(f"  -> Params: {params}")
            print()
        else:
            print(f"Prompt: {prompt}")
            print(f"  -> No matching workflow")
            print()

    # Test URL-based workflow matching
    test_urls = [
        "https://www.facebook.com/ads/library/?active_status=active&ad_type=all",
        "https://www.linkedin.com/search/results/people/?keywords=software%20engineer",
        "https://www.reddit.com/search/?q=cryptocurrency",
        "https://www.google.com/maps/search/coffee+shops+seattle",
        "https://mail.google.com/mail/u/0/#inbox",
        "https://www.example.com"
    ]

    print("\n\nTesting URL-based workflow auto-selection:\n")
    for url in test_urls:
        workflow = match_workflow_from_url(url)
        if workflow:
            print(f"URL: {url}")
            print(f"  -> Auto-selected workflow: {workflow.name}")
            print()
        else:
            print(f"URL: {url}")
            print(f"  -> No workflow auto-selected")
            print()

    # Test combined matching (URL takes priority)
    print("\n\nTesting combined matching (URL-based + prompt-based):\n")
    test_cases = [
        ("extract data", "https://www.facebook.com/ads/library/"),
        ("search for coffee", "https://www.google.com/maps/"),
        ("find engineers", None),
    ]

    for prompt, url in test_cases:
        workflow = match_workflow(prompt, current_url=url)
        if workflow:
            print(f"Prompt: '{prompt}' | URL: {url}")
            print(f"  -> Selected workflow: {workflow.name}")
            print()
        else:
            print(f"Prompt: '{prompt}' | URL: {url}")
            print(f"  -> No workflow selected")
            print()
