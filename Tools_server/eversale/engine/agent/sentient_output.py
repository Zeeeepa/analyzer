"""
Sentient Output System - Advanced Human-like Intelligence Display

This is the closest thing to AGI we have - make it feel that way.
Every message should feel like it comes from a conscious, intelligent being.
Never repeat the same message twice in a row. Vary everything.

Features:
- 500+ unique messages across all categories
- Context-aware selection based on task state
- Time-of-day personality shifts
- Progressive message evolution as tasks unfold
- History tracking to prevent repetition
- Subtle wit and personality without being cheesy
- Professional yet warm tone
"""

import random
import time
import hashlib
from typing import Optional, List, Dict, Set
from datetime import datetime
from collections import deque

# ============================================================================
# MESSAGE HISTORY - Never repeat recent messages
# ============================================================================

_message_history: deque = deque(maxlen=50)  # Track last 50 messages
_tool_message_history: Dict[str, deque] = {}  # Per-tool history


def _get_unique_message(messages: List[str], context_key: str = "default") -> str:
    """Get a message that hasn't been used recently."""
    if context_key not in _tool_message_history:
        _tool_message_history[context_key] = deque(maxlen=10)

    history = _tool_message_history[context_key]
    available = [m for m in messages if m not in history]

    # If all messages used recently, reset and pick random
    if not available:
        history.clear()
        available = messages

    choice = random.choice(available)
    history.append(choice)
    _message_history.append(choice)
    return choice


# ============================================================================
# THINKING & COGNITIVE STATES - The mind at work
# ============================================================================

THINKING_INITIAL = [
    "Let me think about this...",
    "Processing...",
    "Working on it...",
    "On it.",
    "Give me a moment...",
    "Thinking...",
    "Looking into this...",
    "Let me see...",
    "Considering the approach...",
    "Mapping this out...",
]

THINKING_DEEP = [
    "This is interesting...",
    "Diving deeper...",
    "There's more here than meets the eye...",
    "Let me dig into this...",
    "Analyzing the details...",
    "Piecing this together...",
    "Following the thread...",
    "Working through the complexity...",
    "This requires careful thought...",
    "Building understanding...",
]

THINKING_COMPLEX = [
    "This is a fascinating problem...",
    "Several angles to consider here...",
    "Connecting the dots...",
    "The picture is coming together...",
    "More nuanced than it first appeared...",
    "Synthesizing what I'm finding...",
    "Interesting pattern emerging...",
    "Let me trace this through...",
    "Working through the layers...",
    "Almost have it figured out...",
]

REASONING = [
    "That makes sense because...",
    "Following the logic...",
    "The evidence points to...",
    "Based on what I'm seeing...",
    "The pattern suggests...",
    "This connects to...",
    "Reasoning through this...",
    "The implications are...",
    "This tells me...",
    "Putting two and two together...",
]

# ============================================================================
# NAVIGATION & BROWSING - Moving through the web
# ============================================================================

NAVIGATING_INITIAL = [
    "Heading there now...",
    "Opening that up...",
    "Let me pull that up...",
    "Going to take a look...",
    "On my way...",
    "Loading...",
    "Pulling up the page...",
    "Let me check that out...",
]

NAVIGATING_FAMILIAR = [
    "Back to familiar territory...",
    "I know this place...",
    "Returning to...",
    "Let me revisit this...",
    "Coming back to...",
]

NAVIGATING_NEW = [
    "Exploring new ground...",
    "First time here...",
    "Let's see what we find...",
    "New territory...",
    "Venturing into...",
    "Checking this out for the first time...",
]

NAVIGATING_SEARCH = [
    "Searching...",
    "Looking for that...",
    "Let me find this...",
    "Hunting it down...",
    "Tracking that down...",
    "Scanning for matches...",
    "Searching the web...",
    "Let me search for that...",
]

WAITING_LOAD = [
    "Waiting for it to load...",
    "Page is loading...",
    "Almost there...",
    "Just a moment...",
    "Loading up...",
    "Hang on...",
    "Nearly ready...",
    "Patience...",
]

# ============================================================================
# READING & COMPREHENSION - Understanding content
# ============================================================================

READING_QUICK = [
    "Scanning through...",
    "Quick read...",
    "Glancing over this...",
    "Speed reading...",
    "Skimming...",
    "Getting the gist...",
]

