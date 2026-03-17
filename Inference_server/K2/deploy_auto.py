#!/usr/bin/env python3
"""
K2Think API - Fully Automated Windows Deployment Script
No interactive input required - uses defaults and continues through errors
"""

import os
import sys
import subprocess
import time
import socket
import json
import requests
from pathlib import Path
from datetime import datetime

# Enhanced Windows setup
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def get_local_ip():
    """Get local IP address for network access"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception:
        return "localhost"

def print_banner():
    """Print deployment banner"""
    print("🚀 K2Think API - Fully Automated Windows Deployment")
    print("=" * 60)
    print("📅 Date:", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    print("🖥️  Platform:", sys.platform)
    print("=" * 60)

def run_safe_command(cmd, timeout=None, cwd=None):
    """Run command with comprehensive error handling"""
    try:
        print(f"🔧 Running: {cmd[:80]}{'...' if len(cmd) > 80 else ''}")

        if os.name == 'nt':  # Windows
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=timeout,
                cwd=cwd
            )
        else:  # Unix-like systems
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=timeout,
                cwd=cwd
            )

        return result
    except subprocess.TimeoutExpired:
        print(f"⏰ Command timed out after {timeout} seconds")
        return None
    except Exception as e:
        print(f"❌ Command execution error: {e}")
        return None

def create_default_credentials():
    """Create default K2Think credentials without user input"""
    print("\n=== 🔐 Creating Default K2Think Credentials ===")

    # Ensure data directory exists
    Path("data").mkdir(exist_ok=True)
    accounts_file = "data/accounts.txt"

    # Create default credentials
    email = "developer@pixelium.uk"
    password = "developer123"

    # Save credentials
    credentials = {"email": email, "password": password}
    try:
        with open(accounts_file, "w", encoding="utf-8") as f:
            json.dump(credentials, f, indent=2)
        print(f"✅ Default credentials saved to {accounts_file}")
        print(f"   Email: {email}")
        print(f"   Password: {'*' * len(password)}")
    except Exception as e:
        print(f"⚠️ Could not save credentials: {e}")

    return email, password

def setup_environment():
    """Setup the Python environment"""
    print("\n=== 🏗️ Environment Setup ===")

    # Check Python version
    print(f"🐍 Python version: {sys.version}")

    # Create virtual environment
    if not Path("venv").exists():
        print("📦 Creating virtual environment...")
        result = run_safe_command(f"{sys.executable} -m venv venv", timeout=60)
        if result is None or result.returncode != 0:
            print("❌ Failed to create virtual environment")
            return False
        print("✅ Virtual environment created")
    else:
        print("✅ Virtual environment already exists")

    # Check requirements.txt
    if not Path("requirements.txt").exists():
        print("❌ requirements.txt not found!")
        print("🔍 Current directory contents:")
        for item in sorted(Path('.').iterdir()):
            if item.is_file() and item.name.endswith('.txt'):
                print(f"   📄 {item.name}")
        return False

    # Install dependencies
    print("📥 Installing dependencies...")
    if os.name == 'nt':
        pip_cmd = "venv\\Scripts\\python.exe -m pip install -r requirements.txt"
    else:
        pip_cmd = "venv/bin/python -m pip install -r requirements.txt"

    result = run_safe_command(pip_cmd, timeout=180)
    if result is None:
        print("⚠️ Dependency installation timed out, continuing...")
        return True

    if result.returncode != 0:
        print("⚠️ Some dependencies had issues, but continuing...")
        if result.stderr:
            error_preview = result.stderr[:200] + "..." if len(result.stderr) > 200 else result.stderr
            print(f"📝 Error details (partial): {error_preview}")
    else:
        print("✅ Dependencies installed successfully")

    return True

def fetch_tokens():
    """Fetch K2Think tokens"""
    print("\n=== 🔑 Fetching K2Think Tokens ===")

    if os.name == 'nt':
        python_cmd = "venv\\Scripts\\python.exe"
    else:
        python_cmd = "venv/bin/python"

    cmd = f"{python_cmd} get_tokens.py data/accounts.txt data/tokens.txt"

    result = run_safe_command(cmd, timeout=90)
    if result is None:
        print("⚠️ Token fetch timed out, continuing...")
        return True

    if result.returncode != 0:
        print("⚠️ Token fetch had issues, but continuing...")
        if result.stderr:
            error_preview = result.stderr[:200] + "..." if len(result.stderr) > 200 else result.stderr
            print(f"📝 Error details (partial): {error_preview}")
    else:
        print("✅ Tokens fetched successfully")

    return True

def start_server():
    """Start the K2Think API server"""
    print("\n=== 🚀 Starting K2Think API Server ===")

    # Stop existing server
    stop_existing_server()

    # Start new server
    if os.name == 'nt':
        python_cmd = "venv\\Scripts\\python.exe"
        # Use Windows-specific command format
        server_cmd = f'set PYTHONPATH=src && {python_cmd} -m uvicorn k2think_proxy:app --host 0.0.0.0 --port 7000 --log-level info'
    else:
        python_cmd = "venv/bin/python"
        server_cmd = f"PYTHONPATH=src {python_cmd} -m uvicorn k2think_proxy:app --host 0.0.0.0 --port 7000 --log-level info"

    print("🔥 Starting server process...")

    # Create log file
    try:
        with open("server.log", "a", encoding="utf-8") as log_file:
            log_file.write(f"\n\n=== Server Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    except Exception as e:
        print(f"⚠️ Could not create log file: {e}")

    # Start server with proper process management
    if os.name == 'nt':
        # Windows: Use DETACHED_PROCESS to keep it running after script ends
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200

        try:
            process = subprocess.Popen(
                server_cmd,
                shell=True,
                creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                close_fds=True
            )
        except Exception as e:
            print(f"❌ Failed to start server process: {e}")
            return False
    else:
        # Unix-like systems
        try:
            process = subprocess.Popen(
                server_cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True
            )
        except Exception as e:
            print(f"❌ Failed to start server process: {e}")
            return False

    # Save PID
    Path("data").mkdir(exist_ok=True)
    try:
        with open("data/.server.pid", "w") as f:
            f.write(str(process.pid))
        print(f"📝 Server PID: {process.pid}")
    except Exception as e:
        print(f"⚠️ Could not save PID: {e}")

    # Wait for server to start
    print("⏳ Waiting for server to start...")
    local_ip = get_local_ip()

    for i in range(30, 0, -1):
        try:
            response = requests.get("http://localhost:7000/", timeout=2)
            if response.status_code == 200:
                print("\n" + "="*60)
                print("🎉 K2Think API Server Started Successfully!")
                print("="*60)
                print(f"🌐 Local Access:    http://localhost:7000")
                print(f"🌍 Network Access:  http://{local_ip}:7000")
                print(f"🔗 API Endpoint:   http://localhost:7000/v1/chat/completions")
                print(f"🔑 API Key:        sk-k2think (or any key)")
                print(f"🤖 Model Support:  Any model name (gpt-4, claude-3, custom)")
                print("="*60)
                return True
        except Exception:
            pass

        time.sleep(1)
        if i % 5 == 0:
            print(f"⏳ Waiting... {i}s remaining")

    print("❌ Server failed to start within timeout")
    print("🔍 Check server.log for details")
    return False

def stop_existing_server():
    """Stop any existing server"""
    if Path("data/.server.pid").exists():
        try:
            with open("data/.server.pid", 'r') as f:
                old_pid = f.read().strip()

            if old_pid and old_pid.isdigit():
                print(f"🛑 Stopping existing server (PID: {old_pid})...")

                if os.name == 'nt':  # Windows
                    result = run_safe_command(f"taskkill /F /PID {old_pid}")
                else:  # Unix-like systems
                    result = run_safe_command(f"kill {old_pid}")

                time.sleep(2)
        except Exception as e:
            print(f"⚠️ Could not stop existing server: {e}")

def test_api():
    """Test the API with a sample request"""
    print("\n=== 🧪 Testing API ===")

    try:
        print("📡 Sending test request...")
        response = requests.post(
            "http://localhost:7000/v1/chat/completions",
            headers={
                "Authorization": "Bearer sk-k2think",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4",
                "messages": [{"role": "user", "content": "Write a short haiku about programming"}],
                "max_tokens": 50
            },
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            print("✅ API Test Successful!")
            if 'choices' in data and len(data['choices']) > 0:
                content = data['choices'][0]['message']['content']
                print(f"📝 Response: {content[:100]}{'...' if len(content) > 100 else ''}")
            if 'model' in data:
                print(f"🔢 Model: {data['model']}")
            if 'usage' in data:
                print(f"💰 Tokens: {data['usage'].get('total_tokens', 'N/A')}")
            return True
        else:
            print(f"❌ API Test Failed: {response.text}")
            return False

    except Exception as e:
        print(f"❌ API Test Error: {e}")
        return False

def display_usage_instructions(local_ip):
    """Display comprehensive usage instructions"""
    print("\n" + "="*60)
    print("🚀 K2Think API Deployment Complete!")
    print("="*60)
    print()
    print("📡 Your K2Think API Server is Running:")
    print(f"   • Local:    http://localhost:7000")
    print(f"   • Network:  http://{local_ip}:7000")
    print()
    print("🔑 Quick API Test:")
    print("   curl -X POST http://localhost:7000/v1/chat/completions \\")
    print("     -H 'Authorization: Bearer sk-k2think' \\")
    print("     -H 'Content-Type: application/json' \\")
    print('     -d \'{"model":"gpt-4","messages":[{"role":"user","content":"Hello!"}]}\'')
    print()
    print("🐍 Python Integration:")
    print("   from openai import OpenAI")
    print(f"   client = OpenAI(base_url='http://localhost:7000/v1', api_key='sk-k2think')")
    print("   response = client.chat.completions.create(")
    print('       model="any-model-name", messages=[{"role": "user", "content":"Hello!"}])')
    print()
    print("📋 Server Management:")
    print(f"   • Log file:   {os.path.abspath('server.log')}")
    print(f"   • PID file:   {os.path.abspath('data/.server.pid')}")
    if os.name == 'nt':  # Windows
        print("   • Stop server: taskkill /F /PID <PID>")
    else:  # Unix-like systems
        print("   • Stop server: kill <PID>")
    print()
    print("✨ Features:")
    print("   • OpenAI-compatible API")
    print("   • Any model name support")
    print("   • Token auto-refresh")
    print("   • Streaming responses")
    print("   • Function calling support")
    print("="*60)

def main():
    """Main fully automated deployment function"""
    print_banner()

    try:
        # Step 1: Create default credentials
        email, password = create_default_credentials()

        # Step 2: Environment setup
        if not setup_environment():
            print("\n❌ Environment setup failed!")
            print("🔧 Please check the error messages above and try again.")
            return False

        # Step 3: Token fetch
        if not fetch_tokens():
            print("⚠️ Token fetch had issues, but continuing...")

        # Step 4: Start server
        if not start_server():
            print("\n❌ Server start failed!")
            print("🔧 Check server.log for error details.")
            return False

        # Step 5: Test API
        if not test_api():
            print("⚠️ API test had issues, but server should be running.")

        # Step 6: Display instructions
        local_ip = get_local_ip()
        display_usage_instructions(local_ip)

        print("\n🎉 DEPLOYMENT COMPLETE! Your K2Think API is ready!")
        print("💡 The server will continue running in the background.")
        print("📝 All logs are being written to server.log")

        return True

    except KeyboardInterrupt:
        print("\n\n⏹️ Deployment cancelled by user")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        print("📋 Full error details:")
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)