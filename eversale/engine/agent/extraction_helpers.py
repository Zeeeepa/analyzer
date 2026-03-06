"""
JavaScript-based extraction utilities for fast, efficient page data extraction.

This module provides helper functions that run optimized JavaScript in the browser
to extract structured data without requiring LLM analysis. All functions return
element refs (mmid) for subsequent interactions.

Key Features:
- Pure JavaScript execution for speed
- Filtering and limiting in-browser
- Minimal data transfer
- Element refs for follow-up interactions
- Support for batching multiple extractions

Usage:
    # Single extraction
    links = await extract_links(page, contains_text='signup', limit=10)

    # Batch multiple extractions
    extractor = QuickExtractor(page)
    result = await extractor.extract({
        'links': {'contains_text': 'signup'},
        'buttons': {'role': 'button'},
        'forms': True
    })
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class ExtractedElement:
    """Represents an extracted page element with interaction metadata."""
    mmid: str  # Element reference for interactions
    tag: str
    text: str
    href: Optional[str] = None
    role: Optional[str] = None
    type: Optional[str] = None
    name: Optional[str] = None
    value: Optional[str] = None
    aria_label: Optional[str] = None
    placeholder: Optional[str] = None
    x: Optional[float] = None
    y: Optional[float] = None
    width: Optional[float] = None
    height: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values."""
        return {k: v for k, v in asdict(self).items() if v is not None}