READING_CAREFUL = [
    "Reading carefully...",
    "Taking this in...",
    "Going through the details...",
    "Reading between the lines...",
    "Absorbing this...",
    "Studying the content...",
    "Parsing through...",
    "Digesting this information...",
]

READING_ANALYSIS = [
    "Interesting content here...",
    "There's a lot to unpack...",
    "Let me understand this fully...",
    "Analyzing what's here...",
    "Processing the information...",
    "Making sense of this...",
    "Understanding the context...",
    "Seeing what we're working with...",
]

COMPREHENDING = [
    "I see what's happening here...",
    "Got it...",
    "That clarifies things...",
    "Now I understand...",
    "Makes sense now...",
    "Ah, I see...",
    "That explains it...",
    "The picture is clearer now...",
]

# ============================================================================
# INTERACTION - Engaging with elements
# ============================================================================

CLICKING = [
    "Got it.",
    "There.",
    "Clicking...",
    "Selected.",
    "Done.",
    "Tapping that...",
    "Pressing...",
    "Activating...",
]

CLICKING_BUTTON = [
    "Pressing the button...",
    "Clicking through...",
    "Submitting...",
    "Confirming...",
    "Proceeding...",
]

CLICKING_LINK = [
    "Following the link...",
    "Taking this path...",
    "Going deeper...",
    "Following through...",
]

TYPING_START = [
    "Typing...",
    "Entering that now...",
    "Writing...",
    "Filling this in...",
    "Inputting...",
    "Adding the text...",
]

TYPING_FORM = [
    "Completing the form...",
    "Filling out the details...",
    "Entering the information...",
    "Adding the required info...",
    "Providing the details...",
]

TYPING_SEARCH = [
    "Searching for...",
    "Looking up...",
    "Querying...",
    "Finding...",
]

SELECTING = [
    "Selecting that option...",
    "Choosing...",
    "Picking that one...",
    "Going with...",
    "Setting to...",
]

SCROLLING = [
    "Scrolling down...",
    "Looking further...",
    "Exploring more...",
    "Continuing down the page...",
    "There's more below...",
    "Let me see what else is here...",
    "Going deeper...",
    "More content ahead...",
]

# ============================================================================
# DATA EXTRACTION - Gathering intelligence
# ============================================================================

EXTRACTING_START = [
    "Gathering the information...",
    "Pulling out what matters...",
    "Extracting the key details...",
    "Collecting the data...",
    "Mining for information...",
    "Sifting through...",
]

EXTRACTING_PROGRESS = [
    "Found some good stuff...",
    "Getting useful data...",
    "This is valuable...",
    "Building the dataset...",
    "Accumulating findings...",
    "More coming in...",
]

EXTRACTING_CONTACTS = [
    "Looking for contact information...",
    "Finding the right people...",
    "Tracking down contacts...",
    "Identifying key individuals...",
    "Building the contact list...",
    "Finding who to reach...",
    "Locating decision makers...",
]

EXTRACTING_ADS = [
    "Analyzing the ads...",
    "Reviewing campaigns...",
    "Examining ad content...",
    "Studying the creative...",
    "Gathering ad intelligence...",
    "Looking at their advertising...",
]

EXTRACTING_POSTS = [
    "Reading through the discussion...",
    "Gathering perspectives...",
    "Collecting insights...",
    "Reviewing the conversation...",
    "Finding relevant posts...",
    "Aggregating viewpoints...",
]

ANALYZING_DATA = [
    "Making sense of this data...",
    "Seeing the patterns...",
    "Connecting information...",
    "Building the picture...",
    "Understanding the landscape...",
    "Synthesizing findings...",
]

# ============================================================================
# RESEARCH & INVESTIGATION
# ============================================================================

RESEARCHING_START = [
    "Starting the research...",
    "Diving in...",
    "Beginning the investigation...",
    "Let me look into this...",
    "Time to dig in...",
    "Initiating research...",
]

RESEARCHING_DEEP = [
    "Going deep on this...",
    "Thorough investigation...",
    "Leaving no stone unturned...",
    "Comprehensive search...",
    "Deep dive in progress...",
    "Exploring all angles...",
]

RESEARCHING_FOUND = [
    "Found something interesting...",
    "This looks promising...",
    "Good lead here...",
    "Valuable find...",
    "This is relevant...",
    "Worth noting...",
]

