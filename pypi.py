#!/usr/bin/env python3
"""
PyPI search scraper - ALWAYS sorted by most recent (o=-created)
Uses changelog_since_serial API for real search across recent packages.
Usage: python pypi.py --<query>
"""
import sys
import xmlrpc.client
from datetime import datetime, timezone

def fetch_pypi_packages(query, lookback=100000):
    """Fetch MOST RECENT packages from PyPI matching query.
    
    Uses PyPI's XML-RPC changelog_since_serial API to scan
    recent package activity and filter by name.
    
    Args:
        query: search term (case-insensitive substring match on package name)
        lookback: how many serial entries to go back (100k ≈ 2 days)
    """
    try:
        client = xmlrpc.client.ServerProxy('https://pypi.org/pypi')
        serial = client.changelog_last_serial()
        
        # Fetch recent changelog entries
        results = client.changelog_since_serial(serial - lookback)
        
        # Extract unique packages matching query, keep most recent entry per package
        seen = {}
        for name, version, timestamp, action, serial_num in results:
            if query and query.lower() not in name.lower():
                continue
            if name not in seen or timestamp > seen[name][2]:
                seen[name] = (name, version, timestamp, action)
        
        # Sort by timestamp desc (most recent first) - o=-created
        packages = sorted(seen.values(), key=lambda x: x[2], reverse=True)
        
        result = []
        for name, version, timestamp, action in packages:
            dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            result.append({
                'name': name,
                'version': version or 'N/A',
                'published': dt.strftime('%Y-%m-%d %H:%M:%S UTC'),
                'action': action,
                'link': f'https://pypi.org/project/{name}/'
            })
        
        return result
        
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
        print("         python pypi.py --''  (all recent)")
        sys.exit(1)
    
    print(f"Searching PyPI for: '{query}' (sorted by MOST RECENT)")
    print("=" * 60)
    
    packages = fetch_pypi_packages(query)
    
    if packages:
        print(f"\nFound {len(packages)} packages:\n")
        for i, pkg in enumerate(packages, 1):
            print(f"{i}. {pkg['name']} ({pkg['version']})")
            print(f"   Published: {pkg['published']}")
            print(f"   Action: {pkg['action']}")
            print(f"   Link: {pkg['link']}")
            print()
    else:
        print(f"No packages found matching '{query}'")

if __name__ == '__main__':
    main()

