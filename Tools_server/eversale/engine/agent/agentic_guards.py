"""
Agentic Guards - Common-sense mechanisms for robust agent behavior.

Provides:
1. Adaptive Timeouts - Learn how long actions take per site
2. Navigation Guards - Detect when agent goes off-task
3. Data Validation - Verify extracted data quality
4. Self-Correction - Detect mistakes and roll back
5. Doom Loop Guard - Prevent repeated identical tool calls
6. Directory Boundary Guard - Prevent file access outside working directory
7. Human Escalation - Ask for help when truly stuck
"""

import asyncio
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from loguru import logger


# =============================================================================
# 1. ADAPTIVE TIMEOUTS
# =============================================================================

class AdaptiveTimeout:
    """
    Learn how long actions take per site/action type and adjust timeouts dynamically.

    Usage:
        timeout_mgr = AdaptiveTimeout()
        timeout = timeout_mgr.get_timeout('facebook.com', 'click')
        # ... perform action ...
        timeout_mgr.record_duration('facebook.com', 'click', actual_duration)
    """

    def __init__(self, default_timeout: float = 10.0, min_timeout: float = 2.0, max_timeout: float = 60.0):
        self.default_timeout = default_timeout
        self.min_timeout = min_timeout
        self.max_timeout = max_timeout

        # Store timing history: {domain: {action_type: [durations]}}
        self.history: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))

        # Known slow sites/actions
        self.slow_patterns = {
            'google.com': 1.5,      # Google is generally slower
            'facebook.com': 1.3,   # FB has lots of JS
            'linkedin.com': 1.4,   # LinkedIn is slow
            'amazon.com': 1.2,
        }

        # Action type multipliers
        self.action_multipliers = {
            'navigate': 2.0,       # Navigation takes longer
            'fill': 0.5,           # Filling is quick
            'click': 1.0,
            'screenshot': 1.5,
            'extract': 2.0,        # Extraction can be slow
        }

    def get_timeout(self, domain: str, action_type: str = 'default') -> float:
        """Get adaptive timeout based on learned history."""
        # Check history first
        if domain in self.history and action_type in self.history[domain]:
            durations = self.history[domain][action_type]
            if len(durations) >= 3:
                # Use 90th percentile + 50% buffer
                sorted_d = sorted(durations)
                p90 = sorted_d[int(len(sorted_d) * 0.9)]
                timeout = p90 * 1.5
                return max(self.min_timeout, min(timeout, self.max_timeout))

        # Fall back to pattern-based estimation
        base = self.default_timeout

        # Apply site multiplier
        for pattern, mult in self.slow_patterns.items():
            if pattern in domain:
                base *= mult
                break

        # Apply action multiplier
        action_mult = self.action_multipliers.get(action_type, 1.0)
        timeout = base * action_mult

        return max(self.min_timeout, min(timeout, self.max_timeout))

    def record_duration(self, domain: str, action_type: str, duration: float):
        """Record actual duration for learning."""
        # Keep last 20 samples per domain/action
        self.history[domain][action_type].append(duration)
        if len(self.history[domain][action_type]) > 20:
            self.history[domain][action_type] = self.history[domain][action_type][-20:]

        logger.debug(f"[ADAPTIVE_TIMEOUT] Recorded {action_type} on {domain}: {duration:.2f}s")


# Global instance
_adaptive_timeout = None

def get_adaptive_timeout() -> AdaptiveTimeout:
    global _adaptive_timeout
    if _adaptive_timeout is None:
        _adaptive_timeout = AdaptiveTimeout()
    return _adaptive_timeout


# =============================================================================
# 2. NAVIGATION GUARDS
# =============================================================================

