# Sleep Optimization Quick Reference

## Quick Decision Tree

```
Need to wait for something?
│
├─ After page navigation?
│   └─ Use: wait_for_load_state('networkidle', 5000)
│
├─ Before clicking/filling element?
│   └─ Use: wait_for_selector('#element', 5000)
│
├─ After click that triggers navigation?
│   └─ Use: wait_for_load_state('domcontentloaded', 3000)
│
├─ API rate limiting?
│   └─ Use: asyncio.sleep(seconds)  # Add comment explaining rate limit
│
├─ Retry loop?
│   └─ Use: exponential backoff pattern (see below)
│
└─ Lazy loading / Dynamic content?
    └─ Use: sleep(0.5) max OR wait_for_selector() for specific element
```

## Common Patterns

### Pattern 1: Navigate to Page

**DON'T:**
```python
await self.mcp.call_tool('playwright_navigate', {'url': url})
await asyncio.sleep(3)
```

**DO:**
```python
await self.mcp.call_tool('playwright_navigate', {'url': url})
await self.mcp.call_tool('playwright_wait_for_load_state', {
    'state': 'networkidle',
    'timeout': 5000
})
```

### Pattern 2: Fill Form

**DON'T:**
```python
await self.mcp.call_tool('playwright_navigate', {'url': form_url})
await asyncio.sleep(2)
await self.mcp.call_tool('playwright_fill', {'selector': '#username', 'value': 'test'})
```

**DO:**
```python
await self.mcp.call_tool('playwright_navigate', {'url': form_url})
await self.mcp.call_tool('playwright_wait_for_selector', {
    'selector': '#username',
    'timeout': 5000
})
await self.mcp.call_tool('playwright_fill', {'selector': '#username', 'value': 'test'})
```

### Pattern 3: Click and Wait for Response

**DON'T:**
```python
await self.mcp.call_tool('playwright_click', {'selector': '#submit'})
await asyncio.sleep(2)
```

**DO:**
```python
await self.mcp.call_tool('playwright_click', {'selector': '#submit'})
try:
    await self.mcp.call_tool('playwright_wait_for_load_state', {
        'state': 'domcontentloaded',
        'timeout': 3000
    })
except Exception:
    await asyncio.sleep(0.5)  # Fallback if no navigation occurs
```

### Pattern 4: Exponential Backoff Retry

**DON'T:**
```python
for attempt in range(5):
    try:
        result = await do_something()
        if result:
            return result
    except:
        await asyncio.sleep(1)  # Same delay every time
```

**DO:**
```python
base_delay = 1
max_delay = 30
for attempt in range(5):
    try:
        result = await do_something()
        if result:
            return result
    except:
        delay = min(base_delay * (2 ** attempt), max_delay)
        await asyncio.sleep(delay)  # 1s, 2s, 4s, 8s, 16s
```

### Pattern 5: CAPTCHA/Challenge Wait

**DON'T:**
```python
solved = await solver.solve_captcha()
if solved:
    await asyncio.sleep(3)  # Hope page updates
```

**DO:**
```python
solved = await solver.solve_captcha()
if solved:
    try:
        await page.wait_for_load_state('networkidle', timeout=3000)
    except:
        await asyncio.sleep(0.5)  # Brief fallback
```

## Load State Reference

| State | When to Use | Typical Timeout |
|-------|-------------|-----------------|
| `networkidle` | Full page loads, AJAX sites, dynamic content | 5-8s |
| `domcontentloaded` | Quick interactions, partial updates | 3s |
| `load` | Resource-heavy pages (images, media) | 10-15s |

## Timeout Guidelines

| Scenario | Recommended Timeout |
|----------|---------------------|
| Fast sites (Wikipedia, Google) | 3-5s |
| Normal sites (most websites) | 5s |
| Slow sites (Maps, heavy AJAX) | 8-10s |
| Form selector waits | 3-5s |
| After click (DOM update) | 3s |
| After click (full navigation) | 5s |

## When to Keep asyncio.sleep()

1. **API Rate Limiting**
   ```python
   await asyncio.sleep(1.2)  # Respect API rate limit: 50 requests/minute
   ```

