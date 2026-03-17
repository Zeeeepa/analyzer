"""
Goal Sequencer - Parses complex prompts into sequential goals with dependencies.

Handles prompts like:
- "go to gmail then check inbox then reply to first email"
- "search google for X, then extract results, then save to file"
- "navigate to site A, then site B, then site C"
- "if logged in then check messages, otherwise login first"
- "Go to X. Go to Y. Go to Z." (sentence-delimited with action verbs)
- "Search A. Open B. Visit C." (mixed action verbs)

Splitting strategies:
1. Numbered list pattern (1. X 2. Y 3. Z)
2. Sentence boundary + action verb (". Go to ", ". Navigate to ", etc.)
3. Explicit sequence connectors (then, next, after that, etc.)
4. Comma-separated actions with verb detection
5. "and" between distinct actions

Scalability: Optimized for 100-300+ step sequences with:
- Bounded result storage (200 chars max per goal)
- Cached property computations (avoid O(n^2))
- Pre-compiled regex patterns
- Hard limits on goal count (300 max)
- Automatic variable cleanup
- Checkpoint support for crash recovery
"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any, Callable
from enum import Enum
from pathlib import Path
from datetime import datetime
import re
import json
import hashlib
from loguru import logger

# === SCALABILITY CONSTANTS ===
MAX_GOALS = 300  # Hard limit on goal count
MAX_RESULT_LENGTH = 200  # Truncate results to prevent memory bloat
MAX_VARIABLES = 50  # Max stored variables before cleanup
CONTEXT_HISTORY_LIMIT = 3  # Only show last N completed goals in context

# === CHECKPOINT STORAGE ===
CHECKPOINT_DIR = Path.home() / '.eversale' / 'checkpoints' / 'goals'
CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)


class GoalStatus(Enum):
    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class GoalType(Enum):
    """Type of goal for execution handling."""
    ACTION = "action"        # Standard action goal
    CONDITIONAL = "conditional"  # If/then/else goal
    ASSERTION = "assertion"  # Check/verify condition
    EXTRACTION = "extraction"  # Extract data from page


@dataclass
class GoalSequenceCheckpoint:
    """
    Checkpoint state for goal sequences - enables resume after crashes.

    Enables:
    - Resume from any goal index after crash/restart
    - Restore page state (URL, title, variables)
    - Restore completed goal results
    - Track progress across restarts

    Usage:
        # Save checkpoint before each goal
        checkpoint = GoalSequenceCheckpoint.from_sequence(sequence, prompt)
        checkpoint.save()

        # On restart
        checkpoint = GoalSequenceCheckpoint.load(sequence_id)
        if checkpoint:
            sequence = checkpoint.restore_to_sequence()
    """
    sequence_id: str  # Hash of original prompt
    original_prompt: str
    current_index: int
    total_goals: int

    # Page state
    page_url: Optional[str] = None
    page_title: Optional[str] = None
    page_snapshot: Optional[str] = None
    page_variables: Dict[str, Any] = field(default_factory=dict)

    # Completed goals (index -> result)
    completed_results: Dict[int, str] = field(default_factory=dict)

    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    checkpoint_count: int = 0

    @classmethod
    def generate_sequence_id(cls, prompt: str) -> str:
        """Generate unique sequence ID from prompt."""
        return hashlib.md5(prompt[:200].encode()).hexdigest()[:16]

    @classmethod
    def from_sequence(cls, sequence: 'GoalSequence', original_prompt: str) -> 'GoalSequenceCheckpoint':
        """Create checkpoint from current sequence state."""
        sequence_id = cls.generate_sequence_id(original_prompt)

        # Extract completed goal results
        completed = {}
        for goal in sequence.goals:
            if goal.status == GoalStatus.COMPLETED and goal.result:
                completed[goal.index] = goal.result

        return cls(
            sequence_id=sequence_id,
            original_prompt=original_prompt,
            current_index=sequence.current_index,
            total_goals=len(sequence.goals),
            page_url=sequence.page_state.url if sequence.page_state else None,
            page_title=sequence.page_state.title if sequence.page_state else None,
            page_snapshot=sequence.page_state.snapshot_summary if sequence.page_state else None,
            page_variables=dict(sequence.page_state.variables) if sequence.page_state else {},
            completed_results=completed
        )

    @classmethod
    def load(cls, sequence_id: str) -> Optional['GoalSequenceCheckpoint']:
        """Load checkpoint from disk."""
        checkpoint_file = CHECKPOINT_DIR / f'{sequence_id}.json'
        if not checkpoint_file.exists():
            return None

        try:
            data = json.loads(checkpoint_file.read_text())
            checkpoint = cls(
                sequence_id=data['sequence_id'],
                original_prompt=data['original_prompt'],
                current_index=data['current_index'],
                total_goals=data['total_goals'],
                page_url=data.get('page_url'),
                page_title=data.get('page_title'),
                page_snapshot=data.get('page_snapshot'),
                page_variables=data.get('page_variables', {}),
                completed_results={int(k): v for k, v in data.get('completed_results', {}).items()},
                created_at=data.get('created_at', datetime.now().isoformat()),
                updated_at=data.get('updated_at', datetime.now().isoformat()),
                checkpoint_count=data.get('checkpoint_count', 0)
            )
            logger.info(f"[CHECKPOINT] Loaded goal sequence checkpoint: {checkpoint.current_index}/{checkpoint.total_goals} goals completed")
            return checkpoint
        except Exception as e:
            logger.warning(f"[CHECKPOINT] Failed to load checkpoint {sequence_id}: {e}")
            return None

    def save(self):
        """Save checkpoint to disk."""
        checkpoint_file = CHECKPOINT_DIR / f'{self.sequence_id}.json'
        self.updated_at = datetime.now().isoformat()
        self.checkpoint_count += 1

        try:
            data = {
                'sequence_id': self.sequence_id,
                'original_prompt': self.original_prompt,
                'current_index': self.current_index,
                'total_goals': self.total_goals,
                'page_url': self.page_url,
                'page_title': self.page_title,
                'page_snapshot': self.page_snapshot,
                'page_variables': self.page_variables,
                'completed_results': {str(k): v for k, v in self.completed_results.items()},
                'created_at': self.created_at,
                'updated_at': self.updated_at,
                'checkpoint_count': self.checkpoint_count
            }
            checkpoint_file.write_text(json.dumps(data, indent=2, default=str))
            logger.debug(f"[CHECKPOINT] Saved goal sequence checkpoint #{self.checkpoint_count}: goal {self.current_index}/{self.total_goals}")
        except Exception as e:
            logger.warning(f"[CHECKPOINT] Failed to save checkpoint: {e}")

    def restore_to_sequence(self, sequence: 'GoalSequence') -> 'GoalSequence':
        """Restore checkpoint state into a sequence object."""
        # Restore page state
        if sequence.page_state:
            sequence.page_state.url = self.page_url
            sequence.page_state.title = self.page_title
            sequence.page_state.snapshot_summary = self.page_snapshot
            sequence.page_state.variables = dict(self.page_variables)

        # Restore current index
        sequence.current_index = self.current_index

        # Mark completed goals as completed and restore their results
        for goal in sequence.goals:
            if goal.index < self.current_index:
                goal.status = GoalStatus.COMPLETED
                if goal.index in self.completed_results:
                    goal.result = self.completed_results[goal.index]

        # Invalidate cache after restoration
        sequence._invalidate_cache()

        logger.info(f"[CHECKPOINT] Restored sequence state: resuming at goal {self.current_index}/{len(sequence.goals)}")
        return sequence

    def delete(self):
        """Delete checkpoint file (called after successful completion)."""
        checkpoint_file = CHECKPOINT_DIR / f'{self.sequence_id}.json'
        try:
            if checkpoint_file.exists():
                checkpoint_file.unlink()
                logger.info(f"[CHECKPOINT] Deleted checkpoint {self.sequence_id}")
        except Exception as e:
            logger.warning(f"[CHECKPOINT] Failed to delete checkpoint: {e}")

    @staticmethod
    def list_all() -> List['GoalSequenceCheckpoint']:
        """List all available checkpoints."""
        checkpoints = []
        for checkpoint_file in CHECKPOINT_DIR.glob('*.json'):
            try:
                data = json.loads(checkpoint_file.read_text())
                sequence_id = data.get('sequence_id', checkpoint_file.stem)
                checkpoint = GoalSequenceCheckpoint.load(sequence_id)
                if checkpoint:
                    checkpoints.append(checkpoint)
            except Exception as e:
                logger.debug(f"Failed to load checkpoint from {checkpoint_file}: {e}")
        return checkpoints

    @staticmethod
    def cleanup_old_checkpoints(max_age_days: int = 7):
        """Remove old checkpoint files."""
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(days=max_age_days)
        removed = 0

        for checkpoint_file in CHECKPOINT_DIR.glob('*.json'):
            try:
                data = json.loads(checkpoint_file.read_text())
                updated_at = datetime.fromisoformat(data.get('updated_at', data.get('created_at', '')))
                if updated_at < cutoff:
                    checkpoint_file.unlink()
                    removed += 1
            except Exception:
                pass

        if removed:
            logger.info(f"[CHECKPOINT] Cleaned up {removed} old goal sequence checkpoints")


@dataclass
class PageState:
    """Tracks browser page state between goals for context passing.

    Optimized for long sequences:
    - Results bounded to MAX_RESULT_LENGTH
    - Variables auto-cleaned when exceeding MAX_VARIABLES
    - Pre-compiled regex for URL/title extraction
    """
    url: Optional[str] = None
    title: Optional[str] = None
    snapshot_summary: Optional[str] = None
    extracted_elements: Dict[str, str] = field(default_factory=dict)
    last_action: Optional[str] = None
    last_result: Optional[str] = None
    variables: Dict[str, Any] = field(default_factory=dict)

    # Pre-compiled patterns for efficiency
    _URL_PATTERN = re.compile(r'https?://[^\s\'"<>]+')
    _TITLE_PATTERN = re.compile(r'(?:title|page)[\s:]+["\']?([^"\'<>\n]+)["\']?', re.I)

    def update_from_result(self, result: str, action: str = None):
        """Update page state from execution result."""
        # Bound result to prevent memory bloat
        self.last_result = result[:MAX_RESULT_LENGTH] if result else None
        self.last_action = action[:100] if action else None

        # Extract URL from result if present (use pre-compiled pattern)
        url_match = self._URL_PATTERN.search(result or '')
        if url_match:
            self.url = url_match.group(0)

        # Extract title from result if present
        title_match = self._TITLE_PATTERN.search(result or '')
        if title_match:
            self.title = title_match.group(1).strip()[:100]

    def set_variable(self, name: str, value: Any):
        """Store a variable with automatic cleanup for long sequences."""
        self.variables[name] = value
        # Auto-cleanup: remove oldest variables if exceeding limit
        if len(self.variables) > MAX_VARIABLES:
            # Keep only the most recent MAX_VARIABLES entries
            keys_to_remove = list(self.variables.keys())[:-MAX_VARIABLES]
            for key in keys_to_remove:
                del self.variables[key]
            logger.debug(f"Auto-cleaned {len(keys_to_remove)} old variables")

    def to_context_string(self) -> str:
        """Generate context string for LLM prompts."""
        parts = []
        if self.url:
            parts.append(f"Current URL: {self.url}")
        if self.title:
            parts.append(f"Page title: {self.title}")
        if self.last_action:
            parts.append(f"Last action: {self.last_action}")
        # Only show last 5 variables to prevent context bloat
        if self.variables:
            recent_vars = dict(list(self.variables.items())[-5:])
            parts.append(f"Variables: {recent_vars}")
        return " | ".join(parts) if parts else "No page state"


@dataclass
class Condition:
    """A condition for conditional execution."""
    check: str  # What to check (e.g., "logged in", "element exists")
    negate: bool = False  # True for "if NOT x"

    def matches(self, page_state: PageState) -> bool:
        """Check if condition matches based on page state."""
        check_lower = self.check.lower()

        # Check for login state
        if 'logged in' in check_lower or 'signed in' in check_lower:
            # Check if URL/result suggests logged in state
            result = page_state.last_result or ''
            logged_in = any(kw in result.lower() for kw in ['inbox', 'dashboard', 'account', 'profile', 'welcome'])
            return not logged_in if self.negate else logged_in

        # Check for element existence
        if 'exists' in check_lower or 'found' in check_lower or 'visible' in check_lower:
            # This would need actual page inspection - for now return True
            return True

        # Check for error state
        if 'error' in check_lower or 'failed' in check_lower:
            result = page_state.last_result or ''
            has_error = any(kw in result.lower() for kw in ['error', 'failed', 'not found', 'denied'])
            return not has_error if self.negate else has_error

        # Default to true (condition passes)
        return True


@dataclass
class Goal:
    """A single goal in a sequence.

    Results are bounded to MAX_RESULT_LENGTH to prevent memory bloat
    in long sequences (100-300+ goals).
    """
    description: str
    index: int
    status: GoalStatus = GoalStatus.PENDING
    _result: Optional[str] = field(default=None, repr=False)  # Internal storage
    error: Optional[str] = None
    depends_on: List[int] = field(default_factory=list)
    is_blocking: bool = True  # If True, failure stops the sequence
    retries: int = 0
    max_retries: int = 2
    goal_type: GoalType = GoalType.ACTION
    condition: Optional[Condition] = None  # For conditional goals
    else_goal: Optional['Goal'] = None  # Alternative goal if condition fails

    @property
    def result(self) -> Optional[str]:
        """Get the bounded result."""
        return self._result

    @result.setter
    def result(self, value: Optional[str]):
        """Set result with automatic truncation."""
        if value and len(value) > MAX_RESULT_LENGTH:
            self._result = value[:MAX_RESULT_LENGTH] + "..."
        else:
            self._result = value


@dataclass
class GoalSequence:
    """A sequence of goals parsed from a complex prompt.

    Optimized for 100-300+ goal sequences with:
    - Cached completed/pending counts (avoid O(n^2) recalculation)
    - Bounded context generation
    - Efficient state tracking
    """
    original_prompt: str
    goals: List[Goal]
    current_index: int = 0
    page_state: PageState = field(default_factory=PageState)  # Track state between goals

    # Cached counts to avoid O(n) recalculation on every access
    _completed_count: int = field(default=0, repr=False)
    _cache_valid: bool = field(default=False, repr=False)

    def _invalidate_cache(self):
        """Mark cache as invalid - called when goals change state."""
        self._cache_valid = False

    def _update_cache(self):
        """Recalculate cached values if needed."""
        if not self._cache_valid:
            self._completed_count = sum(1 for g in self.goals if g.status == GoalStatus.COMPLETED)
            self._cache_valid = True

    @property
    def current_goal(self) -> Optional[Goal]:
        if 0 <= self.current_index < len(self.goals):
            return self.goals[self.current_index]
        return None

    @property
    def completed_count(self) -> int:
        """Get completed goal count (cached)."""
        self._update_cache()
        return self._completed_count

    @property
    def completed_goals(self) -> List[Goal]:
        """Get completed goals - use sparingly in long sequences."""
        return [g for g in self.goals if g.status == GoalStatus.COMPLETED]

    @property
    def pending_goals(self) -> List[Goal]:
        """Get pending goals - use sparingly in long sequences."""
        return [g for g in self.goals if g.status == GoalStatus.PENDING]

    @property
    def is_complete(self) -> bool:
        return all(g.status in [GoalStatus.COMPLETED, GoalStatus.SKIPPED] for g in self.goals)

    @property
    def progress_summary(self) -> str:
        completed = self.completed_count  # Use cached count
        total = len(self.goals)
        return f"Progress: {completed}/{total} goals completed"

    def update_state(self, result: str, action: str = None):
        """Update page state after goal execution."""
        self.page_state.update_from_result(result, action)

    def set_variable(self, name: str, value: Any):
        """Store a variable for use in later goals (with auto-cleanup)."""
        self.page_state.set_variable(name, value)

    def get_variable(self, name: str, default: Any = None) -> Any:
        """Retrieve a stored variable."""
        return self.page_state.variables.get(name, default)

    def get_recent_completed(self, limit: int = CONTEXT_HISTORY_LIMIT) -> List[Goal]:
        """Get only the most recent completed goals (efficient for long sequences)."""
        # Scan backwards from current_index to find recent completed
        recent = []
        for i in range(self.current_index - 1, -1, -1):
            if self.goals[i].status == GoalStatus.COMPLETED:
                recent.append(self.goals[i])
                if len(recent) >= limit:
                    break
        return list(reversed(recent))

    def get_context_for_llm(self) -> str:
        """Generate context string to inject into LLM prompts.

        Note: We intentionally DON'T include the original task to avoid
        confusing the LLM. Each goal should be executed independently.

        Optimized: Uses get_recent_completed() instead of full list scan.
        """
        lines = []

        # Add page state context (current URL, title, etc.)
        state_str = self.page_state.to_context_string()
        if state_str != "No page state":
            lines.append(f"BROWSER STATE: {state_str}")

        # Use efficient recent completed lookup
        recent = self.get_recent_completed(CONTEXT_HISTORY_LIMIT)
        if recent:
            lines.append("\nPREVIOUS COMPLETED:")
            for goal in recent:
                result_preview = (goal.result[:80] + "...") if goal.result and len(goal.result) > 80 else (goal.result or "Done")
                lines.append(f"  - {goal.description[:50]}: {result_preview}")

        # Show current goal position (use cached count)
        lines.append(f"\nPROGRESS: {self.completed_count}/{len(self.goals)} completed")

        return "\n".join(lines) if lines else ""


class GoalSequencer:
    """Parses complex prompts into goal sequences.

    Optimized for 100-300+ goal sequences with:
    - Pre-compiled regex patterns (avoid recompilation per goal)
    - Hard limit on goal count (MAX_GOALS)
    - Efficient splitting algorithms
    """

    # Connectors that indicate sequential goals
    SEQUENCE_CONNECTORS = [
        r'\bthen\b',
        r'\bafter that\b',
        r'\bnext\b',
        r'\bafterwards?\b',
        r'\bfollowed by\b',
        r'\band then\b',
        r'\bfinally\b',
        r'\blastly\b',
        r',\s*then\b',
    ]

    # Patterns that indicate conditional execution
    CONDITIONAL_PATTERNS = [
        r'\bif\s+.+\s+then\b',
        r'\bwhen\s+.+\s+then\b',
        r'\bonce\s+.+\s+then\b',
    ]

    # Extended conditional patterns with capture groups (PRE-COMPILED)
    CONDITIONAL_REGEX = [
        # "if X then Y else Z" pattern
        re.compile(r'\bif\s+(.+?)\s+then\s+(.+?)(?:\s+(?:else|otherwise)\s+(.+))?$', re.I),
        # "when X then Y" pattern
        re.compile(r'\bwhen\s+(.+?)\s+then\s+(.+)$', re.I),
        # "once X then Y" pattern
        re.compile(r'\bonce\s+(.+?)\s+then\s+(.+)$', re.I),
    ]

    # Action verbs for splitting (constant, defined once)
    ACTION_VERBS = [
        'find', 'search', 'go to', 'navigate', 'open', 'visit', 'click',
        'type', 'enter', 'extract', 'get', 'check', 'look for', 'browse',
        'scroll', 'download', 'upload', 'send', 'reply', 'dm', 'message'
    ]

    # Platform names that commonly start goals after sentence boundaries
    # IMPORTANT: Order matters for regex alternation - more specific names first
    # 'Zoho Mail' before 'Zoho', 'Google Maps' before 'Google', etc.
    PLATFORM_NAMES = [
        # Sales & Marketing
        'FB Ads', 'Facebook Ads', 'Facebook', 'Reddit', 'LinkedIn',
        'Google Maps', 'Google Mail', 'Google Scholar', 'Google News', 'Google', 'Gmail',
        'Zoho Mail', 'Zoho', 'Salesforce', 'HubSpot',
        # Social Media
        'Twitter', 'X.com', 'Instagram', 'TikTok', 'YouTube', 'Pinterest', 'Twitch',
        # Recruiting & HR
        'Indeed', 'Glassdoor', 'ZipRecruiter', 'Upwork', 'Fiverr', 'Freelancer', 'Toptal',
        # E-commerce
        'Amazon', 'eBay', 'Etsy', 'Shopify', 'Alibaba',
        # Real Estate
        'Zillow', 'Realtor', 'Redfin',
        # Local Business & Reviews
        'Yelp', 'TripAdvisor', 'OpenTable',
        # Travel & Hospitality
        'Booking.com', 'Airbnb', 'Expedia', 'Kayak',
        # Finance & Banking
        'Coinbase', 'Robinhood', 'Yahoo Finance', 'TurboTax',
        # Healthcare
        'Zocdoc', 'WebMD', 'Healthgrades',
        # Education & Learning
        'Coursera', 'Udemy', 'LinkedIn Learning', 'Khan Academy',
        # Food & Delivery
        'DoorDash', 'Uber Eats', 'Grubhub',
        # Automotive
        'AutoTrader', 'CarGurus', 'CarMax',
        # Tickets & Events
        'Ticketmaster', 'Eventbrite', 'StubHub', 'Meetup',
        # Logistics & Shipping
        'FedEx', 'UPS', 'USPS', 'DHL',
        # Customer Support
        'Zendesk', 'Intercom', 'Freshdesk',
        # Accounting & Finance
        'QuickBooks', 'Xero', 'FreshBooks', 'Wave',
        # Legal & Documents
        'DocuSign', 'PandaDoc',
        # B2B Marketplaces
        'ThomasNet', 'Made-in-China',
        # Gaming
        'Steam', 'Epic Games',
        # Research & Community
        'Wikipedia', 'Quora', 'Hacker News', 'Product Hunt', 'Medium', 'Substack',
        # Productivity & Project Management
        'Trello', 'Asana', 'Notion', 'Slack',
        # Email
        'Outlook',
        # Government
        'IRS', 'USCIS',
        # Other
        'Craigslist', 'Bing', 'Yahoo', 'Spotify', 'Netflix',
        'Discord', 'Telegram', 'WhatsApp'
    ]

    def __init__(self):
        self._sequence_pattern = '|'.join(self.SEQUENCE_CONNECTORS)
        # Pre-compile the sequence pattern
        self._sequence_regex = re.compile(f'({self._sequence_pattern})', re.IGNORECASE)
        # Pre-compile action verb patterns for splitting
        self._action_verb_pattern = '|'.join(rf'\b{re.escape(v)}\b' for v in self.ACTION_VERBS)
        self._comma_split_regex = re.compile(r',\s*(?=' + self._action_verb_pattern + r')', re.IGNORECASE)
        self._and_split_regex = re.compile(r'\s+and\s+(?=' + self._action_verb_pattern + r')', re.IGNORECASE)
        # Pre-compile leading conjunction removal
        self._leading_conjunction_regex = re.compile(r'^(and|but|or|,)\s*', re.IGNORECASE)
        # Pre-compile sentence boundary + action verb pattern (for ". Go to " or ".Go to " style prompts)
        # This matches ".<optional space><action verb>" where action verb is capitalized
        # Uses \s* to allow zero or more spaces (handles copy-paste where spaces get removed)
        action_verbs_capitalized = '|'.join(re.escape(v.title()) for v in self.ACTION_VERBS)
        self._sentence_action_pattern = re.compile(
            rf'\.\s*({action_verbs_capitalized})\s+',
            re.IGNORECASE
        )
        # Pre-compile sentence boundary + platform name pattern (for ". Reddit " or ".Reddit " style prompts)
        # This matches ".<optional space><platform name>" where platform name appears after sentence boundary
        # Uses \s* to allow zero or more spaces (handles copy-paste where spaces get removed)
        platform_names_pattern = '|'.join(re.escape(p) for p in self.PLATFORM_NAMES)
        self._sentence_platform_pattern = re.compile(
            rf'\.\s*({platform_names_pattern})\b',
            re.IGNORECASE
        )

    def is_complex_prompt(self, prompt: str) -> bool:
        """Check if prompt contains multiple sequential goals.

        BULLETPROOF DETECTION - works regardless of formatting:
        - With or without spaces after periods
        - With or without periods at all
        - Just by counting distinct sites/platforms mentioned
        """
        prompt_lower = prompt.lower()

        # BULLETPROOF CHECK 1: Count distinct platforms/sites mentioned
        # If 2+ distinct sites are mentioned, it's multi-goal regardless of formatting
        sites_mentioned = set()
        site_keywords = {
            # Sales & Marketing
            'fb ads': 'fb_ads', 'facebook ads': 'fb_ads', 'ads library': 'fb_ads',
            'reddit': 'reddit', 'subreddit': 'reddit',
            'linkedin': 'linkedin',
            'google maps': 'maps',
            'gmail': 'gmail', 'google mail': 'gmail',
            'zoho': 'zoho', 'zoho mail': 'zoho',
            'hubspot': 'hubspot',
            'salesforce': 'salesforce',
            # Social Media
            'twitter': 'twitter', 'x.com': 'twitter',
            'instagram': 'instagram',
            'tiktok': 'tiktok',
            'youtube': 'youtube',
            'pinterest': 'pinterest',
            'twitch': 'twitch',
            # Recruiting & HR
            'indeed': 'indeed', 'indeed.com': 'indeed',
            'glassdoor': 'glassdoor',
            'ziprecruiter': 'ziprecruiter',
            # Freelance & Gig
            'upwork': 'upwork',
            'fiverr': 'fiverr',
            'freelancer': 'freelancer',
            'toptal': 'toptal',
            # E-commerce
            'amazon': 'amazon', 'amazon.com': 'amazon',
            'ebay': 'ebay', 'ebay.com': 'ebay',
            'etsy': 'etsy', 'etsy.com': 'etsy',
            'shopify': 'shopify',
            'alibaba': 'alibaba',
            # Real Estate
            'zillow': 'zillow', 'zillow.com': 'zillow',
            'realtor': 'realtor', 'realtor.com': 'realtor',
            'redfin': 'redfin', 'redfin.com': 'redfin',
            # Local Business & Reviews
            'yelp': 'yelp', 'yelp.com': 'yelp',
            'tripadvisor': 'tripadvisor',
            'opentable': 'opentable',
            # Travel & Hospitality
            'booking.com': 'booking', 'booking': 'booking',
            'airbnb': 'airbnb',
            'expedia': 'expedia',
            'kayak': 'kayak',
            # Finance & Banking
            'coinbase': 'coinbase',
            'robinhood': 'robinhood',
            'yahoo finance': 'yahoofinance',
            'turbotax': 'turbotax',
            # Healthcare
            'zocdoc': 'zocdoc',
            'webmd': 'webmd',
            'healthgrades': 'healthgrades',
            # Education & Learning
            'coursera': 'coursera',
            'udemy': 'udemy',
            'linkedin learning': 'linkedinlearning',
            'khan academy': 'khanacademy',
            # Food & Delivery
            'doordash': 'doordash',
            'uber eats': 'ubereats', 'ubereats': 'ubereats',
            'grubhub': 'grubhub',
            # Automotive
            'autotrader': 'autotrader', 'auto trader': 'autotrader',
            'cargurus': 'cargurus', 'car gurus': 'cargurus',
            'carmax': 'carmax',
            # Tickets & Events
            'ticketmaster': 'ticketmaster',
            'eventbrite': 'eventbrite',
            'stubhub': 'stubhub',
            'meetup': 'meetup',
            # Logistics & Shipping
            'fedex': 'fedex',
            'ups': 'ups',
            'usps': 'usps',
            'dhl': 'dhl',
            # Customer Support
            'zendesk': 'zendesk',
            'intercom': 'intercom',
            'freshdesk': 'freshdesk',
            # Accounting & Finance Tools
            'quickbooks': 'quickbooks',
            'xero': 'xero',
            'freshbooks': 'freshbooks',
            'wave': 'wave',
            # Legal & Documents
            'docusign': 'docusign',
            'pandadoc': 'pandadoc',
            # B2B Marketplaces
            'thomasnet': 'thomasnet',
            'made-in-china': 'madeinchina', 'made in china': 'madeinchina',
            # Gaming
            'steam': 'steam',
            'epic games': 'epicgames',
            # Research & Community
            'google search': 'google', 'google.com': 'google',
            'google scholar': 'scholar',
            'google news': 'gnews',
            'wikipedia': 'wikipedia',
            'quora': 'quora',
            'hacker news': 'hackernews', 'hn': 'hackernews',
            'product hunt': 'producthunt',
            'medium': 'medium',
            'substack': 'substack',
            # Productivity & Project Management
            'trello': 'trello',
            'asana': 'asana',
            'notion': 'notion',
            'slack': 'slack',
            # Email
            'outlook': 'outlook',
            # Government
            'irs': 'irs',
            'uscis': 'uscis',
            # Other
            'craigslist': 'craigslist',
            'bing': 'bing',
        }
        for keyword, site_id in site_keywords.items():
            if keyword in prompt_lower:
                sites_mentioned.add(site_id)

        if len(sites_mentioned) >= 2:
            logger.info(f"[MULTI-GOAL] Detected {len(sites_mentioned)} distinct sites: {sites_mentioned}")
            return True

        # BULLETPROOF CHECK 2: Count "go to" occurrences (most common pattern)
        go_to_count = len(re.findall(r'\bgo\s*to\b', prompt_lower))
        if go_to_count >= 2:
            logger.info(f"[MULTI-GOAL] Detected {go_to_count} 'go to' occurrences")
            return True

        # BULLETPROOF CHECK 3: Count action verbs
        action_verbs = ['go to', 'navigate to', 'visit', 'open', 'search', 'find', 'check', 'output']
        verb_count = sum(len(re.findall(rf'\b{re.escape(verb)}\b', prompt_lower)) for verb in action_verbs)
        if verb_count >= 3:
            logger.info(f"[MULTI-GOAL] Detected {verb_count} action verbs")
            return True

        # Check for conditional patterns
        if self._has_conditional(prompt_lower):
            return True

        # Check for sentence boundary + action verb pattern (". Go to ", ".Go to ", etc.)
        if self._sentence_action_pattern.search(prompt):
            return True

        # Check for sentence boundary + platform name pattern (". Reddit ", ".Reddit ", etc.)
        if self._sentence_platform_pattern.search(prompt):
            return True

        # Check for sequence connectors
        for pattern in self.SEQUENCE_CONNECTORS:
            if re.search(pattern, prompt_lower):
                return True

        # Check for comma-separated actions
        if verb_count >= 2 and ',' in prompt:
            return True

        return False

    def _has_conditional(self, prompt: str) -> bool:
        """Check if prompt has conditional logic."""
        for pattern in self.CONDITIONAL_PATTERNS:
            if re.search(pattern, prompt, re.I):
                return True
        return False

    def _parse_conditional(self, prompt: str) -> Optional[tuple]:
        """Parse conditional pattern, returns (condition, then_action, else_action)."""
        for regex in self.CONDITIONAL_REGEX:
            match = regex.search(prompt)
            if match:
                groups = match.groups()
                condition = groups[0].strip() if groups[0] else None
                then_action = groups[1].strip() if len(groups) > 1 and groups[1] else None
                else_action = groups[2].strip() if len(groups) > 2 and groups[2] else None
                return (condition, then_action, else_action)
        return None

    def parse(self, prompt: str) -> GoalSequence:
        """Parse a complex prompt into a goal sequence."""
        if not self.is_complex_prompt(prompt):
            # Single goal - wrap in sequence
            return GoalSequence(
                original_prompt=prompt,
                goals=[Goal(description=prompt.strip(), index=0)]
            )

        # Check for conditional pattern first
        conditional = self._parse_conditional(prompt)
        if conditional:
            condition_text, then_action, else_action = conditional
            goals = []

            # Create conditional goal
            main_goal = Goal(
                description=then_action,
                index=0,
                goal_type=GoalType.CONDITIONAL,
                condition=Condition(check=condition_text),
            )

            # Create else goal if present
            if else_action:
                else_goal = Goal(
                    description=else_action,
                    index=1,
                    goal_type=GoalType.ACTION,
                    is_blocking=False,  # Don't fail whole sequence if else fails
                )
                main_goal.else_goal = else_goal
                goals = [main_goal, else_goal]
            else:
                goals = [main_goal]

            logger.info(f"Parsed conditional: IF {condition_text} THEN {then_action} {'ELSE ' + else_action if else_action else ''}")
            return GoalSequence(original_prompt=prompt, goals=goals)

        # Split by sequence connectors
        goal_texts = self._split_into_goals(prompt)

        # CRITICAL FIX: Enforce MAX_GOALS limit to prevent memory exhaustion (audit fix)
        if len(goal_texts) > MAX_GOALS:
            logger.warning(f"Goal count {len(goal_texts)} exceeds MAX_GOALS {MAX_GOALS} - truncating")
            goal_texts = goal_texts[:MAX_GOALS]

        # Create goal objects with dependencies
        goal_objects = []
        for i, goal_text in enumerate(goal_texts):
            # Check if this individual goal has a conditional
            nested_conditional = self._parse_conditional(goal_text)
            if nested_conditional:
                cond, then_act, else_act = nested_conditional
                goal = Goal(
                    description=then_act,
                    index=i,
                    depends_on=[i - 1] if i > 0 else [],
                    goal_type=GoalType.CONDITIONAL,
                    condition=Condition(check=cond),
                    is_blocking=False,  # Conditionals shouldn't block the entire sequence
                )
                if else_act:
                    goal.else_goal = Goal(
                        description=else_act,
                        index=i,  # Same index, alternative path
                        goal_type=GoalType.ACTION,
                        is_blocking=False,
                    )
            else:
                # For multi-goal sequences, make goals non-blocking by default
                # This allows the sequence to continue even if individual goals fail
                # User can still see which goals succeeded/failed in the summary
                is_blocking = len(goal_texts) == 1  # Only block if it's a single goal
                goal = Goal(
                    description=goal_text.strip(),
                    index=i,
                    depends_on=[i - 1] if i > 0 else [],
                    is_blocking=is_blocking,
                )
            goal_objects.append(goal)

        logger.info(f"Parsed {len(goal_objects)} goals from prompt")
        for g in goal_objects:
            type_str = f" [{g.goal_type.value}]" if g.goal_type != GoalType.ACTION else ""
            logger.debug(f"  Goal {g.index + 1}{type_str}: {g.description[:50]}...")

        return GoalSequence(
            original_prompt=prompt,
            goals=goal_objects
        )

    def _split_into_goals(self, prompt: str) -> List[str]:
        """Split prompt into individual goal strings.

        BULLETPROOF SPLITTING - works regardless of formatting:
        0. Split by "Go to X" pattern (most common, handles bad formatting)
        1. Split by numbered list pattern (1. X 2. Y 3. Z)
        2. Split by explicit sequence connectors (then, after that, next, etc.)
        3. Split by ". Go to " pattern (sentence boundary + action verb)
        4. Split comma-separated tasks that each have action verbs
        5. Split "and" between distinct actions

        Optimized for 100-300+ goals:
        - Uses pre-compiled regex patterns
        - Enforces MAX_GOALS limit
        - Early exit if goal limit reached
        """
        # BULLETPROOF SPLIT: Split by "Go to" occurrences (handles any formatting)
        # Pattern: "Go to X" where X continues until next "Go to" or "." or end
        go_to_pattern = re.compile(r'(Go\s*to\s+[^.]+?)(?=\.?\s*Go\s*to\b|$)', re.IGNORECASE | re.DOTALL)
        go_to_matches = go_to_pattern.findall(prompt)
        if len(go_to_matches) >= 2:
            goals = []
            for match in go_to_matches:
                text = match.strip().rstrip('.')
                if text and len(text) > 5:
                    goals.append(text)
            if len(goals) >= 2:
                logger.debug(f"Split by 'Go to' pattern: found {len(goals)} goals")
                return goals[:MAX_GOALS]

        # First, check for numbered list pattern: "1. Go to X 2. Go to Y 3. Go to Z"
        # This is the most explicit multi-task format
        numbered_list_pattern = re.compile(r'(\d+)\.\s+([^.]+?)(?=\s+\d+\.|$)', re.IGNORECASE | re.DOTALL)
        numbered_matches = numbered_list_pattern.findall(prompt)
        if len(numbered_matches) >= 2:  # At least 2 numbered items
            goals = []
            for num, text in numbered_matches:
                text = text.strip()
                if text and len(text) > 5:
                    goals.append(text)
            if goals:
                logger.debug(f"Split by numbered list pattern: found {len(goals)} goals")
                return goals[:MAX_GOALS]

        # Second, check for sentence boundary + action verb pattern (". Go to ", ". Navigate to ", etc.)
        # This handles prompts like: "Go to X. Go to Y. Go to Z." or "Search X. Open Y. Visit Z."
        if self._sentence_action_pattern.search(prompt):
            # Use a simpler approach: split and re-add the action verb to each part
            # First, replace ". <ActionVerb> " with a unique marker + the action verb
            marker = "<<<GOAL_SPLIT>>>"

            def repl(match):
                """Replacement function that preserves the action verb."""
                action_verb = match.group(1)  # The captured action verb
                return marker + action_verb + " "

            marked_prompt = self._sentence_action_pattern.sub(repl, prompt)

            # Split by marker
            parts = marked_prompt.split(marker)

            # Clean and collect chunks
            chunks = []
            for part in parts:
                part = part.strip().rstrip('.')
                if part and len(part) > 5:
                    chunks.append(part)

            # Return if we successfully split
            if len(chunks) > 1:
                logger.debug(f"Split by sentence + action verb pattern: found {len(chunks)} goals")
                return chunks[:MAX_GOALS]

        # Third, check for sentence boundary + platform name pattern (". Reddit ", ". LinkedIn ", etc.)
        # This handles prompts like: "FB Ads Library search X. Reddit search Y. LinkedIn search Z."
        if self._sentence_platform_pattern.search(prompt):
            marker = "<<<GOAL_SPLIT>>>"

            def repl_platform(match):
                """Replacement function that preserves the platform name."""
                platform_name = match.group(1)  # The captured platform name
                return marker + platform_name

            marked_prompt = self._sentence_platform_pattern.sub(repl_platform, prompt)

            # Split by marker
            parts = marked_prompt.split(marker)

            # Clean and collect chunks - normalize whitespace
            chunks = []
            for part in parts:
                # Normalize multiple spaces to single space, strip, and remove trailing period
                part = ' '.join(part.split()).strip().rstrip('.')
                if part and len(part) > 5:
                    chunks.append(part)

            # Return if we successfully split
            if len(chunks) > 1:
                logger.debug(f"Split by sentence + platform name pattern: found {len(chunks)} goals")
                return chunks[:MAX_GOALS]

        # Fall back to original splitting logic
        # Split by explicit sequence connectors (use pre-compiled pattern)
        chunks = self._sequence_regex.split(prompt)

        # Filter out connectors and collect chunks
        intermediate_chunks = []
        current = ""
        for chunk in chunks:
            chunk = chunk.strip()
            if not chunk:
                continue

            # Check if this is a connector (use pre-compiled patterns)
            is_connector = any(
                re.match(p, chunk, re.IGNORECASE)
                for p in self.SEQUENCE_CONNECTORS
            )

            if is_connector:
                if current:
                    intermediate_chunks.append(current.strip())
                    current = ""
            else:
                current = chunk if not current else current + " " + chunk

        if current:
            intermediate_chunks.append(current.strip())

        # Now process each chunk to split comma-separated or "and"-separated tasks
        all_goals = []

        for chunk in intermediate_chunks:
            # Early exit if we've hit the goal limit
            if len(all_goals) >= MAX_GOALS:
                logger.warning(f"Goal limit ({MAX_GOALS}) reached, truncating remaining goals")
                break

            # Check if chunk has multiple action verbs (indicating multiple tasks)
            chunk_lower = chunk.lower()

            # Count action verbs (simple check, no full regex scan)
            verb_count = sum(1 for v in self.ACTION_VERBS if f' {v} ' in f' {chunk_lower} ' or chunk_lower.startswith(v))

            # If we have multiple distinct action verbs, try to split
            if verb_count >= 2:
                # Try splitting by ", " followed by action verb (use pre-compiled)
                sub_parts = self._comma_split_regex.split(chunk)

                if len(sub_parts) > 1:
                    for part in sub_parts:
                        part = part.strip()
                        if part and len(all_goals) < MAX_GOALS:
                            # Also split by " and " between actions (use pre-compiled)
                            and_parts = self._split_by_and(part)
                            all_goals.extend(and_parts[:MAX_GOALS - len(all_goals)])
                else:
                    # Try splitting by " and " between actions
                    and_parts = self._split_by_and(chunk)
                    all_goals.extend(and_parts[:MAX_GOALS - len(all_goals)])
            else:
                # Single task or no clear split point
                all_goals.append(chunk)

        # Clean up goals (use pre-compiled pattern)
        cleaned_goals = []
        for goal in all_goals:
            if len(cleaned_goals) >= MAX_GOALS:
                break
            # Remove leading conjunctions (use pre-compiled)
            goal = self._leading_conjunction_regex.sub('', goal).strip()
            if goal and len(goal) > 5:  # Skip very short fragments
                cleaned_goals.append(goal)

        if len(cleaned_goals) >= MAX_GOALS:
            logger.warning(f"Prompt resulted in {MAX_GOALS}+ goals, truncated to {MAX_GOALS}")

        return cleaned_goals if cleaned_goals else [prompt]

    def _split_by_and(self, text: str) -> List[str]:
        """Split text by 'and' when it separates distinct actions.

        Uses pre-compiled regex for efficiency.
        """
        parts = self._and_split_regex.split(text)
        return [p.strip() for p in parts if p.strip()]

    def advance(self, sequence: GoalSequence, success: bool, result: Optional[str] = None, error: Optional[str] = None) -> bool:
        """
        Mark current goal as complete/failed and advance to next.
        Also updates page state for context passing between goals.

        Returns True if there are more goals to execute.

        Optimized: Invalidates sequence cache when status changes.
        """
        current = sequence.current_goal
        if not current:
            return False

        # Update page state with result from this goal (already bounded in update_state)
        sequence.update_state(result or error or '', current.description)

        if success:
            current.status = GoalStatus.COMPLETED
            current.result = result  # Result is auto-bounded by Goal.result setter
            sequence.current_index += 1
            # Invalidate cache since status changed
            sequence._invalidate_cache()
        else:
            current.retries += 1
            if current.retries >= current.max_retries:
                current.status = GoalStatus.FAILED
                current.error = error[:MAX_RESULT_LENGTH] if error else None
                # Invalidate cache since status changed
                sequence._invalidate_cache()
                if current.is_blocking:
                    # Mark remaining goals as skipped
                    for goal in sequence.goals[sequence.current_index + 1:]:
                        goal.status = GoalStatus.SKIPPED
                    return False
                else:
                    sequence.current_index += 1

        return sequence.current_index < len(sequence.goals)

    def evaluate_condition(self, sequence: GoalSequence, goal: Goal) -> bool:
        """
        Evaluate a conditional goal's condition against current page state.

        Returns True if the condition is met, False otherwise.
        """
        if not goal.condition:
            return True  # No condition means always execute

        return goal.condition.matches(sequence.page_state)

    def get_goal_to_execute(self, sequence: GoalSequence) -> Optional[Goal]:
        """
        Get the next goal to execute, handling conditionals.

        For conditional goals, evaluates the condition and may return
        the else_goal instead if condition is not met.
        """
        current = sequence.current_goal
        if not current:
            return None

        # Handle conditional goals
        if current.goal_type == GoalType.CONDITIONAL and current.condition:
            if self.evaluate_condition(sequence, current):
                logger.debug(f"Condition '{current.condition.check}' evaluated TRUE - executing main goal")
                return current
            elif current.else_goal:
                logger.debug(f"Condition '{current.condition.check}' evaluated FALSE - executing else goal")
                return current.else_goal
            else:
                logger.debug(f"Condition '{current.condition.check}' evaluated FALSE - no else goal, skipping")
                current.status = GoalStatus.SKIPPED
                sequence.current_index += 1
                return self.get_goal_to_execute(sequence)  # Recurse to next goal

        return current


# Global instance
_sequencer = GoalSequencer()


def parse_goals(prompt: str) -> GoalSequence:
    """Parse a prompt into a goal sequence."""
    return _sequencer.parse(prompt)


def is_multi_goal(prompt: str) -> bool:
    """Check if prompt has multiple goals."""
    return _sequencer.is_complex_prompt(prompt)


def advance_goal(sequence: GoalSequence, success: bool, result: str = None, error: str = None) -> bool:
    """Advance to next goal in sequence."""
    return _sequencer.advance(sequence, success, result, error)


def get_next_goal(sequence: GoalSequence) -> Optional[Goal]:
    """Get the next goal to execute, handling conditionals."""
    return _sequencer.get_goal_to_execute(sequence)


def evaluate_condition(sequence: GoalSequence, goal: Goal) -> bool:
    """Evaluate a conditional goal's condition."""
    return _sequencer.evaluate_condition(sequence, goal)