@dataclass
class NavigationGuard:
    """
    Detect when agent goes off-task (wrong page, redirected, popup, etc.)

    Usage:
        guard = NavigationGuard(target_domain='facebook.com', target_keywords=['ads', 'library'])
        is_ok, reason = guard.check_url('https://facebook.com/ads/library')
    """

    target_domain: str = ''
    target_keywords: List[str] = field(default_factory=list)
    allowed_domains: List[str] = field(default_factory=list)
    blocked_patterns: List[str] = field(default_factory=lambda: [
        'login', 'signin', 'auth', 'captcha', 'challenge',
        'error', '404', '500', 'blocked', 'suspended'
    ])
    history: List[str] = field(default_factory=list)
    max_history: int = 10

    def check_url(self, current_url: str) -> tuple:
        """
        Check if current URL is on-task.
        Returns: (is_ok: bool, reason: str)
        """
        url_lower = current_url.lower()

        # Track history
        self.history.append(current_url)
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]

        # Check for blocked patterns (error pages, auth challenges)
        for pattern in self.blocked_patterns:
            if pattern in url_lower:
                return False, f"Blocked pattern detected: {pattern}"

        # Check domain
        if self.target_domain:
            if self.target_domain not in url_lower:
                # Check if it's an allowed domain
                if self.allowed_domains:
                    if not any(d in url_lower for d in self.allowed_domains):
                        return False, f"Off-domain: expected {self.target_domain}"
                else:
                    return False, f"Off-domain: expected {self.target_domain}"

        # Check for redirect loops (same URL visited 3+ times)
        if self.history.count(current_url) >= 3:
            return False, "Redirect loop detected"

        return True, "OK"

    def detect_popup(self, page_title: str, page_content: str) -> bool:
        """Detect if a popup/modal is blocking the main content."""
        popup_indicators = [
            'cookie', 'accept', 'consent', 'subscribe', 'newsletter',
            'sign up', 'create account', 'download app', 'notification'
        ]
        content_lower = (page_title + ' ' + page_content[:500]).lower()
        return any(ind in content_lower for ind in popup_indicators)


# =============================================================================
# 3. DATA VALIDATION
# =============================================================================