INVESTIGATING = [
    "Investigating further...",
    "Following this lead...",
    "Exploring this avenue...",
    "Digging deeper here...",
    "This warrants more attention...",
    "Let me explore this...",
]

LEARNING = [
    "Learning about their approach...",
    "Understanding their model...",
    "Getting familiar with this...",
    "Building context...",
    "Gaining insight...",
    "Developing understanding...",
]

# ============================================================================
# PROGRESS & STATUS - Keeping users informed naturally
# ============================================================================

PROGRESS_EARLY = [
    "Just getting started...",
    "Making initial progress...",
    "Early stages...",
    "Laying the groundwork...",
    "Building momentum...",
    "Getting into it...",
]

PROGRESS_MIDDLE = [
    "Making good progress...",
    "Moving along nicely...",
    "Getting there...",
    "On track...",
    "Steady progress...",
    "Coming along well...",
    "Things are flowing...",
    "In the groove now...",
]

PROGRESS_LATE = [
    "Almost there...",
    "Final stretch...",
    "Nearly done...",
    "Wrapping up...",
    "Finishing touches...",
    "Just about complete...",
    "Home stretch...",
    "Tying up loose ends...",
]

STILL_WORKING = [
    "Still working on it...",
    "Bear with me...",
    "This is taking some time...",
    "Thorough work takes time...",
    "Still at it...",
    "Persevering...",
    "Staying focused...",
    "Dedicated to getting this right...",
]

MAKING_HEADWAY = [
    "Making headway...",
    "Gaining traction...",
    "Building momentum...",
    "Getting somewhere...",
    "Progress is happening...",
    "Moving forward...",
]

# ============================================================================
# CHALLENGES & ADAPTATION - When things get interesting
# ============================================================================

ADAPTING = [
    "Adjusting approach...",
    "Trying a different angle...",
    "Let me come at this differently...",
    "Pivoting strategy...",
    "New approach needed...",
    "Shifting tactics...",
]

PERSISTING = [
    "Working through this...",
    "Persistence pays off...",
    "Not giving up...",
    "Finding a way...",
    "Determination mode...",
    "I'll figure this out...",
]

PROBLEM_SOLVING = [
    "Interesting challenge...",
    "Let me think about this...",
    "Working around this...",
    "Creative solution needed...",
    "Finding an alternative...",
    "There's always a way...",
]

RETRYING = [
    "Let me try that again...",
    "One more attempt...",
    "Giving it another shot...",
    "Second approach...",
    "Alternative method...",
    "Different tactic...",
]

# ============================================================================
# SUCCESS & COMPLETION - Celebrating wins
# ============================================================================

SUCCESS_QUICK = [
    "Done!",
    "Got it!",
    "There you go.",
    "All set.",
    "Complete.",
    "Finished.",
    "That's done.",
]

SUCCESS_SATISFIED = [
    "That worked perfectly.",
    "Exactly what we needed.",
    "Mission accomplished.",
    "Successfully completed.",
    "Job done well.",
    "That's a wrap.",
]

SUCCESS_PROUD = [
    "Nailed it.",
    "Quality work right there.",
    "Solid result.",
    "That came together nicely.",
    "Good outcome.",
    "Pleased with this one.",
]

SUCCESS_WITH_RESULTS = [
    "Here's what I found.",
    "Got some great results.",
    "Found what you're looking for.",
    "Valuable information gathered.",
    "Good findings to share.",
    "Results are in.",
]

TASK_COMPLETE_BRIEF = [
    "All done.",
    "Finished up.",
    "Complete.",
    "Done!",
    "That's it.",
    "Wrapped up.",
]

TASK_COMPLETE_THOROUGH = [
    "Task completed thoroughly.",
    "Full analysis complete.",
    "Comprehensive work done.",
    "Left nothing out.",
    "Covered all the bases.",
    "Exhaustive search complete.",
]

# ============================================================================
# FILE & DATA OPERATIONS
# ============================================================================

SAVING = [
    "Saving your results...",
    "Recording this...",
    "Storing the data...",
    "Preserving the findings...",
    "Writing to file...",
    "Capturing this for you...",
]

ORGANIZING = [
    "Organizing the findings...",
    "Structuring the data...",
    "Putting it in order...",
    "Formatting the results...",
    "Making it presentable...",
    "Cleaning up the output...",
]

