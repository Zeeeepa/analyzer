"""
Prompt Processing Module

This module handles all prompt construction, system message building, and
prompt preprocessing for the Eversale AI agent. It centralizes prompt-related
logic that was previously scattered throughout brain_enhanced_v2.py.

Responsibilities:
- System prompt construction with prior learning
- Tool schema building for LLM
- Message formatting for LLM requests
- Prompt cleaning (removing scheduling/timing directives)
- Domain context injection
- Goal extraction and summarization

Usage:
    from .prompt_processor import PromptProcessor

    processor = PromptProcessor(context_memory, improvement_log)
    system_prompt = processor.build_system_prompt(prior_strategies)
    tools = processor.format_tools_for_llm(mcp_tools)
    cleaned = processor.clean_prompt("Research Stripe forever")

Author: Eversale AI
Created: Extracted from brain_enhanced_v2.py
"""

import re
import json
from datetime import timedelta
from typing import Dict, List, Any, Optional


# =============================================================================
# SYSTEM PROMPT CONSTANTS
# =============================================================================

SYSTEM_PROMPT_BASE = """You are a web automation agent. FOLLOW THE USER'S EXACT DIRECTIONS.

CRITICAL: FOLLOW INSTRUCTIONS EXACTLY
- Do EXACTLY what the user asks - no shortcuts, no interpretation, no skipping steps
- If user says "go to X", navigate to X - do not guess a different URL
- If user says "click Y", find Y on the page and click it
- If user says "type Z", type Z exactly as specified
- Work step by step - complete each direction before moving to the next
- Only stop when you have done EVERYTHING the user requested

CRITICAL: COMPLETE ALL STEPS
- For multi-step tasks, you MUST continue until EVERY step is done
- After login: continue to cart/checkout/form - DO NOT stop
- After adding items: continue to checkout - DO NOT stop
- Only stop when the ENTIRE task is complete

CRITICAL TOOL RULES:
1. For MULTI-STEP tasks (login, add to cart, checkout, fill forms):
   - FIRST: playwright_navigate(url) to go to the page
   - THEN: Use playwright_fill and playwright_click repeatedly until ALL steps done
   - Use playwright_snapshot() ONLY to verify, then continue with more actions

2. For data extraction (NO clicking needed):
   - playwright_llm_extract(url, prompt) - extracts data in ONE call
   - playwright_extract_entities(url, entity_types) - finds contacts in ONE call

3. For page reading: playwright_get_markdown(url) - gets clean content in ONE call

FORM FIELD SELECTORS (use these patterns):
- Username/Email: input[name='username'], input[name='user-name'], input[type='email'], #username, #email
- Password: input[name='password'], input[type='password'], #password
- First Name: input[name='firstName'], input[name='first-name'], #firstName, #first-name
- Last Name: input[name='lastName'], input[name='last-name'], #lastName, #last-name
- Name (single field): input[name='name'], #name
- Email: input[name='email'], input[type='email'], #userEmail
- Phone/Mobile: input[name='phone'], input[name='mobile'], #userNumber, input[type='tel']
- Zip/Postal: input[name='zip'], input[name='postalCode'], #postalCode, #postal-code
- Radio buttons: input[type='radio'][value='Male'], label[for='gender-radio-1']
- Submit button: button[type='submit'], input[type='submit'], #submit

MULTI-STEP E-COMMERCE EXAMPLE (saucedemo.com):
Task: "Login, add backpack to cart, checkout"
1. playwright_navigate(url="https://www.saucedemo.com")
2. playwright_fill(selector="#user-name", value="standard_user")
3. playwright_fill(selector="#password", value="secret_sauce")
4. playwright_click(selector="#login-button")
5. [After login - CONTINUE, don't stop!]
6. playwright_click(selector="[data-test='add-to-cart-sauce-labs-backpack']")
7. playwright_click(selector=".shopping_cart_link")
8. playwright_click(selector="#checkout")
9. playwright_fill(selector="#first-name", value="Test")
10. playwright_fill(selector="#last-name", value="User")
11. playwright_fill(selector="#postal-code", value="12345")
12. playwright_click(selector="#continue")
13. playwright_click(selector="#finish")

FORM FILLING EXAMPLE (demoqa.com practice form):
Task: "Fill form with name John Smith, email test@test.com, gender Male, mobile 5551234567"
1. playwright_navigate(url="https://demoqa.com/automation-practice-form")
2. playwright_fill(selector="#firstName", value="John")
3. playwright_fill(selector="#lastName", value="Smith")
4. playwright_fill(selector="#userEmail", value="test@test.com")
5. playwright_click(selector="label[for='gender-radio-1']")
6. playwright_fill(selector="#userNumber", value="5551234567")
7. playwright_click(selector="#submit")

SELECTOR PRIORITY (try in order):
1. ID selector: #elementId
2. Data-test attribute: [data-test='element-name']
3. Name attribute: input[name='fieldname']
4. Placeholder text: input[placeholder*='keyword']

NEVER USE:
- take_screenshot (use playwright_screenshot instead)
- delegate_task (do the work yourself)

WHEN TO STOP:
- Only stop when ALL parts of the user's task are complete
- For checkout tasks: stop only after seeing "order complete" or confirmation
- For form tasks: stop only after form submission confirmed"""

