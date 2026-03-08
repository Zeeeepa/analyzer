#!/usr/bin/env python3
"""
MCP-Style Agent Runner - Production Ready v2

Fixes:
1. Ultra-simple prompting - qwen3 outputs action directly
2. Non-headless mode - visible browser by default
3. Persistent sessions - ~/.eversale/browser-profile (isolated from normal Chrome)
4. Captcha handling - WAIT_HUMAN with auto-detection
5. Battle-tested stealth from mcp_tools.py

Usage:
    python run_mcp.py "Go to google.com and search for playwright"
    python run_mcp.py "Open FB Ads Library and search for booked meetings"
"""

import asyncio
import sys
import os
import re
import httpx
import base64
import random
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).parent))
from loguru import logger

# Paths - use consistent isolated profile name across all entry points
# IMPORTANT: This is an ISOLATED profile - we never use the user's real Chrome profile
# to prevent corruption, lock file issues, and "profile in use" errors
BROWSER_PROFILE = Path.home() / ".eversale" / "browser-profile"
BROWSER_PROFILE.mkdir(parents=True, exist_ok=True)
# Legacy alias for backward compatibility
CHROME_PROFILE = BROWSER_PROFILE

# License
LICENSE_KEY = ""
license_file = Path.home() / ".eversale" / "license.key"
if license_file.exists():
    LICENSE_KEY = license_file.read_text().strip()

