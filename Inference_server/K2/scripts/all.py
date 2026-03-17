#!/usr/bin/env python3
"""
K2Think API - Complete Automated Deployment
Single command: asks for credentials, saves them, starts server, shows IP:port, runs tests
"""

import os
import sys
import subprocess
import time
import socket
import json
from pathlib import Path

# Ensure UTF-8 encoding
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

def get_python_executable():
    """Get the correct Python executable path for the current OS"""
    if os.name == 'nt':
        return "venv/Scripts/python.exe"
    else:
        return "venv/bin/python"

def get_credentials():
    """Get K2Think credentials from user"""
    print("\n=== K2Think Credentials Setup ===")
    print("Enter your K2Think account credentials:")
    print("(Press Enter to use default: developer@pixelium.uk)")
    print()

    email = input("Email [developer@pixelium.uk]: ").strip()
    if not email:
        email = "developer@pixelium.uk"

    password = input("Password [developer123?]: ").strip()
    if not password:
        password = "developer123?"

    return email, password

def save_credentials(email, password):
    """Save credentials to data/accounts.txt"""
    # Ensure data directory exists
    os.makedirs("data", exist_ok=True)

    credentials = {
        "email": email,
        "password": password
    }

    with open("data/accounts.txt", "w", encoding="utf-8") as f:
        json.dump(credentials, f, indent=2)

    print(f"\n✅ Credentials saved to data/accounts.txt")
    print(f"   Email: {email}")

def setup_environment():
    """Setup the environment"""
    print("\n=== Phase 1: Environment Setup ===")

    # Create virtual environment if it doesn't exist
    if not Path("venv").exists():
        print("Creating virtual environment...")
        result = subprocess.run([sys.executable, "-m", "venv", "venv"], capture_output=True, text=True)
        if result.returncode != 0:
            print(f"❌ Failed to create venv: {result.stderr}")
            return False
        print("✅ Virtual environment created")
    else:
        print("✅ Virtual environment already exists")

    # Install dependencies
    print("Installing dependencies...")
    pip_cmd = f"{get_python_executable()} -m pip install -r requirements.txt"

    # Check if requirements.txt exists
    if not Path("requirements.txt").exists():
        print("❌ requirements.txt not found in current directory")
        print(f"Current directory: {os.getcwd()}")
        print("Files in current directory:")
        for f in os.listdir('.'):
            if f.endswith('.txt'):
                print(f"  - {f}")
        return False

    result = run_command_with_encoding(pip_cmd, timeout=120)
    if result is None:
        print("❌ Dependency installation timed out")
        return False

    if result.returncode != 0:
        print(f"❌ Failed to install dependencies: {result.stderr}")
        print("Continuing anyway...")
        return True  # Continue even if some packages fail
    print("✅ Dependencies installed")

    return True

def run_command_with_encoding(cmd, timeout=None):
    """Run command with proper UTF-8 encoding handling"""
    try:
        if os.name == 'nt':  # Windows
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=timeout
            )
        else:  # Unix-like systems
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=timeout
            )
        return result
    except subprocess.TimeoutExpired:
        return None
    except Exception as e:
        print(f"Command error: {e}")
        return None

def fetch_tokens():
    """Fetch K2Think tokens using credentials"""
    print("\n=== Phase 2: Fetching K2Think Tokens ===")

    # Run get_tokens.py
    if os.name == 'nt':
        python_cmd = "venv\\Scripts\\python.exe"
    else:
        python_cmd = get_python_executable()

    cmd = f"{python_cmd} get_tokens.py data/accounts.txt data/tokens.txt"
    print(f"Running: {cmd}")

    result = run_command_with_encoding(cmd, timeout=60)
    if result is None:
        print("⚠️ Token fetch timed out, but continuing...")
        return True

    if result.returncode != 0:
        print(f"⚠️ Token fetch had issues: {result.stderr}")
        print("Continuing anyway...")
        return True

    print("✅ Tokens fetched successfully")
    return True

def stop_existing_server():
    """Stop any existing server process"""
    if Path("data/.server.pid").exists():
        try:
            with open("data/.server.pid", 'r') as f:
                old_pid = f.read().strip()
            if os.name == 'nt':  # Windows
                subprocess.run(f"taskkill /F /PID {old_pid}", shell=True, capture_output=True)
            else:  # Unix-like systems
                subprocess.run(f"kill {old_pid}", shell=True, capture_output=True)
            time.sleep(2)
        except:
            pass

