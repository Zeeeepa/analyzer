#!/usr/bin/env python3
"""
Eversale Agentic Browser v2 - Browser automation agent.

Fast, deterministic workflows for known sites.
Element refs for precise actions.
AI for complex analysis when needed.
"""

import os
import sys
import warnings

# Suppress Python runpy warning about module already in sys.modules
warnings.filterwarnings('ignore', message=".*found in sys.modules.*")

# =============================================================================
# LOGGING CONFIGURATION - Must be FIRST before any other imports
# =============================================================================
_DEBUG_MODE = '--debug' in sys.argv or '-d' in sys.argv or os.environ.get('EVERSALE_DEBUG', '').lower() in ('1', 'true')

from loguru import logger
logger.remove()  # Remove default stderr handler

# Create logs directory
from pathlib import Path
_log_dir = Path(os.environ.get('EVERSALE_HOME', os.path.expanduser('~/.eversale'))) / 'logs'
_log_dir.mkdir(parents=True, exist_ok=True)

# File logging always enabled
logger.add(str(_log_dir / 'eversale.log'), rotation="10 MB", level="DEBUG")

# stderr logging only in debug mode - production output stays clean
if _DEBUG_MODE:
    logger.add(sys.stderr, level="DEBUG", format="<dim>{time:HH:mm:ss}</dim> | {message}")

# Signal to submodules not to add handlers
os.environ['EVERSALE_LOGGING_CONFIGURED'] = '1'
# =============================================================================

import asyncio
import json
import logging
from pathlib import Path
from urllib.parse import quote_plus, urlparse
from typing import Dict, Any, List, Optional, Union

# Try importing Rich for beautiful output
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich import print as rprint
    RICH_AVAILABLE = True
    console = Console()
except ImportError:
    RICH_AVAILABLE = False
    console = None
    # Fallback for rprint if rich is not available
    def rprint(*args, **kwargs):
        print(*args, **kwargs)

try:
    import html2text
    h2t = html2text.HTML2Text()
    h2t.ignore_links = False
    h2t.ignore_images = True
except ImportError:
    h2t = None

# Re-add other necessary imports that were removed or modified
import re
import time
from dataclasses import dataclass
from typing import Callable # Keep Callable if it's used elsewhere

from .failure_modes import FailureMode

from .social_lead_criteria import (
    extract_icp_text,
    extract_keywords,
    has_explicit_date_window,
    parse_relative_date_window,
)
try:
    from .prompt_compiler import compile_prompt, should_enforce_exact_lines, extract_output_contract
except ImportError:
    # Basic fallback if module missing
    def compile_prompt(p): return {"prompt": p}
    def should_enforce_exact_lines(c): return None
    def extract_output_contract(p): return {}
from .site_router import suggest_sources
from .gpu_llm_client import get_gpu_client, GPU_MODELS # Import GPULLMClient
from .config_loader import load_config # Import config_loader
from .strategic_planner import get_strategic_planner, ExecutionState, create_plan_guided_prompt # Strategic Planner


def _get_package_version() -> str:
    """Read version from env var, version.txt, or package.json."""
    # First check env var (set by Node.js wrapper)
    env_version = os.environ.get('EVERSALE_VERSION')
    if env_version:
        return env_version

    # Second fallback - check ~/.eversale/version.txt (written by Node.js wrapper)
    try:
        eversale_home = os.environ.get('EVERSALE_HOME') or os.path.join(os.path.expanduser('~'), '.eversale')
        version_txt_path = Path(eversale_home) / 'version.txt'
        if version_txt_path.exists():
            version = version_txt_path.read_text().strip()
            if version:
                return version
    except Exception:
        pass

    # Third fallback - check package.json (dev environment)
    try:
        cli_root = Path(__file__).parent.parent.parent
        package_json_path = cli_root / "package.json"
        if package_json_path.exists():
            with open(package_json_path, 'r') as f:
                package_data = json.load(f)
                return package_data.get('version', '0.0.0')
    except Exception:
        pass

    return '0.0.0'


VERSION = _get_package_version()

# Try to import Kimi client for smart analysis
try:
    from .kimi_k2_client import KimiK2Client
    KIMI_AVAILABLE = True
except ImportError:
    KIMI_AVAILABLE = False

# Try to import RedditHandler for API-based extraction (faster than browser)
try:
    from .reddit_handler import RedditHandler, find_icp_profile_urls
    REDDIT_HANDLER_AVAILABLE = True
except ImportError:
    try:
        # Fallback for different import paths
        from reddit_handler import RedditHandler, find_icp_profile_urls
        REDDIT_HANDLER_AVAILABLE = True
    except ImportError:
        REDDIT_HANDLER_AVAILABLE = False

# Try to import DeepSearchEngine for Google fallback
try:
    from .deep_search_engine import DeepSearchEngine
    DEEP_SEARCH_AVAILABLE = True
except ImportError:
    DEEP_SEARCH_AVAILABLE = False

# Try to import AGI reasoning for automatic smart execution
try:
    from .agi_reasoning import (
        AGIReasoning, get_agi_reasoning, ProactiveGuard,
        reason_before_action, verify_action_success, get_smart_correction
    )
    AGI_REASONING_AVAILABLE = True
except ImportError:
    AGI_REASONING_AVAILABLE = False
    get_agi_reasoning = None

# Try to import AGI Core (full cognitive architecture)
try:
    from .agi_core import (
        CognitiveEngine, get_cognitive_engine, think_before_act,
        get_historical_success_rate, WorkingMemory, EpisodicMemory
    )
    AGI_CORE_AVAILABLE = True
except ImportError:
    AGI_CORE_AVAILABLE = False
    get_cognitive_engine = None

# Try to import output format handler for custom output formats
try:
    from .output_format_handler import format_output
    OUTPUT_FORMAT_AVAILABLE = True
except ImportError:
    OUTPUT_FORMAT_AVAILABLE = False
    format_output = None

# Subreddit targeting for common ICPs
ICP_SUBREDDITS = {
    # B2B / Agency keywords
    "lead generation": ["Entrepreneur", "startups", "smallbusiness", "marketing", "sales", "agency"],
    "agency": ["Entrepreneur", "marketing", "digitalmarketing", "SEO", "PPC", "agency"],
    "marketing": ["marketing", "digitalmarketing", "socialmedia", "content_marketing", "growthHacking"],
    "sales": ["sales", "B2B_Sales", "salesforce", "Entrepreneur", "startups"],
    "saas": ["SaaS", "startups", "Entrepreneur", "indiehackers", "microsaas"],
    "startup": ["startups", "Entrepreneur", "smallbusiness", "indiehackers", "venturecapital"],
    "entrepreneur": ["Entrepreneur", "startups", "smallbusiness", "sweatystartup", "EntrepreneurRideAlong"],
    "ecommerce": ["ecommerce", "shopify", "dropshipping", "FulfillmentByAmazon", "AmazonSeller"],
    "real estate": ["realestate", "RealEstateInvesting", "CommercialRealEstate", "realtors", "RealEstateTechnology"],
    "finance": ["FinancialCareers", "CFP", "personalfinance", "investing", "fintech"],
    "consulting": ["consulting", "BusinessConsulting", "Entrepreneur", "startups", "smallbusiness"],
    # Default fallback
    "default": ["Entrepreneur", "startups", "smallbusiness", "marketing", "sales"]
}

# Session storage
EVERSALE_HOME = Path(os.environ.get("EVERSALE_HOME", Path.home() / ".eversale"))
SESSION_DIR = EVERSALE_HOME / "sessions"
SESSION_DIR.mkdir(parents=True, exist_ok=True)

# Colors for terminal output
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    CYAN = "\033[36m"
    RED = "\033[31m"


# Animated activity indicator (shows the AI is working)
class ActivityIndicator:
    """
    Dynamic activity indicator that shows the AI is actively working.
    Cycles through different phases to feel alive and fast-moving.
    """
    THINKING_PHASES = [
        "Analyzing task",
        "Planning approach",
        "Reasoning",
        "Deciding next step",
    ]
    BROWSER_PHASES = [
        "Loading page",
        "Reading content",
        "Finding elements",
        "Processing data",
    ]
    # Cycle: 1 dot, 2 dots, 3 dots, 0 dots (as requested)
    DOTS = [".", "..", "...", ""]

    def __init__(self, phase: str = "thinking"):
        self.phase = phase
        self._running = False
        self._thread = None
        self._frame = 0
        self._message_idx = 0
        self._start_time = 0

    def start(self):
        """Start the activity animation."""
        import threading
        self._running = True
        self._start_time = time.time()
        self._thread = threading.Thread(target=self._animate, daemon=True)
        self._thread.start()

    def _get_phases(self):
        if self.phase == "browser":
            return self.BROWSER_PHASES
        return self.THINKING_PHASES

    def _animate(self):
        """Animation loop - cycles through phases."""
        while self._running:
            phases = self._get_phases()
            msg = phases[self._message_idx % len(phases)]
            dots = self.DOTS[self._frame % len(self.DOTS)]
            # Pad dots to ensure consistent length so we don't have trailing characters from previous frames
            # Max length is 3 dots, so pad to length 3 with spaces if needed
            dots_padded = f"{dots:<3}"
            
            elapsed = time.time() - self._start_time

            # Show elapsed time after 2 seconds
            time_str = f" [{elapsed:.0f}s]" if elapsed > 2 else ""

            # \033[K clears the rest of the line to handle varying string lengths cleanly
            sys.stdout.write(f"\r{Colors.CYAN}  > {msg}{dots_padded}{Colors.DIM}{time_str}{Colors.RESET}\033[K")
            sys.stdout.flush()

            self._frame += 1
            # Change message every ~1.5 seconds
            if self._frame % 5 == 0:
                self._message_idx += 1
            time.sleep(0.3)

    def stop(self, clear: bool = True):
        """Stop the indicator."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=0.5)
        if clear:
            sys.stdout.write("\r" + " " * 50 + "\r")
            sys.stdout.flush()

    def set_phase(self, phase: str):
        """Switch to a different phase (thinking, browser)."""
        self.phase = phase
        self._message_idx = 0


# Fast-moving spinner for ADHD-friendly feedback (never looks stuck)
class LiveSpinner:
    """
    Constantly-moving spinner that shows the AI is working.
    Updated to use dot animation as requested: . -> .. -> ... -> (empty)
    """
    # Cycle: 1 dot, 2 dots, 3 dots, 0 dots
    DOTS = [".", "..", "...", ""]

    def __init__(self, message: str = "Working"):
        self.message = message
        self._running = False
        self._thread = None
        self._frame = 0
        self._start_time = 0
        self._items_found = 0
        self._lock = None

    def start(self, message: str = None):
        """Start the spinner animation."""
        import threading
        if message:
            self.message = message
        self._running = True
        self._start_time = time.time()
        self._frame = 0
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._animate, daemon=True)
        self._thread.start()

    def update(self, message: str = None, items: int = None):
        """Update the spinner message or item count."""
        if self._lock:
            with self._lock:
                if message:
                    self.message = message
                if items is not None:
                    self._items_found = items

    def _animate(self):
        """Animation loop - cycles through dots."""
        while self._running:
            dots = self.DOTS[self._frame % len(self.DOTS)]
            # Pad to length 3 to prevent trailing characters
            dots_padded = f"{dots:<3}"
            
            elapsed = time.time() - self._start_time

            # Build status line
            items_str = f" | {self._items_found} found" if self._items_found > 0 else ""
            time_str = f" [{elapsed:.0f}s]" if elapsed > 1 else ""

            # Clear line and write spinner: "  > Message..."
            line = f"\r{Colors.CYAN}  > {self.message}{dots_padded}{Colors.RESET}{Colors.DIM}{items_str}{time_str}{Colors.RESET}\033[K"
            sys.stdout.write(line)
            sys.stdout.flush()

            self._frame += 1
            time.sleep(0.3)

            self._frame += 1
            time.sleep(0.1)  # 10 FPS - fast enough to never look stuck

    def stop(self, final_message: str = None):
        """Stop the spinner with optional final message."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=0.3)
        # Clear the spinner line
        sys.stdout.write("\r" + " " * 80 + "\r")
        sys.stdout.flush()
        if final_message:
            print(f"{Colors.GREEN}+{Colors.RESET} {final_message}")


# Global spinner instance for use across the codebase
_global_spinner = None

def start_spinner(message: str = "Working"):
    """Start the global spinner."""
    global _global_spinner
    if _global_spinner is None:
        _global_spinner = LiveSpinner(message)
    _global_spinner.start(message)

def update_spinner(message: str = None, items: int = None):
    """Update the global spinner."""
    global _global_spinner
    if _global_spinner:
        _global_spinner.update(message, items)

def stop_spinner(final_message: str = None):
    """Stop the global spinner."""
    global _global_spinner
    if _global_spinner:
        _global_spinner.stop(final_message)
        _global_spinner = None


def clean_llm_output(text: str) -> str:
    """
    Clean raw LLM output by removing action markers and formatting noise.
    Removes patterns like 'Action: talk', 'Action: finished', etc.
    """
    if not text:
        return ""

    import re

    # Remove action markers
    patterns_to_remove = [
        r'\nAction:\s*\w+',           # Action: talk, Action: finished, etc.
        r'Action:\s*\w+\n?',          # Same at start of line
        r'You are an AI assistant\n?', # LLM self-identification
        r'\[Interrupted\].*',         # Interrupt messages
    ]

    result = text
    for pattern in patterns_to_remove:
        result = re.sub(pattern, '', result, flags=re.IGNORECASE)

    # Clean up excessive whitespace
    result = re.sub(r'\n{3,}', '\n\n', result)  # Max 2 newlines
    result = result.strip()

    return result


def print_step(step: int, action: str, target: str, status: str = "running", details: str = None):
    """
    Print action step with dynamic, alive output.
    Shows what the AI is doing in real-time.
    """
    if getattr(print_step, "_quiet", False):
        return

    # Action icons - make it feel alive
    icons = {
        "running": f"{Colors.YELLOW}>{Colors.RESET}",
        "success": f"{Colors.GREEN}+{Colors.RESET}",
        "error": f"{Colors.RED}x{Colors.RESET}"
    }
    icon = icons.get(status, ">")

    # Map engine action to descriptive action verbs
    action_verbs = {
        "navigate": ("Opening", "URL"),
        "click": ("Clicking", "element"),
        "type": ("Typing", "text"),
        "press": ("Pressing", "key"),
        "scroll": ("Scrolling", "page"),
        "extract": ("Extracting", "data"),
        "done": ("Completed", "task"),
        "prepare": ("Preparing", "page"),
        "thinking": ("Thinking", "about next step"),
        "analyzing": ("Analyzing", "page content"),
    }

    verb, noun = action_verbs.get(action, (action.capitalize(), ""))

    # Format the target for display
    display_target = target
    if target and len(target) > 60:
        display_target = target[:57] + "..."

    # Print the action line
    if display_target:
        print(f"\n{icon} {Colors.BOLD}{verb}{Colors.RESET} {Colors.DIM}{display_target}{Colors.RESET}")
    else:
        print(f"\n{icon} {Colors.BOLD}{verb}{Colors.RESET}")

    # Show details on separate line if provided
    if details:
        print(f"  {Colors.DIM}{details}{Colors.RESET}")

def format_yaml_snapshot(element_refs: Dict[str, Any]) -> str:
    """Format element references as a YAML accessibility tree like Playwright MCP."""
    if not element_refs:
        return "  (No interactive elements found)"
    
    lines = ["```yaml"]
    for ref, data in element_refs.items():
        role = data.get('type', 'element')
        text = (data.get('text', '') or '').strip()
        placeholder = (data.get('placeholder', '') or '').strip()
        label = (data.get('label', '') or '').strip()
        display_text = text or placeholder or label
        # Clean text
        display_text = (display_text[:40] + "..") if len(display_text) > 40 else display_text
        text_str = f'"{display_text}"' if display_text else ""
        
        lines.append(f"- {role} {text_str} [ref={ref}]")
    lines.append("```")
    return "\n".join(lines)


