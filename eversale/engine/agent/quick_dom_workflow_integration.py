"""
Real-world integration example: Using quick_dom_inspect in agent workflows

This shows how to integrate quick_dom_inspect into actual browser automation
to reduce roundtrips and improve performance.
"""

import asyncio
from typing import Dict, Any, Optional


class MockBrowser:
    """Mock browser for demonstration - replace with actual DOMFirstBrowser"""

    def __init__(self):
        self.current_html = ""
        self.snapshots = 0

    async def navigate(self, url: str):
        print(f"[Browser] Navigating to {url}")
        # Simulate navigation
        self.current_html = f"<html><body>Page: {url}</body></html>"

    async def snapshot(self) -> Dict[str, Any]:
        self.snapshots += 1
        print(f"[Browser] Taking snapshot #{self.snapshots}")
        return {"html": self.current_html, "nodes": []}

    def get_cached_html(self) -> str:
        """Get last HTML without new snapshot"""
        return self.current_html


async def workflow_before_optimization():
    """
    BEFORE: Multiple snapshots for analysis
    Problem: Each snapshot = MCP roundtrip = latency
    """
    browser = MockBrowser()

    print("=== BEFORE OPTIMIZATION ===\n")

    # Navigate to page
    await browser.navigate("https://example.com/login")

    # Snapshot 1: Check if login form exists
    snapshot = await browser.snapshot()
    print("Snapshot 1: Check for login form")

    # Snapshot 2: Find submit button
    snapshot = await browser.snapshot()
    print("Snapshot 2: Find submit button")

    # Snapshot 3: Check for 'remember me' checkbox
    snapshot = await browser.snapshot()
    print("Snapshot 3: Check for remember me")

    print(f"\nTotal snapshots: {browser.snapshots}")
    print("Total roundtrips: 3 (slow, high latency)\n")


async def workflow_after_optimization():
    """
    AFTER: Single snapshot + quick DOM inspect
    Solution: Parse cached HTML locally
    """
    from quick_dom_inspect import (
        quick_extract_forms,
        quick_find_element,
        quick_extract_inputs
    )

    browser = MockBrowser()

    print("=== AFTER OPTIMIZATION ===\n")

    # Navigate to page
    await browser.navigate("https://example.com/login")

    # Single snapshot to get HTML
    snapshot = await browser.snapshot()
    cached_html = browser.get_cached_html()
    print("Snapshot 1: Get initial HTML")

    # ALL ANALYSIS DONE LOCALLY - NO BROWSER CALLS
    print("\n[Local] Analyzing form structure...")
    forms = quick_extract_forms(cached_html)

    print("[Local] Finding submit button...")
    submit = quick_find_element(cached_html, text="submit", tag="button")

    print("[Local] Checking for remember me...")
    inputs = quick_extract_inputs(cached_html)
    remember_me = next((i for i in inputs if 'remember' in i['name'].lower()), None)

    print(f"\nTotal snapshots: {browser.snapshots}")
    print("Total roundtrips: 1 (fast, low latency)")
    print("Analysis: 100% local (instant)\n")


