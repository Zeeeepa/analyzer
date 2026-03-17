#!/bin/bash
# all.sh - Complete K2Think API workflow orchestrator
# Runs: setup → start → test → display usage examples

set -e
set -u
set -o pipefail

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
echo "🚀 K2Think API - Complete Deployment"
echo "====================================="
echo ""

# Check if we're in the project directory
if [ ! -f "src/k2think_proxy.py" ]; then
    log_error "Not in K2Think project directory!"
    echo ""
    echo "Expected files not found. Make sure you're in the project root."
    echo ""
    echo "Proper usage:"
    echo "   export K2_EMAIL=\"your@email.com\""
    echo "   export K2_PASSWORD=\"yourpassword\""
    echo "   git clone https://github.com/Zeeeepa/k2think2api3"
    echo "   cd k2think2api3"
    echo "   bash scripts/all.sh"
    echo ""
    exit 1
fi

PROJECT_DIR="$(pwd)"
log_success "Working in: $PROJECT_DIR"
echo ""

# Make scripts executable
chmod +x scripts/*.sh 2>/dev/null || true

# ============================================================================
# PHASE 1: SETUP
# ============================================================================
echo "╔════════════════════════════════════════════════════════╗"
echo "║            📦 PHASE 1: ENVIRONMENT SETUP               ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""

if bash scripts/setup.sh; then
    log_success "Phase 1 Complete: Environment is configured"
else
    log_error "Setup failed!"
    exit 1
fi

echo ""
echo ""

# ============================================================================
# PHASE 2: GENERATE TOKENS
# ============================================================================
echo "╔════════════════════════════════════════════════════════╗"
echo "║            🔑 PHASE 2: GENERATE TOKENS                 ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""

log_info "Activating virtual environment..."
source venv/bin/activate

log_info "Generating K2Think tokens..."
if python3 get_tokens.py; then
    log_success "Tokens generated successfully"
    
    # Verify tokens file exists and has content
    if [ -f "data/tokens.txt" ] && [ -s "data/tokens.txt" ]; then
        TOKEN_COUNT=$(grep -v '^#' data/tokens.txt | grep -v '^$' | wc -l)
        log_success "Token pool ready with ${TOKEN_COUNT} token(s)"
    else
        log_error "Token file is empty or missing!"
        exit 1
    fi
else
    log_error "Token generation failed!"
    exit 1
fi

log_success "Phase 2 Complete: Tokens are ready"

echo ""
echo ""

# ============================================================================
# PHASE 3: START SERVER
# ============================================================================
echo "╔════════════════════════════════════════════════════════╗"
echo "║              🚀 PHASE 3: START SERVER                  ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""

if bash scripts/start.sh; then
    log_success "Phase 3 Complete: Server is running"
else
    log_error "Server start failed!"
    exit 1
fi

echo ""
echo ""

# Wait for server to stabilize and load tokens
log_info "Waiting for server to load token pool..."
sleep 5

# Verify tokens loaded by checking admin endpoint
if curl -s "http://localhost:${SERVER_PORT:-7000}/admin/tokens/stats" | grep -q '"total_tokens"'; then
    log_success "Token pool loaded successfully"
else
    log_warning "Token pool may need more time to initialize"
fi

# ============================================================================
# PHASE 4: TEST API
# ============================================================================
echo "╔════════════════════════════════════════════════════════╗"
echo "║               🧪 PHASE 4: TEST API                     ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""

if bash scripts/send_request.sh; then
    log_success "Phase 4 Complete: API tests passed"
else
    log_warning "Some API tests failed (check output above)"
fi

echo ""
echo ""

# ============================================================================
# GET CONFIGURATION INFO
# ============================================================================

# Load environment variables
if [ -f ".env" ]; then
    API_KEY=$(grep VALID_API_KEY .env | cut -d'=' -f2 2>/dev/null || echo "")
    # Load PORT from .env and evaluate it (handles ${SERVER_PORT:-7000} syntax)
    source .env 2>/dev/null || true
    PORT=${PORT:-7000}
else
    PORT=7000
    API_KEY=""
fi

BASE_URL="http://localhost:${PORT}"

# ============================================================================
# CREATE HELPER SCRIPTS
# ============================================================================

log_info "Creating helper scripts..."

# Create Python wrapper script
cat > "${PROJECT_DIR}/python-k2" << 'WRAPPER_EOF'
#!/bin/bash
# Auto-activate venv and run Python with OpenAI configured
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/venv/bin/activate" 2>/dev/null
WRAPPER_EOF

if [ -n "$API_KEY" ]; then
    echo "export OPENAI_API_KEY=\"${API_KEY}\"" >> "${PROJECT_DIR}/python-k2"
fi
echo "export OPENAI_BASE_URL=\"${BASE_URL}/v1\"" >> "${PROJECT_DIR}/python-k2"
echo 'python3 "$@"' >> "${PROJECT_DIR}/python-k2"
chmod +x "${PROJECT_DIR}/python-k2"

# Create activation script
cat > "${PROJECT_DIR}/activate-k2.sh" << ACTIVATE_EOF
#!/bin/bash
# Source this file to activate K2Think environment in current shell
source "${PROJECT_DIR}/venv/bin/activate"
ACTIVATE_EOF

if [ -n "$API_KEY" ]; then
    echo "export OPENAI_API_KEY=\"${API_KEY}\"" >> "${PROJECT_DIR}/activate-k2.sh"
fi
echo "export OPENAI_BASE_URL=\"${BASE_URL}/v1\"" >> "${PROJECT_DIR}/activate-k2.sh"
echo 'echo "✅ K2Think environment activated!"' >> "${PROJECT_DIR}/activate-k2.sh"
echo 'echo "🐍 Python: $(which python3)"' >> "${PROJECT_DIR}/activate-k2.sh"
echo 'echo "🔑 API Key: $OPENAI_API_KEY"' >> "${PROJECT_DIR}/activate-k2.sh"
echo 'echo "🌐 Base URL: $OPENAI_BASE_URL"' >> "${PROJECT_DIR}/activate-k2.sh"

log_success "Helper scripts created"
echo ""
echo ""

# ============================================================================
# DISPLAY USAGE INFORMATION
# ============================================================================

echo "╔════════════════════════════════════════════════════════╗"
echo "║          🎉 ALL PHASES COMPLETE! 🎉                    ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""

echo -e "${CYAN}📡 Server Information:${NC}"
echo "   • Base URL:  ${BASE_URL}/v1"
echo "   • Port:      ${PORT}"
if [ -n "$API_KEY" ]; then
    echo "   • API Key:   ${API_KEY}"
fi
echo ""

# Python usage example
echo -e "${MAGENTA}🐍 Python Usage Example:${NC}"
echo ""
cat << 'EOF'
from openai import OpenAI

client = OpenAI(
EOF
echo "    base_url=\"${BASE_URL}/v1\","
if [ -n "$API_KEY" ]; then
    echo "    api_key=\"${API_KEY}\""
else
    echo "    api_key=\"your-api-key\""
fi
cat << 'EOF'
)

# Simple request
response = client.chat.completions.create(
    model="MBZUAI-IFM/K2-Think",
    messages=[{"role": "user", "content": "Hello!"}]
)
print(response.choices[0].message.content)

# Streaming request
stream = client.chat.completions.create(
    model="MBZUAI-IFM/K2-Think",
    messages=[{"role": "user", "content": "Explain quantum computing"}],
    stream=True
)
for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
EOF
echo ""

# curl example
echo -e "${CYAN}🌐 cURL Test Command:${NC}"
echo ""
if [ -n "$API_KEY" ]; then
    cat << EOF
curl ${BASE_URL}/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ${API_KEY}" \\
  -d '{
    "model": "MBZUAI-IFM/K2-Think",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
EOF
else
    cat << EOF
curl ${BASE_URL}/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer your-api-key" \\
  -d '{
    "model": "MBZUAI-IFM/K2-Think",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
EOF
fi
echo ""
echo ""

# Add prominent venv warning
echo ""
echo -e "${RED}⚠️  IMPORTANT: PYTHON VIRTUAL ENVIRONMENT REQUIRED! ⚠️${NC}"
echo -e "${YELLOW}   Always use ./python-k2 or activate the venv before running Python!${NC}"
echo -e "${YELLOW}   Running 'python' directly will fail with externally-managed-environment${NC}"
echo -e "${YELLOW}   See VENV_USAGE.md for detailed instructions.${NC}"
echo ""
# Environment setup options
echo -e "${CYAN}🔧 Environment Setup Options:${NC}"
echo ""
echo -e "${GREEN}Option 1: Use Python wrapper (Recommended)${NC}"
echo "   ${PROJECT_DIR}/python-k2 your_script.py"
echo "   ${PROJECT_DIR}/python-k2 -c \"from openai import OpenAI; print('Works!')\""
echo ""
echo -e "${GREEN}Option 2: Activate environment in current shell${NC}"
echo "   source ${PROJECT_DIR}/activate-k2.sh"
echo "   python3 your_script.py"
echo ""
echo -e "${GREEN}Option 3: Manual activation${NC}"
echo "   source ${PROJECT_DIR}/venv/bin/activate"
if [ -n "$API_KEY" ]; then
    echo "   export OPENAI_API_KEY=\"${API_KEY}\""
fi
echo "   export OPENAI_BASE_URL=\"${BASE_URL}/v1\""
echo "   python3 your_script.py"
echo ""

# Management commands
echo -e "${YELLOW}📊 Server Management:${NC}"
if [ -f ".server.pid" ]; then
    SERVER_PID=$(cat .server.pid)
    echo "   • View logs:   tail -f ${PROJECT_DIR}/server.log"
    echo "   • Stop server: kill ${SERVER_PID}"
    echo "   • Restart:     bash scripts/start.sh"
    echo "   • Health:      curl ${BASE_URL}/health"
fi
echo ""

# Final status
echo "╔════════════════════════════════════════════════════════╗"
echo "║  🌟 Server is RUNNING and ready for requests! 🌟      ║"
echo "║                                                        ║"
echo "║  Quick start: ${PROJECT_DIR}/python-k2 script.py      ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""

log_success "All systems operational!"
echo ""