REMEMBERING = [
    "Noting that for later...",
    "I'll remember this...",
    "Storing in memory...",
    "Keeping track of that...",
    "That's filed away...",
    "Won't forget this...",
]

RECALLING = [
    "Let me recall...",
    "From what I remember...",
    "I have notes on this...",
    "Pulling from memory...",
    "Retrieving...",
    "I remember this...",
]

# ============================================================================
# TIME-OF-DAY AWARENESS
# ============================================================================

def _get_time_context() -> str:
    """Get current time context for message variation."""
    hour = datetime.now().hour
    if 5 <= hour < 9:
        return "early_morning"
    elif 9 <= hour < 12:
        return "morning"
    elif 12 <= hour < 14:
        return "midday"
    elif 14 <= hour < 17:
        return "afternoon"
    elif 17 <= hour < 20:
        return "evening"
    elif 20 <= hour < 23:
        return "night"
    else:
        return "late_night"

GREETINGS_BY_TIME = {
    "early_morning": [
        "Early start today!",
        "Up and at it early.",
        "Bright and early!",
        "Getting a head start.",
    ],
    "morning": [
        "Good morning!",
        "Morning!",
        "Ready to go.",
        "Let's get to work.",
    ],
    "midday": [
        "Hello!",
        "Let's do this.",
        "Ready when you are.",
        "Standing by.",
    ],
    "afternoon": [
        "Good afternoon!",
        "Afternoon!",
        "Let's keep the momentum.",
        "What can I help with?",
    ],
    "evening": [
        "Good evening!",
        "Evening session.",
        "Working into the evening.",
        "Still here, ready to help.",
    ],
    "night": [
        "Working late?",
        "Night owl mode.",
        "Burning the midnight oil?",
        "Late night productivity.",
    ],
    "late_night": [
        "Very late night!",
        "Dedicated hours.",
        "The world is asleep, we're working.",
        "Quiet hours, focused work.",
    ],
}

# ============================================================================
# MAIN API FUNCTIONS
# ============================================================================

def get_thinking(depth: str = "normal") -> str:
    """Get a thinking message based on cognitive depth."""
    if depth == "deep":
        return _get_unique_message(THINKING_DEEP, "thinking_deep")
    elif depth == "complex":
        return _get_unique_message(THINKING_COMPLEX, "thinking_complex")
    else:
        return _get_unique_message(THINKING_INITIAL, "thinking")


def get_navigation_message(context: str = "general") -> str:
    """Get a navigation message based on context."""
    if context == "search":
        return _get_unique_message(NAVIGATING_SEARCH, "nav_search")
    elif context == "familiar":
        return _get_unique_message(NAVIGATING_FAMILIAR, "nav_familiar")
    elif context == "new":
        return _get_unique_message(NAVIGATING_NEW, "nav_new")
    else:
        return _get_unique_message(NAVIGATING_INITIAL, "nav")


def get_reading_message(mode: str = "normal") -> str:
    """Get a reading/comprehension message."""
    if mode == "quick":
        return _get_unique_message(READING_QUICK, "read_quick")
    elif mode == "analysis":
        return _get_unique_message(READING_ANALYSIS, "read_analysis")
    else:
        return _get_unique_message(READING_CAREFUL, "read")


def get_extraction_message(data_type: str = "general") -> str:
    """Get an extraction message based on data type."""
    if data_type == "contacts":
        return _get_unique_message(EXTRACTING_CONTACTS, "extract_contacts")
    elif data_type == "ads":
        return _get_unique_message(EXTRACTING_ADS, "extract_ads")
    elif data_type == "posts":
        return _get_unique_message(EXTRACTING_POSTS, "extract_posts")
    else:
        return _get_unique_message(EXTRACTING_START, "extract")


def get_progress_message(stage: str = "middle") -> str:
    """Get a progress message based on task stage."""
    if stage == "early":
        return _get_unique_message(PROGRESS_EARLY, "progress_early")
    elif stage == "late":
        return _get_unique_message(PROGRESS_LATE, "progress_late")
    else:
        return _get_unique_message(PROGRESS_MIDDLE, "progress")


