#!/usr/bin/env python3
"""
Dynamic Library Sync System for Analyzer

This script synchronizes external libraries (autogenlib, serena, graph-sitter)
into the Libraries folder, ensuring they stay up-to-date with source changes.

Usage:
    python sync_libraries.py                    # Sync all libraries
    python sync_libraries.py --library autogenlib  # Sync specific library
    python sync_libraries.py --check            # Check for changes without syncing
"""

import argparse
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
REPO_ROOT = Path(__file__).parent
LIBRARIES_DIR = REPO_ROOT / "Libraries"
TEMP_DIR = REPO_ROOT / ".lib_sync_temp"
SYNC_STATE_FILE = LIBRARIES_DIR / ".sync_state.json"

LIBRARY_CONFIGS = {
    "autogenlib": {
        "repo_url": "https://github.com/Zeeeepa/autogenlib.git",
        "source_path": "autogenlib",  # Path within the repo
        "target_path": LIBRARIES_DIR / "autogenlib",
        "include_patterns": ["*.py", "*.pyi", "*.typed"],
        "exclude_patterns": ["*test*", "*__pycache__*", "*.pyc"],
    },
    "serena": {
        "repo_url": "https://github.com/Zeeeepa/serena.git",
        "source_path": "src/serena",  # Main serena package
        "target_path": LIBRARIES_DIR / "serena",
        "include_patterns": ["*.py", "*.pyi", "*.typed"],
        "exclude_patterns": ["*test*", "*__pycache__*", "*.pyc"],
    },
    "graph_sitter": {
        "repo_url": "https://github.com/Zeeeepa/graph-sitter.git",
        "source_path": "src",  # graph_sitter package is in src/
        "target_path": LIBRARIES_DIR / "graph_sitter_lib",
        "include_patterns": ["*.py", "*.pyi", "*.typed"],
        "exclude_patterns": ["*test*", "*__pycache__*", "*.pyc"],
    },
}


class LibrarySync:
    """Manages synchronization of external libraries."""

    def __init__(self, library_name: str, config: Dict):
        self.library_name = library_name
        self.config = config
        self.repo_url = config["repo_url"]
        self.source_path = config["source_path"]
        self.target_path = Path(config["target_path"])
        self.include_patterns = config.get("include_patterns", ["*"])
        self.exclude_patterns = config.get("exclude_patterns", [])

    def clone_or_pull(self) -> Path:
        """Clone or update the library repository."""
        temp_repo_path = TEMP_DIR / self.library_name
        
        if temp_repo_path.exists():
            logger.info(f"Updating {self.library_name} repository...")
            try:
                subprocess.run(
                    ["git", "pull", "--ff-only"],
                    cwd=temp_repo_path,
                    check=True,
                    capture_output=True,
                    text=True
                )
            except subprocess.CalledProcessError as e:
                logger.warning(f"Git pull failed, re-cloning: {e}")
                shutil.rmtree(temp_repo_path)
                return self.clone_or_pull()
        else:
            logger.info(f"Cloning {self.library_name} repository...")
            TEMP_DIR.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "clone", "--depth", "1", self.repo_url, str(temp_repo_path)],
                check=True,
                capture_output=True,
                text=True
            )
        
        return temp_repo_path

    def calculate_directory_hash(self, directory: Path) -> str:
        """Calculate hash of directory contents for change detection."""
        hash_md5 = hashlib.md5()
        
        if not directory.exists():
            return ""
        
        for file_path in sorted(directory.rglob("*.py")):
            if file_path.is_file() and not any(excl in str(file_path) for excl in self.exclude_patterns):
                try:
                    with open(file_path, 'rb') as f:
                        for chunk in iter(lambda: f.read(4096), b""):
                            hash_md5.update(chunk)
                except Exception as e:
                    logger.warning(f"Error hashing {file_path}: {e}")
        
        return hash_md5.hexdigest()

    def should_sync(self, source_dir: Path) -> bool:
        """Check if sync is needed based on content changes."""
        source_hash = self.calculate_directory_hash(source_dir)
        target_hash = self.calculate_directory_hash(self.target_path)
        
        logger.info(f"{self.library_name}: source_hash={source_hash[:8]}, target_hash={target_hash[:8]}")
        
        return source_hash != target_hash

    def copy_filtered(self, source: Path, target: Path):
        """Copy files from source to target with filtering."""
        if target.exists():
            shutil.rmtree(target)
        
        target.mkdir(parents=True, exist_ok=True)
        
        copied_count = 0
        for file_path in source.rglob("*"):
            if not file_path.is_file():
                continue
            
            # Check exclude patterns
            if any(excl in str(file_path) for excl in self.exclude_patterns):
                continue
            
            # Check include patterns
            if not any(file_path.match(pattern) for pattern in self.include_patterns):
                continue
            
            # Calculate relative path and target location
            rel_path = file_path.relative_to(source)
            target_file = target / rel_path
            
            # Create parent directories
            target_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Copy file
            shutil.copy2(file_path, target_file)
            copied_count += 1
        
        logger.info(f"Copied {copied_count} files to {target}")

    def sync(self, force: bool = False) -> bool:
        """Synchronize the library."""
        logger.info(f"Syncing {self.library_name}...")
        
        # Clone or update repository
        temp_repo_path = self.clone_or_pull()
        source_dir = temp_repo_path / self.source_path
        
        if not source_dir.exists():
            logger.error(f"Source path {source_dir} does not exist!")
            return False
        
        # Check if sync is needed
        if not force and not self.should_sync(source_dir):
            logger.info(f"{self.library_name} is up-to-date, skipping sync")
            return True
        
        # Copy files
        logger.info(f"Syncing {self.library_name} from {source_dir} to {self.target_path}")
        self.copy_filtered(source_dir, self.target_path)
        
        # Create __init__.py if it doesn't exist
        init_file = self.target_path / "__init__.py"
        if not init_file.exists():
            init_file.write_text(f'"""Synced from {self.repo_url}"""\n')
        
        logger.info(f"✅ Successfully synced {self.library_name}")
        return True

    def check_status(self) -> Dict:
        """Check sync status without syncing."""
        temp_repo_path = TEMP_DIR / self.library_name
        
        if not temp_repo_path.exists():
            temp_repo_path = self.clone_or_pull()
        
        source_dir = temp_repo_path / self.source_path
        
        return {
            "library": self.library_name,
            "target_exists": self.target_path.exists(),
            "source_hash": self.calculate_directory_hash(source_dir),
            "target_hash": self.calculate_directory_hash(self.target_path),
            "needs_sync": self.should_sync(source_dir),
        }


