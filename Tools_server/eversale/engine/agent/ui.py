"""
Eversale CLI UI - Claude Code-inspired premium terminal interface.

Features:
- Real-time streaming tool visualization
- Animated progress with satisfying feedback
- Claude Code-style thinking indicators
- Tool call streaming with syntax highlighting
- Satisfying completion celebrations
- Premium color gradients
"""

import asyncio
import sys
import time
import random
from typing import Optional, List, Callable, Dict, Any
from datetime import datetime
from rich.console import Console, Group
from rich.panel import Panel
from rich.text import Text
from rich.live import Live
from rich.spinner import Spinner
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn
from rich.table import Table
from rich.box import ROUNDED, DOUBLE, HEAVY, SIMPLE, MINIMAL
from rich.style import Style
from rich.align import Align
from rich.columns import Columns
from rich.rule import Rule
from rich.syntax import Syntax
from rich.markdown import Markdown
from rich import print as rprint

console = Console()

# Premium brand colors - Claude Code inspired
BRAND_PRIMARY = "#00D4AA"      # Teal/cyan - main accent
BRAND_SECONDARY = "#A78BFA"    # Soft purple
BRAND_ACCENT = "#FBBF24"       # Warm amber
BRAND_SUCCESS = "#34D399"      # Mint green
BRAND_ERROR = "#F87171"        # Soft red
BRAND_DIM = "#6B7280"          # Muted gray
BRAND_BRIGHT = "#F9FAFB"       # Almost white
BRAND_TOOL = "#60A5FA"         # Tool blue
BRAND_BROWSER = "#C084FC"      # Browser purple
BRAND_DATA = "#2DD4BF"         # Data teal

# Import sentient output for human-like messages
try:
    from .sentient_output import get_tool_message, get_thinking, get_progress, get_success
    SENTIENT_OUTPUT_AVAILABLE = True
except ImportError:
    SENTIENT_OUTPUT_AVAILABLE = False

# Activity verbs for different tool types - human-like, sentient descriptions
# These are fallbacks; sentient_output provides varied messages
TOOL_VERBS = {
    # Browser navigation - natural language
    'playwright_navigate': ('Opening', BRAND_BROWSER),
    'playwright_go_back': ('Going back', BRAND_BROWSER),
    'playwright_go_forward': ('Moving forward', BRAND_BROWSER),
    'playwright_reload': ('Refreshing', BRAND_BROWSER),

    # Browser interaction - conversational
    'playwright_click': ('Clicking', BRAND_BROWSER),
    'playwright_fill': ('Typing', BRAND_BROWSER),
    'playwright_type': ('Entering', BRAND_BROWSER),
    'playwright_press': ('Pressing', BRAND_BROWSER),
    'playwright_select': ('Selecting', BRAND_BROWSER),
    'playwright_check': ('Checking', BRAND_BROWSER),
    'playwright_uncheck': ('Unchecking', BRAND_BROWSER),
    'playwright_hover': ('Looking at', BRAND_BROWSER),
    'playwright_scroll': ('Scrolling', BRAND_BROWSER),

    # Browser capture - friendly
    'playwright_snapshot': ('Reading page', BRAND_BROWSER),
    'playwright_screenshot': ('Capturing', BRAND_BROWSER),
    'playwright_pdf': ('Creating PDF', BRAND_BROWSER),

    # Data extraction - natural
    'playwright_get_text': ('Reading', BRAND_DATA),
    'playwright_get_markdown': ('Reading content', BRAND_DATA),
    'playwright_extract': ('Gathering data', BRAND_DATA),
    'playwright_extract_fb_ads': ('Finding ads', BRAND_DATA),
    'playwright_extract_reddit': ('Reading posts', BRAND_DATA),
    'playwright_extract_page_fast': ('Collecting info', BRAND_DATA),
    'playwright_batch_extract': ('Processing batch', BRAND_DATA),
    'playwright_find_contacts': ('Finding contacts', BRAND_DATA),
    'playwright_evaluate': ('Processing', BRAND_DATA),

    # Wait operations - patient
    'playwright_wait': ('Waiting', BRAND_BROWSER),
    'playwright_wait_for_selector': ('Waiting', BRAND_BROWSER),
    'playwright_wait_for_navigation': ('Loading', BRAND_BROWSER),

    # File operations - simple
    'read_file': ('Reading', BRAND_TOOL),
    'write_file': ('Saving', BRAND_TOOL),
    'list_directory': ('Looking at files', BRAND_TOOL),
    'create_directory': ('Creating folder', BRAND_TOOL),

    # Memory operations - human-like
    'memory_store': ('Remembering', BRAND_TOOL),
    'memory_retrieve': ('Recalling', BRAND_TOOL),
    'memory_search': ('Searching memory', BRAND_TOOL),

    # Search/analysis - natural
    'search': ('Searching', BRAND_TOOL),
    'analyze': ('Analyzing', BRAND_TOOL),
    'summarize': ('Summarizing', BRAND_TOOL),

    # Default fallback
    'default': ('Working on', BRAND_TOOL),
}