# =============================================================================
# STEALTH CONFIG (from mcp_tools.py battle-tested patterns)
# =============================================================================

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
window.chrome = {runtime: {}};
"""

CAPTCHA_INDICATORS = ["g-recaptcha", "h-captcha", "captcha", "cf-browser-verification", "turnstile", "challenge"]

POPUP_SELECTORS = [
    'text="Accept"', 'text="Accept All"', 'text="Accept Cookies"',
    'text="OK"', 'text="Close"', 'text="Got it"', 'text="I Accept"',
    '[aria-label="Close"]', '[aria-label="Dismiss"]',
    'button:has-text("Accept")', '.cookie-accept', '#cookie-accept',
]

@dataclass
class Result:
    ok: bool
    msg: str
    data: Any = None


# =============================================================================
# SIMPLE LLM CALL - Direct action output
# =============================================================================

def extract_action_from_reasoning(reasoning: str, has_captcha: bool = False, check_done: bool = False, need_navigate: bool = False) -> str:
    """Extract action from qwen3 reasoning output (since qwen3 uses thinking mode)."""

    reasoning_lower = reasoning.lower()

    # If captcha and model mentions it
    if has_captcha and any(x in reasoning_lower for x in ["captcha", "verify", "human"]):
        return "WAIT_HUMAN: solve captcha"

    # PRIORITY 0: If check_done flag is set, look for DONE signals first
    if check_done:
        done_indicators = ["task is complete", "task is done", "we have completed", "already done",
                          "already on the", "successfully", "that's it", "nothing more", "no more",
                          "done:", "finished", "accomplished", "completed the task"]
        if any(x in reasoning_lower for x in done_indicators):
            return "DONE: task completed"

    # PRIORITY 0.5: If we need to navigate (on blank page), find URL first
    if need_navigate:
        # Look for any URL in reasoning
        m = re.search(r'(https?://[^\s"\'<>,]+)', reasoning)
        if m:
            return f'navigate(url="{m.group(1).rstrip(".")}")'
        # Look for domain names
        m = re.search(r'(?:go to|navigate to|visit)\s+([a-z0-9][-a-z0-9]*\.(?:com|org|net|io|co)[^\s,]*)', reasoning, re.I)
        if m:
            return f'navigate(url="https://{m.group(1)}")'
        # Extract domain from task mentioned in reasoning
        m = re.search(r'([a-z0-9][-a-z0-9]*\.(?:com|org|net|io|co|ycombinator\.com))', reasoning, re.I)
        if m:
            return f'navigate(url="https://{m.group(1)}")'

    # PRIORITY 1: Check for explicit tool calls first (these take precedence)
    # Check for navigate with URL
    m = re.search(r'navigate\s*\(\s*url\s*=\s*["\']([^"\']+)["\']', reasoning, re.I)
    if m:
        return f'navigate(url="{m.group(1)}")'

    # Check for click with selector
    m = re.search(r'click\s*\(\s*selector\s*=\s*["\']([^"\']+)["\']', reasoning, re.I)
    if m:
        return f'click(selector="{m.group(1)}")'

    # Check for type
    m = re.search(r'type\s*\(.*?selector\s*=\s*["\']([^"\']+)["\'].*?text\s*=\s*["\']([^"\']+)["\']', reasoning, re.I | re.DOTALL)
    if m:
        return f'type(selector="{m.group(1)}", text="{m.group(2)}")'

    # Check for press/enter
    m = re.search(r'press.*?(enter|tab|escape)', reasoning, re.I)
    if m:
        return f'press(key="{m.group(1).title()}")'

    # PRIORITY 2: Look for natural language action descriptions
    # Look for "click on X" or "click the X" (before DONE check)
    m = re.search(r'(?:should|need to|will|must|going to|let\'s|i\'ll)\s+click\s+(?:on\s+)?(?:the\s+)?["\']?([^"\',.!?\n]+)["\']?', reasoning, re.I)
    if m:
        text = m.group(1).strip()
        if 2 < len(text) < 30 and text.lower() not in ["it", "that", "this", "here", "there"]:
            return f'click(selector="text={text}")'

    # Look for "go to X" or "navigate to X"
    m = re.search(r'(?:should|need to|will|must|going to|let\'s)\s+(?:go|navigate)\s+to\s+(https?://[^\s"\'<>]+|[a-z0-9][-a-z0-9]*\.[a-z]{2,}[^\s"\'<>,!?]*)', reasoning, re.I)
    if m:
        url = m.group(1).rstrip('.')
        if not url.startswith("http"):
            url = "https://" + url
        return f'navigate(url="{url}")'

    # PRIORITY 3: Check for DONE only with strong signals
    # Must have explicit completion language AND not mention needing to do something
    strong_done = ["task is complete", "task has been completed", "successfully completed the task",
                   "finished the task", "task is done", "all done", "that completes"]
    if any(x in reasoning_lower for x in strong_done):
        # Make sure it's not saying "not done" or "need to"
        if not any(x in reasoning_lower for x in ["not done", "not complete", "need to", "should", "must", "will click", "will navigate"]):
            return "DONE: task completed"

    # PRIORITY 4: Fallbacks for natural language
    # Check for scroll
    if re.search(r'(?:should|need to|will|let\'s)\s+scroll', reasoning_lower):
        direction = "up" if "up" in reasoning_lower else "down"
        return f'scroll(direction="{direction}")'

    # Generic click pattern (weaker match)
    m = re.search(r'click\s+(?:on\s+)?(?:the\s+)?["\']([^"\']+)["\']', reasoning, re.I)
    if m:
        text = m.group(1).strip()
        if 2 < len(text) < 30:
            return f'click(selector="text={text}")'

    # Generic URL pattern
    m = re.search(r'(https?://[^\s"\'<>]+)', reasoning)
    if m and "about:blank" not in m.group(1):
        return f'navigate(url="{m.group(1)}")'

    # Look for domain names without protocol
    m = re.search(r'(?:navigate to|go to|visit)\s+([a-z0-9][-a-z0-9]*\.(?:com|org|net|io|co)[^\s,]*)', reasoning, re.I)
    if m:
        return f'navigate(url="https://{m.group(1)}")'

    # If reasoning mentions "done" or "complete" and we're checking completion
    if "check if" in reasoning_lower and ("done" in reasoning_lower or "complete" in reasoning_lower):
        # Model is evaluating completion - check its conclusion
        if any(x in reasoning_lower for x in ["yes", "is complete", "is done", "finished", "accomplished"]):
            return "DONE: task completed"

    return f"PARSE_FAILED: {reasoning[:80]}"


async def get_action(task: str, url: str, title: str, elements: List[str], history: List[str], has_captcha: bool) -> str:
    """Get next action from LLM."""

    # Format elements simply
    el_str = ", ".join(elements[:12]) if elements else "none"

    # Determine what stage we're at and give appropriate guidance
    if url == "about:blank" or not url.startswith("http"):
        # Need to navigate first
        stage_hint = "First, navigate to the website."
    elif len(history) > 1 and any("click" in h.lower() for h in history):
        # Already clicked something - check if we're done
        # Extract what was clicked from history
        clicked_items = [h for h in history if "click" in h.lower()]
        stage_hint = f"We already clicked: {clicked_items[-1] if clicked_items else 'something'}. If the task is complete, output DONE: [reason]. Only click more if task needs more steps."
    else:
        stage_hint = "Look at the elements and decide what to click."

    # Simple prompt with clear stage guidance
    prompt = f"""Task: {task}
URL: {url}
Elements: [{el_str}]
Steps done: {history[-3:] if history else 'none'}
{f'CAPTCHA DETECTED' if has_captcha else ''}

{stage_hint}

