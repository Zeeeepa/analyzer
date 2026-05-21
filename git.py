#!/usr/bin/env python3
"""
GitHub search scraper - ALWAYS sorted by most recent
Usage: python git.py --<query>
"""
import sys
import requests
from datetime import datetime, timedelta

def fetch_github_repos(query):
    """Fetch MOST RECENT repos from GitHub, filtered by query"""
    headers = {
        'User-Agent': 'Mozilla/5.0',
        'Accept': 'application/vnd.github.v3+json'
    }
    
    # GitHub API search endpoint - sorted by recently created
    # Use created:>YYYY-MM-DD to get recent repos
    today = datetime.now()
    week_ago = today - timedelta(days=7)
    date_filter = week_ago.strftime('%Y-%m-%d')
    
    # Build search query
    if query and query.strip():
        search_query = f"{query} created:>{date_filter}"
    else:
        search_query = f"created:>{date_filter}"
    
    url = "https://api.github.com/search/repositories"
    params = {
        'q': search_query,
        'sort': 'created',
        'order': 'desc',
        'per_page': 30
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        repos = []
        
        for item in data.get('items', []):
            repos.append({
                'name': item['full_name'],
                'description': item['description'] or 'No description',
                'stars': item['stargazers_count'],
                'language': item['language'] or 'Unknown',
                'created': item['created_at'],
                'url': item['html_url']
            })
        
        return repos
        
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
        print("Usage: python git.py --<query>")
        print("Example: python git.py --machine-learning")
        print("         python git.py --api")
        print("         python git.py --''  (all recent)")
        sys.exit(1)
    
    print(f"Searching GitHub for: '{query}' (sorted by MOST RECENT)")
    print("=" * 60)
    
    repos = fetch_github_repos(query)
    
    if repos:
        print(f"\nFound {len(repos)} most recent repositories:\n")
        for i, repo in enumerate(repos, 1):
            print(f"{i}. {repo['name']}")
            print(f"   {repo['description'][:100]}...")
            print(f"   Language: {repo['language']} | Stars: {repo['stars']}")
            print(f"   Created: {repo['created']}")
            print(f"   URL: {repo['url']}")
            print()
    else:
        print(f"No repositories found matching '{query}'")

if __name__ == '__main__':
    main()

