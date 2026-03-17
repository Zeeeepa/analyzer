#!/usr/bin/env python3
"""
Test script to verify K2Think API configuration works as expected
This simulates how Code would interact with the K2Think API endpoint
"""

import os
import sys
import json
import requests

def test_k2think_api():
    """Test the K2Think API with the same configuration Code would use"""

    # Configuration from ~/.code/config.toml
    base_url = "http://172.17.255.77:7000/v1"
    api_key = os.getenv("K2THINK_API_KEY", "sk-k2think")
    model = "k2.test"

    print(f"🧪 Testing K2Think API Configuration")
    print(f"📡 Base URL: {base_url}")
    print(f"🔑 API Key: {api_key[:10]}..." if len(api_key) > 10 else f"🔑 API Key: {api_key}")
    print(f"🤖 Model: {model}")
    print()

    # Test 1: Health check
    print("1. Testing API health endpoint...")
    try:
        response = requests.get(f"{base_url.replace('/v1', '')}/", timeout=10)
        if response.status_code == 200:
            print(f"   ✅ Health check passed: {response.json().get('message', 'OK')}")
        else:
            print(f"   ❌ Health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"   ❌ Health check error: {e}")
        return False

    # Test 2: Chat completions (the main API Code would use)
    print("2. Testing chat completions endpoint...")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": "Hello! Please respond with 'Configuration test successful!'"
            }
        ],
        "max_tokens": 20,
        "temperature": 0.1
    }

    try:
        response = requests.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            message = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            print(f"   ✅ Chat completion successful!")
            print(f"   📝 Response: {message}")
            print(f"   🔢 Tokens used: {data.get('usage', {}).get('total_tokens', 'N/A')}")
            return True
        else:
            print(f"   ❌ Chat completion failed: {response.status_code}")
            print(f"   📄 Error response: {response.text}")
            return False

    except Exception as e:
        print(f"   ❌ Chat completion error: {e}")
        return False

def test_config_file():
    """Test that the config file exists and has the right structure"""
    print("3. Testing configuration file...")

    config_path = os.path.expanduser("~/.code/config.toml")
    if not os.path.exists(config_path):
        print(f"   ❌ Config file not found: {config_path}")
        return False

    print(f"   ✅ Config file exists: {config_path}")

    try:
        with open(config_path, 'r') as f:
            content = f.read()

        required_elements = [
            'model = "k2.test"',
            'model_provider = "k2think"',
            '[model_providers.k2think]',
            'base_url = "http://172.17.255.77:7000/v1"',
            'env_key = "K2THINK_API_KEY"',
            'wire_api = "chat"'
        ]

        missing = []
        for element in required_elements:
            if element not in content:
                missing.append(element)

        if missing:
            print(f"   ❌ Missing configuration elements:")
            for m in missing:
                print(f"      - {m}")
            return False
        else:
            print(f"   ✅ All required configuration elements found")
            return True

    except Exception as e:
        print(f"   ❌ Error reading config file: {e}")
        return False

def main():
    print("🚀 K2Think API Configuration Test for Code")
    print("=" * 50)
    print()

    # Check environment variable
    api_key = os.getenv("K2THINK_API_KEY")
    if not api_key:
        print("⚠️  K2THINK_API_KEY environment variable not set")
        print("   Setting it to default value 'sk-k2think'")
        os.environ["K2THINK_API_KEY"] = "sk-k2think"

    tests = [
        test_config_file,
        test_k2think_api
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"   ❌ Test failed with exception: {e}")
            results.append(False)
        print()

    print("📊 Test Results Summary:")
    print("=" * 30)

    passed = sum(results)
    total = len(results)

    print(f"✅ Passed: {passed}/{total}")
    print(f"❌ Failed: {total - passed}/{total}")

    if all(results):
        print()
        print("🎉 All tests passed! K2Think API is ready to use with Code.")
        print()
        print("📋 Usage instructions:")
        print("   1. Build and run Code from the cloned repository")
        print("   2. It will automatically use the k2.test model")
        print("   3. The model will connect to your K2Think API server")
        return 0
    else:
        print()
        print("❌ Some tests failed. Please check the configuration.")
        return 1

if __name__ == "__main__":
    sys.exit(main())