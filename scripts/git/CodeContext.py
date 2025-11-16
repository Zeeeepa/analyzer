#!/usr/bin/env python3
"""
CodeContext - Repository Code Analysis
Clones repositories one by one and extracts detailed code context:
- Language detection
- File counts (total, code, docs)
- Code lines count
- Module/package detection
- Directory structure analysis
"""

import os
import sys
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Optional, List
from dataclasses import dataclass, asdict
import csv
import json


@dataclass
class CodeContext:
    """Detailed code context for a repository"""
    number: int
    repository_name: str
    full_name: str
    
    # Language and file statistics
    primary_language: str
    total_files: int
    total_directories: int
    total_size_bytes: int
    
    # Code file statistics
    code_files: int
    code_lines: int
    code_extensions: str  # Pipe-separated list of extensions found
    
    # Documentation statistics
    doc_files: int
    doc_types: str  # Pipe-separated list (md, rst, txt, etc)
    
    # Module/Package detection
    modules_count: int
    module_types: str  # Pipe-separated (python, npm, cargo, etc)
    
    # Configuration files
    config_files: int
    config_types: str  # Pipe-separated
    
    # Test files
    test_files: int
    test_frameworks: str  # Detected test frameworks
    
    # Build and CI/CD
    has_ci: bool
    ci_systems: str  # github-actions, gitlab-ci, etc
    build_systems: str  # make, cmake, gradle, etc
    
    # Repository structure
    max_depth: int
    largest_file: str
    largest_file_size: int


