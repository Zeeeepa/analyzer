# Eversale Code Export Guide

## Overview

Eversale can export any workflow as clean, production-ready code in multiple formats. After the agent performs a task using Playwright tools, it can generate standalone scripts that replicate the workflow without needing the agent.

## Supported Formats

| Format | File Extension | Use Case |
|--------|---------------|----------|
| python_async | .py | Web apps, concurrent tasks, modern Python projects |
| python_sync | .py | Scripts, notebooks, simple automation |
| pytest | .py | Automated testing, CI/CD pipelines |
| typescript | .ts | Node.js apps, type safety, enterprise projects |
| javascript | .js | Browser scripts, quick prototypes, Node.js |

## Usage

### From CLI

Export the last workflow that the agent performed:

```bash
# Export as async Python (default)
eversale export --format python_async --output my_script.py

# Export as TypeScript
eversale export --format typescript --output my_script.ts

# Export as pytest test
eversale export --format pytest --output test_workflow.py
```

### From Agent (Interactive Mode)

```
User: "Search for Python books on books.toscrape.com"
Agent: [performs task using Playwright tools]

User: "Export that workflow as TypeScript"
Agent: [generates search_books.ts file]
```

### Programmatic Usage

```python
from agent.code_generator import PlaywrightCodeGenerator, CodeGenerationConfig

# Configure the generator
config = CodeGenerationConfig(
    format="typescript",
    add_error_handling=True,
    add_logging=True,
    parameterize=True,
    add_retries=True,
    max_retries=3,
    headless=False
)

# Generate code from workflow actions
generator = PlaywrightCodeGenerator(config)
result = generator.generate_from_trace(
    actions=[
        {"tool": "playwright_navigate", "arguments": {"url": "https://example.com"}},
        {"tool": "playwright_click", "arguments": {"selector": "button.submit"}}
    ],
    description="Example workflow"
)

# Save to file
generator.save_to_file(result, Path("workflow.ts"))
```

## Output Features

All exported code includes:

- **Error handling** - Try/catch blocks with proper error messages
- **Retries** - Automatic retry logic for flaky operations (configurable)
- **Logging** - Integration with standard logging libraries
- **Type hints** - Python type annotations and TypeScript interfaces
- **Parameterization** - URLs and selectors extracted as variables/parameters
- **Comments** - Human-readable descriptions of each step
- **Clean formatting** - Idiomatic code following language best practices

## Format-Specific Features

### Python Async (`python_async`)

- Uses `playwright.async_api` for concurrent execution
- Async/await syntax throughout
- Context managers for resource cleanup
- Type hints with `typing` module

**Example output:**

```python
import asyncio
from playwright.async_api import async_playwright, Page, Browser
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main(
    search_url: str = "https://books.toscrape.com",
    search_query: str = "python"
) -> dict:
    """
    Search for books on books.toscrape.com

    Args:
        search_url: Target URL for navigation
        search_query: Query to use
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        )
        page = await context.new_page()

        try:
            # Navigate to search page
            await page.goto(search_url, wait_until='domcontentloaded')

            # Fill search input
            await page.fill("input#search", search_query, timeout=30000)

            # Click search button
            await page.click("button[type='submit']", timeout=30000)

            return {"success": True, "message": "Workflow completed"}

        except Exception as e:
            logger.error(f"Workflow failed: {e}")
            return {"success": False, "error": str(e)}

        finally:
            await browser.close()

if __name__ == "__main__":
    result = asyncio.run(main())
    print(f"Result: {result}")
```

### Python Sync (`python_sync`)

- Uses `playwright.sync_api` for simpler, synchronous code
- No async/await required
- Easier to understand for beginners
- Better for Jupyter notebooks and scripts

**Example output:**

```python
from playwright.sync_api import sync_playwright, Page, Browser
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main(url: str = "https://books.toscrape.com") -> dict:
    """Search for books on books.toscrape.com"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080}
        )
        page = context.new_page()

        try:
            page.goto(url, wait_until='domcontentloaded')
            # ... workflow steps ...
            return {"success": True}

        except Exception as e:
            logger.error(f"Failed: {e}")
            return {"success": False, "error": str(e)}

        finally:
            browser.close()

if __name__ == "__main__":
    result = main()
    print(f"Result: {result}")
```

### Pytest (`pytest`)

- Test fixtures for browser and page
- Assertions to verify workflow success
- Integration with pytest framework
- Ready for CI/CD pipelines

**Example output:**

