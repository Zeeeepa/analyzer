"""
Quick DOM Inspect - Lightweight HTML parsing without browser roundtrips

This utility provides fast DOM inspection functions that work with raw HTML strings.
No browser or Playwright required - pure Python HTML parsing.

Use case: When you already have page HTML (from a previous fetch), you can extract
data without any browser calls or MCP roundtrips.

Example:
    from quick_dom_inspect import quick_extract_links

    html = "<html>...</html>"  # Already have HTML from previous request
    links = quick_extract_links(html, contains_text="signup")

Features:
- Zero browser dependencies
- Works with cached/stored HTML
- Fast parsing with html.parser
- Returns structured data for easy consumption
"""

import re
from html.parser import HTMLParser
from typing import List, Dict, Optional, Any
from urllib.parse import urljoin


class HTMLExtractor(HTMLParser):
    """Custom HTML parser for extracting specific elements."""

    # Void elements that don't have closing tags
    VOID_ELEMENTS = {
        'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
        'link', 'meta', 'param', 'source', 'track', 'wbr'
    }

    def __init__(self):
        super().__init__()
        self.elements = []
        self.current_tag = None
        self.current_attrs = {}
        self.current_text = []
        self.tag_stack = []
        self.element_id = 0

    def handle_starttag(self, tag, attrs):
        self.element_id += 1
        parent_id = self.tag_stack[-1][3] if self.tag_stack else None

        # For void elements, immediately add to elements without pushing to stack
        if tag in self.VOID_ELEMENTS:
            self.elements.append({
                'tag': tag,
                'attrs': dict(attrs),
                'text': '',
                'depth': len(self.tag_stack),
                'id_internal': self.element_id,
                'parent_id': parent_id
            })
        else:
            self.tag_stack.append((tag, dict(attrs), [], self.element_id, parent_id))

    def handle_endtag(self, tag):
        if not self.tag_stack:
            return

        # Find matching opening tag in stack (handle malformed HTML)
        stack_index = -1
        for i in range(len(self.tag_stack) - 1, -1, -1):
            if self.tag_stack[i][0] == tag:
                stack_index = i
                break

        if stack_index == -1:
            return  # No matching opening tag

        # Pop from stack and record element
        popped_tag, popped_attrs, popped_text, elem_id, parent_id = self.tag_stack.pop(stack_index)
        text_content = ''.join(popped_text).strip()

        # Store element data
        self.elements.append({
            'tag': popped_tag,
            'attrs': popped_attrs,
            'text': text_content,
            'depth': len(self.tag_stack),
            'id_internal': elem_id,
            'parent_id': parent_id
        })

        # Propagate text to parent
        if self.tag_stack:
            self.tag_stack[-1][2].append(text_content)

    def handle_data(self, data):
        if self.tag_stack:
            self.tag_stack[-1][2].append(data)


