# Smart Retry System - Enhanced Features Guide

## Overview

The enhanced Smart Retry system provides enterprise-grade retry logic with intelligent error handling, circuit breakers, and exponential backoff. It addresses common agent weaknesses like stuck loops, silent failures, and brittle error handling.

## Key Features (December 2024 Enhancements)

### 1. Exponential Backoff with Jitter

Prevents "thundering herd" problems where multiple retries happen simultaneously.

```python
from agent.smart_retry import BackoffCalculator, RetryStrategy

# Calculate delay with jitter
delay = BackoffCalculator.calculate_delay(
    strategy=RetryStrategy.EXPONENTIAL_JITTER,
    attempt=2,  # 3rd attempt (0-indexed)
    base_delay_ms=1000,  # Start at 1 second
    max_delay_ms=60000   # Cap at 60 seconds
)
# Result: ~4000ms + random jitter (0-25%)
```

**Available Strategies:**
- `IMMEDIATE` - No delay (0ms)
- `LINEAR` - Base × attempt (1s, 2s, 3s, 4s...)
- `EXPONENTIAL` - Base × 2^attempt (1s, 2s, 4s, 8s...)
- `EXPONENTIAL_JITTER` - Exponential + 0-25% random jitter

### 2. Per-Error-Type Retry Strategies

Different errors need different retry approaches. The system automatically classifies errors and applies the right strategy.

```python
from agent.smart_retry import ErrorClassifier, ErrorType

# Automatic classification
error_type = ErrorClassifier.classify("429 Too Many Requests")
# Result: ErrorType.RATE_LIMIT

# Check if error is permanent (shouldn't retry)
is_permanent = ErrorClassifier.is_permanent(error_type)
# Result: False for rate limits, True for 404/auth errors

# Check if error is transient (retry immediately)
is_transient = ErrorClassifier.is_transient(error_type)
# Result: True for timeouts, connection resets
```

**Error Type Configurations:**

| Error Type | Max Attempts | Strategy | Base Delay | Notes |
|------------|--------------|----------|------------|-------|
| Network Timeout | 3 | Immediate | 0ms | Retry once immediately, then backoff |
| Rate Limit (429) | 3 | Exponential Jitter | 30s | Long backoff to respect rate limits |
| Server Error (5xx) | 4 | Exponential Jitter | 5s | Medium backoff for server issues |
| CAPTCHA | 1 | Immediate | 0ms | Don't retry, escalate to user |
| Selector Not Found | 3 | Linear | 1s | Short retry with page re-snapshot |
| Stale Element | 3 | Immediate | 500ms | Quick retry after DOM refresh |
| 404 Not Found | 1 | Immediate | 0ms | Permanent - don't retry |
| Auth Required | 1 | Immediate | 0ms | Permanent - escalate to user |
| Connection Reset | 3 | Exponential Jitter | 1s | Retry with backoff |
| Page Crash | 2 | Linear | 2s | Retry after page reload |

### 3. Circuit Breaker Integration

Prevents infinite retry loops and protects against cascading failures.

```python
from agent.smart_retry import SmartRetryManager

manager = SmartRetryManager(enable_circuit_breaker=True)

# Record attempts - circuit breaker tracks patterns
manager.record_attempt(
    action="fetch_data",
    strategy="default",
    args={"url": "https://example.com"},
    success=False,
    error="Connection timeout"
)

# Check if domain circuit is broken
is_broken, reason = manager.check_domain_circuit_breaker("example.com")
# After 3 errors in 30s: is_broken=True, cooloff for 60s

# Smart retry decision respects circuit breaker
should_retry, reason, delay = manager.should_retry(
    error="timeout",
    attempt=0,
    context={"url": "https://example.com"}
)
# Returns: (False, "Domain example.com in cooloff for 60.0s", 0)
```

**Circuit Breaker Behavior:**
- Triggers after 3 consecutive errors in 30 seconds
- Cooloff period: 60 seconds
- Prevents further retries to failing domain
- Automatically resets after cooloff

### 4. Smart Retry Conditions

The system knows which errors are permanent vs transient and handles them appropriately.

```python
from agent.smart_retry import SmartRetryManager

manager = SmartRetryManager()

# Permanent errors - don't retry
should_retry, reason, delay = manager.should_retry(
    error="404 Not Found",
    attempt=0,
    context={"url": "https://example.com"}
)
# Result: (False, "not_found is not retryable", 0)

# Transient errors - retry immediately once
should_retry, reason, delay = manager.should_retry(
    error="Network timeout",
    attempt=0,
    context={"url": "https://example.com"}
)
# Result: (True, "Retry #1 with immediate backoff (0ms delay)", 0)

# Rate limits - long backoff
should_retry, reason, delay = manager.should_retry(
    error="429 Too Many Requests",
    attempt=0,
    context={"url": "https://api.example.com"}
)
# Result: (True, "Retry #1 with exponential_jitter backoff", ~30000ms)
```

