#!/usr/bin/env python3
"""
PyPI search scraper - ALWAYS sorted by most recent (o=-created)
Usage: python pypi.py --<query>
"""
import sys
import requests
import xml.etree.ElementTree as ET

def fetch_pypi_packages(query):
    """Fetch MOST RECENT packages from PyPI, filtered by query"""
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    # ALWAYS use RSS feed which is sorted by most recent
    rss_url = "https://pypi.org/rss/packages.xml"
    
    try:
        response = requests.get(rss_url, headers=headers, timeout=10)
        response.raise_for_status()
        
        root = ET.fromstring(response.content)
        packages = []
        
        for item in root.findall('.//item'):
            title = item.find('title')
            pubDate = item.find('pubDate')
            link = item.find('link')
            
            if title is not None:
                title_text = title.text.strip().replace(' added to PyPI', '')
                parts = title_text.rsplit(' ', 1)
                
                pkg_name = parts[0] if len(parts) > 0 else title_text
                
                # Filter by query (case-insensitive)
                if not query or query.lower() in pkg_name.lower():
                    packages.append({
                        'name': pkg_name,
                        'version': parts[1] if len(parts) > 1 else 'N/A',
                        'published': pubDate.text.strip() if pubDate is not None else 'N/A',
                        'link': link.text.strip() if link is not None else 'N/A'
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
        print("Example: python pypi.py --assistant")
        print("         python pypi.py --workflow")
        print("         python pypi.py --''  (all recent)")
        sys.exit(1)
    
    print(f"Searching PyPI for: '{query}' (sorted by MOST RECENT)")
    print("=" * 60)
    
    packages = fetch_pypi_packages(query)
    
    if packages:
        print(f"\nFound {len(packages)} most recent packages:\n")
        for i, pkg in enumerate(packages, 1):
            print(f"{i}. {pkg['name']} ({pkg['version']})")
            print(f"   Published: {pkg['published']}")
            print(f"   Link: {pkg['link']}")
            print()
    else:
        print(f"No packages found matching '{query}'")

if __name__ == '__main__':
    main()

