#!/usr/bin/env python3
"""
npm search scraper - ALWAYS sorted by most recent
Usage: python npm.py --<query>
"""
import sys
import requests
from datetime import datetime

def fetch_npm_packages(query):
    """Fetch MOST RECENT packages from npm, filtered by query"""
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    # npm registry search API
    # Use the search endpoint with text query
    url = "https://registry.npmjs.org/-/v1/search"
    
    params = {
        'text': query if query and query.strip() else '',
        'size': 30
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        packages = []
        
        for item in data.get('objects', []):
            pkg = item.get('package', {})
            
            # Get the date from package metadata
            date_str = pkg.get('date', '')
            
            packages.append({
                'name': pkg.get('name', 'Unknown'),
                'version': pkg.get('version', 'N/A'),
                'description': pkg.get('description', 'No description'),
                'author': pkg.get('author', {}).get('name', 'Unknown') if isinstance(pkg.get('author'), dict) else str(pkg.get('author', 'Unknown')),
                'date': date_str,
                'url': f"https://www.npmjs.com/package/{pkg.get('name', '')}"
            })
        
        # Sort by date (most recent first)
        packages.sort(key=lambda x: x['date'], reverse=True)
        
        return packages
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return []

def main():
    query = None
    
    for arg in sys.argv[1:]:
        if arg.startswith('--'):
            query = arg[2:]
            break
    
    if query is None:
        print("Usage: python npm.py --<query>")
        print("Example: python npm.py --react")
        print("         python npm.py --typescript")
        print("         python npm.py --api")
        sys.exit(1)
    
    print(f"Searching npm for: '{query}' (sorted by MOST RECENT)")
    print("=" * 60)
    
    packages = fetch_npm_packages(query)
    
    if packages:
        print(f"\nFound {len(packages)} most recent packages:\n")
        for i, pkg in enumerate(packages, 1):
            print(f"{i}. {pkg['name']} ({pkg['version']})")
            print(f"   {pkg['description'][:100]}...")
            print(f"   Author: {pkg['author']}")
            print(f"   Published: {pkg['date']}")
            print(f"   URL: {pkg['url']}")
            print()
    else:
        print(f"No packages found matching '{query}'")

if __name__ == '__main__':
    main()