class SyncManager:
    """Manages synchronization of all libraries."""

    def __init__(self):
        self.libraries = {
            name: LibrarySync(name, config)
            for name, config in LIBRARY_CONFIGS.items()
        }

    def sync_all(self, force: bool = False) -> bool:
        """Sync all libraries."""
        logger.info("=" * 60)
        logger.info("SYNCING ALL LIBRARIES")
        logger.info("=" * 60)
        
        results = {}
        for name, lib_sync in self.libraries.items():
            try:
                results[name] = lib_sync.sync(force=force)
            except Exception as e:
                logger.error(f"Error syncing {name}: {e}", exc_info=True)
                results[name] = False
        
        # Save sync state
        self.save_sync_state(results)
        
        # Summary
        logger.info("\n" + "=" * 60)
        logger.info("SYNC SUMMARY")
        logger.info("=" * 60)
        for name, success in results.items():
            status = "✅ SUCCESS" if success else "❌ FAILED"
            logger.info(f"{name:20} {status}")
        
        return all(results.values())

    def sync_one(self, library_name: str, force: bool = False) -> bool:
        """Sync a specific library."""
        if library_name not in self.libraries:
            logger.error(f"Unknown library: {library_name}")
            logger.info(f"Available libraries: {', '.join(self.libraries.keys())}")
            return False
        
        lib_sync = self.libraries[library_name]
        try:
            return lib_sync.sync(force=force)
        except Exception as e:
            logger.error(f"Error syncing {library_name}: {e}", exc_info=True)
            return False

    def check_all(self) -> Dict:
        """Check status of all libraries."""
        statuses = {}
        for name, lib_sync in self.libraries.items():
            try:
                statuses[name] = lib_sync.check_status()
            except Exception as e:
                logger.error(f"Error checking {name}: {e}", exc_info=True)
                statuses[name] = {"error": str(e)}
        
        return statuses

    def save_sync_state(self, results: Dict):
        """Save sync state to file."""
        state = {
            "last_sync": datetime.now().isoformat(),
            "results": results,
        }
        
        LIBRARIES_DIR.mkdir(parents=True, exist_ok=True)
        with open(SYNC_STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
        
        logger.info(f"Sync state saved to {SYNC_STATE_FILE}")

    def load_sync_state(self) -> Optional[Dict]:
        """Load sync state from file."""
        if not SYNC_STATE_FILE.exists():
            return None
        
        with open(SYNC_STATE_FILE) as f:
            return json.load(f)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Sync external libraries into analyzer"
    )
    parser.add_argument(
        "--library",
        "-l",
        help="Sync specific library (autogenlib, serena, graph_sitter)"
    )
    parser.add_argument(
        "--check",
        "-c",
        action="store_true",
        help="Check status without syncing"
    )
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Force sync even if no changes detected"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output"
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    
    manager = SyncManager()
    
    try:
        if args.check:
            # Check status
            statuses = manager.check_all()
            print("\n" + "=" * 60)
            print("LIBRARY STATUS")
            print("=" * 60)
            for name, status in statuses.items():
                if "error" in status:
                    print(f"\n{name}: ❌ ERROR - {status['error']}")
                else:
                    needs_sync = "⚠️  NEEDS SYNC" if status['needs_sync'] else "✅ UP-TO-DATE"
                    print(f"\n{name}: {needs_sync}")
                    print(f"  Target exists: {status['target_exists']}")
                    print(f"  Source hash: {status['source_hash'][:8]}")
                    print(f"  Target hash: {status['target_hash'][:8]}")
            return 0
        
        elif args.library:
            # Sync specific library
            success = manager.sync_one(args.library, force=args.force)
            return 0 if success else 1
        
        else:
            # Sync all libraries
            success = manager.sync_all(force=args.force)
            return 0 if success else 1
    
    except KeyboardInterrupt:
        logger.info("\nSync interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