class AgenticBrowser:
    """
    Playwright MCP-style browser automation.

    Hybrid approach:
    - Deterministic workflows for extraction (FAST)
    - Kimi for ICP analysis in parallel (SMART)
    - Best of both worlds
    """

    def __init__(self, headless: bool = True, debug: bool = False, use_kimi: bool = True, direct_mode: bool = True,
                 session_file: str = None, save_session_path: str = None, 
                 video_dir: str = None, trace_path: str = None, max_steps: int = 8):
        self.headless = headless
        self.debug = debug
        self.use_kimi = use_kimi and KIMI_AVAILABLE
        self.direct_mode = direct_mode  # True = follow exact directions like Playwright MCP
        self.session_file = session_file
        self.save_session_path = save_session_path
        self.video_dir = video_dir
        self.trace_path = trace_path
        self.max_steps = max_steps
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.step = 0
        self.results = []
        self.element_refs = {}  # ref_id -> selector mapping
        self.kimi = None

        # Initialize Recovery Engine
        from .recovery_engine import RecoveryEngine
        self.recovery = None # Will be initialized once browser is connected

        # Initialize GPU LLM Client
        self.config = load_config()
        self.gpu_client = get_gpu_client(
            base_url=self.config.get("llm", {}).get("base_url"),
            license_key=self.config.get("llm", {}).get("api_key")
        )

        # Initialize Strategic Planner
        self.strategic_planner = get_strategic_planner(self.config)
        self.current_execution_state: Optional[ExecutionState] = None

        # Playwright MCP-style state tracking
        self._previous_snapshot = None
        self._snapshot_mode = 'incremental'
        self._console_messages = []
        self._network_requests = []

        # Initialize browser optimization modules
        from .token_optimizer import create_optimizer
        from .devtools_hooks import DevToolsHooks
        from .visual_grounding import get_engine as get_visual_engine
        try:
            from .history_pruner import HistoryPruner
            self.history_pruner = HistoryPruner(max_history_items=10)
        except ImportError:
            self.history_pruner = None

        self.visual_engine = get_visual_engine()
        self.token_optimizer = create_optimizer(
            max_elements=140,  # Match MAX_ELEMENTS in snapshot
            max_text_length=200,
            token_budget=8000
        )
        self.devtools = None  # Lazy init when page is available
        self.snapshot_first = True  # Default to snapshot mode over screenshots
        self._last_snapshot = None
        self._last_snapshot_hash = None
        self._last_action_type = None

        logger.debug("Browser optimizations enabled: TokenOptimizer + DevToolsHooks + snapshot-first mode")

        # Initialize Kimi client if available and enabled
        if self.use_kimi:
            try:
                self.kimi = KimiK2Client()
            except Exception:
                self.kimi = None
                self.use_kimi = False

    async def _maybe_init_devtools(self):
        """Lazy initialize DevTools hooks when page becomes available."""
        if self.devtools is None and self.page:
            from .devtools_hooks import DevToolsHooks
            self.devtools = DevToolsHooks(self.page, max_network_entries=500)
            await self.devtools.start_capture(network=True, console=True)
            logger.debug("DevTools hooks initialized and capturing")

    def _should_use_cached_snapshot(self, action_type: str) -> bool:
        """Check if we should use cached snapshot based on action type."""
        if not self._last_snapshot or not self.token_optimizer:
            return False
        return not self.token_optimizer.should_resnapshot(action_type)

    def _update_action_tracking(self, action_type: str):
        """Track last action type for snapshot caching logic."""
        self._last_action_type = action_type

    def get_optimization_stats(self) -> Dict[str, Any]:
        """Get statistics about browser optimizations (token savings, cache hits, etc.)."""
        stats = {
            "optimizations_enabled": True,
            "snapshot_first_mode": self.snapshot_first,
        }

        # Token optimizer stats
        if self.token_optimizer:
            stats["token_optimizer"] = self.token_optimizer.get_stats()

        # DevTools summary
        if self.devtools:
            stats["devtools"] = self.devtools.summary()

        return stats

    async def get_page_diagnostics(self) -> Dict[str, Any]:
        """Get page diagnostics (errors, failed requests, slow requests) from DevTools."""
        if not self.devtools:
            return {"error": "DevTools not initialized"}

        diagnostics = {
            "failed_requests": self.devtools.get_failed_requests(),
            "console_errors": self.devtools.get_console_log(level="error"),
            "page_errors": self.devtools.get_errors(),
            "slow_requests": self.devtools.get_slow_requests(threshold_ms=3000),
            "blocked_resources": self.devtools.get_blocked_resources(),
        }

        return diagnostics

    async def analyze_icp_fit(self, lead: Dict, icp_description: str) -> Dict:
        """Use Kimi to analyze if a lead matches ICP. Returns lead with score."""
        if not self.kimi:
            # Fallback to keyword-based scoring
            lead['icp_score'] = 70 if lead.get('has_icp_signal') else 30
            return lead

        prompt = f"""Analyze if this person is a good prospect for: {icp_description}

Lead info:
- Username: {lead.get('username', '')}
- Post title: {lead.get('title', '')}
- Content: {lead.get('content', '')}
- Subreddit: {lead.get('subreddit', '')}

Return ONLY a JSON object: {{"score": 0-100, "reason": "one sentence why"}}
Score 80+ = hot lead, 50-79 = warm, <50 = not a fit"""

        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(self.kimi.chat, prompt),
                timeout=5.0  # 5 second timeout per lead
            )
            # Parse JSON from response
            import json
            match = re.search(r'\{[^}]+\}', response)
            if match:
                result = json.loads(match.group())
                lead['icp_score'] = result.get('score', 50)
                lead['icp_reason'] = result.get('reason', '')
        except Exception:
            lead['icp_score'] = 70 if lead.get('has_icp_signal') else 30

        return lead

    async def analyze_leads_parallel(self, leads: List[Dict], icp: str) -> List[Dict]:
        """Analyze multiple leads in parallel with Kimi."""
        if not leads:
            return leads

        # Analyze all leads in parallel (fast!)
        tasks = [self.analyze_icp_fit(lead, icp) for lead in leads]
        analyzed = await asyncio.gather(*tasks)

        # Sort by ICP score
        analyzed.sort(key=lambda x: x.get('icp_score', 0), reverse=True)
        return analyzed

    def _looks_like_social_lead_prompt(self, prompt_lower: str) -> bool:
        if not prompt_lower:
            return False

        lead_words = (
            "lead", "leads", "prospect", "prospects", "warm lead", "warm leads",
            "icp", "ideal customer", "outreach", "appointment", "appointments",
            "booked", "meetings", "pipeline", "persona", "target audience",
        )
        social_words = (
            "post", "posts", "comment", "comments", "thread", "threads", "subreddit", "subreddits",
            "engaged", "engagement", "interacting", "interaction", "participants",
            "talking about", "discussing", "asking about", "recommendations", "social media",
            "reddit", "linkedin", "facebook", "tiktok", "instagram", "ads library",
        )
        return any(w in prompt_lower for w in lead_words) and any(w in prompt_lower for w in social_words)

    async def _classify_social_lead_workflow(self, prompt: str) -> Dict[str, Any]:
        """
        Choose the best workflow for a social lead prompt when the user didn't specify a platform.
        """
        from .platform_data import PLATFORM_INDICATORS
        prompt_lower = (prompt or "").lower()
        requested_count = self._extract_requested_count(prompt) or 0

        # Data-driven classification
        from .platform_data import PLATFORM_INDICATORS, PLATFORM_REDDIT, PLATFORM_FB_ADS, PLATFORM_LINKEDIN
        for platform_name, platform_data in PLATFORM_INDICATORS.items():
            if any(k in prompt_lower for k in platform_data["keywords"]):
                workflow = platform_data["workflow"]
                if platform_data.get("default_topic"):
                    icp_text = extract_icp_text(prompt)
                    topic = " ".join(extract_keywords(icp_text or prompt)[:6]) if (icp_text or prompt) else platform_data["default_topic"]
                    return {"workflow": workflow, "topic": topic, "count": requested_count, "prompt": prompt}
                else:
                    query = platform_data.get("default_query", "SDR")
                    return {"workflow": workflow, "query": query, "prompt": prompt, "count": requested_count}

        # Ambiguous: use one Kimi call if available, otherwise default to first platform (generic)
        if not self.kimi:
            default_platform = list(PLATFORM_INDICATORS.keys())[0]
            data = PLATFORM_INDICATORS[default_platform]
            icp_text = extract_icp_text(prompt)
            topic = " ".join(extract_keywords(icp_text or prompt)[:6]) if (icp_text or prompt) else data.get("default_topic", "leads")
            return {"workflow": data["workflow"], "topic": topic, "count": requested_count, "prompt": prompt, "fallback": "heuristic_default"}

        kimi_prompt = (
            "Pick the best platform workflow for this request.\n"
            "Return ONLY JSON with keys: workflow, topic_or_query.\n"
            "workflow must be one of: reddit, linkedin_warm, linkedin, fb_ads.\n"
            "If reddit: topic_or_query should be a short search topic.\n"
            "If linkedin_warm: topic_or_query should be a short keyword query.\n"
            "If fb_ads: topic_or_query should be the ads library search query.\n\n"
            f"User prompt: {prompt}\n"
        )

        try:
            response = await asyncio.wait_for(asyncio.to_thread(self.kimi.chat, kimi_prompt), timeout=5.0)
            m = re.search(r"\{.*\}", response, flags=re.DOTALL)
            if m:
                data = json.loads(m.group(0))
                wf = (data.get("workflow") or "").strip()
                topic_or_query = (data.get("topic_or_query") or "").strip()
                if wf in [d["workflow"] for d in PLATFORM_INDICATORS.values()]:
                    from .platform_data import PLATFORM_INDICATORS, PLATFORM_REDDIT, PLATFORM_FB_ADS
                    # Find platform by workflow
                    platform_data = next((d for d in PLATFORM_INDICATORS.values() if d["workflow"] == wf), None)
                    # Find platform_name by workflow
                    platform_name = next((name for name, d in PLATFORM_INDICATORS.items() if d["workflow"] == wf), None)
                    
                    if platform_data:
                        if platform_data.get("default_topic") and not topic_or_query:
                            icp_text = extract_icp_text(prompt)
                            topic_or_query = " ".join(extract_keywords(icp_text or prompt)[:6]) or platform_data["default_topic"]
                        elif platform_data.get("default_query") and not topic_or_query:
                            topic_or_query = platform_data["default_query"]
                            
                    return {"workflow": wf, "topic": topic_or_query, "query": topic_or_query, "prompt": prompt, "count": requested_count, "fallback": "kimi"}
        except Exception:
            pass

        icp_text = extract_icp_text(prompt)
        topic = " ".join(extract_keywords(icp_text or prompt)[:6]) if (icp_text or prompt) else "lead generation"
        return {"workflow": "reddit", "topic": topic, "count": requested_count, "prompt": prompt, "fallback": "kimi_failed"}

    def _is_vague_icp(self, icp_text: Optional[str], keywords: List[str]) -> bool:
        if not icp_text:
            return False
        if len((icp_text or "").split()) <= 3:
            return True
        return len(keywords) < 4

    def _heuristic_expand_keywords(self, icp_text: str) -> List[str]:
        t = (icp_text or "").lower()
        expansions: List[str] = []

        if "dentist" in t or "dental" in t:
            expansions.extend([
                "dental practice",
                "dentistry",
                "orthodontist",
                "dds",
                "dmd",
                "hygienist",
                "patients",
                "insurance billing",
                "new patient",
            ])

        return expansions

    async def expand_keywords(self, icp_text: Optional[str], base_keywords: List[str]) -> List[str]:
        """
        Expand keywords/intent phrases for vague ICPs.

        - Uses exactly 1 Kimi call when available and ICP is vague
        - Falls back to heuristic expansions when Kimi is unavailable
        """
        if not icp_text:
            return base_keywords

        keywords = list(base_keywords)

        if not self._is_vague_icp(icp_text, keywords):
            return keywords

        for kw in self._heuristic_expand_keywords(icp_text):
            if kw.lower() not in {k.lower() for k in keywords}:
                keywords.append(kw)

        if not self.kimi:
            return keywords[:20]

        prompt = (
            "Generate 10-20 search phrases and synonyms for this ICP. "
            "Return ONLY JSON: {\"phrases\": [\"...\"]}. No extra text.\n\n"
            f"ICP: {icp_text}\n\n"
            "Rules:\n"
            "- Mix synonyms, job titles, and intent phrases.\n"
            "- Keep phrases short (2-6 words).\n"
        )

        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(self.kimi.chat, prompt),
                timeout=6.0
            )
            m = re.search(r"\{.*\}", response, flags=re.DOTALL)
            if m:
                data = json.loads(m.group(0))
                phrases = data.get("phrases") or []
                if isinstance(phrases, list):
                    for phrase in phrases:
                        if not isinstance(phrase, str):
                            continue
                        phrase = phrase.strip()
                        if not phrase:
                            continue
                        if phrase.lower() not in {k.lower() for k in keywords}:
                            keywords.append(phrase)
        except Exception:
            pass

        return keywords[:20]

    def _reddit_thread_url_from_comment_url(self, comment_url: str) -> Optional[str]:
        if not comment_url:
            return None
        m = re.search(r"(https?://[^/]+/r/[^/]+/comments/[^/]+/[^/]+/)", comment_url)
        return m.group(1) if m else None

    async def _reddit_pullpush_warm_leads(
        self,
        handler: "RedditHandler",
        topic: str,
        subreddits: List[str],
        keywords: List[str],
        after_utc: int,
        before_utc: int,
        max_leads: int,
    ) -> List[Dict[str, Any]]:
        phrases = [k for k in keywords if k and len(k) >= 3][:10]
        if not phrases:
            return []

        q = " OR ".join([f"\"{p}\"" if " " in p else p for p in phrases])

        comment_hits: List[Any] = []
        for sub in subreddits[:3]:
            try:
                res = await handler.search_pullpush(
                    query=q,
                    subreddit=sub,
                    after=after_utc,
                    before=before_utc,
                    limit=100,
                    content_type="comment",
                )
                if res.get("success"):
                    comment_hits.extend(res.get("items", []))
            except Exception:
                continue

        if not comment_hits:
            try:
                res = await handler.search_pullpush(
                    query=q,
                    subreddit=None,
                    after=after_utc,
                    before=before_utc,
                    limit=100,
                    content_type="comment",
                )
                if res.get("success"):
                    comment_hits.extend(res.get("items", []))
            except Exception:
                pass

        best_by_user: Dict[str, Dict[str, Any]] = {}
        for c in comment_hits:
            author = getattr(c, "author", None) or ""
            if not author or author in ("[deleted]", "AutoModerator") or author.lower().endswith("bot"):
                continue

            body = getattr(c, "body", "") or ""
            permalink = getattr(c, "permalink", "") or ""
            score = int(getattr(c, "score", 0) or 0)
            created_utc = int(getattr(c, "created_utc", 0) or 0)

            matched = [k for k in phrases if (k.lower() in body.lower())]
            if not matched:
                continue

            from .platform_data import PLATFORM_INDICATORS, PLATFORM_REDDIT, COMMON_TLDS
            reddit_base = next((k for k, v in PLATFORM_INDICATORS.items() if v["workflow"] == PLATFORM_REDDIT), "reddit" + COMMON_TLDS[0])
            if not reddit_base.endswith(COMMON_TLDS[0]): reddit_base = "reddit" + COMMON_TLDS[0]
            
            comment_url = permalink if permalink.startswith("http") else f"https://{reddit_base}{permalink}"
            thread_url = self._reddit_thread_url_from_comment_url(comment_url)

            evidence = {
                "type": "comment",
                "comment_url": comment_url,
                "thread_url": thread_url,
                "created_utc": created_utc,
                "score": score,
                "matched_keywords": matched[:6],
                "snippet": (body[:240].replace("\n", " ")),
                "verified": False,
            }

            cur = best_by_user.get(author)
            if not cur:
                best_by_user[author] = {
                    "username": author,
                    "url": f"https://{reddit_base}/user/{author}",
                    "profile_url": f"https://{reddit_base}/user/{author}",
                    "evidence_url": comment_url,
                    "subreddit": getattr(c, "subreddit", "") or "",
                    "icp_match_score": (len(matched) * 12) + min(score, 10),
                    "matched_keywords": list({m.lower(): m for m in matched}.values()),
                    "evidence": [evidence],
                    "source": "pullpush",
                }
                continue

            new_score = (len(matched) * 12) + min(score, 10)
            if new_score > cur.get("icp_match_score", 0):
                cur["icp_match_score"] = new_score
                cur["evidence_url"] = comment_url
            cur["evidence"].append(evidence)
            cur["matched_keywords"] = sorted(
                list({k.lower(): k for k in (cur.get("matched_keywords", []) + matched)}.values()),
                key=lambda s: s.lower()
            )

        leads = list(best_by_user.values())
        leads.sort(key=lambda x: x.get("icp_match_score", 0), reverse=True)
        leads = leads[: max_leads * 2]

        verify_budget = min(8, max_leads * 2)
        verified = 0

        for lead in leads:
            for ev in lead.get("evidence", [])[:3]:
                if verified >= verify_budget:
                    break
                thread_url = ev.get("thread_url")
                if not thread_url:
                    continue
                try:
                    post_res = await handler.get_post_json(thread_url, comment_limit=200)
                    if not post_res.get("success"):
                        continue
                    post = post_res.get("post")
                    if post:
                        lead["title"] = getattr(post, "title", "") or lead.get("title", "")
                        lead["subreddit"] = getattr(post, "subreddit", "") or lead.get("subreddit", "")
                    for rc in post_res.get("comments", [])[:200]:
                        if getattr(rc, "author", "") != lead["username"]:
                            continue
                        if ev["snippet"] and ev["snippet"][:40].lower() in (getattr(rc, "body", "") or "").lower():
                            ev["verified"] = True
                            ev["comment_url"] = getattr(rc, "permalink", ev["comment_url"])
                            break
                    verified += 1
                except Exception:
                    continue

        final_leads = [l for l in leads if l.get("evidence")]
        return final_leads[:max_leads]

    # =========================================================================
    # SETUP
    # =========================================================================

    async def setup(self):
        """Initialize Playwright and Browser with session persistence."""
        try:
            from patchright.async_api import async_playwright
            logger.info("Using Patchright for stealth (Automatic)")
        except ImportError:
            from playwright.async_api import async_playwright
            logger.info("Using standard Playwright (Patchright not found)")
        self.playwright = await async_playwright().start()
        
        # Use session storage for persistence (Goodies like 'Remember Me')
        storage_path = SESSION_DIR / "default_browser_state.json"
        
            # Advanced Stealth Arguments
        # These flags mute common automation signals used by bot detectors (Cloudflare, Akamai etc.)
        stealth_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-infobars",
            "--exclude-switches=enable-automation",
            "--use-fake-ui-for-media-stream",
            "--use-fake-device-for-media-stream",
            "--disable-background-networking",
            "--enable-features=NetworkService,NetworkServiceInProcess",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-breakpad",
            "--disable-client-side-phishing-detection",
            "--disable-component-extensions-with-background-pages",
            "--disable-default-apps",
            "--disable-extensions",
            "--disable-features=Translate",
            "--disable-hang-monitor",
            "--disable-ipc-flooding-protection",
            "--disable-popup-blocking",
            "--disable-prompt-on-repost",
            "--disable-renderer-backgrounding",
            "--disable-sync",
            "--force-color-profile=srgb",
            "--metrics-recording-only",
            "--no-first-run",
            "--password-store=basic",
            "--use-mock-keychain",
        ]

        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=stealth_args
        )
        
        # Fingerprint Rotation (Stealth)
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
        ]
        
        # Randomize slightly to avoid fixed patterns
        import random
        width = 1280 + random.randint(-40, 40)
        height = 800 + random.randint(-40, 40)
        user_agent = random.choice(user_agents)

        # Load existing state if available
        launch_args = {
            "viewport": {"width": width, "height": height},
            "user_agent": user_agent,
            "device_scale_factor": random.choice([1, 2]),
            "has_touch": random.choice([True, False]),
        }
        
        # Priority: Explicit session file > Default session file
        state_to_load = None
        
        if hasattr(self, 'session_file') and self.session_file:
            # Check if absolute path or relative to CWD
            custom_path = Path(self.session_file)
            if custom_path.exists():
                state_to_load = custom_path
            else:
                # Check relative to SESSION_DIR
                session_dir_path = SESSION_DIR / self.session_file
                if session_dir_path.exists():
                    state_to_load = session_dir_path
                else:
                    logger.warning(f"Session file not found: {self.session_file}")
        elif storage_path.exists():
            state_to_load = storage_path
            
        if state_to_load:
            logger.info(f"Loading session state from: {state_to_load}")
            launch_args["storage_state"] = str(state_to_load)
            
        if self.video_dir:
            launch_args["record_video_dir"] = self.video_dir
            launch_args["record_video_size"] = {"width": 1280, "height": 800}

        self.context = await self.browser.new_context(**launch_args)
        
        # Start Tracing if requested
        if self.trace_path:
            await self.context.tracing.start(screenshots=True, snapshots=True, sources=True)
            logger.info(f"Tracing enabled -> {self.trace_path}")

        self.page = await self.context.new_page()

        # Initialize recovery engine with active page
        from .recovery_engine import RecoveryEngine
        self.recovery = RecoveryEngine(self.page)

        # Initialize Human Cursor (Stealth)
        try:
            from .humanization.bezier_cursor import BezierCursor
            self.cursor = BezierCursor()
            logger.info("Human-like mouse movement enabled 🖱️")
        except ImportError:
            self.cursor = None
            logger.warning("Humanization deps (scipy/numpy) not found - using standard mouse")

        # Initialize DevTools hooks for network/console monitoring
        await self._maybe_init_devtools()

        logger.info(f"AgenticBrowser initialized (headless={self.headless}, persistence=True, optimizations=enabled)")

    async def save_session(self, path: str = None):
        """Save current browser state (cookies, local storage) to file."""
        target_path = Path(path) if path else (Path(self.save_session_path) if self.save_session_path else None)
        
        if not target_path:
            return

        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            await self.context.storage_state(path=str(target_path))
            logger.info(f"Session saved to: {target_path}")
        except Exception as e:
            logger.error(f"Failed to save session to {target_path}: {e}")

    async def close(self):
        """Clean up and close browser resources."""
        # Auto-save if path provided
        if hasattr(self, 'save_session_path') and self.save_session_path and self.context:
            await self.save_session(self.save_session_path)
            
        if self.recovery:
            pass  # cleanup if needed
            
        # Close tracing
        if hasattr(self, 'trace_path') and self.trace_path and self.context:
            await self.context.tracing.stop(path=self.trace_path)
            logger.info(f"Trace saved to {self.trace_path}")

        if self.context:
            await self.context.close()
        
        if self.browser:
            await self.browser.close()
            
        if self.playwright:
            await self.playwright.stop()
        if self.gpu_client:
            await self.gpu_client.close() # Close GPU client session

    # =========================================================================
    # BROWSER ACTIONS - Playwright MCP style with refs
    # =========================================================================

    async def _run_with_recovery(self, coro_func, *args, hints: Optional[Any] = None, **kwargs):
        """Helper to run a coroutine with automatic recovery and escalation."""
        from .failure_modes import SITE_HINTS
        from .failure_modes import FailureMode
        
        # 1. Automatic Hint Discovery
        if hints is None and self.page:
            try:
                current_url = self.page.url
                domain = urlparse(current_url).netloc.replace('www.', '')
                hints = next((v for k, v in SITE_HINTS.items() if k in domain), None)
            except: pass

        def _classify_block_reason(modes: List[FailureMode]) -> str:
            if not modes:
                return "blocked"
            if FailureMode.CAPTCHA_PRESENT in modes:
                return "captcha"
            if FailureMode.BOT_DETECTED in modes:
                return "bot"
            if FailureMode.GEO_BLOCKED in modes:
                return "geo"
            if FailureMode.AUTH_REQUIRED in modes or FailureMode.MFA_REQUIRED in modes:
                return "auth"
            if FailureMode.RATE_LIMITED in modes:
                return "rate_limited"
            if FailureMode.OVERLAY_BLOCKING_INTERACTION in modes:
                return "overlay"
            return "blocked"

        async def _blocked_result(error: str) -> Dict[str, Any]:
            screenshot_path = f"logs/failure_{int(time.time())}.png"
            os.makedirs("logs", exist_ok=True)
            try:
                await self.page.screenshot(path=screenshot_path)
            except Exception:
                screenshot_path = ""

            modes = getattr(self.recovery, "last_detected_modes", []) or []
            block_reason = _classify_block_reason(modes)
            telemetry = []
            try:
                telemetry = self.recovery.get_latest_telemetry()
            except Exception:
                telemetry = []

            return {
                "status": "blocked",
                "error": error,
                "needs_intervention": True,
                "screenshot": screenshot_path,
                "url": self.page.url if self.page else "",
                "block_reason": block_reason,
                "detected_modes": [m.value for m in modes] if modes else [],
                "recovery_telemetry": telemetry,
            }

        try:
            # First attempt
            result = await coro_func(*args, **kwargs)
            # 2. Post-action Health Check
            pipeline_success = await self.recovery.run_pipeline(hints)
            if pipeline_success:
                try:
                    self.recovery.get_latest_telemetry()  # clear
                except Exception:
                    pass
                return result

            modes = getattr(self.recovery, "last_detected_modes", []) or []
            reason = _classify_block_reason(modes)
            return await _blocked_result(f"Blocked ({reason}). User intervention required.")
        except Exception as e:
            # 3. Trigger Recovery Pipeline on Exception
            logger.info(f"Action failed ({e}). Triggering recovery pipeline...")
            
            recovery_success = await self.recovery.run_pipeline(hints)
            
            if recovery_success:
                # Step 2: Retry the original action once
                try:
                    return await coro_func(*args, **kwargs)
                except Exception as e2:
                    logger.error(f"Recovery successful but action still failed on retry: {e2}")
            
            # Structured Escalation (HITL)
            err = str(e) if e else "Action failed"
            return await _blocked_result(err)

    async def navigate(self, url: str, hints: Optional[Any] = None) -> Dict:
        """Navigate to URL - simple and reliable like v2.1.171."""
        if not url.startswith('http'):
            url = 'https://' + url

        try:
            await self.page.goto(url, wait_until='domcontentloaded', timeout=30000)
        except Exception as e:
            # Auto-fix: try appending a common TLD if it looks like a bare domain
            err_str = str(e)
            if "ERR_NAME_NOT_RESOLVED" in err_str:
                parts = url.split("//")
                if len(parts) > 1:
                    domain_part = parts[1].split("/")[0]
                    from .platform_data import COMMON_TLDS
                    if "." not in domain_part or not any(domain_part.endswith(t) for t in COMMON_TLDS):
                        print(f"  {Colors.YELLOW}Retrying with .com...{Colors.RESET}")
                        new_url = url.replace(domain_part, domain_part + ".com")
                        await self.page.goto(new_url, wait_until='domcontentloaded', timeout=30000)
                        await asyncio.sleep(1.5)
                        self._update_action_tracking('navigate')
                        return {"action": "navigate", "url": new_url}
            # Re-raise if not a domain resolution issue
            raise e

        await asyncio.sleep(1.5)
        self._update_action_tracking('navigate')  # Track for snapshot caching
        return {"action": "navigate", "url": url}

    async def click_ref(self, ref: str) -> Dict:
        """Click element by ref (like Playwright MCP)."""
        if ref in self.element_refs:
            selector = self.element_refs[ref]['selector']
            try:
                await self.page.click(selector, timeout=5000)
                await asyncio.sleep(0.5)
                return {"action": "click", "ref": ref, "status": "ok"}
            except Exception as e:
                return {"action": "click", "ref": ref, "error": str(e)}
        return {"action": "click", "ref": ref, "error": "ref not found"}

    async def click_text(self, text: str) -> Dict:
        """Click element by text content. Uses ref-first if snapshot available."""
        # Try ref-first if we have element_refs from a recent snapshot
        if self.element_refs:
            found_ref = self._find_ref_by_text(text)
            if found_ref:
                locator = self._get_locator(found_ref)
                if locator:
                    try:
                        await locator.click(timeout=3000)
                        return {"action": "click", "text": text, "ref": found_ref, "status": "ok"}
                    except:
                        pass  # Fall through to regular methods

        # Fallback to direct Playwright methods
        try:
            # Try exact text first
            await self.page.get_by_text(text, exact=True).first.click(timeout=3000)
            return {"action": "click", "text": text, "status": "ok"}
        except:
            pass
        try:
            # Try partial text
            await self.page.get_by_text(text, exact=False).first.click(timeout=3000)
            return {"action": "click", "text": text, "status": "ok"}
        except:
            pass
        try:
            # Try button role
            await self.page.get_by_role("button", name=text).first.click(timeout=3000)
            return {"action": "click", "text": text, "method": "button"}
        except:
            pass
        try:
            # Try link role
            await self.page.get_by_role("link", name=text).first.click(timeout=3000)
            return {"action": "click", "text": text, "method": "link"}
        except Exception as e:
            return {"action": "click", "text": text, "error": str(e)}

    async def type_ref(self, ref: str, text: str) -> Dict:
        """Type into element by ref."""
        if ref in self.element_refs:
            selector = self.element_refs[ref]['selector']
            try:
                el = self.page.locator(selector).first
                await el.clear()
                await el.type(text)
                return {"action": "type", "ref": ref, "text": text}
            except Exception as e:
                return {"action": "type", "ref": ref, "error": str(e)}
        return {"action": "type", "ref": ref, "error": "ref not found"}

    async def type_placeholder(self, placeholder: str, text: str) -> Dict:
        """Type into input by placeholder. Uses ref-first if snapshot available."""
        # Try ref-first if we have element_refs from a recent snapshot
        if self.element_refs:
            # Find input with matching placeholder
            for ref, data in self.element_refs.items():
                if data.get('type') == 'input':
                    # Check if placeholder matches
                    input_placeholder = data.get('placeholder', '').lower()
                    if placeholder.lower() in input_placeholder or input_placeholder in placeholder.lower():
                        locator = self._get_locator(ref)
                        if locator:
                            try:
                                await locator.clear()
                                await locator.type(text)
                                return {"action": "type", "placeholder": placeholder, "ref": ref, "text": text, "status": "ok"}
                            except:
                                pass  # Fall through to regular method

        # Fallback to direct Playwright method
        try:
            el = self.page.get_by_placeholder(placeholder, exact=False).first
            await el.clear()
            await el.type(text)
            return {"action": "type", "placeholder": placeholder, "text": text}
        except Exception as e:
            return {"action": "type", "placeholder": placeholder, "error": str(e)}

    async def type_role(self, role: str, text: str) -> Dict:
        """Type into element by role (searchbox, textbox, etc)."""
        try:
            el = self.page.get_by_role(role).first
            await el.clear()
            await el.type(text)
            return {"action": "type", "role": role, "text": text}
        except Exception as e:
            return {"action": "type", "role": role, "error": str(e)}

    async def press_key(self, key: str) -> Dict:
        """Press keyboard key."""
        await self.page.keyboard.press(key)
        return {"action": "press", "key": key}

    async def scroll(self, direction: str = "down", amount: int = 500) -> Dict:
        """Scroll page."""
        if direction == "down":
            await self.page.evaluate(f"window.scrollBy(0, {amount})")
        elif direction == "up":
            await self.page.evaluate(f"window.scrollBy(0, -{amount})")
        self._update_action_tracking('scroll')  # Track for snapshot caching
        return {"action": "scroll", "direction": direction}

    async def tabs_list(self) -> Dict:
        """List all open tabs/pages."""
        if not self.context:
            return {"action": "tabs_list", "tabs": [], "count": 0, "status": "error", "error": "Browser not initialized"}
        pages = self.context.pages
        tabs = []
        for i, page in enumerate(pages):
            try:
                title = await page.title() if page else ""
            except Exception:
                title = ""
            tabs.append({
                "index": i,
                "url": page.url if page else "",
                "title": title,
                "is_current": page == self.page
            })
        return {"action": "tabs_list", "tabs": tabs, "count": len(tabs), "status": "ok"}

    async def tabs_new(self, url: str = None) -> Dict:
        """Create a new tab."""
        try:
            new_page = await self.context.new_page()
            if url:
                await new_page.goto(url, wait_until='domcontentloaded', timeout=30000)
            self.page = new_page
            self._previous_snapshot = None
            return {"action": "tabs_new", "url": url, "status": "ok"}
        except Exception as e:
            return {"action": "tabs_new", "error": str(e)}

    async def tabs_select(self, index: int) -> Dict:
        """Select a tab by index."""
        try:
            pages = self.context.pages
            if 0 <= index < len(pages):
                self.page = pages[index]
                self._previous_snapshot = None
                await self.page.bring_to_front()
                return {"action": "tabs_select", "index": index, "status": "ok"}
            return {"action": "tabs_select", "error": f"invalid index {index}, have {len(pages)} tabs"}
        except Exception as e:
            return {"action": "tabs_select", "error": str(e)}

    async def tabs_close(self, index: int = None) -> Dict:
        """Close a tab by index. If no index, closes current tab."""
        try:
            pages = self.context.pages
            if len(pages) <= 1:
                return {"action": "tabs_close", "error": "cannot close last tab"}

            if index is None:
                current_index = pages.index(self.page)
                await self.page.close()
                self.page = pages[max(0, current_index - 1)]
            else:
                if 0 <= index < len(pages):
                    was_current = pages[index] == self.page
                    await pages[index].close()
                    if was_current:
                        self.page = self.context.pages[0]
                else:
                    return {"action": "tabs_close", "error": f"invalid index {index}"}

            self._previous_snapshot = None
            return {"action": "tabs_close", "status": "ok"}
        except Exception as e:
            return {"action": "tabs_close", "error": str(e)}

    async def manage_tabs(self, action: str, index: Optional[int] = None, url: Optional[str] = None) -> Dict:
        """
        Manage browser tabs (unified interface matching Playwright MCP).

        Args:
            action: "list", "new", "select", or "close"
            index: Tab index for select/close actions
            url: URL for new tab (optional)

        Returns:
            Dict with action result
        """
        if action == "list":
            return await self.tabs_list()
        elif action == "new":
            return await self.tabs_new(url)
        elif action == "select":
            if index is None:
                return {"action": "manage_tabs", "error": "index required for select action"}
            return await self.tabs_select(index)
        elif action == "close":
            return await self.tabs_close(index)
        else:
            return {"action": "manage_tabs", "error": f"unknown action: {action}"}

    async def wait(self, seconds: float = 1) -> Dict:
        """Wait for specified time."""
        await asyncio.sleep(seconds)
        self._update_action_tracking('wait')  # Track for snapshot caching
        return {"action": "wait", "seconds": seconds}

    async def select_option(self, selector: str, value: str) -> Dict:
        """Select dropdown option."""
        try:
            await self.page.select_option(selector, value)
            return {"action": "select", "value": value}
        except Exception as e:
            return {"action": "select", "error": str(e)}

    async def screenshot(self, path: str = None, full_page: bool = False,
                         ref: str = None) -> Dict:
        """Take screenshot of page or element."""
        try:
            # Generate default path if not provided
            if not path:
                timestamp = int(time.time())
                path = str(EVERSALE_HOME / f"screenshot_{timestamp}.png")

            # Screenshot specific element
            if ref and ref in self.element_refs:
                locator = self._get_locator(ref)
                if locator:
                    await locator.screenshot(path=path, timeout=5000)
                    return {"action": "screenshot", "path": path, "element": ref, "status": "ok"}

            # Screenshot full page or viewport
            await self.page.screenshot(path=path, full_page=full_page)
            return {"action": "screenshot", "path": path, "full_page": full_page, "status": "ok"}
        except Exception as e:
            return {"action": "screenshot", "error": str(e)}

    async def file_upload(self, paths: List[str], ref: str = None,
                          selector: str = None) -> Dict:
        """Upload one or multiple files to a file input."""
        try:
            # Find file input element
            locator = None
            if ref and ref in self.element_refs:
                locator = self._get_locator(ref)
            elif selector:
                locator = self.page.locator(selector).first
            else:
                # Try common file input selectors
                locator = self.page.locator('input[type="file"]').first

            if not locator:
                return {"action": "file_upload", "error": "file input not found"}

            # Upload files
            await locator.set_input_files(paths, timeout=5000)
            return {"action": "file_upload", "paths": paths, "status": "ok"}
        except Exception as e:
            return {"action": "file_upload", "error": str(e)}

    # -------------------------------------------------------------------------
    # HOVER - Mouse hover over element
    # -------------------------------------------------------------------------

    async def hover(self, ref: str = None, text: str = None) -> Dict:
        """Hover over element - ref is primary, text is fallback."""
        if ref and ref in self.element_refs:
            # Human Hover
            if hasattr(self, 'cursor') and self.cursor:
                selector = self.element_refs[ref].get('selector')
                if selector:
                    try:
                        await self.cursor.hover(self.page, selector)
                        self._update_action_tracking('hover')
                        return {"action": "hover", "ref": ref, "status": "ok"}
                    except Exception:
                        pass # Fallback

            locator = self._get_locator(ref)
            if locator:
                try:
                    await locator.hover(timeout=5000)
                    self._update_action_tracking('hover')  # Track for snapshot caching
                    return {"action": "hover", "ref": ref, "status": "ok"}
                except Exception as e:
                    return {"action": "hover", "ref": ref, "error": str(e)}

        if text:
            found_ref = self._find_ref_by_text(text)
            if found_ref:
                return await self.hover(ref=found_ref)
            try:
                locator = self.page.get_by_text(text, exact=False).first
                await locator.hover(timeout=5000)
                self._update_action_tracking('hover')  # Track for snapshot caching
                return {"action": "hover", "text": text, "status": "ok"}
            except Exception as e:
                return {"action": "hover", "text": text, "error": str(e)}

        return {"action": "hover", "error": "element not found"}

    # -------------------------------------------------------------------------
    # DRAG - Drag and drop between elements
    # -------------------------------------------------------------------------

    async def drag(self, start_ref: str = None, end_ref: str = None,
                   start_text: str = None, end_text: str = None) -> Dict:
        """Drag from one element to another."""
        start_locator = None
        if start_ref and start_ref in self.element_refs:
            start_locator = self._get_locator(start_ref)
        elif start_text:
            found_ref = self._find_ref_by_text(start_text)
            if found_ref:
                start_locator = self._get_locator(found_ref)
            else:
                start_locator = self.page.get_by_text(start_text, exact=False).first

        end_locator = None
        if end_ref and end_ref in self.element_refs:
            end_locator = self._get_locator(end_ref)
        elif end_text:
            found_ref = self._find_ref_by_text(end_text)
            if found_ref:
                end_locator = self._get_locator(found_ref)
            else:
                end_locator = self.page.get_by_text(end_text, exact=False).first

        if not start_locator or not end_locator:
            return {"action": "drag", "error": "start or end element not found"}

        try:
            await start_locator.drag_to(end_locator, timeout=5000)
            return {"action": "drag", "status": "ok"}
        except Exception as e:
            return {"action": "drag", "error": str(e)}

    # -------------------------------------------------------------------------
    # EVALUATE - Run JavaScript on page or element
    # -------------------------------------------------------------------------

    async def evaluate(self, expression: str, ref: str = None) -> Dict:
        """Evaluate JavaScript expression on page or element."""
        try:
            if ref and ref in self.element_refs:
                locator = self._get_locator(ref)
                if locator:
                    result = await locator.evaluate(expression)
                    return {"action": "evaluate", "ref": ref, "result": result, "status": "ok"}
                return {"action": "evaluate", "ref": ref, "error": "element not found"}

            result = await self.page.evaluate(expression)
            return {"action": "evaluate", "result": result, "status": "ok"}
        except Exception as e:
            return {"action": "evaluate", "error": str(e)}

    # -------------------------------------------------------------------------
    # NAVIGATE_BACK - Go back to previous page
    # -------------------------------------------------------------------------

    async def navigate_back(self) -> Dict:
        """Go back to the previous page."""
        try:
            await self.page.go_back(wait_until='domcontentloaded', timeout=30000)
            self._previous_snapshot = None
            await asyncio.sleep(0.5)
            return {"action": "navigate_back", "status": "ok"}
        except Exception as e:
            return {"action": "navigate_back", "error": str(e)}

    # -------------------------------------------------------------------------
    # NAVIGATE_FORWARD - Go forward to the next page
    # -------------------------------------------------------------------------

    async def navigate_forward(self) -> Dict:
        """Go forward to the next page."""
        try:
            await self.page.go_forward(wait_until='domcontentloaded', timeout=30000)
            self._previous_snapshot = None
            await asyncio.sleep(0.5)
            return {"action": "navigate_forward", "status": "ok"}
        except Exception as e:
            return {"action": "navigate_forward", "error": str(e)}

    async def forward(self) -> Dict:
        """Alias for navigate_forward()."""
        return await self.navigate_forward()

    # -------------------------------------------------------------------------
    # REFRESH - Reload the current page
    # -------------------------------------------------------------------------

    async def refresh(self) -> Dict:
        """Reload the current page."""
        try:
            await self.page.reload(wait_until='domcontentloaded', timeout=30000)
            self._previous_snapshot = None
            await asyncio.sleep(0.5)
            return {"action": "refresh", "status": "ok"}
        except Exception as e:
            return {"action": "refresh", "error": str(e)}

    # -------------------------------------------------------------------------
    # CONSOLE_MESSAGES - Get browser console output
    # -------------------------------------------------------------------------

    async def console_messages(self, level: str = "info") -> Dict:
        """Get console messages from the page.

        Args:
            level: Minimum log level - 'error', 'warning', 'info', or 'debug'
        """
        level_priority = {"error": 0, "warning": 1, "info": 2, "debug": 3}
        min_priority = level_priority.get(level, 2)

        type_to_level = {
            "error": 0, "warning": 1, "log": 2, "info": 2, "debug": 3, "trace": 3
        }

        filtered = [
            msg for msg in self._console_messages
            if type_to_level.get(msg.get("type", "log"), 2) <= min_priority
        ]

        return {"action": "console_messages", "level": level, "messages": filtered, "status": "ok"}

    # -------------------------------------------------------------------------
    # NETWORK_REQUESTS - Get network activity
    # -------------------------------------------------------------------------

    async def network_requests(self, include_static: bool = False) -> Dict:
        """Get network requests made by the page.

        Args:
            include_static: Include static resources (images, fonts, scripts, css).
        """
        static_types = {"image", "font", "stylesheet", "script", "media"}

        if include_static:
            requests = self._network_requests
        else:
            requests = [
                req for req in self._network_requests
                if req.get("resource_type") not in static_types
            ]

        return {"action": "network_requests", "count": len(requests), "requests": requests, "status": "ok"}

    async def handle_dialog(self, accept: bool = True, prompt_text: str = None) -> Dict:
        """Handle browser dialogs (alert, confirm, prompt).

        Args:
            accept: Whether to accept or dismiss the dialog.
            prompt_text: Text to enter if it's a prompt dialog.
        """
        # Set up dialog handler for the next dialog
        async def dialog_handler(dialog):
            if accept:
                if prompt_text and dialog.type == "prompt":
                    await dialog.accept(prompt_text)
                else:
                    await dialog.accept()
            else:
                await dialog.dismiss()

        self.page.once("dialog", dialog_handler)
        return {"action": "handle_dialog", "accept": accept, "status": "ok"}

    async def resize(self, width: int, height: int) -> Dict:
        """Resize the browser viewport.

        Args:
            width: Viewport width in pixels.
            height: Viewport height in pixels.
        """
        await self.page.set_viewport_size({"width": width, "height": height})
        return {"action": "resize", "width": width, "height": height, "status": "ok"}

    async def fill_form(self, fields: List[Dict]) -> Dict:
        """Fill multiple form fields at once.

        Args:
            fields: List of field definitions, each with:
                - ref: Element ref from snapshot
                - value: Value to fill
                - type: Field type (textbox, checkbox, radio, combobox)
        """
        results = []
        for field in fields:
            ref = field.get("ref", "")
            value = field.get("value", "")
            field_type = field.get("type", "textbox")

            if ref not in self.element_refs:
                results.append({"ref": ref, "status": "not_found"})
                continue

            locator = self._get_locator(ref)
            if not locator:
                results.append({"ref": ref, "status": "no_locator"})
                continue

            try:
                if field_type in ("textbox", "textarea"):
                    await locator.clear()
                    await locator.fill(value)
                elif field_type == "checkbox":
                    if value.lower() in ("true", "1", "yes", "on"):
                        await locator.check()
                    else:
                        await locator.uncheck()
                elif field_type == "radio":
                    await locator.check()
                elif field_type in ("combobox", "select"):
                    await locator.select_option(value)
                results.append({"ref": ref, "status": "ok"})
            except Exception as e:
                results.append({"ref": ref, "status": "error", "error": str(e)})

        return {"action": "fill_form", "fields": len(fields), "results": results, "status": "ok"}

    # =========================================================================
    # SNAPSHOT - Get page state with element refs (like Playwright MCP)
    # =========================================================================

    async def read_page(self) -> Dict:
        """Extract full page text for reading."""
        try:
            content = await self.page.evaluate("document.body.innerText")
            # Limit to reasonable size for LLM context (approx 20k chars)
            truncated = content[:20000]
            remaining = len(content) - 20000
            msg = truncated
            if remaining > 0:
                msg += f"\n... ({remaining} more characters)"
            return {"action": "read_page", "content": msg, "length": len(content), "status": "ok"}
        except Exception as e:
            return {"action": "read_page", "error": str(e)}

    async def get_snapshot(self) -> str:
        """
        Get page snapshot using Accessibility Tree + DOM mapping.
        Superior to standard Playwright MCP snapshots.
        Now with automatic token optimization and caching.
        """
        if not self.page:
            return "Error: Browser not initialized"

        # Check if we should use cached snapshot (action didn't change DOM)
        if self._last_action_type and self._should_use_cached_snapshot(self._last_action_type):
            logger.debug(f"Using cached snapshot (action: {self._last_action_type} doesn't change DOM)")
            return self._last_snapshot

        self.element_refs = {}
        try:
            title = await self.page.title()
            url = self.page.url

            # Extract interactive elements and map to stable refs.
            # Important: clear previous refs to avoid collisions across snapshots.
            elements = await self.page.evaluate(r"""() => {
                const MAX_ELEMENTS = 140;
                const results = [];

                // Clear any old refs (prevents `[data-eversale-ref="e1"]` matching multiple elements).
                document.querySelectorAll('[data-eversale-ref]').forEach(el => {
                    try { el.removeAttribute('data-eversale-ref'); } catch (e) {}
                });

                const interactiveSelector = [
                    'a[href]',
                    'button',
                    'input',
                    'textarea',
                    'select',
                    '[role="button"]',
                    '[role="link"]',
                    '[role="textbox"]',
                    '[role="searchbox"]',
                    '[role="combobox"]',
                    '[role="menuitem"]',
                    '[role="option"]',
                    '[contenteditable="true"]'
                ].join(',');

                const nodes = Array.from(document.querySelectorAll(interactiveSelector));

                function isVisible(node) {
                    if (!node || node.nodeType !== 1) return false;
                    
                    // Fast path for common hidden patterns
                    if (node.offsetWidth === 0 || node.offsetHeight === 0) return false;
                    
                    const style = window.getComputedStyle(node);
                    if (style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity || '1') <= 0.1) return false;
                    
                    const rect = node.getBoundingClientRect();
                    if (rect.width < 2 || rect.height < 2) return false;
                    
                    // In-viewport (or near it) for a compact snapshot.
                    const pad = 100; // Increased padding for better context
                    const inView = rect.bottom >= -pad && rect.top <= (window.innerHeight + pad) &&
                                   rect.right >= -pad && rect.left <= (window.innerWidth + pad);
                    return inView;
                }

                function textOf(node) {
                    // Prioritize user-visible text
                    let t = (node.innerText || '').trim();
                    if (!t) t = (node.getAttribute('aria-label') || '').trim();
                    if (!t) t = (node.placeholder || '').trim();
                    if (!t) t = (node.title || '').trim();
                    if (!t && node.tagName === 'INPUT') t = node.value;
                    
                    return (t || '').replace(/\s+/g, ' ').substring(0, 120).trim();
                }

                function labelOf(node) {
                    const tag = (node.tagName || '').toLowerCase();
                    if (!['input','textarea','select'].includes(tag)) return '';
                    const id = node.getAttribute('id') || '';
                    if (id) {
                        const escaped = id.replace(/"/g, '\\"');
                        const lab = document.querySelector(`label[for="${escaped}"]`);
                        const t = lab ? (lab.innerText || '').trim() : '';
                        if (t) return t.replace(/\s+/g, ' ').trim();
                    }
                    const parentLabel = node.closest ? node.closest('label') : null;
                    if (parentLabel) {
                        const t = (parentLabel.innerText || '').trim();
                        if (t) return t.replace(/\s+/g, ' ').trim();
                    }
                    return '';
                }

                function score(node) {
                    const tag = node.tagName.toLowerCase();
                    const role = (node.getAttribute('role') || '').toLowerCase();
                    const type = node.getAttribute('type') || '';
                    const rect = node.getBoundingClientRect();
                    
                    let s = 0;
                    // Highly interactive elements
                    if (tag === 'input' || tag === 'textarea' || tag === 'select') s += 150;
                    if (tag === 'button' || role === 'button' || type === 'submit') s += 100;
                    if (tag === 'a' || role === 'link') s += 80;
                    
                    // Important roles
                    if (role === 'textbox' || role === 'searchbox' || role === 'combobox') s += 90;
                    if (role === 'menuitem' || role === 'option' || role === 'checkbox' || role === 'radio') s += 60;
                    
                    // Visual priority (near center of screen is better)
                    const centerX = window.innerWidth / 2;
                    const centerY = window.innerHeight / 2;
                    const elCenterX = rect.left + rect.width / 2;
                    const elCenterY = rect.top + rect.height / 2;
                    const distance = Math.sqrt(Math.pow(elCenterX - centerX, 2) + Math.pow(elCenterY - centerY, 2));
                    s += Math.max(0, 50 - (distance / 100));

                    // Text length bonus (prefer elements with descriptive text)
                    const text = textOf(node);
                    if (text) s += Math.min(30, text.length / 2);
                    
                    return s;
                }

                const scored = [];
                for (const node of nodes) {
                    if (!isVisible(node)) continue;
                    scored.push({ node, s: score(node) });
                }

                scored.sort((a, b) => b.s - a.s);
                const chosen = scored.slice(0, MAX_ELEMENTS);

                let refId = 1;
                for (const item of chosen) {
                    const node = item.node;
                    const tag = (node.tagName || '').toLowerCase();
                    const role = (node.getAttribute && node.getAttribute('role')) ? (node.getAttribute('role') || '').toLowerCase() : '';
                    const type = role || tag || 'element';
                    const ref = 'e' + (refId++);
                    const text = textOf(node);
                    const placeholder = (node.placeholder || '').trim();
                    const label = labelOf(node);

                    try { node.setAttribute('data-eversale-ref', ref); } catch (e) {}
                    results.push({
                        ref,
                        type,
                        text: (text || '').substring(0, 100),
                        placeholder: (placeholder || '').substring(0, 80),
                        label: (label || '').substring(0, 80),
                        selector: `[data-eversale-ref="${ref}"]`
                    });
                }

                return results;
            }""")
            
            for el in elements:
                self.element_refs[el['ref']] = el

            # Build MCP Style Output
            lines = [
                f"### Page state",
                f"- Page URL: {url}",
                f"- Page Title: {title}",
                f"- Page Snapshot (AXTree):",
                format_yaml_snapshot(self.element_refs)
            ]

            snapshot = "\n".join(lines)

            # Apply token optimization (compress and cache)
            if self.token_optimizer:
                # Estimate raw tokens
                raw_tokens = self.token_optimizer.estimate_tokens(snapshot)

                # Cache snapshot for future use
                snapshot_hash = self.token_optimizer.cache_snapshot({'text': snapshot, 'elements': elements})

                # Compress if needed (already optimized by MAX_ELEMENTS=140, but track stats)
                compressed_tokens = self.token_optimizer.estimate_tokens(snapshot)
                self.token_optimizer.update_stats(raw_tokens, compressed_tokens)

                # Store for cache checking
                self._last_snapshot = snapshot
                self._last_snapshot_hash = snapshot_hash

                logger.debug(f"Snapshot: {len(elements)} elements, ~{compressed_tokens} tokens")

            return snapshot
        except Exception as e:
            return f"Error capturing snapshot: {str(e)}"

    # =========================================================================
    # REF HELPER METHODS - Find elements by text or role
    # =========================================================================

    def _get_locator(self, ref: str):
        """Get Playwright locator for a ref ID."""
        if ref not in self.element_refs:
            return None
        selector = self.element_refs[ref]['selector']
        return self.page.locator(selector).first

    def _find_ref_by_text(self, text: str, exact: bool = False) -> str:
        """Find ref ID by matching text, placeholder, or label (case-insensitive)."""
        text_lower = text.lower()
        for ref, data in self.element_refs.items():
            # Check text, placeholder, and label fields
            el_text = data.get('text', '').lower()
            el_placeholder = data.get('placeholder', '').lower()
            el_label = data.get('label', '').lower()

            candidates = [el_text, el_placeholder, el_label]
            candidates = [c for c in candidates if c]  # Remove empty strings

            if exact:
                if text_lower in candidates:
                    return ref
            else:
                for candidate in candidates:
                    if text_lower in candidate or candidate in text_lower:
                        return ref
        return None

    def _find_ref_by_role(self, role: str, name: str = None) -> str:
        """Find ref ID by role (button, link, input, dropdown) and optional name."""
        role_lower = role.lower()
        name_lower = name.lower() if name else None

        for ref, data in self.element_refs.items():
            if data.get('type') != role_lower and data.get('role') != role_lower:
                continue
            if name_lower is None:
                return ref
            el_text = data.get('text', '').lower()
            if name_lower in el_text or el_text in name_lower:
                return ref
        return None

    async def click(self, ref: str = None, text: str = None, role: str = None, hints: Optional[Any] = None) -> Dict:
        """
        Click element by ref (primary) or text/role (fallback).
        Ref-first targeting pattern like Playwright MCP.
        """
        async def _click_internal():
            # Try ref first
            if ref and ref in self.element_refs:
                # Human Click
                if hasattr(self, 'cursor') and self.cursor:
                    selector = self.element_refs[ref].get('selector')
                    if selector:
                        try:
                            success = await self.cursor.click_at(self.page, selector=selector)
                            if success:
                                await asyncio.sleep(0.5)
                                self._update_action_tracking('click')
                                return {"action": "click", "ref": ref, "status": "ok"}
                        except Exception as e:
                            logger.debug(f"Human click failed: {e}")
                            pass # Fallback
                
                locator = self._get_locator(ref)
                if locator:
                    try:
                        await locator.click(timeout=5000)
                        await asyncio.sleep(0.5)
                        self._update_action_tracking('click')  # Track for snapshot caching
                        return {"action": "click", "ref": ref, "status": "ok"}
                    except Exception as e:
                        if self.debug:
                            logger.debug(f"Ref click failed, falling back: {e}")
                        # Fall through to text/role fallbacks (A/B layouts, stale refs, overlays, etc.)
                        pass

            # Try finding ref by text
            if text:
                found_ref = self._find_ref_by_text(text)
                if found_ref:
                    locator = self._get_locator(found_ref)
                    if locator:
                        await locator.click(timeout=5000)
                        self._update_action_tracking('click')  # Track for snapshot caching
                        return {"action": "click", "ref": found_ref, "status": "ok"}

                # Fallback to direct text click
                res = await self.click_text(text)
                if res.get("status") == "ok":
                    self._update_action_tracking('click')  # Track for snapshot caching
                    return res
                raise Exception(f"Text click failed: {res.get('error')}")

            # Try finding ref by role
            if role:
                found_ref = self._find_ref_by_role(role, text)
                if found_ref:
                    locator = self._get_locator(found_ref)
                    if locator:
                        await locator.click(timeout=5000)
                        self._update_action_tracking('click')  # Track for snapshot caching
                        return {"action": "click", "ref": found_ref, "status": "ok"}

            # LAST RESORT: Visual Grounding (Self-Healing)
            if text or ref:
                description = text or ref
                logger.info(f"DOM click failed for '{description}', trying visual grounding...")
                from .visual_grounding import GroundingStrategy
                vis_result = await self.visual_engine.ground_element(self.page, description, strategy=GroundingStrategy.HYBRID)
                if vis_result.success and vis_result.best_match:
                    success = await self.visual_engine.click_grounded_element(self.page, vis_result.best_match)
                    if success:
                        self._update_action_tracking('click')
                        return {"action": "click", "description": description, "method": "visual", "status": "ok"}

            raise Exception("Element not found")

        return await self._run_with_recovery(_click_internal, hints=hints)

    async def type(self, text: str, ref: str = None, element_text: str = None, press_key: str = None, hints: Optional[Any] = None) -> Dict:
        """
        Type into element by ref (primary) or element_text (fallback).
        Ref-first targeting pattern like Playwright MCP.
        """
        async def _type_internal():
            # Try ref first
            if ref and ref in self.element_refs:
                locator = self._get_locator(ref)
                if locator:
                    try:
                        await locator.clear()
                        await locator.type(text)
                        if press_key:
                            await locator.press(press_key)
                        self._update_action_tracking('type')  # Track for snapshot caching
                        return {"action": "type", "ref": ref, "text": text, "status": "ok"}
                    except Exception as e:
                        if self.debug:
                            logger.debug(f"Ref type failed, falling back: {e}")
                        pass

            # Try finding ref by element text/placeholder
            if element_text:
                found_ref = self._find_ref_by_role('input', element_text)
                if found_ref:
                    locator = self._get_locator(found_ref)
                    if locator:
                        await locator.clear()
                        await locator.type(text)
                        if press_key:
                            await locator.press(press_key)
                        self._update_action_tracking('type')  # Track for snapshot caching
                        return {"action": "type", "ref": found_ref, "text": text, "status": "ok"}

            # LAST RESORT: Visual Grounding (Self-Healing)
            if element_text or ref:
                description = element_text or ref
                logger.info(f"DOM type failed for '{description}', trying visual grounding...")
                from .visual_grounding import GroundingStrategy, ElementType
                vis_result = await self.visual_engine.ground_element(self.page, description, strategy=GroundingStrategy.HYBRID, element_type=ElementType.INPUT)
                if vis_result.success and vis_result.best_match:
                    success = await self.visual_engine.fill_grounded_element(self.page, vis_result.best_match, text)
                    if success:
                        if press_key:
                            await self.page.keyboard.press(press_key)
                        self._update_action_tracking('type')
                        return {"action": "type", "description": description, "method": "visual", "status": "ok"}

            raise Exception("Element not found")

        return await self._run_with_recovery(_type_internal, hints=hints)

    async def click_coords(self, x: int, y: int) -> Dict:
        """Click at absolute coordinates (0-1000 scaled)."""
        if not self.page:
            return {"error": "no page open"}
        viewport = self.page.viewport_size or {"width": 1280, "height": 720}
        real_x = int(x * viewport["width"] / 1000)
        real_y = int(y * viewport["height"] / 1000)
        await self.page.mouse.click(real_x, real_y)
        self._update_action_tracking('click')
        return {"action": "click_coords", "x": x, "y": y, "status": "ok"}

    async def type_coords(self, text: str, x: int, y: int) -> Dict:
        """Type text at absolute coordinates (0-1000 scaled)."""
        if not self.page:
            return {"error": "no page open"}
        await self.click_coords(x, y)
        await asyncio.sleep(0.3)
        await self.page.keyboard.type(text, delay=random.randint(50, 150))
        self._update_action_tracking('type')
        return {"action": "type_coords", "text": text, "x": x, "y": y, "status": "ok"}

    async def drag_coords(self, x1: int, y1: int, x2: int, y2: int) -> Dict:
        """Drag from (x1,y1) to (x2,y2) (0-1000 scaled)."""
        if not self.page:
            return {"error": "no page open"}
        viewport = self.page.viewport_size or {"width": 1280, "height": 720}
        rx1, ry1 = int(x1 * viewport["width"] / 1000), int(y1 * viewport["height"] / 1000)
        rx2, ry2 = int(x2 * viewport["width"] / 1000), int(y2 * viewport["height"] / 1000)
        await self.page.mouse.move(rx1, ry1)
        await self.page.mouse.down()
        await self.page.mouse.move(rx2, ry2, steps=10)
        await self.page.mouse.up()
        self._update_action_tracking('drag')
        return {"action": "drag_coords", "status": "ok"}

    def _parse_native_action(self, response: str) -> Optional[Dict]:
        """Parse native UI-Tars action format: click(start_box='...')"""
        # Click: click(start_box='<|box_start|>(y,x)<|box_end|>')
        click_match = re.search(r"(?:click|tap)\s*\(\s*(?:start_box|box)\s*=\s*['\"]?[^'\"]*\((\d+),(\d+)\)[^'\"]*['\"]?\s*\)", response, re.IGNORECASE)
        if click_match:
            y, x = int(click_match.group(1)), int(click_match.group(2))
            return {"action": "click", "x": x, "y": y}
        
        # Type: type(text='...', start_box='<|box_start|>(y,x)<|box_end|>')
        type_match = re.search(r"type\s*\(\s*text\s*=\s*['\"]([^'\"]*)['\"].*?\((\d+),(\d+)\)[^'\"]*['\"]?\s*\)", response, re.IGNORECASE)
        if type_match:
            text, y, x = type_match.group(1), int(type_match.group(2)), int(type_match.group(3))
            return {"action": "type", "text": text, "x": x, "y": y}
        
        # Drag: drag(start_box='...', end_box='...')
        drag_match = re.search(r"drag\s*\(\s*start_box\s*=\s*['\"]?[^'\"]*\((\d+),(\d+)\)[^'\"]*['\"]?.*?end_box\s*=\s*['\"]?[^'\"]*\((\d+),(\d+)\)[^'\"]*['\"]?\s*\)", response, re.IGNORECASE)
        if drag_match:
            y1, x1, y2, x2 = int(drag_match.group(1)), int(drag_match.group(2)), int(drag_match.group(3)), int(drag_match.group(4))
            return {"action": "drag", "x1": x1, "y1": y1, "x2": x2, "y2": y2}
        
        # Simple coordinate extraction as last resort
        coord_match = re.search(r"\((\d+),(\d+)\)", response)
        if coord_match and ("click" in response.lower() or "tap" in response.lower()):
            y, x = int(coord_match.group(1)), int(coord_match.group(2))
            return {"action": "click", "x": x, "y": y}

        # Done
        if "done(" in response.lower() or "finished(" in response.lower():
            res_match = re.search(r"(?:done|finished)\s*\(\s*(?:result\s*=\s*)?['\"]([^'\"]*)['\"]?\s*\)", response, re.IGNORECASE)
            return {"action": "done", "result": res_match.group(1) if res_match else "Task complete"}
        return None

    async def get_markdown(self, selector: str = "body") -> str:
        """Get markdown content of the page or a specific element."""
        try:
            # First try to get the HTML content
            if selector == "body":
                html_content = await self.page.content()
            else:
                try:
                    locator = self.page.locator(selector).first
                    html_content = await locator.inner_html()
                except Exception:
                    # Fallback if selector not found
                    html_content = await self.page.content()

            # Convert to markdown using html2text
            h = html2text.HTML2Text()
            h.ignore_links = False
            h.ignore_images = False
            h.ignore_tables = False
            h.body_width = 0  # No wrapping
            
            markdown = h.handle(html_content)
            return markdown
            
        except Exception as e:
            logger.warning(f"Error extracting markdown: {e}")
            # Fallback to inner_text
            try:
                if selector == "body":
                    return await self.page.inner_text("body")
                else:
                    return await self.page.locator(selector).first.inner_text()
            except Exception:
                return ""

    # =========================================================================
    # SITE WORKFLOWS - Deterministic steps for known sites (FAST)
    # =========================================================================

    async def generic_search_and_extract(
        self, 
        url: str, 
        hints: Optional[Any] = None, 
        label: str = "Search",
        extractor_func: Optional[Callable] = None,
        max_leads: int = 5
    ) -> Dict:
        """Generic workflow for searching and extracting data from any site."""
        self.step = 0
        self.results = []

        # Show progress for generic workflows
        print(f"{Colors.CYAN}  * {label}: Starting extraction...{Colors.RESET}")

        # Step 1: Navigate
        self.step += 1
        print_step(self.step, "navigate", f"{label}: {url}", "running")
        nav_result = await self.navigate(url, hints=hints)
        if isinstance(nav_result, dict) and nav_result.get("status") == "blocked":
            return nav_result
        print_step(self.step, "navigate", label, "success")

        # Step 2: Stability and Recovery pipeline
        self.step += 1
        print_step(self.step, "prepare", "running recovery pipeline", "running")
        await self.recovery.run_pipeline(hints)
        print_step(self.step, "prepare", "page ready", "success")

        # Step 3: Site-specific preparations based on hints (not domain!)
        if hints and any(m in hints.expected_failure_modes for m in [FailureMode.INFINITE_SCROLL_REQUIRED]):
            self.step += 1
            max_scrolls = hints.max_pages or 3
            print_step(self.step, "scroll", f"loading content ({max_scrolls} iterations)", "running")
            for _ in range(max_scrolls):
                # Trigger scroll recovery step directly
                await self.recovery.handlers[FailureMode.INFINITE_SCROLL_REQUIRED].recovery_steps[0](self.page)
                await asyncio.sleep(1)
            print_step(self.step, "scroll", "done", "success")

        # Step 4: Extract
        self.step += 1
        print_step(self.step, "extract", "collecting data", "running")
        
        if extractor_func:
            data = await extractor_func()
        else:
            # Generic extraction using preferred selectors if available
            selectors = hints.preferred_selectors if hints else []
            # ... generic extraction logic ...
            data = None # Placeholder

        if data:
            # Handle list vs single object
            results_count = len(data) if isinstance(data, list) else 1
            print_step(self.step, "extract", f"found {results_count} results", "success")
            
            # Limit results to max_leads
            if isinstance(data, list):
                data = data[:max_leads]

            # Generate unique summary output
            result_obj = {
                "status": "complete",
                "steps": self.step,
                "url": self.page.url,
                "data": data,
                "leads": data if isinstance(data, list) else [data],
                "recovery_telemetry": self.recovery.get_latest_telemetry()
            }
            
            # Promoting trick: actually return the data summary as the primary 'result' string
            result_obj["result"] = await generate_summary(label, result_obj, self.gpu_client)
            return result_obj
        
        return {"status": "failed", "error": "No data extracted"}

    async def workflow_fb_ads(self, query: str) -> Dict:
        """
        FB Ads Library workflow - now using generic state-based logic.
        """
        print(f"{Colors.CYAN}  * FB Ads: Quick search for '{query[:40]}'...{Colors.RESET}")
        from .failure_modes import SITE_HINTS
        hints = SITE_HINTS.get("facebook.com")
        search_url = f"https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=US&q={quote_plus(query)}&media_type=all"

        async def fb_extractor():
            return await self.page.evaluate(r"""() => {
                function findAdCard(e){let c=e,d=0;while(c&&d<30){if(c.getAttribute&&c.getAttribute('aria-labelledby'))return c;const l=c.querySelectorAll?c.querySelectorAll('a'):[];if(l.length>=3&&Array.from(l).some(x=>x.href&&x.href.match(/facebook\.com\/\d{8,}/))&&c.offsetHeight>200)return c;c=c.parentElement;d++}return null}
                function getName(c){if(!c)return'Unknown';const l=c.querySelectorAll('a');for(const x of l){const m=x.href.match(/facebook\.com\/([^\/]+)\/(\d{8,})/) || x.href.match(/facebook\.com\/([^\/\?]+)/);if(m && !['l.php', 'ads'].includes(m[1])){const t=x.innerText?.trim();if(t&&t.length>2)return t}}return'Unknown'}
                const res=[];const rl=document.querySelectorAll('a[href*="l.facebook.com/l.php"]');
                for(const l of rl){const h=l.href;const m=h.match(/[?&]u=([^&]+)/);if(m){let u=decodeURIComponent(m[1]);if(u.match(/facebook\.com|instagram\.com|fb\.com|ig\.me|fb\.me|messenger\.com/i))continue;const c=findAdCard(l);res.push({name:getName(c),url:u,type:'landing_page'})}}
                return res.length > 0 ? res : null;
            }""")

        return await self.generic_search_and_extract(
            url=search_url, 
            hints=hints, 
            label="FB Ads Library",
            extractor_func=fb_extractor
        )

        # If no specific advertiser found, get current URL
        current_url = self.page.url
        print_step(self.step, "extract", "search results page", "success")
        return {
            "status": "complete",
            "result": f"Search results for '{query}' | URL: {current_url}",
            "steps": self.step,
            "url": current_url
        }

    async def workflow_fb_ads_many(self, query: str, max_leads: int = 5, prompt: str = "") -> Dict:
        """
        FB Ads Library workflow (improved): collect multiple leads within a time budget.

        - Respects explicit counts ("find 1", "get 5") unless the prompt says "as many".
        - Uses a scroll+extract loop until count met or per-site time is exhausted.
        - Prefers landing-page URLs (decoded from l.facebook.com redirects); falls back to FB page URLs.
        - If prompt requests URLs-only, returns one URL per line in `result`.
        - Supports up to 60 minutes of scrolling and 500+ unique advertisers.
        - Auto-saves to CSV if filename pattern detected in prompt.
        - Deduplicates by advertiser name (1 URL per advertiser).
        """
        self.step = 0
        prompt = prompt or ""

        # Immediately show progress so user knows we're working
        print(f"{Colors.CYAN}  * FB Ads: Searching for advertisers in '{query[:40]}'...{Colors.RESET}")

        def wants_urls_only(p: str) -> bool:
            p = (p or "").lower()
            return (
                ("output only" in p and ("url" in p or "urls" in p or "username" in p or "usernames" in p)) or
                ("urls only" in p) or
                ("no explanations" in p) or
                ("no explanation" in p) or
                (bool(re.search(r"\boutput\s+(?:exactly\s+)?(?:1|one)\b", p)) and ("url" in p or "urls" in p))
            )

        def wants_many(p: str) -> bool:
            p = (p or "").lower()
            return (
                "as many" in p or
                "return as many" in p or
                ("spend max" in p and "minute" in p) or
                ("max " in p and "minute" in p) or
                ("up to" in p and "minute" in p) or
                ("scroll for" in p and "minute" in p)
            )

        def extract_max_seconds(p: str) -> int:
            # Check for explicit time budget in prompt
            p_lower = (p or "").lower()

            # Pattern: "up to X minutes", "scroll for X minutes", "max X minutes"
            time_match = re.search(
                r'\b(?:up\s+to|scroll\s+(?:for\s+)?(?:up\s+to\s+)?|max(?:imum)?|spend\s+(?:up\s+to\s+)?|for\s+up\s+to)\s*(\d{1,3})\s*(?:minutes?|mins?)\b',
                p_lower
            )
            if time_match:
                try:
                    minutes = int(time_match.group(1))
                    # Allow up to 120 minutes (2 hours)
                    return min(minutes * 60, 7200)
                except ValueError:
                    pass

            # Fallback to general time budget
            seconds = self._get_time_budget_seconds(p) if p else 180
            return max(30, seconds)  # No upper cap - trust _get_time_budget_seconds

        def extract_csv_filename(p: str) -> str:
            """Extract CSV filename from prompt if specified."""
            # Pattern: "save to filename.csv" or just "filename.csv"
            csv_match = re.search(r'(?:save\s+(?:to|as)\s+)?([a-zA-Z0-9_-]+\.csv)\b', p, re.I)
            if csv_match:
                return csv_match.group(1)
            # Also check for "save to filename" without .csv
            save_match = re.search(r'save\s+(?:to|as)\s+([a-zA-Z0-9_-]+)', p, re.I)
            if save_match:
                return save_match.group(1) + ".csv"
            # Default: if "save" mentioned, use default filename
            if "save" in p.lower():
                return f"fb_advertisers_{query.replace(' ', '_')[:20]}.csv"
            return ""

        urls_only = wants_urls_only(prompt)
        max_seconds = extract_max_seconds(prompt)
        csv_filename = extract_csv_filename(prompt)

        requested = self._extract_requested_count(prompt) or 0
        if wants_many(prompt) or requested >= 50:
            # For large requests, use the requested count or default to higher limit
            target_count = max(100, requested or 0, max_leads or 0)
        elif requested > 0:
            target_count = requested
        else:
            target_count = max(1, max_leads or 5)

        prompt_lower = (prompt or "").lower()
        # ALWAYS prefer external landing pages (actual websites) - that's what SDRs need
        # Only use FB page URLs as fallback when no external website is found
        type_rank = {"landing_page": 0, "fb_page": 1, "ad_library": 2}

        start_time = time.time()

        # Navigate directly with search query in URL (simple like v2.1.171)
        self.step += 1
        print_step(self.step, "navigate", f"FB Ads Library: {query}", "running")
        search_url = f"https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=US&q={quote_plus(query)}&media_type=all"
        await self.navigate(search_url)
        print_step(self.step, "navigate", f"FB Ads Library: {query}", "success")

        # Wait for results to load
        self.step += 1
        print_step(self.step, "wait", "results loading", "running")
        await asyncio.sleep(4)
        print_step(self.step, "wait", "results loading", "success")

        # Close any dialogs/panels that might be open
        self.step += 1
        print_step(self.step, "press", "Escape (close dialogs)", "running")
        await self.press_key("Escape")
        await asyncio.sleep(0.5)
        print_step(self.step, "press", "Escape (close dialogs)", "success")

        async def extract_batch() -> list:
            # Use larger batch limit for high-target tasks
            batch_limit = min(200, target_count)
            return await self.page.evaluate(r"""(batchLimit) => {
                function findAdCard(element) {
                    let current = element;
                    let depth = 0;
                    while (current && depth < 30) {
                        if (current.getAttribute && current.getAttribute('aria-labelledby')) return current;
                        const links = current.querySelectorAll ? current.querySelectorAll('a') : [];
                        const hasMultipleLinks = links.length >= 3;
                        const hasFbPageLink = Array.from(links).some(l => l.href && l.href.match(/facebook\.com\/\d{8,}/));
                        if (hasMultipleLinks && hasFbPageLink) return current;
                        current = current.parentElement;
                        depth++;
                    }
                    return element.closest ? element.closest('[role="article"]') : null;
                }

                function getAdvertiserName(card) {
                    if (!card) return 'Unknown';
                    const imgs = card.querySelectorAll('img[alt]');
                    for (const img of imgs) {
                        const alt = img.alt?.trim();
                        if (alt && alt.length > 2 && alt.length < 60 &&
                            !alt.toLowerCase().includes('facebook') &&
                            !alt.toLowerCase().includes('meta') &&
                            !alt.toLowerCase().includes('profile') && !alt.includes('Photo')) {
                            return alt;
                        }
                    }
                    const strong = card.querySelector('strong, [style*="font-weight: bold"], [style*="font-weight:bold"]');
                    if (strong && strong.innerText?.trim().length > 2) {
                        return strong.innerText.trim().substring(0, 60);
                    }
                    return 'Unknown';
                }

                const out = [];
                const seen = new Set();

                // 1) Meta Ad Library URLs (advertiser/ad URLs)
                const adLibraryLinks = document.querySelectorAll('a[href*="/ads/library/?"]');
                for (const link of adLibraryLinks) {
                    if (out.length >= batchLimit) break;
                    const href = (link.href || '').split('#')[0];
                    if (!href) continue;
                    if (!/[?&](view_all_page_id|id|ad_id)=/i.test(href)) continue;
                    if (seen.has(href)) continue;
                    seen.add(href);
                    const adCard = findAdCard(link);
                    const name = getAdvertiserName(adCard);
                    out.push({ name, url: href, type: 'ad_library' });
                }

                // 2) External landing URLs via l.facebook.com redirect
                const redirectLinks = document.querySelectorAll('a[href*="l.facebook.com/l.php"]');
                for (const link of redirectLinks) {
                    if (out.length >= batchLimit) break;
                    const href = link.href;
                    const urlMatch = href.match(/[?&]u=([^&]+)/);
                    if (!urlMatch) continue;
                    let targetUrl = decodeURIComponent(urlMatch[1]);
                    if (targetUrl.match(/facebook\.com|instagram\.com|fb\.com|ig\.me|fb\.me|messenger\.com/i)) continue;
                    targetUrl = targetUrl.split('#')[0];
                    if (seen.has(targetUrl)) continue;
                    seen.add(targetUrl);
                    const adCard = findAdCard(link);
                    const name = getAdvertiserName(adCard);
                    let domain = '';
                    try { domain = new URL(targetUrl).hostname.replace('www.', ''); } catch(e) {}
                    out.push({ name, url: targetUrl, domain, type: 'landing_page' });
                }

                // 3) Advertiser FB page URLs
                const allLinks = document.querySelectorAll('a[href*="facebook.com/"]');
                for (const link of allLinks) {
                    if (out.length >= batchLimit) break;
                    const href = link.href || '';
                    const match = href.match(/facebook\.com\/(\d{10,})\/?$/);
                    if (!match) continue;
                    const pageId = match[1];
                    const pageUrl = 'https://www.facebook.com/' + pageId;
                    if (seen.has(pageUrl)) continue;
                    if (href.includes('/ads/library/?') || href.includes('/help')) continue;
                    const text = link.innerText?.trim() || '';
                    const img = link.querySelector('img');
                    const name = (text && text.length > 3 && text.length < 100) ? text : (img && img.alt ? img.alt : '');
                    if (!name || /sponsored|see all/i.test(name)) continue;
                    seen.add(pageUrl);
                    out.push({ name, url: pageUrl, type: 'fb_page' });
                }

                return out;
            }""", batch_limit)

        async def resolve_final_url(url: str) -> str:
            try:
                import aiohttp
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12)) as session:
                    try:
                        async with session.head(url, allow_redirects=True) as resp:
                            return str(resp.url)
                    except Exception:
                        async with session.get(url, allow_redirects=True) as resp:
                            try:
                                await resp.content.read(1)
                            except Exception:
                                pass
                            return str(resp.url)
            except Exception:
                return url

        async def extract_contact_from_website(url: str) -> Dict[str, str]:
            """
            Visit a website and extract contact info (email or contact page URL).
            Returns: {"email": "...", "contact_url": "..."} - at least one will be set.
            """
            result = {"email": "", "contact_url": ""}
            try:
                import aiohttp
                import re
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                    async with session.get(url, allow_redirects=True, headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                    }) as resp:
                        if resp.status != 200:
                            return result
                        html = await resp.text()
                        base_url = str(resp.url)

                        # Extract emails from page (mailto: links and text patterns)
                        email_patterns = [
                            r'mailto:([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
                            r'["\']([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})["\']',
                            r'>([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})<',
                        ]
                        for pattern in email_patterns:
                            matches = re.findall(pattern, html, re.I)
                            for email in matches:
                                # Skip common non-contact emails
                                email_lower = email.lower()
                                if any(skip in email_lower for skip in ['example.com', 'yourdomain', 'test.', 'noreply', 'no-reply']):
                                    continue
                                result["email"] = email
                                break
                            if result["email"]:
                                break

                        # Find contact page URL
                        contact_patterns = [
                            r'href=["\']([^"\']*(?:/contact|/contact-us|/get-in-touch|/reach-us|/connect)[^"\']*)["\']',
                            r'href=["\']([^"\']*contact[^"\']*)["\']',
                        ]
                        for pattern in contact_patterns:
                            matches = re.findall(pattern, html, re.I)
                            for match in matches:
                                # Skip non-page links
                                if any(skip in match.lower() for skip in ['javascript:', 'mailto:', '.css', '.js', '.png', '.jpg']):
                                    continue
                                # Make absolute URL
                                if match.startswith('/'):
                                    from urllib.parse import urljoin
                                    match = urljoin(base_url, match)
                                elif not match.startswith('http'):
                                    from urllib.parse import urljoin
                                    match = urljoin(base_url, match)
                                result["contact_url"] = match
                                break
                            if result["contact_url"]:
                                break
            except Exception as e:
                logger.debug(f"Contact extraction failed for {url}: {e}")
            return result

        leads = []
        seen_urls = set()
        seen_advertisers = set()  # Track by advertiser name for deduplication
        stale_count = 0  # Track consecutive iterations with no new items
        last_progress_report = start_time
        scroll_amount = 1200  # Start with normal scroll
        keywords_to_try = []  # Queue of keywords to try
        keywords_searched = {query}  # Track keywords already searched
        current_keyword = query
        reload_attempts = 0
        max_reload_attempts = 5  # Max page reloads before trying new keywords

        # Be more persistent with stale detection - FB Ads loads slowly
        # Higher thresholds = more scrolling before giving up
        stale_threshold = 20 if target_count >= 100 else (15 if target_count >= 50 else 12)

        async def get_related_keywords(base_query: str) -> List[str]:
            """Use Kimi to generate related keywords for broader search."""
            try:
                from .kimi_k2_client import get_kimi_client
                kimi = get_kimi_client({})
                if not kimi:
                    return []

                response = await kimi.chat(
                    messages=[
                        {"role": "system", "content": "You generate related marketing/advertising keywords. Output ONLY a comma-separated list of 5 related phrases, nothing else."},
                        {"role": "user", "content": f"Generate 5 related advertising keywords for: '{base_query}'. Think about synonyms, related concepts, and alternative phrasings that advertisers might use."}
                    ],
                    temperature=0.7,
                    max_tokens=100
                )
                if hasattr(response, 'content'):
                    keywords = [k.strip() for k in response.content.split(',') if k.strip()]
                    return keywords[:5]
            except Exception as e:
                logger.debug(f"Kimi keyword expansion failed: {e}")
            return []

        # Start the live spinner for ADHD-friendly feedback
        start_spinner(f"Collecting FB advertisers (0/{target_count})")

        try:
            while (time.time() - start_time) < max_seconds and len(leads) < target_count:
                elapsed = int(time.time() - start_time)
                remaining = max(0, int(max_seconds - elapsed))

                self.step += 1

                # Update spinner with current progress
                update_spinner(f"Collecting FB advertisers ({len(leads)}/{target_count})", len(leads))

                # Progress report every 60 seconds for long-running tasks
                if (time.time() - last_progress_report) >= 60:
                    stop_spinner()  # Temporarily stop to show progress
                    print_step(self.step, "progress", f"{len(leads)}/{target_count} collected, {remaining}s remaining", "running")
                    last_progress_report = time.time()
                    start_spinner(f"Collecting FB advertisers ({len(leads)}/{target_count})")

                batch = await extract_batch()
                new = 0
                if isinstance(batch, list):
                    batch_sorted = sorted(
                        batch,
                        key=lambda item: type_rank.get(((item or {}).get("type") if isinstance(item, dict) else "") or "", 99),
                    )
                    for item in batch_sorted:
                        if not isinstance(item, dict):
                            continue
                        u = (item.get("url") or "").strip()
                        advertiser_name = (item.get("name") or "").strip().lower()

                        # Deduplicate by URL AND by advertiser name (1 URL per advertiser)
                        if not u or u in seen_urls:
                            continue
                        if advertiser_name and advertiser_name != "unknown" and advertiser_name in seen_advertisers:
                            continue

                        seen_urls.add(u)
                        if advertiser_name and advertiser_name != "unknown":
                            seen_advertisers.add(advertiser_name)
                        leads.append(item)
                        new += 1
                        if len(leads) >= target_count:
                            break

                # Update spinner with new count after each batch
                update_spinner(f"Collecting FB advertisers ({len(leads)}/{target_count})", len(leads))

                if len(leads) >= target_count:
                    break

                # Track stale iterations - if no new items found, try recovery strategies
                if new == 0:
                    stale_count += 1
                    if stale_count >= 3:
                        # Try aggressive scroll to load more content
                        scroll_amount = min(scroll_amount + 500, 3000)
                        update_spinner(f"Scrolling deeper ({len(leads)}/{target_count})", len(leads))

                    if stale_count >= stale_threshold:
                        # Page exhausted - try recovery strategies
                        reload_attempts += 1

                        if reload_attempts <= max_reload_attempts:
                            # Strategy 1: Reload page and scroll from top
                            stop_spinner()
                            print_step(self.step, "reload", f"Page exhausted, reloading (attempt {reload_attempts})", "running")
                            await self.page.reload()
                            await asyncio.sleep(3)
                            await self.scroll("top")
                            await asyncio.sleep(1)
                            stale_count = 0
                            scroll_amount = 1200
                            start_spinner(f"Collecting FB advertisers ({len(leads)}/{target_count})")
                        else:
                            # Strategy 2: Try related keywords via Kimi
                            stop_spinner()
                            print_step(self.step, "expand", "Trying related keywords...", "running")

                            # Get related keywords if we haven't already
                            if not keywords_to_try:
                                related = await get_related_keywords(query)
                                # Only add keywords we haven't searched yet
                                for kw in related:
                                    if kw and kw.lower() not in {k.lower() for k in keywords_searched}:
                                        keywords_to_try.append(kw)
                                if keywords_to_try:
                                    print_step(self.step, "expand", f"Got {len(keywords_to_try)} related keywords from Kimi", "success")

                            # Get next keyword from queue
                            if keywords_to_try:
                                next_keyword = keywords_to_try.pop(0)
                                keywords_searched.add(next_keyword.lower())
                                current_keyword = next_keyword
                                print_step(self.step, "search", f"Trying keyword: '{next_keyword}'", "running")
                                new_url = f"https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=US&q={quote_plus(next_keyword)}&media_type=all"
                                await self.navigate(new_url)
                                await asyncio.sleep(3)
                                stale_count = 0
                                scroll_amount = 1200
                                reload_attempts = 0
                                start_spinner(f"Collecting FB advertisers ({len(leads)}/{target_count}) - '{next_keyword}'")
                            else:
                                # No more keywords to try - exit
                                print_step(self.step, "complete", f"Exhausted all options, collected {len(leads)}", "running")
                                break
                else:
                    stale_count = 0
                    scroll_amount = 1200  # Reset to normal scroll

                self.step += 1
                await self.scroll("down", scroll_amount)
                await asyncio.sleep(1.2 if scroll_amount <= 1500 else 2.0)  # Wait longer for aggressive scrolls

        finally:
            # Always stop the spinner when done
            stop_spinner(f"Collected {len(leads)} FB advertisers")

        wants_final_urls = bool(re.search(r"\b(?:final|resulting|current)\s+url\b", prompt_lower)) or ("url reached" in prompt_lower)
        wants_contact = any(k in prompt_lower for k in ("contact", "email", "reach out", "outreach", "sdr"))

        def get_clean_domain_url(url: str) -> str:
            """Extract clean domain URL from tracking/landing page URL."""
            try:
                from urllib.parse import urlparse
                parsed = urlparse(url)
                domain = parsed.netloc.lower()
                # Remove common tracking subdomains
                if domain.startswith(('lp.', 'go.', 'link.', 'click.', 'track.', 'trk.', 'w2a.', 'a.', 'l.')):
                    parts = domain.split('.')
                    if len(parts) > 2:
                        domain = '.'.join(parts[1:])
                # Skip known tracking/redirect domains
                tracking_domains = ['bit.ly', 'tinyurl.com', 'goo.gl', 't.co', 'ow.ly']
                if any(td in domain for td in tracking_domains):
                    return ""
                return f"https://{domain}"
            except Exception:
                return url

        urls = []
        normalized_leads = []
        for item in leads:
            u = (item.get("url") or "").strip()
            if not u:
                continue
            if wants_final_urls and item.get("type") == "landing_page":
                u = await resolve_final_url(u)

            # Get clean domain for contact extraction
            domain_url = get_clean_domain_url(u) if item.get("type") == "landing_page" else ""

            urls.append(u)
            normalized_leads.append({
                "advertiser": item.get("name") or "Unknown",
                "url": u,
                "advertiser_url": u,  # Full URL for CSV
                "domain_url": domain_url,  # Clean domain URL for contact extraction
                "type": item.get("type") or "unknown",
                "domain": item.get("domain") or "",
                "email": "",
                "contact_url": "",
            })

        # Extract contact info from landing pages (for SDR use cases)
        if wants_contact and normalized_leads:
            self.step += 1
            print_step(self.step, "contacts", f"Extracting contact info from {len(normalized_leads)} websites...", "running")
            start_spinner(f"Extracting contacts (0/{len(normalized_leads)})")

            # Process in batches of 10 for speed
            batch_size = 10
            contacts_found = 0
            for i in range(0, len(normalized_leads), batch_size):
                batch = normalized_leads[i:i+batch_size]
                tasks = []
                leads_with_tasks = []
                for lead in batch:
                    # Use clean domain URL for contact extraction (not tracking URLs)
                    contact_url = lead.get("domain_url") or lead.get("url", "")
                    if lead.get("type") == "landing_page" and contact_url:
                        tasks.append(extract_contact_from_website(contact_url))
                        leads_with_tasks.append(lead)

                if tasks:
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    for lead, result in zip(leads_with_tasks, results):
                        if isinstance(result, dict):
                            if result.get("email"):
                                lead["email"] = result["email"]
                                contacts_found += 1
                            if result.get("contact_url"):
                                lead["contact_url"] = result["contact_url"]
                                if not result.get("email"):
                                    contacts_found += 1

                update_spinner(f"Extracting contacts ({i + len(batch)}/{len(normalized_leads)})", i + len(batch))

            stop_spinner(f"Found contact info for {contacts_found} websites")
            print_step(self.step, "contacts", f"Found {contacts_found} emails/contact pages", "success")

        if not urls:
            print_step(self.step, "extract", "no advertisers found", "error")
            return {"status": "no_results", "result": "No advertisers found", "steps": self.step, "data": [], "leads": [], "url": self.page.url}

        # Auto-save to CSV if filename was specified in prompt
        saved_path = None
        file_appended = False
        if csv_filename:
            try:
                from .output_path import save_csv, should_append_to_file, get_file_location_message
                from pathlib import Path

                # Smart CSV output: use clean domain URL (not tracking URLs)
                if wants_contact:
                    # Output: website, contact (email or contact_url - whichever is available)
                    csv_data = []
                    for lead in normalized_leads:
                        # Use clean domain URL if available, otherwise fall back to full URL
                        website = lead.get("domain_url") or lead.get("url", "")
                        contact = lead.get("email") or lead.get("contact_url") or ""
                        csv_data.append({
                            "website": website,
                            "contact": contact,
                        })
                    headers = ["website", "contact"]
                else:
                    # Simple URL-only output - use clean domain URLs
                    csv_data = []
                    for lead in normalized_leads:
                        website = lead.get("domain_url") or lead.get("url", "")
                        csv_data.append({"website": website})
                    headers = ["website"]

                # Check if user wants to append to existing file
                append_mode = should_append_to_file(prompt)
                saved_path_obj = save_csv(csv_filename, csv_data, headers=headers, append=append_mode)
                saved_path = str(saved_path_obj)
                file_appended = append_mode and saved_path_obj.exists()
                # Show clear file location message
                file_msg = get_file_location_message(saved_path_obj, len(csv_data), file_appended)
                print_step(self.step, "save", file_msg, "success")
            except Exception as e:
                print_step(self.step, "save", f"Failed to save CSV: {e}", "error")

        elapsed_total = int(time.time() - start_time)
        result_summary = f"Found {len(urls)} unique advertisers in {elapsed_total}s"
        if saved_path:
            result_summary += f" - saved to {csv_filename}"

        # Completion message with file location
        completion_msg = f"Done! Found {len(urls)} advertisers in {elapsed_total}s"
        if saved_path:
            completion_msg += f"\n{Colors.CYAN}  File: {saved_path}{Colors.RESET}"
        print(f"{Colors.GREEN}  * FB Ads: {completion_msg}{Colors.RESET}")

        return {
            "status": "complete",
            "result": "\n".join(urls) if urls_only else result_summary,
            "steps": self.step,
            "data": normalized_leads,
            "leads": normalized_leads,
            "urls": urls,
            "url": urls[0],
            "saved_path": saved_path,
            "elapsed_seconds": elapsed_total,
        }

    def _get_target_subreddits(self, topic: str) -> List[str]:
        """Get relevant subreddits for the topic."""
        topic_lower = topic.lower()
        for keyword, subs in ICP_SUBREDDITS.items():
            if keyword in topic_lower:
                return subs
        return ICP_SUBREDDITS["default"]

    async def workflow_reddit_icp(self, icp_description: str, max_leads: int = 20) -> Dict:
        """
        ICP-focused Reddit extraction (SMARTEST).
        Uses find_icp_profile_urls for ICP-scored leads with profile URLs.

        Best for: "find agency owners", "find SaaS founders", etc.
        Returns pre-scored leads based on ICP match signals.
        """
        if not REDDIT_HANDLER_AVAILABLE:
            return None

        self.step = 0

        # Immediately show progress so user knows we're working
        print(f"{Colors.CYAN}  * Reddit ICP: Finding '{icp_description[:40]}'...{Colors.RESET}")

        try:
            self.step += 1
            print_step(self.step, "icp", f"ICP search: {icp_description[:40]}", "running")

            # Use the ICP profile URL extraction
            result = await find_icp_profile_urls(
                icp_description=icp_description,
                target_count=max_leads,
                deep_scan=False,  # Fast mode
                min_score=20
            )

            if result.get("success") and result.get("matches"):
                matches = result["matches"]
                print_step(self.step, "icp", f"{len(matches)} ICP matches found", "success")

                # Format leads from matches
                leads = []
                for match in matches:
                    leads.append({
                        "username": match["username"],
                        "url": match["profile_url"],
                        "subreddit": match.get("source", "").replace("r/", ""),
                        "icp_score": match.get("score", 0),
                        "total_score": match.get("score", 0),
                        "comment_count": 1,
                        "has_icp_signal": match.get("score", 0) >= 50,
                        "warm_signal": ", ".join(match.get("signals", [])[:2]),
                        "source": "icp_extraction"
                    })

                icp_count = sum(1 for l in leads if l.get("has_icp_signal"))

                self.step += 1
                print_step(self.step, "complete", f"{len(leads)} leads ({icp_count} high ICP)", "success")

                return {
                    "status": "complete",
                    "result": f"Found {len(leads)} ICP-matched users ({icp_count} high score)",
                    "steps": self.step,
                    "url": leads[0]["url"] if leads else "",
                    "data": leads,
                    "leads": leads,
                    "icp_count": icp_count,
                    "metadata": result.get("metadata", {}),
                    "source": "icp_extraction"
                }

        except Exception as e:
            print_step(self.step, "icp", f"ICP search failed: {str(e)[:30]}", "error")

        return None

    async def workflow_reddit_api(self, topic: str, max_leads: int = 10, prompt: Optional[str] = None) -> Dict:
        """
        Reddit extraction via JSON API (FASTEST) with PARALLEL processing.

        Uses all available tricks:
        1. JSON API - Primary, fastest
        2. find_commenters - Gets engaged users from comments
        3. find_users_by_interest - Cross-subreddit aggregation
        4. PullPush - Historical data fallback
        5. find_icp_profile_urls - ICP-based extraction

        All subreddits searched IN PARALLEL for maximum speed.
        """
        if not REDDIT_HANDLER_AVAILABLE:
            return None

        self.step = 0

        # Immediately show progress so user knows we're working
        print(f"{Colors.CYAN}  * Reddit: Searching for warm leads in {topic[:40]}...{Colors.RESET}")

        prompt_text = prompt or topic
        icp_text = extract_icp_text(prompt_text)
        date_window = parse_relative_date_window(prompt_text, default_min_days=7, default_max_days=14)
        after_utc, before_utc = date_window.to_after_before_utc()
        keywords = extract_keywords(icp_text or prompt_text)
        if not keywords:
            keywords = extract_keywords(topic)
        if not keywords and topic:
            keywords = [topic.strip()[:60]]
        keywords = await self.expand_keywords(icp_text, keywords)
        explicit_window = has_explicit_date_window(prompt_text)

        target_subs = self._get_target_subreddits(icp_text or topic)

        # ICP keywords for filtering warm leads
        ICP_SIGNALS = [
            'looking for', 'need help', 'anyone know', 'recommend', 'suggestions',
            'struggling with', 'how do i', 'how to', 'best way', 'advice',
            'my business', 'my company', 'our team', 'we need', 'i need',
            'agency', 'startup', 'founder', 'ceo', 'owner', 'entrepreneur',
            'client', 'customer', 'leads', 'sales', 'marketing', 'growth',
            'revenue', 'mrr', 'arr', 'churn', 'conversion', 'roi'
        ]

        try:
            handler = RedditHandler()

            # If the user explicitly specified a date window, prefer PullPush for precise after/before filtering.
            if explicit_window:
                self.step += 1
                print_step(self.step, "pullpush", f"after/before: {date_window.min_days_ago}-{date_window.max_days_ago}d", "running")
                pullpush_leads = await self._reddit_pullpush_warm_leads(
                    handler=handler,
                    topic=topic,
                    subreddits=target_subs,
                    keywords=keywords,
                    after_utc=after_utc,
                    before_utc=before_utc,
                    max_leads=max_leads,
                )
                if pullpush_leads:
                    if icp_text:
                        pullpush_leads = await self.analyze_leads_parallel(
                            pullpush_leads[: min(len(pullpush_leads), 12)],
                            icp_text
                        )
                        pullpush_leads = [l for l in pullpush_leads if l.get("icp_score", 0) >= 50]

                    icp_count = sum(1 for l in pullpush_leads if l.get("matched_keywords"))
                    summary_lines = []
                    for lead in pullpush_leads[: min(5, len(pullpush_leads))]:
                        summary_lines.append(
                            f"reddit lead u/{lead.get('username')} evidence={lead.get('evidence_url','')} profile={lead.get('profile_url','')}"
                        )

                    self.step += 1
                    print_step(self.step, "complete", f"{len(pullpush_leads)} leads ({icp_count} kw)", "success")
                    if extract_output_contract(prompt_text).get("no_extra_text"):
                        token_text = self._format_reddit_tokens_only(pullpush_leads, prompt_text, max_leads)
                        return {
                            "status": "complete",
                            "result": token_text,
                            "steps": self.step,
                            "url": (token_text.splitlines()[0].strip() if token_text else ""),
                            "data": pullpush_leads[:max_leads],
                            "leads": pullpush_leads[:max_leads],
                            "source": "pullpush",
                            "date_window_days": {"min": date_window.min_days_ago, "max": date_window.max_days_ago},
                            "keywords": keywords,
                        }
                    return {
                        "status": "complete",
                        "result": f"Found {len(pullpush_leads)} warm leads ({icp_count} with keyword evidence)",
                        "steps": self.step,
                        "url": pullpush_leads[0].get("evidence_url") or pullpush_leads[0].get("profile_url") or "",
                        "data": pullpush_leads[:max_leads],
                        "leads": pullpush_leads[:max_leads],
                        "summary": "\n".join(summary_lines),
                        "icp_count": icp_count,
                        "source": "pullpush",
                        "date_window_days": {"min": date_window.min_days_ago, "max": date_window.max_days_ago},
                        "keywords": keywords,
                    }
                print_step(self.step, "pullpush", "no results", "error")

            # =====================================================================
            # STRATEGY 1: Parallel subreddit search (FAST)
            # =====================================================================
            self.step += 1
            print_step(self.step, "parallel", f"searching {len(target_subs[:4])} subreddits", "running")

            async def search_subreddit(sub: str) -> List[Dict]:
                """Search single subreddit - runs in parallel."""
                leads = []
                try:
                    result = await handler.find_commenters(
                        subreddit=sub,
                        query=topic,
                        max_posts=5,
                        max_comments_per_post=30,
                        min_score=1,
                        after_utc=after_utc,
                        before_utc=before_utc,
                        icp_keywords=keywords or None,
                        require_keyword_match=True,
                    )

                    if result.get("success") and result.get("commenters"):
                        for commenter in result["commenters"][:max_leads]:
                            evidence = commenter.get("sample_comments", []) or []
                            evidence_url = ""
                            if evidence:
                                evidence_url = (evidence[0].get("comment_url") or evidence[0].get("post_url") or "")

                            leads.append({
                                "username": commenter["username"],
                                "url": commenter["profile_url"],  # backward-compat
                                "profile_url": commenter["profile_url"],
                                "evidence_url": evidence_url,
                                "subreddit": sub,
                                "total_score": commenter.get("total_score", 0),
                                "comment_count": commenter.get("comment_count", 0),
                                "matched_keywords": commenter.get("matched_keywords", []),
                                "has_icp_signal": bool(commenter.get("matched_keywords")),
                                "icp_match_score": commenter.get("icp_match_score", 0),
                                "warm_signal": (evidence[0].get("body", "")[:140] if evidence else ""),
                                "evidence": evidence,
                                "source": "json_api"
                            })
                except Exception:
                    pass
                return leads

            # Run all subreddit searches IN PARALLEL - Increased to 6 for better coverage
            tasks = [search_subreddit(sub) for sub in target_subs[:6]]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            all_leads = []
            for result in results:
                if isinstance(result, list):
                    all_leads.extend(result)

            subs_with_results = sum(1 for r in results if isinstance(r, list) and len(r) > 0)
            print_step(self.step, "parallel", f"{subs_with_results} subs, {len(all_leads)} users", "success")

            # =====================================================================
            # STRATEGY 2: find_users_by_interest for cross-subreddit aggregation
            # =====================================================================
            if len(all_leads) < max_leads:
                self.step += 1
                print_step(self.step, "aggregate", "cross-subreddit search", "running")
                try:
                    # Extract keywords from topic
                    interest_keywords = [w for w in topic.lower().split() if len(w) > 3][:5]
                    if not interest_keywords:
                        interest_keywords = [topic]

                    interested = await handler.find_users_by_interest(
                        topic_keywords=interest_keywords,
                        subreddits=target_subs[:5],
                        min_engagement=3,
                        max_posts_per_search=5
                    )

                    for user in interested[:max_leads]:
                        if not any(l["username"] == user["username"] for l in all_leads):
                            evidence = user.get("sample_comments", []) or []
                            evidence_url = ""
                            if evidence:
                                evidence_url = (evidence[0].get("comment_url") or evidence[0].get("post_url") or "")
                            all_leads.append({
                                "username": user["username"],
                                "url": user["profile_url"],  # backward-compat
                                "profile_url": user["profile_url"],
                                "evidence_url": evidence_url,
                                "subreddit": ", ".join(user.get("subreddits", [])[:2]),
                                "total_score": user.get("total_score", 0),
                                "comment_count": user.get("comment_count", 0),
                                "matched_keywords": user.get("keywords", []),
                                "has_icp_signal": True,
                                "warm_signal": (evidence[0].get("body", "")[:140] if evidence else ""),
                                "evidence": evidence,
                                "source": "cross_subreddit"
                            })

                    print_step(self.step, "aggregate", f"+{len(interested)} users", "success")
                except Exception as e:
                    print_step(self.step, "aggregate", str(e)[:30], "error")

            # =====================================================================
            # STRATEGY 3: PullPush for historical data (if still need more)
            # =====================================================================
            if len(all_leads) < max_leads // 2:
                self.step += 1
                print_step(self.step, "pullpush", "historical archive", "running")
                try:
                    # Search within requested window (or default)
                    after_ts = after_utc
                    before_ts = before_utc

                    for sub in target_subs[:2]:
                        pp_result = await handler.search_pullpush(
                            query=topic,
                            subreddit=sub,
                            after=after_ts,
                            before=before_ts,
                            limit=30,
                            content_type="submission"
                        )

                        if pp_result.get("success"):
                            for item in pp_result.get("items", []):
                                author = item.author if hasattr(item, 'author') else item.get('author', '')
                                if not author or author in ['[deleted]', 'AutoModerator']:
                                    continue
                                if any(l["username"] == author for l in all_leads):
                                    continue

                                title = item.title if hasattr(item, 'title') else item.get('title', '')
                                matched = [k for k in keywords[:10] if k.lower() in title.lower()]
                                if not matched:
                                    continue

                                all_leads.append({
                                    "username": author,
                                    "url": f"https://www.reddit.com/user/{author}",
                                    "profile_url": f"https://www.reddit.com/user/{author}",
                                    "evidence_url": (item.permalink if hasattr(item, 'permalink') else item.get('permalink', '')),
                                    "subreddit": sub,
                                    "total_score": item.score if hasattr(item, 'score') else item.get('score', 0),
                                    "comment_count": 0,
                                    "matched_keywords": matched[:6],
                                    "has_icp_signal": True,
                                    "icp_match_score": len(matched) * 12,
                                    "warm_signal": title[:140],
                                    "evidence": [{
                                        "type": "post",
                                        "post_title": title[:100],
                                        "post_url": (item.permalink if hasattr(item, 'permalink') else item.get('permalink', '')),
                                        "matched_keywords": matched[:6],
                                    }],
                                    "source": "pullpush"
                                })

                    print_step(self.step, "pullpush", f"total {len(all_leads)} users", "success")
                except Exception as e:
                    print_step(self.step, "pullpush", str(e)[:30], "error")

            # =====================================================================
            # Final processing: sort, dedupe, return
            # =====================================================================
            if all_leads:
                # Sort by keyword evidence first, then engagement score
                all_leads.sort(key=lambda x: (
                    x.get("icp_match_score", 0),
                    x.get("total_score", 0) * max(x.get("comment_count", 1), 1),
                ), reverse=True)

                # Dedupe by username
                seen = set()
                unique_leads = []
                for lead in all_leads:
                    if lead["username"] not in seen:
                        seen.add(lead["username"])
                        unique_leads.append(lead)

                icp_count = sum(1 for l in unique_leads if l.get("has_icp_signal"))

                # Collect sources used
                sources = list(set(l.get("source", "unknown") for l in unique_leads))

                self.step += 1
                print_step(self.step, "complete", f"{len(unique_leads)} leads ({icp_count} ICP)", "success")

                summary_lines = []
                for lead in unique_leads[: min(5, len(unique_leads))]:
                    summary_lines.append(
                        f"reddit lead u/{lead.get('username')} evidence={lead.get('evidence_url','')} profile={lead.get('profile_url','')}"
                    )

                if extract_output_contract(prompt_text).get("no_extra_text"):
                    token_text = self._format_reddit_tokens_only(unique_leads, prompt_text, max_leads)
                    return {
                        "status": "complete",
                        "result": token_text,
                        "steps": self.step,
                        "url": (token_text.splitlines()[0].strip() if token_text else ""),
                        "data": unique_leads[:max_leads],
                        "leads": unique_leads[:max_leads],
                        "icp_count": icp_count,
                        "sources": sources,
                        "source": "multi_strategy",
                        "date_window_days": {"min": date_window.min_days_ago, "max": date_window.max_days_ago},
                        "keywords": keywords,
                    }

                # Completion message
                print(f"{Colors.GREEN}  * Reddit: Done! Found {len(unique_leads)} leads ({icp_count} with ICP signals){Colors.RESET}")

                return {
                    "status": "complete",
                    "result": f"Found {len(unique_leads)} warm leads ({icp_count} with keyword evidence)",
                    "steps": self.step,
                    "url": (unique_leads[0].get("evidence_url") or unique_leads[0].get("url")) if unique_leads else "",
                    "data": unique_leads[:max_leads],
                    "leads": unique_leads[:max_leads],
                    "summary": "\n".join(summary_lines),
                    "icp_count": icp_count,
                    "sources": sources,
                    "source": "multi_strategy",
                    "date_window_days": {"min": date_window.min_days_ago, "max": date_window.max_days_ago},
                    "keywords": keywords,
                }

            await handler.close()

        except Exception as e:
            error_msg = str(e)[:50]
            print_step(self.step, "api", f"Reddit API failed: {error_msg}", "error")
            print(f"{Colors.YELLOW}  * Reddit API unavailable - will try browser fallback{Colors.RESET}")

        return None  # Signal to use browser fallback

    async def workflow_reddit(self, topic: str, max_leads: int = 5, prompt: Optional[str] = None) -> Dict:
        """
        Reddit workflow - find WARM leads who posted/commented about topic in last 7-14 days.

        Strategy (tries in order, uses first that works):
        1. ICP extraction for ICP-focused queries (smartest)
        2. Multi-strategy API with parallel processing (fastest)
        3. Browser fallback (most reliable)

        Returns users who are actually engaged (not just random usernames):
        - Posted about the topic recently
        - Shows ICP signals (asking questions, sharing problems, looking for solutions)
        - Includes what they said as warm signal
        """
        prompt_text = prompt or topic
        icp_text = extract_icp_text(prompt_text)
        from .platform_data import PLATFORM_INDICATORS, PLATFORM_REDDIT
        handler_data = PLATFORM_INDICATORS[PLATFORM_REDDIT]
        
        if not REDDIT_HANDLER_AVAILABLE:
            # Skip to browser fallback if no handler available
            pass
        else:
            # Check if this is an ICP-focused query (looking for specific persona)
            icp_keywords = ['agency', 'founder', 'owner', 'ceo', 'startup', 'saas',
                           'consultant', 'entrepreneur', 'business owner', 'coach']
            topic_lower = topic.lower()
            is_icp_query = any(kw in topic_lower for kw in icp_keywords)

            # SMART PATH: Try ICP extraction for persona-focused queries, but skip if user asked for warm leads/evidence.
            if is_icp_query and not icp_text and "warm" not in prompt_text.lower():
                icp_result = await self.workflow_reddit_icp(topic, max_leads * 2)
                if icp_result and icp_result.get("leads"):
                    return icp_result

            # FAST PATH: Try multi-strategy API with parallel processing
            api_result = await self.workflow_reddit_api(topic, max_leads, prompt=prompt_text)
            if api_result:
                return api_result

        # FALLBACK: Browser-based extraction (now using state-based recovery)
        print(f"{Colors.CYAN}  * Reddit: Using browser extraction for {topic[:40]}...{Colors.RESET}")
        from .failure_modes import SITE_HINTS
        hints = SITE_HINTS.get("reddit.com")

        # Get targeted subreddits for this topic
        target_subs = self._get_target_subreddits(topic)
        subreddit_filter = "+".join(target_subs[:3])  # Use top 3 relevant subreddits
        search_url = f"https://www.reddit.com/r/{subreddit_filter}/search/?q={quote_plus(topic)}&restrict_sr=1&sort=new&t=month"

        async def reddit_extractor():
            return await self.page.evaluate(r"""(limit) => {
                const res=[];const posts=document.querySelectorAll('[data-testid="post-container"],.thing,article');
                for(const p of posts){if(res.length>=limit)break;
                const a=p.querySelector('a[href*="/user/"],a[href*="/u/"]');if(!a)continue;
                const u=a.href.split('/user/')[1]?.split('/')[0] || a.href.split('/u/')[1]?.split('/')[0];
                if(!u||['reddit','deleted'].includes(u.toLowerCase()))continue;
                const t=p.querySelector('h3,.title')?.innerText?.trim()||'';
                res.push({username:u,url:'https://www.reddit.com/user/'+u,title:t,source:'reddit'});}
                return res;
            }""", max_leads)

        result = await self.generic_search_and_extract(
            url=search_url,
            hints=hints,
            label=f"Reddit r/{subreddit_filter}",
            extractor_func=reddit_extractor
        )

        # Make the top extracted profile URL the primary URL for URL-focused prompts.
        try:
            data = result.get("data") if isinstance(result, dict) else None
            if isinstance(data, list) and data:
                # Add completion message for browser fallback
                lead_count = len(data)
                print(f"{Colors.GREEN}  * Reddit: Done! Found {lead_count} leads via browser{Colors.RESET}")

                first = data[0] if isinstance(data[0], dict) else {}
                first_url = (first.get("profile_url") or first.get("url") or "").strip()
                if first_url:
                    result["url"] = first_url
                    pl = (prompt_text or "").lower()
                    urls_only = (
                        ("urls only" in pl)
                        or ("no explanations" in pl)
                        or ("no explanation" in pl)
                        or ("output only" in pl and ("url" in pl or "urls" in pl or "username" in pl or "usernames" in pl))
                        or (bool(re.search(r"\boutput\s+(?:exactly\s+)?(?:1|one)\b", pl)) and ("url" in pl or "urls" in pl))
                    )
                    if urls_only:
                        result["result"] = first_url
        except Exception:
            pass

        return result

    async def workflow_google_maps(self, query: str, max_leads: int = 20, prompt: str = "") -> Dict:
        """
        Google Maps business search workflow.

        Tricks used:
        - Feed panel scrolling for more results
        - aria-label extraction for clean business names
        - Place URL parsing for business details
        """
        self.step = 0
        prompt_lower = (prompt or "").lower()

        # Immediately show progress so user knows we're working
        print(f"{Colors.CYAN}  * Google Maps: Searching for '{query[:40]}'...{Colors.RESET}")

        def wants_urls_only(p: str) -> bool:
            pl = (p or "").lower()
            return (
                ("urls only" in pl) or
                ("no explanations" in pl) or
                ("no explanation" in pl) or
                ("output only" in pl and ("url" in pl or "urls" in pl)) or
                (bool(re.search(r"\boutput\s+(?:exactly\s+)?(?:1|one)\b", pl)) and ("url" in pl or "urls" in pl))
            )

        urls_only = wants_urls_only(prompt_lower)

        # Step 1: Navigate
        self.step += 1
        print_step(self.step, "navigate", "Google Maps", "running")
        nav_result = await self.navigate(f"https://www.google.com/maps/search/{quote_plus(query)}")
        if isinstance(nav_result, dict) and nav_result.get("status") == "blocked":
            return nav_result
        await asyncio.sleep(3)
        print_step(self.step, "navigate", "Google Maps", "success")

        # Step 2: Scroll results panel for more businesses
        self.step += 1
        print_step(self.step, "scroll", "loading businesses", "running")
        for _ in range(3):
            # Scroll the results feed panel
            await self.page.evaluate(r"""() => {
                const panel = document.querySelector('[role="feed"]');
                if (panel) panel.scrollTop += 800;
            }""")
            await asyncio.sleep(1)
        print_step(self.step, "scroll", "loading businesses", "success")

        # Step 3: Extract businesses
        self.step += 1
        print_step(self.step, "extract", "businesses", "running")

        businesses = await self.page.evaluate(r"""(maxLeads) => {
            const results = [];
            const seen = new Set();

            document.querySelectorAll('a[href*="/maps/place/"]').forEach(a => {
                if (results.length >= maxLeads) return;

                const name = a.getAttribute('aria-label') || a.innerText?.trim() || '';
                const href = a.href;

                // Skip empty or duplicates
                if (!name || name.length < 2 || seen.has(name)) return;
                seen.add(name);

                // Extract place ID from URL if available
                const placeMatch = href.match(/place\/([^\/]+)/);
                const placeId = placeMatch ? placeMatch[1] : '';

                results.push({
                    name: name.substring(0, 100),
                    url: href,
                    place_id: placeId,
                    source: 'google_maps'
                });
            });

            return results;
        }""", max_leads)

        if businesses and len(businesses) > 0:
            seen_urls = set()
            urls: List[str] = []
            for b in businesses:
                u = (b.get("url") or "").strip()
                if not u:
                    continue
                u = u.split("#")[0]
                if u in seen_urls:
                    continue
                seen_urls.add(u)
                urls.append(u)

            found_count = len(urls) if urls else len(businesses)
            print_step(self.step, "extract", f"{found_count} businesses", "success")

            # Completion message
            self.step += 1
            print_step(self.step, "complete", f"Google Maps: Done! Found {found_count} businesses", "success")

            first_url = urls[0] if urls else (self.page.url if self.page else "")
            result_text = "\n".join(urls[: max(1, int(max_leads or 1))]) if urls_only else f"Found {found_count} businesses"

            return {
                "status": "complete",
                "result": result_text,
                "steps": self.step,
                "data": businesses,
                "leads": businesses,
                "urls": urls,
                "url": first_url,
            }

        print_step(self.step, "extract", "No businesses found", "warning")
        print(f"{Colors.YELLOW}  * Google Maps: No results - Try broader search terms or different location{Colors.RESET}")
        return {
            "status": "no_results",
            "result": "No businesses found for this query. Try: (1) Broader search terms, (2) Include location (e.g., 'coffee shops in Seattle'), or (3) Different search keywords.",
            "steps": self.step,
            "url": self.page.url
        }

    async def workflow_linkedin_search(self, query: str, max_leads: int = 10, prompt: str = "") -> Dict:
        """LinkedIn people search workflow (public-first, with Google fallback)."""
        self.step = 0
        prompt_lower = (prompt or "").lower()

        # Immediately show progress so user knows we're working
        print(f"{Colors.CYAN}  * LinkedIn: Searching for '{query[:40]}'...{Colors.RESET}")

        def wants_urls_only(p: str) -> bool:
            pl = (p or "").lower()
            return (
                ("urls only" in pl) or
                ("no explanations" in pl) or
                ("no explanation" in pl) or
                ("output only" in pl and ("url" in pl or "urls" in pl)) or
                (bool(re.search(r"\boutput\s+(?:exactly\s+)?(?:1|one)\b", pl)) and ("url" in pl or "urls" in pl))
            )

        urls_only = wants_urls_only(prompt_lower)

        # Extract conditional count for fallback (e.g., "if blocked, output 1")
        fallback_count = max_leads  # Default to main count
        fallback_match = re.search(r"if\s+blocked[^0-9]*(?:output|return)\s+(\d+)", prompt_lower)
        if fallback_match:
            fallback_count = int(fallback_match.group(1))

        # Step 1: Navigate
        self.step += 1
        print_step(self.step, "navigate", "LinkedIn", "running")
        nav_result = await self.navigate(f"https://www.linkedin.com/search/results/people/?keywords={quote_plus(query)}")
        if isinstance(nav_result, dict) and nav_result.get("status") == "blocked":
            return nav_result
        print_step(self.step, "navigate", "LinkedIn", "success")

        await asyncio.sleep(1.5)

        blocked = False
        try:
            current_url = (self.page.url or "") if self.page else ""
            blocked = any(x in current_url for x in ("/login", "/checkpoint", "authwall"))
        except Exception:
            blocked = False

        profiles = []
        if not blocked:
            # Step 2: Extract profiles
            self.step += 1
            print_step(self.step, "extract", "profiles", "running")

            profiles = await self.page.evaluate(r"""(limit) => {
                const results = [];
                const cards = document.querySelectorAll('.entity-result__item, .search-result__wrapper');
                cards.forEach(card => {
                    if (results.length >= limit) return;
                    const link = card.querySelector('a[href*="/in/"]');
                    const name = card.querySelector('.entity-result__title-text, .actor-name');
                    if (link && name) {
                        results.push({
                            name: name.innerText?.trim(),
                            url: link.href.split('?')[0]
                        });
                    }
                });
                return results.slice(0, Math.max(1, limit || 10));
            }""", max(1, int(max_leads or 10)))

        if profiles and len(profiles) > 0:
            print_step(self.step, "extract", f"{len(profiles)} profiles", "success")

            # Deduplicate URLs before returning
            seen_urls = set()
            unique_urls = []
            for p in profiles:
                url = (p.get("url") or "").strip()
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    unique_urls.append(url)

            # Completion message
            self.step += 1
            print_step(self.step, "complete", f"LinkedIn: Done! Found {len(profiles)} profiles", "success")

            first_url = unique_urls[0] if unique_urls else ""
            return {
                "status": "complete",
                "result": "\n".join(unique_urls[: max(1, int(max_leads or 1))]) if urls_only else f"Found {len(profiles)} profiles",
                "steps": self.step,
                "data": profiles,
                "urls": unique_urls,
                "url": first_url or (self.page.url if self.page else "")
            }

        # Search-engine fallback for blocked/logged-out LinkedIn.
        print(f"{Colors.YELLOW}  * LinkedIn blocked - trying Google fallback...{Colors.RESET}")
        self.step += 1
        print_step(self.step, "fallback", "Google search (LinkedIn profiles)", "running")

        google_query = f"site:linkedin.com/in {query}".strip()
        google_search_url = f"https://www.google.com/search?q={quote_plus(google_query)}"
        
        try:
            await self.page.goto(google_search_url, wait_until='domcontentloaded', timeout=15000)
            await asyncio.sleep(2)

            # Extract LinkedIn URLs from Google results
            profiles = await self.page.evaluate(r"""
                () => {
                    const results = [];
                    const seen = new Set();

                    // Get all links from Google search results
                    document.querySelectorAll('a[href]').forEach(a => {
                        const href = a.href || '';
                        const text = (a.innerText || '').trim();

                        // Only include actual LinkedIn profile URLs
                        if (href.includes('linkedin.com/in/')) {
                            const match = href.match(/linkedin\.com\/in\/([^\/\?&]+)/);
                            if (match && !seen.has(match[1])) {
                                seen.add(match[1]);

                                // Clean up name from Google result
                                let name = text.replace(' - LinkedIn', '').replace(' | LinkedIn', '').trim();

                                // Skip if name is too short or looks like UI text
                                if (name.length > 2 && name.length < 100 && !name.toLowerCase().includes('cached')) {
                                    results.push({
                                        name: name.substring(0, 80),
                                        url: 'https://www.linkedin.com/in/' + match[1],
                                        profile_id: match[1],
                                        source: 'google_fallback'
                                    });
                                }
                            }
                        }
                    });

                    return results.slice(0, 10);
                }
            """)

            if profiles and len(profiles) > 0:
                print_step(self.step, "fallback", f"Found {len(profiles)} profiles via Google", "success")
                print(f"{Colors.GREEN}  * LinkedIn: Done! Found {len(profiles)} profiles via Google fallback{Colors.RESET}")
                first_url = (profiles[0].get("url") or "").strip()
                urls = [(p.get("url") or "").strip() for p in profiles if (p.get("url") or "").strip()]
                if urls_only:
                    result_text = "\n".join(urls[: max(1, int(fallback_count or 1))])
                else:
                    result_text = f"LinkedIn blocked - found {len(profiles)} profiles via Google"
                # Limit data to fallback_count when in fallback mode
                limited_profiles = profiles[:fallback_count] if fallback_count else profiles
                limited_urls = urls[:fallback_count] if fallback_count else urls
                return {
                    "status": "complete",
                    "result": result_text,
                    "steps": self.step,
                    "data": limited_profiles,
                    "google_search_url": google_search_url,
                    "fallback_used": True,
                    "profiles": limited_profiles,
                    "urls": limited_urls,
                    "url": first_url or (self.page.url if self.page else "")
                }
            else:
                print_step(self.step, "fallback", "No profiles found in Google results", "warning")
                print(f"{Colors.YELLOW}  * LinkedIn blocked - Try using a logged-in session or different search terms{Colors.RESET}")
                return {
                    "status": "no_results",
                    "result": f"LinkedIn requires login - Google fallback found no profiles. Try: (1) Log into LinkedIn first, or (2) Use different search terms. Search URL: {google_search_url}",
                    "steps": self.step,
                    "google_search_url": google_search_url,
                    "fallback_used": True,
                    "url": self.page.url
                }
        except Exception as e:
            error_msg = str(e)[:60]
            print_step(self.step, "fallback", f"Google fallback error: {error_msg}", "error")
            print(f"{Colors.YELLOW}  * Suggestion: Log into LinkedIn manually first, then retry{Colors.RESET}")
            return {
                "status": "error",
                "result": f"LinkedIn blocked and Google fallback failed: {error_msg}. Suggestion: Log into LinkedIn first, then retry.",
                "steps": self.step,
                "error": error_msg,
                "url": self.page.url
            }

    async def workflow_linkedin_warm_leads(self, prompt: str, max_leads: int = 10) -> Dict:
        """
        Social warm leads: prioritize people posting about ICP/keywords in a recent window.

        Uses saved browser session state; if the platform blocks public access, this may return no_results.
        """
        self.step = 0

        # Immediately show progress so user knows we're working
        print(f"{Colors.CYAN}  * LinkedIn Warm Leads: Searching recent posts...{Colors.RESET}")

        icp_text = extract_icp_text(prompt)
        date_window = parse_relative_date_window(prompt, default_min_days=7, default_max_days=14)
        keywords = extract_keywords(icp_text or prompt)

        if icp_text and keywords:
            keywords = await self.expand_keywords(icp_text, keywords)

        query = " ".join(keywords[:6]) if keywords else prompt

        self.step += 1
        print_step(self.step, "navigate", "LinkedIn content search", "running")
        nav_result = await self.navigate(f"https://www.linkedin.com/search/results/content/?keywords={quote_plus(query)}")
        if isinstance(nav_result, dict) and nav_result.get("status") == "blocked":
            return nav_result
        print_step(self.step, "navigate", "LinkedIn content search", "success")
        await asyncio.sleep(3)

        self.step += 1
        print_step(self.step, "extract", "warm leads", "running")

        leads = await self.page.evaluate(r"""(payload) => {
            const maxLeads = Math.max(1, parseInt(payload.maxLeads || 10));
            const KEYWORDS = Array.isArray(payload.keywords)
              ? payload.keywords.map(k => (k || '').toLowerCase()).filter(Boolean)
              : [];
            const MIN_AGE_DAYS = (typeof payload.minDaysAgo === 'number') ? payload.minDaysAgo : 0;
            const MAX_AGE_DAYS = (typeof payload.maxDaysAgo === 'number') ? payload.maxDaysAgo : 14;

            const results = [];

            function textOf(el) {
                return (el?.innerText || '').replace(/\s+/g, ' ').trim();
            }

            function parseAgeDays(lowerText) {
                const m = (lowerText || '').match(/\b(\d{1,3})\s*(h|hr|hrs|hour|hours|d|day|days|w|wk|wks|week|weeks|mo|mos|month|months)\b/);
                if (!m) return null;
                const n = parseInt(m[1]);
                const unit = m[2];
                if (!Number.isFinite(n)) return null;
                if (unit.startsWith('h')) return n / 24;
                if (unit.startsWith('d')) return n;
                if (unit.startsWith('w')) return n * 7;
                if (unit.startsWith('mo') || unit.startsWith('m')) return n * 30;
                return null;
            }

            const cards = document.querySelectorAll(
                'li.reusable-search__result-container, div.reusable-search__result-container, .search-result__wrapper'
            );

            for (const card of cards) {
                if (results.length >= maxLeads) break;

                const profileLink = card.querySelector('a[href*=\"/in/\"]');
                if (!profileLink) continue;

                const url = profileLink.href.split('?')[0];
                const postLink = card.querySelector('a[href*=\"/feed/update/\"], a[href*=\"/posts/\"]');
                const postUrl = postLink ? postLink.href.split('?')[0] : null;

                const text = textOf(card);
                if (!text) continue;

                const lower = text.toLowerCase();
                const ageDays = parseAgeDays(lower);

                if (ageDays !== null && ageDays > MAX_AGE_DAYS) continue;
                if (ageDays !== null && ageDays < MIN_AGE_DAYS) continue;

                const matched = KEYWORDS.filter(k => k && lower.includes(k)).slice(0, 6);
                if (KEYWORDS.length && matched.length === 0) continue;

                const name = textOf(card.querySelector('.entity-result__title-text, span[aria-hidden=\"true\"]')) || null;

                results.push({
                    name,
                    url,
                    post_url: postUrl,
                    evidence_url: postUrl || url,
                    matched_keywords: matched,
                    warm_signal: text.slice(0, 220),
                    days_ago: ageDays
                });
            }

            return results;
        }""", {
            "maxLeads": max_leads,
            "keywords": keywords,
            "minDaysAgo": date_window.min_days_ago,
            "maxDaysAgo": date_window.max_days_ago
        })

        if leads and len(leads) > 0:
            print_step(self.step, "extract", f"{len(leads)} warm leads", "success")
            summary_lines = []
            for lead in leads[: min(5, len(leads))]:
                summary_lines.append(
                    f"linkedin lead evidence={lead.get('evidence_url','')} profile={lead.get('url','')}"
                )
            return {
                "status": "complete",
                "result": f"Found {len(leads)} LinkedIn warm leads",
                "steps": self.step,
                "data": leads,
                "leads": leads,
                "url": leads[0].get("evidence_url") or leads[0].get("url") or self.page.url,
                "summary": "\n".join(summary_lines),
                "date_window_days": {"min": date_window.min_days_ago, "max": date_window.max_days_ago},
                "keywords": keywords,
            }

        print_step(self.step, "extract", "no results on LinkedIn, trying Google fallback", "warning")

        # Google SERP fallback for blocked/logged-out LinkedIn
        self.step += 1
        print_step(self.step, "fallback", "Google search (LinkedIn profiles)", "running")

        google_query = f"site:linkedin.com/in {query}".strip()
        google_search_url = f"https://www.google.com/search?q={quote_plus(google_query)}"

        try:
            await self.page.goto(google_search_url, wait_until='domcontentloaded', timeout=15000)
            await asyncio.sleep(2)

            # Extract LinkedIn URLs from Google results
            profiles = await self.page.evaluate(r"""
                (maxLeads) => {
                    const results = [];
                    const seen = new Set();

                    // Get all links from Google search results
                    document.querySelectorAll('a[href]').forEach(a => {
                        if (results.length >= maxLeads) return;
                        const href = a.href || '';
                        const text = (a.innerText || '').trim();

                        // Only include actual LinkedIn profile URLs
                        if (href.includes('linkedin.com/in/')) {
                            const match = href.match(/linkedin\.com\/in\/([^\/\?&]+)/);
                            if (match && !seen.has(match[1])) {
                                seen.add(match[1]);

                                // Clean up name from Google result
                                let name = text.replace(' - LinkedIn', '').replace(' | LinkedIn', '').trim();

                                // Skip if name is too short or looks like UI text
                                if (name.length > 2 && name.length < 100 && !name.toLowerCase().includes('cached')) {
                                    results.push({
                                        name: name.substring(0, 80),
                                        url: 'https://www.linkedin.com/in/' + match[1],
                                        profile_id: match[1],
                                        source: 'google_fallback',
                                        evidence_url: 'https://www.linkedin.com/in/' + match[1],
                                        matched_keywords: [],
                                        warm_signal: 'Found via Google search fallback'
                                    });
                                }
                            }
                        }
                    });

                    return results;
                }
            """, max_leads)

            if profiles and len(profiles) > 0:
                print_step(self.step, "fallback", f"Found {len(profiles)} profiles via Google", "success")
                return {
                    "status": "complete",
                    "result": f"LinkedIn blocked - found {len(profiles)} warm leads via Google",
                    "steps": self.step,
                    "data": profiles,
                    "leads": profiles,
                    "google_search_url": google_search_url,
                    "fallback_used": True,
                    "url": profiles[0].get("url") or self.page.url,
                    "date_window_days": {"min": date_window.min_days_ago, "max": date_window.max_days_ago},
                    "keywords": keywords,
                }
            else:
                print_step(self.step, "fallback", "No profiles found in Google results", "warning")
                return {
                    "status": "no_results",
                    "result": f"LinkedIn blocked - Google fallback found no profiles for: {query}",
                    "steps": self.step,
                    "data": [],
                    "leads": [],
                    "google_search_url": google_search_url,
                    "fallback_used": True,
                    "url": self.page.url
                }
        except Exception as e:
            print_step(self.step, "fallback", f"Google fallback failed: {str(e)[:40]}", "error")
            return {
                "status": "error",
                "result": f"LinkedIn blocked and Google fallback failed: {str(e)}",
                "steps": self.step,
                "data": [],
                "leads": [],
                "url": self.page.url
            }

    # =========================================================================
    # TASK ROUTER - Match task to workflow or use LLM
    # =========================================================================

    def _extract_requested_count(self, prompt: str) -> Optional[int]:
        """
        Extract the exact count requested by user from the prompt.

        Examples:
        - "find 1 reddit user" -> 1
        - "get 5 advertisers" -> 5
        - "find 10 leads" -> 10
        - "collect 200 unique" -> 200
        - "find a reddit user" -> 1 (a/an = 1)

        Returns None if no specific count requested (use default).
        """
        prompt_lower = (prompt or "").lower()

        # Pattern: "output/return N ..." (common in parity prompts)
        number_words = {
            "one": 1,
            "two": 2,
            "three": 3,
            "four": 4,
            "five": 5,
            "six": 6,
            "seven": 7,
            "eight": 8,
            "nine": 9,
            "ten": 10,
        }
        m = re.search(r"\b(?:output|return)\s+(?:exactly\s+)?(\d{1,3})\b", prompt_lower)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                pass
        m = re.search(
            r"\b(?:output|return)\s+(?:exactly\s+)?(one|two|three|four|five|six|seven|eight|nine|ten)\b",
            prompt_lower,
        )
        if m:
            return number_words.get(m.group(1), 1)
        if re.search(r"\b(?:output|return)\s+(?:exactly\s+)?(?:a|an)\b", prompt_lower):
            return 1

        # Pattern: "collect N unique" - common for scraping tasks
        collect_match = re.search(r'\b(?:collect|gather|scrape|extract)\s+(\d{1,4})\s+(?:unique\s+)?(?:advertiser|url|lead|profile|item|result)', prompt_lower)
        if collect_match:
            try:
                return int(collect_match.group(1))
            except ValueError:
                pass

        # Pattern: "N unique advertisers/urls" - number before unique
        unique_match = re.search(r'\b(\d{1,4})\s+unique\s+(?:advertiser|url|lead|profile|item|result)', prompt_lower)
        if unique_match:
            try:
                return int(unique_match.group(1))
            except ValueError:
                pass

        # Pattern: "find/get/search N thing(s)" - explicit number
        from .platform_data import COUNT_PATTERNS
        for pattern in COUNT_PATTERNS:
            match = re.search(pattern, prompt_lower)
            if match:
                return int(match.group(1))

        # Pattern: "a/an thing" = 1
        from .platform_data import PLATFORM_INDICATORS
        all_keywords = []
        for d in PLATFORM_INDICATORS.values(): all_keywords.extend(d["keywords"])
        clean_keywords = [re.escape(k) for k in all_keywords if "/" not in k and "." not in k]
        keywords_pattern = "|".join(clean_keywords)

        if re.search(fr'\b(?:a|an|one|1)\s+(?:{keywords_pattern}|advertiser|user|lead|profile)', prompt_lower):
            return 1

        # No specific count found - return None to use default
        return None

    def _parse_task(self, prompt: str) -> Dict:
        """Parse task to determine workflow using site-agnostic data."""
        prompt_lower = prompt.lower()
        requested_count = self._extract_requested_count(prompt)

        # If the user (or recovery system) explicitly instructs a particular starting source
        # or to continue without navigating, force the flexible LLM workflow so we don't
        # re-route back into a deterministic site workflow.
        if (
            "use this source first:" in prompt_lower
            or "use this source only:" in prompt_lower
            or prompt_lower.startswith("continue from the current page without navigating")
        ):
            return {"workflow": "llm"}

        # 1. Navigation Services
        from .platform_data import (
            NAVIGATION_SERVICES,
            PLATFORM_FB_ADS,
            PLATFORM_GOOGLE_MAPS,
            PLATFORM_INDICATORS,
            PLATFORM_LINKEDIN,
            PLATFORM_REDDIT,
        )

        def _extract_search_query(fallback: str) -> str:
            raw = (prompt or "").strip()
            if not raw:
                return fallback

            m = re.search(r'["\']([^"\']+)["\']', raw)
            if m and m.group(1).strip():
                raw = m.group(1).strip()
            else:
                m = re.search(r"\(([^)]+)\)", raw)
                if m and m.group(1).strip():
                    raw = m.group(1).strip()
                else:
                    # After ":" is often the query intent ("Go to X: find Y")
                    m = re.search(r":\s*(.+)$", raw)
                    if m and m.group(1).strip():
                        raw = m.group(1).strip()

            # Normalize separators commonly used in prompts.
            raw = raw.replace("/", " ").replace("|", " ").replace(",", " ")
            raw = re.sub(r"\s+", " ", raw).strip()

            # Prefer the noun phrase between "output N" and "URL" when present.
            m = re.search(
                r"\boutput\s+(?:exactly\s+)?(?:\d{1,3}|one|a|an)\s+([^\n.;]{3,160}?)\s+url\b",
                raw,
                flags=re.IGNORECASE,
            )
            if m and m.group(1).strip():
                candidate = m.group(1).strip()
                if candidate.lower() not in ("final", "current", "resulting"):
                    raw = candidate

            try:
                kws = extract_keywords(raw)
                if kws:
                    return " ".join(kws[:8])
            except Exception:
                pass

            return raw if len(raw) >= 3 else fallback

        def is_navigation_only_task(p: str) -> bool:
            """
            True when the user is effectively asking to just navigate and report
            the resulting URL/title (Playwright MCP-style "go to X" tasks).
            """
            pl = (p or "").lower()
            if not pl:
                return False

            # Explicit "final/current URL" requests
            if re.search(r"\b(?:final|current|resulting)\s+url\b", pl) or ("url reached" in pl):
                return True

            # Explicit page title requests
            if "page title" in pl or re.search(r"\bwhat\s+is\s+the\s+title\b", pl):
                return True

            # If the prompt contains follow-up actions, it's not navigation-only.
            followup_actions = (
                "search",
                "click",
                "type",
                "enter",
                "fill",
                "submit",
                "select",
                "filter",
                "sort",
                "download",
                "upload",
                "extract",
                "scrape",
                "sign in",
                "log in",
                "login",
                "tell",
                "what",
                "find",
                "get",
                "read",
                "report",
            )
            if any(a in pl for a in followup_actions):
                return False

            return bool(re.search(r"^\s*(?:go\s+to|open|visit|navigate(?:\s+to)?)\b", pl))

        def sanitize_url_candidate(s: str) -> str:
            s = (s or "").strip()
            s = s.strip().strip('\'"')
            s = s.strip("()[]<>")
            # Common trailing punctuation from prompts
            s = s.rstrip(".,;:!?)]\"'")
            return s

        for svc, data in NAVIGATION_SERVICES.items():
            if any(k in prompt_lower for k in data["keywords"]):
                if "go to" in prompt_lower or "open" in prompt_lower or "visit" in prompt_lower or "navigate" in prompt_lower or svc == "zoho":
                    # Only treat as pure navigation when the user is explicitly asking for the final/current URL/title.
                    # Otherwise, let the LLM follow the rest of the instructions on that site.
                    if is_navigation_only_task(prompt_lower):
                        return {"workflow": "navigate", "url": data["url"]}
                    return {"workflow": "llm"}

        # 2. Generic "go to"
        go_to_match = re.search(r'\bgo\s+to\s+([^\s]+)', prompt_lower)
        if go_to_match:
            target = sanitize_url_candidate(go_to_match.group(1))
            if '.' in target or any(target in d["keywords"] for d in NAVIGATION_SERVICES.values()):
                # Only route to bare navigation if it's a navigation-only task.
                if is_navigation_only_task(prompt_lower):
                    return {"workflow": "navigate", "url": target}
                return {"workflow": "llm"}

        # 3. Extraction Workflows
        for platform, data in PLATFORM_INDICATORS.items():
            matched = any(k in prompt_lower for k in data["keywords"])
            # Avoid false positives like "sdr/" matching "r/" (subreddit shorthand).
            if platform == PLATFORM_REDDIT and re.search(r"(?:^|\\s)r/[a-z0-9_]{2,}", prompt_lower):
                matched = True
            if matched:
                workflow = data["workflow"]
                if platform == PLATFORM_FB_ADS:
                    match = re.search(r'["\']([^"\']+)["\']', prompt_lower)
                    query = match.group(1).strip() if match else data["default_query"]
                    return {"workflow": workflow, "query": query, "count": requested_count}
                elif platform == PLATFORM_REDDIT:
                    icp_text = extract_icp_text(prompt)
                    topic = data["default_topic"]
                    if icp_text:
                        icp_keywords = extract_keywords(icp_text)
                        topic = " ".join(icp_keywords[:6]) if icp_keywords else icp_text
                    return {"workflow": workflow, "topic": topic, "prompt": prompt, "count": requested_count}

                # LinkedIn: public/no-login prompts should use people search + Google fallback (not warm-leads).
                if platform == PLATFORM_LINKEDIN:
                    no_login = any(
                        k in prompt_lower
                        for k in (
                            "no login",
                            "no logins",
                            "not logged in",
                            "dont login",
                            "don't login",
                            "do not login",
                        )
                    )
                    wants_public_profile = any(k in prompt_lower for k in ("profile url", "prospect", "/in/")) or "if blocked" in prompt_lower
                    if no_login or wants_public_profile:
                        q = _extract_search_query("sdr lead gen agency")
                        return {"workflow": "linkedin", "query": q, "prompt": prompt, "count": requested_count}

                    return {"workflow": workflow, "prompt": prompt, "count": requested_count}

                # Google Maps: always derive a concrete search query.
                if platform == PLATFORM_GOOGLE_MAPS:
                    q = _extract_search_query("lead generation agency")
                    if "agency" not in q.lower() and any(k in prompt_lower for k in ("lead gen", "lead generation", "appointment setting", "marketing")):
                        q = f"agency {q}".strip()
                    return {"workflow": workflow, "query": q, "prompt": prompt, "count": requested_count}

                # Default: pass a best-effort query instead of a hardcoded placeholder.
                q = _extract_search_query(data.get("default_query") or "SDR")
                return {"workflow": workflow, "prompt": prompt, "query": q, "count": requested_count}

        return {"workflow": "llm"}

    def _split_tasks(self, prompt: str) -> List[str]:
        """Split multi-task prompt into individual tasks."""
        text = (prompt or "").strip()
        if not text:
            return [prompt]

        # Pre-normalize: add space after sentence-ending punctuation if missing (e.g., ".Go to" -> ". Go to")
        text = re.sub(r'([.!?])([A-Z])', r'\1 \2', text)
        # Normalize multiple spaces to single space
        text = re.sub(r'  +', ' ', text)
        # Strip Unicode whitespace (NBSP, etc.) from the whole text
        text = re.sub(r'[\u00a0\u2000-\u200b\u202f\u205f\u3000]+', ' ', text)

        # More split markers including common transition words
        split_markers = [
            r"\b(?:go\s+to|open|visit|navigate\s+to)\b",
            r"\b(?:then|and\s+then|afterwards|finally)\b",
            r"\b(?:search\s+for|find|get|scrape|extract)\b",
        ]
        split_markers_re = re.compile("|".join(split_markers), re.IGNORECASE)

        # Keywords to identify "site tasks" (used to avoid splitting on semicolons inside a single task).
        site_keywords = [
            "facebook", "fb ads", "meta", "ads library",
            "reddit",
            "linkedin",
            "google maps", "maps.google",
            "gmail", "mail.google",
            "zoho", "zoho mail",
            "twitter", "x.com",
            "youtube",
        ]

        task_prefix_re = re.compile(r"^(?:go\s+to|open|visit|navigate|search|find|get|check|scrape|extract)\b", re.IGNORECASE)
        continuation_re = re.compile(r"^[\s\u00a0]*(?:if|then|else|otherwise|but|and|or)\b", re.IGNORECASE)

        def clean_task(s: str) -> str:
            s = (s or "").strip()
            if not s:
                return ""
            # Strip Unicode whitespace first
            s = re.sub(r'^[\s\u00a0\u2000-\u200b\u202f\u205f\u3000]+', '', s)
            s = re.sub(r'[\s\u00a0\u2000-\u200b\u202f\u205f\u3000]+$', '', s)
            # Strip bullets/numbering like "-", "1.", "1)", "(1)"
            s = re.sub(r"^\s*(?:[-*•]+|\d+\s*[.)]|\(\d+\))\s*", "", s).strip()
            s = s.rstrip().rstrip(";").strip()
            return s

        def is_site_task(s: str) -> bool:
            sl = (s or "").lower()
            if re.search(r"\bfb\b", sl):
                return True
            return any(kw in sl for kw in site_keywords)

        def is_task_like(s: str) -> bool:
            sl = (s or "").strip()
            if not sl:
                return False
            return bool(task_prefix_re.match(sl)) or is_site_task(sl)

        def merge_continuations(parts: List[str]) -> List[str]:
            merged: List[str] = []
            for part in parts:
                t = clean_task(part)
                if not t:
                    continue
                if merged and continuation_re.match(t):
                    merged[-1] = f"{merged[-1]} {t}".strip()
                else:
                    merged.append(t)
            return merged

        def clean_task(s: str) -> str:
            s = (s or "").strip()
            if not s:
                return ""
            # Strip Unicode whitespace first
            s = re.sub(r'^[\s\u00a0\u2000-\u200b\u202f\u205f\u3000]+', '', s)
            s = re.sub(r'[\s\u00a0\u2000-\u200b\u202f\u205f\u3000]+$', '', s)
            # Strip bullets/numbering like "-", "1.", "1)", "(1)"
            s = re.sub(r"^\s*(?:[-*•]+|\d+\s*[.)]|\(\d+\))\s*", "", s).strip()
            s = s.rstrip().rstrip(";").strip()
            return s

        def is_site_task(s: str) -> bool:
            sl = (s or "").lower()
            if re.search(r"\bfb\b", sl):
                return True
            return any(kw in sl for kw in site_keywords)

        def is_task_like(s: str) -> bool:
            sl = (s or "").strip()
            if not sl:
                return False
            return bool(task_prefix_re.match(sl)) or is_site_task(sl)

        def merge_continuations(parts: List[str]) -> List[str]:
            merged: List[str] = []
            for part in parts:
                t = clean_task(part)
                if not t:
                    continue
                if merged and continuation_re.match(t):
                    merged[-1] = f"{merged[-1]} {t}".strip()
                else:
                    merged.append(t)
            return merged

        # 1) Newline/bullet list tasks (common when pasting).
        if "\n" in text or "\r" in text:
            raw_lines = [l for l in re.split(r"[\r\n]+", text) if l.strip()]
            merged_lines = merge_continuations(raw_lines)
            task_lines = [l for l in merged_lines if is_task_like(l)]
            if len(task_lines) > 1:
                return task_lines

        # 2) Multiple "Go to/Open/Visit/Navigate to" clauses in one line.
        # Detect start of new task even without space after punctuation: ".Go to", "!Open"
        # and also handle "Go to X.Go to Y" (no space at all)
        marker_starts: List[int] = []
        for m in split_markers_re.finditer(text):
            idx = m.start()
            if idx == 0:
                marker_starts.append(idx)
                continue
            
            # Check previous non-whitespace char
            j = idx - 1
            while j >= 0 and text[j].isspace():
                j -= 1
            
            if j < 0:
                marker_starts.append(idx)
                continue
                
            # If previous char is punctuation, it's definitely a new task
            if text[j] in ".:!?":
                marker_starts.append(idx)
                continue
                
            # If previous char is lowercase and current is capitalized "Go to", 
            # it's likely a missing delimiter like "meetings".Go to"
            if text[j].islower() and text[idx].isupper():
                marker_starts.append(idx)

        if len(marker_starts) > 1:
            parts: List[str] = []
            for i, start in enumerate(marker_starts):
                end = marker_starts[i + 1] if i + 1 < len(marker_starts) else len(text)
                parts.append(text[start:end])
            merged = merge_continuations(parts)
            if len(merged) > 1:
                return merged

        # 3) Numbered parentheses format: (1) task; (2) task; (3) task
        numbered_paren = re.split(r"\s*\(\d+\)\s*", text)
        numbered_paren = [clean_task(p) for p in numbered_paren if clean_task(p)]
        valid_tasks = [p for p in numbered_paren if is_task_like(p)]
        if len(valid_tasks) > 1:
            return valid_tasks

        # 4) Numbered period format: 1. task 2. task 3. task
        numbered_period = re.split(r"\s*\d+\.\s+", text)
        numbered_period = [clean_task(p) for p in numbered_period if clean_task(p)]
        valid_tasks = [p for p in numbered_period if is_task_like(p)]
        if len(valid_tasks) > 1:
            return valid_tasks

        # 5) Semicolon-separated tasks (only when it *looks* like task delim; preserve "; if blocked, ..." clauses).
        if ";" in text:
            raw_parts = [p.strip() for p in text.split(";") if p.strip()]
            if raw_parts:
                stitched: List[str] = [raw_parts[0]]
                for part in raw_parts[1:]:
                    if continuation_re.match(part):
                        stitched[-1] = f"{stitched[-1]}; {part}".strip()
                    else:
                        stitched.append(part)
                stitched = merge_continuations(stitched)
                # Require at least 2 site tasks; avoids splitting "go to X; click Y" into separate tasks.
                if len(stitched) > 1 and sum(1 for p in stitched if is_site_task(p)) >= 2:
                    return stitched

        return [prompt]

    async def run(self, prompt: str) -> Dict:
        """Run task - routes to workflow or LLM with automatic AGI cognitive architecture."""
        contract = extract_output_contract(prompt)
        quiet_output = bool(contract.get("no_extra_text"))
        print_step._quiet = quiet_output

        def _extract_global_instructions(full_prompt: str) -> str:
            lines = []
            for raw in (full_prompt or "").splitlines():
                t = raw.strip()
                if not t:
                    continue
                tl = t.lower()
                if any(
                    k in tl for k in (
                        "no logins", "dont login", "don't login", "do not login",
                        "public pages only", "public sites only",
                        "spend max", "max ", "minute", "minutes", "seconds",
                        "output only", "no explanations", "no explanation",
                        "nothing else", "no extra text", "https only", "exactly",
                    )
                ):
                    lines.append(t)
            return "\n".join(lines[:12]).strip()

        global_instructions = _extract_global_instructions(prompt)

        # Print header (unless the prompt forbids extra text)
        if not quiet_output:
            print()
            print(f"{Colors.BOLD}{Colors.GREEN}EVERSALE{Colors.RESET} {Colors.DIM}v{VERSION}{Colors.RESET}")
            print(f"{Colors.DIM}{'='*50}{Colors.RESET}")

        # Keep default runtime minimal: only initialize AGI/cognitive reasoning on failure inside _run_single_with_retry.
        cognitive = None
        agi = None

        # Check for multi-task
        tasks = self._split_tasks(prompt)

        import contextlib
        import io

        def _apply_global_instructions(task_prompt: str) -> str:
            if not global_instructions:
                return task_prompt
            tl = (task_prompt or "").lower()
            gl = global_instructions.lower()
            if gl and gl in tl:
                return task_prompt
            return f"{global_instructions}\n\n{task_prompt}"

        def _enforce_output_contract_text(text: str, contract_dict: Dict[str, Any]) -> str:
            if not contract_dict or not contract_dict.get("no_extra_text"):
                return (text or "").strip()
            allow_urls = bool(contract_dict.get("allow_urls", True))
            allow_usernames = bool(contract_dict.get("allow_usernames", True))
            out_lines = []
            seen = set()

            if allow_urls:
                for u in re.findall(r"https?://[^\\s)\\]}>\\\"']+", text or ""):
                    k = u.strip()
                    if not k:
                        continue
                    kl = k.lower()
                    if kl in seen:
                        continue
                    seen.add(kl)
                    out_lines.append(k)

            if allow_usernames:
                candidates = []
                candidates.extend(re.findall(r"\\bu/([a-z0-9_\\-]{2,})\\b", (text or ""), flags=re.IGNORECASE))
                candidates.extend(re.findall(r"reddit\.com/user/([a-z0-9_\-]{2,})", (text or ""), flags=re.IGNORECASE))
                for name in candidates:
                    k = name.strip()
                    if not k:
                        continue
                    kl = k.lower()
                    if kl in seen:
                        continue
                    seen.add(kl)
                    out_lines.append(k)

            return "\n".join(out_lines).strip()

        if len(tasks) > 1:
            if not quiet_output:
                print(f"{Colors.CYAN}Multi-task mode:{Colors.RESET} {len(tasks)} tasks")
                print(f"{Colors.DIM}{'='*50}{Colors.RESET}")

            all_results = []
            for i, task in enumerate(tasks, 1):
                task = _apply_global_instructions(task)
                if not quiet_output:
                    print()
                    print(f"{Colors.BOLD}[Task {i}/{len(tasks)}]{Colors.RESET} {task[:60]}...")
                    print(f"{Colors.DIM}{'-'*50}{Colors.RESET}")

                if quiet_output:
                    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                        result = await self._run_single_with_retry(task, agi, cognitive)
                else:
                    result = await self._run_single_with_retry(task, agi, cognitive)
                clarify_prompt = task
                for _ in range(3):
                    if not (result and result.get("status") == "needs_clarification"):
                        break
                    resolved = await self._maybe_resolve_clarification(clarify_prompt, result)
                    if not resolved or resolved == clarify_prompt:
                        break
                    clarify_prompt = resolved
                    if quiet_output:
                        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                            result = await self._run_single_with_retry(resolved, agi, cognitive)
                    else:
                        result = await self._run_single_with_retry(resolved, agi, cognitive)

                # Autonomous mode should never bubble up needs_clarification (no stdin).
                if self._is_autonomous_mode() and result and result.get("status") == "needs_clarification":
                    result = self._coerce_needs_clarification_to_blocked(clarify_prompt, result)
                all_results.append(result)

                if quiet_output:
                    print(_enforce_output_contract_text(str(result.get("result", "") or ""), contract))
                else:
                    print()
                    task_lower = (task or "").lower()
                    urls_only = (
                        ("output only" in task_lower and ("url" in task_lower or "urls" in task_lower)) or
                        ("urls only" in task_lower) or
                        ("no explanations" in task_lower) or
                        ("no explanation" in task_lower) or
                        (bool(re.search(r"\boutput\s+(?:exactly\s+)?(?:1|one)\b", task_lower)) and ("url" in task_lower or "urls" in task_lower))
                    )
                    if urls_only:
                        requested_count = self._extract_requested_count(task) or 0

                        urls: List[str] = []
                        if isinstance(result.get("urls"), list):
                            urls = [str(u).strip() for u in result.get("urls") if str(u).strip()]

                        if not urls:
                            raw = str(result.get("result", "") or "").strip()
                            # Prefer the structured URL field when the result text isn't already a URL.
                            if (not re.search(r"https?://", raw)) and result.get("url"):
                                raw = str(result.get("url") or "").strip()
                            # Strip common prefixes for URL-only output.
                            raw = re.sub(r"^\s*url\s*:\s*", "", raw, flags=re.IGNORECASE).strip()
                            urls = re.findall(r"https?://[^\\s)\\]}>\\\"']+", raw)

                        if requested_count > 0:
                            urls = urls[:requested_count]

                        print("\n".join(urls).strip() if urls else "")
                    else:
                        # Smart output for multi-task - same logic as single task
                        leads = result.get('leads', [])
                        data = result.get('data', [])
                        has_structured_data = (isinstance(leads, list) and len(leads) > 0) or (isinstance(data, list) and len(data) > 0)

                        output_printed = False

                        if has_structured_data:
                            output_lines = []
                            _format_task_data_clean(result, output_lines, indent="")
                            for line in output_lines:
                                try:
                                    print(f"  {line}")
                                except UnicodeEncodeError:
                                    print(f"  {line.encode('ascii', 'replace').decode('ascii')}")
                            output_printed = True
                        else:
                            # Try smart LLM output for general tasks
                            try:
                                smart_output = await generate_smart_output(task, result, getattr(self, 'kimi_client', None))
                                if smart_output:
                                    for line in smart_output.split('\n')[:20]:
                                        try:
                                            print(f"  {line}")
                                        except UnicodeEncodeError:
                                            print(f"  {line.encode('ascii', 'replace').decode('ascii')}")
                                    output_printed = True
                            except Exception:
                                pass

                            # Fallback to standard text output
                            if not output_printed:
                                raw_result = str(result.get('result', '') or '')
                                cleaned_result = clean_llm_output(raw_result)
                                if cleaned_result:
                                    for line in cleaned_result.split('\n')[:20]:
                                        try:
                                            print(f"  {line}")
                                        except UnicodeEncodeError:
                                            print(f"  {line.encode('ascii', 'replace').decode('ascii')}")

                        if result.get('url'):
                            print(f"  {Colors.CYAN}URL: {result.get('url')}{Colors.RESET}")
                        if result.get('saved_path'):
                            print(f"  {Colors.CYAN}File: {result.get('saved_path')}{Colors.RESET}")

            if not quiet_output:
                print()
                print(f"{Colors.DIM}{'='*50}{Colors.RESET}")
                print(f"{Colors.GREEN}{Colors.BOLD}+ All tasks complete{Colors.RESET}")
                # Show any saved files from all tasks
                for r in all_results:
                    if r and r.get('saved_path'):
                        print(f"  {Colors.CYAN}File: {r.get('saved_path')}{Colors.RESET}")
                        print(f"  {Colors.DIM}(Run again with 'add more' to append){Colors.RESET}")
                        break  # Only show first file location
            return {"tasks": all_results, "status": "complete"}

        # Single task
        prompt = _apply_global_instructions(prompt)
        if not quiet_output:
            print(f"{Colors.DIM}Task: {prompt[:60]}...{Colors.RESET}" if len(prompt) > 60 else f"{Colors.DIM}Task: {prompt}{Colors.RESET}")
            print(f"{Colors.DIM}{'='*50}{Colors.RESET}")

        if quiet_output:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                result = await self._run_single_with_retry(prompt, agi, cognitive)
        else:
            result = await self._run_single_with_retry(prompt, agi, cognitive)
        clarify_prompt = prompt
        for _ in range(3):
            if not (result and result.get("status") == "needs_clarification"):
                break
            resolved = await self._maybe_resolve_clarification(clarify_prompt, result)
            if not resolved or resolved == clarify_prompt:
                break
            clarify_prompt = resolved
            if quiet_output:
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    result = await self._run_single_with_retry(resolved, agi, cognitive)
            else:
                result = await self._run_single_with_retry(resolved, agi, cognitive)

        # Autonomous mode should never bubble up needs_clarification (no stdin).
        if self._is_autonomous_mode() and result and result.get("status") == "needs_clarification":
            result = self._coerce_needs_clarification_to_blocked(clarify_prompt, result)

        if quiet_output:
            print(_enforce_output_contract_text(str(result.get("result", "") or ""), contract))
        else:
            # Smart output formatting for all task types
            print()
            status = str(result.get("status") or "").lower()
            if status == "blocked":
                print(f"{Colors.RED}{Colors.BOLD}+ Blocked{Colors.RESET}")
            elif status == "error":
                print(f"{Colors.RED}{Colors.BOLD}+ Error{Colors.RESET}")
            else:
                print(f"{Colors.GREEN}{Colors.BOLD}+ Complete{Colors.RESET}")
            print(f"{Colors.DIM}{'~'*50}{Colors.RESET}")

            # Check if we have structured data (leads/data) to format nicely
            leads = result.get('leads', [])
            data = result.get('data', [])
            has_structured_data = (isinstance(leads, list) and len(leads) > 0) or (isinstance(data, list) and len(data) > 0)

            output_printed = False

            if has_structured_data:
                # Use clean formatter for known structured workflows
                output_lines = []
                _format_task_data_clean(result, output_lines, indent="")
                for line in output_lines:
                    try:
                        print(f"  {line}")
                    except UnicodeEncodeError:
                        print(f"  {line.encode('ascii', 'replace').decode('ascii')}")
                output_printed = True
            else:
                # Try smart LLM output for general tasks
                try:
                    smart_output = await generate_smart_output(prompt, result, getattr(self, 'kimi_client', None))
                    if smart_output:
                        for line in smart_output.split('\n'):
                            try:
                                print(f"  {line}")
                            except UnicodeEncodeError:
                                print(f"  {line.encode('ascii', 'replace').decode('ascii')}")
                        output_printed = True
                except Exception as e:
                    logger.debug(f"Smart output failed: {e}")

                # Fallback to standard text output
                if not output_printed:
                    raw_result = str(result.get('result', '') or '')
                    cleaned_result = clean_llm_output(raw_result)
                    if cleaned_result:
                        for line in cleaned_result.split('\n'):
                            try:
                                print(f"  {line}")
                            except UnicodeEncodeError:
                                print(f"  {line.encode('ascii', 'replace').decode('ascii')}")

            # Show URL if available
            if result.get('url'):
                print(f"  {Colors.CYAN}URL: {result.get('url')}{Colors.RESET}")

            # Show saved file location
            if result.get('saved_path'):
                print(f"  {Colors.CYAN}File: {result.get('saved_path')}{Colors.RESET}")
                print(f"  {Colors.DIM}(Run again with 'add more' to append){Colors.RESET}")

            print(f"{Colors.DIM}{'~'*50}{Colors.RESET}")
            print(f"  {Colors.GREEN}{result.get('steps', 0)} steps{Colors.RESET}")

        return result

    def _format_reddit_tokens_only(self, leads: List[Dict[str, Any]], prompt: str, limit: int) -> str:
        contract = extract_output_contract(prompt or "")
        allow_urls = bool(contract.get("allow_urls", True))
        allow_usernames = bool(contract.get("allow_usernames", True))

        out_lines: List[str] = []
        seen = set()

        def add_line(s: str) -> None:
            s = (s or "").strip()
            if not s:
                return
            key = s.lower()
            if key in seen:
                return
            seen.add(key)
            out_lines.append(s)

        for lead in (leads or [])[: max(1, int(limit or 1))]:
            username = (lead.get("username") or "").strip()
            profile_url = (lead.get("profile_url") or lead.get("url") or "").strip()
            evidence_url = (lead.get("evidence_url") or "").strip()
            thread_url = ""

            ev = None
            ev_list = lead.get("evidence") or []
            if isinstance(ev_list, list) and ev_list:
                ev = ev_list[0] if isinstance(ev_list[0], dict) else None
            if ev and isinstance(ev, dict):
                thread_url = (ev.get("thread_url") or ev.get("post_url") or "").strip()
            if not thread_url and evidence_url:
                thread_url = self._reddit_thread_url_from_comment_url(evidence_url) or evidence_url

            if allow_urls:
                add_line(thread_url)
            if allow_usernames:
                add_line(username)
            if allow_urls:
                add_line(profile_url)

        return "\n".join(out_lines).strip()

    def _blocked_to_needs_clarification(self, original_prompt: str, blocked: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert an internal block (captcha/login/bot/geo/overlay) into a single clarification
        prompt that the CLI can ask the user.
        """
        url = str(blocked.get("url") or (self.page.url if self.page else "") or "").strip()
        reason = str(blocked.get("block_reason") or "blocked").strip().lower()
        screenshot = str(blocked.get("screenshot") or "").strip()
        err = str(blocked.get("error") or "").strip()

        if reason == "captcha":
            question = f"CAPTCHA detected at {url}. Solve it in the browser, then continue."
        elif reason == "auth":
            question = f"Login required at {url}. Log in (and finish any MFA), then continue."
        elif reason == "bot":
            question = f"Bot/anti-automation check detected at {url}. If you can pass it manually, continue."
        elif reason == "geo":
            question = f"Blocked by region/location at {url}. Provide an alternate source or URL."
        elif reason == "overlay":
            question = f"A cookie/consent overlay is blocking interaction at {url}. Close it, then continue."
        elif reason == "rate_limited":
            question = f"Rate-limited at {url}. Wait a bit, then continue or pick another source."
        else:
            question = f"Blocked at {url}. Continue after resolving the block, or pick another source."

        if screenshot:
            question = f"{question} (Screenshot: {screenshot})"

        options: List[Dict[str, Any]] = []
        if not getattr(self, "headless", True):
            options.append({"name": "Continue (I fixed it)", "action": "continue"})

        # Always offer fallback sources for autonomous runs (search engines / low-JS).
        query_text = (original_prompt or url or "").strip()
        try:
            query_text = re.sub(r"(?im)^\s*EVERSALE_AUTOFALLBACK_TRIED=.*$", "", query_text).strip()
            query_text = re.sub(r"(?im)^\s*use this source (?:first|only):.*$", "", query_text).strip()
            query_text = re.sub(r"(?im)^\s*continue from the current page.*$", "", query_text).strip()
        except Exception:
            pass
        q = quote_plus(query_text or url or "")
        options.extend(
            [
                {
                    "key": "duckduckgo_html",
                    "name": "Use DuckDuckGo (HTML) instead",
                    "url": "https://html.duckduckgo.com/html/?q=" + q,
                },
                {
                    "key": "bing_search",
                    "name": "Use Bing Search instead",
                    "url": "https://www.bing.com/search?q=" + q,
                },
                {
                    "key": "google_search",
                    "name": "Use Google Search instead",
                    "url": "https://www.google.com/search?q=" + q,
                },
            ]
        )

        return {
            "status": "needs_clarification",
            "result": "Needs clarification",
            "question": question,
            "options": options[:4],
            "url": url,
            "error": err or blocked.get("error") or "",
            "blocked": blocked,
        }

    def _is_autonomous_mode(self) -> bool:
        """
        True when we should not wait for stdin (headless/background).
        """
        try:
            return bool(getattr(self, "headless", True)) or (not sys.stdin.isatty())
        except Exception:
            return True

    def _extract_autofallback_metadata(self, prompt: str) -> Dict[str, Any]:
        """
        Extract metadata injected by autonomous clarification resolution so downstream automation
        can detect degraded/fallback mode.
        """
        meta: Dict[str, Any] = {}
        tried: List[str] = []
        source_url: str = ""
        source_policy: str = ""

        for raw in (prompt or "").splitlines():
            line = (raw or "").strip()
            if not line:
                continue
            lower = line.lower()

            if lower.startswith("eversale_autofallback_tried=") and not tried:
                _, rhs = line.split("=", 1)
                parts = [p.strip() for p in rhs.split(",") if p.strip()]
                seen = set()
                for p in parts:
                    key = p.lower()
                    if key in seen:
                        continue
                    seen.add(key)
                    tried.append(p)
                continue

            if not source_url and lower.startswith("use this source only:"):
                source_policy = "only"
                source_url = line.split(":", 1)[1].strip().strip('"').strip("'").rstrip(".,;")
                continue

            if not source_url and lower.startswith("use this source first:"):
                source_policy = "first"
                source_url = line.split(":", 1)[1].strip().strip('"').strip("'").rstrip(".,;")
                continue

        if tried:
            meta["tried"] = tried
        if source_url:
            meta["source_url"] = source_url
        if source_policy:
            meta["source_policy"] = source_policy

        return meta

    def _with_autofallback_metadata(self, prompt: str, result: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(result, dict):
            return result
        meta = self._extract_autofallback_metadata(prompt)
        if not meta:
            return result
        out = dict(result)
        existing = out.get("autofallback")
        merged: Dict[str, Any] = {}
        if isinstance(existing, dict):
            merged.update(existing)
        merged.update(meta)
        out["autofallback"] = merged
        out["autofallback_used"] = True
        return out

    def _coerce_needs_clarification_to_blocked(self, prompt: str, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        In autonomous mode, avoid returning needs_clarification (no human can answer).
        Convert to blocked with enough metadata for automation to decide next steps.
        """
        if not isinstance(result, dict) or str(result.get("status") or "").lower() != "needs_clarification":
            return result

        meta = self._extract_autofallback_metadata(prompt)
        tried = meta.get("tried") if isinstance(meta.get("tried"), list) else []
        exhausted = bool(tried)

        url = str(result.get("url") or "").strip()
        if not url and isinstance(result.get("blocked"), dict):
            url = str(result["blocked"].get("url") or "").strip()

        question = str(result.get("question") or "Needs clarification").strip()
        err = (
            f"Autonomous run requires clarification but no input is available ({url})."
            if url
            else "Autonomous run requires clarification but no input is available."
        )
        if exhausted:
            err = f"Autonomous fallback exhausted: {question}"

        out = dict(result)
        out.update(
            {
                "status": "blocked",
                "block_reason": "fallback_exhausted" if exhausted else "clarification_required",
                "needs_intervention": True,
                "fallback_exhausted": exhausted,
                "error": err,
                "result": err,
                "url": url,
            }
        )
        if meta:
            out["autofallback"] = meta
            out["autofallback_used"] = True
        return out

    async def _maybe_resolve_clarification(self, original_prompt: str, result: Dict[str, Any]) -> Optional[str]:
        """
        If the engine needs user clarification (ambiguous site choice), ask once in interactive mode.
        Returns a new prompt if resolved, or None to keep the original result.
        """
        if (result or {}).get("status") != "needs_clarification":
            return None

        question = str(result.get("question") or "Choose a source")
        options = result.get("options") or []
        if not isinstance(options, list) or not options:
            return None

        # Autonomous mode: do not block on stdin. Pick a reasonable default and proceed.
        # This is critical for headless/background runs.
        auto_mode = self._is_autonomous_mode()

        if auto_mode:
            tried_keys: List[str] = []
            try:
                m = re.search(r"EVERSALE_AUTOFALLBACK_TRIED=([^\n]+)", original_prompt or "", flags=re.IGNORECASE)
                if m and m.group(1):
                    parts = [p.strip().lower() for p in m.group(1).split(",") if p.strip()]
                    seen = set()
                    for p in parts:
                        if p in seen:
                            continue
                        seen.add(p)
                        tried_keys.append(p)
            except Exception:
                tried_keys = []

            tried_set = set(tried_keys)

            def _key(opt: Dict[str, Any]) -> str:
                return str(opt.get("key") or opt.get("action") or opt.get("name") or "").strip().lower()

            # Prefer low-friction sources first.
            preferred_order = [
                "duckduckgo_html",
                "duckduckgo",
                "bing_search",
                "bing",
                "google_search",
                "google",
                "guess_com",
                "explicit",
            ]

            chosen: Optional[Dict[str, Any]] = None
            for k in preferred_order:
                for opt in options:
                    if not isinstance(opt, dict):
                        continue
                    ok = _key(opt)
                    if ok != k or ok in tried_set:
                        continue
                    if str(opt.get("action") or "").strip().lower() == "continue":
                        continue
                    if opt.get("url"):
                        chosen = opt
                        break
                if chosen:
                    break

            if chosen is None:
                for opt in options:
                    if not isinstance(opt, dict):
                        continue
                    ok = _key(opt)
                    if ok in tried_set:
                        continue
                    if str(opt.get("action") or "").strip().lower() == "continue":
                        continue
                    if opt.get("url"):
                        chosen = opt
                        break

            if chosen and chosen.get("url"):
                chosen_url = str(chosen["url"]).strip()
                chosen_key = _key(chosen)
                new_tried: List[str] = list(tried_keys)
                if chosen_key and chosen_key not in tried_set:
                    new_tried.append(chosen_key)
                tried_line = f"EVERSALE_AUTOFALLBACK_TRIED={','.join(new_tried)}" if new_tried else ""
                # Force LLM workflow routing (see _parse_task override) and keep the source constraint explicit.
                return "\n".join(
                    [l for l in [
                        tried_line,
                        f"Use this source only: {chosen_url}",
                        "Do not visit other sites unless absolutely necessary; satisfy the request from this source.",
                        "",
                        original_prompt,
                    ] if l]
                )

            return None

        print()
        print(f"{Colors.YELLOW}{question}{Colors.RESET}")
        for i, opt in enumerate(options[:4], 1):
            if not isinstance(opt, dict):
                continue
            name = opt.get("name") or opt.get("key") or f"Option {i}"
            url = opt.get("url") or ""
            print(f"  [{i}] {name} - {url}")

        try:
            choice = input(f"{Colors.CYAN}Choose 1-{min(4, len(options))}:{Colors.RESET} ").strip()
        except Exception:
            return None

        if not choice:
            return None

        if choice.strip().lower() in ("c", "continue"):
            return f"Continue from the current page without navigating.\n\n{original_prompt}"

        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= min(4, len(options)):
                chosen = options[idx - 1]
                if isinstance(chosen, dict) and str(chosen.get("action") or "").strip().lower() == "continue":
                    return f"Continue from the current page without navigating.\n\n{original_prompt}"
                if isinstance(chosen, dict) and chosen.get("url"):
                    url = str(chosen["url"]).strip()
                    return f"{original_prompt}\n\nUse this source first: {url}"

        # Allow pasting a URL directly
        if choice.startswith("http"):
            return f"{original_prompt}\n\nUse this source first: {choice}"

        return None

    async def _run_single_with_retry(self, prompt: str, agi=None, cognitive=None, max_retries: int = 2) -> Dict:
        """
        Run single task with automatic AGI-powered retry on failure.

        Uses full cognitive architecture when available:
        1. Perceive current state
        2. Reason about best approach
        3. Execute with monitoring
        4. Verify outcome
        5. Learn from result

        Falls back to simpler AGI reasoning if cognitive engine unavailable.
        """
        last_error = None
        all_actions = []
        original_prompt = prompt
        autofallback_meta = self._extract_autofallback_metadata(original_prompt)

        def _attach_meta(res: Dict[str, Any]) -> Dict[str, Any]:
            if not isinstance(res, dict) or not autofallback_meta:
                return res
            out = dict(res)
            existing = out.get("autofallback")
            merged: Dict[str, Any] = {}
            if isinstance(existing, dict):
                merged.update(existing)
            merged.update(autofallback_meta)
            out["autofallback"] = merged
            out["autofallback_used"] = True
            return out

        start_time = time.time()
        max_seconds = self._get_time_budget_seconds(prompt)

        for attempt in range(max_retries + 1):
            if (time.time() - start_time) > max_seconds:
                last_error = f"Time budget exceeded ({max_seconds}s)"
                break
            # Lazy-init reasoning only after a failure (keeps the hot path simple + fast).
            if attempt > 0 and not cognitive and AGI_CORE_AVAILABLE and get_cognitive_engine:
                try:
                    cognitive = get_cognitive_engine()
                    # Historical success rate hint
                    try:
                        success_rate = get_historical_success_rate(original_prompt)
                        if success_rate < 0.5 and success_rate > 0:
                            print(f"{Colors.YELLOW}* Similar tasks succeeded {success_rate:.0%} - will adapt strategy{Colors.RESET}")
                    except Exception:
                        pass
                except Exception:
                    cognitive = None

            if attempt > 0 and not agi and not cognitive and AGI_REASONING_AVAILABLE and get_agi_reasoning:
                try:
                    agi = get_agi_reasoning()
                    intent = await agi.understand_intent(original_prompt, {
                        'url': self.page.url if self.page else '',
                    })
                    if intent and intent.get('actual_goal'):
                        print(f"{Colors.DIM}* Goal: {intent.get('actual_goal')[:50]}{Colors.RESET}")
                except Exception:
                    agi = None
            # Cognitive pre-check: detect loops and low-confidence situations
            if cognitive and attempt > 0:
                meta = await cognitive.metacognize()
                if meta.get("in_loop"):
                    print(f"{Colors.YELLOW}* Loop detected - forcing strategy change{Colors.RESET}")
                    # Get completely different approach
                    if self.page:
                        page_state = {"url": self.page.url, "text": ""}
                        try:
                            page_state["text"] = (await self.page.content())[:2000]
                        except:
                            pass
                        reasoning = await think_before_act(original_prompt, page_state)
                        if reasoning.get("strategy"):
                            prompt = f"Using fallback: {reasoning['strategy']}"
                            print(f"{Colors.CYAN}* New strategy: {prompt[:50]}...{Colors.RESET}")

            try:
                result = await self._run_single(prompt)

                # Hard blockers should ask the user instead of retry-looping.
                if isinstance(result, dict):
                    status = str(result.get("status") or "").lower()
                    if status == "blocked" or bool(result.get("needs_intervention")):
                        return _attach_meta(self._blocked_to_needs_clarification(original_prompt, result))

                # Check if result indicates success
                if result and result.get('status') != 'error':
                    # Record success for learning
                    if agi:
                        agi.record_action(prompt, result.get('result', ''), True)

                    # Cognitive learning: record successful episode
                    if cognitive:
                        all_actions.append({"action": prompt, "success": True})
                        await cognitive.learn(
                            original_prompt,
                            all_actions,
                            result.get('result', 'success'),
                            True
                        )
                        print(f"{Colors.DIM}* Learned: success pattern recorded{Colors.RESET}")

                    return _attach_meta(result)

                # Task returned but with error status
                last_error = result.get('error', 'Unknown error')
                all_actions.append({"action": prompt, "success": False, "error": last_error})

            except Exception as e:
                last_error = str(e)
                all_actions.append({"action": prompt, "success": False, "error": last_error})

            # If we have AGI and more retries, get smart correction
            if (agi or cognitive) and attempt < max_retries:
                print(f"{Colors.YELLOW}* Analyzing failure (attempt {attempt + 1}/{max_retries + 1})...{Colors.RESET}")

                # Try cognitive reasoning first (has memory of what worked before)
                if cognitive:
                    try:
                        page_state = {"url": self.page.url if self.page else "", "text": ""}
                        perception = await cognitive.perceive(page_state)
                        reasoning = await cognitive.reason(original_prompt, perception)

                        if reasoning.get("action") == "use_fallback":
                            new_approach = reasoning.get("strategy", "")
                            if new_approach:
                                print(f"{Colors.CYAN}* Cognitive fallback: {new_approach[:50]}...{Colors.RESET}")
                                prompt = new_approach
                                await asyncio.sleep(1)
                                continue
                    except Exception as e:
                        logger.debug(f"Cognitive reasoning failed: {e}")

                # Fall back to simpler AGI reasoning
                if agi:
                    try:
                        correction = await agi.get_correction(
                            action=prompt,
                            error=last_error,
                            current_state={'url': self.page.url if self.page else '', 'attempt': attempt + 1}
                        )

                        if correction and correction.get('new_action'):
                            new_approach = correction.get('new_action')
                            print(f"{Colors.CYAN}* Correction: {new_approach[:50]}...{Colors.RESET}")
                            prompt = new_approach
                        elif correction and not correction.get('should_retry', True):
                            break
                    except Exception:
                        pass

                await asyncio.sleep(1)

        # All retries exhausted - record failure for learning
        if agi:
            agi.record_action(prompt, last_error, False)

        if cognitive:
            await cognitive.learn(original_prompt, all_actions, f"Failed: {last_error}", False)
            print(f"{Colors.DIM}* Learned: failure pattern recorded for future avoidance{Colors.RESET}")

        return _attach_meta({"status": "error", "error": last_error, "result": f"Failed after {max_retries + 1} attempts: {last_error}"})

    def _get_time_budget_seconds(self, prompt: str) -> int:
        """
        Per-task time budget (simple governor).

        Defaults:
        - 180s for general browser tasks
        - 240s for multi-step/lead tasks
        - 90s if user asks "quick/fast"
        - Up to 3600s (60 minutes) for explicit time requests
        """
        p = (prompt or "").lower()

        if any(w in p for w in ("quick", "fast", "asap")):
            return 90

        # Check for explicit time budgets: "up to X minutes", "scroll for X minutes", "max X minutes"
        time_match = re.search(
            r'\b(?:up\s+to|scroll\s+(?:for\s+)?(?:up\s+to\s+)?|max(?:imum)?|spend\s+(?:up\s+to\s+)?|for\s+up\s+to)\s*(\d{1,3})\s*(?:minutes?|mins?)\b',
            p
        )
        if time_match:
            try:
                minutes = int(time_match.group(1))
                # Allow up to 120 minutes (2 hours), cap at 7200 seconds
                return min(minutes * 60, 7200)
            except ValueError:
                pass

        # Check for hour-based requests
        hour_match = re.search(r'\b(?:up\s+to|for|max)\s*(\d{1,2})\s*(?:hours?|hrs?)\b', p)
        if hour_match:
            try:
                hours = int(hour_match.group(1))
                return min(hours * 3600, 7200)
            except ValueError:
                pass

        from .platform_data import PLATFORM_INDICATORS
        for data in PLATFORM_INDICATORS.values():
            if any(k in p for k in data["keywords"]):
                return 240

        # If the user explicitly asked for many results, allow a bit more.
        requested_count = self._extract_requested_count(prompt) or 0
        if requested_count >= 100:
            return 1800  # 30 minutes for 100+ items
        if requested_count >= 50:
            return 900   # 15 minutes for 50+ items
        if requested_count >= 10:
            return 300   # 5 minutes for 10+ items

        return 180



    async def _execute_workflow(self, workflow_name: str, params: Dict, prompt: str, requested_count: Optional[int], wants_many: bool) -> Dict:
        """Site-agnostic workflow executor."""
        # Mapping names to our refactored hint-driven methods
        # These methods are internal logic containers, the engine code inside them is generic.
        workflow_map = {
            "fb_ads": lambda: self.workflow_fb_ads_many(
                params.get("query", "booked meetings"),
                max_leads=requested_count or (50 if wants_many else 5),
                prompt=prompt,
            ),
            "reddit": lambda: self.workflow_reddit(params.get("topic", "lead generation"), 
                                                 max_leads=requested_count or (20 if wants_many else 5), 
                                                 prompt=params.get("prompt", prompt)),
            "linkedin": lambda: self.workflow_linkedin_search(
                params.get("query", "sales"),
                max_leads=requested_count or 10,
                prompt=prompt,
            ),
            "linkedin_warm": lambda: self.workflow_linkedin_warm_leads(params.get("prompt", prompt), 
                                                                     max_leads=requested_count or 10),
            "google_maps": lambda: self.workflow_google_maps(
                params.get("query", ""),
                max_leads=requested_count or 20,
                prompt=prompt,
            )
        }
        
        if workflow_name in workflow_map:
            result = await workflow_map[workflow_name]()

            # Skip LLM fallback for workflows that already have their own fallback mechanisms.
            # LinkedIn has Google fallback, Google Maps is deterministic - don't enter verbose LLM loop.
            # This prevents excessive snapshot printing and keeps output clean.
            skip_llm_fallback = workflow_name in ("linkedin", "google_maps")

            if not skip_llm_fallback:
                # If the deterministic workflow couldn't complete, fall back to the general LLM loop.
                # This keeps "works no matter what" behavior closer to Playwright MCP when sites change.
                try:
                    status = (result.get("status") or "").lower() if isinstance(result, dict) else ""
                    if status in ("no_results", "failed", "error") and (prompt or "").strip():
                        llm_result = await self._run_with_llm(prompt)
                        if isinstance(llm_result, dict) and llm_result.get("status") == "complete":
                            return llm_result
                        if isinstance(result, dict) and isinstance(llm_result, dict):
                            result["llm_fallback_status"] = llm_result.get("status")
                except Exception:
                    pass

            # Post-processing: limit results if requested
            if result and requested_count and result.get("data") and isinstance(result["data"], list):
                result["data"] = result["data"][:requested_count]
                result["leads"] = result.get("leads", [])[:requested_count]
            return result
            
        return await self._run_with_llm(prompt)

    async def _run_single(self, prompt: str) -> Dict:
        """Run single task."""
        # 1. Try Strategic Planning for complex tasks
        if getattr(self, "strategic_planner", None):
            # Get available tools
            available_tools = [
                "navigate", "click", "type", "scroll", "tabs_new", 
                "tabs_select", "tabs_close", "extract", "done"
            ]
            try:
                state = await self.strategic_planner.plan(prompt, available_tools)
                if state:
                    logger.info(f"Complex task detected, using strategic plan: {state.current_plan.summary}")
                    # Execute the plan
                    results = []
                    while not state.is_overall_task_complete:
                        action_info = await self.strategic_planner.get_next_action(state)
                        if not action_info: break
                        
                        # Translate strategic action to browser action
                        # (Simple version for now, could be more elaborate)
                        action_name = action_info['tool']
                        if action_name.startswith('playwright_'):
                            action_name = action_name.replace('playwright_', '')
                        
                        # ... execution logic ...
                        # For now, we'll fall through to existing logic if planning fails
                        # but this is where we'd put the plan execution loop.
            except Exception as e:
                logger.debug(f"Strategic planning failed or skipped: {e}")

        task = self._parse_task(prompt)
        workflow = task.get("workflow")
        requested_count = task.get("count")
        wants_many = "as many" in (prompt or "").lower() or ("spend max" in (prompt or "").lower() and "minute" in (prompt or "").lower()) or ("max " in (prompt or "").lower() and "minute" in (prompt or "").lower())

        # Even in direct_mode (Playwright MCP-style), prefer deterministic workflows for known tasks.
        # This improves speed + reliability, and keeps LLM in the loop only when needed.
        if self.direct_mode and workflow not in ("llm", "navigate"):
            return await self._execute_workflow(workflow, task, prompt, requested_count, wants_many)

        # Auto-route vague social lead prompts
        if workflow == "llm" and self._looks_like_social_lead_prompt((prompt or "").lower()):
            decision = await self._classify_social_lead_workflow(prompt)
            workflow = decision.get("workflow")
            task.update(decision)

        if workflow == "navigate":
            url = task["url"]
            if not url.startswith("http"):
                url = "https://" + url
            from .platform_data import COMMON_TLDS
            if "." not in url:
                url = url + COMMON_TLDS[0]
            self.step = 1
            details = f"await page.goto('{url}');"
            print_step(1, "navigate", url, "running", details=details)
            nav_result = await self.navigate(url)
            # For navigation-only tasks, we still return the final URL even if the page is a login wall
            # or bot/geo block (no-human runs frequently hit these).
            if isinstance(nav_result, dict) and nav_result.get("status") == "blocked":
                pass

            prompt_lower = (prompt or "").lower()
            wants_current_url = (
                bool(re.search(r"\b(?:final|current|resulting)\s+url\b", prompt_lower))
                or ("url reached" in prompt_lower)
            )
            wants_page_title = (
                ("page title" in prompt_lower)
                or ("what is the title" in prompt_lower and "of the" not in prompt_lower)
                or ("the title" in prompt_lower and "of the" not in prompt_lower)
            )
            urls_only = (
                ("output only" in prompt_lower and ("url" in prompt_lower or "urls" in prompt_lower))
                or ("urls only" in prompt_lower)
                or ("no explanations" in prompt_lower)
                or ("no explanation" in prompt_lower)
                or (bool(re.search(r"\boutput\s+(?:exactly\s+)?(?:1|one)\b", prompt_lower)) and ("url" in prompt_lower or "urls" in prompt_lower))
            )

            final_url = self.page.url if self.page else ""
            if wants_page_title:
                try:
                    title = await self.page.title() if self.page else ""
                except Exception:
                    title = ""
                if urls_only:
                    return {"status": "complete", "result": title, "steps": 1, "url": final_url}
                return {"status": "complete", "result": f"Page title: {title}", "steps": 1, "url": final_url}
            if wants_current_url or urls_only:
                return {"status": "complete", "result": final_url, "steps": 1, "url": final_url}

            print(await self.get_snapshot())
            return {"status": "complete", "result": f"URL: {final_url}", "steps": 1, "url": final_url}

        return await self._execute_workflow(workflow, task, prompt, requested_count, wants_many)

    async def _try_extract_hackernews_top(self, prompt: str) -> Optional[str]:
        """Deterministically extract top N items from an HN-style front page (tr.athing rows)."""
        if not self.page:
            return None

        prompt_lower = (prompt or "").lower()
        wants_top = any(k in prompt_lower for k in ("top", "front page", "frontpage", "first"))
        if not wants_top:
            return None

        limit = self._extract_requested_count(prompt) or 3
        limit = max(1, min(int(limit), 30))

        try:
            items = await self.page.evaluate(
                r"""(n) => {
  const base = new URL('/', window.location.href).href;
  const rows = Array.from(document.querySelectorAll('tr.athing'));
  const out = [];

  for (const row of rows.slice(0, n)) {
    const linkEl = row.querySelector('.titleline > a');
    const title = linkEl && linkEl.textContent ? linkEl.textContent.trim() : '';
    let href = linkEl && linkEl.getAttribute ? (linkEl.getAttribute('href') || '') : '';

    if (href && !href.startsWith('http://') && !href.startsWith('https://')) {
      try { href = new URL(href, base).href; } catch (e) {}
    }

    const subtextRow = row.nextElementSibling;
    const subtext = subtextRow ? subtextRow.querySelector('.subtext') : null;
    const scoreEl = subtext ? subtext.querySelector('.score') : null;
    const points = scoreEl && scoreEl.textContent ? scoreEl.textContent.trim() : '';

    let comments = '';
    if (subtext) {
      const links = Array.from(subtext.querySelectorAll('a'));
      const c = links.find(a => /\bcomment\b|\bdiscuss\b/i.test(a.textContent || ''));
      comments = c && c.textContent ? c.textContent.trim() : '';
    }

    out.push({ title, link: href, points, comments });
  }

  return out;
}""",
                limit,
            )
        except Exception:
            return None

        if not isinstance(items, list) or not items:
            return None

        lines: List[str] = []
        for idx, item in enumerate(items[:limit], start=1):
            if not isinstance(item, dict):
                continue
            title = (item.get("title") or "").strip()
            link = (item.get("link") or "").strip()
            points = (item.get("points") or "").strip()
            comments = (item.get("comments") or "").strip()
            if not title:
                continue

            meta_parts = [p for p in (points, comments) if p]
            meta = f" ({', '.join(meta_parts)})" if meta_parts else ""
            link_part = f" - {link}" if link else ""
            lines.append(f"{idx}. {title}{meta}{link_part}")

        return "\n".join(lines) if lines else None

    async def _try_extract_structured_links(self, prompt: str) -> Optional[Dict[str, Any]]:
        """
        Deterministically extract link-style outputs from known structured pages
        (e.g., search results) using `utils.site_selectors`.
        """
        if not self.page:
            return None

        current_url = str(getattr(self.page, "url", "") or "").strip()
        if not current_url or current_url == "about:blank":
            return None

        prompt_lower = (prompt or "").lower()
        if not re.search(r"\b(?:url|urls|link|links)\b", prompt_lower):
            return None

        # Navigation-only URL requests are handled separately.
        if re.search(r"\b(?:final|current|resulting)\s+url\b", prompt_lower) or ("url reached" in prompt_lower):
            return None

        requested = self._extract_requested_count(prompt) or 0
        limit = max(1, min(10, requested or 5))

        try:
            from .utils.site_selectors import get_site_selectors
            site_cfg = get_site_selectors(current_url)
        except Exception:
            site_cfg = None

        if not isinstance(site_cfg, dict):
            return None

        item_selector = str(site_cfg.get("item_selector") or "").strip()
        field_selectors = site_cfg.get("field_selectors") or {}
        if not item_selector or not isinstance(field_selectors, dict):
            return None

        link_field = None
        for k in ("url", "link", "website"):
            if k in field_selectors:
                link_field = k
                break
        if not link_field:
            return None

        # Generic path-fragment filter (avoids domain literals).
        path_filter = None
        if "/in/" in prompt_lower:
            path_filter = "/in/"
        elif "/maps/place/" in prompt_lower:
            path_filter = "/maps/place/"
        elif "/user/" in prompt_lower:
            path_filter = "/user/"

        try:
            items = await self.page.evaluate(
                """(args) => {
  const itemSelector = args.itemSelector;
  const fieldSelectors = args.fieldSelectors || {};
  const limit = args.limit || 5;
  const out = [];

  const parseSelector = (s) => {
    const raw = (s || '').trim();
    const at = raw.lastIndexOf('@');
    if (at > 0 && at < raw.length - 1) {
      return { sel: raw.slice(0, at).trim(), attr: raw.slice(at + 1).trim() };
    }
    return { sel: raw, attr: null };
  };

  const getValue = (root, selectorRaw) => {
    if (!selectorRaw) return '';
    const parts = selectorRaw.split(',').map(s => s.trim()).filter(Boolean);
    for (const part of parts) {
      const { sel, attr } = parseSelector(part);
      if (!sel) continue;
      const el = root.querySelector(sel);
      if (!el) continue;
      if (attr) {
        const v = el.getAttribute(attr) || '';
        if (v) return v;
      } else {
        const v = (el.innerText || el.textContent || '').trim();
        if (v) return v;
      }
    }
    return '';
  };

  const absUrl = (href) => {
    const h = (href || '').trim();
    if (!h) return '';
    if (h.startsWith('http://') || h.startsWith('https://')) return h;
    try { return new URL(h, window.location.href).href; } catch (e) { return h; }
  };

  const nodes = Array.from(document.querySelectorAll(itemSelector)).slice(0, limit * 4);
  for (const node of nodes) {
    const obj = {};
    for (const [field, selRaw] of Object.entries(fieldSelectors)) {
      const v = getValue(node, selRaw);
      if (!v) continue;
      obj[field] = (field === 'link' || field === 'url' || field === 'website') ? absUrl(v) : v;
    }
    if (Object.keys(obj).length) out.push(obj);
    if (out.length >= limit) break;
  }
  return out;
}""",
                {"itemSelector": item_selector, "fieldSelectors": field_selectors, "limit": limit},
            )
        except Exception:
            return None

        if not isinstance(items, list) or not items:
            return None

        urls: List[str] = []
        rows: List[Dict[str, Any]] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            u = str(it.get(link_field) or "").strip()
            if not u:
                continue
            if path_filter and path_filter not in u:
                continue
            urls.append(u)
            rows.append(it)
            if len(urls) >= limit:
                break

        if requested > 0:
            urls = urls[:requested]
            rows = rows[:requested]

        if not urls:
            return None

        urls_only = (
            ("urls only" in prompt_lower)
            or ("output only" in prompt_lower and ("url" in prompt_lower or "urls" in prompt_lower))
            or ("no explanations" in prompt_lower)
            or ("no explanation" in prompt_lower)
        )
        if urls_only or requested > 0:
            result_text = "\n".join(urls).strip()
        else:
            lines: List[str] = []
            for idx, row in enumerate(rows, start=1):
                title = str(row.get("title") or row.get("business_name") or "").strip()
                url_out = urls[idx - 1]
                if title:
                    lines.append(f"{idx}. {title} - {url_out}")
                else:
                    lines.append(f"{idx}. {url_out}")
            result_text = "\n".join(lines).strip()

        return {
            "status": "complete",
            "result": result_text,
            "urls": urls,
            "url": current_url,
        }

    async def _run_with_llm(self, prompt: str) -> Dict:
        """Optimized LLM-driven browser automation."""
        import hashlib

        # Show progress for general tasks
        task_preview = prompt[:50].replace('\n', ' ').strip()
        print(f"{Colors.CYAN}  * Task: {task_preview}...{Colors.RESET}")

        # OPTIMIZATION 1: Use dynamic max steps (default 8, but configurable via self.max_steps)
        max_steps = getattr(self, "max_steps", 8)
        history: List[Dict[str, str]] = []
        no_progress_streak = 0
        start_time = time.time()
        max_seconds = self._get_time_budget_seconds(prompt)
        compiled = compile_prompt(prompt)
        exact_lines = should_enforce_exact_lines(compiled.get("output_contract") or {})
        source_suggestion = suggest_sources(prompt)
        compiled["site_routing"] = source_suggestion

        # If the task is ambiguous and needs a human choice, bubble it up.
        if source_suggestion.get("status") == "needs_clarification":
            return {
                "status": "needs_clarification",
                "result": "Needs clarification",
                "question": source_suggestion.get("question", "Choose a source"),
                "options": source_suggestion.get("options", []),
                "intent": source_suggestion.get("intent", ""),
            }

        # OPTIMIZATION 4: Early exit - extract answer from prompt keywords
        prompt_lower = prompt.lower()
        # Only early exit for PAGE title, not "title of the top story" etc.
        wants_page_title = ("page title" in prompt_lower or
                            "the title" in prompt_lower and "of the" not in prompt_lower or
                            "what is the title" in prompt_lower and "of the" not in prompt_lower)
        # Only early-exit for the *current/final* URL (navigation-only tasks).
        # Do NOT early-exit for tasks where a URL is the *target data* (e.g. "profile URL", "ad URL").
        # Also avoid if specific counts or extraction keywords are present.
        wants_current_url = (
            bool(re.search(r"\b(?:final|current|resulting)\s+url\b", prompt_lower))
            or ("url reached" in prompt_lower)
        ) and not any(
            kw in prompt_lower
            for kw in (
                # These indicate the URL is the *data being extracted*, not the current/final URL.
                "advertiser",
                "ad url",
                "profile url",
                "user profile",
                "listing url",
                "google result url",
                "extract",
            )
        )

        # OPTIMIZATION 5: Direct URL extraction for "Go to X" patterns
        start_url = source_suggestion.get("start_url") if isinstance(source_suggestion, dict) else None
        if not start_url:
            # First try to extract explicit URLs like https://example.com
            url_match = re.search(r'https?://[^\s\'"]+', prompt)
            if url_match:
                start_url = url_match.group().rstrip('.,;:')
            else:
                # Fall back to site name extraction from "go to X" patterns
                go_to_match = re.search(r'go\s+to\s+([a-zA-Z0-9.-]+)', prompt_lower)
                if go_to_match:
                    site_name = go_to_match.group(1)
                    from .platform_data import SITE_NAME_TO_URL
                    start_url = SITE_NAME_TO_URL.get(site_name)
                    if not start_url and '.' in site_name:
                        start_url = f"https://{site_name}"
                    elif not start_url:
                        start_url = f"https://{site_name}.com"

        # If we have a start URL and the prompt is explicitly navigational, navigate up front.
        # Multi-task runs should not "stick" to the prior task's page.
        try:
            if start_url and self.page:
                current_url = (self.page.url or "").strip()

                def _origin(u: str) -> str:
                    try:
                        from urllib.parse import urlparse
                        p = urlparse(u)
                        scheme = (p.scheme or "").lower()
                        netloc = (p.netloc or "").lower()
                        if not scheme or not netloc:
                            return ""
                        return f"{scheme}://{netloc}"
                    except Exception:
                        return ""

                explicit_nav = bool(re.search(r"^\s*(?:go\s+to|open|visit|navigate(?:\s+to)?)\b", prompt_lower))
                target_origin = _origin(str(start_url))
                current_origin = _origin(current_url)

                already_on_target = False
                if current_url and target_origin:
                    already_on_target = current_origin == target_origin and current_url.startswith(str(start_url))

                needs_nav = (current_url in ("about:blank", "")) or (explicit_nav and not already_on_target)

                if needs_nav:
                    self.step = 1
                    details = f"await page.goto('{start_url}');"
                    print_step(self.step, "navigate", f"{start_url}", "running", details=details)
                    nav_result = await self.navigate(str(start_url))
                    if isinstance(nav_result, dict) and nav_result.get("status") == "blocked":
                        return self._blocked_to_needs_clarification(prompt, nav_result)
                    print(await self.get_snapshot())

                # OPTIMIZATION 4: Early exit after navigation if task is simple
                if wants_page_title or wants_current_url:
                    await asyncio.sleep(0.5)
                    page_title = await self.page.title() if self.page else ""
                    page_url = self.page.url if self.page else ""
                    if wants_page_title and page_title:
                        print_step(2, "done", page_title, "success")
                        print(f"  {Colors.DIM}  ### Result{Colors.RESET}")
                        print(f"    Page title: {page_title}")
                        return {"status": "complete", "result": f"Page title: {page_title}", "steps": 2, "url": page_url}
                    if wants_current_url and page_url:
                        print_step(2, "done", page_url, "success")
                        print(f"  {Colors.DIM}  ### Result{Colors.RESET}")
                        print(f"    URL: {page_url}")
                        return {"status": "complete", "result": f"URL: {page_url}", "steps": 2, "url": page_url}
        except Exception:
            pass

        # Deterministic fast paths (critical for non-human runs): extract answers from known
        # structured layouts without entering the LLM action loop.
        try:
            hn_answer = await self._try_extract_hackernews_top(prompt)
            if hn_answer:
                step_base = getattr(self, "step", 0) or 0
                print_step(step_base + 1, "extract", "reading page content", "running")
                print_step(step_base + 2, "done", hn_answer, "success")
                print(f"  {Colors.DIM}ƒZ¨ ### Result{Colors.RESET}")
                print(f"    {hn_answer}")
                return {
                    "status": "complete",
                    "result": hn_answer,
                    "steps": step_base + 2,
                    "url": self.page.url if self.page else "",
                }
        except Exception:
            pass

        try:
            structured = await self._try_extract_structured_links(prompt)
            if structured:
                step_base = getattr(self, "step", 0) or 0
                structured["steps"] = step_base + 1
                return structured
        except Exception:
            pass

        # OPTIMIZATION 6: [DISABLED FOR BENCHMARKS]
        # Fast path for extraction-only tasks on standard content sites.
        # if not needs_action and not self.is_spa and len(snapshot_refs) > 5 and any(kw in p.lower() for kw in ["find", "extract", "get", "list", "search"]):
        #     rprint("[dim][OPTIMIZATION] Using fast extraction path...[/dim]")
        #     ...
        # if is_extraction_task and not needs_action and self.page and self.page.url != "about:blank":
        #     try:
        #         # Prefer deterministic DOM extraction for known layouts (faster + less hallucination).
        #         hn_answer = await self._try_extract_hackernews_top(prompt)
        #         if hn_answer:
        #             print_step(self.step + 1, "extract", "reading page content", "running")
        #             print_step(self.step + 2, "done", hn_answer, "success")
        #             print(f"  {Colors.DIM}⎿ ### Result{Colors.RESET}")
        #             print(f"    {hn_answer}")
        #             return {
        #                 "status": "complete",
        #                 "result": hn_answer,
        #                 "steps": self.step + 2,
        #                 "url": self.page.url if self.page else "",
        #             }

        #         requested_count = self._extract_requested_count(prompt)
        #         snapshot = await self.get_snapshot()
        #         snapshot_short = snapshot[:3000] if len(snapshot) > 3000 else snapshot

        #         list_constraint = ""
        #         if requested_count and any(k in prompt_lower for k in ("top", "first", "best", "list")):
        #             list_constraint = (
        #                 f"- If the user asks for {requested_count} items (e.g., top {requested_count}), "
        #                 f"output a numbered list with {requested_count} items (or fewer if fewer are visible) "
        #                 "and nothing else.\n"
        #             )

        #         # Simple QA prompt that works well with the model
        #         qa_prompt = f"""You are answering strictly from the page content below.
        # Rules:
        # - Do not speculate. If the answer isn't visible, reply exactly: Not found on this page.
        # {list_constraint}- Keep it short (<= 8 lines). No preamble.

        # PAGE:
        # {snapshot_short}

        # QUESTION:
        # {prompt}

        # ANSWER:"""

        #         # 1. Output MCP style thinking
        #         print_step(self.step + 1, "extract", "reading page content", "running")
        #         print(f"  {Colors.DIM}⎿ ### Ran Playwright code{Colors.RESET}")
        #         print(f"    // Reading AXTree and page text for QA")
                
        #         llm_response = await self.gpu_client.chat(
        #             model=GPU_MODELS['fast'],
        #             messages=[{"role": "user", "content": qa_prompt}],
        #             temperature=0.0,
        #             max_tokens=160
        #         )
                
        #         result_text = llm_response.content.strip()
        #         result_text = re.sub(r'<think>.*?</think>', '', result_text, flags=re.DOTALL).strip()
                
        #         if result_text:
        #             print_step(self.step + 2, "done", result_text, "success")
        #             print(f"  {Colors.DIM}⎿ ### Result{Colors.RESET}")
        #             print(f"    {result_text}")
        #             return {
        #                 "status": "complete",
        #                 "result": result_text,
        #                 "steps": self.step + 2,
        #                 "url": self.page.url if self.page else ""
        #             }
        #     except Exception as e:
        #         if self.debug:
        #             print(f"DEBUG: Fast extraction failed: {e}")
        #         # Fall through to action loop
        #         pass

        for step in range(1, max_steps + 1):
            if (time.time() - start_time) > max_seconds:
                return {"status": "timeout", "steps": step - 1, "url": self.page.url if self.page else "", "error": f"Time budget exceeded ({max_seconds}s)"}

            # OPTIMIZATION 6: [DISABLED FOR BENCHMARKS]
            # Fast path for extraction-only tasks on standard content sites.
            # if not needs_action and not self.is_spa and len(snapshot_refs) > 5 and any(kw in p.lower() for kw in ["find", "extract", "get", "list", "search"]):
            #     rprint("[dim][OPTIMIZATION] Using fast extraction path...[/dim]")
            #     ...
            
            # EARLY TERMINATION [RELAXED FOR BENCHMARKS]
            # if no_progress_streak >= 10 and self.page and self.page.url and self.page.url != "about:blank":
            #     rprint("[yellow]! Terminating due to no progress streak...[/yellow]")
            #     break
            # OPTIMIZATION 4: Early exit on no progress (only after we've navigated somewhere)
            # if no_progress_streak >= 3 and self.page and self.page.url and self.page.url != "about:blank":
            #     try:
            #         page_title = await self.page.title() if self.page else ""
            #         page_url = self.page.url if self.page else ""
            #         if page_title:
            #             return {"status": "complete", "result": f"Page: {page_title} at {page_url}", "steps": step, "url": page_url}
            #     except Exception:
            #         pass

            self.step = step
            snapshot = await self.get_snapshot()
            before_url = self.page.url if self.page else ""
            before_sig = hashlib.sha1((before_url + "\n" + snapshot[:1200]).encode("utf-8", errors="ignore")).hexdigest()

            # COMPACT SYSTEM PROMPT (Token Optimized)
            system = """JSON ONLY. No talk.
Actions: 
- navigate(url)
- click(ref) or click(x,y)
- type(ref,text) or type(x,y,text)
- scroll(direction)
- tabs_new(url), tabs_select(index), tabs_close()
- save_session(path)
- done(result)

Example: {"action":"click","ref":"e1"}
When using done(result), output the final answer only (no meta commentary) and keep it concise.
If the user asked for "top N", return numbered lines 1..N and include URLs when available.
Use refs from page state. "done" when task complete."""

            recent = history[-3:]  # OPTIMIZATION 2: Less history = fewer tokens
            history_pruner = getattr(self, "history_pruner", None)
            if history_pruner:
                recent = history_pruner.prune(recent)
            
            # OPTIMIZATION 2: Smaller snapshot (2000 chars is enough for most tasks)
            snapshot_for_llm = snapshot[:2000] if len(snapshot) > 2000 else snapshot
            user_msg = f"Task:{prompt}\nURL:{before_url}\nPage:\n{snapshot_for_llm}\nAction:"

            try:
                llm_response = await self.gpu_client.chat(
                    model=GPU_MODELS['fast'],  # OPTIMIZATION 3: Use fast model
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_msg}
                    ],
                    temperature=0.0,  # OPTIMIZATION: Deterministic for speed
                    max_tokens=150    # OPTIMIZATION 2: Reduced from 1000 (only need small JSON)
                )

                content = llm_response.content
                response = content.strip()
                response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL).strip()
                print(f"  {Colors.DIM}  ### LLM Response: {response[:200]}{Colors.RESET}")

                # Parse JSON - expect single action
                try:
                    # Try to find JSON block first
                    json_match = re.search(r'\{.*\}', response, re.DOTALL)
                    if json_match:
                        action_obj = json.loads(json_match.group(0))
                    else:
                        action_obj = {}
                except Exception:
                    action_obj = {}

                if not isinstance(action_obj, dict) or "action" not in action_obj:
                    # HEURISTIC FALLBACK: Extract actions from natural language
                    response_lower = response.lower()
                    if "done" in response_lower:
                        # Extract result: "done(result='...')" or "done: ..."
                        res_match = re.search(r"done\s*(?:\(|:)\s*(?:result\s*=\s*)?['\"]?([^'\")]+)['\"]?", response, re.IGNORECASE)
                        action_obj = {"action": "done", "result": res_match.group(1) if res_match else response[:200]}
                    elif "navigate" in response_lower or "go to" in response_lower:
                        url_match = re.search(r'https?://[^\s\'"]+', response)
                        if url_match:
                            action_obj = {"action": "navigate", "url": url_match.group().rstrip('.,;:')}
                    elif "click" in response_lower:
                        ref_match = re.search(r'\b(e\d+)\b', response)
                        if ref_match:
                            action_obj = {"action": "click", "ref": ref_match.group(1)}
                    
                    if not action_obj.get("action"):
                        # Try native UI-Tars parsing
                        native_action = self._parse_native_action(response)
                        if native_action:
                            action_obj = native_action
                        else:
                            if self.debug:
                                print(f"  {Colors.RED}Failed to parse: {response[:100]}{Colors.RESET}")
                            no_progress_streak += 1
                            continue

                action = str(action_obj.get("action", "")).strip().lower()
                if self.debug:
                    print(f"DEBUG: Parsed action: {action} Params: {str(action_obj)[:100]}")

                if not action:
                    continue

                # Execute action using refs (Playwright MCP style - full action set)
                action_desc = ""

                        # === NAVIGATION ===
                if action == "navigate":
                    url = action_obj.get("url", "")
                    details = f"await page.goto('{url}');"
                    print_step(step, action, url, "running", details=details)
                    nav_result = await self.navigate(url)
                    if isinstance(nav_result, dict) and nav_result.get("status") == "blocked":
                        return self._blocked_to_needs_clarification(prompt, nav_result)
                    print(await self.get_snapshot())

                elif action == "navigate_back":
                    details = "await page.goBack();"
                    print_step(step, action, "back", "running", details=details)
                    await self.navigate_back()
                    print(await self.get_snapshot())

                # === INTERACTION ===
                elif action == "click":
                    ref = action_obj.get("ref", "")
                    x, y = action_obj.get("x"), action_obj.get("y")
                    if x is not None and y is not None:
                        details = f"await page.mouse.click({x}, {y}); // scaled"
                        print_step(step, action, f"({x}, {y})", "running", details=details)
                        await self.click_coords(x, y)
                    else:
                        text = action_obj.get("text", ref)
                        selector = self.element_refs.get(ref, {}).get('selector', f"text='{text}'")
                        details = f"await page.locator('{selector}').click();"
                        print_step(step, action, f"[{ref}]", "running", details=details)
                        click_result = await self.click(ref=ref or None, text=text or None)
                        if isinstance(click_result, dict) and click_result.get("status") == "blocked":
                            return self._blocked_to_needs_clarification(prompt, click_result)
                    print(await self.get_snapshot())

                elif action == "type":
                    ref = action_obj.get("ref", "")
                    text = action_obj.get("text", "")
                    x, y = action_obj.get("x"), action_obj.get("y")
                    if x is not None and y is not None:
                        details = f"await page.mouse.click({x}, {y}); await page.keyboard.type('{text}');"
                        print_step(step, action, f"({x}, {y}) = {text[:20]}", "running", details=details)
                        await self.type_coords(text, x, y)
                    else:
                        selector = self.element_refs.get(ref, {}).get('selector', 'input')
                        details = f"await page.locator('{selector}').fill('{text}');"
                        print_step(step, action, f"[{ref}] = {text[:20]}", "running", details=details)
                        if ref and ref in self.element_refs:
                            type_result = await self.type(text, ref=ref)
                            if isinstance(type_result, dict) and type_result.get("status") == "blocked":
                                return self._blocked_to_needs_clarification(prompt, type_result)
                        else:
                            placeholder = action_obj.get("placeholder", ref)
                            type_result = await self.type_placeholder(placeholder, text)
                            if isinstance(type_result, dict) and type_result.get("status") == "blocked":
                                return self._blocked_to_needs_clarification(prompt, type_result)
                    print(await self.get_snapshot())

                elif action == "hover":
                    ref = action_obj.get("ref", "")
                    action_desc = f"hover [{ref}]"
                    print_step(step, action, f"[{ref}]", "running")
                    await self.hover(ref=ref)

                elif action == "drag":
                    x1, y1 = action_obj.get("x1"), action_obj.get("y1")
                    x2, y2 = action_obj.get("x2"), action_obj.get("y2")
                    if x1 is not None and y1 is not None and x2 is not None and y2 is not None:
                        details = f"await page.mouse.move({x1}, {y1}); await page.mouse.down(); await page.mouse.move({x2}, {y2}); await page.mouse.up();"
                        print_step(step, action, f"({x1},{y1})->({x2},{y2})", "running", details=details)
                        await self.drag_coords(x1, y1, x2, y2)
                    else:
                        start_ref = action_obj.get("startRef", "")
                        end_ref = action_obj.get("endRef", "")
                        action_desc = f"drag [{start_ref}] to [{end_ref}]"
                        print_step(step, action, f"[{start_ref}]->[{end_ref}]", "running")
                        await self.drag(start_ref=start_ref, end_ref=end_ref)

                elif action == "select":
                    ref = action_obj.get("ref", "")
                    value = action_obj.get("value", "")
                    action_desc = f"select [{ref}]: {value[:20]}"
                    print_step(step, action, f"[{ref}] = {value[:20]}", "running")
                    if ref and ref in self.element_refs:
                        selector = self.element_refs[ref]['selector']
                        await self.select_option(selector, value)

                # === KEYBOARD ===
                elif action == "press":
                    key = action_obj.get("key", "Enter")
                    details = f"await page.keyboard.press('{key}');"
                    print_step(step, action, key, "running", details=details)
                    await self.press_key(key)
                    print(await self.get_snapshot())

                        # === PAGE ===
                elif action == "scroll":
                    direction = action_obj.get("direction", "down")
                    pixels = 500 if direction == "down" else -500
                    details = f"await page.mouse.wheel(0, {pixels});"
                    print_step(step, action, direction, "running", details=details)
                    await self.scroll(direction)
                    print(await self.get_snapshot())

                elif action == "wait":
                    seconds = float(action_obj.get("seconds", 1))
                    print_step(step, action, f"{seconds}s", "running")
                    await self.wait(seconds)
                    print(f"  {Colors.DIM}  ### Result{Colors.RESET}")
                    print(f"    Waited for {seconds}")

                elif action == "wait_for":
                    text = action_obj.get("text", "")
                    details = f"await page.waitForSelector('text={text}');"
                    print_step(step, action, text[:20], "running", details=details)
                    try:
                        await self.page.wait_for_selector(f"text={text}", timeout=10000)
                    except Exception:
                        pass  # Continue even if timeout
                    print(await self.get_snapshot())

                elif action == "screenshot":
                    path = action_obj.get("path", None)
                    print_step(step, action, path or "viewport", "running")
                    result = await self.screenshot(path=path)
                    if result.get("path"):
                        print(f"  {Colors.DIM}  ### Result{Colors.RESET}")
                        print(f"    Screenshot saved to {result['path']}")

                elif action == "save_session":
                    path = action_obj.get("path", None)
                    print_step(step, action, path or "default/arg path", "running")
                    await self.save_session(path)
                    print(f"  {Colors.DIM}  ### Result{Colors.RESET}")
                    print(f"    Session saved")

                        # === TABS ===
                elif action == "tabs_list":
                    action_desc = "list tabs"
                    print_step(step, action, "list", "running")
                    tabs = await self.tabs_list()
                    history.append({"action": action, "result": str(tabs.get("tabs", []))[:60]})

                elif action == "tabs_new":
                    url = action_obj.get("url", "")
                    action_desc = f"new tab: {url[:30]}"
                    print_step(step, action, url[:30] or "blank", "running")
                    await self.tabs_new(url if url else None)

                elif action == "tabs_select":
                    index = int(action_obj.get("index", 0))
                    action_desc = f"select tab {index}"
                    print_step(step, action, str(index), "running")
                    await self.tabs_select(index)

                elif action == "tabs_close":
                    index = action_obj.get("index", None)
                    action_desc = f"close tab {index if index else 'current'}"
                    print_step(step, action, str(index) if index else "current", "running")
                    await self.tabs_close(int(index) if index else None)

                        # === ADVANCED ===
                elif action == "file_upload":
                    ref = action_obj.get("ref", "")
                    paths = action_obj.get("paths", [])
                    action_desc = f"upload {len(paths)} file(s)"
                    print_step(step, action, f"{len(paths)} files", "running")
                    await self.file_upload(paths, ref=ref if ref else None)

                elif action == "evaluate":
                    expr = action_obj.get("expression", "")
                    action_desc = f"evaluate: {expr[:30]}"
                    print_step(step, action, expr[:30], "running")
                    result = await self.evaluate(expr)
                    history.append({"action": action, "result": str(result.get("result", ""))[:60]})

                elif action == "console_messages":
                    action_desc = "get console messages"
                    print_step(step, action, "console", "running")
                    msgs = await self.console_messages()
                    history.append({"action": action, "count": len(msgs.get("messages", []))})

                elif action == "network_requests":
                    action_desc = "get network requests"
                    print_step(step, action, "network", "running")
                    reqs = await self.network_requests()
                    history.append({"action": action, "count": len(reqs.get("requests", []))})

                elif action == "handle_dialog":
                    accept = action_obj.get("accept", True)
                    prompt_text = action_obj.get("promptText", None)
                    action_desc = f"handle dialog: {'accept' if accept else 'dismiss'}"
                    print_step(step, action, "accept" if accept else "dismiss", "running")
                    await self.handle_dialog(accept=accept, prompt_text=prompt_text)

                elif action == "resize":
                    width = int(action_obj.get("width", 1280))
                    height = int(action_obj.get("height", 720))
                    action_desc = f"resize to {width}x{height}"
                    print_step(step, action, f"{width}x{height}", "running")
                    await self.resize(width, height)

                elif action == "fill_form":
                    fields = action_obj.get("fields", [])
                    action_desc = f"fill {len(fields)} form fields"
                    print_step(step, action, f"{len(fields)} fields", "running")
                    result = await self.fill_form(fields)
                    history.append({"action": action, "fields": len(fields), "results": result.get("results", [])})

                        # === COMPLETION ===
                elif action == "done":
                    result = action_obj.get("result", "")
                    print_step(step, action, result, "success")
                    print(f"  {Colors.DIM}  ### Result{Colors.RESET}")
                    print(f"    {result}")
                    return {
                        "status": "complete",
                        "result": result,
                        "steps": step,
                        "url": self.page.url if self.page else ""
                    }
                else:
                    # Unknown action - skip
                    if self.debug:
                        print(f"DEBUG: Unknown action skipped: {action}")
                    continue

                        # Record action attempt
                history.append({"action": action, "desc": action_desc[:80]})

                        # Check progress signal (URL or snapshot changed)
                await asyncio.sleep(0.5)
                after_url = self.page.url if self.page else ""
                after_snapshot = await self.get_snapshot()
                after_sig = hashlib.sha1((after_url + "\n" + after_snapshot[:1200]).encode("utf-8", errors="ignore")).hexdigest()
                progressed = (after_sig != before_sig)

                # VISUAL VERIFICATION (Optional but improves reliability)
                if not progressed and action in ("click", "type", "press"):
                    logger.debug(f"Action '{action}' might have stalled, verifying visually...")
                    screenshot_bytes = await self.page.screenshot()
                    # We can use the vision engine to check if we're stuck
                    # For now, just log it. In a perfect version, we'd ask the LLM if we need to retry.
                
                print_step(step, action, action_desc[:40], "success" if progressed else "error")
                if progressed:
                    no_progress_streak = 0
                else:
                    no_progress_streak += 1

            except Exception as e:
                if self.debug:
                    print(f"  {Colors.RED}Error: {e}{Colors.RESET}")
                continue

        return {"status": "max_steps", "steps": max_steps, "url": self.page.url}


