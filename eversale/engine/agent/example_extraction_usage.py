"""
Example usage of extraction_helpers.py with the existing agent.

This demonstrates how to integrate the new extraction helpers with
the existing playwright_direct.py browser automation.
"""

import asyncio
from playwright.async_api import async_playwright
from extraction_helpers import (
    extract_links,
    extract_clickable,
    extract_forms,
    extract_contact_forms,
    extract_navigation_links,
    QuickExtractor
)


async def example_basic_extractions():
    """Basic extraction examples."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # Navigate to a test site
        await page.goto('https://news.ycombinator.com')

        print("=== BASIC EXTRACTIONS ===\n")

        # Extract links
        links = await extract_links(page, limit=10)
        print(f"Found {len(links)} links")
        for link in links[:3]:
            print(f"  - {link['text'][:50]} -> {link['href'][:50]}")

        # Extract clickable elements
        clickable = await extract_clickable(page, limit=10)
        print(f"\nFound {len(clickable)} clickable elements")

        # Extract navigation
        nav_links = await extract_navigation_links(page, limit=10)
        print(f"\nFound {len(nav_links)} navigation links")
        for link in nav_links:
            print(f"  - {link['text']}")

        await browser.close()


async def example_form_extraction():
    """Form extraction example."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # Create a test form
        await page.set_content("""
            <html>
            <body>
                <form name="contact" action="/submit" method="post">
                    <input type="text" name="name" placeholder="Your name" required>
                    <input type="email" name="email" placeholder="Email address" required>
                    <input type="tel" name="phone" placeholder="Phone number">
                    <textarea name="message" placeholder="Your message"></textarea>
                    <button type="submit">Send Message</button>
                </form>
            </body>
            </html>
        """)

        print("\n=== FORM EXTRACTION ===\n")

        # Extract all forms
        forms = await extract_forms(page)
        print(f"Found {len(forms)} forms")

        for form in forms:
            print(f"\nForm: {form['name']}")
            print(f"  Action: {form['action']}")
            print(f"  Method: {form['method']}")
            print(f"  Fields: {form['field_count']}")

            for field in form['fields']:
                req = " (required)" if field['required'] else ""
                print(f"    - {field['name']} ({field['type']}){req}")

        # Extract contact forms specifically
        contact_forms = await extract_contact_forms(page)
        print(f"\nContact forms: {len(contact_forms)}")

        await browser.close()