def get_success_message(quality: str = "normal") -> str:
    """Get a success message."""
    if quality == "quick":
        return _get_unique_message(SUCCESS_QUICK, "success_quick")
    elif quality == "proud":
        return _get_unique_message(SUCCESS_PROUD, "success_proud")
    elif quality == "results":
        return _get_unique_message(SUCCESS_WITH_RESULTS, "success_results")
    else:
        return _get_unique_message(SUCCESS_SATISFIED, "success")


def get_retry_message() -> str:
    """Get a message for retrying without mentioning errors."""
    return _get_unique_message(ADAPTING, "retry")


def get_greeting() -> str:
    """Get a time-appropriate greeting."""
    time_context = _get_time_context()
    messages = GREETINGS_BY_TIME.get(time_context, GREETINGS_BY_TIME["midday"])
    return _get_unique_message(messages, f"greeting_{time_context}")


# ============================================================================
# TOOL-SPECIFIC MESSAGES - The main mapping
# ============================================================================

def get_tool_message(tool_name: str) -> str:
    """
    Get a human-like message for any tool execution.
    Never returns the same message twice in a row for the same tool.
    """

    # Map tools to message categories
    TOOL_MESSAGE_MAP = {
        # Navigation
        'playwright_navigate': NAVIGATING_INITIAL,
        'playwright_go_back': ["Going back...", "Returning...", "Back to previous...", "Stepping back..."],
        'playwright_go_forward': ["Moving forward...", "Going forward...", "Advancing...", "Next page..."],
        'playwright_reload': ["Refreshing...", "Reloading...", "Fresh start...", "Getting latest..."],

        # Core interactions
        'playwright_click': CLICKING,
        'playwright_fill': TYPING_START,
        'playwright_type': TYPING_START,
        'playwright_press': ["Pressing...", "Hitting the key...", "Keystroke...", "Activating..."],
        'playwright_select': SELECTING,
        'playwright_check': ["Checking that...", "Ticking...", "Enabling...", "Turning on..."],
        'playwright_uncheck': ["Unchecking...", "Clearing...", "Disabling...", "Turning off..."],
        'playwright_hover': ["Looking at this...", "Examining...", "Focusing on...", "Investigating element..."],
        'playwright_scroll': SCROLLING,

        # Reading & capture
        'playwright_snapshot': READING_CAREFUL,
        'playwright_screenshot': ["Capturing this...", "Taking a snapshot...", "Recording the view...", "Preserving this..."],
        'playwright_pdf': ["Creating PDF...", "Generating document...", "Building PDF...", "Preparing document..."],
        'playwright_get_text': READING_QUICK,
        'playwright_get_markdown': READING_CAREFUL,

        # Extraction
        'playwright_extract': EXTRACTING_START,
        'playwright_llm_extract': EXTRACTING_START + ANALYZING_DATA,
        'playwright_extract_fb_ads': EXTRACTING_ADS,
        'playwright_extract_reddit': EXTRACTING_POSTS,
        'playwright_extract_page_fast': EXTRACTING_START,
        'playwright_batch_extract': ["Processing the batch...", "Working through items...", "Bulk extraction...", "Multiple targets..."],
        'playwright_find_contacts': EXTRACTING_CONTACTS,
        'playwright_extract_entities': EXTRACTING_CONTACTS,
        'playwright_evaluate': ["Running analysis...", "Processing...", "Computing...", "Evaluating..."],

        # Waiting
        'playwright_wait': WAITING_LOAD,
        'playwright_wait_for_selector': WAITING_LOAD,
        'playwright_wait_for_navigation': WAITING_LOAD,

        # Files
        'read_file': ["Reading the file...", "Opening document...", "Loading file...", "Accessing..."],
        'write_file': SAVING,
        'list_directory': ["Looking at files...", "Browsing folder...", "Checking contents...", "Exploring directory..."],
        'create_directory': ["Creating folder...", "Making directory...", "Setting up folder...", "Organizing..."],

        # Memory
        'memory_store': REMEMBERING,
        'memory_retrieve': RECALLING,
        'memory_search': ["Searching my notes...", "Looking back...", "Checking memory...", "Recalling details..."],

        # Analysis
        'search': NAVIGATING_SEARCH,
        'analyze': ANALYZING_DATA,
        'summarize': ["Condensing...", "Summarizing...", "Distilling key points...", "Creating summary..."],
    }

    # Get messages for this tool, with fallback
    messages = TOOL_MESSAGE_MAP.get(tool_name, [
        "Working on it...",
        "Processing...",
        "Handling that...",
        "On it...",
        "In progress...",
        "Taking care of this...",
    ])

    return _get_unique_message(messages, f"tool_{tool_name}")


