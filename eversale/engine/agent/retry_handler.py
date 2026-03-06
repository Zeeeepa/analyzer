"""
Retry Handler with Error Correction

When tool calls fail, this analyzes the error and helps the LLM retry with corrections.
"""

from typing import Dict, Any, Optional
from loguru import logger


class RetryHandler:
    """
    Handles retries with intelligent error correction

    Tracks common failure modes and provides guidance to the LLM for retry attempts.
    """

    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
        self.retry_count = {}  # Track retries per tool
        self.error_patterns = self._load_error_patterns()

    def _load_error_patterns(self) -> Dict[str, Dict[str, Any]]:
        """Common error patterns and how to fix them"""

        return {
            "selector_not_found": {
                "keywords": ["selector", "not found", "no such element"],
                "guidance": """
The selector you used doesn't exist on the page.

Before retrying:
1. Use playwright_get_outline to see what elements are actually on the page
2. Look for similar elements with different selectors
3. Use a more general selector (e.g., 'button' instead of 'button.specific-class')
                """,
                "suggested_tool": "playwright_get_outline"
            },

            "navigation_failed": {
                "keywords": ["navigate", "failed to load", "timeout", "net::ERR"],
                "guidance": """
Navigation failed - the page didn't load.

Before retrying:
1. Check if the URL is correct
2. Try adding https:// if missing
3. The page might require login - check if you're logged in first
4. Try a simpler version of the URL (e.g., homepage first)
                """,
                "suggested_tool": "playwright_navigate"
            },

            "bad_json": {
                "keywords": ["json", "parse", "invalid", "syntax error"],
                "guidance": """
Your tool call had invalid JSON format.

CRITICAL FORMAT:
{"name": "tool_name", "arguments": {"param": "value"}}

Common mistakes:
- Extra text before the JSON
- Missing quotes around strings
- Trailing commas
- Using single quotes instead of double quotes

Example CORRECT format:
{"name": "playwright_navigate", "arguments": {"url": "https://example.com"}}
                """,
                "suggested_tool": None
            },

            "wrong_tool": {
                "keywords": ["unknown tool", "not available", "doesn't exist"],
                "guidance": """
The tool name you used doesn't exist.

Available tools:
- playwright_navigate (NOT navigate, goto, open)
- playwright_click (NOT click, press)
- playwright_fill (NOT type, enter, input)
- playwright_evaluate (NOT run_js, execute)
- save_contact (NOT add_contact, create_contact)
- get_contact (NOT find_contact, search_contact)

Use EXACT tool names.
                """,
                "suggested_tool": None
            },

            "missing_params": {
                "keywords": ["missing", "required", "parameter", "argument"],
                "guidance": """
You're missing a required parameter.

Check the tool definition for required params.
For example:
- playwright_navigate requires 'url'
- playwright_click requires 'selector'
- save_contact requires 'name' and 'company'
                """,
                "suggested_tool": None
            },

            "login_required": {
                "keywords": ["login", "sign in", "authenticate", "session"],
                "guidance": """
This page requires login but you're not logged in.

Options:
1. Use your browser profile with saved sessions (check config.yaml)
2. Navigate to the login page first
3. Use credentials from environment variables
4. Check if the page works without login
                """,
                "suggested_tool": "playwright_navigate"
            },

            "rate_limited": {
                "keywords": ["rate limit", "too many requests", "blocked", "captcha"],
                "guidance": """
You've been rate limited or blocked.

Solutions:
1. Add a delay before retrying (wait 10-30 seconds)
2. Use a different search query
3. Try a different approach to get the same data
4. Check if CAPTCHA appeared (can't automate CAPTCHAs)
                """,
                "suggested_tool": None
            }
        }

    def should_retry(self, tool_name: str, error: str) -> bool:
        """Determine if we should retry this tool call"""

        # Get retry count for this tool
        count = self.retry_count.get(tool_name, 0)

        if count >= self.max_retries:
            logger.warning(f"Max retries ({self.max_retries}) reached for {tool_name}")
            return False

        # Don't retry certain errors
        non_retryable = [
            "captcha",
            "account suspended",
            "permanently blocked"
        ]

        error_lower = error.lower()

        if any(keyword in error_lower for keyword in non_retryable):
            logger.info(f"Non-retryable error for {tool_name}: {error[:100]}")
            return False

        return True

    def get_retry_guidance(self, tool_name: str, error: str, last_response: str) -> str:
        """
        Generate guidance for the LLM to help it retry successfully

        Args:
            tool_name: The tool that failed
            error: The error message
            last_response: The LLM's last response (for context)

        Returns:
            Guidance message to prepend to the next LLM call
        """

        # Increment retry count
        self.retry_count[tool_name] = self.retry_count.get(tool_name, 0) + 1

        retry_num = self.retry_count[tool_name]

        # Match error pattern
        error_type = self._match_error_pattern(error)

        if error_type:
            pattern = self.error_patterns[error_type]
            guidance = pattern["guidance"]
            suggested_tool = pattern.get("suggested_tool")

            retry_message = f"""
RETRY {retry_num}/{self.max_retries}: The previous tool call failed.

Error: {error}

{guidance}

{'Suggested next step: Use ' + suggested_tool if suggested_tool else 'Try again with the corrections above.'}

Think step-by-step about what went wrong and how to fix it.
            """

        else:
            # Generic retry guidance
            retry_message = f"""
RETRY {retry_num}/{self.max_retries}: The previous tool call failed.

Error: {error}

Please analyze what went wrong and try a different approach.

Suggestions:
1. Double-check the tool name is correct
2. Verify all required parameters are provided
3. Make sure the format is valid JSON
4. Consider using a simpler approach
            """

        logger.info(f"Retry guidance generated for {tool_name} (attempt {retry_num})")

        return retry_message

    def _match_error_pattern(self, error: str) -> Optional[str]:
        """Match error to known pattern"""

        error_lower = error.lower()

        for error_type, pattern in self.error_patterns.items():
            keywords = pattern["keywords"]

            if any(keyword in error_lower for keyword in keywords):
                return error_type

        return None

    def reset_retries(self, tool_name: str):
        """Reset retry counter for a tool (after success)"""

        if tool_name in self.retry_count:
            del self.retry_count[tool_name]

    def get_retry_stats(self) -> Dict[str, int]:
        """Get retry statistics"""
        return dict(self.retry_count)