async def example_batch_extraction():
    """Batch extraction using QuickExtractor."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        await page.goto('https://news.ycombinator.com')

        print("\n=== BATCH EXTRACTION ===\n")

        # Create extractor
        extractor = QuickExtractor(page)

        # Execute multiple extractions in parallel
        result = await extractor.extract({
            'all_links': {'type': 'links', 'limit': 50},
            'story_links': {'type': 'links', 'contains_text': '', 'limit': 30},
            'nav_links': {'type': 'links', 'limit': 10},
            'clickable': {'type': 'clickable', 'limit': 20},
            'forms': True,
            'inputs': True
        })

        print(f"Links: {len(result['all_links'])}")
        print(f"Story links: {len(result['story_links'])}")
        print(f"Nav links: {len(result['nav_links'])}")
        print(f"Clickable elements: {len(result['clickable'])}")
        print(f"Forms: {len(result['forms'])}")
        print(f"Inputs: {len(result['inputs'])}")

        await browser.close()


async def example_lead_generation_workflow():
    """Real-world lead generation workflow."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # Example: Extract contact info from a business website
        await page.set_content("""
            <html>
            <body>
                <nav>
                    <a href="/">Home</a>
                    <a href="/about">About</a>
                    <a href="/contact">Contact Us</a>
                    <a href="/services">Services</a>
                </nav>
                <main>
                    <h1>Acme Corp</h1>
                    <p class="tagline">Leading provider of innovative solutions</p>
                    <a href="mailto:info@acme.com">Email Us</a>
                    <a href="tel:+15551234567">Call Us</a>
                </main>
                <footer>
                    <form name="quick-contact" action="/submit" method="post">
                        <input type="text" name="name" placeholder="Name" required>
                        <input type="email" name="email" placeholder="Email" required>
                        <button type="submit">Get Started</button>
                    </form>
                </footer>
            </body>
            </html>
        """)

        print("\n=== LEAD GENERATION WORKFLOW ===\n")

        # Step 1: Extract navigation to find contact page
        nav_links = await extract_navigation_links(page)
        contact_link = next((l for l in nav_links if 'contact' in l['text'].lower()), None)

        if contact_link:
            print(f"Found contact page: {contact_link['href']}")
            print(f"Element ref: {contact_link['mmid']}")

        # Step 2: Extract all contact information at once
        extractor = QuickExtractor(page)
        data = await extractor.extract({
            'contact_links': {'type': 'links', 'contains_text': 'contact'},
            'email_links': {'type': 'links', 'contains_text': 'email'},
            'forms': True
        })

        print(f"\nContact links: {len(data['contact_links'])}")
        print(f"Email links: {len(data['email_links'])}")
        print(f"Forms: {len(data['forms'])}")

        # Step 3: Extract contact forms
        contact_forms = await extract_contact_forms(page)
        if contact_forms:
            form = contact_forms[0]
            print(f"\nContact form found: {form['name']}")
            print(f"  Fields: {', '.join(f['name'] for f in form['fields'])}")

            # In real scenario, would fill and submit form here
            # await page.fill(f"[data-mmid='{form['fields'][0]['mmid']}']", "John Doe")

        await browser.close()


async def example_ecommerce_scraping():
    """E-commerce product extraction."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # Mock product page
        await page.set_content("""
            <html>
            <body>
                <h1 class="product-title">Amazing Laptop Pro</h1>
                <div class="price">$1,299.99</div>
                <img class="product-image" src="/laptop.jpg" alt="Laptop">
                <div data-rating="4.5">4.5 stars</div>
                <div class="description">High-performance laptop for professionals</div>
                <button class="add-to-cart">Add to Cart</button>
                <table class="specs">
                    <tr><th>CPU</th><th>RAM</th><th>Storage</th></tr>
                    <tr><td>Intel i7</td><td>16GB</td><td>512GB SSD</td></tr>
                </table>
            </body>
            </html>
        """)

        print("\n=== E-COMMERCE SCRAPING ===\n")

        # Use QuickExtractor with structured schema
        extractor = QuickExtractor(page)
        result = await extractor.extract({
            'product': {
                'type': 'structured',
                'schema': {
                    'title': 'h1.product-title',
                    'price': '.price',
                    'image': 'img.product-image@src',
                    'rating': '[data-rating]@data-rating',
                    'description': '.description'
                }
            },
            'buttons': {'type': 'clickable', 'role': 'button'},
            'specs': {'type': 'tables'}
        })

        print("Product Information:")
        for key, value in result['product'].items():
            print(f"  {key}: {value}")

        print(f"\nButtons: {len(result['buttons'])}")
        for btn in result['buttons']:
            print(f"  - {btn['text']} (mmid: {btn['mmid']})")

        print(f"\nSpecification tables: {len(result['specs'])}")
        if result['specs']:
            table = result['specs'][0]
            print(f"  Headers: {table['headers']}")
            print(f"  Data: {table['rows']}")

        await browser.close()


async def main():
    """Run all examples."""
    print("Extraction Helpers Examples\n")
    print("=" * 60)

    await example_basic_extractions()
    await example_form_extraction()
    await example_batch_extraction()
    await example_lead_generation_workflow()
    await example_ecommerce_scraping()

    print("\n" + "=" * 60)
    print("\nAll examples completed!")


if __name__ == '__main__':
    asyncio.run(main())