async def extract_links(
    page,
    contains_text: str = None,
    domain: str = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """
    Extract links from the page with optional filtering.

    Args:
        page: Playwright page object
        contains_text: Filter links containing this text (case-insensitive)
        domain: Filter links to specific domain (e.g., 'example.com')
        limit: Maximum number of links to return

    Returns:
        List of link objects with mmid, href, text, and position

    Example:
        signup_links = await extract_links(page, contains_text='sign up', limit=5)
        external = await extract_links(page, domain='github.com')
    """
    try:
        # Ensure mmid attributes are injected
        await _inject_mmids_if_needed(page)

        js_code = """
        (args) => {
            const [containsText, domain, maxLinks] = args;
            const results = [];
            const links = document.querySelectorAll('a[href]');

            for (const link of links) {
                if (results.length >= maxLinks) break;

                const text = link.textContent?.trim() || '';
                const href = link.href;

                // Filter by text if specified
                if (containsText && !text.toLowerCase().includes(containsText.toLowerCase())) {
                    continue;
                }

                // Filter by domain if specified
                if (domain) {
                    try {
                        const url = new URL(href);
                        if (!url.hostname.includes(domain)) {
                            continue;
                        }
                    } catch (e) {
                        continue;
                    }
                }

                // Get element position
                const rect = link.getBoundingClientRect();

                // Get mmid (try different attribute names)
                const mmid = link.getAttribute('data-mmid') ||
                            link.getAttribute('data-mmid-v1') ||
                            link.getAttribute('data-mmid-id') || '';

                results.push({
                    mmid: mmid,
                    tag: 'a',
                    text: text,
                    href: href,
                    aria_label: link.getAttribute('aria-label'),
                    x: rect.x,
                    y: rect.y,
                    width: rect.width,
                    height: rect.height
                });
            }

            return results;
        }
        """

        result = await page.evaluate(js_code, [contains_text, domain, limit])
        return result

    except Exception as e:
        logger.error(f"extract_links failed: {e}")
        return []


async def extract_clickable(
    page,
    contains_text: str = None,
    role: str = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """
    Extract clickable elements (buttons, links, inputs) with optional filtering.

    Args:
        page: Playwright page object
        contains_text: Filter elements containing this text
        role: Filter by ARIA role (button, link, menuitem, etc.)
        limit: Maximum number of elements to return

    Returns:
        List of clickable element objects with mmid and metadata

    Example:
        buttons = await extract_clickable(page, role='button')
        submit_btns = await extract_clickable(page, contains_text='submit')
    """
    try:
        await _inject_mmids_if_needed(page)

        js_code = """
        (args) => {
            const [containsText, roleFilter, maxElements] = args;
            const results = [];

            // Clickable selectors
            const selectors = [
                'button',
                'a[href]',
                'input[type="button"]',
                'input[type="submit"]',
                'input[type="reset"]',
                '[role="button"]',
                '[role="link"]',
                '[role="menuitem"]',
                '[onclick]'
            ];

            const elements = document.querySelectorAll(selectors.join(','));

            for (const el of elements) {
                if (results.length >= maxElements) break;

                const text = el.textContent?.trim() || el.value || '';
                const role = el.getAttribute('role') ||
                           (el.tagName === 'BUTTON' ? 'button' :
                            el.tagName === 'A' ? 'link' :
                            el.type || '');

                // Filter by text if specified
                if (containsText && !text.toLowerCase().includes(containsText.toLowerCase())) {
                    continue;
                }

                // Filter by role if specified
                if (roleFilter && role.toLowerCase() !== roleFilter.toLowerCase()) {
                    continue;
                }

                // Check visibility
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                const isVisible = style.display !== 'none' &&
                                style.visibility !== 'hidden' &&
                                rect.width > 0 && rect.height > 0;

                if (!isVisible) continue;

                const mmid = el.getAttribute('data-mmid') ||
                            el.getAttribute('data-mmid-v1') ||
                            el.getAttribute('data-mmid-id') || '';

                results.push({
                    mmid: mmid,
                    tag: el.tagName.toLowerCase(),
                    text: text,
                    role: role,
                    type: el.type || null,
                    href: el.href || null,
                    aria_label: el.getAttribute('aria-label'),
                    x: rect.x,
                    y: rect.y,
                    width: rect.width,
                    height: rect.height
                });
            }

            return results;
        }
        """

        result = await page.evaluate(js_code, [contains_text, role, limit])
        return result

    except Exception as e:
        logger.error(f"extract_clickable failed: {e}")
        return []


async def extract_forms(page) -> List[Dict[str, Any]]:
    """
    Extract all forms and their input fields.

    Args:
        page: Playwright page object

    Returns:
        List of form objects with mmid, action, method, and fields

    Example:
        forms = await extract_forms(page)
        for form in forms:
            print(f"Form: {form['name']} with {len(form['fields'])} fields")
    """
    try:
        await _inject_mmids_if_needed(page)

        js_code = """
        () => {
            const results = [];
            const forms = document.querySelectorAll('form');

            for (const form of forms) {
                const mmid = form.getAttribute('data-mmid') ||
                            form.getAttribute('data-mmid-v1') ||
                            form.getAttribute('data-mmid-id') || '';

                const fields = [];
                const inputs = form.querySelectorAll('input, textarea, select');

                for (const input of inputs) {
                    const inputMmid = input.getAttribute('data-mmid') ||
                                     input.getAttribute('data-mmid-v1') ||
                                     input.getAttribute('data-mmid-id') || '';

                    fields.push({
                        mmid: inputMmid,
                        tag: input.tagName.toLowerCase(),
                        type: input.type || 'text',
                        name: input.name || '',
                        placeholder: input.placeholder || '',
                        value: input.value || '',
                        required: input.required || false,
                        aria_label: input.getAttribute('aria-label')
                    });
                }

                results.push({
                    mmid: mmid,
                    tag: 'form',
                    name: form.name || '',
                    action: form.action || '',
                    method: form.method || 'get',
                    fields: fields,
                    field_count: fields.length
                });
            }

            return results;
        }
        """

        result = await page.evaluate(js_code)
        return result

    except Exception as e:
        logger.error(f"extract_forms failed: {e}")
        return []


async def extract_inputs(page) -> List[Dict[str, Any]]:
    """
    Extract all input fields, including those not in forms.

    Args:
        page: Playwright page object

    Returns:
        List of input objects with mmid and metadata

    Example:
        inputs = await extract_inputs(page)
        email_inputs = [i for i in inputs if 'email' in i['type']]
    """
    try:
        await _inject_mmids_if_needed(page)

        js_code = """
        () => {
            const results = [];
            const inputs = document.querySelectorAll('input, textarea, select');

            for (const input of inputs) {
                const mmid = input.getAttribute('data-mmid') ||
                            input.getAttribute('data-mmid-v1') ||
                            input.getAttribute('data-mmid-id') || '';

                const rect = input.getBoundingClientRect();
                const style = window.getComputedStyle(input);
                const isVisible = style.display !== 'none' &&
                                style.visibility !== 'hidden' &&
                                rect.width > 0 && rect.height > 0;

                results.push({
                    mmid: mmid,
                    tag: input.tagName.toLowerCase(),
                    type: input.type || 'text',
                    name: input.name || '',
                    placeholder: input.placeholder || '',
                    value: input.value || '',
                    required: input.required || false,
                    aria_label: input.getAttribute('aria-label'),
                    is_visible: isVisible,
                    x: rect.x,
                    y: rect.y
                });
            }

            return results;
        }
        """

        result = await page.evaluate(js_code)
        return result

    except Exception as e:
        logger.error(f"extract_inputs failed: {e}")
        return []


async def extract_text_content(
    page,
    selector: str = None
) -> str:
    """
    Extract text content from page or specific element.

    Args:
        page: Playwright page object
        selector: Optional CSS selector to extract from specific element

    Returns:
        Extracted text content

    Example:
        full_text = await extract_text_content(page)
        main_text = await extract_text_content(page, selector='main')
    """
    try:
        js_code = """
        (selector) => {
            if (selector) {
                const el = document.querySelector(selector);
                return el ? el.textContent?.trim() : '';
            }
            return document.body.textContent?.trim() || '';
        }
        """

        result = await page.evaluate(js_code, selector)
        return result or ''

    except Exception as e:
        logger.error(f"extract_text_content failed: {e}")
        return ''


async def extract_tables(page) -> List[Dict[str, Any]]:
    """
    Extract all tables with headers and row data.

    Args:
        page: Playwright page object

    Returns:
        List of table objects with mmid, headers, and rows

    Example:
        tables = await extract_tables(page)
        for table in tables:
            print(f"Table with {len(table['rows'])} rows")
    """
    try:
        await _inject_mmids_if_needed(page)

        js_code = """
        () => {
            const results = [];
            const tables = document.querySelectorAll('table');

            for (const table of tables) {
                const mmid = table.getAttribute('data-mmid') ||
                            table.getAttribute('data-mmid-v1') ||
                            table.getAttribute('data-mmid-id') || '';

                // Extract headers
                const headers = [];
                const headerCells = table.querySelectorAll('thead th, thead td, tr:first-child th');
                for (const cell of headerCells) {
                    headers.push(cell.textContent?.trim() || '');
                }

                // Extract rows
                const rows = [];
                const bodyRows = table.querySelectorAll('tbody tr, tr');

                for (const row of bodyRows) {
                    // Skip header row if no thead
                    if (row.querySelector('th') && !table.querySelector('thead')) {
                        continue;
                    }

                    const cells = [];
                    const rowCells = row.querySelectorAll('td');
                    for (const cell of rowCells) {
                        cells.push(cell.textContent?.trim() || '');
                    }

                    if (cells.length > 0) {
                        rows.push(cells);
                    }
                }

                // Only include tables with data
                if (headers.length > 0 || rows.length > 0) {
                    results.push({
                        mmid: mmid,
                        tag: 'table',
                        headers: headers,
                        rows: rows,
                        row_count: rows.length,
                        column_count: headers.length || (rows[0]?.length || 0)
                    });
                }
            }

            return results;
        }
        """

        result = await page.evaluate(js_code)
        return result

    except Exception as e:
        logger.error(f"extract_tables failed: {e}")
        return []


async def extract_structured(
    page,
    schema: Dict[str, str]
) -> Dict[str, Any]:
    """
    Extract data according to a custom schema with CSS selectors.

    Args:
        page: Playwright page object
        schema: Dict mapping field names to CSS selectors
               Use @attr syntax to extract attributes (e.g., 'a@href')

    Returns:
        Dict with extracted values for each schema field

    Example:
        product = await extract_structured(page, {
            'title': 'h1.product-title',
            'price': '.price',
            'image': 'img.main@src',
            'rating': '[data-rating]@data-rating'
        })
    """
    try:
        js_code = """
        (schema) => {
            const result = {};

            for (const [field, selector] of Object.entries(schema)) {
                let sel = selector;
                let attr = null;

                // Check for @attribute syntax
                if (selector.includes('@')) {
                    const parts = selector.split('@');
                    sel = parts[0];
                    attr = parts[1];
                }

                const el = document.querySelector(sel);
                if (el) {
                    if (attr) {
                        result[field] = el.getAttribute(attr) || '';
                    } else {
                        result[field] = el.textContent?.trim() || '';
                    }
                } else {
                    result[field] = null;
                }
            }

            return result;
        }
        """

        result = await page.evaluate(js_code, schema)
        return result

    except Exception as e:
        logger.error(f"extract_structured failed: {e}")
        return {}


class QuickExtractor:
    """
    Batch multiple extractions in a single operation.

    This class allows you to define multiple extraction operations and
    execute them in parallel for better performance.

    Example:
        extractor = QuickExtractor(page)
        result = await extractor.extract({
            'links': {'contains_text': 'signup', 'limit': 5},
            'buttons': {'role': 'button'},
            'forms': True,
            'inputs': True,
            'tables': True
        })

        # Access results
        signup_links = result['links']
        all_buttons = result['buttons']
        all_forms = result['forms']
    """

    def __init__(self, page):
        """
        Initialize QuickExtractor.

        Args:
            page: Playwright page object
        """
        self.page = page

    async def extract(self, operations: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute multiple extraction operations in parallel.

        Args:
            operations: Dict mapping result keys to extraction configs
                       Config can be True (use defaults) or dict with params

        Returns:
            Dict mapping result keys to extraction results

        Example:
            result = await extractor.extract({
                'links': {'contains_text': 'contact'},
                'buttons': True,  # Use defaults
                'forms': True,
                'product_info': {
                    'type': 'structured',
                    'schema': {'title': 'h1', 'price': '.price'}
                }
            })
        """
        tasks = []
        keys = []

        for key, config in operations.items():
            if config is True:
                config = {}

            # Determine extraction type
            extract_type = config.pop('type', key)

            # Create task based on type
            if extract_type == 'links':
                task = extract_links(self.page, **config)
            elif extract_type == 'clickable' or extract_type == 'buttons':
                task = extract_clickable(self.page, **config)
            elif extract_type == 'forms':
                task = extract_forms(self.page)
            elif extract_type == 'inputs':
                task = extract_inputs(self.page)
            elif extract_type == 'tables':
                task = extract_tables(self.page)
            elif extract_type == 'text':
                task = extract_text_content(self.page, **config)
            elif extract_type == 'structured':
                schema = config.get('schema', {})
                task = extract_structured(self.page, schema)
            else:
                logger.warning(f"Unknown extraction type: {extract_type}")
                continue

            tasks.append(task)
            keys.append(key)

        # Execute all tasks in parallel
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Build result dict
            output = {}
            for key, result in zip(keys, results):
                if isinstance(result, Exception):
                    logger.error(f"Extraction '{key}' failed: {result}")
                    output[key] = [] if key != 'text' else ''
                else:
                    output[key] = result

            return output

        except Exception as e:
            logger.error(f"QuickExtractor.extract failed: {e}")
            return {key: [] for key in keys}


async def _inject_mmids_if_needed(page) -> None:
    """
    Internal helper to inject mmid attributes if not already present.

    This ensures all extracted elements have unique identifiers for
    subsequent interactions. Uses the same strategy as dom_fusion.py.
    """
    try:
        # Check if mmids already exist
        has_mmids = await page.evaluate("""
            () => {
                const el = document.querySelector('[data-mmid], [data-mmid-v1], [data-mmid-id]');
                return el !== null;
            }
        """)

        if has_mmids:
            return

        # Inject mmids with randomized counter
        import random
        counter = random.randint(1000, 9999)

        # Randomize attribute name to avoid detection
        attr_suffix = random.choice(['', '-v1', '-id', ''])
        attr_name = f'data-mmid{attr_suffix}'

        js_code = f"""
        (function() {{
            let counter = {counter};
            const elements = document.querySelectorAll('*');
            elements.forEach(el => {{
                if (!el.hasAttribute('data-mmid') &&
                    !el.hasAttribute('data-mmid-v1') &&
                    !el.hasAttribute('data-mmid-id')) {{
                    el.setAttribute('{attr_name}', 'mm-' + counter++);
                }}
            }});
            return counter;
        }})()
        """

        await page.evaluate(js_code)
        logger.debug(f"Injected mmid attributes using {attr_name}")

    except Exception as e:
        logger.debug(f"mmid injection skipped: {e}")


# Convenience exports for common patterns
async def extract_contact_forms(page) -> List[Dict[str, Any]]:
    """Extract forms that look like contact/signup forms."""
    forms = await extract_forms(page)
    contact_forms = []

    for form in forms:
        # Check if form has typical contact/signup fields
        field_types = [f['type'] for f in form['fields']]
        if any(t in ['email', 'tel', 'text'] for t in field_types):
            contact_forms.append(form)

    return contact_forms


async def extract_navigation_links(page, limit: int = 20) -> List[Dict[str, Any]]:
    """Extract main navigation links (header/menu)."""
    try:
        await _inject_mmids_if_needed(page)

        js_code = """
        (maxLinks) => {
            const results = [];

            // Look for nav elements and common navigation selectors
            const navs = document.querySelectorAll('nav, header, [role="navigation"]');

            for (const nav of navs) {
                const links = nav.querySelectorAll('a[href]');

                for (const link of links) {
                    if (results.length >= maxLinks) break;

                    const text = link.textContent?.trim() || '';
                    if (!text) continue;

                    const mmid = link.getAttribute('data-mmid') ||
                                link.getAttribute('data-mmid-v1') ||
                                link.getAttribute('data-mmid-id') || '';

                    results.push({
                        mmid: mmid,
                        tag: 'a',
                        text: text,
                        href: link.href
                    });
                }
            }

            return results;
        }
        """

        result = await page.evaluate(js_code, limit)
        return result

    except Exception as e:
        logger.error(f"extract_navigation_links failed: {e}")
        return []