# Error correction prompts for specific failure modes

ERROR_CORRECTION_PROMPTS = {
    "bad_json": """
CRITICAL: Your last response had invalid JSON.

CORRECT FORMAT (use EXACTLY this structure):
{"name": "playwright_navigate", "arguments": {"url": "https://example.com"}}

Common mistakes to AVOID:
❌ I'll navigate to the site. {"name": "playwright_navigate", ...}
❌ {'name': 'playwright_navigate', ...}  # Single quotes
❌ {name: "playwright_navigate", ...}  # Missing quotes
❌ {"name": "playwright_navigate", "arguments": {"url": "https://example.com",}}  # Trailing comma

✓ {"name": "playwright_navigate", "arguments": {"url": "https://example.com"}}

Respond with ONLY the JSON, nothing else.
    """,

    "wrong_selector": """
The selector you used doesn't exist on the page.

Before retrying, use playwright_get_outline to see what's actually on the page.

Then use a selector from the outline results.

Example:
Step 1: {"name": "playwright_get_outline", "arguments": {}}
[See results...]
Step 2: {"name": "playwright_click", "arguments": {"selector": "button#login"}}  # Use actual selector from outline
    """,

    "hallucinated_data": """
WARNING: It looks like you're making up data instead of actually extracting it.

You MUST use tools to get real data from the page.

DO NOT:
❌ Assume company names
❌ Make up email addresses
❌ Invent contact information

DO:
✓ Use playwright_evaluate to extract actual text from the page
✓ Use playwright_get_outline to see what data is available
✓ If data isn't on the page, say "Data not found" - don't make it up
    """
}


def get_error_correction_prompt(error_type: str) -> str:
    """Get error correction prompt for specific error type"""

    return ERROR_CORRECTION_PROMPTS.get(error_type, "")