# =============================================================================
# MAIN
# =============================================================================

async def run(prompt: str, headless: bool = True, session_file: str = None, save_session: str = None,
              video_dir: str = None, trace_path: str = None, max_steps: int = 8) -> Dict:
    """Main entry point."""
    debug = os.environ.get("EVERSALE_DEBUG", "0") == "1"
    browser = AgenticBrowser(headless=headless, debug=debug, session_file=session_file, save_session_path=save_session,
                             video_dir=video_dir, trace_path=trace_path, max_steps=max_steps)
    try:
        await browser.setup()
        return await browser.run(prompt)
    finally:
        await browser.close()


def format_result_human_readable(result: Dict) -> str:
    """
    Convert result dict to human-readable, copy-pasteable format.
    Handles both single-task and multi-task results.
    Focuses on actionable data (URLs, names) that users can easily copy.
    """
    lines = []

    # Multi-task result
    if isinstance(result, dict) and 'tasks' in result and isinstance(result['tasks'], list):
        lines.append("")
        lines.append("COLLECTED DATA")
        lines.append("-" * 40)
        lines.append("")

        for i, task in enumerate(result['tasks'], 1):
            if len(result['tasks']) > 1:
                lines.append(f"[Task {i}]")
            _format_task_data_clean(task, lines, indent="")
            if i < len(result['tasks']):
                lines.append("")
    else:
        # Single task result
        lines.append("")
        lines.append("COLLECTED DATA")
        lines.append("-" * 40)
        lines.append("")
        _format_task_data_clean(result, lines, indent="")

    # Add file location if available
    saved_path = result.get('saved_path') if isinstance(result, dict) else None
    if not saved_path and isinstance(result, dict) and 'tasks' in result:
        for task in result.get('tasks', []):
            if task.get('saved_path'):
                saved_path = task.get('saved_path')
                break

    if saved_path:
        lines.append("")
        lines.append("-" * 40)
        lines.append(f"File saved: {saved_path}")
        lines.append("(Run again with 'add more' to append additional results)")

    return "\n".join(lines)


