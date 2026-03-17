#!/bin/bash
# send_request.sh - Test K2Think API with various requests
# Sends real test requests and displays responses

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m'

log_info() { echo -e "${BLUE}ℹ️  $1${NC}"; }
log_success() { echo -e "${GREEN}✅ $1${NC}"; }
log_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
log_error() { echo -e "${RED}❌ $1${NC}"; }

echo ""
echo "🧪 K2Think API - Test Request Script"
echo "====================================="
echo ""

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
else
    log_error "Virtual environment not found!"
    echo "Run setup first: bash scripts/setup.sh"
    exit 1
fi

# Load environment variables
if [ -f ".env" ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Prefer SERVER_PORT over .env PORT
PORT=${SERVER_PORT:-${PORT:-7000}}
API_KEY=${VALID_API_KEY:-test-key-123}
BASE_URL="http://localhost:$PORT"

# Check if server is running
log_info "Checking server status..."
if ! curl -s ${BASE_URL}/ > /dev/null 2>&1; then
    log_error "Server not responding on port $PORT"
    echo ""
    echo "Start the server first:"
    echo "   bash scripts/start.sh"
    echo ""
    exit 1
fi
log_success "Server is running on port $PORT"
echo ""

# Create comprehensive test script
log_info "Preparing API tests..."

# Quick demonstration that any API key and any model name work
echo ""
echo "======================================================================"
echo "🎯 QUICK DEMO: Permissive Mode (any key, any model)"
echo "======================================================================"
echo ""
python3 << 'DEMO_EOF'
from openai import OpenAI
import os

port = os.getenv("PORT", "7000")
base_url = f"http://localhost:{port}/v1"

client = OpenAI(
    api_key="sk-any",  # ✅ Any key works!
    base_url=base_url
)

try:
    response = client.chat.completions.create(
        model="gpt-5",  # ✅ Any model name works!
        messages=[{"role": "user", "content": "Say hello in 5 words."}]
    )
    print(f"✅ Response: {response.choices[0].message.content}")
    print(f"📍 Server PORT: {port}")
except Exception as e:
    print(f"❌ Error: {e}")
DEMO_EOF
echo ""
echo "======================================================================"
echo ""

cat > /tmp/test_k2think.py << 'PYEOF'
from openai import OpenAI
import sys
import os

def print_separator(char="=", length=70):
    print(char * length)

def test_simple_request(client):
    """Test 1: Simple greeting"""
    print("\n🔹 TEST 1: Simple Greeting")
    print_separator("-")
    
    try:
        response = client.chat.completions.create(
            model="MBZUAI-IFM/K2-Think",
            messages=[{"role": "user", "content": "Say hello in one sentence."}]
        )
        
        print(f"✅ Status: Success")
        print(f"📝 Response: {response.choices[0].message.content}")
        print(f"🔢 Tokens - Prompt: {response.usage.prompt_tokens}, "
              f"Completion: {response.usage.completion_tokens}, "
              f"Total: {response.usage.total_tokens}")
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_complex_query(client):
    """Test 2: Complex reasoning query"""
    print("\n🔹 TEST 2: Complex Query (Reasoning)")
    print_separator("-")
    
    try:
        response = client.chat.completions.create(
            model="MBZUAI-IFM/K2-Think",
            messages=[{
                "role": "user", 
                "content": "Explain what makes you different from other AI models. Be brief."
            }]
        )
        
        print(f"✅ Status: Success")
        print(f"📝 Response:\n{response.choices[0].message.content}")
        print(f"\n🔢 Tokens - Prompt: {response.usage.prompt_tokens}, "
              f"Completion: {response.usage.completion_tokens}, "
              f"Total: {response.usage.total_tokens}")
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_streaming(client):
    """Test 3: Streaming response"""
    print("\n🔹 TEST 3: Streaming Response")
    print_separator("-")
    
    try:
        print("📝 Streaming output:")
        print("-" * 70)
        
        stream = client.chat.completions.create(
            model="MBZUAI-IFM/K2-Think",
            messages=[{"role": "user", "content": "Count from 1 to 5 with a word between each number."}],
            stream=True
        )
        
        for chunk in stream:
            if chunk.choices[0].delta.content:
                print(chunk.choices[0].delta.content, end="", flush=True)
        
        print("\n" + "-" * 70)
        print("✅ Streaming test completed")
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_model_info(client):
    """Test 4: Model information"""
    print("\n🔹 TEST 4: Model Information Query")
    print_separator("-")
    
    try:
        response = client.chat.completions.create(
            model="MBZUAI-IFM/K2-Think",
            messages=[{"role": "user", "content": "What is your model name and version?"}]
        )
        
        print(f"✅ Status: Success")
        print(f"🤖 Model ID: {response.model}")
        print(f"🆔 Response ID: {response.id}")
        print(f"📝 Response: {response.choices[0].message.content}")
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def main():
    # Get configuration from environment
    base_url = os.getenv("OPENAI_BASE_URL", "http://localhost:7000/v1")
    api_key = os.getenv("OPENAI_API_KEY", "test-key-123")
    
    print_separator("=")
    print("🚀 K2THINK API - COMPREHENSIVE TEST SUITE")
    print_separator("=")
    print(f"\n🔌 Endpoint: {base_url}")
    print(f"🔑 API Key: {api_key[:20]}...")
    
    # Initialize client
    client = OpenAI(
        base_url=base_url,
        api_key=api_key
    )
    
    # Run all tests
    tests = [
        test_simple_request,
        test_complex_query,
        test_streaming,
        test_model_info
    ]
    
    results = []
    for test_func in tests:
        try:
            result = test_func(client)
            results.append(result)
        except Exception as e:
            print(f"\n❌ Test failed with exception: {e}")
            results.append(False)
    
    # Summary
    print("\n" + "=" * 70)
    print("📊 TEST SUMMARY")
    print("=" * 70)
    passed = sum(results)
    total = len(results)
    print(f"\n✅ Passed: {passed}/{total}")
    print(f"❌ Failed: {total - passed}/{total}")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED! API is working perfectly! 🎉")
        return 0
    else:
        print(f"\n⚠️  Some tests failed. Check the output above for details.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
PYEOF

# Set environment variables for the test script
export OPENAI_BASE_URL="${BASE_URL}/v1"
export OPENAI_API_KEY="${API_KEY}"

# Run the comprehensive test suite
log_info "Running comprehensive API test suite..."
echo ""
python3 /tmp/test_k2think.py
TEST_RESULT=$?

# Cleanup
rm -f /tmp/test_k2think.py

echo ""
if [ $TEST_RESULT -eq 0 ]; then
    log_success "All API tests completed successfully!"
else
    log_warning "Some tests failed. Check the output above."
fi
echo ""

exit $TEST_RESULT

