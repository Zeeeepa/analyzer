"""
Steering Module - Real-time user input during task execution

Enables Claude Code-style steering where users can provide guidance,
corrections, or new instructions while a task is running.

Usage:
    steering = SteeringInput()
    steering.start()  # Start listening in background

    # In ReAct loop:
    user_input = steering.check()  # Non-blocking check
    if user_input:
        # Inject user message into conversation
        messages.append({'role': 'user', 'content': user_input})

    steering.stop()
"""

import sys
import select
import threading
import queue
import asyncio
from typing import Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class SteeringMessage:
    """A steering message from the user."""
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    message_type: str = "guidance"  # guidance, stop, pause, redirect

    @classmethod
    def parse(cls, raw: str) -> 'SteeringMessage':
        """Parse raw input into a steering message with type detection."""
        content = raw.strip()
        lower = content.lower()

        # Detect special commands
        if lower in ('stop', 'quit', 'cancel', 'abort'):
            return cls(content=content, message_type="stop")
        elif lower in ('pause', 'wait', 'hold'):
            return cls(content=content, message_type="pause")
        elif lower.startswith('go to ') or lower.startswith('instead ') or lower.startswith('actually '):
            return cls(content=content, message_type="redirect")
        else:
            return cls(content=content, message_type="guidance")