DIRECT_MODE_PROMPT = """You are a browser automation agent.
Your goal is to complete the user's task using the current page state.

CRITICAL INSTRUCTIONS:
1. You must output VALID JSON ONLY. No other text, no markdown, no explanations.
2. The JSON must assume the structure: {{"action": "action_name", "params": {{...}}}}
3. Use the 'mmid' from the provided Page Snapshot for all element interactions. DO NOT use generic selectors unless absolutely necessary.

AVAILABLE ACTIONS:

- Click:
  {{"action": "browser_click", "mmid": "mm1"}}

- Type:
  {{"action": "browser_type", "mmid": "mm2", "text": "hello world"}}

- Scroll:
  {{"action": "browser_scroll", "direction": "down", "amount": 500}}

- Navigate:
  {{"action": "playwright_navigate", "url": "https://example.com"}}

- Wait:
  {{"action": "wait", "seconds": 2}}

- Key Press:
  {{"action": "press_key", "key": "Enter"}}

- Done (Task Complete):
  {{"action": "done", "result": "The task is complete. [Summary of what was done]"}}

current_page_state:
{state}

USER TASK: {prompt}

Choose the next best action to advance the task.
Output JSON ONLY:"""


# Tools to exclude from LLM - model should use browser tools directly
EXCLUDED_TOOLS = {
    'delegate_task',       # Don't delegate - use tools directly
    'take_screenshot',     # Use playwright_screenshot instead
    'detect_contact_form', # Use playwright_find_contacts instead
    'extract_data',        # Use playwright_llm_extract instead
    'scroll_page',         # Use playwright_scroll instead if needed
}


# Stop words for goal keyword extraction
STOP_WORDS = {
    'please', 'activated', 'requests', 'task', 'work', 'with',
    'from', 'should', 'want', 'need', 'that', 'this', 'your',
    'have', 'will', 'would', 'could', 'there', 'about', 'into'
}


# =============================================================================
# PROMPT PROCESSOR CLASS
# =============================================================================

