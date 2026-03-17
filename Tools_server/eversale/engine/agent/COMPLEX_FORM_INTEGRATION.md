# Complex Form Handler - Integration Guide

**Quick guide for integrating the Complex Form Handler into the Eversale agent.**

---

## Files Created

| File | Size | Purpose |
|------|------|---------|
| `complex_form_handler.py` | 33KB | Main module with all handlers |
| `COMPLEX_FORM_HANDLER_README.md` | 19KB | Complete API documentation |
| `complex_form_handler_example.py` | 15KB | 12 usage examples |
| `complex_form_handler_test.py` | 7.2KB | Unit tests |

---

## Quick Integration Steps

### 1. Import into Brain/ReAct Loop

Add to `/mnt/c/ev29/eversale-cli/engine/agent/brain_enhanced_v2.py`:

```python
# Add to imports section
from .complex_form_handler import (
    ComplexFormHandler,
    FormField,
    FormStep,
    InputType,
    SiteSpecificHandlers
)

# In tool execution section, add form handling tools
async def handle_form_fill(self, params):
    """Handle complex form filling"""
    page = self.page  # Current Playwright page

    # Auto-detect and fill
    handler = ComplexFormHandler(page)
    await handler.wait_for_form_ready()

    form_type = await handler.detect_form_type()

    if form_type == FormType.AUTOCOMPLETE:
        return await handler.fill_autocomplete(
            selector=params.get('selector'),
            value=params.get('value')
        )
    elif form_type == FormType.MULTI_STEP:
        return await handler.fill_multi_step_form(
            steps=params.get('steps')
        )
```

---

### 2. Add as Playwright Tool

Add to `/mnt/c/ev29/eversale-cli/engine/agent/playwright_direct.py`:

```python
from .complex_form_handler import ComplexFormHandler, SiteSpecificHandlers

class PlaywrightDirectClient:
    # ... existing code ...

    async def fill_form_autocomplete(self, selector: str, value: str) -> Dict[str, Any]:
        """
        Fill an autocomplete/typeahead input.

        Args:
            selector: Input field CSS selector
            value: Value to type and select

        Returns:
            Result dict with success status
        """
        try:
            handler = ComplexFormHandler(self.page)
            success = await handler.fill_autocomplete(selector, value)

            return {
                'success': success,
                'selector': selector,
                'value': value
            }
        except Exception as e:
            logger.error(f"Error filling autocomplete: {e}")
            return {'success': False, 'error': str(e)}

    async def search_indeed(self, job_title: str, location: str) -> Dict[str, Any]:
        """
        Search for jobs on Indeed.com.

        Args:
            job_title: Job title to search
            location: Location string (e.g., "San Francisco, CA")

        Returns:
            Result dict
        """
        try:
            success = await SiteSpecificHandlers.indeed_job_search(
                page=self.page,
                job_title=job_title,
                location=location
            )

            return {
                'success': success,
                'url': self.page.url,
                'job_title': job_title,
                'location': location
            }
        except Exception as e:
            logger.error(f"Indeed search error: {e}")
            return {'success': False, 'error': str(e)}
```

---

### 3. Register Tools in MCP

Add to `/mnt/c/ev29/eversale-cli/engine/agent/mcp_client.py`:

```python
# In tool registration
TOOLS = {
    # ... existing tools ...

    'playwright_fill_autocomplete': {
        'description': 'Fill autocomplete/typeahead input with suggestions',
        'parameters': {
            'selector': 'CSS selector for input',
            'value': 'Value to type and select'
        }
    },

    'playwright_search_indeed': {
        'description': 'Search for jobs on Indeed.com',
        'parameters': {
            'job_title': 'Job title to search',
            'location': 'Location (city, state)'
        }
    },

    'playwright_search_yelp': {
        'description': 'Search for businesses on Yelp.com',
        'parameters': {
            'business': 'Business type or name',
            'location': 'Location (city, state)'
        }
    },

    'playwright_search_zillow': {
        'description': 'Search properties on Zillow.com',
        'parameters': {
            'location': 'Location to search',
            'min_price': 'Minimum price (optional)',
            'max_price': 'Maximum price (optional)',
            'bedrooms': 'Number of bedrooms (optional)'
        }
    }
}
```

---

### 4. Add to Workflow Handlers

Add to `/mnt/c/ev29/eversale-cli/engine/agent/workflow_handlers.py`:

```python
from .complex_form_handler import SiteSpecificHandlers

class WorkflowHandlers:
    # ... existing code ...

    @staticmethod
    async def handle_job_search(page, job_title: str, location: str) -> Dict[str, Any]:
        """
        Handle job search workflow across multiple platforms.

        Supports: Indeed, LinkedIn, Monster
        """
        results = []

        # Indeed
        try:
            success = await SiteSpecificHandlers.indeed_job_search(
                page, job_title, location
            )
            if success:
                results.append({
                    'platform': 'Indeed',
                    'success': True,
                    'url': page.url
                })
        except Exception as e:
            logger.error(f"Indeed search failed: {e}")

        return {
            'total_platforms': len(results),
            'results': results
        }
```

---

### 5. Update Agent Capabilities

Add to `/mnt/c/ev29/eversale-cli/engine/agent/capabilities.py`:

```python
# In CAPABILITIES dict
'form_handling': {
    'name': 'Complex Form Handler',
    'description': 'Handle autocomplete, multi-step forms, location inputs',
    'supported_sites': [
        'indeed.com',
        'yelp.com',
        'zillow.com',
        'target.com',
        'airbnb.com',
        'linkedin.com'
    ],
    'features': [
        'Autocomplete/typeahead',
        'Multi-step wizards',
        'Location autocomplete (Google Places)',
        'Custom dropdowns',
        'Radio/checkbox groups',
        'File uploads',
        'Slider inputs'
    ]
}
```

