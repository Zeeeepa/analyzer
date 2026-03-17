#!/usr/bin/env python3
"""
Retry Handler v2 - Auto-fix errors and retry failed operations
Learns from errors and adjusts approach automatically
"""

import asyncio
from typing import Dict, List, Any, Optional, Callable, Tuple
from dataclasses import dataclass
from loguru import logger


@dataclass
class RetryAttempt:
    """Record of a retry attempt"""
    attempt_number: int
    error: str
    fix_applied: str
    arguments_before: Dict[str, Any]
    arguments_after: Dict[str, Any]
    success: bool


class RetryHandler:
    """Intelligent retry logic with auto-fix capabilities"""

    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
        self.retry_history: List[RetryAttempt] = []

        # Error pattern → Fix function mapping
        self.error_fixes = {
            'timeout': self._fix_timeout,
            'selector not found': self._fix_selector,
            'element not visible': self._fix_visibility,
            'navigation failed': self._fix_navigation,
            'invalid url': self._fix_url,
            'connection': self._fix_connection,
            'rate limit': self._fix_rate_limit,
        }

    async def execute_with_retry(
        self,
        function: str,
        arguments: Dict[str, Any],
        executor: Callable,
        context: Optional[str] = None
    ) -> Tuple[bool, Any, Optional[str]]:
        """
        Execute function with automatic retry and error fixing
        Returns: (success, result, error_message)
        """

        for attempt in range(1, self.max_retries + 1):
            logger.info(f"Attempt {attempt}/{self.max_retries}: {function}")

            try:
                # Execute the function
                result = await executor(function, arguments)

                logger.success(f"✓ {function} succeeded on attempt {attempt}")
                return True, result, None

            except Exception as e:
                error_msg = str(e).lower()
                logger.warning(f"✗ {function} failed: {e}")

                # Last attempt - give up
                if attempt >= self.max_retries:
                    logger.error(f"Failed after {self.max_retries} attempts")
                    return False, None, str(e)

                # Try to fix the error
                fixed_args, fix_applied = self._apply_fix(
                    function, arguments, error_msg, attempt
                )

                if fixed_args is None:
                    logger.warning(f"No fix available for error: {error_msg}")
                    # Try again with same args (transient error?)
                    await asyncio.sleep(1 * attempt)  # Exponential backoff
                    continue

                # Record retry attempt
                self.retry_history.append(RetryAttempt(
                    attempt_number=attempt,
                    error=str(e),
                    fix_applied=fix_applied,
                    arguments_before=arguments.copy(),
                    arguments_after=fixed_args.copy(),
                    success=False
                ))

                logger.info(f"Applied fix: {fix_applied}")
                arguments = fixed_args

                # Wait before retry (exponential backoff)
                await asyncio.sleep(1 * attempt)

        return False, None, "Max retries exceeded"

    def _apply_fix(
        self,
        function: str,
        arguments: Dict[str, Any],
        error: str,
        attempt: int
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        """
        Apply appropriate fix based on error type
        Returns: (fixed_arguments, fix_description)
        """

        # Match error to fix function
        for error_pattern, fix_func in self.error_fixes.items():
            if error_pattern in error:
                fixed_args, fix_desc = fix_func(function, arguments, error, attempt)
                if fixed_args:
                    return fixed_args, fix_desc

        # No specific fix found - try generic fixes
        return self._generic_fix(function, arguments, attempt)

    def _fix_timeout(
        self,
        function: str,
        arguments: Dict[str, Any],
        error: str,
        attempt: int
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        """Fix timeout errors by increasing timeout"""

        fixed = arguments.copy()

        # Increase timeout if present
        if 'timeout' in fixed:
            fixed['timeout'] = fixed['timeout'] * 2
            return fixed, f"Increased timeout to {fixed['timeout']}ms"

        # Add timeout if missing
        fixed['timeout'] = 30000 * attempt  # 30s, 60s, 90s
        return fixed, f"Added timeout: {fixed['timeout']}ms"

    def _fix_selector(
        self,
        function: str,
        arguments: Dict[str, Any],
        error: str,
        attempt: int
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        """Fix selector not found errors"""

        if 'selector' not in arguments:
            return None, "No selector to fix"

        fixed = arguments.copy()
        selector = arguments['selector']

        # Attempt 1: Make selector more generic
        if attempt == 1:
            # Remove :nth-child, :first-child, etc
            generic = re.sub(r':nth-child\(\d+\)', '', selector)
            generic = re.sub(r':first-child|:last-child', '', generic)

            if generic != selector:
                fixed['selector'] = generic
                return fixed, f"Simplified selector: {generic}"

            # Try without attribute value
            if '[' in selector:
                # input[name="search"] → input[name]
                generic = re.sub(r'=("[^"]*"|\'[^\']*\')', '', selector)
                fixed['selector'] = generic
                return fixed, f"Simplified attribute selector: {generic}"

        # Attempt 2: Try alternative selectors
        if attempt == 2:
            alternatives = self._generate_alternative_selectors(selector)
            if alternatives:
                fixed['selector'] = alternatives[0]
                return fixed, f"Trying alternative selector: {alternatives[0]}"

        return None, "Could not fix selector"

    def _fix_visibility(
        self,
        function: str,
        arguments: Dict[str, Any],
        error: str,
        attempt: int
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        """Fix element not visible errors"""

        fixed = arguments.copy()

        # Add wait for selector to be visible
        if 'force' not in fixed:
            fixed['force'] = True
            return fixed, "Added force:true to bypass visibility check"

        # Try scrolling into view first
        if 'scroll' not in fixed:
            fixed['scroll'] = True
            return fixed, "Will scroll element into view"

        return None, "Could not fix visibility issue"

    def _fix_navigation(
        self,
        function: str,
        arguments: Dict[str, Any],
        error: str,
        attempt: int
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        """Fix navigation failures"""

        if 'url' not in arguments:
            return None, "No URL to fix"

        fixed = arguments.copy()
        url = arguments['url']

        # Attempt 1: Try https if http
        if attempt == 1 and url.startswith('http://'):
            fixed['url'] = url.replace('http://', 'https://')
            return fixed, f"Changed to HTTPS: {fixed['url']}"

        # Attempt 2: Add www if missing
        if attempt == 2 and 'www.' not in url:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            new_netloc = f"www.{parsed.netloc}"
            fixed['url'] = f"{parsed.scheme}://{new_netloc}{parsed.path}"
            return fixed, f"Added www: {fixed['url']}"

        # Attempt 3: Remove www if present
        if attempt == 3 and 'www.' in url:
            fixed['url'] = url.replace('www.', '')
            return fixed, f"Removed www: {fixed['url']}"

        return None, "Could not fix navigation"

    def _fix_url(
        self,
        function: str,
        arguments: Dict[str, Any],
        error: str,
        attempt: int
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        """Fix invalid URL formats"""

        if 'url' not in arguments:
            return None, "No URL to fix"

        fixed = arguments.copy()
        url = arguments['url']

        # Add protocol if missing
        if not url.startswith(('http://', 'https://')):
            fixed['url'] = f'https://{url}'
            return fixed, f"Added protocol: {fixed['url']}"

        # Remove spaces
        if ' ' in url:
            fixed['url'] = url.replace(' ', '')
            return fixed, f"Removed spaces: {fixed['url']}"

        # Fix double slashes
        if '//' in url.replace('://', ''):
            fixed['url'] = url.replace('://', '|||').replace('//', '/').replace('|||', '://')
            return fixed, f"Fixed double slashes: {fixed['url']}"

        return None, "Could not fix URL"

    def _fix_connection(
        self,
        function: str,
        arguments: Dict[str, Any],
        error: str,
        attempt: int
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        """Fix connection errors"""

        # Connection errors are usually transient
        # Just wait longer before retry
        return arguments.copy(), f"Waiting {attempt * 2}s before retry (connection error)"

    def _fix_rate_limit(
        self,
        function: str,
        arguments: Dict[str, Any],
        error: str,
        attempt: int
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        """Fix rate limit errors"""

        # Wait exponentially longer
        wait_time = 5 * (2 ** attempt)  # 10s, 20s, 40s
        return arguments.copy(), f"Rate limited - waiting {wait_time}s"

    def _generic_fix(
        self,
        function: str,
        arguments: Dict[str, Any],
        attempt: int
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        """Generic fixes when no specific error pattern matched"""

        fixed = arguments.copy()

        # Add longer timeout
        if 'timeout' not in fixed:
            fixed['timeout'] = 30000
            return fixed, "Added timeout (generic fix)"

        # Increase existing timeout
        if 'timeout' in fixed:
            fixed['timeout'] *= 2
            return fixed, f"Increased timeout to {fixed['timeout']}ms (generic fix)"

        return None, "No generic fix applicable"

    def _generate_alternative_selectors(self, selector: str) -> List[str]:
        """Generate alternative selectors to try"""
        alternatives = []

        # If it's an ID, try as class
        if selector.startswith('#'):
            alternatives.append(f".{selector[1:]}")

        # If it's a class, try as attribute
        if selector.startswith('.'):
            alternatives.append(f"[class*=\"{selector[1:]}\"]")

        # If it has an attribute, try without value
        if '[' in selector and '=' in selector:
            import re
            no_value = re.sub(r'=("[^"]*"|\'[^\']*\')', '', selector)
            alternatives.append(no_value)

        # Try more generic version
        if ' > ' in selector:  # Direct child
            generic = selector.replace(' > ', ' ')  # Any descendant
            alternatives.append(generic)

        return alternatives

    def get_retry_stats(self) -> Dict[str, Any]:
        """Get statistics about retry attempts"""
        if not self.retry_history:
            return {
                "total_retries": 0,
                "fixes_applied": [],
                "success_rate": 0.0
            }

        total = len(self.retry_history)
        successful = sum(1 for r in self.retry_history if r.success)
        fixes = [r.fix_applied for r in self.retry_history]

        return {
            "total_retries": total,
            "successful_fixes": successful,
            "success_rate": (successful / total) * 100 if total > 0 else 0,
            "fixes_applied": fixes,
            "recent_attempts": self.retry_history[-5:]  # Last 5
        }


# Singleton instance
retry_handler = RetryHandler(max_retries=3)


async def execute_with_retry(
    function: str,
    arguments: Dict[str, Any],
    executor: Callable,
    context: Optional[str] = None
) -> Tuple[bool, Any, Optional[str]]:
    """Convenience function for retry execution"""
    return await retry_handler.execute_with_retry(
        function, arguments, executor, context
    )
