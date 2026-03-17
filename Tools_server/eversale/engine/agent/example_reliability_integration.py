"""
Example: Integrating reliability_core into existing tools

This demonstrates how to wrap existing browser tools with reliability_core
for production-ready error handling, retry logic, and validation.
"""

import asyncio
import time
from typing import Optional
from loguru import logger

from reliability_core import (
    ToolResult,
    BrowserHealthCheck,
    ReliableExecutor,
    InputValidator,
    TimeoutConfig,
    create_success_result,
    create_error_result,
    create_validation_error,
    create_timeout_result
)


# =============================================================================
# EXAMPLE 1: Simple Tool Wrapper
# =============================================================================

async def click_element(page, selector: str) -> ToolResult:
    """
    Click an element with validation and error handling.

    This is the basic pattern for wrapping any browser operation.
    """
    start_time = time.time()
    validator = InputValidator()

    # Step 1: Validate input
    is_valid, error = validator.validate_selector(selector)
    if not is_valid:
        return create_validation_error("selector", error)

    # Step 2: Execute with try/catch
    try:
        await page.click(
            selector,
            timeout=TimeoutConfig.to_ms(TimeoutConfig.NORMAL)
        )

        duration_ms = int((time.time() - start_time) * 1000)
        logger.info(f"[CLICK] Clicked {selector} in {duration_ms}ms")

        return create_success_result(
            data={"selector": selector, "action": "clicked"},
            duration_ms=duration_ms
        )

    except asyncio.TimeoutError:
        duration_ms = int((time.time() - start_time) * 1000)
        return create_timeout_result("Click", TimeoutConfig.NORMAL)

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(f"[CLICK] Failed to click {selector}: {e}")

        return create_error_result(
            error=str(e),
            error_code="CLICK_FAILED",
            duration_ms=duration_ms
        )


# =============================================================================
# EXAMPLE 2: Navigation with Retry
# =============================================================================

async def navigate_to_url(page, url: str) -> ToolResult:
    """
    Navigate to URL with validation and retry logic.

    This shows how to combine validation + retry for robust navigation.
    """
    validator = InputValidator()

    # Validate URL first
    is_valid, error = validator.validate_url(url)
    if not is_valid:
        return create_validation_error("url", error)

    # Execute with retry
    executor = ReliableExecutor()

    async def do_navigation():
        await page.goto(url, wait_until="domcontentloaded")
        return {"url": url, "status": "loaded"}

    result = await executor.execute(
        operation=do_navigation,
        timeout=TimeoutConfig.SLOW,  # Navigation can be slow
        retries=2,
        backoff=True
    )

    if result.success:
        logger.info(f"[NAV] Navigated to {url} in {result.duration_ms}ms")
    else:
        logger.error(f"[NAV] Failed to navigate to {url}: {result.error}")

    return result


# =============================================================================
# EXAMPLE 3: Form Fill with Health Check
# =============================================================================

async def fill_form_field(page, selector: str, value: str) -> ToolResult:
    """
    Fill form field with health check and validation.

    This demonstrates checking browser health before critical operations.
    """
    start_time = time.time()
    validator = InputValidator()
    health = BrowserHealthCheck()

    # Validate inputs
    is_valid, error = validator.validate_selector(selector)
    if not is_valid:
        return create_validation_error("selector", error)

    is_valid, error = validator.validate_text_input(value, max_length=1000)
    if not is_valid:
        return create_validation_error("value", error)

    # Check browser health before proceeding
    if not await health.check_browser_alive(page):
        logger.warning("[FORM] Browser unresponsive, attempting recovery")
        recovery_result = await health.recover_browser(page)
        if not recovery_result.success:
            return recovery_result

    # Wait for page to be ready
    ready_result = await health.wait_for_ready(page, timeout=TimeoutConfig.NORMAL)
    if not ready_result.success:
        return ready_result

    # Execute form fill
    try:
        await page.fill(
            selector,
            value,
            timeout=TimeoutConfig.to_ms(TimeoutConfig.NORMAL)
        )

        duration_ms = int((time.time() - start_time) * 1000)
        logger.info(f"[FORM] Filled {selector} in {duration_ms}ms")

        return create_success_result(
            data={"selector": selector, "value_length": len(value)},
            duration_ms=duration_ms
        )

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        return create_error_result(str(e), "FILL_FAILED", duration_ms)


# =============================================================================
# EXAMPLE 4: Batch Operations with Statistics
# =============================================================================

async def process_multiple_elements(page, selectors: list) -> dict:
    """
    Process multiple elements and track success rate.

    This shows how to use ReliableExecutor for batch operations with stats.
    """
    executor = ReliableExecutor()
    results = []

    for selector in selectors:
        async def click_op():
            await page.click(
                selector,
                timeout=TimeoutConfig.to_ms(TimeoutConfig.FAST)
            )
            return selector

        result = await executor.execute(
            operation=click_op,
            timeout=TimeoutConfig.FAST,
            retries=1,
            backoff=True
        )

        results.append({
            "selector": selector,
            "success": result.success,
            "error": result.error,
            "duration_ms": result.duration_ms
        })

        if not result.success:
            logger.warning(f"[BATCH] Failed {selector}: {result.error}")

    # Get overall statistics
    stats = executor.get_stats()

    return {
        "results": results,
        "stats": stats,
        "success_rate": stats.get("success_rate_pct", 0)
    }