### 5. Partial Retry Support

Process batches efficiently by retrying only failed items, not the entire batch.

```python
from agent.smart_retry import SmartRetryManager

manager = SmartRetryManager()

items = [
    {"id": 1, "url": "https://example.com/1"},
    {"id": 2, "url": "https://example.com/2"},
    {"id": 3, "url": "https://example.com/3"},
]

async def process_item(item):
    # Process one item
    # May raise exceptions for some items
    pass

# Retry only failed items, not the whole batch
successful, failed = await manager.partial_retry(
    items=items,
    processor=process_item,
    context={"url": "https://example.com"},
    max_attempts=3
)

print(f"Successful: {len(successful)}")
print(f"Failed: {len(failed)}")
for item, error in failed:
    print(f"  {item['id']}: {error}")
```

**Example Output:**
```
Successful: 2
Failed: 1
  2: 404 Not Found - permanent failure
```

**Benefits:**
- Don't waste time re-processing successful items
- Smart per-item retry decisions
- Collects both successes and failures
- Tracks attempts per item

### 6. Decorator Usage

The simplest way to add retry logic to any async function.

```python
from agent.smart_retry import with_retry

@with_retry(
    max_attempts=5,
    strategy="exponential_jitter",
    context_builder=lambda url: {"url": url}
)
async def fetch_data(url: str):
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()

# Usage - retries automatically on failure
data = await fetch_data("https://api.example.com/data")
```

**Decorator Parameters:**
- `max_attempts` - Maximum retry attempts (default: 3)
- `strategy` - Retry strategy name or enum (default: "exponential_jitter")
- `backoff` - Enable backoff delays (default: True)
- `action_name` - Custom action name for logging (default: function name)
- `context_builder` - Function to extract context from args/kwargs

**Example with Custom Context:**
```python
@with_retry(
    max_attempts=4,
    strategy="exponential",
    action_name="scrape_page",
    context_builder=lambda url, **kw: {
        "url": url,
        "timeout": kw.get("timeout", 30)
    }
)
async def scrape_page(url: str, timeout: int = 30):
    # Scraping logic here
    pass
```

### 7. Context Manager Usage

For more control over retry logic within a function.

```python
from agent.smart_retry import retry_context

async def process_data(url: str):
    async with retry_context(
        action="fetch_data",
        context={"url": url},
        max_attempts=5,
        strategy="exponential_jitter"
    ) as ctx:
        # Code inside this block is automatically retried
        async with httpx.AsyncClient() as client:
            response = await client.get(url)

        # Modify context for next retry if needed
        if ctx.attempt > 0:
            ctx.modify_on_retry(timeout=60)  # Increase timeout

        return response.json()
```

**Context Manager Features:**
- `ctx.attempt` - Current attempt number (0-indexed)
- `ctx.last_error` - Last exception that occurred
- `ctx.modify_on_retry(**kwargs)` - Modify context for next retry
- Automatic backoff between retries
- Smart retry decisions based on error type

## Usage Examples

### Example 1: Simple Decorator

```python
from agent.smart_retry import with_retry

@with_retry(max_attempts=3)
async def send_email(to: str, subject: str, body: str):
    # SMTP logic here
    pass

await send_email("user@example.com", "Hello", "Test")
```

### Example 2: Batch Processing with Partial Retry

```python
from agent.smart_retry import SmartRetryManager

manager = SmartRetryManager()

urls = ["https://example.com/1", "https://example.com/2", ...]

async def scrape_url(url):
    # May fail for some URLs
    pass

successful, failed = await manager.partial_retry(
    items=urls,
    processor=scrape_url,
    context={"domain": "example.com"},
    max_attempts=3
)

print(f"Scraped {len(successful)} pages")
print(f"Failed: {len(failed)} pages")
```

### Example 3: Custom Error Handling

```python
from agent.smart_retry import SmartRetryManager, ErrorType

manager = SmartRetryManager()

# Customize retry config for specific error type
manager.retry_configs[ErrorType.RATE_LIMIT].base_delay_ms = 60000  # 1 minute
manager.retry_configs[ErrorType.RATE_LIMIT].max_attempts = 5

# Now rate limit retries wait longer
should_retry, reason, delay = manager.should_retry(
    error="429 Too Many Requests",
    attempt=0,
    context={"url": "https://api.example.com"}
)
# Result: delay ~60000ms instead of 30000ms
```

### Example 4: Monitoring and Statistics