# Smooth animation frames
PULSE_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
DOT_FRAMES = ["   ", ".  ", ".. ", "...", " ..", "  .", "   "]
ARROW_FRAMES = ["▹▹▹▹▹", "▸▹▹▹▹", "▹▸▹▹▹", "▹▹▸▹▹", "▹▹▹▸▹", "▹▹▹▹▸"]
PROGRESS_CHARS = "░▒▓█"
SPARKLE = ["✦", "✧", "★", "☆"]

# ASCII Art Logo - Clean, modern
LOGO_MODERN = """
 ███████╗██╗   ██╗███████╗██████╗ ███████╗ █████╗ ██╗     ███████╗
 ██╔════╝██║   ██║██╔════╝██╔══██╗██╔════╝██╔══██╗██║     ██╔════╝
 █████╗  ██║   ██║█████╗  ██████╔╝███████╗███████║██║     █████╗
 ██╔══╝  ╚██╗ ██╔╝██╔══╝  ██╔══██╗╚════██║██╔══██║██║     ██╔══╝
 ███████╗ ╚████╔╝ ███████╗██║  ██║███████║██║  ██║███████╗███████╗
 ╚══════╝  ╚═══╝  ╚══════╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚══════╝╚══════╝
"""

LOGO_COMPACT = """╔═╗╦  ╦╔═╗╦═╗╔═╗╔═╗╦  ╔═╗
║╣ ╚╗╔╝║╣ ╠╦╝╚═╗╠═╣║  ║╣
╚═╝ ╚╝ ╚═╝╩╚═╚═╝╩ ╩╩═╝╚═╝"""


class ToolCallDisplay:
    """Renders a tool call with beautiful formatting."""

    def __init__(self, tool_name: str, args: Dict[str, Any] = None):
        self.tool_name = tool_name
        self.args = args or {}
        self.start_time = time.time()
        self.status = "running"  # running, success, error

    def render(self) -> Text:
        """Render the tool call as a Text object - human-like, no technical jargon."""
        # Use sentient output for varied messages if available
        if SENTIENT_OUTPUT_AVAILABLE:
            verb = get_tool_message(self.tool_name)
            _, color = TOOL_VERBS.get(self.tool_name, TOOL_VERBS['default'])
        else:
            verb, color = TOOL_VERBS.get(self.tool_name, TOOL_VERBS['default'])

        text = Text()

        # Status indicator - subtle, not technical
        if self.status == "running":
            frame_idx = int((time.time() * 10) % len(PULSE_FRAMES))
            text.append(f" {PULSE_FRAMES[frame_idx]} ", style=f"bold {color}")
        elif self.status == "success":
            text.append(" ✓ ", style=f"bold {BRAND_SUCCESS}")
        else:
            # Don't show error symbol - just dim it
            text.append(" ○ ", style=f"dim {BRAND_DIM}")

        # Show human-like message (verb already contains full message from sentient_output)
        text.append(f"{verb}", style=f"{color}")

        # Don't show technical args (URLs, selectors, etc.) - keep it human
        # Only show elapsed time subtly for longer operations
        if self.status == "running":
            elapsed = time.time() - self.start_time
            if elapsed > 3:  # Only show time if taking a while
                text.append(f"  ({elapsed:.0f}s)", style=f"dim {BRAND_DIM}")

        return text


