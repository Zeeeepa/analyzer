"""
Example: Using quick_dom_inspect to avoid browser roundtrips

This shows how to use quick_dom_inspect when you already have HTML
from a previous browser fetch or cache, avoiding unnecessary MCP calls.
"""

from quick_dom_inspect import (
    quick_extract_links,
    quick_extract_forms,
    quick_extract_buttons,
    quick_find_element,
    quick_summary
)


async def example_login_workflow():
    """
    Example: Login form detection without extra browser calls.

    Scenario: We already fetched the page HTML and want to find the login form
    without making another snapshot request.
    """

    # Assume we got this from a previous browser.snapshot() or fetch
    cached_html = """
    <html>
        <body>
            <nav>
                <a href="/home">Home</a>
                <a href="/login">Login</a>
                <a href="/signup">Sign Up</a>
            </nav>

            <div class="login-page">
                <h1>Welcome Back</h1>
                <form action="/api/auth" method="post" id="login-form">
                    <input type="email" name="email" placeholder="Enter email" required>
                    <input type="password" name="password" placeholder="Enter password" required>
                    <input type="checkbox" name="remember" id="remember-me">
                    <label for="remember-me">Remember me</label>
                    <button type="submit">Log In</button>
                </form>
                <a href="/forgot-password">Forgot password?</a>
            </div>
        </body>
    </html>
    """

    # Quick analysis without any browser calls
    print("=== Page Summary ===")
    summary = quick_summary(cached_html)
    print(f"Found {summary['link_count']} links, {summary['form_count']} forms")
    print(f"H1: {summary['h1_headings']}")

    print("\n=== Login Form Details ===")
    forms = quick_extract_forms(cached_html)
    if forms:
        login_form = forms[0]
        print(f"Action: {login_form['action']}")
        print(f"Method: {login_form['method']}")
        print(f"Inputs: {len(login_form['inputs'])}")

        for inp in login_form['inputs']:
            print(f"  - {inp['tag']} type={inp['type']} name={inp['name']}")

    print("\n=== Find Submit Button ===")
    submit_btn = quick_find_element(cached_html, text="Log In", tag="button")
    if submit_btn:
        print(f"Found: {submit_btn['tag']} with text '{submit_btn['text']}'")
        print(f"Type: {submit_btn['type']}")

    print("\n=== Extract Specific Links ===")
    signup_links = quick_extract_links(cached_html, contains_text="sign")
    print(f"Sign-up related links: {len(signup_links)}")
    for link in signup_links:
        print(f"  - {link['text']}: {link['href']}")


async def example_search_results():
    """
    Example: Extracting search results without extra snapshots.

    Scenario: We fetched search results and want to extract all product links
    without additional browser calls.
    """

    search_results_html = """
    <html>
        <body>
            <div class="results">
                <div class="product">
                    <h2><a href="/product/123">Laptop Pro 15</a></h2>
                    <p>$1299.99</p>
                    <button>Add to Cart</button>
                </div>
                <div class="product">
                    <h2><a href="/product/456">Wireless Mouse</a></h2>
                    <p>$29.99</p>
                    <button>Add to Cart</button>
                </div>
                <div class="product">
                    <h2><a href="/product/789">USB-C Cable</a></h2>
                    <p>$12.99</p>
                    <button>Add to Cart</button>
                </div>
            </div>
            <div class="pagination">
                <a href="?page=2">Next</a>
            </div>
        </body>
    </html>
    """

    print("=== Search Results ===")

    # Extract all product links
    all_links = quick_extract_links(search_results_html)
    product_links = [link for link in all_links if '/product/' in link['href']]

    print(f"Found {len(product_links)} products:")
    for link in product_links:
        print(f"  - {link['text']}: {link['href']}")

    # Extract add-to-cart buttons
    buttons = quick_extract_buttons(search_results_html, contains_text="Add to Cart")
    print(f"\nFound {len(buttons)} Add to Cart buttons")

    # Find pagination
    next_link = quick_find_element(search_results_html, text="Next", tag="a")
    if next_link:
        print(f"\nNext page: {next_link['href']}")


async def example_form_filling_prep():
    """
    Example: Prepare form filling strategy without extra snapshots.

    Scenario: We want to analyze a form and plan our filling strategy
    before actually interacting with it.
    """

    registration_html = """
    <html>
        <body>
            <form action="/register" method="post">
                <input type="text" name="first_name" placeholder="First Name" required>
                <input type="text" name="last_name" placeholder="Last Name" required>
                <input type="email" name="email" placeholder="Email" required>
                <input type="password" name="password" placeholder="Password" required>
                <input type="password" name="confirm_password" placeholder="Confirm Password" required>
                <select name="country">
                    <option value="us">United States</option>
                    <option value="ca">Canada</option>
                </select>
                <input type="checkbox" name="terms" required>
                <label>I agree to terms</label>
                <input type="checkbox" name="newsletter">
                <label>Subscribe to newsletter</label>
                <button type="submit">Create Account</button>
            </form>
        </body>
    </html>
    """

    print("=== Form Analysis ===")

    forms = quick_extract_forms(registration_html)
    if forms:
        form = forms[0]
        print(f"Form submits to: {form['action']}")

        # Categorize inputs
        required_fields = [inp for inp in form['inputs'] if inp['required']]
        optional_fields = [inp for inp in form['inputs'] if not inp['required']]

        print(f"\nRequired fields ({len(required_fields)}):")
        for field in required_fields:
            print(f"  - {field['name']} ({field['type']})")

        print(f"\nOptional fields ({len(optional_fields)}):")
        for field in optional_fields:
            print(f"  - {field['name']} ({field['type']})")

        # Now we can plan filling strategy without any browser calls
        print("\nFilling strategy:")
        print("1. Fill all required text/email/password fields")
        print("2. Select country from dropdown")
        print("3. Check required 'terms' checkbox")
        print("4. Optionally check 'newsletter' checkbox")
        print("5. Click submit button")


if __name__ == '__main__':
    import asyncio

    print("Example 1: Login Workflow\n")
    asyncio.run(example_login_workflow())

    print("\n" + "="*60 + "\n")
    print("Example 2: Search Results\n")
    asyncio.run(example_search_results())

    print("\n" + "="*60 + "\n")
    print("Example 3: Form Filling Prep\n")
    asyncio.run(example_form_filling_prep())