Reply with ONE of:
- navigate(url="https://...")
- click(selector="text=...")
- type(selector="...", text="...")
- DONE: [reason]
- WAIT_HUMAN: [reason]"""

            async with httpx.AsyncClient(timeout=60) as client:
                r = await client.post(
                    "https://irrpfq5xoh5dto-4174.proxy.runpod.net/v1/chat/completions",
                    headers={"Authorization": f"Bearer {LICENSE_KEY}", "Content-Type": "application/json"},
                    json={
                        "model": "0000/ui-tars-1.5-7b:latest",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.1,
                        "max_tokens": 1000  # Need enough for reasoning + action
                    }
                )
                msg = r.json().get("choices", [{}])[0].get("message", {})
        # qwen3 outputs to reasoning field in thinking mode
        reasoning = msg.get("reasoning", "") or msg.get("content", "")

        # Check if we should prioritize DONE detection
        check_done = len(history) > 1 and any("click" in h.lower() for h in history)

        # Check if we need to navigate (on blank page)
        need_navigate = url == "about:blank" or not url.startswith("http")

        # Extract action from reasoning
        return extract_action_from_reasoning(reasoning, has_captcha, check_done, need_navigate)


# =============================================================================
# BROWSER CLASS - With stealth and captcha handling
# =============================================================================

class Browser:
    def __init__(self, headless: bool = False):
        self.headless = headless
        self._pw = None
        self._ctx = None
        self._page = None

    async def launch(self) -> Result:
        try:
            try:
                from patchright.async_api import async_playwright
                lib = "patchright"
            except ImportError:
                from playwright.async_api import async_playwright
                lib = "playwright"

            self._pw = await async_playwright().start()

            args = [
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--no-first-run",
                "--disable-dev-shm-usage",
            ]

            self._ctx = await self._pw.chromium.launch_persistent_context(
                str(CHROME_PROFILE),
                headless=self.headless,
                args=args,
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
                locale="en-US",
                timezone_id="America/New_York",
            )

            self._page = self._ctx.pages[0] if self._ctx.pages else await self._ctx.new_page()
            await self._page.add_init_script(STEALTH_JS)

            return Result(True, f"Browser ready ({lib})")
        except Exception as e:
            return Result(False, str(e))

    async def close(self):
        if self._ctx:
            await self._ctx.close()
        if self._pw:
            await self._pw.stop()

    async def get_state(self) -> Dict:
        """Get page state with captcha detection."""
        try:
            url = self._page.url
            title = await self._page.title()

            # Get clickable elements (simplified)
            elements = await self._page.evaluate("""
                () => Array.from(document.querySelectorAll('a, button, input, [role="button"]'))
                    .filter(e => e.offsetParent !== null)
                    .slice(0, 30)
                    .map(e => e.innerText?.slice(0, 30)?.trim() || e.placeholder || e.getAttribute('aria-label') || e.id || '')
                    .filter(t => t.length > 0)
            """)

            # Check for captcha
            html = (await self._page.content()).lower()
            has_captcha = any(x in html for x in CAPTCHA_INDICATORS)

            return {"url": url, "title": title, "elements": elements, "captcha": has_captcha}
        except Exception as e:
            return {"url": "", "title": "", "elements": [], "captcha": False, "error": str(e)}

    async def execute(self, action: str) -> Result:
        """Execute action with human-like timing."""
        action = action.strip()

        # Human-like delay
        await asyncio.sleep(random.uniform(0.1, 0.3))

        try:
            if action.lower().startswith("click("):
                sel = self._extract(action, "selector")
                # Try to dismiss popups first if click fails
                try:
                    await self._page.click(sel, timeout=5000)
                except:
                    await self._dismiss_popups()
                    await self._page.click(sel, timeout=5000)
                await self._page.wait_for_timeout(500)
                return Result(True, f"Clicked: {sel}")

            elif action.lower().startswith("type("):
                sel = self._extract(action, "selector")
                text = self._extract(action, "text")
                await self._page.fill(sel, text, timeout=5000)
                return Result(True, f"Typed: {text[:20]}")

            elif action.lower().startswith("press("):
                key = self._extract(action, "key")
                await self._page.keyboard.press(key)
                return Result(True, f"Pressed: {key}")

            elif action.lower().startswith("scroll("):
                d = self._extract(action, "direction") or "down"
                await self._page.mouse.wheel(0, 500 if d == "down" else -500)
                await self._page.wait_for_timeout(300)
                return Result(True, f"Scrolled {d}")

            elif action.lower().startswith("navigate("):
                url = self._extract(action, "url")
                if not url.startswith("http"):
                    url = "https://" + url
                await self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await self._page.wait_for_timeout(random.randint(500, 1000))
                return Result(True, f"Navigated: {url}")

            elif action.lower().startswith("dismiss"):
                n = await self._dismiss_popups()
                return Result(True, f"Dismissed {n} popups")

            return Result(False, f"Unknown: {action[:50]}")
        except Exception as e:
            return Result(False, str(e))

    def _extract(self, action: str, arg: str) -> str:
        for p in [rf'{arg}\s*=\s*"([^"]+)"', rf"{arg}\s*=\s*'([^']+)'"]:
            m = re.search(p, action)
            if m:
                return m.group(1)
        return ""

    async def _dismiss_popups(self) -> int:
        n = 0
        for sel in POPUP_SELECTORS:
            try:
                if await self._page.is_visible(sel, timeout=200):
                    await self._page.click(sel, timeout=500)
                    n += 1
            except:
                pass
        try:
            await self._page.keyboard.press("Escape")
        except:
            pass
        return n

    async def wait_human(self, reason: str, timeout: int = 120) -> Result:
        """Wait for human to solve captcha/login."""
        print(f"\n{'='*50}")
        print(f"HUMAN NEEDED: {reason}")
        print(f"Solve in browser, waiting {timeout}s...")
        print(f"{'='*50}\n")

        initial_url = self._page.url
        initial_len = len(await self._page.content())

        for i in range(timeout):
            await asyncio.sleep(1)
            if self._page.url != initial_url or abs(len(await self._page.content()) - initial_len) > 500:
                print("Human action detected!")
                await self._page.wait_for_timeout(1000)
                return Result(True, "Human completed")
            if i % 15 == 0 and i > 0:
                print(f"  Waiting... {i}s")

        return Result(False, "Timeout")


# =============================================================================
# MAIN AGENT
# =============================================================================

async def run(task: str, headless: bool = False, max_steps: int = 30):
    browser = Browser(headless=headless)
    r = await browser.launch()
    if not r.ok:
        print(f"Launch failed: {r.msg}")
        return

    print(f"\nTask: {task}")
    print("=" * 50)

    history = []

    try:
        for step in range(1, max_steps + 1):
            state = await browser.get_state()
            print(f"\nStep {step}: {state['url'][:40]}...")

            # Get action from LLM
            action = await get_action(
                task=task,
                url=state["url"],
                title=state["title"],
                elements=state["elements"],
                history=history,
                has_captcha=state["captcha"]
            )

            print(f"  Action: {action[:50]}")

            # Handle action types
            if action.upper().startswith("DONE"):
                print(f"\n{'='*50}")
                print("TASK DONE")
                print(f"URL: {state['url']}")
                print(f"{'='*50}")
                break

            elif action.upper().startswith("WAIT_HUMAN"):
                reason = action.split(":", 1)[1].strip() if ":" in action else "solve captcha/login"
                r = await browser.wait_human(reason)
                history.append(f"HUMAN: {reason} -> {'ok' if r.ok else 'timeout'}")

            elif any(action.lower().startswith(x) for x in ["click(", "type(", "navigate(", "scroll(", "press(", "dismiss"]):
                r = await browser.execute(action)
                print(f"  Result: {'OK' if r.ok else 'FAIL'} - {r.msg}")
                history.append(f"{action[:30]} -> {r.msg[:30]}")

            else:
                print(f"  Unknown action format")
                history.append(f"unknown: {action[:30]}")

        else:
            print(f"\nMax steps ({max_steps}) reached")

    finally:
        await browser.close()


# =============================================================================
# CLI
# =============================================================================

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("task", nargs="*")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--steps", type=int, default=30)
    args = parser.parse_args()

    if not args.task:
        print("Usage: python run_mcp.py \"task\"")
        print("\nExamples:")
        print('  python run_mcp.py "Go to google.com and search for AI SDR"')
        print('  python run_mcp.py "Open FB Ads Library search for booked meetings"')
        print('  python run_mcp.py "Login to LinkedIn find sales directors"')
        print("\nFeatures:")
        print("  - Persistent login sessions (saved in ~/.eversale/browser-profile)")
        print("  - Auto captcha detection -> waits for human")
        print("  - Stealth mode to avoid bot detection")
        print("  - Non-headless by default (--headless to hide)")
        return

    logger.remove()
    logger.add(sys.stderr, level="WARNING")

    task = " ".join(args.task)
    start = datetime.now()
    asyncio.run(run(task, args.headless, args.steps))
    print(f"\nTime: {(datetime.now() - start).total_seconds():.1f}s")


if __name__ == "__main__":
    main()