# =============================================================================
# EXAMPLE 5: Complex Operation with Full Error Handling
# =============================================================================

async def login_with_retry(
    page,
    username: str,
    password: str,
    login_url: str
) -> ToolResult:
    """
    Complete login flow with validation, health checks, and retry.

    This is a comprehensive example showing all patterns together.
    """
    start_time = time.time()
    validator = InputValidator()
    health = BrowserHealthCheck()
    executor = ReliableExecutor()

    # Step 1: Validate all inputs
    is_valid, error = validator.validate_url(login_url)
    if not is_valid:
        return create_validation_error("login_url", error)

    is_valid, error = validator.validate_text_input(username)
    if not is_valid:
        return create_validation_error("username", error)

    is_valid, error = validator.validate_text_input(password)
    if not is_valid:
        return create_validation_error("password", error)

    # Step 2: Navigate with retry
    nav_result = await navigate_to_url(page, login_url)
    if not nav_result.success:
        return nav_result

    # Step 3: Check browser health
    if not await health.check_browser_alive(page):
        logger.warning("[LOGIN] Browser unresponsive")
        recovery = await health.recover_browser(page)
        if not recovery.success:
            return recovery

    # Step 4: Fill form with retry
    async def fill_username():
        await page.fill("#username", username)

    async def fill_password():
        await page.fill("#password", password)

    async def click_submit():
        await page.click("button[type=submit]")

    # Execute each step with retry
    for step_name, operation in [
        ("Fill username", fill_username),
        ("Fill password", fill_password),
        ("Click submit", click_submit)
    ]:
        result = await executor.execute(
            operation=operation,
            timeout=TimeoutConfig.NORMAL,
            retries=2,
            backoff=True
        )

        if not result.success:
            logger.error(f"[LOGIN] {step_name} failed: {result.error}")
            return create_error_result(
                error=f"Login failed at: {step_name}",
                error_code="LOGIN_FAILED",
                duration_ms=int((time.time() - start_time) * 1000)
            )

    # Step 5: Wait for navigation after login
    async def wait_for_redirect():
        await page.wait_for_url(lambda url: url != login_url, timeout=5000)

    redirect_result = await executor.execute(
        operation=wait_for_redirect,
        timeout=TimeoutConfig.NORMAL,
        retries=1
    )

    duration_ms = int((time.time() - start_time) * 1000)

    if redirect_result.success:
        logger.info(f"[LOGIN] Login successful in {duration_ms}ms")
        return create_success_result(
            data={"username": username, "logged_in": True},
            duration_ms=duration_ms
        )
    else:
        logger.error(f"[LOGIN] Login redirect failed: {redirect_result.error}")
        return create_error_result(
            error="Login may have failed - no redirect detected",
            error_code="NO_REDIRECT",
            duration_ms=duration_ms
        )


# =============================================================================
# EXAMPLE 6: Error Recovery Chain
# =============================================================================

async def extract_data_with_recovery(page, selector: str) -> ToolResult:
    """
    Extract data with cascading recovery strategies.

    Shows how to implement fallback strategies when primary method fails.
    """
    validator = InputValidator()

    # Validate
    is_valid, error = validator.validate_selector(selector)
    if not is_valid:
        return create_validation_error("selector", error)

    executor = ReliableExecutor()

    # Strategy 1: Try to get text content
    async def get_text():
        element = await page.query_selector(selector)
        if not element:
            raise ValueError("Element not found")
        return await element.text_content()

    result = await executor.execute(
        operation=get_text,
        timeout=TimeoutConfig.FAST,
        retries=1
    )

    if result.success:
        return result

    # Strategy 2: Try inner text
    logger.info("[EXTRACT] text_content failed, trying inner_text")

    async def get_inner_text():
        element = await page.query_selector(selector)
        if not element:
            raise ValueError("Element not found")
        return await element.inner_text()

    result = await executor.execute(
        operation=get_inner_text,
        timeout=TimeoutConfig.FAST,
        retries=1
    )

    if result.success:
        return result

    # Strategy 3: Try evaluate
    logger.info("[EXTRACT] inner_text failed, trying evaluate")

    async def get_via_evaluate():
        return await page.evaluate(
            f"document.querySelector('{selector}')?.textContent"
        )

    result = await executor.execute(
        operation=get_via_evaluate,
        timeout=TimeoutConfig.FAST,
        retries=1
    )

    if result.success:
        return result

    # All strategies failed
    return create_error_result(
        error=f"Failed to extract data from {selector} after all strategies",
        error_code="EXTRACTION_FAILED"
    )


# =============================================================================
# DEMO RUNNER
# =============================================================================

async def demo():
    """Run all examples (requires actual browser)."""
    print("\n" + "=" * 60)
    print("RELIABILITY CORE INTEGRATION EXAMPLES")
    print("=" * 60)

    print("\nThese examples show how to integrate reliability_core")
    print("into your browser automation tools.")
    print("\nPatterns demonstrated:")
    print("1. Simple tool wrapper with validation")
    print("2. Navigation with retry")
    print("3. Form fill with health check")
    print("4. Batch operations with statistics")
    print("5. Complex operation (login) with full error handling")
    print("6. Error recovery chain with fallback strategies")
    print("\nTo run these with a real browser, integrate with your")
    print("existing Playwright setup.")
    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(demo())
