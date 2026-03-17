"""
Smart Agent - Zero-Config Autonomous Entry Point

This is the seamless wrapper that makes everything "just work".
User types `eversale` and talks in natural language - that's it.

Key Features:
1. AUTO-DETECTS forever mode from natural language
2. AUTO-CONNECTS Playwright MCP (no user config)
3. AUTO-HANDLES questions ("need more info? I'll ask")
4. AUTO-SAVES results to sensible locations
5. LEARNS from interactions for next time

Example user interactions:
- "scrape leads from facebook ads" -> runs once, saves CSV
- "monitor my inbox forever" -> runs forever mode
- "check competitor prices every hour" -> forever + scheduling
- "do this 1000 times" -> long-running mode
- "research stripe" -> one-shot research
"""

import re
import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from loguru import logger


# =============================================================================
# SMART INTENT DETECTION
# =============================================================================

@dataclass
class SmartIntent:
    """Detected intent from natural language."""
    is_forever: bool = False           # Should run forever?
    is_long_running: bool = False      # Many iterations?
    requested_iterations: int = 0      # How many times?
    poll_interval_minutes: int = 0     # Check every X minutes?
    needs_browser: bool = True         # Needs web automation?
    needs_question: bool = False       # Should ask user something first?
    question: str = ""                 # What to ask
    auto_save: bool = True             # Auto-save results?
    output_format: str = "csv"         # csv, json, md, txt
    category: str = "general"          # leads, research, monitor, scrape, etc.