def _format_task_data(task: Dict, lines: list, indent: str = ""):
    """Helper to format a single task's data."""

    # Status
    status = task.get('status', 'unknown')
    lines.append(f"{indent}Status: {status}")

    # Result summary - clean up raw LLM output
    if task.get('result'):
        cleaned = clean_llm_output(str(task['result']))
        if cleaned:
            lines.append(f"{indent}Result: {cleaned}")

    # URL
    if task.get('url'):
        lines.append(f"{indent}URL: {task['url']}")

    # Steps count
    if task.get('steps'):
        lines.append(f"{indent}Steps: {task['steps']}")

    # Error
    if task.get('error'):
        lines.append(f"{indent}Error: {task['error']}")

    # Clarification
    if task.get("status") == "needs_clarification":
        q = task.get("question")
        if q:
            lines.append(f"{indent}Question: {q}")
        opts = task.get("options") or []
        if isinstance(opts, list) and opts:
            for opt in opts[:4]:
                if not isinstance(opt, dict):
                    continue
                name = opt.get("name") or opt.get("key") or "Option"
                url = opt.get("url") or ""
                if url:
                    lines.append(f"{indent}  - {name}: {url}")

    # Handle different data types
    data = task.get('data', {})

    # FB Ads data
    if isinstance(data, dict) and data.get('name') and data.get('type') in ['landing_page', 'fb_page']:
        lines.append(f"{indent}Advertiser: {data.get('name')}")
        if data.get('domain'):
            lines.append(f"{indent}Domain: {data.get('domain')}")
        lines.append(f"{indent}Type: {data.get('type')}")

    # Reddit/LinkedIn leads (list of users/profiles)
    elif isinstance(data, list) and len(data) > 0:
        leads = task.get('leads', data)
        icp_count = sum(1 for l in leads if l.get('has_icp_signal')) if leads else 0

        # Use generic property-based detection
        has_subreddit = any(l.get('subreddit') for l in leads if isinstance(l, dict))
        has_usernames = any(l.get('username') for l in leads if isinstance(l, dict))
        has_profile_urls = any('linkedin' in str(l.get('url', '')) for l in leads if isinstance(l, dict))

        if has_subreddit or (has_usernames and not has_profile_urls):
            lines.append(f"{indent}Found: {len(leads)} users" + (f" ({icp_count} with ICP signals)" if icp_count > 0 else ""))
            lines.append("")
            lines.append(f"{indent}All Leads:")

            # Show all leads with details (user requested all unique leads)
            for lead in leads:
                username = lead.get('username', 'Unknown')
                profile_url = lead.get('profile_url', lead.get('url', ''))
                evidence_url = lead.get('evidence_url', '')
                subreddit = lead.get('subreddit', '')
                signal = lead.get('warm_signal', lead.get('title', ''))
                score = lead.get('total_score', lead.get('score', 0))
                has_icp = lead.get('has_icp_signal', False)

                icp_marker = "[ICP] " if has_icp else ""
                lines.append(f"{indent}  - {icp_marker}{username} (score: {score})")
                if evidence_url:
                    lines.append(f"{indent}    Evidence: {evidence_url}")
                if profile_url:
                    lines.append(f"{indent}    Profile: {profile_url}")
                if subreddit:
                    lines.append(f"{indent}    Source: {subreddit}")
                if signal:
                    signal_preview = signal[:80] + "..." if len(signal) > 80 else signal
                    lines.append(f"{indent}    Signal: \"{signal_preview}\"")
                lines.append("")

        elif has_profile_urls:
            lines.append(f"{indent}Profiles Found: {len(leads)}")
            lines.append("")

            for lead in leads:
                name = lead.get('name', 'Unknown')
                url = lead.get('url', '')
                evidence_url = lead.get('evidence_url', lead.get('post_url', ''))
                if evidence_url:
                    lines.append(f"{indent}  - {name}: {evidence_url}")
                    lines.append(f"{indent}    Profile: {url}")
                    continue
                lines.append(f"{indent}  - {name}: {url}")

        else:
            # Generic list data (e.g., Google Maps businesses)
            lines.append(f"{indent}Items Found: {len(leads)}")
            lines.append("")

            for item in leads:
                if isinstance(item, dict):
                    # Try to find a name/title field
                    name = item.get('name') or item.get('title') or item.get('business_name') or 'Unknown'
                    url = item.get('url', '')
                    lines.append(f"{indent}  - {name}")
                    if url:
                        lines.append(f"{indent}    URL: {url}")
                    # Show other relevant fields
                    for key, value in item.items():
                        if key not in ['name', 'title', 'url', 'business_name'] and value:
                            lines.append(f"{indent}    {key.replace('_', ' ').title()}: {value}")
                    lines.append("")

    # LinkedIn fallback info
    if task.get('fallback_method'):
        lines.append(f"{indent}Fallback: {task['fallback_method']}")

    # Additional metadata for Reddit API results
    if task.get('sources'):
        lines.append(f"{indent}Sources: {', '.join(task['sources'])}")

    if task.get('icp_count') is not None:
        lines.append(f"{indent}ICP Matches: {task['icp_count']}")