class DataValidator:
    """
    Validate extracted data for quality and completeness.

    Usage:
        validator = DataValidator()
        is_valid, errors = validator.validate_contact({
            'email': 'test@example.com',
            'phone': '555-1234'
        })
    """

    # Regex patterns for common data types
    PATTERNS = {
        'email': r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$',
        'phone': r'^[\d\s\-\+\(\)\.]{7,20}$',
        'url': r'^https?://[^\s<>"{}|\\^`\[\]]+$',
        'linkedin_url': r'linkedin\.com/(in|company)/[\w\-]+',
        'twitter_handle': r'^@?[a-zA-Z0-9_]{1,15}$',
    }

    # Known garbage patterns (bot traps, placeholders)
    GARBAGE_PATTERNS = [
        r'example\.com',
        r'test@test',
        r'xxx@',
        r'noreply@',
        r'no-reply@',
        r'donotreply@',
        r'\*\*\*',
        r'placeholder',
        r'your-?email',
        r'name@domain',
    ]

    def validate_email(self, email: str) -> tuple:
        """Validate email format and quality."""
        if not email or not isinstance(email, str):
            return False, "Empty or invalid email"

        email = email.strip().lower()

        # Check format
        if not re.match(self.PATTERNS['email'], email):
            return False, f"Invalid email format: {email}"

        # Check for garbage
        for pattern in self.GARBAGE_PATTERNS:
            if re.search(pattern, email, re.IGNORECASE):
                return False, f"Garbage email detected: {email}"

        return True, "Valid"

    def validate_phone(self, phone: str) -> tuple:
        """Validate phone number format."""
        if not phone or not isinstance(phone, str):
            return False, "Empty or invalid phone"

        # Remove common formatting
        cleaned = re.sub(r'[\s\-\(\)\.]', '', phone)

        # Check length (should be 7-15 digits)
        digits_only = re.sub(r'[^\d]', '', cleaned)
        if len(digits_only) < 7 or len(digits_only) > 15:
            return False, f"Invalid phone length: {phone}"

        # Check for obvious garbage
        if digits_only in ['0000000', '1111111', '1234567', '9999999']:
            return False, f"Garbage phone detected: {phone}"

        return True, "Valid"

    def validate_url(self, url: str) -> tuple:
        """Validate URL format."""
        if not url or not isinstance(url, str):
            return False, "Empty or invalid URL"

        url = url.strip()

        # Add protocol if missing
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        if not re.match(self.PATTERNS['url'], url):
            return False, f"Invalid URL format: {url}"

        return True, "Valid"

    def validate_contact(self, data: Dict[str, Any]) -> tuple:
        """Validate a contact record."""
        errors = []

        if 'email' in data and data['email']:
            valid, msg = self.validate_email(data['email'])
            if not valid:
                errors.append(f"email: {msg}")

        if 'phone' in data and data['phone']:
            valid, msg = self.validate_phone(data['phone'])
            if not valid:
                errors.append(f"phone: {msg}")

        if 'website' in data and data['website']:
            valid, msg = self.validate_url(data['website'])
            if not valid:
                errors.append(f"website: {msg}")

        # Check for minimum required fields
        has_contact = any([
            data.get('email'),
            data.get('phone'),
            data.get('website'),
        ])
        if not has_contact:
            errors.append("No contact information found")

        return len(errors) == 0, errors

    def clean_extracted_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Clean and normalize extracted data."""
        cleaned = {}

        for key, value in data.items():
            if value is None:
                continue

            if isinstance(value, str):
                # Strip whitespace
                value = value.strip()

                # Remove common garbage
                if value.lower() in ['n/a', 'na', 'none', 'null', '-', '']:
                    continue

                # Normalize emails
                if key == 'email' or '@' in value:
                    value = value.lower()

            cleaned[key] = value

        return cleaned


# Global instance
_data_validator = None

def get_data_validator() -> DataValidator:
    global _data_validator
    if _data_validator is None:
        _data_validator = DataValidator()
    return _data_validator


# =============================================================================
# 4. SELF-CORRECTION
# =============================================================================

@dataclass
class ActionRecord:
    """Record of an action for potential rollback."""
    action_type: str
    args: Dict[str, Any]
    timestamp: float
    url_before: str
    url_after: str = ''
    success: bool = True
    reversible: bool = False
    reverse_action: Optional[Dict] = None


class SelfCorrector:
    """
    Track actions and provide undo/correction capabilities.

    Usage:
        corrector = SelfCorrector()
        corrector.record_action('click', {'selector': '#btn'}, url_before='...')
        if something_went_wrong:
            await corrector.undo_last(mcp_client)
    """

    def __init__(self, max_history: int = 50):
        self.history: List[ActionRecord] = []
        self.max_history = max_history
        self.failure_patterns: Dict[str, int] = defaultdict(int)

    def record_action(
        self,
        action_type: str,
        args: Dict[str, Any],
        url_before: str,
        url_after: str = '',
        success: bool = True
    ):
        """Record an action for potential rollback."""
        # Determine if action is reversible
        reversible = action_type in ['click', 'navigate', 'fill']
        reverse_action = None

        if action_type == 'navigate' and url_before:
            reverse_action = {'action': 'navigate', 'url': url_before}
        elif action_type == 'fill':
            reverse_action = {'action': 'fill', 'selector': args.get('selector'), 'value': ''}

        record = ActionRecord(
            action_type=action_type,
            args=args,
            timestamp=time.time(),
            url_before=url_before,
            url_after=url_after,
            success=success,
            reversible=reversible,
            reverse_action=reverse_action
        )

        self.history.append(record)
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]

        # Track failure patterns
        if not success:
            key = f"{action_type}:{args.get('selector', args.get('url', 'unknown'))}"
            self.failure_patterns[key] += 1

    async def undo_last(self, mcp_client) -> bool:
        """Undo the last reversible action."""
        for record in reversed(self.history):
            if record.reversible and record.reverse_action:
                try:
                    action = record.reverse_action
                    if action['action'] == 'navigate':
                        await mcp_client.call_tool('playwright_navigate', {'url': action['url']})
                        logger.info(f"[UNDO] Navigated back to {action['url']}")
                        return True
                except Exception as e:
                    logger.error(f"[UNDO] Failed: {e}")

        return False

    def get_failure_count(self, action_type: str, selector_or_url: str) -> int:
        """Get how many times this action/selector has failed."""
        key = f"{action_type}:{selector_or_url}"
        return self.failure_patterns.get(key, 0)

    def should_try_alternative(self, action_type: str, selector: str, threshold: int = 2) -> bool:
        """Check if we should try an alternative approach."""
        return self.get_failure_count(action_type, selector) >= threshold

    def detect_loop(self, window: int = 5) -> bool:
        """Detect if we're in a loop (same URL visited multiple times)."""
        if len(self.history) < window:
            return False

        recent_urls = [r.url_after for r in self.history[-window:] if r.url_after]
        if len(recent_urls) < window:
            return False

        # Check if more than half are the same URL
        url_counts = defaultdict(int)
        for url in recent_urls:
            url_counts[url] += 1

        max_count = max(url_counts.values()) if url_counts else 0
        return max_count >= window // 2 + 1