2. **Intentional User-Requested Delay**
   ```python
   if action_type == 'wait':
       seconds = action.get('seconds', 5)
       await asyncio.sleep(seconds)  # User explicitly requested wait
   ```

3. **Polling with Fixed Interval**
   ```python
   while not condition_met:
       await asyncio.sleep(0.5)  # Check every 500ms
       condition_met = await check_condition()
   ```

4. **Brief Pause for Lazy Loading**
   ```python
   await page.scroll({'direction': 'down', 'amount': 600})
   await asyncio.sleep(0.5)  # Brief pause for lazy-loaded content
   ```

5. **Fallback When Playwright Wait Fails**
   ```python
   try:
       await page.wait_for_load_state('networkidle', timeout=3000)
   except:
       await asyncio.sleep(0.5)  # Fallback if networkidle times out
   ```

## MCP Tool Names

When using MCP client (`self.mcp.call_tool()`):

```python
# Navigation
await self.mcp.call_tool('playwright_navigate', {'url': url})

# Wait for load state
await self.mcp.call_tool('playwright_wait_for_load_state', {
    'state': 'networkidle',  # or 'domcontentloaded' or 'load'
    'timeout': 5000
})

# Wait for selector
await self.mcp.call_tool('playwright_wait_for_selector', {
    'selector': '#element-id',
    'timeout': 5000
})

# Interactions
await self.mcp.call_tool('playwright_click', {'selector': '#button'})
await self.mcp.call_tool('playwright_fill', {'selector': '#input', 'value': 'text'})
```

## Direct Playwright API (when using page object)

```python
# Navigation
await page.goto(url)

# Wait for load state
await page.wait_for_load_state('networkidle', timeout=5000)

# Wait for selector
await page.wait_for_selector('#element', timeout=5000)

# Interactions
await page.click('#button')
await page.fill('#input', 'text')
```

## Checklist for Code Review

- [ ] All navigation followed by wait_for_load_state?
- [ ] All element interactions preceded by wait_for_selector (if needed)?
- [ ] All hardcoded sleeps have comments explaining why?
- [ ] Retry loops use exponential backoff?
- [ ] Timeouts are reasonable (not too long, not too short)?
- [ ] Fallback waits in place for edge cases?

## Common Mistakes to Avoid

1. **Mixing sleep with Playwright waits**
   ```python
   # BAD - redundant
   await page.goto(url)
   await page.wait_for_load_state('networkidle')
   await asyncio.sleep(2)  # Unnecessary!
   ```

2. **Too short timeouts**
   ```python
   # BAD - will fail on slow connections
   await page.wait_for_load_state('networkidle', timeout=1000)  # Only 1s!
   ```

3. **Too long timeouts**
   ```python
   # BAD - users wait too long on actual failures
   await page.wait_for_load_state('networkidle', timeout=60000)  # 60s is too long
   ```

4. **No fallback for optional waits**
   ```python
   # BAD - crashes if element doesn't appear
   await page.wait_for_selector('#optional-element', timeout=5000)

   # GOOD - graceful degradation
   try:
       await page.wait_for_selector('#optional-element', timeout=5000)
   except:
       pass  # Element optional, continue anyway
   ```

5. **Using sleep instead of condition-based wait**
   ```python
   # BAD
   await asyncio.sleep(5)  # Hope content loads by then

   # GOOD
   await page.wait_for_selector('#content', timeout=5000)  # Wait for actual condition
   ```

## Performance Tips

1. **Use domcontentloaded for speed when possible**
   - 2-3x faster than networkidle
   - Good for interactions that don't require full page load

2. **Set reasonable timeouts**
   - Don't wait longer than needed
   - Balance between reliability and speed

3. **Parallelize independent waits**
   ```python
   # If waiting for multiple independent elements
   await asyncio.gather(
       page.wait_for_selector('#element1'),
       page.wait_for_selector('#element2'),
       page.wait_for_selector('#element3'),
   )
   ```

4. **Use specific selectors**
   - Faster than waiting for page state
   - More reliable for dynamic content

---

**Last Updated:** 2025-12-12
**Related:** SLEEP_OPTIMIZATION_SUMMARY.md