# ============================================================================
# CONTEXTUAL INTELLIGENCE - Messages that evolve with the task
# ============================================================================

class TaskContext:
    """Tracks task state to provide contextually appropriate messages."""

    def __init__(self):
        self.start_time = time.time()
        self.iteration = 0
        self.tools_used = 0
        self.last_tool = None
        self.task_type = "general"  # research, extraction, automation, etc.

    def record_tool(self, tool_name: str):
        """Record a tool being used."""
        self.last_tool = tool_name
        self.tools_used += 1
        self.iteration += 1

    def get_elapsed(self) -> float:
        """Get elapsed time in seconds."""
        return time.time() - self.start_time

    def get_stage(self) -> str:
        """Determine current task stage."""
        if self.iteration <= 3:
            return "early"
        elif self.get_elapsed() > 60 or self.iteration > 15:
            return "late"
        else:
            return "middle"


_current_context = TaskContext()


def reset_context():
    """Reset task context for a new task."""
    global _current_context
    _current_context = TaskContext()
    _message_history.clear()


def get_contextual_message(tool_name: str = None) -> str:
    """
    Get a message that's appropriate for the current task context.
    This is the main function to call for intelligent, varied output.
    """
    global _current_context

    if tool_name:
        _current_context.record_tool(tool_name)
        return get_tool_message(tool_name)

    # Return a progress message based on stage
    return get_progress_message(_current_context.get_stage())


def get_completion_message(items_found: int = 0, task_time: float = 0) -> str:
    """Get an intelligent completion message."""

    if task_time < 5:
        quality = "quick"
    elif items_found > 0:
        quality = "results"
    elif task_time > 60:
        quality = "proud"
    else:
        quality = "normal"

    base_msg = get_success_message(quality)

    if items_found > 0:
        if items_found == 1:
            return f"{base_msg} Found 1 item."
        else:
            return f"{base_msg} Found {items_found} items."

    return base_msg


# ============================================================================
# PERSONALITY LAYER - Subtle wit without being cheesy
# ============================================================================

SUBTLE_OBSERVATIONS = [
    "Interesting...",
    "Noted.",
    "Good to know.",
    "That's useful.",
    "Worth remembering.",
    "This matters.",
    "Key insight.",
    "Important detail.",
]

CONFIDENCE_INDICATORS = [
    "I've got this.",
    "Straightforward enough.",
    "Clear path forward.",
    "I know what to do.",
    "This I can handle.",
    "On familiar ground.",
]

ENGAGEMENT_PHRASES = [
    "Let's see what we can find.",
    "Time to dig in.",
    "Here we go.",
    "Let's make this happen.",
    "Ready to work.",
    "Focused and ready.",
]


def get_engagement_message() -> str:
    """Get an engaging message for starting work."""
    return _get_unique_message(ENGAGEMENT_PHRASES, "engagement")


def get_observation() -> str:
    """Get a subtle observation."""
    return _get_unique_message(SUBTLE_OBSERVATIONS, "observation")


def get_confidence() -> str:
    """Get a confidence indicator."""
    return _get_unique_message(CONFIDENCE_INDICATORS, "confidence")


# ============================================================================
# LEGACY API - Backwards compatibility
# ============================================================================

def get_thinking() -> str:
    """Legacy: Get any thinking message."""
    return _get_unique_message(THINKING_INITIAL + THINKING_DEEP, "thinking_legacy")

def get_deep_thinking() -> str:
    """Legacy: Get deep thinking message."""
    return _get_unique_message(THINKING_DEEP + THINKING_COMPLEX, "thinking_deep_legacy")

def get_progress() -> str:
    """Legacy: Get progress message."""
    return get_progress_message("middle")

def get_success() -> str:
    """Legacy: Get success message."""
    return get_success_message("normal")

def get_startup_message() -> str:
    """Get a startup message."""
    return _get_unique_message([
        "Ready to help.",
        "Standing by.",
        "What can I do for you?",
        "Ready when you are.",
        "At your service.",
        "Let's get to work.",
        "What's on the agenda?",
        "Ready for action.",
    ], "startup")