# =============================================================================
# 5. DOOM LOOP GUARD
# =============================================================================

@dataclass
class CallRecord:
    """Record of a tool call for doom loop detection."""
    tool_name: str
    args_hash: str
    timestamp: float


class DoomLoopGuard:
    """
    Detect when the same tool is called repeatedly with identical arguments.

    This prevents the agent from getting stuck calling the same failing tool
    over and over (the "doom loop").

    Usage:
        guard = DoomLoopGuard()
        is_loop, reason = guard.check_call('playwright_click', {'selector': '#btn'})
        if is_loop:
            # Skip this call or escalate
            pass
    """

    def __init__(self, threshold: int = 3, time_window: Optional[float] = None, history_size: int = 50):
        """
        Initialize the doom loop guard.

        Args:
            threshold: Number of identical calls in recent history to trigger (default: 3)
            time_window: Optional time window in seconds to check (default: None = all time)
            history_size: Maximum number of calls to keep in history (default: 50)
        """
        self.threshold = threshold
        self.time_window = time_window
        self.history_size = history_size
        self.call_history: List[CallRecord] = []

    def _hash_args(self, args: Any) -> str:
        """Create a stable hash of tool arguments."""
        if args is None:
            return "none"

        if isinstance(args, dict):
            # Sort dict keys for stable hash
            sorted_items = sorted(args.items())
            return str(sorted_items)

        return str(args)

    def check_call(self, tool_name: str, args: Any) -> tuple:
        """
        Check if this call would trigger a doom loop.

        Args:
            tool_name: Name of the tool being called
            args: Arguments being passed to the tool

        Returns:
            Tuple of (is_doom_loop: bool, reason: str)
        """
        current_time = time.time()
        args_hash = self._hash_args(args)

        # Filter history by time window if specified
        if self.time_window:
            relevant_history = [
                record for record in self.call_history
                if current_time - record.timestamp <= self.time_window
            ]
        else:
            relevant_history = self.call_history

        # Look at last N calls (configurable window)
        recent_calls = relevant_history[-5:] if len(relevant_history) >= 5 else relevant_history

        # Count identical calls in recent history
        identical_count = sum(
            1 for record in recent_calls
            if record.tool_name == tool_name and record.args_hash == args_hash
        )

        # Check if we've hit the threshold
        if identical_count >= self.threshold:
            return True, f"Tool '{tool_name}' called {identical_count} times with identical args in last {len(recent_calls)} calls"

        return False, "OK"

    def record_call(self, tool_name: str, args: Any):
        """
        Record a tool call in the history.

        Args:
            tool_name: Name of the tool being called
            args: Arguments being passed to the tool
        """
        args_hash = self._hash_args(args)
        record = CallRecord(
            tool_name=tool_name,
            args_hash=args_hash,
            timestamp=time.time()
        )

        self.call_history.append(record)

        # Keep history size bounded
        if len(self.call_history) > self.history_size:
            self.call_history = self.call_history[-self.history_size:]

    def reset(self):
        """Clear the call history."""
        self.call_history = []

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about recent calls."""
        if not self.call_history:
            return {
                'total_calls': 0,
                'unique_calls': 0,
                'most_common': None
            }

        # Count calls by (tool_name, args_hash)
        call_counts = defaultdict(int)
        for record in self.call_history:
            key = (record.tool_name, record.args_hash)
            call_counts[key] += 1

        # Find most common call
        most_common = max(call_counts.items(), key=lambda x: x[1]) if call_counts else None

        return {
            'total_calls': len(self.call_history),
            'unique_calls': len(call_counts),
            'most_common': {
                'tool': most_common[0][0],
                'count': most_common[1]
            } if most_common else None
        }


# Global instance
_doom_loop_guard = None


def get_doom_loop_guard() -> DoomLoopGuard:
    """Get or create the global DoomLoopGuard instance."""
    global _doom_loop_guard
    if _doom_loop_guard is None:
        _doom_loop_guard = DoomLoopGuard()
    return _doom_loop_guard


# =============================================================================
# 6. DIRECTORY BOUNDARY GUARD
# =============================================================================

import os
from pathlib import Path


class DirectoryBoundaryGuard:
    """
    Prevent file operations outside the allowed working directory.

    Protects against path traversal attacks and accidental file access
    outside the designated workspace.

    Usage:
        guard = DirectoryBoundaryGuard('/home/user/project')
        allowed, reason = guard.check_access('/home/user/project/file.txt')
        if allowed:
            # Safe to proceed
            ...
    """

    def __init__(self, working_dir: str):
        """
        Initialize the guard with a working directory.

        Args:
            working_dir: The root directory where file operations are allowed
        """
        # Resolve working_dir to absolute path and resolve symlinks
        self.working_dir = Path(working_dir).resolve()

        # Whitelist of always-allowed paths (e.g., /tmp)
        self.whitelist: List[Path] = [
            Path('/tmp').resolve(),
            Path('/var/tmp').resolve(),
        ]

        # Temporary permissions (for specific paths granted at runtime)
        self.temp_permissions: List[Path] = []

        logger.info(f"[DIRECTORY_GUARD] Working directory: {self.working_dir}")
        logger.info(f"[DIRECTORY_GUARD] Whitelist: {[str(p) for p in self.whitelist]}")

    def check_access(self, path: str) -> tuple:
        """
        Check if access to the given path is allowed.

        Args:
            path: The file/directory path to check

        Returns:
            Tuple of (allowed: bool, reason: str)
        """
        try:
            # Resolve to absolute path and follow symlinks
            target_path = Path(path).resolve()

            # Check if path is within working directory
            try:
                # This will raise ValueError if target_path is not relative to working_dir
                target_path.relative_to(self.working_dir)
                return True, "Within working directory"
            except ValueError:
                pass  # Not within working_dir, check whitelist

            # Check whitelist
            for allowed_path in self.whitelist:
                try:
                    target_path.relative_to(allowed_path)
                    return True, f"In whitelist: {allowed_path}"
                except ValueError:
                    continue

            # Check temporary permissions
            for temp_path in self.temp_permissions:
                try:
                    target_path.relative_to(temp_path)
                    return True, f"Temporary permission: {temp_path}"
                except ValueError:
                    continue

            # Access denied
            return False, f"Path outside allowed boundaries: {target_path}"

        except Exception as e:
            # Any error in resolution means deny access
            return False, f"Path resolution error: {str(e)}"

    def add_temporary_permission(self, path: str):
        """
        Grant temporary access to a specific path.

        Useful for one-off operations like reading config files
        outside the working directory.

        Args:
            path: Path to grant temporary access to
        """
        try:
            resolved = Path(path).resolve()
            if resolved not in self.temp_permissions:
                self.temp_permissions.append(resolved)
                logger.info(f"[DIRECTORY_GUARD] Added temporary permission: {resolved}")
        except Exception as e:
            logger.warning(f"[DIRECTORY_GUARD] Failed to add temp permission for {path}: {e}")

    def remove_temporary_permission(self, path: str):
        """
        Remove a temporary permission.

        Args:
            path: Path to revoke temporary access from
        """
        try:
            resolved = Path(path).resolve()
            if resolved in self.temp_permissions:
                self.temp_permissions.remove(resolved)
                logger.info(f"[DIRECTORY_GUARD] Removed temporary permission: {resolved}")
        except Exception as e:
            logger.warning(f"[DIRECTORY_GUARD] Failed to remove temp permission for {path}: {e}")

    def clear_temporary_permissions(self):
        """Clear all temporary permissions."""
        count = len(self.temp_permissions)
        self.temp_permissions.clear()
        logger.info(f"[DIRECTORY_GUARD] Cleared {count} temporary permissions")

    def add_to_whitelist(self, path: str):
        """
        Add a path to the permanent whitelist.

        Args:
            path: Path to whitelist
        """
        try:
            resolved = Path(path).resolve()
            if resolved not in self.whitelist:
                self.whitelist.append(resolved)
                logger.info(f"[DIRECTORY_GUARD] Added to whitelist: {resolved}")
        except Exception as e:
            logger.warning(f"[DIRECTORY_GUARD] Failed to add to whitelist {path}: {e}")


# Global instance (initialized on first use)
_directory_guard = None


def get_directory_guard(working_dir: str = None) -> DirectoryBoundaryGuard:
    """
    Get or create the global DirectoryBoundaryGuard instance.

    Args:
        working_dir: Working directory (required on first call)

    Returns:
        DirectoryBoundaryGuard instance
    """
    global _directory_guard
    if _directory_guard is None:
        if working_dir is None:
            # Default to current working directory
            working_dir = os.getcwd()
        _directory_guard = DirectoryBoundaryGuard(working_dir)
    return _directory_guard


# =============================================================================
# 7. HUMAN ESCALATION
# =============================================================================

@dataclass
class StuckState:
    """Track when agent is stuck and needs human help."""
    consecutive_failures: int = 0
    same_page_count: int = 0
    last_successful_action: float = 0
    escalation_reasons: List[str] = field(default_factory=list)


class HumanEscalator:
    """
    Detect when agent is truly stuck and should ask for human help.

    Usage:
        escalator = HumanEscalator()
        escalator.record_outcome(success=False, reason="Element not found")
        if escalator.should_escalate():
            options = escalator.get_escalation_options()
            # Present to user
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        same_page_threshold: int = 3,
        time_threshold: float = 120.0  # 2 minutes without progress
    ):
        self.failure_threshold = failure_threshold
        self.same_page_threshold = same_page_threshold
        self.time_threshold = time_threshold

        self.state = StuckState()
        self.last_url = ''
        self.start_time = time.time()

    def record_outcome(self, success: bool, reason: str = '', current_url: str = ''):
        """Record the outcome of an action."""
        if success:
            self.state.consecutive_failures = 0
            self.state.same_page_count = 0
            self.state.last_successful_action = time.time()
            self.state.escalation_reasons = []
        else:
            self.state.consecutive_failures += 1
            if reason:
                self.state.escalation_reasons.append(reason)

        # Track same-page detection
        if current_url:
            if current_url == self.last_url:
                self.state.same_page_count += 1
            else:
                self.state.same_page_count = 0
            self.last_url = current_url

    def should_escalate(self) -> bool:
        """Check if we should escalate to human."""
        # Too many consecutive failures
        if self.state.consecutive_failures >= self.failure_threshold:
            return True

        # Stuck on same page
        if self.state.same_page_count >= self.same_page_threshold:
            return True

        # No progress for too long
        if self.state.last_successful_action > 0:
            time_since_success = time.time() - self.state.last_successful_action
            if time_since_success >= self.time_threshold:
                return True

        return False

    def get_escalation_message(self) -> str:
        """Get a message explaining why escalation is needed."""
        reasons = []

        if self.state.consecutive_failures >= self.failure_threshold:
            reasons.append(f"{self.state.consecutive_failures} consecutive failures")

        if self.state.same_page_count >= self.same_page_threshold:
            reasons.append(f"stuck on same page {self.state.same_page_count} times")

        if self.state.last_successful_action > 0:
            elapsed = time.time() - self.state.last_successful_action
            if elapsed >= self.time_threshold:
                reasons.append(f"no progress for {elapsed:.0f}s")

        recent_errors = list(set(self.state.escalation_reasons[-3:]))

        msg = "I'm having trouble completing this task.\n"
        msg += f"Issues: {', '.join(reasons)}\n"
        if recent_errors:
            msg += f"Recent errors: {', '.join(recent_errors)}\n"

        return msg

    def get_escalation_options(self) -> List[Dict[str, str]]:
        """Get options to present to user."""
        return [
            {'key': '1', 'label': 'Retry with different approach', 'action': 'retry'},
            {'key': '2', 'label': 'Skip this step and continue', 'action': 'skip'},
            {'key': '3', 'label': 'Take manual control (I will do it)', 'action': 'manual'},
            {'key': '4', 'label': 'Abort task', 'action': 'abort'},
            {'key': '5', 'label': 'Give me a hint (describe what you see)', 'action': 'describe'},
        ]

    def reset(self):
        """Reset escalation state."""
        self.state = StuckState()
        self.last_url = ''