def quick_extract_links(
    html: str,
    contains_text: Optional[str] = None,
    domain: Optional[str] = None,
    base_url: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Extract links from HTML.

    Args:
        html: Raw HTML string
        contains_text: Filter links by text content (case-insensitive)
        domain: Filter links by domain (e.g., "example.com")
        base_url: Base URL for resolving relative links

    Returns:
        List of dicts with 'href', 'text', 'title' keys

    Example:
        links = quick_extract_links(html, contains_text="signup")
        # [{'href': '/signup', 'text': 'Sign Up', 'title': ''}]
    """
    parser = HTMLExtractor()
    parser.feed(html)

    links = []
    for elem in parser.elements:
        if elem['tag'] != 'a':
            continue

        href = elem['attrs'].get('href', '')
        text = elem['text']
        title = elem['attrs'].get('title', '')

        # Skip empty hrefs
        if not href or href == '#':
            continue

        # Resolve relative URLs if base_url provided
        if base_url:
            href = urljoin(base_url, href)

        # Filter by text content
        if contains_text and contains_text.lower() not in text.lower():
            continue

        # Filter by domain
        if domain and domain not in href:
            continue

        links.append({
            'href': href,
            'text': text,
            'title': title,
            'rel': elem['attrs'].get('rel', ''),
            'target': elem['attrs'].get('target', '')
        })

    return links


def quick_extract_forms(html: str) -> List[Dict[str, Any]]:
    """
    Extract forms from HTML.

    Args:
        html: Raw HTML string

    Returns:
        List of dicts with 'action', 'method', 'inputs' keys

    Example:
        forms = quick_extract_forms(html)
        # [{'action': '/login', 'method': 'post', 'inputs': [...]}]
    """
    parser = HTMLExtractor()
    parser.feed(html)

    # Build parent-child relationships
    form_elements = {}
    for elem in parser.elements:
        if elem['tag'] == 'form':
            form_elements[elem['id_internal']] = {
                'action': elem['attrs'].get('action', ''),
                'method': elem['attrs'].get('method', 'get').lower(),
                'id': elem['attrs'].get('id', ''),
                'name': elem['attrs'].get('name', ''),
                'inputs': []
            }

    # Find inputs that belong to each form
    for elem in parser.elements:
        if elem['tag'] in ('input', 'textarea', 'select', 'button'):
            # Walk up parent chain to find containing form
            parent_id = elem['parent_id']
            while parent_id:
                if parent_id in form_elements:
                    # Found parent form
                    form_elements[parent_id]['inputs'].append({
                        'type': elem['attrs'].get('type', 'text'),
                        'name': elem['attrs'].get('name', ''),
                        'id': elem['attrs'].get('id', ''),
                        'value': elem['attrs'].get('value', ''),
                        'placeholder': elem['attrs'].get('placeholder', ''),
                        'required': 'required' in elem['attrs'],
                        'tag': elem['tag']
                    })
                    break

                # Move to next parent
                parent_elem = next((e for e in parser.elements if e['id_internal'] == parent_id), None)
                if parent_elem:
                    parent_id = parent_elem['parent_id']
                else:
                    break

    return list(form_elements.values())


def quick_extract_inputs(html: str) -> List[Dict[str, Any]]:
    """
    Extract all input fields from HTML.

    Args:
        html: Raw HTML string

    Returns:
        List of dicts with input field details

    Example:
        inputs = quick_extract_inputs(html)
        # [{'type': 'email', 'name': 'user_email', 'id': 'email-input'}]
    """
    parser = HTMLExtractor()
    parser.feed(html)

    inputs = []
    for elem in parser.elements:
        if elem['tag'] in ('input', 'textarea', 'select'):
            inputs.append({
                'tag': elem['tag'],
                'type': elem['attrs'].get('type', 'text'),
                'name': elem['attrs'].get('name', ''),
                'id': elem['attrs'].get('id', ''),
                'value': elem['attrs'].get('value', ''),
                'placeholder': elem['attrs'].get('placeholder', ''),
                'required': 'required' in elem['attrs'],
                'class': elem['attrs'].get('class', ''),
                'aria_label': elem['attrs'].get('aria-label', '')
            })

    return inputs


def quick_extract_text(html: str, selector: Optional[str] = None) -> str:
    """
    Extract text content from HTML.

    Args:
        html: Raw HTML string
        selector: CSS-like selector (tag name or #id or .class)

    Returns:
        Extracted text content

    Example:
        text = quick_extract_text(html, selector='h1')
        # "Welcome to Our Site"
    """
    parser = HTMLExtractor()
    parser.feed(html)

    if not selector:
        # Return all text
        return ' '.join(elem['text'] for elem in parser.elements if elem['text'])

    # Simple selector parsing
    target_tag = None
    target_id = None
    target_class = None

    if selector.startswith('#'):
        target_id = selector[1:]
    elif selector.startswith('.'):
        target_class = selector[1:]
    else:
        target_tag = selector

    # Find matching elements
    texts = []
    for elem in parser.elements:
        if target_tag and elem['tag'] != target_tag:
            continue
        if target_id and elem['attrs'].get('id') != target_id:
            continue
        if target_class and target_class not in elem['attrs'].get('class', '').split():
            continue

        if elem['text']:
            texts.append(elem['text'])

    return ' '.join(texts)


def quick_extract_tables(html: str) -> List[Dict[str, Any]]:
    """
    Extract tables from HTML.

    Args:
        html: Raw HTML string

    Returns:
        List of dicts with 'headers' and 'rows' keys

    Example:
        tables = quick_extract_tables(html)
        # [{'headers': ['Name', 'Email'], 'rows': [['John', 'john@ex.com']]}]
    """
    parser = HTMLExtractor()
    parser.feed(html)

    tables = []
    current_table = None
    current_row = []
    in_header = False
    table_depth = -1

    for elem in parser.elements:
        if elem['tag'] == 'table':
            current_table = {'headers': [], 'rows': [], 'id': elem['attrs'].get('id', '')}
            table_depth = elem['depth']
            tables.append(current_table)

        elif current_table and elem['depth'] > table_depth:
            if elem['tag'] == 'thead':
                in_header = True
            elif elem['tag'] == 'tbody':
                in_header = False
            elif elem['tag'] == 'tr':
                current_row = []
            elif elem['tag'] in ('th', 'td'):
                current_row.append(elem['text'])

                # Check if row is complete (simplified - assumes all rows have same length)
                if elem['tag'] == 'th':
                    if current_row and current_row not in (current_table['headers'] or []):
                        current_table['headers'].append(current_row[-1])
                elif elem['tag'] == 'td' and current_row:
                    # Add row when we hit the last td (simplified)
                    pass

        # Simplified row completion detection
        if elem['tag'] == 'tr' and current_row and current_table:
            if in_header:
                if current_row and current_row not in current_table.get('headers', []):
                    current_table['headers'] = current_row
            else:
                if current_row and current_row not in current_table.get('rows', []):
                    current_table['rows'].append(current_row)
            current_row = []

    return tables


def quick_find_element(
    html: str,
    text: Optional[str] = None,
    role: Optional[str] = None,
    tag: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Find a single element by text content, ARIA role, or tag name.

    Args:
        html: Raw HTML string
        text: Text to search for (case-insensitive partial match)
        role: ARIA role to search for
        tag: HTML tag name to search for

    Returns:
        Dict with element details or None if not found

    Example:
        elem = quick_find_element(html, text="Submit", tag="button")
        # {'tag': 'button', 'text': 'Submit', 'id': 'submit-btn'}
    """
    parser = HTMLExtractor()
    parser.feed(html)

    for elem in parser.elements:
        # Check text match
        if text and text.lower() not in elem['text'].lower():
            continue

        # Check role match
        if role and elem['attrs'].get('role') != role:
            continue

        # Check tag match
        if tag and elem['tag'] != tag:
            continue

        # Found match
        return {
            'tag': elem['tag'],
            'text': elem['text'],
            'id': elem['attrs'].get('id', ''),
            'class': elem['attrs'].get('class', ''),
            'name': elem['attrs'].get('name', ''),
            'role': elem['attrs'].get('role', ''),
            'aria_label': elem['attrs'].get('aria-label', ''),
            'type': elem['attrs'].get('type', ''),
            'href': elem['attrs'].get('href', ''),
            'value': elem['attrs'].get('value', '')
        }

    return None


def quick_extract_buttons(html: str, contains_text: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Extract buttons from HTML (button tags and input type=button/submit).

    Args:
        html: Raw HTML string
        contains_text: Filter buttons by text content (case-insensitive)

    Returns:
        List of dicts with button details

    Example:
        buttons = quick_extract_buttons(html, contains_text="submit")
        # [{'text': 'Submit Form', 'type': 'submit', 'id': 'submit-btn'}]
    """
    parser = HTMLExtractor()
    parser.feed(html)

    buttons = []
    for elem in parser.elements:
        is_button = (
            elem['tag'] == 'button' or
            (elem['tag'] == 'input' and elem['attrs'].get('type') in ('button', 'submit', 'reset'))
        )

        if not is_button:
            continue

        text = elem['text'] or elem['attrs'].get('value', '')

        # Filter by text
        if contains_text and contains_text.lower() not in text.lower():
            continue

        buttons.append({
            'tag': elem['tag'],
            'text': text,
            'type': elem['attrs'].get('type', 'button'),
            'id': elem['attrs'].get('id', ''),
            'name': elem['attrs'].get('name', ''),
            'class': elem['attrs'].get('class', ''),
            'disabled': 'disabled' in elem['attrs']
        })

    return buttons


def quick_extract_headings(html: str) -> Dict[str, List[str]]:
    """
    Extract all headings (h1-h6) from HTML.

    Args:
        html: Raw HTML string

    Returns:
        Dict mapping heading levels to lists of text

    Example:
        headings = quick_extract_headings(html)
        # {'h1': ['Main Title'], 'h2': ['Section 1', 'Section 2']}
    """
    parser = HTMLExtractor()
    parser.feed(html)

    headings = {'h1': [], 'h2': [], 'h3': [], 'h4': [], 'h5': [], 'h6': []}

    for elem in parser.elements:
        if elem['tag'] in headings and elem['text']:
            headings[elem['tag']].append(elem['text'])

    return headings


# Convenience function for quick debugging
def quick_summary(html: str) -> Dict[str, Any]:
    """
    Get a quick summary of HTML structure.

    Args:
        html: Raw HTML string

    Returns:
        Dict with counts and samples of various elements

    Example:
        summary = quick_summary(html)
        # {'link_count': 42, 'form_count': 1, 'sample_links': [...]}
    """
    links = quick_extract_links(html)
    forms = quick_extract_forms(html)
    inputs = quick_extract_inputs(html)
    buttons = quick_extract_buttons(html)
    headings = quick_extract_headings(html)

    return {
        'link_count': len(links),
        'form_count': len(forms),
        'input_count': len(inputs),
        'button_count': len(buttons),
        'heading_count': sum(len(v) for v in headings.values()),
        'sample_links': links[:5],
        'sample_buttons': buttons[:3],
        'h1_headings': headings.get('h1', [])
    }


if __name__ == '__main__':
    # Quick test
    test_html = """
    <html>
        <head><title>Test Page</title></head>
        <body>
            <h1>Welcome</h1>
            <form action="/login" method="post">
                <input type="email" name="email" placeholder="Email" required>
                <input type="password" name="password" placeholder="Password">
                <button type="submit">Login</button>
            </form>
            <a href="/signup">Sign Up</a>
            <a href="/about">About Us</a>
        </body>
    </html>
    """

    print("Links:", quick_extract_links(test_html))
    print("\nForms:", quick_extract_forms(test_html))
    print("\nInputs:", quick_extract_inputs(test_html))
    print("\nButtons:", quick_extract_buttons(test_html))
    print("\nHeadings:", quick_extract_headings(test_html))
    print("\nSummary:", quick_summary(test_html))
    print("\nFind element:", quick_find_element(test_html, text="Login", tag="button"))