```python
import pytest
from playwright.sync_api import Page, Browser, expect

@pytest.fixture(scope="function")
def browser_context(browser):
    context = browser.new_context(
        viewport={"width": 1920, "height": 1080}
    )
    yield context
    context.close()

@pytest.fixture(scope="function")
def page(browser_context):
    page = browser_context.new_page()
    yield page
    page.close()

def test_search_books(page: Page):
    """Test book search workflow"""

    # Navigate to site
    page.goto("https://books.toscrape.com")

    # Fill search
    page.fill("input#search", "python")

    # Click search
    page.click("button[type='submit']")

    # Verify workflow completed
    assert page.url, "Page should have loaded"
```

### TypeScript (`typescript`)

- Full TypeScript type safety
- Playwright TypeScript API
- Interfaces for return types
- Modern ES6+ syntax

**Example output:**

```typescript
import { chromium, Browser, Page } from 'playwright';

interface WorkflowResult {
    success: boolean;
    data?: any;
    error?: string;
}

interface WorkflowParams {
    searchUrl?: string;
    searchQuery?: string;
}

async function runWorkflow(params: WorkflowParams = {}): Promise<WorkflowResult> {
    const {
        searchUrl = 'https://books.toscrape.com',
        searchQuery = 'python'
    } = params;

    const browser: Browser = await chromium.launch({ headless: false });
    const page: Page = await browser.newPage({
        viewport: { width: 1920, height: 1080 },
        userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
    });

    try {
        // Navigate to search page
        await page.goto(searchUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });

        // Fill search input
        await page.fill('input#search', searchQuery, { timeout: 30000 });

        // Click search button
        await page.click('button[type="submit"]', { timeout: 30000 });

        return { success: true, data: { message: 'Workflow completed' } };

    } catch (error) {
        console.error('Workflow failed:', error);
        return { success: false, error: String(error) };

    } finally {
        await browser.close();
    }
}

// Execute workflow
runWorkflow().then(result => {
    console.log('Result:', result);
});
```

### JavaScript (`javascript`)

- ES6+ syntax without TypeScript overhead
- Same Playwright API as TypeScript
- Quick prototyping and browser console usage
- Node.js compatible

**Example output:**

```javascript
const { chromium } = require('playwright');

async function runWorkflow({
    searchUrl = 'https://books.toscrape.com',
    searchQuery = 'python'
} = {}) {
    const browser = await chromium.launch({ headless: false });
    const page = await browser.newPage({
        viewport: { width: 1920, height: 1080 },
        userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
    });

    try {
        // Navigate to search page
        await page.goto(searchUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });

        // Fill search input
        await page.fill('input#search', searchQuery, { timeout: 30000 });

        // Click search button
        await page.click('button[type="submit"]', { timeout: 30000 });

        return { success: true, data: { message: 'Workflow completed' } };

    } catch (error) {
        console.error('Workflow failed:', error);
        return { success: false, error: String(error) };

    } finally {
        await browser.close();
    }
}

// Execute workflow
runWorkflow().then(result => {
    console.log('Result:', result);
});
```

## Configuration Options

Customize code generation with these options:

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `format` | str | python_async | Output format (python_async, python_sync, pytest, typescript, javascript) |
| `add_comments` | bool | True | Include human-readable comments |
| `add_error_handling` | bool | True | Wrap code in try/catch blocks |
| `add_retries` | bool | True | Add retry logic for flaky operations |
| `add_logging` | bool | True | Include logging statements |
| `add_screenshots` | bool | False | Take screenshots after each step |
| `parameterize` | bool | True | Extract URLs/selectors as parameters |
| `max_retries` | int | 3 | Number of retry attempts |
| `timeout` | int | 30000 | Timeout in milliseconds |
| `headless` | bool | False | Run browser in headless mode |
| `function_name` | str | main | Name for main function |
| `test_name` | str | test_workflow | Name for pytest test function |

## Common Workflows

### E-commerce Research

**Agent task:** "Research book prices on books.toscrape.com"

**Generated Python:**
```python
async def research_book_prices(url: str = "https://books.toscrape.com"):
    """Research book prices across categories"""
    # ... generated code ...
```

**Generated TypeScript:**
```typescript
async function researchBookPrices(url: string = 'https://books.toscrape.com'): Promise<WorkflowResult> {
    // ... generated code ...
}
```

### Lead Generation (SDR)

**Agent task:** "Find leads from Facebook Ads Library for 'CRM software'"

**Generated code includes:**
- Navigation to Facebook Ads Library
- Search for advertiser keywords
- Extraction of contact information
- Saving results to CSV

### Email Management

**Agent task:** "Read my Gmail inbox and summarize unread emails"

**Generated code includes:**
- Gmail login (requires manual authentication first)
- Inbox navigation
- Email extraction
- Summary generation

## Dependencies

### Python

Install required packages:

```bash
pip install playwright pytest
playwright install chromium
```

### TypeScript/JavaScript

Install required packages:

```bash
npm install playwright
npx playwright install chromium
```

For TypeScript:

```bash
npm install -D typescript @types/node
npx tsc --init
```

## Running Generated Code

### Python

```bash
# Async Python
python my_script.py

# With pytest
pytest test_workflow.py -v
```

### TypeScript

```bash
# Compile and run
npx ts-node workflow.ts

# Or compile first
npx tsc workflow.ts
node workflow.js
```

### JavaScript

```bash
node workflow.js
```

## Advanced Usage

### Exporting from Skill Library

If you have saved skills in the agent's skill library:

```python
from agent.skill_library import SkillLibrary
from agent.code_generator import PlaywrightCodeGenerator

# Load skill
library = SkillLibrary()
skill = library.get_skill("search_books")

# Export skill as code
generator = PlaywrightCodeGenerator()
result = generator.generate_from_skill(skill, format="typescript")
```

### Batch Export

Export multiple workflows:

```python
workflows = [
    {"name": "search_books", "format": "python_async"},
    {"name": "lead_gen", "format": "typescript"},
    {"name": "email_check", "format": "pytest"}
]

for workflow in workflows:
    result = generator.generate_from_trace(
        actions=workflow_actions[workflow["name"]],
        description=workflow["name"],
        format=workflow["format"]
    )
    generator.save_to_file(result, Path(f"{workflow['name']}.{workflow['format'][-2:]}"))
```

### Custom Parameterization

Control which values become parameters:

```python
config = CodeGenerationConfig(
    parameterize=True,
    # Only URLs and search queries become parameters
    # Selectors stay hardcoded for reliability
)
```

## Troubleshooting

### Issue: Generated code doesn't work

**Solution:** Make sure you installed Playwright browsers:

```bash
playwright install chromium
```

### Issue: Login required

**Solution:** Generated code can't handle authentication. Either:
1. Login manually first, then export the post-login workflow
2. Modify generated code to include login steps
3. Use browser profiles with saved sessions

### Issue: Selectors not working

**Solution:** Websites change frequently. Update selectors in generated code:

```python
# Before
await page.click("button.old-selector")

# After
await page.click("button.new-selector")
```

### Issue: TypeScript compilation errors

**Solution:** Install type definitions:

```bash
npm install -D @types/node
```

## Best Practices

1. **Test generated code** - Always test exported workflows in a safe environment
2. **Version control** - Commit generated code to track changes over time
3. **Add validations** - Enhance generated code with business logic validations
4. **Handle edge cases** - Generated code handles happy path, add error cases
5. **Update selectors** - Keep selectors up-to-date as websites change
6. **Use parameterization** - Makes code reusable across different inputs
7. **Add logging** - Enable logging to debug issues in production
8. **Set timeouts** - Adjust timeouts based on network conditions

## Integration with CI/CD

### GitHub Actions

```yaml
name: Run Playwright Tests

on: [push]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install playwright pytest
          playwright install chromium
      - name: Run tests
        run: pytest test_workflow.py -v
```

### Jenkins

```groovy
pipeline {
    agent any
    stages {
        stage('Test') {
            steps {
                sh 'pip install playwright pytest'
                sh 'playwright install chromium'
                sh 'pytest test_workflow.py -v'
            }
        }
    }
}
```

## Examples by Industry

### Real Estate (G)

**Task:** "Find comps on Zillow for 123 Main St"

**Generated code:** Navigates Zillow, searches address, extracts comparable properties

### Legal (G)

**Task:** "Extract parties and amounts from this contract PDF"

**Generated code:** Reads PDF, uses regex to extract legal entities and monetary values

### Support (C)

**Task:** "Check Zendesk tickets and draft replies"

**Generated code:** Authenticates to Zendesk, fetches open tickets, generates response templates

### Education (M)

**Task:** "Create quiz from Wikipedia article on photosynthesis"

**Generated code:** Fetches Wikipedia content, extracts key facts, formats as quiz questions

## Limitations

1. **Custom Eversale tools** - Tools like `playwright_extract_page_fast` are placeholders requiring custom implementation
2. **Anti-bot detection** - Generated code may fail on sites with aggressive bot protection
3. **Authentication** - Login flows need manual handling or browser profiles
4. **Dynamic content** - SPAs and infinite scroll require additional logic
5. **Rate limiting** - Generated code doesn't include rate limiting logic

## Future Enhancements

- Rust code generation for high-performance automation
- Go code generation for enterprise deployments
- Selenium WebDriver support for broader browser compatibility
- Puppeteer export for Chromium-specific workflows
- GraphQL/API code generation when browser automation isn't needed

## Support

For questions or issues with code export:

1. Check this guide first
2. Review the generated code comments
3. Test with `books.toscrape.com` (demo site without bot protection)
4. Open an issue on GitHub with the workflow trace

---

Generated with Eversale - Your AI Employee for Web Automation