def _format_task_data_clean(task: Dict, lines: list, indent: str = ""):
    """
    Format task data in a clean, copy-pasteable way.
    Focuses on actionable data - URLs, names, usernames that users can copy.
    """
    data = task.get('data', {})
    leads = task.get('leads', [])

    # Use leads if available, otherwise fall back to data
    if not leads and isinstance(data, list):
        leads = data

    if not leads:
        # No structured data, just show the result text
        result_text = task.get('result', '')
        if result_text:
            lines.append(result_text)
        return

    # Detect data type and format accordingly
    if isinstance(leads, list) and len(leads) > 0:
        first_lead = leads[0] if isinstance(leads[0], dict) else {}

        # FB Ads advertisers
        if first_lead.get('source') == 'fb_ads' or first_lead.get('type') in ('landing_page', 'fb_page'):
            lines.append(f"FB Advertisers ({len(leads)}):")
            lines.append("")
            for lead in leads:
                name = lead.get('name', 'Unknown')
                url = lead.get('url', '')
                domain = lead.get('domain', '')
                lines.append(f"  {name}")
                if url:
                    lines.append(f"  {url}")
                if domain:
                    lines.append(f"  ({domain})")
                lines.append("")

        # Reddit users
        elif first_lead.get('username') or first_lead.get('source') == 'reddit':
            icp_count = sum(1 for l in leads if l.get('has_icp_signal'))
            lines.append(f"Reddit Users ({len(leads)})" + (f" - {icp_count} high-intent" if icp_count else "") + ":")
            lines.append("")
            for lead in leads:
                username = lead.get('username', 'Unknown')
                profile_url = lead.get('profile_url', lead.get('url', ''))
                evidence_url = lead.get('evidence_url', '')
                has_icp = lead.get('has_icp_signal', False)

                icp_marker = "[HIGH-INTENT] " if has_icp else ""
                lines.append(f"  {icp_marker}u/{username}")
                if evidence_url:
                    lines.append(f"  Post: {evidence_url}")
                if profile_url:
                    lines.append(f"  Profile: {profile_url}")
                lines.append("")

        # LinkedIn profiles
        elif 'linkedin' in str(first_lead.get('url', '')) or first_lead.get('source') == 'linkedin':
            lines.append(f"LinkedIn Profiles ({len(leads)}):")
            lines.append("")
            for lead in leads:
                name = lead.get('name', 'Unknown')
                url = lead.get('url', '')
                evidence_url = lead.get('evidence_url', lead.get('post_url', ''))
                lines.append(f"  {name}")
                if url:
                    lines.append(f"  {url}")
                if evidence_url:
                    lines.append(f"  Found via: {evidence_url}")
                lines.append("")

        # Google Maps businesses
        elif first_lead.get('source') == 'google_maps' or 'maps.google' in str(first_lead.get('url', '')):
            lines.append(f"Businesses ({len(leads)}):")
            lines.append("")
            for lead in leads:
                name = lead.get('name', lead.get('business_name', 'Unknown'))
                url = lead.get('url', '')
                lines.append(f"  {name}")
                if url:
                    lines.append(f"  {url}")
                lines.append("")

        # Generic list data
        else:
            lines.append(f"Results ({len(leads)}):")
            lines.append("")
            for lead in leads:
                if isinstance(lead, dict):
                    # Try to find name/title
                    name = lead.get('name') or lead.get('title') or lead.get('username') or 'Item'
                    url = lead.get('url', '')
                    lines.append(f"  {name}")
                    if url:
                        lines.append(f"  {url}")
                    lines.append("")
                else:
                    lines.append(f"  {lead}")


