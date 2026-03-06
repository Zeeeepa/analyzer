"""
Tests for extraction_helpers.py

Run with: pytest engine/agent/test_extraction_helpers.py -v
"""

import pytest
from playwright.async_api import async_playwright
from extraction_helpers import (
    extract_links,
    extract_clickable,
    extract_forms,
    extract_inputs,
    extract_text_content,
    extract_tables,
    extract_structured,
    extract_contact_forms,
    extract_navigation_links,
    QuickExtractor
)


@pytest.fixture
async def browser_and_page():
    """Fixture providing a browser and page for testing."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        yield browser, page
        await browser.close()


@pytest.mark.asyncio
async def test_extract_links(browser_and_page):
    """Test link extraction."""
    _, page = browser_and_page

    # Create a simple test page
    await page.set_content("""
        <html>
        <body>
            <a href="https://example.com">Example Link</a>
            <a href="https://github.com">GitHub</a>
            <a href="https://example.com/signup">Sign Up</a>
        </body>
        </html>
    """)

    # Extract all links
    links = await extract_links(page, limit=10)
    assert len(links) == 3
    assert all('mmid' in link for link in links)
    assert all('href' in link for link in links)

    # Filter by text
    signup_links = await extract_links(page, contains_text='sign up', limit=10)
    assert len(signup_links) == 1
    assert 'signup' in signup_links[0]['href']

    # Filter by domain
    github_links = await extract_links(page, domain='github.com', limit=10)
    assert len(github_links) == 1


@pytest.mark.asyncio
async def test_extract_clickable(browser_and_page):
    """Test clickable element extraction."""
    _, page = browser_and_page

    await page.set_content("""
        <html>
        <body>
            <button type="submit">Submit</button>
            <button type="button">Click Me</button>
            <input type="button" value="Button Input">
            <a href="#" role="button">Link Button</a>
        </body>
        </html>
    """)

    # Extract all clickable elements
    clickable = await extract_clickable(page, limit=20)
    assert len(clickable) >= 4

    # Filter by role
    buttons = await extract_clickable(page, role='button', limit=20)
    assert len(buttons) >= 2

    # Filter by text
    submit_btns = await extract_clickable(page, contains_text='submit', limit=20)
    assert len(submit_btns) == 1


@pytest.mark.asyncio
async def test_extract_forms(browser_and_page):
    """Test form extraction."""
    _, page = browser_and_page

    await page.set_content("""
        <html>
        <body>
            <form name="contact" action="/submit" method="post">
                <input type="text" name="name" placeholder="Your name">
                <input type="email" name="email" placeholder="Email">
                <textarea name="message"></textarea>
                <button type="submit">Send</button>
            </form>
        </body>
        </html>
    """)

    forms = await extract_forms(page)
    assert len(forms) == 1
    assert forms[0]['name'] == 'contact'
    assert forms[0]['action'].endswith('/submit')
    assert forms[0]['method'] == 'post'
    assert forms[0]['field_count'] == 3
    assert all('mmid' in field for field in forms[0]['fields'])


@pytest.mark.asyncio
async def test_extract_inputs(browser_and_page):
    """Test input extraction."""
    _, page = browser_and_page

    await page.set_content("""
        <html>
        <body>
            <input type="text" name="username" placeholder="Username">
            <input type="password" name="password">
            <input type="email" name="email">
            <textarea name="bio"></textarea>
        </body>
        </html>
    """)

    inputs = await extract_inputs(page)
    assert len(inputs) == 4
    assert all('mmid' in inp for inp in inputs)
    assert all('type' in inp for inp in inputs)

    # Check email input
    email_inputs = [i for i in inputs if i['type'] == 'email']
    assert len(email_inputs) == 1


@pytest.mark.asyncio
async def test_extract_text_content(browser_and_page):
    """Test text extraction."""
    _, page = browser_and_page

    await page.set_content("""
        <html>
        <body>
            <main>
                <h1>Main Content</h1>
                <p>This is the main text.</p>
            </main>
            <footer>Footer text</footer>
        </body>
        </html>
    """)

    # Extract full body text
    full_text = await extract_text_content(page)
    assert 'Main Content' in full_text
    assert 'Footer text' in full_text

    # Extract specific element text
    main_text = await extract_text_content(page, selector='main')
    assert 'Main Content' in main_text
    assert 'Footer text' not in main_text


@pytest.mark.asyncio
async def test_extract_tables(browser_and_page):
    """Test table extraction."""
    _, page = browser_and_page

    await page.set_content("""
        <html>
        <body>
            <table>
                <thead>
                    <tr>
                        <th>Name</th>
                        <th>Age</th>
                        <th>City</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td>Alice</td>
                        <td>30</td>
                        <td>NYC</td>
                    </tr>
                    <tr>
                        <td>Bob</td>
                        <td>25</td>
                        <td>LA</td>
                    </tr>
                </tbody>
            </table>
        </body>
        </html>
    """)

    tables = await extract_tables(page)
    assert len(tables) == 1
    assert tables[0]['headers'] == ['Name', 'Age', 'City']
    assert tables[0]['row_count'] == 2
    assert tables[0]['column_count'] == 3
    assert len(tables[0]['rows']) == 2
    assert 'mmid' in tables[0]


@pytest.mark.asyncio
async def test_extract_structured(browser_and_page):
    """Test structured extraction with schema."""
    _, page = browser_and_page

    await page.set_content("""
        <html>
        <body>
            <h1 class="product-title">Amazing Product</h1>
            <div class="price">$99.99</div>
            <img class="main-image" src="/image.jpg" alt="Product">
            <span data-rating="4.5">4.5 stars</span>
        </body>
        </html>
    """)

    schema = {
        'title': 'h1.product-title',
        'price': '.price',
        'image': 'img.main-image@src',
        'rating': '[data-rating]@data-rating'
    }

    result = await extract_structured(page, schema)
    assert result['title'] == 'Amazing Product'
    assert result['price'] == '$99.99'
    assert result['image'] == '/image.jpg'
    assert result['rating'] == '4.5'


@pytest.mark.asyncio
async def test_quick_extractor(browser_and_page):
    """Test QuickExtractor batch operations."""
    _, page = browser_and_page

    await page.set_content("""
        <html>
        <body>
            <nav>
                <a href="/">Home</a>
                <a href="/about">About</a>
            </nav>
            <form>
                <input type="email" name="email">
                <button type="submit">Submit</button>
            </form>
            <table>
                <tr><th>Col1</th><th>Col2</th></tr>
                <tr><td>Data1</td><td>Data2</td></tr>
            </table>
        </body>
        </html>
    """)

    extractor = QuickExtractor(page)
    result = await extractor.extract({
        'links': True,
        'buttons': {'role': 'button'},
        'forms': True,
        'tables': True
    })

    assert 'links' in result
    assert 'buttons' in result
    assert 'forms' in result
    assert 'tables' in result

    assert len(result['links']) == 2
    assert len(result['forms']) == 1
    assert len(result['tables']) == 1


@pytest.mark.asyncio
async def test_extract_contact_forms(browser_and_page):
    """Test contact form detection."""
    _, page = browser_and_page

    await page.set_content("""
        <html>
        <body>
            <form name="contact">
                <input type="text" name="name">
                <input type="email" name="email">
                <input type="tel" name="phone">
                <button>Send</button>
            </form>
            <form name="other">
                <input type="checkbox" name="agree">
            </form>
        </body>
        </html>
    """)

    contact_forms = await extract_contact_forms(page)
    assert len(contact_forms) == 1
    assert contact_forms[0]['name'] == 'contact'


@pytest.mark.asyncio
async def test_extract_navigation_links(browser_and_page):
    """Test navigation link extraction."""
    _, page = browser_and_page

    await page.set_content("""
        <html>
        <body>
            <nav>
                <a href="/">Home</a>
                <a href="/products">Products</a>
                <a href="/about">About</a>
            </nav>
            <main>
                <a href="/random">Random Link</a>
            </main>
        </body>
        </html>
    """)

    nav_links = await extract_navigation_links(page, limit=10)
    assert len(nav_links) == 3
    assert all('mmid' in link for link in nav_links)
    assert all(link['text'] in ['Home', 'Products', 'About'] for link in nav_links)


@pytest.mark.asyncio
async def test_mmid_injection(browser_and_page):
    """Test that mmid attributes are properly injected."""
    _, page = browser_and_page

    await page.set_content("""
        <html>
        <body>
            <div>Test</div>
            <a href="#">Link</a>
            <button>Button</button>
        </body>
        </html>
    """)

    # First extraction should inject mmids
    links = await extract_links(page, limit=10)

    # Check that mmids exist
    has_mmids = await page.evaluate("""
        () => {
            const elements = document.querySelectorAll('[data-mmid], [data-mmid-v1], [data-mmid-id]');
            return elements.length > 0;
        }
    """)

    assert has_mmids
    assert all(link['mmid'].startswith('mm-') for link in links)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