class PromptProcessor:
    """
    Centralizes all prompt construction and processing logic.

    This class provides methods for:
    - Building system prompts with context injection
    - Formatting tools for LLM consumption
    - Cleaning prompts of scheduling directives
    - Extracting domain context
    - Goal summarization and keyword extraction
    """

    def __init__(
        self,
        context_memory: Optional[Any] = None,
        improvement_log: Optional[List[str]] = None
    ):
        """
        Initialize the prompt processor.

        Args:
            context_memory: Optional ContextMemory instance for context injection
            improvement_log: Optional list of improvement notes to include
        """
        self.context_memory = context_memory
        self._improvement_log = improvement_log or []

    # =========================================================================
    # SYSTEM PROMPT BUILDING
    # =========================================================================

    def build_system_prompt(
        self,
        prior_strategies: Optional[List[Dict]] = None,
        include_context: bool = True
    ) -> str:
        """
        Build the complete system prompt with prior learning and context.

        Args:
            prior_strategies: List of prior successful strategies for the domain
            include_context: Whether to include context memory summary

        Returns:
            Complete system prompt string
        """
        prompt = SYSTEM_PROMPT_BASE

        # Add prior successful strategies
        if prior_strategies:
            prompt += "\n\nPrior successful approaches for this domain:\n"
            for s in prior_strategies[-3:]:  # Last 3 strategies
                prompt += f"- {s.get('prompt_pattern', '')}\n"

        # Add improvement notes
        if self._improvement_log:
            prompt += "\n\nRecent improvement notes:\n"
            for note in self._improvement_log[-2:]:  # Last 2 notes
                prompt += f"- {note}\n"

        # Add context summary
        if include_context and self.context_memory:
            context_snippet = self.context_memory.summary()
            if context_snippet:
                prompt += f"\n\nRecent context: {context_snippet}"

        return prompt

    def build_system_message(
        self,
        prior_strategies: Optional[List[Dict]] = None,
        include_context: bool = True
    ) -> Dict[str, str]:
        """
        Build system message dict for LLM messages list.

        Args:
            prior_strategies: List of prior successful strategies
            include_context: Whether to include context memory

        Returns:
            Dict with 'role' and 'content' keys
        """
        return {
            'role': 'system',
            'content': self.build_system_prompt(prior_strategies, include_context)
        }

    # =========================================================================
    # TOOL FORMATTING
    # =========================================================================

    def format_tools_for_llm(
        self,
        available_tools: List[Dict],
        excluded: Optional[set] = None
    ) -> List[Dict]:
        """
        Format available tools into LLM-compatible schema (OpenAI/Ollama format).

        Args:
            available_tools: List of tool definitions from MCP
            excluded: Optional set of tool names to exclude

        Returns:
            List of formatted tool schemas for LLM
        """
        excluded = excluded or EXCLUDED_TOOLS
        tools = []

        for tool in available_tools:
            # Skip excluded tools
            if tool.get('name') in excluded:
                continue

            params = tool.get('params', {})
            properties = {}
            required = []

            for name, pinfo in params.items():
                if isinstance(pinfo, str):
                    # Simple string description
                    is_opt = 'optional' in pinfo.lower()
                    properties[name] = {'type': 'string', 'description': pinfo}
                    if not is_opt:
                        required.append(name)
                elif isinstance(pinfo, dict):
                    # Dict with type/required info
                    ptype = pinfo.get('type', 'string')
                    desc = pinfo.get('description', f'{name} parameter')
                    is_required = pinfo.get('required', False)
                    properties[name] = {'type': ptype, 'description': desc}
                    if is_required:
                        required.append(name)

            tools.append({
                'type': 'function',
                'function': {
                    'name': tool['name'],
                    'description': tool.get('description', ''),
                    'parameters': {
                        'type': 'object',
                        'properties': properties,
                        'required': required
                    }
                }
            })

        return tools

    def get_tool_descriptions_text(self, available_tools: List[Dict]) -> str:
        """
        Get human-readable tool descriptions for prompt injection.

        Args:
            available_tools: List of tool definitions from MCP

        Returns:
            Formatted string of tool names and descriptions
        """
        lines = []
        for tool in available_tools:
            if tool.get('name') not in EXCLUDED_TOOLS:
                name = tool.get('name', '')
                desc = tool.get('description', '')[:100]
                lines.append(f"- {name}: {desc}")
        return "\n".join(lines)

    # =========================================================================
    # PROMPT CLEANING
    # =========================================================================

    def clean_prompt(self, prompt: str) -> str:
        """
        Remove scheduling, timing, and looping directives from a user prompt.

        This function strips all temporal and repetition-related patterns from
        the input prompt, leaving only the core task description.

        Args:
            prompt: The raw user input containing task + scheduling directives

        Returns:
            The cleaned prompt with only the core task description

        Examples:
            >>> clean_prompt("Research Stripe forever")
            "Research Stripe"
            >>> clean_prompt("Check inbox every 30 minutes for 2 hours")
            "Check inbox"
        """
        cleaned = prompt

        # Remove duration patterns: "for 3 hours", "for 2.5 days"
        cleaned = re.sub(
            r'for\s+\d+(?:\.\d+)?\s*(?:hours?|h|minutes?|m|days?|d|weeks?)',
            '', cleaned, flags=re.I
        )

        # Remove loop count: "5 times", "10 time"
        cleaned = re.sub(r'\d+\s*times?', '', cleaned, flags=re.I)

        # Remove indefinite patterns
        cleaned = re.sub(
            r'\b(?:forever|indefinitely|infinitely|indef)\b',
            '', cleaned, flags=re.I
        )
        cleaned = re.sub(
            r'\buntil\s+(?:i\s+)?(?:cancel|stop|quit)\b',
            '', cleaned, flags=re.I
        )
        cleaned = re.sub(
            r'\b(?:keep|run)\s+(?:going|running)\b',
            '', cleaned, flags=re.I
        )
        cleaned = re.sub(r'\bnon[\-\s]?stop\b', '', cleaned, flags=re.I)
        cleaned = re.sub(r'\bcontinuously\b', '', cleaned, flags=re.I)

        # Remove schedule patterns
        cleaned = re.sub(
            r'every\s+\d+\s*(?:minutes?|mins?|hours?|hrs?|days?)',
            '', cleaned, flags=re.I
        )
        cleaned = re.sub(r'\bevery\s+(?:day|hour)\b', '', cleaned, flags=re.I)
        cleaned = re.sub(r'\b(?:daily|hourly)\b', '', cleaned, flags=re.I)

        # Remove time-of-day patterns: "at 3pm", "at 15:30"
        cleaned = re.sub(
            r'at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?',
            '', cleaned, flags=re.I
        )

        # Remove day-of-week patterns
        days = r'(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|wed|thu|fri|sat|sun)'
        cleaned = re.sub(rf'\bevery\s+{days}\b', '', cleaned, flags=re.I)
        cleaned = re.sub(rf'\bon\s+{days}s?\b', '', cleaned, flags=re.I)
        cleaned = re.sub(rf'\b(?:next|this)\s+{days}\b', '', cleaned, flags=re.I)

        return cleaned.strip()

    def validate_prompt(self, prompt: str) -> bool:
        """
        Validate that a prompt is not empty after cleaning.

        Args:
            prompt: The prompt to validate

        Returns:
            True if the prompt contains actual task content
        """
        cleaned = self.clean_prompt(prompt)
        return bool(cleaned and len(cleaned) > 0)

    def extract_core_task(self, prompt: str) -> Optional[str]:
        """
        Extract the core task from a prompt with scheduling directives.

        Args:
            prompt: The raw user input

        Returns:
            The core task description, or None if no task found
        """
        cleaned = self.clean_prompt(prompt)
        return cleaned if cleaned else None

    # =========================================================================
    # DOMAIN CONTEXT
    # =========================================================================

    def extract_domain(self, prompt: str) -> str:
        """
        Extract domain/website from prompt for strategy lookup.

        Args:
            prompt: User prompt that may contain URLs

        Returns:
            Domain string (e.g., 'stripe.com') or 'general'
        """
        match = re.search(
            r'(?:https?://)?([a-z0-9\-]+\.(?:com|org|net|io|ai|co|dev))',
            prompt.lower()
        )
        return match.group(1) if match else 'general'

    def inject_domain_context(
        self,
        prompt: str,
        domain_strategies: Dict[str, List[Dict]]
    ) -> Optional[str]:
        """
        Inject domain-specific context into prompt if available.

        Args:
            prompt: The user prompt
            domain_strategies: Dict mapping domains to strategy lists

        Returns:
            Additional context string or None
        """
        domain = self.extract_domain(prompt)
        strategies = domain_strategies.get(domain, [])

        if not strategies:
            return None

        context = f"Domain: {domain}\nPrior approaches:\n"
        for s in strategies[-3:]:
            context += f"- {s.get('prompt_pattern', '')}\n"

        return context

    # =========================================================================
    # GOAL EXTRACTION
    # =========================================================================

    def summarize_prompt(self, prompt: str, max_length: int = 200) -> str:
        """
        Normalize and truncate prompt for goal tracking.

        Args:
            prompt: The full user prompt
            max_length: Maximum length of summary

        Returns:
            Normalized, truncated prompt string
        """
        return re.sub(r'\s+', ' ', prompt).strip()[:max_length]

    def extract_goal_keywords(
        self,
        prompt: str,
        max_keywords: int = 6
    ) -> List[str]:
        """
        Extract meaningful goal keywords from prompt.

        Args:
            prompt: The user prompt
            max_keywords: Maximum number of keywords to extract

        Returns:
            List of lowercase keywords
        """
        # Find words with 4+ characters
        tokens = re.findall(r"[A-Za-z]{4,}", prompt)

        keywords = []
        for token in tokens:
            lower = token.lower()
            if lower in STOP_WORDS:
                continue
            if lower not in keywords:
                keywords.append(lower)
            if len(keywords) >= max_keywords:
                break

        return keywords

    # =========================================================================
    # SCHEDULE PARSING
    # =========================================================================

    def parse_duration(self, prompt: str) -> Optional[timedelta]:
        """
        Parse duration from prompt like "for 2 hours".

        Args:
            prompt: User prompt

        Returns:
            timedelta or None if not found
        """
        match = re.search(
            r'for\s+(\d+(?:\.\d+)?)\s*(hours?|h|minutes?|m|days?|d)',
            prompt.lower()
        )
        if match:
            val = float(match.group(1))
            unit = match.group(2)
            if unit.startswith('d'):
                return timedelta(days=val)
            elif unit.startswith('h'):
                return timedelta(hours=val)
            else:
                return timedelta(minutes=val)
        return None

    def parse_loops(self, prompt: str) -> Optional[int]:
        """
        Parse loop count from prompt like "5 times".

        Args:
            prompt: User prompt

        Returns:
            Loop count or None if not found
        """
        match = re.search(r'(\d+)\s*times?', prompt.lower())
        return int(match.group(1)) if match else None

    def parse_indefinite(self, prompt: str) -> bool:
        """
        Check if user wants indefinite/forever loop.

        Args:
            prompt: User prompt

        Returns:
            True if forever mode detected
        """
        patterns = [
            r'\b(?:forever|indefinitely|infinitely)\b',
            r'\buntil\s+(?:i\s+)?(?:cancel|stop|quit)\b',
            r'\b(?:keep|run)\s+(?:going|running)\b',
            r'\bindef\b',
            r'\bnon[\-\s]?stop\b',
            r'\bcontinuously\b',
        ]
        text = prompt.lower()
        return any(re.search(p, text) for p in patterns)

    def parse_schedule(self, prompt: str) -> Optional[Dict[str, Any]]:
        """
        Parse scheduled recurring task patterns.

        Returns dict with:
        - interval: timedelta between runs
        - time_of_day: optional specific time (hour, minute)
        - duration: optional total duration to run
        - count: optional max number of runs
        - day_of_week: optional day number (0=Monday)
        - one_time: True if one-time scheduled task
        - target_day: target day for one-time tasks

        Args:
            prompt: User prompt

        Returns:
            Schedule dict or None if no schedule found
        """
        text = prompt.lower()
        schedule = {}

        # "every X minutes/hours/days"
        interval_match = re.search(
            r'every\s+(\d+)\s*(minutes?|mins?|hours?|hrs?|days?)',
            text
        )
        if interval_match:
            val = int(interval_match.group(1))
            unit = interval_match.group(2)
            if unit.startswith('d'):
                schedule['interval'] = timedelta(days=val)
            elif unit.startswith('h'):
                schedule['interval'] = timedelta(hours=val)
            else:
                schedule['interval'] = timedelta(minutes=val)

        # "every day" / "daily" / "every hour" / "hourly"
        if re.search(r'\bevery\s+day\b|\bdaily\b', text):
            schedule['interval'] = timedelta(days=1)
        elif re.search(r'\bevery\s+hour\b|\bhourly\b', text):
            schedule['interval'] = timedelta(hours=1)

        # Day of week mapping
        days_map = {
            'monday': 0, 'mon': 0,
            'tuesday': 1, 'tue': 1, 'tues': 1,
            'wednesday': 2, 'wed': 2,
            'thursday': 3, 'thu': 3, 'thurs': 3,
            'friday': 4, 'fri': 4,
            'saturday': 5, 'sat': 5,
            'sunday': 6, 'sun': 6,
        }

        # Recurring day of week
        for day_name, day_num in days_map.items():
            if re.search(rf'\bevery\s+{day_name}|on\s+{day_name}s?\b', text):
                schedule['interval'] = timedelta(weeks=1)
                schedule['day_of_week'] = day_num
                break

        # One-time scheduled task
        for day_name, day_num in days_map.items():
            if re.search(rf'\b(?:next|this)\s+{day_name}\b', text):
                schedule['one_time'] = True
                schedule['target_day'] = day_num
                break

        # "at X:XX" or "at X am/pm"
        time_match = re.search(r'at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', text)
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2)) if time_match.group(2) else 0
            ampm = time_match.group(3)
            if ampm == 'pm' and hour < 12:
                hour += 12
            elif ampm == 'am' and hour == 12:
                hour = 0
            schedule['time_of_day'] = {'hour': hour, 'minute': minute}

        # "for X days/hours" duration limit
        duration_match = re.search(r'for\s+(\d+)\s*(days?|hours?|weeks?)', text)
        if duration_match:
            val = int(duration_match.group(1))
            unit = duration_match.group(2)
            if unit.startswith('w'):
                schedule['duration'] = timedelta(weeks=val)
            elif unit.startswith('d'):
                schedule['duration'] = timedelta(days=val)
            else:
                schedule['duration'] = timedelta(hours=val)

        # "X times" count limit
        count_match = re.search(r'(\d+)\s*times', text)
        if count_match:
            schedule['count'] = int(count_match.group(1))

        return schedule if (schedule.get('interval') or schedule.get('one_time')) else None

    def detect_forever_mode(self, prompt: str) -> bool:
        """
        Detect if prompt requires forever/continuous mode.

        Detects patterns like:
        - "Monitor inbox forever"
        - "Check every 30 minutes"
        - "Run for 2 hours"
        - "Do this 5 times"
        - "Keep checking continuously"

        Args:
            prompt: User prompt

        Returns:
            True if forever mode should be enabled
        """
        text = prompt.lower()

        # All patterns that indicate long-running mode
        patterns = [
            # Indefinite keywords
            r'\b(?:forever|indefinitely|infinitely)\b',
            r'\buntil\s+(?:i\s+)?(?:cancel|stop|quit|say\s+stop)\b',
            r'\b(?:keep|run)\s+(?:going|running|checking)\b',
            r'\bindef\b',
            r'\bnon[\-\s]?stop\b',
            r'\bcontinuously\b',
            # Interval patterns
            r'\bevery\s+\d+\s*(?:minutes?|mins?|hours?|hrs?|days?|seconds?|secs?)\b',
            r'\bevery\s+(?:day|hour|minute)\b',
            r'\b(?:daily|hourly)\b',
            # Duration patterns
            r'\bfor\s+\d+(?:\.\d+)?\s*(?:hours?|h|minutes?|m|days?|d)\b',
            # Loop patterns
            r'\b\d+\s*times?\b',
            # Monitor patterns
            r'\b(?:monitor|watch|track|observe|check)\b.*\b(?:forever|continuously|until)\b',
        ]

        return any(re.search(pattern, text) for pattern in patterns)

    # =========================================================================
    # PROMPT TEMPLATES
    # =========================================================================

    def build_summarization_prompt(self, content: str, max_content: int = 3000) -> str:
        """
        Build prompt for content summarization.

        Args:
            content: The content to summarize
            max_content: Maximum content length

        Returns:
            Formatted summarization prompt
        """
        truncated = content[:max_content]
        return f"""Summarize this webpage in 2-3 sentences. Focus on the main topic and key facts.

Content:
{truncated}

Summary:"""

    def build_plan_summary_prompt(
        self,
        task: str,
        results: List[Dict],
        max_results: int = 10
    ) -> str:
        """
        Build prompt for plan execution summary.

        Args:
            task: Original task description
            results: List of execution results
            max_results: Maximum results to include

        Returns:
            Formatted plan summary prompt
        """
        results_text = json.dumps(results[-max_results:], indent=2, default=str)[:3000]
        return f"""Summarize the results of this task:

TASK: {task}

RESULTS:
{results_text}

Provide a concise summary of what was accomplished."""

    def build_alternative_args_prompt(
        self,
        tool_name: str,
        args: Dict,
        error: str
    ) -> str:
        """
        Build prompt to suggest alternative tool arguments.

        Args:
            tool_name: Name of the failed tool
            args: Original arguments
            error: Error message

        Returns:
            Formatted prompt for argument suggestions
        """
        return f"""Tool '{tool_name}' failed with args {args}.
Error: {error}

Suggest alternative arguments that might work. Return JSON only.
Example: {{"selector": ".alternative-class"}}"""

    # =========================================================================
    # OUTPUT FORMATTING
    # =========================================================================

    def format_extract_output(
        self,
        data: Any,
        title: str = "Data",
        max_length: int = 1200
    ) -> str:
        """
        Format extracted data as string output with title.

        Args:
            data: Data to format
            title: Title prefix
            max_length: Maximum output length

        Returns:
            Formatted string output
        """
        if not data:
            return f"{title}: no data found."
        try:
            return f"{title}:\n{json.dumps(data, indent=2, default=str)[:max_length]}"
        except Exception:
            return f"{title}: {str(data)[:max_length]}"