async def generate_summary(prompt: str, result: Dict, gpu_client: Any) -> str:
    """Generate a natural language summary of the task result using the LLM."""

    # Prepare context
    status = result.get('status', 'unknown')
    raw_result = result.get('result', '')
    url = result.get('url', '')
    steps = result.get('steps', 0)

    # Add structured data context if available
    data_summary = ""
    if result.get('data'):
        data = result['data']
        if isinstance(data, list):
            data_sample = str(data[:10]) # More items for context
            data_summary = f"\nData Collected ({len(data)} items): {data_sample}..."
        else:
            data_summary = f"\nData Collected: {str(data)[:1000]}..."

    system_prompt = """You are a precision-focused AI browser assistant.
Your goal is to provide a CONCISE, DIRECT, and HELPFUL summary of the automation task results.
- If data was found, present it clearly (use lists for multiple items).
- If a specific question was asked, answer it directly.
- DO NOT mention internal steps, tools used, or browser technicalities.
- DO NOT start with "The task was successful" or similar filler.
- Just give the requested information in a clean format."""

    user_msg = f"""USER REQUEST: {prompt}
RAW RESULTS: {raw_result if not data_summary else data_summary}
URL REACHED: {url}

Provide the final summary:"""

    try:
        llm_response = await gpu_client.chat(
            model=GPU_MODELS.get('quality', GPU_MODELS['fast']),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg}
            ],
            temperature=0.2,
            max_tokens=800
        )
        summary = llm_response.content.strip()
        # Clean up think blocks if present
        summary = re.sub(r'<think>.*?</think>', '', summary, flags=re.DOTALL).strip()
        return summary
    except Exception as e:
        logger.error(f"Summary generation failed: {e}")
        return f"{raw_result}" if raw_result else "Task complete (summary failed)."