def start_server():
    """Start the K2Think API server"""
    print("\n=== Phase 3: Starting K2Think API Server ===")

    # Stop any existing server
    stop_existing_server()

    # Start new server
    python_cmd = get_python_executable()
    if os.name == 'nt':
        server_cmd = f"set PYTHONPATH=src && {python_cmd} -m uvicorn k2think_proxy:app --host 0.0.0.0 --port 7000"
    else:
        server_cmd = f"PYTHONPATH=src {python_cmd} -m uvicorn k2think_proxy:app --host 0.0.0.0 --port 7000"

    # Start server in background with proper process management
    if os.name == 'nt':
        # On Windows, use DETACHED_PROCESS to keep it running after script ends
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        DETACHED_PROCESS = 0x00000008

        process = subprocess.Popen(
            server_cmd,
            shell=True,
            creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            close_fds=True
        )
    else:
        # On Unix-like systems, use nohup-like behavior
        process = subprocess.Popen(
            server_cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True
        )

    # Save PID
    Path("data").mkdir(exist_ok=True)
    with open("data/.server.pid", "w") as f:
        f.write(str(process.pid))

    # Wait for server to start
    local_ip = get_local_ip()
    for i in range(30):
        try:
            import requests
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
                print()
                return True
        except:
            pass
        time.sleep(1)
        print(f"Waiting for server to start... ({i+1}/30)")

    print("❌ Server failed to start")
    return False

def test_api():
    """Test the API with a sample request"""
    print("\n=== Phase 4: Testing API ===")

    try:
        import requests

        print("Sending test request...")
        response = requests.post(
            "http://localhost:7000/v1/chat/completions",
            headers={
                "Authorization": "Bearer sk-k2think",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4",
                "messages": [{"role": "user", "content": "Write a short haiku about programming"}],
                "max_tokens": 100
            },
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            print("✅ API Test Successful!")
            print(f"📝 Response: {data['choices'][0]['message']['content'][:100]}...")
            print(f"🔢 Model: {data['model']}")
            print(f"💰 Tokens: {data['usage']['total_tokens']}")
            return True
        else:
            print(f"❌ API Test Failed: {response.text}")
            return False

    except Exception as e:
        print(f"❌ API Test Error: {e}")
        return False

def display_usage_instructions(local_ip):
    """Display usage instructions"""
    print("\n" + "="*60)
    print("🚀 K2Think API Deployment Complete!")
    print("="*60)
    print()
    print("📡 Your K2Think API Server is Running:")
    print(f"   • Local:    http://localhost:7000")
    print(f"   • Network:  http://{local_ip}:7000")
    print()
    print("🔑 API Usage:")
    print("   curl -X POST http://localhost:7000/v1/chat/completions \\")
    print("     -H 'Authorization: Bearer sk-k2think' \\")
    print("     -H 'Content-Type: application/json' \\")
    print('     -d \'{"model":"gpt-4","messages":[{"role":"user","content":"Hello!"}]}\'')
    print()
    print("🐍 Python Usage:")
    print("   from openai import OpenAI")
    print(f"   client = OpenAI(base_url='http://localhost:7000/v1', api_key='sk-k2think')")
    print("   response = client.chat.completions.create(")
    print('       model="any-model-name", messages=[{"role": "user", "content": "Hello!"}])')
    print()
    print("📋 Management:")
    print("   • View logs:   server.log")
    if os.name == 'nt':  # Windows
        print("   • Stop server: taskkill /F /PID $(cat data/.server.pid)")
    else:  # Unix-like systems
        print("   • Stop server: kill $(cat data/.server.pid)")
    print("="*60)

def main():
    """Main deployment function"""
    print("🚀 K2Think API - Automated Deployment")
    print("="*50)

    # Step 1: Get credentials
    email, password = get_credentials()
    save_credentials(email, password)

    # Step 2: Setup environment
    if not setup_environment():
        print("\n❌ Environment setup failed!")
        sys.exit(1)

    # Step 3: Fetch tokens
    if not fetch_tokens():
        print("\n❌ Token fetch failed!")
        sys.exit(1)

    # Step 4: Start server
    if not start_server():
        print("\n❌ Server start failed!")
        sys.exit(1)

    # Step 5: Test API
    if not test_api():
        print("\n⚠️  API test had issues, but server is running")

    # Step 6: Display usage instructions
    local_ip = get_local_ip()
    display_usage_instructions(local_ip)

    print("\n🎉 DEPLOYMENT COMPLETE! Your K2Think API is ready!")

if __name__ == "__main__":
    main()