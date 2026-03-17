# Simple Agent - Quick Start

**TL;DR:** Minimal browser automation using accessibility refs (like Playwright MCP).

## Installation

Already included in Eversale CLI v2.9+. No additional setup needed.

## 5-Minute Tutorial

### 1. Basic Browser Usage

```python
import asyncio
from a11y_browser import A11yBrowser

async def main():
    # Create and launch browser
    async with A11yBrowser(headless=False) as browser:
        # Navigate
        await browser.navigate("https://google.com")

        # Get snapshot (shows all interactive elements)
        snapshot = await browser.snapshot()
        print(f"Found {len(snapshot.elements)} elements")

        # Find search box
        search = snapshot.find_by_role("searchbox")[0]
        print(f"Search box: {search}")  # [e1] searchbox "Search"

        # Type and submit
        await browser.type(search.ref, "Python tutorials")
        await browser.press("Enter")

        # Wait and screenshot
        await browser.wait(2)
        await browser.screenshot("result.png")

asyncio.run(main())
```

### 2. Agent with LLM

```python
import asyncio
from simple_agent import SimpleAgent
from llm_client import LLMClient

async def main():
    llm = LLMClient()
    agent = SimpleAgent(llm_client=llm, headless=False)

    result = await agent.run("Search Google for AI news and click first result")

    if result.success:
        print(f"Done in {result.steps_taken} steps")
        print(f"Summary: {result.data['summary']}")
    else:
        print(f"Failed: {result.error}")

asyncio.run(main())
```

### 3. Agent without LLM (Fallback)

```python
import asyncio
from simple_agent import SimpleAgent

async def main():
    agent = SimpleAgent(llm_client=None, headless=False)
    result = await agent.run("Search Google for Python")

    print(f"Success: {result.success}")
    print(f"Steps: {result.steps_taken}")

asyncio.run(main())
```

## Key Concepts

### Accessibility Refs

Instead of brittle CSS selectors:
```python
# OLD WAY (fragile)
await page.click('button.btn-primary[data-test="submit"]')

# NEW WAY (stable)
snapshot = await browser.snapshot()
# Shows: [e38] button "Submit"
await browser.click("e38")
```

### Snapshot Format

```
[e1] searchbox "Search"
[e2] button "Google Search"
[e3] button "I'm Feeling Lucky"
[e4] link "Gmail"
[e5] textbox "Email" value=user@example.com (focused)
```

Format: `[ref] role "name" value=X (flags)`

### Finding Elements

```python
snapshot = await browser.snapshot()

# By role
buttons = snapshot.find_by_role("button")
links = snapshot.find_by_role("link")
inputs = snapshot.find_by_role("textbox")

# By name (fuzzy)
search = snapshot.find_by_name("search", partial=True)

# By ref
element = snapshot.find_ref("e38")
```

## Available Actions

| Action | Code | Description |
|--------|------|-------------|
| Navigate | `await browser.navigate("url")` | Go to URL |
| Snapshot | `snapshot = await browser.snapshot()` | Get elements |
| Click | `await browser.click("e38")` | Click element |
| Type | `await browser.type("e12", "text")` | Type into element |
| Press | `await browser.press("Enter")` | Press key |
| Scroll | `await browser.scroll("down")` | Scroll page |
| Wait | `await browser.wait(2)` | Wait seconds |
| Screenshot | `await browser.screenshot("path.png")` | Take screenshot |
| Hover | `await browser.hover("e5")` | Hover element |
| Select | `await browser.select("e3", "option")` | Select dropdown option |
| Get Text | `result = await browser.get_text("e10")` | Get element text |
| Back/Forward | `await browser.go_back()` | Browser navigation |
| Refresh | `await browser.refresh()` | Reload page |

## Agent Actions (LLM Mode)

When using SimpleAgent with LLM, it understands these commands:

```
navigate https://google.com
click e38
type e12 python tutorial
press Enter
scroll down
wait 2
done Task completed successfully
```

## Testing

```bash
cd /mnt/c/ev29/cli/engine/agent

# Run tests
python test_simple_agent.py

# Run examples
python a11y_browser.py              # Browser example
python simple_agent.py              # Agent example
python simple_agent_integration_example.py mock
```

## File Locations

```
/mnt/c/ev29/cli/engine/agent/
├── a11y_browser.py                    # Browser wrapper (946 lines)
├── simple_agent.py                    # Simple agent (343 lines)
├── test_simple_agent.py               # Tests
├── simple_agent_integration_example.py # Integration examples
├── SIMPLE_AGENT_README.md             # Full docs
└── SIMPLE_AGENT_QUICKSTART.md         # This file
```

## Common Patterns

### Pattern 1: Search and Click

```python
async with A11yBrowser() as browser:
    await browser.navigate("https://google.com")
    snapshot = await browser.snapshot()

    search = snapshot.find_by_role("searchbox")[0]
    await browser.type(search.ref, "query")
    await browser.press("Enter")

    await browser.wait(2)
    snapshot = await browser.snapshot()

    first_link = snapshot.find_by_role("link")[0]
    await browser.click(first_link.ref)
```

### Pattern 2: Fill Form

```python
async with A11yBrowser() as browser:
    await browser.navigate("https://example.com/form")
    snapshot = await browser.snapshot()

    # Find inputs by name
    email = snapshot.find_by_name("email", partial=True)[0]
    password = snapshot.find_by_name("password", partial=True)[0]
    submit = snapshot.find_by_role("button")[0]

    # Fill
    await browser.type(email.ref, "user@example.com")
    await browser.type(password.ref, "secret123")
    await browser.click(submit.ref)
```

### Pattern 3: Extract Data

```python
async with A11yBrowser() as browser:
    await browser.navigate("https://example.com/products")
    snapshot = await browser.snapshot()

    # Get all links
    links = snapshot.find_by_role("link")

    # Extract data
    products = []
    for link in links:
        if "product" in link.name.lower():
            result = await browser.get_text(link.ref)
            products.append(result.data["text"])

    print(f"Found {len(products)} products")
```

## Tips

1. **Always get fresh snapshot before actions** - Refs expire when page changes
2. **Use partial name matching** - More flexible than exact matches
3. **Check ActionResult.success** - Every action returns success status
4. **Retry once** - If action fails, wait 1s and retry
5. **Scroll to reveal elements** - Not all elements visible at once

## Debugging

```python
# Print all elements
snapshot = await browser.snapshot()
for el in snapshot.elements:
    print(el)

# Check if ref exists
element = snapshot.find_ref("e38")
if element:
    print(f"Found: {element}")
else:
    print("Ref not found - get new snapshot")

# Check action results
result = await browser.click("e38")
if not result.success:
    print(f"Click failed: {result.error}")
```

## Performance

- Snapshot generation: ~100-300ms
- Action execution: ~50-200ms
- Total time per step: ~1-2 seconds
- Memory usage: ~100MB (Playwright overhead)

## Limitations

- Only interactive elements in accessibility tree
- No CAPTCHA solving (use complex agent for that)
- No visual grounding (text-only)
- Max 20 steps per agent task
- Refs expire when page changes (get new snapshot)

## Next Steps

- Read full docs: `SIMPLE_AGENT_README.md`
- Run tests: `python test_simple_agent.py`
- Try examples: `python simple_agent_integration_example.py`
- Integrate with CLI: Import in `run_ultimate.py`

## Support

Issues? Check:
1. Playwright installed: `pip install playwright`
2. Browser installed: `playwright install chromium`
3. Imports working: `python -c "import a11y_browser; import simple_agent"`

For questions: See main Eversale CLI docs
