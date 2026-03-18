#!/usr/bin/env python3
"""
PyPI search scraper - fetches from https://pypi.org/search/?q=<QUERY>&o=-created
Uses Playwright to bypass JS client challenge, then parses HTML with BeautifulSoup.
Usage: python pypi.py --<query>
"""
import sys
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

PYPI_SEARCH_URL = "https://pypi.org/search/?q={query}&o=-created"

def fetch_pypi_packages(query):
    """Fetch packages from https://pypi.org/search/?q=<QUERY>&o=-created"""
    url = PYPI_SEARCH_URL.format(query=query)
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=['--disable-blink-features=AutomationControlled', '--no-sandbox']
            )
            ctx = browser.new_context(
                user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
            )
            page = ctx.new_page()
            page.add_init_script('Object.defineProperty(navigator, "webdriver", {get: () => undefined})')
            page.goto(url, timeout=30000)
            page.wait_for_selector('a.package-snippet', timeout=15000)
            html = page.content()
            browser.close()

        soup = BeautifulSoup(html, 'html.parser')
        snippets = soup.select('a.package-snippet')
        
        packages = []
        for s in snippets:
            name = s.select_one('.package-snippet__name')
            ver = s.select_one('.package-snippet__version')
            desc = s.select_one('.package-snippet__description')
            created = s.select_one('.package-snippet__created time')
            href = s.get('href', '')
            
            packages.append({
                'name': name.text.strip() if name else '?',
                'version': ver.text.strip() if ver else '?',
                'description': desc.text.strip() if desc else '',
                'published': created.get('datetime', '?') if created else '?',
                'link': f'https://pypi.org{href}' if href else '?'
            })
        
        return packages
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return []

def main():
    query = None
    
    for arg in sys.argv[1:]:
        if arg.startswith('--'):
            query = arg[2:]
            break
    
    if query is None:
        print("Usage: python pypi.py --<query>")
        print("Example: python pypi.py --workflow")
        print("         python pypi.py --mcp")
        print("         python pypi.py --agent")
        sys.exit(1)
    
    url = PYPI_SEARCH_URL.format(query=query)
    print(f"Fetching: {url}")
    print("=" * 60)
    
    packages = fetch_pypi_packages(query)
    
    if packages:
        print(f"\nFound {len(packages)} packages:\n")
        for i, pkg in enumerate(packages, 1):
            print(f"{i}. {pkg['name']} ({pkg['version']})")
            print(f"   {pkg['description'][:100]}")
            print(f"   Published: {pkg['published']}")
            print(f"   Link: {pkg['link']}")
            print()
    else:
        print(f"No packages found matching '{query}'")

if __name__ == '__main__':
    main()