def detect_smart_intent(prompt: str) -> SmartIntent:
    """
    Analyze prompt and detect what the user REALLY wants.

    Returns SmartIntent with all the context needed for smart execution.
    """
    intent = SmartIntent()
    prompt_lower = prompt.lower()

    # ===================
    # FOREVER DETECTION
    # ===================
    forever_patterns = [
        r'\bforever\b',
        r'\bdont stop\b', r"\bdon't stop\b",
        r'\bnever stop\b',
        r'\bkeep going\b', r'\bkeep running\b',
        r'\bcontinuously\b', r'\bcontinuous\b',
        r'\binfinite\b', r'\binfinitely\b',
        r'\buntil i say\b', r'\buntil i tell\b',
        r'\brun indefinitely\b',
        r'\bworld record\b', r'\bendurance\b', r'\bmarathon\b',
        r'\bmonitor\b.*\balways\b', r'\bwatch\b.*\balways\b',
        r'\bcheck\b.*\bevery\b',
    ]

    for pattern in forever_patterns:
        if re.search(pattern, prompt_lower):
            intent.is_forever = True
            break

    # ===================
    # LONG-RUNNING DETECTION
    # ===================

    # "do this 1000 times", "run 500 iterations"
    iteration_match = re.search(
        r'(\d+)\s*(?:times?|iterations?|steps?|cycles?|loops?)',
        prompt_lower
    )
    if iteration_match:
        intent.requested_iterations = int(iteration_match.group(1))
        if intent.requested_iterations >= 10:
            intent.is_long_running = True

    # "do this X times" patterns
    repeat_patterns = [
        r'loop\s+(\d+)',
        r'repeat\s+(\d+)',
        r'(\d+)\s+times\s+(?:in\s+a\s+)?loop',
    ]
    for pattern in repeat_patterns:
        match = re.search(pattern, prompt_lower)
        if match:
            intent.requested_iterations = int(match.group(1))
            intent.is_long_running = True
            break

    # ===================
    # SCHEDULE/POLL DETECTION
    # ===================

    # "every 5 minutes", "every hour", "hourly"
    interval_patterns = [
        (r'every\s+(\d+)\s*min', lambda m: int(m.group(1))),
        (r'every\s+(\d+)\s*hour', lambda m: int(m.group(1)) * 60),
        (r'every\s+hour', lambda m: 60),
        (r'hourly', lambda m: 60),
        (r'every\s+(\d+)\s*sec', lambda m: max(1, int(m.group(1)) // 60)),
        (r'every\s+day', lambda m: 1440),
        (r'daily', lambda m: 1440),
    ]

    for pattern, extractor in interval_patterns:
        match = re.search(pattern, prompt_lower)
        if match:
            intent.poll_interval_minutes = extractor(match)
            intent.is_forever = True  # Scheduled = forever
            break

    # ===================
    # CATEGORY DETECTION
    # ===================

    category_patterns = [
        (r'\b(?:leads?|prospects?|contacts?)\b', 'leads'),
        (r'\b(?:research|investigate|find out|learn about)\b', 'research'),
        (r'\b(?:monitor|watch|track|observe)\b', 'monitor'),
        (r'\b(?:scrape|extract|pull|grab|collect)\b', 'scrape'),
        (r'\b(?:compare|versus|vs|comparison)\b', 'compare'),
        (r'\b(?:email|inbox|mail)\b', 'email'),
        (r'\b(?:price|pricing|cost)\b', 'pricing'),
        (r'\b(?:stock|inventory|availability)\b', 'inventory'),
    ]

    for pattern, category in category_patterns:
        if re.search(pattern, prompt_lower):
            intent.category = category
            break

    # ===================
    # OUTPUT FORMAT DETECTION
    # ===================

    if re.search(r'\b(?:csv|spreadsheet|excel)\b', prompt_lower):
        intent.output_format = 'csv'
    elif re.search(r'\bjson\b', prompt_lower):
        intent.output_format = 'json'
    elif re.search(r'\b(?:markdown|md|report)\b', prompt_lower):
        intent.output_format = 'md'
    elif re.search(r'\b(?:txt|text)\b', prompt_lower):
        intent.output_format = 'txt'

    # ===================
    # BROWSER NEEDED?
    # ===================

    no_browser_patterns = [
        r'\b(?:calculate|compute|math|formula)\b',
        r'\b(?:summarize|summary|tldr)\b.*\b(?:this|the|my)\b',
        r'\b(?:explain|describe)\b',
    ]

    intent.needs_browser = True
    for pattern in no_browser_patterns:
        if re.search(pattern, prompt_lower):
            intent.needs_browser = False
            break

    # Web-related always needs browser
    web_patterns = [
        r'\b(?:website|webpage|site|url|http|www)\b',
        r'\b(?:scrape|browse|navigate|click|open)\b',
        r'\b(?:facebook|google|linkedin|twitter|amazon)\b',
    ]
    for pattern in web_patterns:
        if re.search(pattern, prompt_lower):
            intent.needs_browser = True
            break

    # ===================
    # QUESTION DETECTION
    # ===================

    # Does the prompt need clarification?
    vague_patterns = [
        (r'^(?:help|do something|idk|not sure)', "What would you like me to help with?"),
        (r'^(?:research|find|get)\s*$', "What would you like me to research?"),
        (r'^(?:scrape|monitor)\s*$', "Which website should I work with?"),
    ]

    for pattern, question in vague_patterns:
        if re.search(pattern, prompt_lower):
            intent.needs_question = True
            intent.question = question
            break

    return intent


# =============================================================================
# SMART PROMPT ENHANCEMENT
# =============================================================================

def enhance_prompt_for_mode(prompt: str, intent: SmartIntent) -> str:
    """
    Enhance the prompt with context for the detected mode.

    Adds instructions to the prompt that help the LLM understand the mode.
    """
    enhancements = []

    if intent.is_forever:
        enhancements.append("""
[FOREVER MODE ACTIVE]
- This is a CONTINUOUS task. Do NOT stop after completing once.
- Run in a loop: CHECK -> PROCESS -> SAVE -> SLEEP -> REPEAT
- Never say "task complete" - continue until interrupted
- Save results incrementally after each cycle
- If no new items found, sleep and check again
- Handle errors gracefully and continue
""")

    if intent.is_long_running:
        enhancements.append(f"""
[LONG-RUNNING MODE: {intent.requested_iterations} iterations]
- Execute the task {intent.requested_iterations} times
- Track progress and report every 10% complete
- Save results incrementally
- Handle failures gracefully and continue
""")

    if intent.poll_interval_minutes > 0:
        enhancements.append(f"""
[SCHEDULED MODE: every {intent.poll_interval_minutes} minutes]
- Wait {intent.poll_interval_minutes} minutes between each check
- Only process NEW items (deduplicate from previous runs)
- Report changes since last check
""")

    if intent.category == 'leads':
        enhancements.append("""
[LEADS MODE]
- Extract: company name, website, email (if available), category
- Save to CSV with headers: name, website, email, category, source, extracted_at
- Deduplicate by website/name combo
""")

    if intent.category == 'monitor':
        enhancements.append("""
[MONITOR MODE]
- Establish a baseline on first run
- On subsequent runs, detect CHANGES from baseline
- Alert only when something changes
- Update baseline after detecting change
""")

    if enhancements:
        enhanced = prompt + "\n\n" + "\n".join(enhancements)
        return enhanced

    return prompt


# =============================================================================
# SMART OUTPUT HANDLING
# =============================================================================

def get_smart_output_path(intent: SmartIntent, prompt: str) -> Path:
    """
    Generate a sensible output path based on intent and prompt.
    """
    from datetime import datetime

    # Base output directory
    output_dir = Path.home() / 'Desktop' / 'AI_Agent_Output'
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate name from prompt
    name_words = re.findall(r'\b\w+\b', prompt.lower())[:3]
    name = '_'.join(name_words) if name_words else 'output'
    name = re.sub(r'[^\w_]', '', name)

    # Add timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    # Extension based on format
    ext = intent.output_format

    filename = f"{name}_{timestamp}.{ext}"
    return output_dir / filename


# =============================================================================
# PLAYWRIGHT AUTO-CONNECT
# =============================================================================

async def ensure_playwright_connected(mcp_client) -> bool:
    """
    Ensure Playwright MCP is connected and working.

    Handles:
    - First-time connection
    - Reconnection after crash
    - Browser installation if needed
    """
    try:
        # Check if already connected
        if hasattr(mcp_client, 'servers') and 'playwright' in mcp_client.servers:
            client = mcp_client.servers['playwright'].get('client')
            if client:
                # Test connection with a simple call
                try:
                    await asyncio.wait_for(
                        client.call_tool('browser_snapshot', {}),
                        timeout=5.0
                    )
                    return True
                except:
                    pass  # Need to reconnect

        # Connect all servers (includes Playwright)
        await mcp_client.connect_all_servers()

        # Verify Playwright is there
        if 'playwright' in mcp_client.servers:
            logger.info("[SMART] Playwright connected successfully")
            return True

        logger.warning("[SMART] Playwright not available - web automation limited")
        return False

    except Exception as e:
        logger.error(f"[SMART] Playwright connection failed: {e}")
        return False


# =============================================================================
# SMART AGENT CLASS
# =============================================================================

class SmartAgent:
    """
    The smart wrapper that makes everything "just work".

    Usage:
        agent = SmartAgent()
        await agent.run("scrape leads from facebook ads forever")
    """

    def __init__(self, config: dict = None, mcp_client = None):
        self.config = config or {}
        self.mcp = mcp_client
        self.brain = None
        self.intent: Optional[SmartIntent] = None

        # Import Brain lazily
        self._brain_factory = None

    async def initialize(self):
        """Initialize the agent with MCP and Brain."""
        from agent.brain_enhanced_v2 import create_enhanced_brain
        from agent.mcp_client import MCPClient

        if self.mcp is None:
            self.mcp = MCPClient()

        # Connect MCP (includes Playwright)
        await ensure_playwright_connected(self.mcp)

        # Create Brain
        self.brain = create_enhanced_brain(self.config, self.mcp)

        logger.info("[SMART] Agent initialized")

    async def run(self, prompt: str) -> str:
        """
        Run a task with smart detection and handling.

        This is the main entry point - handles everything automatically.
        """
        # Detect intent from prompt
        self.intent = detect_smart_intent(prompt)

        logger.info(f"[SMART] Detected intent: forever={self.intent.is_forever}, "
                   f"long_running={self.intent.is_long_running}, "
                   f"iterations={self.intent.requested_iterations}, "
                   f"category={self.intent.category}")

        # Need to ask a question first?
        if self.intent.needs_question:
            return f"I need more information: {self.intent.question}"

        # Ensure initialized
        if self.brain is None:
            await self.initialize()

        # Enhance prompt for detected mode
        enhanced_prompt = enhance_prompt_for_mode(prompt, self.intent)

        # Configure Brain for the mode
        if self.intent.is_forever or self.intent.is_long_running:
            # Boost max iterations for forever/long-running
            max_iters = self.intent.requested_iterations if self.intent.requested_iterations > 0 else 10000
            self.brain.max_iterations = max(max_iters, 10000)

            # Relax loop detection for intentional repetition
            if hasattr(self.brain, 'resilience') and self.brain.resilience:
                self.brain.resilience.loop_detector.max_identical_actions = 20

        # Run the task
        if self.intent.is_forever:
            return await self._run_forever(enhanced_prompt)
        else:
            return await self._run_once(enhanced_prompt)

    async def _run_once(self, prompt: str) -> str:
        """Run a one-shot task."""
        result = await self.brain.run(prompt)

        # Auto-save if configured
        if self.intent.auto_save and result:
            self._maybe_save_result(result)

        return result

    async def _run_forever(self, prompt: str) -> str:
        """Run a forever task."""
        from agent.ui import ui

        cycle = 0
        results = []
        poll_seconds = (self.intent.poll_interval_minutes or 5) * 60

        ui.show_status(f"Forever mode started. Press Ctrl+C to stop.", "info")

        try:
            while True:
                cycle += 1
                logger.info(f"[SMART] Forever cycle {cycle}")

                # Run one iteration
                try:
                    result = await self.brain.run(prompt)
                    results.append(result)

                    # Save incrementally
                    self._save_incremental_result(result, cycle)

                    # Show progress
                    ui.console.print(f"[dim]Cycle {cycle} complete. Sleeping {poll_seconds}s...[/dim]")

                except Exception as e:
                    logger.error(f"[SMART] Cycle {cycle} error: {e}")
                    # Continue despite errors

                # Sleep between cycles
                await asyncio.sleep(poll_seconds)

        except KeyboardInterrupt:
            ui.show_status(f"Forever mode stopped after {cycle} cycles.", "warning")

        return f"Completed {cycle} cycles. Results saved."

    def _maybe_save_result(self, result: str):
        """Save result to file if it looks like structured data."""
        if not result:
            return

        # Check if result looks like data
        if any(x in result.lower() for x in ['saved to', 'output:', 'results:']):
            return  # Already saved by Brain

        # For leads/scrape results, save automatically
        if self.intent.category in ['leads', 'scrape'] and len(result) > 100:
            output_path = get_smart_output_path(self.intent, result[:50])
            try:
                output_path.write_text(result)
                logger.info(f"[SMART] Auto-saved to {output_path}")
            except:
                pass

    def _save_incremental_result(self, result: str, cycle: int):
        """Save incremental result for forever mode."""
        if not result:
            return

        output_dir = Path.home() / 'Desktop' / 'AI_Agent_Output' / 'forever_runs'
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"cycle_{cycle}_{timestamp}.txt"

        try:
            (output_dir / filename).write_text(result)
        except:
            pass


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def is_forever_prompt(prompt: str) -> bool:
    """Quick check if prompt should run forever."""
    intent = detect_smart_intent(prompt)
    return intent.is_forever or intent.is_long_running


def get_recommended_iterations(prompt: str) -> int:
    """Get recommended max iterations for a prompt."""
    intent = detect_smart_intent(prompt)

    if intent.is_forever:
        return 100000  # Effectively infinite

    if intent.requested_iterations > 0:
        return intent.requested_iterations + 100  # Buffer

    if intent.is_long_running:
        return 10000

    return 50  # Default


async def run_smart(prompt: str, config: dict = None) -> str:
    """
    Convenience function to run a prompt with smart detection.

    Usage:
        result = await run_smart("scrape leads from facebook forever")
    """
    agent = SmartAgent(config)
    return await agent.run(prompt)


# =============================================================================
# INTEGRATION WITH RUN_ULTIMATE.PY
# =============================================================================

def wrap_brain_with_smart_detection(brain, prompt: str):
    """
    Wrap existing Brain instance with smart detection.

    Called from run_ultimate.py before running a prompt.
    """
    intent = detect_smart_intent(prompt)

    # Apply smart settings to brain
    if intent.is_forever or intent.is_long_running:
        max_iters = intent.requested_iterations if intent.requested_iterations > 0 else 10000
        brain.max_iterations = max(max_iters, brain.max_iterations)

        # Relax loop detection
        if hasattr(brain, 'resilience') and brain.resilience:
            brain.resilience.loop_detector.max_identical_actions = 20
            brain.resilience.loop_detector.max_failures_consecutive = 10

    return intent, enhance_prompt_for_mode(prompt, intent)


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    # Test intent detection
    test_prompts = [
        "scrape leads from facebook ads",
        "monitor my inbox forever and respond to urgent emails",
        "check competitor prices every hour",
        "do this 1000 times in a loop",
        "research stripe and save to json",
        "watch amazon for price drops",
        "find leads for saas companies continuously",
        "help",
    ]

    print("\n=== Smart Intent Detection ===\n")

    for prompt in test_prompts:
        intent = detect_smart_intent(prompt)
        print(f">>> {prompt}")
        print(f"    forever={intent.is_forever}, long={intent.is_long_running}, "
              f"iters={intent.requested_iterations}, poll={intent.poll_interval_minutes}min, "
              f"cat={intent.category}, fmt={intent.output_format}")
        if intent.needs_question:
            print(f"    QUESTION: {intent.question}")
        print()