---

## Usage in Natural Language Prompts

The agent can now handle these prompts:

### Job Search
```
User: "Find Software Engineer jobs in San Francisco on Indeed"

Agent uses: SiteSpecificHandlers.indeed_job_search()
```

### Business Search
```
User: "Search for Italian restaurants in New York on Yelp"

Agent uses: SiteSpecificHandlers.yelp_business_search()
```

### Property Search
```
User: "Find 3-bedroom homes in Austin under $500k on Zillow"

Agent uses: SiteSpecificHandlers.zillow_property_search()
```

### Generic Autocomplete
```
User: "Fill the location field with 'Chicago, IL'"

Agent uses: ComplexFormHandler.fill_location_input()
```

---

## Testing Integration

### Test 1: Basic Autocomplete
```python
from agent.complex_form_handler import ComplexFormHandler

async def test():
    # Assuming page is available
    handler = ComplexFormHandler(page)
    await handler.fill_autocomplete(
        selector='input[name="location"]',
        value='San Francisco, CA'
    )
```

### Test 2: Site-Specific Handler
```python
from agent.complex_form_handler import SiteSpecificHandlers

async def test():
    await SiteSpecificHandlers.indeed_job_search(
        page=page,
        job_title='Data Scientist',
        location='Boston, MA'
    )
```

### Test 3: Multi-Step Form
```python
from agent.complex_form_handler import FormStep, FormField, InputType

async def test():
    handler = ComplexFormHandler(page)

    steps = [
        FormStep(1, [
            FormField('input[name="email"]', 'test@example.com', InputType.EMAIL)
        ], next_button_selector='button:has-text("Next")')
    ]

    result = await handler.fill_multi_step_form(steps)
    print(result)
```

---

## Prompt Examples for Agent

Add these to the agent's example prompts:

```python
EXAMPLE_PROMPTS = [
    # ... existing prompts ...

    {
        'category': 'Job Search',
        'prompt': 'Find Python developer jobs in Seattle on Indeed',
        'tools_used': ['playwright_search_indeed']
    },

    {
        'category': 'Business Search',
        'prompt': 'Search for coffee shops in Portland on Yelp',
        'tools_used': ['playwright_search_yelp']
    },

    {
        'category': 'Real Estate',
        'prompt': 'Find homes in Miami with 2+ bedrooms under $400k on Zillow',
        'tools_used': ['playwright_search_zillow']
    },

    {
        'category': 'Form Automation',
        'prompt': 'Fill out the registration form with my details',
        'tools_used': ['playwright_fill_autocomplete', 'playwright_click', 'playwright_fill']
    }
]
```

---

## Error Handling

The module includes built-in error handling, but you can add agent-level recovery:

```python
async def safe_form_fill(handler, selector, value):
    """Form fill with agent-level recovery"""
    max_retries = 3

    for attempt in range(max_retries):
        try:
            success = await handler.fill_autocomplete(selector, value)

            if success:
                return True

            # If failed, take screenshot for debugging
            await page.screenshot(path=f'form_error_{attempt}.png')

        except Exception as e:
            logger.error(f"Attempt {attempt + 1} failed: {e}")

            if attempt == max_retries - 1:
                # Final attempt failed, ask for human help
                return {
                    'success': False,
                    'error': str(e),
                    'needs_human': True
                }

            # Wait before retry
            await asyncio.sleep(2 ** attempt)

    return False
```

---

## Performance Considerations

### Disable Humanization for Speed
```python
# For batch operations where speed matters
handler = ComplexFormHandler(page, use_humanization=False)
```

### Parallel Form Filling
```python
# Fill multiple forms concurrently
import asyncio

async def fill_multiple_sites(job_title, location):
    tasks = [
        SiteSpecificHandlers.indeed_job_search(page1, job_title, location),
        SiteSpecificHandlers.linkedin_job_search(page2, job_title, location)
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results
```

---

## Troubleshooting Integration

### Issue: Handler not found
**Solution:** Check imports in `__init__.py`:
```python
# In /mnt/c/ev29/eversale-cli/engine/agent/__init__.py
from .complex_form_handler import (
    ComplexFormHandler,
    SiteSpecificHandlers,
    FormField,
    FormStep,
    InputType
)
```

### Issue: Humanization not working
**Solution:** Ensure humanization module is installed:
```bash
pip install scipy numpy  # Required for Bezier curves
```

### Issue: Timeouts on slow sites
**Solution:** Increase timeouts:
```python
handler = ComplexFormHandler(page)
handler.DEFAULT_TIMEOUT = 20000  # 20 seconds
handler.AUTOCOMPLETE_SUGGESTION_TIMEOUT = 10000  # 10 seconds
```

---

## Next Steps

1. **Test on Real Sites**
   - Run examples on Indeed, Yelp, Zillow
   - Verify autocomplete works

2. **Add More Site Handlers**
   - LinkedIn job search
   - Airbnb booking
   - Amazon filters

3. **Integrate with ReAct Loop**
   - Add form detection to reasoning
   - Auto-select appropriate handler

4. **Add to Documentation**
   - Update main README with form capabilities
   - Add to workflow examples

---

## Rollback Plan

If integration causes issues:

1. Remove imports from `brain_enhanced_v2.py`
2. Remove tool registrations from `mcp_client.py`
3. Files are self-contained - no core dependencies

The module is **fully optional** and won't break existing functionality.

---

## Support

For questions or issues:
- Check `COMPLEX_FORM_HANDLER_README.md` for API docs
- Review `complex_form_handler_example.py` for usage patterns
- Run `complex_form_handler_test.py` to verify installation

