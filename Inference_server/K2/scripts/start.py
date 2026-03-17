#!/usr/bin/env python3
"""
K2Think API Proxy - Server Start Script
Activates virtual environment and starts the server with endpoint information
"""

import os
import sys
import subprocess
import time
import platform
import socket
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

def get_config_value(config_file, key):
    """Get value from .env file"""
    if not Path(config_file).exists():
        return None

    with open(config_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line.startswith(key):
                return line.split('=', 1)[1].strip().strip('"\'')

    return None

def get_local_ip():
    """Get local IP address for API access"""
    try:
        # Create a socket to get local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception:
        return "localhost"

def start_server():
    """Start the server with virtual environment"""
    log_step("STEP 1: Activating Virtual Environment")

    # Determine paths based on platform
    if platform.system() == "Windows":
        activate_cmd = "venv\\Scripts\\activate"
        python_cmd = "venv\\Scripts\\python"
    else:
        activate_cmd = "venv/bin/activate"
        python_cmd = "venv/bin/python"

    # Check if virtual environment exists
    if not Path("venv").exists():
        log_error("Virtual environment not found!")
        log_info("Please run 'python setup.py' first to create the environment")
        sys.exit(1)

    # Load environment variables
    config_file = ".env"
    port = "7000"  # Default port

    if Path(config_file).exists():
        port = get_config_value(config_file, "PORT") or get_config_value(config_file, "SERVER_PORT") or "7000"

    log_info(f"Using port: {port}")

    # Check if server is already running
    pid_file = "data/.server.pid"
    if Path(pid_file).exists():
        try:
            with open(pid_file, 'r') as f:
                old_pid = f.read().strip()

            # Check if process is still running
            result = subprocess.run(['ps', '-p', old_pid], capture_output=True, text=True)
            if result.returncode == 0:
                log_warning(f"Server already running with PID {old_pid} on port {port}")
                print()
                print(f"{Colors.CYAN}📊 Server Information:{Colors.NC}")
                print(f"   • URL:  http://localhost:{port}")
                print(f"   • PID:  {old_pid}")
                print(f"   • Logs: tail -f server.log")
                print()
                print(f"{Colors.YELLOW}📋 Management Commands:{Colors.NC}")
                print(f"   • View logs:   tail -f server.log")
                print(f"   • Stop server: kill {old_pid}")
                print(f"   • Restart:     python scripts/start.py")
                return old_pid
            else:
                log_warning(f"Removing stale PID file: {old_pid}")
                Path(pid_file).unlink()
        except Exception as e:
            log_warning(f"Error checking existing PID: {e}")
            Path(pid_file).unlink()

    log_step("STEP 2: Starting K2Think API Server")

    # Start the server
    log_info(f"Starting K2Think API server on port {port}...")

    # Use subprocess to run server in background
    if platform.system() == "Windows":
        # Windows doesn't have nohup, use start
        cmd = f"start /b {python_cmd} src/k2think_proxy.py > server.log 2>&1"
    else:
        cmd = f"nohup {python_cmd} src/k2think_proxy.py > server.log 2>&1 &"

    try:
        # Run activation command and then start server
        if platform.system() == "Windows":
            # Windows approach: run the Python script directly with activated environment
            process = subprocess.Popen(
                [python_cmd, "src/k2think_proxy.py"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
        else:
            # Unix approach: use bash with activation
            process = subprocess.Popen(
                ["bash", "-c", f"source {activate_cmd} && {python_cmd} src/k2think_proxy.py"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

        # Save PID to file
        server_pid = str(process.pid)
        with open(pid_file, 'w') as f:
            f.write(server_pid)

        log_success(f"Server process started with PID {server_pid}")

        # Wait for server to initialize
        log_info("Waiting for server to initialize...")
        time.sleep(3)

        # Check if server is running and responding
        max_retries = 15
        retry = 0
        local_ip = get_local_ip()

        while retry < max_retries:
            try:
                import requests
                response = requests.get(f"http://localhost:{port}/", timeout=2)
                if response.status_code == 200:
                    print()
                    print(f"{Colors.GREEN}╔════════════════════════════════════════════════════════╗{Colors.NC}")
                    print(f"{Colors.GREEN}║         🎉 SERVER STARTED SUCCESSFULLY! 🎉           ║{Colors.NC}")
                    print(f"{Colors.GREEN}╚════════════════════════════════════════════════════════╝{Colors.NC}")
                    print()
                    print(f"{Colors.CYAN}🌐 OpenAI-Compatible API Endpoints:{Colors.NC}")
                    print(f"   • Local Access:   http://localhost:{port}/v1/chat/completions")
                    print(f"   • Network Access: http://{local_ip}:{port}/v1/chat/completions")
                    print(f"   • Health Check:   http://localhost:{port}/")
                    print(f"   • Models List:    http://localhost:{port}/v1/models")
                    print()
                    print(f"{Colors.CYAN}📊 Server Information:{Colors.NC}")
                    print(f"   • Status:           RUNNING ✓")
                    print(f"   • Local URL:        http://localhost:{port}")
                    print(f"   • Network URL:      http://{local_ip}:{port}")
                    print(f"   • PID:              {server_pid}")
                    print(f"   • Logs:             server.log")
                    print()
                    print(f"{Colors.YELLOW}🔑 API Configuration:{Colors.NC}")
                    print(f"   • Base URL:         http://localhost:{port}/v1")
                    print(f"   • API Key:          (any key works - see .env)")
                    print(f"   • Model:            MBZUAI-IFM/K2-Think")
                    print()
                    print(f"{Colors.YELLOW}📋 Management Commands:{Colors.NC}")
                    print(f"   • View logs:        tail -f server.log")
                    print(f"   • Stop server:      kill {server_pid}")
                    print(f"   • Test API:         python scripts/send_request.py")
                    print()
                    print(f"{Colors.GREEN}🚀 Your K2Think API Proxy is ready to use!{Colors.NC}")
                    print()

                    return server_pid
            except requests.exceptions.RequestException:
                retry += 1
                if retry < max_retries:
                    time.sleep(2)

        log_warning("Server process running but not responding to HTTP requests")
        print()
        print(f"{Colors.YELLOW}📄 Recent logs:{Colors.NC}")
        try:
            with open("server.log", 'r') as f:
                lines = f.readlines()[-20:]
                for line in lines:
                    print(f"  {line.strip()}")
        except FileNotFoundError:
            print("  No logs available yet")
        print()
        print(f"{Colors.YELLOW}Server may still be initializing. Check logs with: tail -f server.log{Colors.NC}")
        print(f"Server PID: {server_pid} (saved to .server.pid)")

        return server_pid

    except Exception as e:
        log_error(f"Failed to start server: {e}")
        if Path(pid_file).exists():
            Path(pid_file).unlink()
        sys.exit(1)

def main():
    """Main start function"""
    print()
    print(f"{Colors.MAGENTA}╔════════════════════════════════════════════════════════╗{Colors.NC}")
    print(f"{Colors.MAGENTA}║                🚀 K2Think API - Server Start 🚀        ║{Colors.NC}")
    print(f"{Colors.MAGENTA}╚════════════════════════════════════════════════════════╝{Colors.NC}")
    print()

    try:
        server_pid = start_server()
        log_success("Server startup process completed")

    except Exception as e:
        log_error(f"Server startup failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()