async def generate_smart_output(prompt: str, result: Dict, llm_client: Any = None) -> str:
    """
    Generate smart, natural language output for general browser tasks.
    Uses LLM (Kimi) to create Playwright MCP-style responses.

    For known workflows: Returns None (use structured formatter instead)
    For general tasks: Returns LLM-generated natural response
    """
    # Check if this is a known workflow with structured data
    leads = result.get('leads', [])
    data = result.get('data', [])

    if isinstance(leads, list) and len(leads) > 0:
        first_lead = leads[0] if isinstance(leads[0], dict) else {}
        # Known workflow sources - use structured formatter instead
        known_sources = ['fb_ads', 'reddit', 'linkedin', 'google_maps']
        if first_lead.get('source') in known_sources:
            return None
        if first_lead.get('type') in ('landing_page', 'fb_page'):
            return None
        if first_lead.get('username'):  # Reddit
            return None
        if 'linkedin' in str(first_lead.get('url', '')):
            return None

    # For general tasks, use LLM to generate natural response
    raw_result = str(result.get('result', '') or '')
    url = result.get('url', '')
    status = result.get('status', 'complete')

    # If we have a clean result already, check if it needs LLM enhancement
    if raw_result and len(raw_result) < 500 and not raw_result.startswith('{'):
        # Already clean text - might not need LLM
        # But enhance if it looks like internal output
        internal_markers = ['step', 'navigate', 'click', 'extract', 'wait', 'timeout', 'error:']
        if not any(marker in raw_result.lower() for marker in internal_markers):
            return None  # Already clean, no LLM needed

    # Try to get LLM client
    if not llm_client:
        try:
            from .kimi_k2_client import get_kimi_client
            llm_client = get_kimi_client({})
        except ImportError:
            pass

    if not llm_client:
        try:
            from .gpu_llm_client import GPULLMClient
            llm_client = GPULLMClient()
        except ImportError:
            return None  # No LLM available

    # Generate natural response
    system_prompt = """You are a browser automation assistant providing task results.
Respond naturally and concisely, like a helpful assistant would.

Rules:
- Be direct and informative
- If showing data, format it cleanly
- Include relevant URLs when useful
- NO technical jargon (no "navigated", "clicked", "extracted")
- NO step-by-step details
- NO "I successfully..." or "The task was..."
- Just provide the information requested

Examples of good responses:
- "The page shows 15 search results for 'AI tools'. Top result: OpenAI (openai.com)"
- "Current stock price: $150.25 (+2.3%)"
- "Found 3 articles about the topic. Here are the titles..."
- "The login form is now visible. Enter your credentials to continue."
"""

    # Build context from result
    context_parts = []
    if raw_result:
        context_parts.append(f"Raw output: {raw_result[:1000]}")
    if url:
        context_parts.append(f"Current URL: {url}")
    if status == 'blocked':
        context_parts.append("Status: Blocked (may need login or access denied)")
    if isinstance(data, list) and data:
        context_parts.append(f"Data collected: {len(data)} items")
        if len(data) <= 5:
            context_parts.append(f"Items: {data}")

    user_msg = f"""User asked: "{prompt}"

{chr(10).join(context_parts)}

Provide a natural, helpful response:"""

    try:
        response = await llm_client.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg}
            ],
            temperature=0.3,
            max_tokens=500
        )

        if hasattr(response, 'content'):
            output = response.content.strip()
        else:
            output = str(response).strip()

        # Clean up any think blocks
        output = re.sub(r'<think>.*?</think>', '', output, flags=re.DOTALL).strip()

        return output if output else None

    except Exception as e:
        logger.debug(f"Smart output generation failed: {e}")
        return None


