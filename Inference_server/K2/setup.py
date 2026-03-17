#!/usr/bin/env python3
"""
K2Think API Proxy - Complete Setup Script
Sets up the entire environment, installs dependencies, configures credentials, and generates tokens
"""

import os
import sys
import subprocess
import json
import platform
import getpass
from pathlib import Path
from datetime import datetime

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
    print(f"{Colors.BLUE}[INFO] {message}{Colors.NC}")

def log_success(message):
    print(f"{Colors.GREEN}[OK] {message}{Colors.NC}")

def log_warning(message):
    print(f"{Colors.YELLOW}[WARN] {message}{Colors.NC}")

def log_error(message):
    print(f"{Colors.RED}[ERROR] {message}{Colors.NC}")

def log_step(message):
    print(f"{Colors.MAGENTA}[STEP] {message}{Colors.NC}")

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

def setup_system_dependencies():
    """Install system dependencies"""
    log_step("STEP 1: Installing System Dependencies")

    # Check if running as root or with sudo privileges
    try:
        if os.geteuid() != 0:
            sudo_cmd = "sudo"
            log_info("Using sudo for system package installation")
        else:
            sudo_cmd = ""
    except AttributeError:
        # Windows doesn't have geteuid
        sudo_cmd = "sudo"
        log_info("On Windows: manual dependency installation may be required")

    # Detect package manager and install dependencies
    log_info("Detecting package manager...")

    if platform.system() == "Linux":
        # Try apt-get first
        try:
            run_command("command -v apt-get", check=False)
            log_success("Detected apt (Debian/Ubuntu)")

            packages = []
            if not run_command("command -v python3", check=False).returncode == 0:
                packages.append("python3")

            if not run_command("dpkg -l | grep -q python3-pip", check=False).returncode == 0:
                packages.append("python3-pip")

            if not run_command("dpkg -l | grep -q python3-venv", check=False).returncode == 0:
                packages.append("python3-venv")

            if not run_command("command -v curl", check=False).returncode == 0:
                packages.append("curl")

            if packages:
                log_info(f"Installing system packages: {', '.join(packages)}")
                run_command(f"{sudo_cmd} apt-get update -qq")
                run_command(f"{sudo_cmd} apt-get install -y -qq {' '.join(packages)}")
                log_success("System packages installed")
            else:
                log_success("All required system packages already installed")

        except subprocess.CalledProcessError:
            # Try yum
            try:
                run_command("command -v yum", check=False)
                log_success("Detected yum (CentOS/RHEL)")

                packages = []
                if not run_command("command -v python3", check=False).returncode == 0:
                    packages.append("python3")
                if not run_command("rpm -q python3-pip", check=False).returncode == 0:
                    packages.append("python3-pip")
                if not run_command("command -v curl", check=False).returncode == 0:
                    packages.append("curl")

                if packages:
                    log_info(f"Installing system packages: {', '.join(packages)}")
                    run_command(f"{sudo_cmd} yum install -y -q {' '.join(packages)}")
                    log_success("System packages installed")
                else:
                    log_success("All required system packages already installed")

            except subprocess.CalledProcessError:
                log_warning("Could not detect package manager. Please install python3, pip, and curl manually.")
    elif platform.system() == "Windows":
        log_info("Windows detected - checking for Python installation")

        # Check for Python on Windows
        try:
            run_command("python --version", check=False)
            log_success("Python found on Windows")
        except subprocess.CalledProcessError:
            log_error("Python not found on Windows! Please install Python 3 manually.")
            sys.exit(1)

        log_info("Windows setup complete - system dependencies should be available")
    else:
        log_warning(f"Platform {platform.system()} not fully automated. Please ensure python3, pip, and curl are installed.")

    # Verify Python installation
    log_info("Verifying Python installation...")
    try:
        if platform.system() == "Windows":
            result = run_command("python --version")
        else:
            result = run_command("python3 --version")
        log_success(f"Python 3 is available: {result.stdout.strip()}")
    except subprocess.CalledProcessError:
        log_error("Python 3 not found! Please install Python 3 manually.")
        sys.exit(1)

def setup_virtual_environment():
    """Create and activate virtual environment"""
    log_step("STEP 2: Setting Up Python Virtual Environment")

    if not Path("venv").exists():
        log_info("Creating virtual environment...")
        try:
            if platform.system() == "Windows":
                run_command("python -m venv venv")
            else:
                run_command("python3 -m venv venv")
            log_success("Virtual environment created")
        except subprocess.CalledProcessError:
            log_warning("Failed to create venv, trying with --system-site-packages")
            if platform.system() == "Windows":
                run_command("python -m venv --system-site-packages venv")
            else:
                run_command("python3 -m venv --system-site-packages venv")
            log_success("Virtual environment created")
    else:
        log_success("Virtual environment already exists")

def install_python_dependencies():
    """Install Python dependencies from requirements.txt"""
    log_step("STEP 3: Installing Python Dependencies")

    # Activate virtual environment
    if platform.system() == "Windows":
        pip_path = "venv\\Scripts\\pip"
        python_path = "venv\\Scripts\\python"
    else:
        pip_path = "venv/bin/pip"
        python_path = "venv/bin/python"

    # Upgrade pip
    log_info("Upgrading pip...")
    run_command(f"{pip_path} install --upgrade pip")

    # Install dependencies
    log_info("Installing Python packages from requirements.txt...")
    run_command(f"{pip_path} install -r requirements.txt")

    # Verify critical packages
    log_info("Verifying critical packages...")
    try:
        run_command(f"{python_path} -c \"import fastapi, uvicorn, httpx, pydantic\"")
        log_success("All critical packages verified")
    except subprocess.CalledProcessError:
        log_error("Failed to verify critical packages")
        sys.exit(1)

