#!/usr/bin/env python3
"""
Git Repository Synchronization and Analysis Tool

This script analyzes GitHub repositories and generates comprehensive metadata
including file counts, code statistics, and categorization.
"""

import os
import sys
import csv
import json
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
import requests
from datetime import datetime

@dataclass
class RepoMetadata:
    """Repository metadata structure"""
    number: int
    repository_name: str
    full_name: str
    description: str
    language: str
    origin_repo_stars: int
    updated_at: str
    url: str
    file_number: int
    unpacked_size: int
    total_code_files: int
    total_code_lines: int
    module_number: int
    total_doc_files: int
    category: str
    tags: str

class GitSync:
    """Main Git synchronization and analysis class"""
    
    # File extensions for code files
    CODE_EXTENSIONS = {
        '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.cpp', '.c', '.h', 
        '.hpp', '.cs', '.go', '.rs', '.rb', '.php', '.swift', '.kt', '.scala',
        '.r', '.jl', '.m', '.mm', '.vue', '.svelte', '.sol', '.zig'
    }
    
    # File extensions for documentation
    DOC_EXTENSIONS = {
        '.md', '.rst', '.txt', '.adoc', '.org', '.tex', '.pdf', '.doc', 
        '.docx', '.html', '.xml'
    }
    
    # Module identifiers
    MODULE_FILES = {
        'python': ['__init__.py', 'setup.py', 'pyproject.toml', 'requirements.txt'],
        'node': ['package.json', 'package-lock.json', 'yarn.lock'],
        'rust': ['Cargo.toml', 'Cargo.lock'],
        'go': ['go.mod', 'go.sum'],
        'java': ['pom.xml', 'build.gradle', 'build.gradle.kts'],
        'ruby': ['Gemfile', 'Gemfile.lock', '.gemspec'],
        'php': ['composer.json', 'composer.lock']
    }
    
    def __init__(self, github_token: Optional[str] = None):
        """Initialize GitSync with optional GitHub token"""
        self.github_token = github_token or os.environ.get('GITHUB_TOKEN')
        self.headers = {}
        if self.github_token:
            self.headers['Authorization'] = f'token {self.github_token}'
        
        # Load categories
        self.categories = self._load_categories()
        
    def _load_categories(self) -> Dict:
        """Load category mappings from JSON file"""
        categories_file = Path(__file__).parent / 'categories.json'
        try:
            with open(categories_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"Warning: categories.json not found at {categories_file}")
            return {"categories": {}}
    
    def _get_repo_category(self, repo_name: str) -> Tuple[str, List[str]]:
        """
        Determine repository category and tags
        
        Returns:
            Tuple of (category_name, list_of_tags)
        """
        repo_name_lower = repo_name.lower()
        
        for category_name, category_data in self.categories.get('categories', {}).items():
            repos_in_category = [r.lower() for r in category_data.get('repos', [])]
            if repo_name_lower in repos_in_category:
                # Generate tags from category name
                tags = [category_name.lower().replace(' ', '-')]
                
                # Add additional tags based on keywords
                desc = category_data.get('description', '').lower()
                if 'agent' in desc or 'agent' in repo_name_lower:
                    tags.append('agent')
                if 'mcp' in desc or 'mcp' in repo_name_lower:
                    tags.append('mcp')
                if 'claude' in desc or 'claude' in repo_name_lower:
                    tags.append('claude')
                if 'security' in desc or 'penetration' in desc:
                    tags.append('security')
                if 'api' in desc or 'api' in repo_name_lower:
                    tags.append('api')
                    
                return (category_name, list(set(tags)))
        
        return ('Other', ['uncategorized'])
    
    def _count_lines_in_file(self, file_path: Path) -> int:
        """Count lines in a file"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return sum(1 for _ in f)
        except Exception:
            return 0
    
    def _analyze_local_repo(self, repo_path: Path) -> Dict:
        """
        Analyze a local repository directory
        
        Returns:
            Dictionary with analysis results
        """
        stats = {
            'file_number': 0,
            'unpacked_size': 0,
            'total_code_files': 0,
            'total_code_lines': 0,
            'module_number': 0,
            'total_doc_files': 0
        }
        
        # Walk through repository
        for root, dirs, files in os.walk(repo_path):
            # Skip .git directory
            if '.git' in root:
                continue
                
            for file in files:
                file_path = Path(root) / file
                file_ext = file_path.suffix.lower()
                
                try:
                    file_size = file_path.stat().st_size
                    stats['unpacked_size'] += file_size
                    stats['file_number'] += 1
                    
                    # Count code files and lines
                    if file_ext in self.CODE_EXTENSIONS:
                        stats['total_code_files'] += 1
                        stats['total_code_lines'] += self._count_lines_in_file(file_path)
                    
                    # Count documentation files
                    if file_ext in self.DOC_EXTENSIONS:
                        stats['total_doc_files'] += 1
                    
                    # Count modules
                    for module_files in self.MODULE_FILES.values():
                        if file in module_files:
                            stats['module_number'] += 1
                            break
                            
                except Exception as e:
                    print(f"Error processing {file_path}: {e}")
                    continue
        
        return stats
    
    def _shallow_clone_repo(self, repo_url: str, temp_dir: Path) -> Optional[Path]:
        """
        Perform shallow clone of repository
        
        Returns:
            Path to cloned repository or None if failed
        """
        try:
            print(f"Cloning {repo_url}...")
            result = subprocess.run(
                ['git', 'clone', '--depth', '1', repo_url, str(temp_dir)],
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode == 0:
                return temp_dir
            else:
                print(f"Clone failed: {result.stderr}")
                return None
                
        except subprocess.TimeoutExpired:
            print(f"Clone timeout for {repo_url}")
            return None
        except Exception as e:
            print(f"Clone error for {repo_url}: {e}")
            return None
    
    def _get_github_repo_info(self, owner: str, repo: str) -> Optional[Dict]:
        """
        Fetch repository information from GitHub API
        
        Returns:
            Dictionary with repo info or None if failed
        """
        url = f"https://api.github.com/repos/{owner}/{repo}"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"API error for {owner}/{repo}: {e}")
            return None
    
    def analyze_repository(self, owner: str, repo: str, number: int) -> Optional[RepoMetadata]:
        """
        Analyze a GitHub repository completely
        
        Args:
            owner: Repository owner
            repo: Repository name
            number: Sequential number for this repository
            
        Returns:
            RepoMetadata object or None if analysis failed
        """
        print(f"\n[{number}] Analyzing {owner}/{repo}...")
        
        # Get GitHub API info
        repo_info = self._get_github_repo_info(owner, repo)
        if not repo_info:
            return None
        
        # Create temporary directory for cloning
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / repo
            
            # Clone repository
            clone_url = repo_info['clone_url']
            cloned_path = self._shallow_clone_repo(clone_url, temp_path)
            
            if cloned_path:
                # Analyze local repository
                analysis = self._analyze_local_repo(cloned_path)
            else:
                # Use default values if clone failed
                print(f"Warning: Using default analysis for {repo}")
                analysis = {
                    'file_number': 0,
                    'unpacked_size': 0,
                    'total_code_files': 0,
                    'total_code_lines': 0,
                    'module_number': 0,
                    'total_doc_files': 0
                }
        
        # Get category and tags
        category, tags = self._get_repo_category(repo)
        
        # Build metadata
        metadata = RepoMetadata(
            number=number,
            repository_name=repo,
            full_name=f"{owner}/{repo}",
            description=repo_info.get('description', '').replace(',', ';') if repo_info.get('description') else 'No description',
            language=repo_info.get('language', 'Not specified'),
            origin_repo_stars=repo_info.get('stargazers_count', 0),
            updated_at=repo_info.get('updated_at', ''),
            url=repo_info.get('html_url', ''),
            file_number=analysis['file_number'],
            unpacked_size=analysis['unpacked_size'],
            total_code_files=analysis['total_code_files'],
            total_code_lines=analysis['total_code_lines'],
            module_number=analysis['module_number'],
            total_doc_files=analysis['total_doc_files'],
            category=category,
            tags='|'.join(tags)
        )
        
        print(f"  ✓ Files: {metadata.file_number}, Code: {metadata.total_code_files} files / {metadata.total_code_lines} lines")
        print(f"  ✓ Category: {category}, Tags: {', '.join(tags)}")
        
        return metadata
    
    def sync_repositories(self, repos: List[Tuple[str, str]], output_file: Path):
        """
        Sync and analyze multiple repositories
        
        Args:
            repos: List of (owner, repo) tuples
            output_file: Path to output CSV file
        """
        print(f"\n{'='*60}")
        print(f"Starting repository synchronization")
        print(f"Total repositories: {len(repos)}")
        print(f"Output file: {output_file}")
        print(f"{'='*60}\n")
        
        # Ensure output directory exists
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Collect all metadata
        all_metadata = []
        
        for idx, (owner, repo) in enumerate(repos, start=1):
            try:
                metadata = self.analyze_repository(owner, repo, idx)
                if metadata:
                    all_metadata.append(metadata)
            except Exception as e:
                print(f"Error analyzing {owner}/{repo}: {e}")
                continue
        
        # Write to CSV
        if all_metadata:
            self._write_csv(all_metadata, output_file)
            print(f"\n{'='*60}")
            print(f"✓ Successfully analyzed {len(all_metadata)}/{len(repos)} repositories")
            print(f"✓ Output saved to: {output_file}")
            print(f"{'='*60}\n")
        else:
            print("\nNo repositories were successfully analyzed!")
    
    def _write_csv(self, metadata_list: List[RepoMetadata], output_file: Path):
        """Write metadata to CSV file"""
        fieldnames = [
            'number', 'repository_name', 'full_name', 'description', 
            'language', 'origin_repo_stars', 'updated_at', 'url',
            'file_number', 'unpacked_size', 'total_code_files', 
            'total_code_lines', 'module_number', 'total_doc_files',
            'category', 'tags'
        ]
        
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for metadata in metadata_list:
                writer.writerow(asdict(metadata))


def load_repos_from_github_api(org: str, token: Optional[str] = None) -> List[Tuple[str, str]]:
    """
    Load all repositories from a GitHub organization
    
    Args:
        org: Organization name
        token: Optional GitHub token
        
    Returns:
        List of (owner, repo) tuples
    """
    headers = {}
    if token:
        headers['Authorization'] = f'token {token}'
    
    repos = []
    page = 1
    
    print(f"Fetching repositories from {org}...")
    
    while True:
        url = f"https://api.github.com/orgs/{org}/repos"
        params = {'page': page, 'per_page': 100}
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            
            page_repos = response.json()
            if not page_repos:
                break
            
            for repo in page_repos:
                repos.append((org, repo['name']))
            
            print(f"  Fetched page {page}: {len(page_repos)} repos")
            page += 1
            
        except requests.RequestException as e:
            print(f"Error fetching repos: {e}")
            break
    
    print(f"Total repositories found: {len(repos)}\n")
    return repos


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Synchronize and analyze GitHub repositories',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze Zeeeepa organization
  python gitsync.py --org Zeeeepa
  
  # Analyze specific repositories
  python gitsync.py --repos Zeeeepa/codegen Zeeeepa/analyzer
  
  # Use custom output file
  python gitsync.py --org Zeeeepa --output custom.csv
  
  # Use GitHub token for higher API limits
  export GITHUB_TOKEN=your_token_here
  python gitsync.py --org Zeeeepa
        """
    )
    
    parser.add_argument(
        '--org',
        help='GitHub organization to analyze'
    )
    parser.add_argument(
        '--repos',
        nargs='+',
        help='Specific repositories to analyze (format: owner/repo)'
    )
    parser.add_argument(
        '--output',
        default='DATA/GIT/git.csv',
        help='Output CSV file path (default: DATA/GIT/git.csv)'
    )
    parser.add_argument(
        '--token',
        help='GitHub token (or use GITHUB_TOKEN env var)'
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if not args.org and not args.repos:
        parser.error('Either --org or --repos must be specified')
    
    # Initialize GitSync
    token = args.token or os.environ.get('GITHUB_TOKEN')
    if not token:
        print("Warning: No GitHub token provided. API rate limits will be restrictive.")
        print("Set GITHUB_TOKEN environment variable or use --token option.\n")
    
    syncer = GitSync(github_token=token)
    
    # Build repository list
    if args.org:
        repos = load_repos_from_github_api(args.org, token)
    else:
        repos = []
        for repo_spec in args.repos:
            parts = repo_spec.split('/')
            if len(parts) != 2:
                print(f"Invalid repo format: {repo_spec} (should be owner/repo)")
                continue
            repos.append((parts[0], parts[1]))
    
    if not repos:
        print("No repositories to analyze!")
        return 1
    
    # Perform synchronization
    output_path = Path(args.output)
    syncer.sync_repositories(repos, output_path)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())

