"""
Configuration for accessibility-first browser automation.

This module provides centralized configuration for the a11y system,
making it easy to tune performance and behavior without editing core files.
"""

# === Snapshot Settings ===

# How long to cache snapshots before re-snapshotting (seconds)
SNAPSHOT_CACHE_TTL = 2.0

# Maximum elements to include in a single snapshot
# Increased to capture more elements for dense pages like FB Ads Library
MAX_ELEMENTS_PER_SNAPSHOT = 500

# Interactive roles to extract from accessibility tree
INTERACTIVE_ROLES = {
    "button", "link", "textbox", "searchbox", "combobox",
    "checkbox", "radio", "slider", "spinbutton", "switch",
    "tab", "menuitem", "option", "listitem", "treeitem",
    "cell", "gridcell", "columnheader", "rowheader",
    "heading", "img", "figure", "article", "navigation",
    "main", "complementary", "contentinfo", "banner",
}

# === Timing Settings ===

# Default timeout for browser actions (milliseconds)
DEFAULT_TIMEOUT = 5000

# Delay between actions to allow UI updates (seconds)
ACTION_DELAY = 0.3

# Delay before retrying a failed action (seconds)
RETRY_DELAY = 1.0

# Maximum retry attempts for a single action
MAX_RETRIES = 2

# Exponential backoff multiplier for retries
RETRY_BACKOFF_MULTIPLIER = 2.0

# Random jitter range for retry delays (0.0 to 1.0 = 0% to 100% jitter)
RETRY_JITTER = 0.3

# Navigation timeout (milliseconds)
NAVIGATION_TIMEOUT = 30000

# === Element Resolution Settings ===

# Enable parallel element resolution (faster but uses more resources)
PARALLEL_ELEMENT_RESOLUTION = True

# Number of concurrent element resolutions when parallel is enabled
MAX_PARALLEL_RESOLUTIONS = 5

# Fallback snapshot element limit per selector
FALLBACK_ELEMENT_LIMIT = 30

# === Performance Settings ===

# Enable snapshot caching
ENABLE_SNAPSHOT_CACHE = True

# Maximum size of snapshot cache (number of cached snapshots)
SNAPSHOT_CACHE_SIZE = 10

# Enable performance metrics collection
ENABLE_METRICS = True

# Log performance warnings if action takes longer than this (seconds)
PERFORMANCE_WARNING_THRESHOLD = 3.0

# === Logging Settings ===

# Log snapshots to console (useful for debugging, verbose)
LOG_SNAPSHOTS = False

# Log actions to console
LOG_ACTIONS = True

# Log performance metrics
LOG_METRICS = True

# Log errors and retries
LOG_ERRORS = True

# === Fallback Snapshot Selectors ===

# CSS selectors and their corresponding ARIA roles for fallback snapshot
# Order matters - selectors are tried in order
FALLBACK_SELECTORS = [
    ("button:visible", "button"),
    ("a[href]:visible", "link"),
    ("input[type='text']:visible", "textbox"),
    ("input[type='search']:visible", "searchbox"),
    ("input[type='email']:visible", "textbox"),
    ("input[type='password']:visible", "textbox"),
    ("input[type='tel']:visible", "textbox"),
    ("input[type='url']:visible", "textbox"),
    ("input[type='number']:visible", "spinbutton"),
    ("input[type='checkbox']:visible", "checkbox"),
    ("input[type='radio']:visible", "radio"),
    ("select:visible", "combobox"),
    ("textarea:visible", "textbox"),
    ("[role='button']:visible", "button"),
    ("[role='link']:visible", "link"),
    ("[role='textbox']:visible", "textbox"),
    ("[role='searchbox']:visible", "searchbox"),
    ("[role='tab']:visible", "tab"),
    ("[role='menuitem']:visible", "menuitem"),
    ("h1:visible", "heading"),
    ("h2:visible", "heading"),
    ("h3:visible", "heading"),
]

# === Agent Settings ===

# Maximum steps before agent gives up
MAX_AGENT_STEPS = 20

# Maximum tokens in LLM prompt (for snapshot truncation)
MAX_PROMPT_TOKENS = 4000

# Estimated tokens per element (for truncation calculation)
TOKENS_PER_ELEMENT = 20

# === Browser Settings ===

# Default viewport size (width, height)
DEFAULT_VIEWPORT = (1280, 720)

# Default user agent (None = use Playwright default)
DEFAULT_USER_AGENT = None

# Default headless mode (True = no visible window, False = show browser)
DEFAULT_HEADLESS = True

# Default slow motion delay (milliseconds)
DEFAULT_SLOW_MO = 0

# === Feature Flags ===

# Enable accessibility tree parsing
ENABLE_A11Y_TREE = True

# Enable fallback snapshot when a11y tree fails
ENABLE_FALLBACK_SNAPSHOT = True

# Minimum elements from a11y tree before triggering fallback
# If fewer elements than this, supplement with DOM-based fallback
FALLBACK_ELEMENT_THRESHOLD = 20

# Enable automatic retry on action failure
ENABLE_AUTO_RETRY = True

# Enable exponential backoff for retries
ENABLE_EXPONENTIAL_BACKOFF = True

# Enable jitter in retry delays
ENABLE_RETRY_JITTER = True

# === Token Optimization Settings ===
# These settings dramatically reduce token consumption by optimizing
# snapshot delivery, history management, and action batching.
# Enabled by default for cost reduction and faster LLM responses.

# Snapshot diffing - only send changes (70-80% reduction)
ENABLE_SNAPSHOT_DIFF = True
DIFF_FORMAT = "minimal"  # "minimal" or "detailed"

# History pruning - remove old screenshots (50-60% reduction)
ENABLE_HISTORY_PRUNING = True
MAX_HISTORY_ITEMS = 10
PRESERVE_RECENT_MESSAGES = 3
PRUNE_SCREENSHOTS = True
KEEP_LAST_N_SCREENSHOTS = 3

# Batch actions - combine multiple actions (90% reduction per batch)
ENABLE_BATCH_ACTIONS = True
MAX_ACTIONS_PER_BATCH = 10

# Selector filtering - capture only relevant sections (40-60% reduction)
DEFAULT_SNAPSHOT_SELECTOR = None  # None = full page
DEFAULT_EXCLUDE_SELECTORS = []  # e.g., ["footer", "aside"]

# Flash mode - skip reasoning for simple tasks (30-40% reduction)
ENABLE_FLASH_MODE = False  # Disabled by default, enable per-task
FLASH_MODE_AUTO_DETECT = True  # Auto-enable for simple goals

# Keyboard fallback - use Tab/Enter when clicks fail
ENABLE_KEYBOARD_FALLBACK = True
MAX_TAB_ATTEMPTS = 30
KEYBOARD_FALLBACK_DELAY = 0.1  # seconds between Tab presses

# === Performance Thresholds ===

# Token budget warnings
TOKEN_WARNING_THRESHOLD = 50000  # Warn if snapshot exceeds this
MAX_SNAPSHOT_TOKENS = 100000  # Hard limit, truncate if exceeded

# Prefix caching optimization
ENABLE_PREFIX_CACHING = True
STATIC_CONTEXT_FIRST = True  # Put stable content at start for caching