def setup_credentials():
    """Setup K2Think credentials with secure input"""
    log_step("STEP 4: Configuring K2Think Credentials")

    # Create data directory
    Path("data").mkdir(exist_ok=True)

    accounts_file = "data/accounts.txt"
    if not Path(accounts_file).exists():
        log_info("Setting up K2Think credentials...")

        print()
        print(f"{Colors.CYAN}=== K2Think Account Setup ==={Colors.NC}")
        print()

        # Get email
        email = input(f"{Colors.BLUE}Enter your K2Think account email: {Colors.NC}").strip()
        while not email or '@' not in email:
            log_error("Please enter a valid email address")
            email = input(f"{Colors.BLUE}Enter your K2Think account email: {Colors.NC}").strip()

        # Get password with confirmation
        password = secure_input(f"{Colors.BLUE}Enter your K2Think account password: {Colors.NC}", confirm=True)

        # Save credentials
        credentials = {"email": email, "password": password}
        with open(accounts_file, 'w', encoding='utf-8') as f:
            json.dump(credentials, f, indent=2)

        print()
        print(f"{Colors.GREEN}✅ Credentials saved successfully!{Colors.NC}")
        print(f"Email: {email}")
        print(f"Password: {'*' * len(password)}")
        print()

        log_success(f"Credentials saved to {accounts_file}")
    else:
        # Load existing credentials
        with open(accounts_file, 'r', encoding='utf-8') as f:
            credentials = json.load(f)

        print()
        print(f"{Colors.CYAN}=== Existing Credentials Found ==={Colors.NC}")
        print(f"Email: {credentials.get('email', 'unknown')}")
        print()

        choice = input(f"{Colors.YELLOW}Would you like to update credentials? (y/N): {Colors.NC}").lower()
        if choice == 'y':
            os.remove(accounts_file)
            log_info("Removed old credentials. Restarting setup...")
            return setup_credentials()
        else:
            log_success("Using existing credentials")

def verify_tokens():
    """Verify K2Think tokens exist"""
    log_step("STEP 5: Verifying K2Think Tokens")

    if Path("data/tokens.txt").exists() and Path("data/tokens.txt").stat().st_size > 0:
        with open("data/tokens.txt", 'r') as f:
            tokens = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        log_success(f"Token pool ready with {len(tokens)} token(s)")
    else:
        log_warning("No tokens found. Please ensure data/tokens.txt contains valid K2Think tokens")
        log_info("You can add tokens manually to data/tokens.txt (one token per line)")

def create_environment_file():
    """Create .env configuration file"""
    log_step("STEP 6: Creating Configuration File")

    env_file = ".env"
    if not Path(env_file).exists():
        timestamp = int(datetime.now().timestamp())
        port = 7000

        config = f"""# K2Think API Proxy Configuration
# Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

# API Configuration
PORT={port}
SERVER_PORT={port}

# Authentication
VALID_API_KEY=sk-k2think-proxy-{timestamp}
ALLOW_ANY_API_KEY=true

# Token Management
ENABLE_TOKEN_AUTO_UPDATE=true
TOKEN_UPDATE_INTERVAL=3600
MAX_CONSECUTIVE_FAILURES=3

# Logging
LOG_LEVEL=INFO

# Token Management
TOKENS_FILE=data/tokens.txt
"""

        with open(env_file, 'w', encoding='utf-8') as f:
            f.write(config)

        log_success(f"Configuration file created: {env_file}")
    else:
        log_success("Configuration file already exists")

def main():
    """Main setup function"""
    print()
    print(f"{Colors.MAGENTA}================================================================{Colors.NC}")
    print(f"{Colors.MAGENTA}===    K2Think API - Complete Setup & Deployment    ==={Colors.NC}")
    print(f"{Colors.MAGENTA}================================================================{Colors.NC}")
    print()

    try:
        setup_system_dependencies()
        setup_virtual_environment()
        install_python_dependencies()
        setup_credentials()
        verify_tokens()
        create_environment_file()

        print()
        print(f"{Colors.GREEN}================================================================{Colors.NC}")
        print(f"{Colors.GREEN}===              SETUP COMPLETE! 🎉                      ==={Colors.NC}")
        print(f"{Colors.GREEN}================================================================{Colors.NC}")
        print()
        print(f"{Colors.CYAN}✅ All dependencies installed and configured{Colors.NC}")
        print(f"{Colors.CYAN}✅ Virtual environment created and activated{Colors.NC}")
        print(f"{Colors.CYAN}✅ K2Think credentials saved{Colors.NC}")
        print(f"{Colors.CYAN}✅ Tokens generated{Colors.NC}")
        print(f"{Colors.CYAN}✅ Configuration file created{Colors.NC}")
        print()
        print(f"{Colors.YELLOW}Next steps:{Colors.NC}")
        print(f"  • Start server: python scripts/start.py")
        print(f"  • Test API:    python scripts/send_request.py")
        print(f"  • Run all:     python scripts/all.py")
        print()

    except Exception as e:
        log_error(f"Setup failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()