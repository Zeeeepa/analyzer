#!/usr/bin/env python3
"""
K2Think API Proxy - Scripts Setup Script
Complete environment setup for the scripts directory
"""

import os
import sys
import subprocess
import json
import getpass
from pathlib import Path

# Colors for terminal output
class Colors:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    CYAN = '\033[0;36m'
    MAGENTA = '\033[0;35m'
    NC = '\033[0m'  # No Color

def log_info(message):
    print(f"{Colors.BLUE}ℹ️  {message}{Colors.NC}")

def log_success(message):
    print(f"{Colors.GREEN}✅ {message}{Colors.NC}")

def log_warning(message):
    print(f"{Colors.YELLOW}⚠️  {message}{Colors.NC}")

def log_error(message):
    print(f"{Colors.RED}❌ {message}{Colors.NC}")

def log_step(message):
    print(f"{Colors.MAGENTA}▶️  {message}{Colors.NC}")

def run_command(cmd, check=True, capture_output=False):
    """Run a shell command and return result"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            check=check,
            capture_output=capture_output,
            text=True,
            encoding='utf-8'
        )
        return result
    except subprocess.CalledProcessError as e:
        log_error(f"Command failed: {cmd}")
        log_error(f"Error: {e}")
        if e.stdout:
            log_error(f"Stdout: {e.stdout}")
        if e.stderr:
            log_error(f"Stderr: {e.stderr}")
        raise

def setup_dependencies():
    """Setup system and Python dependencies"""
    log_step("STEP 1: Setting Up Dependencies")

    # Check if we're in the correct directory (root of K2Think project)
    if not Path("../k2think_proxy.py").exists():
        log_error("Not in the K2Think project directory!")
        log_info("Please run this script from the root directory of the project")
        sys.exit(1)

    # Change to parent directory
    os.chdir("..")
    log_info(f"Working in: {os.getcwd()}")

    # Run the main setup script
    log_info("Running complete setup...")
    subprocess.run([sys.executable, "setup.py"])

def secure_input(prompt, confirm=False):
    """Get secure input (password) with optional confirmation"""
    while True:
        value = getpass.getpass(prompt)
        if not value.strip():
            log_error("Input cannot be empty. Please try again.")
            continue

        if not confirm:
            return value.strip()

        confirm_value = getpass.getpass("Confirm: ")
        if value.strip() == confirm_value.strip():
            return value.strip()
        else:
            log_error("Passwords do not match. Please try again.")

def main():
    """Main setup function"""
    print()
    print(f"{Colors.MAGENTA}╔════════════════════════════════════════════════════════╗{Colors.NC}")
    print(f"{Colors.MAGENTA}║     🛠️  K2Think API Scripts - Setup & Configuration 🛠️   ║{Colors.NC}")
    print(f"{Colors.MAGENTA}╚════════════════════════════════════════════════════════╝{Colors.NC}")
    print()

    try:
        setup_dependencies()

        print()
        print(f"{Colors.GREEN}╔════════════════════════════════════════════════════════╗{Colors.NC}")
        print(f"{Colors.GREEN}║         🎉 SCRIPTS SETUP COMPLETE! 🎉                 ║{Colors.NC}")
        print(f"{Colors.GREEN}╚════════════════════════════════════════════════════════╝{Colors.NC}")
        print()
        print(f"{Colors.CYAN}✅ All dependencies installed and configured{Colors.NC}")
        print(f"{Colors.CYAN}✅ Virtual environment created and activated{Colors.NC}")
        print(f"{Colors.CYAN}✅ K2Think credentials saved{Colors.NC}")
        print(f"{Colors.CYAN}✅ Tokens generated{Colors.NC}")
        print(f"{Colors.CYAN}✅ Configuration file created{Colors.NC}")
        print()
        print(f"{Colors.YELLOW}Available Scripts:{Colors.NC}")
        print(f"  • python scripts/start.py     - Start the server")
        print(f"  • python scripts/send_request.py - Test the API")
        print(f"  • python scripts/all.py       - Full workflow (setup → start → test)")
        print()

    except Exception as e:
        log_error(f"Setup failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()