class CodeAnalyzer:
    """Analyzes code repositories for detailed context"""
    
    # Language extensions mapping
    CODE_EXTENSIONS = {
        'py': 'Python', 'js': 'JavaScript', 'ts': 'TypeScript',
        'jsx': 'JavaScript', 'tsx': 'TypeScript', 'java': 'Java',
        'cpp': 'C++', 'cc': 'C++', 'cxx': 'C++', 'c': 'C', 'h': 'C/C++',
        'go': 'Go', 'rs': 'Rust', 'rb': 'Ruby', 'php': 'PHP',
        'swift': 'Swift', 'kt': 'Kotlin', 'scala': 'Scala',
        'r': 'R', 'jl': 'Julia', 'm': 'MATLAB', 'mm': 'Objective-C',
        'vue': 'Vue', 'svelte': 'Svelte', 'sol': 'Solidity',
        'zig': 'Zig', 'cs': 'C#', 'fs': 'F#', 'ex': 'Elixir',
        'erl': 'Erlang', 'hs': 'Haskell', 'ml': 'OCaml', 'dart': 'Dart',
        'lua': 'Lua', 'pl': 'Perl', 'sh': 'Shell', 'bash': 'Bash',
        'zsh': 'Zsh', 'fish': 'Fish', 'ps1': 'PowerShell'
    }
    
    DOC_EXTENSIONS = {
        'md', 'rst', 'txt', 'adoc', 'org', 'tex',
        'pdf', 'doc', 'docx', 'html', 'xml'
    }
    
    CONFIG_EXTENSIONS = {
        'json', 'yaml', 'yml', 'toml', 'ini', 'cfg',
        'conf', 'config', 'env', 'properties'
    }
    
    MODULE_FILES = {
        'setup.py': 'python',
        'pyproject.toml': 'python',
        'requirements.txt': 'python',
        'Pipfile': 'python',
        'package.json': 'npm',
        'yarn.lock': 'yarn',
        'pnpm-lock.yaml': 'pnpm',
        'Cargo.toml': 'cargo',
        'go.mod': 'go',
        'pom.xml': 'maven',
        'build.gradle': 'gradle',
        'Gemfile': 'ruby',
        'composer.json': 'composer',
        'mix.exs': 'elixir',
        'Package.swift': 'swift',
        'pubspec.yaml': 'dart'
    }
    
    CI_FILES = {
        '.github/workflows': 'github-actions',
        '.gitlab-ci.yml': 'gitlab-ci',
        '.travis.yml': 'travis',
        '.circleci/config.yml': 'circleci',
        'azure-pipelines.yml': 'azure-pipelines',
        'Jenkinsfile': 'jenkins',
        '.drone.yml': 'drone'
    }
    
    BUILD_FILES = {
        'Makefile': 'make',
        'CMakeLists.txt': 'cmake',
        'build.gradle': 'gradle',
        'pom.xml': 'maven',
        'meson.build': 'meson',
        'BUILD': 'bazel',
        'WORKSPACE': 'bazel'
    }
    
    TEST_PATTERNS = {
        'test_': 'pytest',
        '_test.': 'go-test',
        '.test.': 'jest',
        '.spec.': 'jasmine/mocha',
        'Test.java': 'junit',
        'Tests.cs': 'nunit'
    }
    
    def __init__(self):
        pass
    
    def clone_repo(self, clone_url: str, temp_dir: Path) -> bool:
        """Clone repository with shallow depth"""
        try:
            subprocess.run(
                ['git', 'clone', '--depth', '1', clone_url, str(temp_dir)],
                check=True,
                capture_output=True,
                timeout=300
            )
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            print(f"  ✗ Clone failed: {e}")
            return False
    
    def analyze_repository(self, owner: str, repo_name: str, number: int) -> Optional[CodeContext]:
        """Analyze a single repository"""
        print(f"[{number}] Analyzing {owner}/{repo_name}...")
        
        clone_url = f"https://github.com/{owner}/{repo_name}.git"
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Clone repository
            print(f"  Cloning {clone_url}...")
            if not self.clone_repo(clone_url, temp_path):
                return None
            
            # Analyze code
            context = self._analyze_local_repo(temp_path, number, repo_name, f"{owner}/{repo_name}")
            
            return context
    
    def _analyze_local_repo(self, repo_path: Path, number: int, repo_name: str, full_name: str) -> CodeContext:
        """Analyze local repository and extract context"""
        
        # Initialize counters
        total_files = 0
        total_dirs = 0
        total_size = 0
        code_files = 0
        code_lines = 0
        code_exts = set()
        doc_files = 0
        doc_types = set()
        config_files = 0
        config_types = set()
        test_files = 0
        test_frameworks = set()
        modules = []
        ci_systems = []
        build_systems = []
        max_depth = 0
        largest_file = ""
        largest_size = 0
        
        # Walk through repository
        for root, dirs, files in os.walk(repo_path):
            # Skip .git directory
            if '.git' in root:
                continue
            
            # Calculate depth
            depth = len(Path(root).relative_to(repo_path).parts)
            max_depth = max(max_depth, depth)
            
            total_dirs += len(dirs)
            
            for file in files:
                file_path = Path(root) / file
                total_files += 1
                
                try:
                    file_size = file_path.stat().st_size
                    total_size += file_size
                    
                    # Track largest file
                    if file_size > largest_size:
                        largest_size = file_size
                        largest_file = str(file_path.relative_to(repo_path))
                    
                except (OSError, PermissionError):
                    continue
                
                file_lower = file.lower()
                ext = file_path.suffix.lstrip('.').lower()
                
                # Check for code files
                if ext in self.CODE_EXTENSIONS:
                    code_files += 1
                    code_exts.add(ext)
                    
                    # Count lines
                    try:
                        lines = self._count_lines(file_path)
                        code_lines += lines
                    except:
                        pass
                
                # Check for documentation
                if ext in self.DOC_EXTENSIONS:
                    doc_files += 1
                    doc_types.add(ext)
                
                # Check for config files
                if ext in self.CONFIG_EXTENSIONS:
                    config_files += 1
                    config_types.add(ext)
                
                # Check for test files
                for pattern, framework in self.TEST_PATTERNS.items():
                    if pattern in file_lower:
                        test_files += 1
                        test_frameworks.add(framework)
                        break
                
                # Check for module files
                if file in self.MODULE_FILES:
                    modules.append(self.MODULE_FILES[file])
                
                # Check for build files
                if file in self.BUILD_FILES:
                    build_systems.append(self.BUILD_FILES[file])
        
        # Check for CI systems
        for ci_path, ci_name in self.CI_FILES.items():
            if (repo_path / ci_path).exists():
                ci_systems.append(ci_name)
        
        # Detect primary language
        primary_lang = self._detect_primary_language(code_exts, repo_path)
        
        context = CodeContext(
            number=number,
            repository_name=repo_name,
            full_name=full_name,
            primary_language=primary_lang,
            total_files=total_files,
            total_directories=total_dirs,
            total_size_bytes=total_size,
            code_files=code_files,
            code_lines=code_lines,
            code_extensions='|'.join(sorted(code_exts)),
            doc_files=doc_files,
            doc_types='|'.join(sorted(doc_types)),
            modules_count=len(set(modules)),
            module_types='|'.join(sorted(set(modules))),
            config_files=config_files,
            config_types='|'.join(sorted(config_types)),
            test_files=test_files,
            test_frameworks='|'.join(sorted(test_frameworks)),
            has_ci=len(ci_systems) > 0,
            ci_systems='|'.join(ci_systems),
            build_systems='|'.join(build_systems),
            max_depth=max_depth,
            largest_file=largest_file,
            largest_file_size=largest_size
        )
        
        print(f"  ✓ Files: {total_files}, Code: {code_files} files / {code_lines:,} lines")
        print(f"  ✓ Language: {primary_lang}, Modules: {len(set(modules))}\n")
        
        return context
    
    def _count_lines(self, file_path: Path) -> int:
        """Count lines in a file"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return sum(1 for _ in f)
        except:
            return 0
    
    def _detect_primary_language(self, code_exts: set, repo_path: Path) -> str:
        """Detect primary language from extensions"""
        if not code_exts:
            return "Unknown"
        
        # Count files per language
        lang_counts = {}
        for ext in code_exts:
            lang = self.CODE_EXTENSIONS.get(ext, ext.upper())
            lang_counts[lang] = lang_counts.get(lang, 0) + 1
        
        # Return most common
        if lang_counts:
            return max(lang_counts, key=lang_counts.get)
        
        return "Unknown"
    
    def analyze_repositories(self, repos: List[tuple], output_file: str):
        """Analyze multiple repositories"""
        contexts = []
        
        print("=" * 60)
        print("Starting code context analysis")
        print(f"Total repositories: {len(repos)}")
        print(f"Output file: {output_file}")
        print("=" * 60)
        print("\n")
        
        for idx, (owner, repo_name) in enumerate(repos, 1):
            try:
                context = self.analyze_repository(owner, repo_name, idx)
                if context:
                    contexts.append(context)
            except Exception as e:
                print(f"  ✗ Error analyzing {owner}/{repo_name}: {e}\n")
                continue
        
        # Write results
        self._write_csv(contexts, output_file)
        
        print("\n" + "=" * 60)
        print(f"✓ Successfully analyzed {len(contexts)}/{len(repos)} repositories")
        print(f"✓ Output saved to: {output_file}")
        print("=" * 60)
    
    def _write_csv(self, contexts: List[CodeContext], output_file: str):
        """Write context data to CSV"""
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            if not contexts:
                return
            
            fieldnames = list(asdict(contexts[0]).keys())
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for context in contexts:
                writer.writerow(asdict(context))


def load_repo_list(index_file: str) -> List[tuple]:
    """Load repository list from index CSV"""
    repos = []
    
    with open(index_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            full_name = row['full_name']
            owner, repo_name = full_name.split('/')
            repos.append((owner, repo_name))
    
    return repos


def main():
    """Main execution"""
    # Configuration
    INDEX_FILE = "DATA/GIT/index.csv"
    OUTPUT_FILE = "DATA/GIT/code_context.csv"
    
    print("=" * 80)
    print("CodeContext - Repository Code Analysis")
    print(f"Index: {INDEX_FILE}")
    print(f"Output: {OUTPUT_FILE}")
    print("=" * 80)
    print()
    
    # Check if index exists
    if not Path(INDEX_FILE).exists():
        print(f"Error: Index file not found: {INDEX_FILE}")
        print("Please run sync.py first to generate the index.")
        sys.exit(1)
    
    # Load repositories from index
    print(f"Loading repositories from {INDEX_FILE}...")
    repos = load_repo_list(INDEX_FILE)
    print(f"Found {len(repos)} repositories to analyze.\n")
    
    # Create analyzer
    analyzer = CodeAnalyzer()
    
    # Analyze repositories
    analyzer.analyze_repositories(repos, OUTPUT_FILE)
    
    print("\n" + "=" * 80)
    print("✓ Code context analysis complete!")
    print(f"✓ Results saved to: {Path(OUTPUT_FILE).absolute()}")
    print("=" * 80)


if __name__ == '__main__':
    main()