class StreamingProgress:
    """Claude Code-style streaming progress with tool visualization."""

    # Dynamic messages to cycle through - keeps users engaged
    WORKING_MESSAGES = [
        "Working",
        "Processing",
        "Analyzing",
        "Looking good",
        "Making progress",
        "Almost there",
        "Finalizing",
    ]

    def __init__(self, console: Console):
        self.console = console
        self.live = None
        self.current_message = "Working"
        self.current_step = None
        self.tool_calls: List[ToolCallDisplay] = []
        self.completed_tools = 0
        self.start_time = time.time()
        self.frame_idx = 0
        self._stop = False
        self._message_idx = 0
        self._last_message_change = time.time()

    def __enter__(self):
        self._start()
        return self

    def __exit__(self, *args):
        self._stop_live()
        self._show_completion()

    def _start(self):
        """Start the live display."""
        self.live = Live(
            self._render(),
            console=self.console,
            refresh_per_second=12,
            transient=False
        )
        self.live.start()

    def _stop_live(self):
        """Stop live display."""
        if self.live:
            self.live.stop()
            self.live = None

    def _render(self) -> Group:
        """Render the current state - human-like, no technical jargon."""
        elements = []

        # Main status line with spinner - sentient feeling
        self.frame_idx = (self.frame_idx + 1) % len(PULSE_FRAMES)

        # Cycle through messages every 3 seconds to keep it alive
        now = time.time()
        if now - self._last_message_change > 3.0:
            self._message_idx = (self._message_idx + 1) % len(self.WORKING_MESSAGES)
            self._last_message_change = now
            # Only update if not manually set
            if self.current_message in self.WORKING_MESSAGES or self.current_message == "Working":
                self.current_message = self.WORKING_MESSAGES[self._message_idx]

        # Add animated dots based on frame
        dots = "." * ((self.frame_idx // 3) % 4)

        status = Text()
        status.append(f"{PULSE_FRAMES[self.frame_idx]} ", style=f"bold {BRAND_PRIMARY}")
        status.append(f"{self.current_message}{dots}", style="bold white")

        # Only show elapsed time if it's been a while (feels more natural)
        elapsed = time.time() - self.start_time
        if elapsed > 10:
            # Human-friendly time display
            if elapsed < 60:
                time_str = f"{int(elapsed)}s"
            else:
                mins = int(elapsed // 60)
                time_str = f"{mins}m"
            status.append(f"  {time_str}", style=f"dim {BRAND_DIM}")

        elements.append(status)

        # Current step - shown subtly only if meaningful
        if self.current_step and len(self.current_step) > 3:
            step_text = Text()
            step_text.append("  ", style="dim")
            step_text.append(self.current_step, style=f"dim {BRAND_DIM}")
            elements.append(step_text)

        # Recent tool calls (show last 2 for cleaner look)
        visible_tools = self.tool_calls[-2:] if self.tool_calls else []
        for tool in visible_tools:
            elements.append(tool.render())

        return Group(*elements)

    def update(self, message: str = None, step: str = None):
        """Update the progress display."""
        if message:
            self.current_message = message
        if step:
            self.current_step = step
        if self.live:
            self.live.update(self._render())

    def tool_start(self, tool_name: str, args: Dict[str, Any] = None):
        """Show a tool starting."""
        tool = ToolCallDisplay(tool_name, args)
        self.tool_calls.append(tool)
        if self.live:
            self.live.update(self._render())
        return tool

    def tool_end(self, tool: ToolCallDisplay, success: bool = True):
        """Mark a tool as completed."""
        tool.status = "success" if success else "error"
        self.completed_tools += 1
        if self.live:
            self.live.update(self._render())

    def step(self, action: str):
        """Show a step being taken."""
        self.current_step = action
        if self.live:
            self.live.update(self._render())

    def _show_completion(self):
        """Show completion summary - human-like, celebratory."""
        elapsed = time.time() - self.start_time

        # Get a varied completion message
        if SENTIENT_OUTPUT_AVAILABLE:
            done_msg = get_success()
        else:
            done_msg = "Done!"

        # Completion line - simple and satisfying
        completion = Text()
        completion.append("✓ ", style=f"bold {BRAND_SUCCESS}")
        completion.append(done_msg, style="bold white")

        # Only show time for longer tasks
        if elapsed > 5:
            if elapsed < 60:
                completion.append(f"  ({int(elapsed)}s)", style=f"dim {BRAND_DIM}")
            else:
                mins = int(elapsed // 60)
                completion.append(f"  ({mins}m)", style=f"dim {BRAND_DIM}")

        self.console.print(completion)

    def get_callback(self):
        """Return a callback function for Brain progress updates."""
        def callback(message: str, step: str = None, tool: str = None, tool_args: dict = None):
            if tool:
                t = self.tool_start(tool, tool_args)
                # Auto-complete after a moment (in real use, brain would call tool_end)
            self.update(message, step)
        return callback


class EversaleUI:
    """Premium UI class for Eversale CLI - Claude Code inspired."""

    def __init__(self):
        self.console = Console()
        self._thinking = False
        self._thinking_task = None
        self.session_start = time.time()
        self.tasks_completed = 0

    async def show_logo(self, animate: bool = True):
        """Display the Eversale logo with optional animation."""
        if animate:
            await self._animate_logo()
        else:
            self._static_logo()

    async def _animate_logo(self):
        """Animate the logo with smooth reveal."""
        # Clear screen
        self.console.clear()

        # Check terminal width - use compact logo if too narrow
        term_width = self.console.width or 80
        if term_width < 75:
            # Use compact logo for narrow terminals
            self._static_logo()
            return

        lines = LOGO_MODERN.strip().split('\n')

        # Color gradient for logo
        colors = ["#00D4AA", "#00C9A7", "#00BEA4", "#00B3A1", "#00A89E", "#009D9B"]

        # Reveal with smooth animation
        for i, line in enumerate(lines):
            color = colors[i % len(colors)]
            styled = Text(line, style=f"bold {color}")
            self.console.print(Align.center(styled))
            await asyncio.sleep(0.06)

        # Tagline with fade-in effect
        await asyncio.sleep(0.2)
        tagline = "Autonomous AI Worker  •  31 Industries  •  Any Web Task  •  Runs Forever"

        # Typing effect for tagline
        typed = Text()
        for char in tagline:
            typed.append(char, style=f"dim {BRAND_DIM}")
            self.console.print(Align.center(typed), end="\r")
            await asyncio.sleep(0.015)
        self.console.print()

        await asyncio.sleep(0.3)
        self.console.print()

    def _static_logo(self):
        """Show static logo."""
        logo = Text(LOGO_COMPACT, style=f"bold {BRAND_PRIMARY}")
        self.console.print(Align.center(logo))
        self.console.print(Align.center(Text("Autonomous AI Worker  •  31 Industries  •  Any Web Task  •  Runs Forever", style="dim")))
        self.console.print()

    async def show_welcome(self):
        """Show minimal welcome - just hint. Details in 'help' command."""
        # Single line hint like Claude Code
        self.console.print(
            f"[dim]Type your task, or [bold]help[/bold] for commands, [bold]examples[/bold] for prompts[/dim]"
        )
        self.console.print()

    def show_help(self):
        """Show comprehensive help screen."""
        # Header
        self.console.print(Panel(
            Text("EVERSALE - Your AI Employee", style=f"bold {BRAND_PRIMARY}", justify="center"),
            box=MINIMAL,
            border_style=BRAND_PRIMARY
        ))

        # Categories with icons
        categories = [
            ("Research & Leads", BRAND_PRIMARY, [
                '"Research <company>" - deep dive analysis',
                '"Find leads from <site>" - extract contacts',
                '"Build lead list for <industry>"',
            ]),
            ("Writing & Content", BRAND_SECONDARY, [
                '"Write cold email for <company>"',
                '"Draft reply to <message>"',
                '"Generate report from <data>"',
            ]),
            ("Browser Automation", BRAND_BROWSER, [
                '"Go to <url> and <action>"',
                '"Fill out form on <site>"',
                '"Extract data from <page>"',
            ]),
            ("Loops & Schedules", BRAND_ACCENT, [
                '"<task> forever" - run continuously',
                '"<task> every hour" - interval repeat',
                '"<task> for 2 hours" - timed run',
                '"<task> every friday at 3pm" - weekly recurring',
                '"<task> next friday at 3pm" - one-time scheduled',
            ]),
            ("Reliability", BRAND_SUCCESS, [
                '"--watchdog" - auto-restart on crash',
                'Auto-recovery from crash state',
                'Mission persistence across restarts',
            ]),
            ("Speed Mode", "cyan", [
                '"fast track <task>" - max speed mode',
                '"quickly <task>" - skip humanization',
                '"turbo <task>" - instant execution',
                'Works with: fast, rapid, instant, rush, asap',
            ]),
        ]

        for title, color, items in categories:
            content = Table.grid(padding=(0, 1))
            content.add_column(style="dim", width=45)
            for item in items:
                content.add_row(item)

            self.console.print(Panel(
                content,
                title=f"[{color}]{title}[/{color}]",
                border_style=BRAND_DIM,
                box=ROUNDED,
                padding=(0, 1)
            ))

        # Pro tip
        self.console.print(f"\n[{BRAND_ACCENT}]⚡ Pro Tip:[/{BRAND_ACCENT}] [dim]Run parallel agents in multiple terminals![/dim]")

        # Commands
        self.console.print(f"\n[bold]Commands:[/bold] [dim]help • about • stats • system • examples • check • health-check • clear • exit[/dim]")
        self.console.print(f"[bold]CLI:[/bold] [dim]./eversale --watchdog • ./eversale setup • ./eversale health-check • ./eversale examples[/dim]")
        self.console.print(f"[bold]Piped Input:[/bold] [dim]echo \"task\" | eversale -i • cat cmds.txt | eversale --interactive[/dim]")
        self.console.print(f"[{BRAND_SUCCESS}]MCP:[/{BRAND_SUCCESS}] [dim]Internal MCP server with 74+ tools always running[/dim]\n")

    def prompt(self) -> str:
        """Show beautiful prompt."""
        prompt_text = Text()
        prompt_text.append("eversale", style=f"bold {BRAND_PRIMARY}")
        prompt_text.append(" ❯ ", style=f"bold {BRAND_SECONDARY}")
        return self.console.input(prompt_text)

    def prompt_piped(self) -> str:
        """Read input from pipe/stdin without Rich formatting.

        This is used when stdin is not a TTY (piped input).
        Reads one line at a time and returns it stripped.
        Raises EOFError when input is exhausted.
        """
        import sys
        line = sys.stdin.readline()
        if not line:
            raise EOFError()
        return line.strip()

    def thinking_sync(self, message: str = "Working"):
        """Return a streaming progress context manager."""
        return StreamingProgress(self.console)

    def show_status(self, message: str, status: str = "info"):
        """Show status message with icon."""
        icons = {
            "info": ("○", BRAND_PRIMARY),
            "success": ("✓", BRAND_SUCCESS),
            "error": ("✗", BRAND_ERROR),
            "warning": ("!", BRAND_ACCENT),
            "thinking": ("◐", BRAND_SECONDARY),
        }

        icon, color = icons.get(status, ("•", BRAND_DIM))
        self.console.print(f"[{color}]{icon}[/{color}] {message}")

    def show_result(self, result: str, title: str = "Result"):
        """Show result in a beautiful panel."""
        # Sanitize: Detect and handle HTML contamination from eversale.io or other sources
        if result and ('_app/immutable' in result or 'svelte-' in result or 'sveltekit' in result.lower()):
            # HTML contamination detected - extract any useful text and show warning
            import re
            # Try to extract any text before the HTML
            clean_parts = re.split(r'<(?:link|script|style|!DOCTYPE|html|head|body)[^>]*>', result, flags=re.IGNORECASE)
            clean_text = clean_parts[0].strip() if clean_parts else ""
            if clean_text and len(clean_text) > 20:
                result = clean_text + "\n\n[dim](Note: HTML content was filtered from output)[/dim]"
            else:
                result = "[Navigation completed but output was corrupted by HTML. Please retry the task.]"

        # Truncate very long results
        display_result = result
        if len(result) > 2000:
            display_result = result[:2000] + "\n\n[dim]... (truncated)[/dim]"

        # Parse result for special formatting
        # If it looks like markdown, render it
        if any(marker in result for marker in ['##', '**', '- ', '* ', '`']):
            content = Markdown(display_result)
        else:
            content = display_result

        panel = Panel(
            content,
            title=f"[bold {BRAND_SUCCESS}]✓ {title}[/bold {BRAND_SUCCESS}]",
            border_style=BRAND_SUCCESS,
            box=ROUNDED,
            padding=(1, 2)
        )
        self.console.print(panel)
        self.tasks_completed += 1

    def show_error(self, error: str):
        """Show error message."""
        panel = Panel(
            f"[{BRAND_ERROR}]{error}[/{BRAND_ERROR}]",
            title="[bold red]Error[/bold red]",
            border_style=BRAND_ERROR,
            box=ROUNDED
        )
        self.console.print(panel)

    def show_stats(self, stats: dict):
        """Show stats in a clean table."""
        table = Table(
            box=SIMPLE,
            border_style=BRAND_DIM,
            show_header=False,
            padding=(0, 2)
        )

        table.add_column("Metric", style=f"dim")
        table.add_column("Value", style=f"bold {BRAND_SUCCESS}", justify="right")

        icons = {
            'iterations': '↻',
            'tool_calls': '⚙',
            'vision_calls': '◉',
            'retries': '↩',
            'cache_hits': '⚡',
            'time_elapsed': '◷',
        }

        for key, value in stats.items():
            icon = icons.get(key, '•')
            display_key = key.replace('_', ' ').title()
            if isinstance(value, float):
                table.add_row(f"{icon} {display_key}", f"{value:.1f}")
            else:
                table.add_row(f"{icon} {display_key}", str(value))

        self.console.print(table)

    def show_tool_call(self, tool_name: str, args: dict = None, status: str = "running"):
        """Show a tool being called - streaming style."""
        verb, color = TOOL_VERBS.get(tool_name, TOOL_VERBS['default'])

        text = Text()

        if status == "running":
            text.append("  ▸ ", style=f"bold {color}")
        elif status == "success":
            text.append("  ✓ ", style=f"bold {BRAND_SUCCESS}")
        else:
            text.append("  ✗ ", style=f"bold {BRAND_ERROR}")

        text.append(f"{verb} ", style=f"{color}")

        if args:
            if 'url' in args:
                url = str(args['url'])[:50]
                text.append(url, style="dim underline")
            elif 'selector' in args:
                text.append(f"'{args['selector']}'", style="dim")

        self.console.print(text)

    def show_saved(self, path: str):
        """Show file saved message."""
        self.console.print(f"\n[{BRAND_SUCCESS}]📄 Saved:[/{BRAND_SUCCESS}] [bold underline]{path}[/bold underline]\n")

    def show_about(self):
        """Show about info."""
        about = Table.grid(padding=(0, 2))
        about.add_column(style=f"bold {BRAND_PRIMARY}")
        about.add_column(style="white")

        about.add_row("What", "Your AI Employee - autonomous web work across 15 industries")
        about.add_row("How", "Real browser automation + AI reasoning (Playwright + LLM)")
        about.add_row("Industries", "Sales, Research, Finance, Support, HR, Marketing, Legal & more")
        about.add_row("Scheduling", "Forever loops, intervals, recurring, timed runs")
        about.add_row("Reliability", "Crash recovery, watchdog, dead man's switch, multi-instance")
        about.add_row("Data", "FB Ads Library, LinkedIn, Reddit, Gmail, any website")
        about.add_row("Hosting", "Cloud (Enterprise: on-premise available)")
        about.add_row("By", "eversale.io")

        panel = Panel(
            about,
            title=f"[bold {BRAND_PRIMARY}]Eversale v2.1[/bold {BRAND_PRIMARY}]",
            border_style=BRAND_PRIMARY,
            box=ROUNDED,
            padding=(1, 2)
        )
        self.console.print(panel)

    async def celebrate_completion(self, task_time: float, output_path: str = None):
        """Premium task completion celebration."""
        # Quick success animation
        frames = ["○", "◔", "◑", "◕", "●", "✓"]
        for frame in frames:
            color = BRAND_SUCCESS if frame == "✓" else BRAND_PRIMARY
            self.console.print(f"\r[{color}]{frame}[/{color}] Complete!", end="")
            await asyncio.sleep(0.08)
        self.console.print()

        # Speed feedback
        if task_time < 30:
            speed_msg = f"[{BRAND_SUCCESS}]⚡ Lightning fast![/{BRAND_SUCCESS}]"
        elif task_time < 60:
            speed_msg = f"[{BRAND_PRIMARY}]✨ Quick work![/{BRAND_PRIMARY}]"
        else:
            speed_msg = f"[{BRAND_ACCENT}]📊 Thorough analysis[/{BRAND_ACCENT}]"

        self.console.print(f"  {speed_msg} {task_time:.1f}s")

        if output_path:
            self.console.print(f"  [{BRAND_SUCCESS}]📄[/{BRAND_SUCCESS}] [bold underline]{output_path}[/bold underline]")

        self.console.print()

    def show_startup_badge(self):
        """Show startup badge."""
        badge = Text()
        badge.append("  ▸ ", style=f"bold {BRAND_PRIMARY}")
        badge.append("Eversale", style=f"bold {BRAND_PRIMARY}")
        badge.append(" v2.1", style="dim")
        self.console.print(badge)

    def show_ready(self):
        """Show ready status."""
        self.console.print(f"[{BRAND_SUCCESS}]✓[/{BRAND_SUCCESS}] [bold]Ready[/bold]\n")

    def show_steering_hint(self):
        """Show hint about real-time steering during task execution."""
        hint = Text()
        hint.append("  ", style="dim")
        hint.append("↳ ", style=f"dim {BRAND_PRIMARY}")
        hint.append("Type while running to steer", style=f"dim {BRAND_DIM}")
        hint.append(" • ", style="dim")
        hint.append("'stop'", style=f"{BRAND_ERROR}")
        hint.append(" ", style="dim")
        hint.append("'pause'", style=f"{BRAND_ACCENT}")
        hint.append(" ", style="dim")
        hint.append("or guidance", style=f"dim {BRAND_DIM}")
        self.console.print(hint)

    def show_action_stream(self, action: str, detail: str = None):
        """Show a streaming action - used during execution."""
        text = Text()
        text.append("  → ", style=f"dim {BRAND_PRIMARY}")
        text.append(action, style="white")
        if detail:
            text.append(f" {detail}", style="dim")
        self.console.print(text)


class ThinkingContext:
    """Legacy thinking context - redirects to StreamingProgress."""

    def __init__(self, ui: EversaleUI, message: str):
        self.ui = ui
        self.message = message
        self.progress = StreamingProgress(ui.console)
        self.progress.current_message = message

    def __enter__(self):
        self.progress.__enter__()
        return self

    def __exit__(self, *args):
        self.progress.__exit__(*args)

    def update(self, message: str, step: str = None):
        """Update progress."""
        self.progress.update(message, step)

    def step(self, action: str):
        """Show a step."""
        self.progress.step(action)

    def get_callback(self):
        """Return callback for Brain progress."""
        return self.progress.get_callback()


# Global UI instance
ui = EversaleUI()


# Convenience functions
async def logo(animate: bool = True):
    await ui.show_logo(animate)

async def welcome():
    await ui.show_welcome()

def help_screen():
    ui.show_help()

def prompt() -> str:
    return ui.prompt()

def status(message: str, status_type: str = "info"):
    ui.show_status(message, status_type)

def result(text: str, title: str = "Result"):
    ui.show_result(text, title)

def error(message: str):
    ui.show_error(message)

def stats(data: dict):
    ui.show_stats(data)

def thinking(message: str = "Working"):
    return ui.thinking_sync(message)

def saved(path: str):
    ui.show_saved(path)

def action(text: str, detail: str = None):
    ui.show_action_stream(text, detail)


if __name__ == "__main__":
    async def _demo():
        """Demo the UI components."""
        await ui.show_welcome()

        # Simulate a task with tool calls
        print("\n[bold]Simulating task execution:[/bold]\n")

        with ui.thinking_sync("Researching company") as progress:
            await asyncio.sleep(0.5)

            # Simulate tool calls
            t1 = progress.tool_start("playwright_navigate", {"url": "https://stripe.com"})
            await asyncio.sleep(1)
            progress.tool_end(t1, True)

            progress.update("Extracting data", "Finding contact information")
            t2 = progress.tool_start("playwright_extract_page_fast", {"selector": "body"})
            await asyncio.sleep(0.8)
            progress.tool_end(t2, True)

            progress.update("Analyzing results")
            await asyncio.sleep(0.5)

        ui.show_result("""## Company: Stripe

**Industry:** Financial Technology
**Website:** stripe.com
**Contacts Found:** 3

### Key Information
- Founded: 2010
- Headquarters: San Francisco
- Products: Payment processing, billing, fraud prevention

### Contacts
- John Doe - CEO - john@stripe.com
- Jane Smith - CTO - jane@stripe.com
""")

        ui.show_stats({
            "iterations": 5,
            "tool_calls": 12,
            "vision_calls": 2,
            "time_elapsed": 8.3
        })

        await ui.celebrate_completion(8.3, "~/Desktop/stripe_research.csv")

    asyncio.run(_demo())