# =============================================================================
# INTEGRATION HELPERS
# =============================================================================

async def safe_action_with_guards(
    mcp_client,
    action: str,
    args: Dict[str, Any],
    corrector: SelfCorrector,
    guard: Optional[NavigationGuard] = None,
    timeout_mgr: Optional[AdaptiveTimeout] = None
) -> Dict[str, Any]:
    """
    Execute an action with all guards active.

    Returns:
        Dict with 'success', 'result', 'corrections_made', 'warnings'
    """
    result = {
        'success': False,
        'result': None,
        'corrections_made': [],
        'warnings': []
    }

    # Get current URL for tracking
    try:
        snap = await mcp_client.call_tool('playwright_snapshot', {})
        url_before = snap.get('url', '')
    except Exception:
        url_before = ''

    # Get adaptive timeout
    domain = ''
    if url_before:
        try:
            from urllib.parse import urlparse
            domain = urlparse(url_before).netloc
        except Exception:
            pass

    timeout = 10.0
    if timeout_mgr:
        timeout = timeout_mgr.get_timeout(domain, action)

    # Check if we should try alternative (too many failures)
    if corrector.should_try_alternative(action, str(args)):
        result['warnings'].append(f"Previous failures detected for {action}")

    # Execute action with timeout
    start_time = time.time()
    try:
        tool_name = f'playwright_{action}' if not action.startswith('playwright_') else action
        action_result = await asyncio.wait_for(
            mcp_client.call_tool(tool_name, args),
            timeout=timeout
        )
        duration = time.time() - start_time

        # Record timing for learning
        if timeout_mgr and domain:
            timeout_mgr.record_duration(domain, action, duration)

        success = action_result.get('success', True)
        result['success'] = success
        result['result'] = action_result

    except asyncio.TimeoutError:
        duration = time.time() - start_time
        result['warnings'].append(f"Action timed out after {timeout:.1f}s")
        success = False

    except Exception as e:
        result['warnings'].append(f"Action failed: {str(e)}")
        success = False

    # Get URL after action
    try:
        snap = await mcp_client.call_tool('playwright_snapshot', {})
        url_after = snap.get('url', '')
    except Exception:
        url_after = url_before

    # Record for self-correction
    corrector.record_action(action, args, url_before, url_after, success)

    # Check navigation guard
    if guard and url_after:
        is_ok, reason = guard.check_url(url_after)
        if not is_ok:
            result['warnings'].append(f"Navigation guard: {reason}")
            # Try to go back
            if await corrector.undo_last(mcp_client):
                result['corrections_made'].append("Navigated back (off-task detected)")

    # Check for loops
    if corrector.detect_loop():
        result['warnings'].append("Loop detected - same actions repeating")

    return result


# Convenience function to get all guards
def create_guards(target_domain: str = '', target_keywords: List[str] = None):
    """Create a set of guards for a task."""
    return {
        'timeout': get_adaptive_timeout(),
        'validator': get_data_validator(),
        'corrector': SelfCorrector(),
        'guard': NavigationGuard(
            target_domain=target_domain,
            target_keywords=target_keywords or []
        ),
        'escalator': HumanEscalator()
    }