async def real_world_login_example():
    """
    Real-world example: Smart login with minimal browser calls
    """
    from quick_dom_inspect import (
        quick_extract_forms,
        quick_find_element,
        quick_extract_buttons
    )

    print("=== REAL WORLD: Smart Login ===\n")

    browser = MockBrowser()

    # Simulate real login page
    browser.current_html = """
    <html>
        <body>
            <h1>Login to Your Account</h1>
            <form action="/api/auth" method="post" id="login-form">
                <div>
                    <label for="email">Email</label>
                    <input type="email" id="email" name="email" required>
                </div>
                <div>
                    <label for="password">Password</label>
                    <input type="password" id="password" name="password" required>
                </div>
                <div>
                    <input type="checkbox" id="remember" name="remember_me">
                    <label for="remember">Remember me</label>
                </div>
                <button type="submit" id="login-btn">Log In</button>
                <a href="/forgot-password">Forgot password?</a>
            </form>
            <div class="signup-link">
                <a href="/signup">Don't have an account? Sign up</a>
            </div>
        </body>
    </html>
    """

    # Step 1: Get page HTML (1 snapshot)
    await browser.navigate("https://example.com/login")
    snapshot = await browser.snapshot()
    html = browser.get_cached_html()
    print(f"[Browser] Snapshot taken ({browser.snapshots} total)")

    # Step 2: Analyze form structure locally (0 snapshots)
    print("\n[Analysis] Parsing form structure...")
    forms = quick_extract_forms(html)

    if not forms:
        print("[Error] No login form found")
        return

    login_form = forms[0]
    print(f"[Analysis] Found form: {login_form['action']}")
    print(f"[Analysis] Method: {login_form['method']}")
    print(f"[Analysis] Inputs: {len(login_form['inputs'])}")

    # Step 3: Identify fields to fill (0 snapshots)
    print("\n[Analysis] Identifying fields...")
    email_field = next((i for i in login_form['inputs'] if i['type'] == 'email'), None)
    password_field = next((i for i in login_form['inputs'] if i['type'] == 'password'), None)
    remember_field = next((i for i in login_form['inputs'] if 'remember' in i['name']), None)

    if email_field:
        print(f"[Analysis] Email field: #{email_field['id']}")
    if password_field:
        print(f"[Analysis] Password field: #{password_field['id']}")
    if remember_field:
        print(f"[Analysis] Remember me: #{remember_field['id']}")

    # Step 4: Find submit button (0 snapshots)
    print("\n[Analysis] Finding submit button...")
    submit_btn = quick_find_element(html, text="Log In", tag="button")
    if submit_btn:
        print(f"[Analysis] Submit button: #{submit_btn['id']}")

    # Step 5: Now do actual interactions
    print("\n[Action] Filling form...")
    print("[Browser] Type in email field")
    print("[Browser] Type in password field")
    print("[Browser] Click remember me checkbox")
    print("[Browser] Click submit button")

    print(f"\n[Summary]")
    print(f"  Total snapshots: {browser.snapshots}")
    print(f"  Browser calls: 1 (navigate) + 1 (snapshot) + 4 (interactions) = 6")
    print(f"  Without optimization: 1 + 5 (snapshots) + 4 (interactions) = 10")
    print(f"  Savings: 40% fewer roundtrips")


async def comparison_table():
    """Show side-by-side comparison"""
    print("\n=== PERFORMANCE COMPARISON ===\n")

    print("Traditional Approach:")
    print("  1. Navigate to page")
    print("  2. Snapshot to check for form")
    print("  3. Snapshot to find email field")
    print("  4. Snapshot to find password field")
    print("  5. Snapshot to find submit button")
    print("  6. Fill email")
    print("  7. Fill password")
    print("  8. Click submit")
    print("  Total: 8 operations, 4 snapshots, ~800ms latency")

    print("\nOptimized with quick_dom_inspect:")
    print("  1. Navigate to page")
    print("  2. Snapshot once")
    print("  3. [Local] Check for form")
    print("  4. [Local] Find email field")
    print("  5. [Local] Find password field")
    print("  6. [Local] Find submit button")
    print("  7. Fill email")
    print("  8. Fill password")
    print("  9. Click submit")
    print("  Total: 9 operations, 1 snapshot, ~200ms latency")

    print("\nBenefits:")
    print("  - 75% fewer snapshots (4 -> 1)")
    print("  - 75% less network latency (~600ms saved)")
    print("  - Instant local analysis (steps 3-6)")
    print("  - Same end result, much faster")


async def main():
    """Run all examples"""
    await workflow_before_optimization()
    print("\n" + "="*60 + "\n")

    await workflow_after_optimization()
    print("\n" + "="*60 + "\n")

    await real_world_login_example()
    print("\n" + "="*60 + "\n")

    await comparison_table()


if __name__ == '__main__':
    asyncio.run(main())