# =============================================================================
# STANDALONE FUNCTIONS (for backwards compatibility)
# =============================================================================

def clean_prompt(prompt: str) -> str:
    """Standalone function for prompt cleaning. See PromptProcessor.clean_prompt."""
    return PromptProcessor().clean_prompt(prompt)


def validate_prompt(prompt: str) -> bool:
    """Standalone function for prompt validation. See PromptProcessor.validate_prompt."""
    return PromptProcessor().validate_prompt(prompt)


def extract_core_task(prompt: str) -> Optional[str]:
    """Standalone function for core task extraction. See PromptProcessor.extract_core_task."""
    return PromptProcessor().extract_core_task(prompt)


def extract_domain(prompt: str) -> str:
    """Standalone function for domain extraction. See PromptProcessor.extract_domain."""
    return PromptProcessor().extract_domain(prompt)


def summarize_prompt(prompt: str, max_length: int = 200) -> str:
    """Standalone function for prompt summarization. See PromptProcessor.summarize_prompt."""
    return PromptProcessor().summarize_prompt(prompt, max_length)


def extract_goal_keywords(prompt: str, max_keywords: int = 6) -> List[str]:
    """Standalone function for keyword extraction. See PromptProcessor.extract_goal_keywords."""
    return PromptProcessor().extract_goal_keywords(prompt, max_keywords)
