#!/usr/bin/env python3
"""
K2Think API Proxy - Send Request Script
Sends real OpenAI API requests to test the K2Think proxy server
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path

# Try to import OpenAI, use requests as fallback
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

import requests

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

def get_config_values():
    """Get configuration from .env file"""
    config = {}
    config_file = ".env"

    if not Path(config_file).exists():
        return config

    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    config[key.strip()] = value.strip().strip('"\'')
    except Exception as e:
        log_warning(f"Error reading config file: {e}")

    return config

def check_server_status(base_url):
    """Check if server is running"""
    try:
        response = requests.get(f"{base_url}/health", timeout=5)
        if response.status_code == 200:
            log_success("Server is running and healthy")
            return True
        else:
            log_error(f"Server returned status code: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        log_error(f"Cannot connect to server: {e}")
        return False

def get_api_key():
    """Get API key from config or generate one"""
    config = get_config_values()
    api_key = config.get('VALID_API_KEY')

    if not api_key:
        # Generate a default API key if none exists
        import datetime
        api_key = f"sk-k2think-proxy-{int(datetime.datetime.now().timestamp())}"

    return api_key

def test_with_openai_sdk(base_url, api_key, model, messages, test_type="simple"):
    """Test using OpenAI SDK"""
    if not OPENAI_AVAILABLE:
        log_error("OpenAI SDK not available. Install with: pip install openai")
        return False

    try:
        # Create OpenAI client
        client = OpenAI(
            base_url=f"{base_url}/v1",
            api_key=api_key
        )

        log_info(f"Testing with OpenAI SDK - {test_type.upper()}")

        if test_type == "simple":
            # Simple test
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.7,
                max_tokens=100
            )
            content = response.choices[0].message.content
            token_usage = response.usage

        elif test_type == "streaming":
            # Streaming test
            stream = client.chat.completions.create(
                model=model,
                messages=messages,
                stream=True,
                temperature=0.7,
                max_tokens=100
            )
            content = ""
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    content += chunk.choices[0].delta.content
            token_usage = None

        else:  # function_calling
            # Function calling test
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=[{
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "description": "Get the current weather for a location",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "location": {
                                    "type": "string",
                                    "description": "The city and state, e.g. San Francisco, CA"
                                }
                            },
                            "required": ["location"]
                        }
                    }
                }],
                tool_choice="auto"
            )
            content = response.choices[0].message.content
            token_usage = response.usage

        # Display results
        print()
        print(f"{Colors.GREEN}═════════════════════════════════════════════════════════{Colors.NC}")
        print(f"{Colors.GREEN}📥 RESPONSE RECEIVED (OpenAI SDK){Colors.NC}")
        print(f"{Colors.GREEN}═════════════════════════════════════════════════════════{Colors.NC}")
        print()
        print(f"Model: {model}")
        print(f"Test Type: {test_type}")
        print()

        if token_usage:
            print(f"Token Usage:")
            print(f"  • Prompt tokens: {token_usage.prompt_tokens}")
            print(f"  • Completion tokens: {token_usage.completion_tokens}")
            print(f"  • Total tokens: {token_usage.total_tokens}")
            print()

        print("Content:")
        print("-" * 50)
        print(content)
        print("-" * 50)
        print()

        return True

    except Exception as e:
        log_error(f"OpenAI SDK test failed: {e}")
        return False

def test_with_requests(base_url, api_key, model, messages, test_type="simple"):
    """Test using raw HTTP requests"""
    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

        if test_type == "simple":
            payload = {
                "model": model,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 100
            }

        elif test_type == "streaming":
            payload = {
                "model": model,
                "messages": messages,
                "stream": True,
                "temperature": 0.7,
                "max_tokens": 100
            }

        else:  # function_calling
            payload = {
                "model": model,
                "messages": messages,
                "tools": [{
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "description": "Get the current weather for a location",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "location": {
                                    "type": "string",
                                    "description": "The city and state, e.g. San Francisco, CA"
                                }
                            },
                            "required": ["location"]
                        }
                    }
                }],
                "tool_choice": "auto"
            }

        log_info(f"Testing with HTTP requests - {test_type.upper()}")

        if test_type == "streaming":
            # Handle streaming response
            response = requests.post(
                f"{base_url}/v1/chat/completions",
                headers=headers,
                json=payload,
                stream=True
            )

            if response.status_code != 200:
                log_error(f"HTTP request failed with status {response.status_code}")
                return False

            print()
            print(f"{Colors.GREEN}═════════════════════════════════════════════════════════{Colors.NC}")
            print(f"{Colors.GREEN}📥 STREAMING RESPONSE (HTTP){Colors.NC}")
            print(f"{Colors.GREEN}═════════════════════════════════════════════════════════{Colors.NC}")
            print()
            print("Streaming content:")
            print("-" * 50)

            content = ""
            for line in response.iter_lines():
                line = line.decode('utf-8')
                if line.startswith('data: '):
                    data = line[6:]
                    if data.strip() == '[DONE]':
                        break
                    try:
                        chunk = json.loads(data)
                        if chunk.get('choices') and chunk['choices'][0].get('delta', {}).get('content'):
                            content += chunk['choices'][0]['delta']['content']
                            print(chunk['choices'][0]['delta']['content'], end='', flush=True)
                    except json.JSONDecodeError:
                        pass

            print()
            print("-" * 50)
            print()

        else:
            # Regular response
            response = requests.post(
                f"{base_url}/v1/chat/completions",
                headers=headers,
                json=payload
            )

            if response.status_code != 200:
                log_error(f"HTTP request failed with status {response.status_code}")
                log_error(f"Response: {response.text}")
                return False

            result = response.json()

            print()
            print(f"{Colors.GREEN}═════════════════════════════════════════════════════════{Colors.NC}")
            print(f"{Colors.GREEN}📥 RESPONSE RECEIVED (HTTP){Colors.NC}")
            print(f"{Colors.GREEN}═════════════════════════════════════════════════════════{Colors.NC}")
            print()
            print(f"Model: {model}")
            print(f"Test Type: {test_type}")
            print()

            if 'usage' in result:
                print(f"Token Usage:")
                print(f"  • Prompt tokens: {result['usage']['prompt_tokens']}")
                print(f"  • Completion tokens: {result['usage']['completion_tokens']}")
                print(f"  • Total tokens: {result['usage']['total_tokens']}")
                print()

            print("Content:")
            print("-" * 50)
            print(result['choices'][0]['message']['content'])
            print("-" * 50)
            print()

        return True

    except Exception as e:
        log_error(f"HTTP request test failed: {e}")
        return False

def get_models(base_url, api_key):
    """Get list of available models"""
    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

        response = requests.get(f"{base_url}/v1/models", headers=headers)

        if response.status_code == 200:
            models = response.json()
            print()
            print(f"{Colors.CYAN}═════════════════════════════════════════════════════════{Colors.NC}")
            print(f"{Colors.CYAN}🤖 AVAILABLE MODELS{Colors.NC}")
            print(f"{Colors.CYAN}═════════════════════════════════════════════════════════{Colors.NC}")
            print()

            for model in models.get('data', []):
                print(f"• {model.get('id', 'Unknown')}")
                print(f"  Created: {model.get('created', 'Unknown')}")
                print(f"  Owned by: {model.get('owned_by', 'Unknown')}")
                print()

            return True
        else:
            log_error(f"Failed to get models: {response.status_code}")
            return False

    except Exception as e:
        log_error(f"Error getting models: {e}")
        return False

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='Test K2Think API Proxy with real requests')
    parser.add_argument('--model', default='MBZUAI-IFM/K2-Think',
                        help='Model name to test (default: MBZUAI-IFM/K2-Think)')
    parser.add_argument('--test-type', choices=['simple', 'streaming', 'function_calling'],
                        default='simple', help='Type of test to run')
    parser.add_argument('--message', default='Hello! Can you introduce yourself briefly?',
                        help='Message to send in the request')
    parser.add_argument('--method', choices=['openai', 'http'], default='openai',
                        help='Method to use for testing')
    parser.add_argument('--check-models', action='store_true',
                        help='Check available models')
    parser.add_argument('--base-url', default='http://localhost:7000',
                        help='Base URL of the proxy server')

    args = parser.parse_args()

    print()
    print(f"{Colors.MAGENTA}╔════════════════════════════════════════════════════════╗{Colors.NC}")
    print(f"{Colors.MAGENTA}║               🧪 K2Think API - Test Request 🧪           ║{Colors.NC}")
    print(f"{Colors.MAGENTA}╚════════════════════════════════════════════════════════╝{Colors.NC}")
    print()

    # Get API key
    api_key = get_api_key()
    base_url = args.base_url

    log_info(f"Testing API at: {base_url}")
    log_info(f"Using model: {args.model}")
    log_info(f"Test type: {args.test_type}")
    log_info(f"Method: {args.method}")

    # Check if server is running
    if not check_server_status(base_url):
        log_error("Server is not running. Please start it first:")
        print(f"  python scripts/start.py")
        sys.exit(1)

    # Check models if requested
    if args.check_models:
        get_models(base_url, api_key)
        return

    # Prepare test messages
    messages = [{"role": "user", "content": args.message}]

    # Run test
    success = False
    if args.method == 'openai':
        success = test_with_openai_sdk(base_url, api_key, args.model, messages, args.test_type)
    else:
        success = test_with_requests(base_url, api_key, args.model, messages, args.test_type)

    if success:
        log_success("API test completed successfully!")
        sys.exit(0)
    else:
        log_error("API test failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()