def print_help():
    """Print a beautiful, comprehensive help screen."""
    if RICH_AVAILABLE:
        table = Table(title="Eversale CLI Commands", show_header=True, header_style="bold magenta")
        table.add_column("Command / Flag", style="cyan", no_wrap=True)
        table.add_column("Description", style="white")
        table.add_column("Example", style="dim")

        table.add_row('"[prompt]"', "Execute a single task", 'eversale "Find Nike CEO on LinkedIn"')
        table.add_row("--interactive / -i", "Start Interactive Mode (REPL)", "eversale -i")
        table.add_row("--file <path>", "Batch process tasks from a file", "eversale --file tasks.txt")
        table.add_row("", "", "")
        table.add_row("--save-session <path>", "Save browser state (logins/cookies)", "--save-session facebook.json")
        table.add_row("--load-session <path>", "Load browser state", "--load-session facebook.json")
        table.add_row("", "", "")
        table.add_row("--headed", "Show browser UI (Debugging)", "--headed")
        table.add_row("--video <dir>", "Record video of session", "--video ./recordings")
        table.add_row("--trace <path>", "Record Playwright trace", "--trace trace.zip")
        table.add_row("", "", "")
        table.add_row("--json / --csv", "Force structured output", '--json')
        table.add_row("--headless", "Run in background (Default)", "")

        rprint(Panel.fit(
            "[bold green]Eversale Agentic Browser[/bold green]\n"
            "The ultimate stealth automation agent.\n"
            "[dim]Auto-Stealth | Human Mouse | Self-Healing | Session Persistence[/dim]",
            border_style="green"
        ))
        console.print(table)
        rprint("\n[bold yellow]Features:[/bold yellow]")
        rprint(" • [cyan]Stealth-by-Default[/cyan]: Uses Patchright & Human Mouse automatically.")
        rprint(" • [cyan]Resilience[/cyan]: Auto-closes cookie banners & handles errors.")
        rprint(" • [cyan]Visuals[/cyan]: Record videos/traces with one flag.\n")
    else:
        # Fallback for systems without Rich
        print(f"Eversale Browser Agent v{VERSION}")
        print("\nCommands:")
        print('  "[prompt]"            Execute task')
        print("  --interactive, -i     Interactive Mode")
        print("  --file <path>         Batch process file")
        print("  --save-session <path> Save session")
        print("  --load-session <path> Load session")
        print("  --headed              Show UI")
        print("  --video <dir>         Record video")
        print("  --trace <path>        Record trace")


async def main():
    """CLI entry."""
    # Check env var first
    prompt_from_env = os.environ.pop("EVERSALE_PROMPT", "").strip()
    
    # Parse args from sys.argv
    args = sys.argv[1:]
    prompt_parts = []
    
    session_file = None
    save_session_path = None
    video_dir = None
    trace_path = None
    batch_file = None
    interactive = False
    output_format = None
    max_steps_arg = 8 # Default max steps
    
    # manual headless override
    headless_arg = True
    
    i = 0
    while i < len(args):
        arg = args[i]
        
        if arg in ['--help', '-h']:
            print_help()
            sys.exit(0)
        elif arg in ["--headless", "-hl"]:
            headless_arg = True
        elif arg == "--headed":
            headless_arg = False
        elif arg in ["--debug", "-d"]:
            pass # Already handled by logger
        elif arg == "--interactive" or arg == "-i":
            interactive = True
        elif arg == "--session-file":
            if i + 1 < len(args):
                session_file = args[i+1]
                i += 1
        elif arg == "--save-session":
            if i + 1 < len(args):
                save_session_path = args[i+1]
                i += 1
        elif arg == "--max-steps":
            if i + 1 < len(args):
                try:
                    max_steps_arg = int(args[i+1])
                    i += 1
                except ValueError:
                    pass
        elif arg == "--video":
            if i + 1 < len(args):
                video_dir = args[i+1]
                i += 1
        elif arg == "--trace":
            if i + 1 < len(args):
                trace_path = args[i+1]
                i += 1
        elif arg in ['--json', '--csv', '--markdown']:
            output_format = arg.replace('--', '')
            interactive = True
        elif arg.startswith('-') and arg not in ['--debug', '-d']: 
            pass
        else:
            if arg not in ['--debug', '-d']:
                 prompt_parts.append(arg)
        i += 1
        
    prompt = prompt_from_env
    if not prompt and prompt_parts:
        prompt = ' '.join(prompt_parts)

    # --- MODE 1: BATCH PROCESSING ---
    if batch_file:
        fpath = Path(batch_file)
        if not fpath.exists():
            print(f"Error: Batch file not found: {batch_file}")
            sys.exit(1)
            
        print(f"{Colors.GREEN}>> Starting Batch Processing from {batch_file}...{Colors.RESET}")
        prompts = [line.strip() for line in fpath.read_text().splitlines() if line.strip() and not line.strip().startswith('#')]
        
        debug = os.environ.get("EVERSALE_DEBUG", "0") == "1"
        browser = AgenticBrowser(headless=headless_arg, debug=debug, 
                               session_file=session_file, save_session_path=save_session,
                               video_dir=video_dir, trace_path=trace_path)
        try:
            await browser.setup()
            for idx, p in enumerate(prompts, 1):
                print(f"\n{Colors.CYAN}[Batch {idx}/{len(prompts)}]{Colors.RESET} {p}")
                await browser.run(p)
                print(f"{Colors.DIM}{'-'*50}{Colors.RESET}")
        finally:
            await browser.close()
        return

    # --- MODE 2: INTERACTIVE MODE ---
    if interactive:
        if RICH_AVAILABLE:
            rprint(Panel("[bold green]Interactive Mode Active[/bold green]\nType commands directly. Type 'exit' to quit.", border_style="green"))
        else:
            print(f"{Colors.GREEN}>> Interactive Mode Active{Colors.RESET}")
            print("   Type your command. Type 'exit' to quit.")
        
        debug = os.environ.get("EVERSALE_DEBUG", "0") == "1"
        browser = AgenticBrowser(headless=headless_arg, debug=debug, 
                               session_file=session_file, save_session_path=save_session,
                               video_dir=video_dir, trace_path=trace_path)
        
        try:
            await browser.setup()
            
            # Use initial prompt if provided
            if prompt:
                print(f"\n{Colors.CYAN}Running initial command:{Colors.RESET} {prompt}")
                await browser.run(prompt)
            
            while True:
                try:
                    user_input = await asyncio.get_event_loop().run_in_executor(None, input, f"\n{Colors.BOLD}eversale>{Colors.RESET} ")
                    user_input = user_input.strip()
                    if not user_input:
                        continue
                        
                    if user_input.lower() in ['exit', 'quit', 'bye']:
                        print("Goodbye! 👋")
                        break
                        
                    if user_input.lower() in ['help', '?']:
                        print_help()
                        continue

                    if user_input.startswith("save_session"):
                        parts = user_input.split()
                        path = parts[1] if len(parts) > 1 else None
                        await browser.save_session(path)
                        continue

                    await browser.run(user_input)
                    
                except KeyboardInterrupt:
                    print("\n(Use 'exit' to quit)")
                    continue
                except Exception as e:
                    print(f"Error: {e}")
        finally:
            await browser.close()
        return

    # --- MODE 3: SINGLE TASK ---
    if not prompt:
        print_help()
        sys.exit(1)
        
    result = await run(prompt, headless=headless_arg, session_file=session_file, save_session=save_session_path,
                       video_dir=video_dir, trace_path=trace_path, max_steps=max_steps_arg)

    # Apply custom output format if user specified one
    if OUTPUT_FORMAT_AVAILABLE and format_output:
        try:
            # Convert multi-task dict to string format for format_output
            result_for_formatting = result
            if isinstance(result, dict) and 'tasks' in result and isinstance(result['tasks'], list):
                # Convert multi-task result to string format expected by output_format_handler
                task_strings = []
                for i, task in enumerate(result['tasks'], 1):
                    task_result = task.get('result', '')
                    if task.get('url'):
                        task_result = f"{task_result}\n  URL: {task['url']}"
                    task_strings.append(f"Goal {i}: {task_result}")
                result_for_formatting = '\n'.join(task_strings)

            formatted_result = format_output(prompt, result_for_formatting)
            # If format_output returns a formatted string, print it directly
            # Otherwise fall back to human-readable
            if isinstance(formatted_result, str) and formatted_result != str(result):
                print(formatted_result)
                return
        except Exception as e:
            # If formatting fails, fall back to human-readable
            pass

    # Default: Human-readable output
    print(format_result_human_readable(result))
    
    # Generate and print natural language summary (Assistant style)
    try:
        print("\n" + "="*50)
        print("ASSISTANT RESPONSE")
        print("="*50)
        
        # Instantiate new client for summary since browser is closed/out of scope
        config = load_config()
        gpu_client = get_gpu_client(
            base_url=config.get("llm", {}).get("base_url"),
            license_key=config.get("llm", {}).get("api_key")
        )
        
        summary = await generate_summary(prompt, result, gpu_client)
        print(f"\n{summary}\n")
    except Exception as e:
        if os.environ.get("EVERSALE_DEBUG"):
            print(f"Summary generation error: {e}")


if __name__ == '__main__':
    import signal
    import atexit

    # Global shutdown flag
    _shutdown_flag = False
    _shutdown_event = None

    def handle_shutdown(signum=None, frame=None):
        """Handle shutdown signals (Ctrl+C, SIGTERM, etc.)."""
        global _shutdown_flag, _shutdown_event

        if _shutdown_flag:
            # Already shutting down, force exit on second signal
            print("\n[Force Exit]", flush=True)
            os._exit(1)

        _shutdown_flag = True
        print("\n[Interrupted] Stopping...", flush=True)

        # Try to get the running event loop and cancel all tasks
        try:
            loop = asyncio.get_running_loop()

            # Set shutdown event if it exists
            if _shutdown_event:
                _shutdown_event.set()

            # Cancel all pending tasks
            tasks = [task for task in asyncio.all_tasks(loop) if not task.done()]
            if tasks:
                for task in tasks:
                    task.cancel()

            # Schedule exit after brief cleanup window (100ms)
            loop.call_later(0.1, lambda: os._exit(0))
        except RuntimeError:
            # No running loop, just exit immediately
            os._exit(0)

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, handle_shutdown)  # Ctrl+C
    signal.signal(signal.SIGTERM, handle_shutdown)  # Process termination

    # Register atexit handler for cleanup
    atexit.register(handle_shutdown)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[Interrupted] Exiting...", flush=True)
        sys.exit(0)
    except asyncio.CancelledError:
        # Tasks were cancelled during shutdown
        sys.exit(0)
    finally:
        # Final cleanup
        handle_shutdown()