```python
from agent.smart_retry import get_retry_stats

# Get comprehensive statistics
stats = get_retry_stats()

print(f"Total attempts: {stats['session_attempts']}")
print(f"Known failure patterns: {stats['known_patterns']}")
print(f"Patterns with solutions: {stats['patterns_with_solutions']}")

# Error type distribution
for error_type, count in stats['error_type_distribution'].items():
    print(f"  {error_type}: {count}")

# Circuit breaker states
for domain, state in stats.get('circuit_breaker_states', {}).items():
    print(f"  {domain}: {state}")
```

## Integration with Existing Code

### Browser Automation

```python
from agent.smart_retry import with_retry

@with_retry(
    max_attempts=3,
    strategy="linear",
    context_builder=lambda page, selector: {
        "url": page.url,
        "selector": selector
    }
)
async def click_element(page, selector: str):
    element = await page.wait_for_selector(selector, timeout=5000)
    await element.click()

# Usage
await click_element(page, "#submit-btn")
# Automatically retries with re-snapshot if selector not found
```

### API Calls

```python
from agent.smart_retry import with_retry

@with_retry(
    max_attempts=5,
    strategy="exponential_jitter",
    context_builder=lambda url, **kw: {"url": url}
)
async def api_request(url: str, method: str = "GET", **kwargs):
    async with httpx.AsyncClient() as client:
        response = await client.request(method, url, **kwargs)
        response.raise_for_status()
        return response.json()

# Automatically handles:
# - Network timeouts (retry immediately once)
# - Rate limits (long backoff)
# - Server errors (medium backoff)
# - Auth errors (don't retry, raise immediately)
```

### Data Extraction

```python
from agent.smart_retry import SmartRetryManager

manager = SmartRetryManager()

async def extract_from_pages(urls: list[str]):
    async def extract_one(url):
        # Extraction logic - may fail
        pass

    # Only retry failed URLs
    results, failures = await manager.partial_retry(
        items=urls,
        processor=extract_one,
        context={"action": "extract"},
        max_attempts=3
    )

    # Save successful results
    await save_results(results)

    # Log failures for manual review
    if failures:
        logger.error(f"Failed to extract from {len(failures)} URLs")
        for url, error in failures:
            logger.error(f"  {url}: {error}")
```

## Best Practices

### 1. Choose the Right Strategy

- **Immediate**: Transient errors (timeouts, stale elements)
- **Linear**: DOM/page state issues (selector not found)
- **Exponential**: Network/API errors (connection issues)
- **Exponential Jitter**: Rate limits, distributed systems

### 2. Set Appropriate Max Attempts

- **1 attempt**: Permanent errors (404, auth required)
- **2-3 attempts**: Most transient errors
- **4-5 attempts**: Critical operations with unreliable networks

### 3. Use Context Builders

Always provide a context builder to enable:
- Domain-based circuit breaking
- Error pattern learning
- Strategy selection per site

```python
@with_retry(
    context_builder=lambda url: {"url": url}  # ✓ Good
)
async def fetch(url): pass

@with_retry()  # ✗ Bad - no domain tracking
async def fetch(url): pass
```

### 4. Monitor Statistics

```python
from agent.smart_retry import get_retry_stats

# Periodically check retry stats
stats = get_retry_stats()
if stats['session_attempts'] > 100:
    logger.warning(f"High retry rate: {stats}")
```

### 5. Handle Escalations

Some errors require user intervention:

```python
from agent.smart_retry import SmartRetryManager

manager = SmartRetryManager()

recommendation = manager.get_recommendation(
    action="login",
    context={"url": "https://example.com"},
    error="CAPTCHA detected"
)

if recommendation['action'] == 'escalate':
    # Notify user
    print(f"Need help: {recommendation['reason']}")
    # Show browser for manual CAPTCHA solving
```

## Troubleshooting

### Circuit Breaker Triggering Too Often

Increase the error threshold or time window:

```python
manager = SmartRetryManager()
# Default: 3 errors in 30s triggers 60s cooloff

# Custom circuit breaker behavior
# (Requires modifying check_domain_circuit_breaker method)
```

### Backoff Too Short/Long

Adjust retry configs:

```python
from agent.smart_retry import SmartRetryManager, ErrorType

manager = SmartRetryManager()

# Increase rate limit backoff
manager.retry_configs[ErrorType.RATE_LIMIT].base_delay_ms = 60000
manager.retry_configs[ErrorType.RATE_LIMIT].max_delay_ms = 600000
```

### Want to Disable Circuit Breaker

```python
manager = SmartRetryManager(enable_circuit_breaker=False)
```

## Summary

The enhanced Smart Retry system provides:

1. **Exponential Backoff with Jitter** - Prevents thundering herd
2. **Per-Error-Type Strategies** - Smart handling for different errors
3. **Circuit Breaker** - Prevents infinite loops and cascading failures
4. **Smart Retry Decisions** - Knows permanent vs transient errors
5. **Partial Retry** - Efficient batch processing
6. **Decorators & Context Managers** - Easy integration

Use it to make your agent more resilient, efficient, and production-ready.
