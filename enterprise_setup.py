#!/usr/bin/env python3
"""
Enterprise WrtnLabs Deployment System
====================================

Production-grade setup orchestrator with advanced features:
- Full CLI with subcommands (install, validate, backup, restore, test)
- Type hints throughout
- Comprehensive error handling
- Modular class-based design
- Beautiful colored output with progress tracking
- Detailed logging system
- Backup/restore capabilities
- Non-interactive test mode
- 5-second smart timeouts
"""

import os
import sys
import subprocess
import json
import shutil
import argparse
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
import tempfile

# ANSI Color codes
class Colors:
    """ANSI color codes for terminal output"""
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    MAGENTA = '\033[0;35m'
    CYAN = '\033[0;36m'
    WHITE = '\033[1;37m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    UNDERLINE = '\033[4m'
    NC = '\033[0m'  # No Color


@dataclass
class ValidationResult:
    """Result of a validation check"""
    success: bool
    message: str
    details: Optional[str] = None


class SystemChecker:
    """Pre-flight validation for system requirements"""
    
    def __init__(self, timeout: int = 5):
        self.timeout = timeout
        self.results: List[ValidationResult] = []
        self.logger = logging.getLogger(__name__)
    
    def run_command(
        self,
        cmd: List[str],
        check_output: bool = True
    ) -> Tuple[int, str, str]:
        """Run command with timeout"""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", f"Command timed out after {self.timeout}s"
        except FileNotFoundError:
            return -1, "", f"Command not found: {cmd[0]}"
        except Exception as e:
            return -1, "", str(e)
    
    def check_node(self) -> ValidationResult:
        """Check Node.js v18+"""
        self.logger.info("Checking Node.js version...")
        code, stdout, stderr = self.run_command(['node', '--version'])
        
        if code != 0:
            return ValidationResult(
                False,
                "Node.js not found",
                "Install Node.js v18+ from https://nodejs.org"
            )
        
        try:
            version = stdout.strip().replace('v', '')
            major = int(version.split('.')[0])
            
            if major >= 18:
                return ValidationResult(
                    True,
                    f"Node.js {version}",
                    "Version requirement satisfied"
                )
            else:
                return ValidationResult(
                    False,
                    f"Node.js {version} too old",
                    "Requires v18+"
                )
        except (ValueError, IndexError):
            return ValidationResult(
                False,
                "Could not parse Node.js version",
                stdout
            )
    
    def check_package_manager(self) -> ValidationResult:
        """Check for pnpm or npm"""
        self.logger.info("Checking package managers...")
        
        for pm in ['pnpm', 'npm']:
            code, stdout, stderr = self.run_command([pm, '--version'])
            if code == 0:
                version = stdout.strip()
                return ValidationResult(
                    True,
                    f"{pm} {version}",
                    f"Package manager available"
                )
        
        return ValidationResult(
            False,
            "No package manager found",
            "Install pnpm: npm install -g pnpm"
        )
    
    def check_git(self) -> ValidationResult:
        """Check Git installation"""
        self.logger.info("Checking Git...")
        code, stdout, stderr = self.run_command(['git', '--version'])
        
        if code == 0:
            return ValidationResult(True, stdout.strip(), "Git available")
        
        return ValidationResult(
            False,
            "Git not found",
            "Install Git from https://git-scm.com"
        )
    
    def check_docker(self) -> ValidationResult:
        """Check Docker daemon"""
        self.logger.info("Checking Docker...")
        code, stdout, stderr = self.run_command(['docker', '--version'])
        
        if code != 0:
            return ValidationResult(
                False,
                "Docker not found (optional)",
                "Docker is optional for PostgreSQL"
            )
        
        # Check daemon
        code, _, _ = self.run_command(['docker', 'ps'])
        if code == 0:
            return ValidationResult(True, stdout.strip(), "Docker daemon running")
        
        return ValidationResult(
            False,
            "Docker daemon not running",
            "Start Docker daemon"
        )
    
    def check_disk_space(self, required_gb: float = 2.0) -> ValidationResult:
        """Check available disk space"""
        self.logger.info("Checking disk space...")
        try:
            stat = shutil.disk_usage('/')
            available_gb = stat.free / (1024 ** 3)
            
            if available_gb >= required_gb:
                return ValidationResult(
                    True,
                    f"{available_gb:.1f} GB available",
                    f"Exceeds {required_gb} GB requirement"
                )
            
            return ValidationResult(
                False,
                f"Only {available_gb:.1f} GB available",
                f"Requires {required_gb} GB"
            )
        except Exception as e:
            return ValidationResult(False, "Disk check failed", str(e))
    
    def check_python(self) -> ValidationResult:
        """Check Python version"""
        self.logger.info("Checking Python...")
        version = sys.version.split()[0]
        major, minor = map(int, version.split('.')[:2])
        
        if major >= 3 and minor >= 8:
            return ValidationResult(
                True,
                f"Python {version}",
                "Version 3.8+ satisfied"
            )
        
        return ValidationResult(
            False,
            f"Python {version} too old",
            "Requires Python 3.8+"
        )
    
    def run_all_checks(self) -> bool:
        """Run all validation checks"""
        checks = [
            ("Node.js", self.check_node),
            ("Package Manager", self.check_package_manager),
            ("Git", self.check_git),
            ("Python", self.check_python),
            ("Disk Space", self.check_disk_space),
            ("Docker", self.check_docker),
        ]
        
        all_passed = True
        
        for name, check_func in checks:
            result = check_func()
            self.results.append(result)
            
            if result.success:
                print(f"{Colors.GREEN}✓{Colors.NC} {name}: {result.message}")
                if result.details:
                    print(f"  {Colors.DIM}{result.details}{Colors.NC}")
            else:
                print(f"{Colors.RED}✗{Colors.NC} {name}: {result.message}")
                if result.details:
                    print(f"  {Colors.YELLOW}→{Colors.NC} {result.details}")
                
                # Docker is optional
                if name != "Docker":
                    all_passed = False
        
        return all_passed


class DependencyInstaller:
    """Auto-detection and installation of dependencies"""
    
    def __init__(self, script_dir: Path, package_manager: str, timeout: int = 300):
        self.script_dir = script_dir
        self.pm = package_manager
        self.timeout = timeout
        self.logger = logging.getLogger(__name__)
        self.repos = ['autobe', 'autoview', 'agentica', 'vector-store', 'backend', 'connectors']
    
    def detect_package_manager(self) -> Optional[str]:
        """Auto-detect available package manager"""
        self.logger.info("Auto-detecting package manager...")
        
        for pm in ['pnpm', 'npm']:
            try:
                result = subprocess.run(
                    [pm, '--version'],
                    capture_output=True,
                    timeout=5
                )
                if result.returncode == 0:
                    self.logger.info(f"Detected {pm}")
                    return pm
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue
        
        return None
    
    def install_repo(self, repo: str, verbose: bool = False) -> bool:
        """Install dependencies for a repository"""
        repo_path = self.script_dir / repo
        
        if not repo_path.exists():
            self.logger.warning(f"Repository {repo} not found, skipping")
            return True
        
        package_json = repo_path / 'package.json'
        if not package_json.exists():
            self.logger.warning(f"No package.json in {repo}, skipping")
            return True
        
        print(f"\n{Colors.BLUE}📦 Installing{Colors.NC} {repo}...")
        self.logger.info(f"Installing dependencies for {repo}")
        
        try:
            result = subprocess.run(
                [self.pm, 'install'],
                cwd=repo_path,
                capture_output=not verbose,
                text=True,
                timeout=self.timeout
            )
            
            if result.returncode == 0:
                print(f"{Colors.GREEN}✓{Colors.NC} {repo} complete")
                return True
            else:
                print(f"{Colors.RED}✗{Colors.NC} {repo} failed")
                if verbose and result.stderr:
                    print(f"  {Colors.RED}{result.stderr[:500]}{Colors.NC}")
                return False
                
        except subprocess.TimeoutExpired:
            print(f"{Colors.RED}✗{Colors.NC} {repo} timeout")
            self.logger.error(f"Timeout installing {repo}")
            return False
        except Exception as e:
            print(f"{Colors.RED}✗{Colors.NC} {repo} error: {e}")
            self.logger.error(f"Error installing {repo}: {e}")
            return False
    
    def install_all(self, verbose: bool = False) -> Tuple[int, int]:
        """Install all repositories"""
        print(f"\n{Colors.CYAN}{Colors.BOLD}Dependency Installation{Colors.NC}")
        print(f"{Colors.CYAN}{'=' * 60}{Colors.NC}\n")
        
        success_count = 0
        fail_count = 0
        
        for repo in self.repos:
            if self.install_repo(repo, verbose):
                success_count += 1
            else:
                fail_count += 1
        
        print(f"\n{Colors.BOLD}Results:{Colors.NC} {Colors.GREEN}{success_count} success{Colors.NC}, {Colors.RED}{fail_count} failed{Colors.NC}")
        
        return success_count, fail_count


class BackupManager:
    """Backup and restore configuration"""
    
    def __init__(self, script_dir: Path):
        self.script_dir = script_dir
        self.backup_dir = script_dir / '.backups'
        self.logger = logging.getLogger(__name__)
    
    def create_backup(self, name: Optional[str] = None) -> Optional[Path]:
        """Create backup of .env file"""
        env_file = self.script_dir / '.env'
        
        if not env_file.exists():
            self.logger.warning("No .env file to backup")
            print(f"{Colors.YELLOW}⚠{Colors.NC} No .env file found")
            return None
        
        # Create backup directory
        self.backup_dir.mkdir(exist_ok=True)
        
        # Generate backup name
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = name or f"env_backup_{timestamp}"
        backup_path = self.backup_dir / backup_name
        
        try:
            shutil.copy2(env_file, backup_path)
            self.logger.info(f"Created backup: {backup_path}")
            print(f"{Colors.GREEN}✓{Colors.NC} Backup created: {backup_name}")
            return backup_path
        except Exception as e:
            self.logger.error(f"Backup failed: {e}")
            print(f"{Colors.RED}✗{Colors.NC} Backup failed: {e}")
            return None
    
    def list_backups(self) -> List[Path]:
        """List available backups"""
        if not self.backup_dir.exists():
            return []
        
        backups = sorted(self.backup_dir.glob('*'), key=lambda p: p.stat().st_mtime, reverse=True)
        return backups
    
    def restore_backup(self, backup_name: str) -> bool:
        """Restore from backup"""
        backup_path = self.backup_dir / backup_name
        
        if not backup_path.exists():
            self.logger.error(f"Backup not found: {backup_name}")
            print(f"{Colors.RED}✗{Colors.NC} Backup not found: {backup_name}")
            return False
        
        env_file = self.script_dir / '.env'
        
        # Backup current before restore
        if env_file.exists():
            self.create_backup('pre_restore')
        
        try:
            shutil.copy2(backup_path, env_file)
            self.logger.info(f"Restored from: {backup_name}")
            print(f"{Colors.GREEN}✓{Colors.NC} Restored from: {backup_name}")
            return True
        except Exception as e:
            self.logger.error(f"Restore failed: {e}")
            print(f"{Colors.RED}✗{Colors.NC} Restore failed: {e}")
            return False


class EnterpriseSetup:
    """Main orchestrator for enterprise setup"""
    
    def __init__(self, script_dir: Path, args: argparse.Namespace):
        self.script_dir = script_dir
        self.args = args
        self.logger = self._setup_logging()
        
        self.checker = SystemChecker(timeout=args.timeout)
        self.backup_mgr = BackupManager(script_dir)
        
        # Detect package manager
        installer_tmp = DependencyInstaller(script_dir, 'npm')
        detected_pm = installer_tmp.detect_package_manager()
        self.installer = DependencyInstaller(
            script_dir,
            detected_pm or 'npm',
            timeout=args.timeout
        )
    
    def _setup_logging(self) -> logging.Logger:
        """Configure logging"""
        log_dir = self.script_dir / 'logs'
        log_dir.mkdir(exist_ok=True)
        
        log_file = log_dir / f"setup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        
        logging.basicConfig(
            level=logging.DEBUG if self.args.verbose else logging.INFO,
            format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler() if self.args.verbose else logging.NullHandler()
            ]
        )
        
        logger = logging.getLogger(__name__)
        logger.info(f"Logging to: {log_file}")
        
        return logger
    
    def print_banner(self):
        """Print setup banner"""
        banner = f"""
{Colors.CYAN}{'═' * 70}
  {Colors.BOLD}Enterprise WrtnLabs Deployment System{Colors.NC}{Colors.CYAN}
  
  AutoBE + AutoView + Agentica + Vector Store
  Powered by Z.ai GLM-4.6 / GLM-4.5V
{'═' * 70}{Colors.NC}
"""
        print(banner)
    
    def cmd_validate(self) -> int:
        """Validate system prerequisites"""
        self.print_banner()
        
        print(f"\n{Colors.BOLD}System Validation{Colors.NC}")
        print(f"{Colors.CYAN}{'─' * 70}{Colors.NC}\n")
        
        if self.checker.run_all_checks():
            print(f"\n{Colors.GREEN}{Colors.BOLD}✓ All checks passed!{Colors.NC}")
            return 0
        else:
            print(f"\n{Colors.RED}{Colors.BOLD}✗ Validation failed{Colors.NC}")
            return 1
    
    def cmd_install(self) -> int:
        """Run full installation"""
        self.print_banner()
        
        # Step 1: Validate
        print(f"\n{Colors.BOLD}Step 1: Validation{Colors.NC}")
        print(f"{Colors.CYAN}{'─' * 70}{Colors.NC}\n")
        
        if not self.checker.run_all_checks():
            print(f"\n{Colors.RED}Prerequisites not met. Aborting.{Colors.NC}")
            return 1
        
        # Step 2: Backup
        if (self.script_dir / '.env').exists():
            print(f"\n{Colors.BOLD}Step 2: Backup{Colors.NC}")
            print(f"{Colors.CYAN}{'─' * 70}{Colors.NC}\n")
            self.backup_mgr.create_backup()
        
        # Step 3: Install
        print(f"\n{Colors.BOLD}Step 3: Dependencies{Colors.NC}")
        print(f"{Colors.CYAN}{'─' * 70}{Colors.NC}")
        
        success, failed = self.installer.install_all(self.args.verbose)
        
        if failed > 0:
            print(f"\n{Colors.YELLOW}⚠{Colors.NC} Installation completed with errors")
            return 1
        
        print(f"\n{Colors.GREEN}{Colors.BOLD}✓ Installation complete!{Colors.NC}")
        return 0
    
    def cmd_backup(self) -> int:
        """Create configuration backup"""
        self.print_banner()
        
        print(f"\n{Colors.BOLD}Creating Backup{Colors.NC}")
        print(f"{Colors.CYAN}{'─' * 70}{Colors.NC}\n")
        
        backup_name = self.args.name if hasattr(self.args, 'name') else None
        result = self.backup_mgr.create_backup(backup_name)
        
        return 0 if result else 1
    
    def cmd_restore(self) -> int:
        """Restore from backup"""
        self.print_banner()
        
        print(f"\n{Colors.BOLD}Available Backups{Colors.NC}")
        print(f"{Colors.CYAN}{'─' * 70}{Colors.NC}\n")
        
        backups = self.backup_mgr.list_backups()
        
        if not backups:
            print(f"{Colors.YELLOW}No backups found{Colors.NC}")
            return 1
        
        for idx, backup in enumerate(backups, 1):
            mtime = datetime.fromtimestamp(backup.stat().st_mtime)
            print(f"{idx}. {backup.name} ({mtime.strftime('%Y-%m-%d %H:%M:%S')})")
        
        if hasattr(self.args, 'backup_name') and self.args.backup_name:
            return 0 if self.backup_mgr.restore_backup(self.args.backup_name) else 1
        
        return 0
    
    def cmd_test(self) -> int:
        """Run in test mode (non-interactive)"""
        self.print_banner()
        
        print(f"\n{Colors.YELLOW}TEST MODE{Colors.NC} - Non-interactive validation\n")
        
        return self.cmd_validate()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Enterprise WrtnLabs Deployment System',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )
    
    parser.add_argument(
        '--timeout', '-t',
        type=int,
        default=5,
        help='Command timeout in seconds (default: 5)'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Validate command
    subparsers.add_parser(
        'validate',
        help='Validate system prerequisites'
    )
    
    # Install command
    subparsers.add_parser(
        'install',
        help='Run full installation'
    )
    
    # Backup command
    backup_parser = subparsers.add_parser(
        'backup',
        help='Create configuration backup'
    )
    backup_parser.add_argument(
        '--name', '-n',
        help='Backup name (default: timestamp)'
    )
    
    # Restore command
    restore_parser = subparsers.add_parser(
        'restore',
        help='Restore from backup'
    )
    restore_parser.add_argument(
        'backup_name',
        nargs='?',
        help='Backup name to restore'
    )
    
    # Test command
    subparsers.add_parser(
        'test',
        help='Run in test mode (non-interactive)'
    )
    
    args = parser.parse_args()
    
    # Default to validate if no command
    if not args.command:
        args.command = 'validate'
    
    # Get script directory
    script_dir = Path(__file__).parent.resolve()
    
    # Create setup instance
    setup = EnterpriseSetup(script_dir, args)
    
    # Route to command
    commands = {
        'validate': setup.cmd_validate,
        'install': setup.cmd_install,
        'backup': setup.cmd_backup,
        'restore': setup.cmd_restore,
        'test': setup.cmd_test,
    }
    
    try:
        exit_code = commands[args.command]()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}Interrupted by user{Colors.NC}")
        sys.exit(130)
    except Exception as e:
        setup.logger.error(f"Fatal error: {e}", exc_info=True)
        print(f"\n{Colors.RED}Fatal error: {e}{Colors.NC}")
        sys.exit(1)


if __name__ == '__main__':
    main()
