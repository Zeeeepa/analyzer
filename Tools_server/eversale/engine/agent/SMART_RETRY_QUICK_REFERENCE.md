# Smart Retry - Quick Reference Card

## Import
```python
from agent.smart_retry import (
    with_retry,           # Decorator
    retry_context,        # Context manager
    SmartRetryManager,    # Manual control
    get_retry_stats,      # Statistics
    ErrorType,            # Error type enum
    RetryStrategy         # Strategy enum
)
```

## 1. Decorator (Simplest)
```python
@with_retry(max_attempts=3, strategy="exponential_jitter")
async def fetch_data(url: str):
    return await httpx.get(url)

# Automatically retries on failure with exponential backoff
data = await fetch_data("https://api.example.com")
```

## 2. Context Manager (More Control)
```python
async with retry_context(
    action="login",
    context={"url": url},
    max_attempts=5,
    strategy="exponential"
) as ctx:
    await page.click("#submit")
    # Modify on retry
    if ctx.attempt > 0:
        ctx.modify_on_retry(selector="#submit-btn-alt")
```

## 3. Manual Control (Full Power)
```python
manager = SmartRetryManager()

should_retry, reason, delay_ms = manager.should_retry(
    error="429 Too Many Requests",
    attempt=0,
    context={"url": "https://api.example.com"}
)

if should_retry:
    await asyncio.sleep(delay_ms / 1000)
    # Retry operation
```

## 4. Batch Processing (Partial Retry)
```python
manager = SmartRetryManager()

async def process_url(url):
    # May fail for some URLs
    pass

successful, failed = await manager.partial_retry(
    items=urls,
    processor=process_url,
    context={"domain": "example.com"},
    max_attempts=3
)
# Only failed items are retried
```

## Error Types & Strategies

| Error Type | Strategy | Base Delay | Max Attempts |
|------------|----------|------------|--------------|
| Network Timeout | Immediate | 0ms | 3 |
| Rate Limit (429) | Exp. Jitter | 30s | 3 |
| Server Error (5xx) | Exp. Jitter | 5s | 4 |
| CAPTCHA | Immediate | 0ms | 1 (escalate) |
| Selector Not Found | Linear | 1s | 3 |
| 404 Not Found | - | - | 0 (permanent) |
| Auth Required | - | - | 0 (escalate) |

## Retry Strategies

| Strategy | Formula | Example (base=1s) |
|----------|---------|-------------------|
| Immediate | 0 | 0, 0, 0, 0 |
| Linear | base × attempt | 1s, 2s, 3s, 4s |
| Exponential | base × 2^attempt | 1s, 2s, 4s, 8s |
| Exp. Jitter | base × 2^attempt + jitter | 1s, 2.1s, 4.3s, 8.7s |

## Circuit Breaker

**Automatic Protection:**
- Triggers: 3 errors in 30 seconds
- Cooloff: 60 seconds
- Per-domain tracking
- Auto-recovery after cooloff

```python
# Check circuit state
is_broken, reason = manager.check_domain_circuit_breaker("example.com")
if is_broken:
    print(f"Circuit broken: {reason}")
```

## Statistics

```python
stats = get_retry_stats()
print(f"Attempts: {stats['session_attempts']}")
print(f"Known patterns: {stats['known_patterns']}")
print(f"Error distribution: {stats['error_type_distribution']}")
```

## Common Patterns

### API with Rate Limiting
```python
@with_retry(
    max_attempts=5,
    strategy="exponential_jitter",
    context_builder=lambda url: {"url": url}
)
async def api_call(url: str):
    # Handles 429 with 30s+ backoff
    pass
```

### Browser Automation
```python
@with_retry(
    max_attempts=3,
    strategy="linear",
    context_builder=lambda page, sel: {"url": page.url}
)
async def click_element(page, selector: str):
    # Retries on stale element, selector not found
    pass
```

### Batch Scraping
```python
results, failures = await manager.partial_retry(
    items=urls,
    processor=scrape_page,
    context={"domain": domain},
    max_attempts=3
)
# Only failed pages retried
```

## Quick Tips

1. **Use decorator for simple cases** - Least code
2. **Use context manager for control** - Modify on retry
3. **Use partial_retry for batches** - Don't re-process successes
4. **Always provide context** - Enables circuit breaker
5. **Monitor stats periodically** - Detect retry storms

## Error Handling

```python
try:
    result = await fetch_data()
except Exception as e:
    # All retries exhausted
    error_type = ErrorClassifier.classify(e)
    if error_type == ErrorType.RATE_LIMIT:
        # Handle rate limit
        pass
    elif error_type == ErrorType.AUTH_REQUIRED:
        # Handle auth
        pass
```

## Disable Circuit Breaker (if needed)

```python
manager = SmartRetryManager(enable_circuit_breaker=False)
```

## Custom Error Config

```python
manager = SmartRetryManager()
manager.retry_configs[ErrorType.RATE_LIMIT].base_delay_ms = 60000  # 1 min
manager.retry_configs[ErrorType.RATE_LIMIT].max_attempts = 10
```

---

**See:** `/mnt/c/ev29/agent/SMART_RETRY_GUIDE.md` for full documentation

