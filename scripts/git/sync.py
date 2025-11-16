#!/usr/bin/env python3
"""
GitSync - Static Repository Index Generator
Fetches repository metadata from GitHub API without cloning.
Creates a simple index with actual GitHub data.
"""

import os
import sys
import json
import requests
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
import csv


@dataclass
class RepoIndex:
    """Simple repository index from GitHub API"""
    number: int
    repository_name: str
    full_name: str
    description: str
    language: Optional[str]
    stars: int
    forks: int
    watchers: int
    open_issues: int
    created_at: str
    updated_at: str
    pushed_at: str
    size: int  # Size in KB from GitHub
    default_branch: str
    url: str
    clone_url: str
    homepage: Optional[str]
    topics: str  # Pipe-separated list
    license: Optional[str]
    is_fork: bool
    is_archived: bool
    is_template: bool


class GitSync:
    """Static repository index generator"""
    
    def __init__(self, github_token: Optional[str] = None):
        self.github_token = github_token or os.getenv('GITHUB_TOKEN')
        self.session = requests.Session()
        if self.github_token:
            self.session.headers.update({
                'Authorization': f'token {self.github_token}',
                'Accept': 'application/vnd.github.v3+json'
            })
    
    def fetch_all_repos(self, username: str) -> List[tuple]:
        """Fetch all repositories for a user/org"""
        repos = []
        page = 1
        per_page = 100
        
        print(f"Fetching all repositories from {username}...")
        
        while True:
            url = f'https://api.github.com/users/{username}/repos'
            params = {
                'page': page,
                'per_page': per_page,
                'sort': 'updated',
                'direction': 'desc'
            }
            
            try:
                response = self.session.get(url, params=params, timeout=30)
                response.raise_for_status()
                page_repos = response.json()
                
                if not page_repos:
                    break
                
                print(f"  Fetched page {page}: {len(page_repos)} repos")
                repos.extend([(username, repo['name']) for repo in page_repos])
                page += 1
                
            except requests.exceptions.RequestException as e:
                print(f"Error fetching repos: {e}")
                break
        
        print(f"  Total repositories found: {len(repos)}\n")
        return repos
    
    def get_repo_metadata(self, owner: str, repo: str) -> Optional[Dict]:
        """Fetch repository metadata from GitHub API"""
        url = f'https://api.github.com/repos/{owner}/{repo}'
        
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"API error for {owner}/{repo}: {e}")
            return None
    
    def create_index(self, repos: List[tuple], output_file: str) -> List[RepoIndex]:
        """Create static index from GitHub API data"""
        index_data = []
        
        print("=" * 60)
        print("Starting static index generation")
        print(f"Total repositories: {len(repos)}")
        print(f"Output file: {output_file}")
        print("=" * 60)
        print("\n")
        
        for idx, (owner, repo_name) in enumerate(repos, 1):
            print(f"[{idx}] Fetching metadata for {owner}/{repo_name}...")
            
            metadata = self.get_repo_metadata(owner, repo_name)
            if not metadata:
                continue
            
            # Extract metadata
            repo_index = RepoIndex(
                number=idx,
                repository_name=metadata['name'],
                full_name=metadata['full_name'],
                description=metadata.get('description', '') or '',
                language=metadata.get('language', ''),
                stars=metadata.get('stargazers_count', 0),
                forks=metadata.get('forks_count', 0),
                watchers=metadata.get('watchers_count', 0),
                open_issues=metadata.get('open_issues_count', 0),
                created_at=metadata.get('created_at', ''),
                updated_at=metadata.get('updated_at', ''),
                pushed_at=metadata.get('pushed_at', ''),
                size=metadata.get('size', 0),
                default_branch=metadata.get('default_branch', 'main'),
                url=metadata.get('html_url', ''),
                clone_url=metadata.get('clone_url', ''),
                homepage=metadata.get('homepage', '') or '',
                topics='|'.join(metadata.get('topics', [])),
                license=metadata.get('license', {}).get('spdx_id', '') if metadata.get('license') else '',
                is_fork=metadata.get('fork', False),
                is_archived=metadata.get('archived', False),
                is_template=metadata.get('is_template', False)
            )
            
            index_data.append(repo_index)
            print(f"  ✓ {metadata.get('language', 'N/A')} | {metadata.get('stargazers_count', 0)} ⭐ | {metadata.get('size', 0)} KB\n")
        
        # Write CSV
        self._write_csv(index_data, output_file)
        
        print("\n" + "=" * 60)
        print(f"✓ Successfully indexed {len(index_data)}/{len(repos)} repositories")
        print(f"✓ Output saved to: {output_file}")
        print("=" * 60)
        
        return index_data
    
    def _write_csv(self, index_data: List[RepoIndex], output_file: str):
        """Write index data to CSV"""
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            if not index_data:
                return
            
            # Get field names from dataclass
            fieldnames = list(asdict(index_data[0]).keys())
            
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for item in index_data:
                writer.writerow(asdict(item))


def main():
    """Main execution"""
    # Configuration
    ORGANIZATION = "Zeeeepa"
    OUTPUT_FILE = "DATA/GIT/index.csv"
    
    print("=" * 80)
    print("GitSync - Static Repository Index")
    print(f"Organization: {ORGANIZATION}")
    print(f"Output: {OUTPUT_FILE}")
    print("=" * 80)
    print()
    
    # Check for GitHub token
    github_token = os.getenv('GITHUB_TOKEN')
    if not github_token:
        print("Warning: No GITHUB_TOKEN environment variable set.")
        print("API rate limits will be restrictive (60 requests/hour).")
        print("Set GITHUB_TOKEN for 5000 requests/hour.\n")
    
    # Create syncer
    syncer = GitSync(github_token)
    
    # Fetch all repos
    repos = syncer.fetch_all_repos(ORGANIZATION)
    
    if not repos:
        print("No repositories found!")
        sys.exit(1)
    
    # Create index
    syncer.create_index(repos, OUTPUT_FILE)
    
    print("\n" + "=" * 80)
    print("✓ Index generation complete!")
    print(f"✓ Total repositories indexed: {len(repos)}")
    print(f"✓ Results saved to: {Path(OUTPUT_FILE).absolute()}")
    print("=" * 80)


if __name__ == '__main__':
    main()