class SteeringInput:
    """
    Non-blocking user input handler for real-time task steering.

    Runs a background thread that listens for user input without
    blocking the main execution loop.
    """

    def __init__(self):
        self._queue: queue.Queue[SteeringMessage] = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._paused = False
        self._stop_requested = False
        self._on_message: Optional[Callable[[SteeringMessage], None]] = None
        self._prompt_shown = False

    def start(self, on_message: Optional[Callable[[SteeringMessage], None]] = None):
        """Start the background input listener."""
        if self._thread and self._thread.is_alive():
            return  # Already running

        self._running = True
        self._paused = False
        self._stop_requested = False
        self._on_message = on_message
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()
        logger.debug("Steering input listener started")

    def stop(self):
        """Stop the background input listener."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=0.5)
            self._thread = None
        logger.debug("Steering input listener stopped")

    def _listen_loop(self):
        """Background thread that listens for user input."""
        while self._running:
            try:
                # Check if input is available (non-blocking on Unix)
                if sys.platform != 'win32':
                    # Unix: use select for non-blocking check
                    readable, _, _ = select.select([sys.stdin], [], [], 0.1)
                    if readable:
                        # Check for ESC key first (single byte read)
                        import termios
                        import tty
                        old_settings = termios.tcgetattr(sys.stdin)
                        try:
                            tty.setcbreak(sys.stdin.fileno())
                            char = sys.stdin.read(1)
                            if char == '\x1b':  # ESC key
                                self._handle_input('pause')
                                continue
                            # Not ESC, read rest of line
                            line = char + sys.stdin.readline()
                        finally:
                            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
                        if line.strip():
                            self._handle_input(line)
                else:
                    # Windows: use msvcrt for non-blocking check
                    import msvcrt
                    if msvcrt.kbhit():
                        char = msvcrt.getwch()
                        # ESC key = pause
                        if char == '\x1b':  # ESC key
                            self._handle_input('pause')
                            continue
                        # Read until newline
                        chars = [char] if char not in ('\r', '\n') else []
                        while True:
                            if msvcrt.kbhit():
                                char = msvcrt.getwch()
                                if char == '\r' or char == '\n':
                                    break
                                if char == '\x1b':  # ESC during input
                                    self._handle_input('pause')
                                    chars = []
                                    break
                                chars.append(char)
                                print(char, end='', flush=True)  # Echo
                            else:
                                import time
                                time.sleep(0.01)
                        if chars:
                            print()  # Newline after input
                            self._handle_input(''.join(chars))
                    else:
                        import time
                        time.sleep(0.1)

            except Exception as e:
                logger.debug(f"Steering input error: {e}")
                import time
                time.sleep(0.1)

    def _handle_input(self, raw: str):
        """Process raw input into a steering message."""
        if not raw.strip():
            return

        msg = SteeringMessage.parse(raw)
        self._queue.put(msg)

        # Handle special types immediately
        if msg.message_type == "stop":
            self._stop_requested = True
        elif msg.message_type == "pause":
            self._paused = True

        # Call callback if registered
        if self._on_message:
            try:
                self._on_message(msg)
            except Exception as e:
                logger.debug(f"Steering callback error: {e}")

    def check(self) -> Optional[SteeringMessage]:
        """
        Non-blocking check for user input.

        Returns:
            SteeringMessage if user provided input, None otherwise
        """
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            return None

    def check_all(self) -> list[SteeringMessage]:
        """Get all pending steering messages."""
        messages = []
        while True:
            try:
                messages.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return messages

    @property
    def is_stop_requested(self) -> bool:
        """Check if user requested stop."""
        return self._stop_requested

    @property
    def is_paused(self) -> bool:
        """Check if user requested pause."""
        return self._paused

    def resume(self):
        """Resume from pause."""
        self._paused = False

    def clear_stop(self):
        """Clear the stop request flag."""
        self._stop_requested = False

    def show_steering_hint(self, console=None):
        """Show hint that user can provide input during execution."""
        if self._prompt_shown:
            return
        self._prompt_shown = True

        hint = "[dim]ESC to pause  Type to steer  'stop' to cancel[/dim]"
        if console:
            console.print(hint)
        else:
            print(hint)


class AsyncSteeringInput:
    """
    Async version of steering input for use with asyncio.

    Uses asyncio queues and can await for user input.
    """

    def __init__(self):
        self._queue: asyncio.Queue[SteeringMessage] = asyncio.Queue()
        self._running = False
        self._paused = False
        self._stop_requested = False
        self._reader_task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the async input listener."""
        if self._reader_task and not self._reader_task.done():
            return

        self._running = True
        self._paused = False
        self._stop_requested = False

        # Start reader task
        self._reader_task = asyncio.create_task(self._read_loop())
        logger.debug("Async steering input started")

    async def stop(self):
        """Stop the async input listener."""
        self._running = False
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None
        logger.debug("Async steering input stopped")

    async def _read_loop(self):
        """Async loop that reads stdin."""
        loop = asyncio.get_event_loop()

        while self._running:
            try:
                # Read line from stdin asynchronously
                line = await loop.run_in_executor(None, sys.stdin.readline)
                if line and line.strip():
                    msg = SteeringMessage.parse(line)
                    await self._queue.put(msg)

                    if msg.message_type == "stop":
                        self._stop_requested = True
                    elif msg.message_type == "pause":
                        self._paused = True

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Async steering read error: {e}")
                await asyncio.sleep(0.1)

    async def check(self) -> Optional[SteeringMessage]:
        """Non-blocking check for user input."""
        try:
            return self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

    async def wait_for_input(self, timeout: float = None) -> Optional[SteeringMessage]:
        """Wait for user input with optional timeout."""
        try:
            if timeout:
                return await asyncio.wait_for(self._queue.get(), timeout)
            else:
                return await self._queue.get()
        except asyncio.TimeoutError:
            return None
        except asyncio.CancelledError:
            return None

    @property
    def is_stop_requested(self) -> bool:
        return self._stop_requested

    @property
    def is_paused(self) -> bool:
        return self._paused

    def resume(self):
        self._paused = False

    def clear_stop(self):
        self._stop_requested = False


def inject_steering_message(messages: list, steering_msg: SteeringMessage) -> str:
    """
    Inject a steering message into the conversation.

    Args:
        messages: The conversation history
        steering_msg: The steering message from the user

    Returns:
        Formatted message content that was injected
    """
    # Format based on message type
    if steering_msg.message_type == "redirect":
        content = f"[USER REDIRECT] The user wants to change direction: {steering_msg.content}"
    elif steering_msg.message_type == "guidance":
        content = f"[USER GUIDANCE] The user has additional input: {steering_msg.content}"
    else:
        content = f"[USER INPUT] {steering_msg.content}"

    messages.append({
        'role': 'user',
        'content': content
    })

    return content
# Auto-deploy test Mon Dec  1 19:58:03 PST 2025
