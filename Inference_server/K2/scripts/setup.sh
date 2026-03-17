#!/bin/bash
# setup.sh - Complete environment setup and server startup for K2Think API
# Installs system dependencies, sets up venv, configures credentials, and starts server
# This is a comprehensive all-in-one setup script

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
log_step() { echo -e "${MAGENTA}▶️  $1${NC}"; }

echo ""
echo "╔════════════════════════════════════════════════════════╗"
echo "║     🚀 K2Think API - Complete Setup & Deployment 🚀   ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""
echo "This script will:"
echo "  1. Install system dependencies"
echo "  2. Set up Python virtual environment"
echo "  3. Install Python packages"
echo "  4. Configure credentials and environment"
echo "  5. Start the API server"
echo ""

# ============================================================================
# STEP 1: INSTALL SYSTEM DEPENDENCIES
# ============================================================================
log_step "STEP 1: Installing System Dependencies"
echo ""

# Detect if running as root or with sudo privileges
if [ "$EUID" -ne 0 ]; then 
    SUDO_CMD="sudo"
    log_info "Running with sudo for system package installation"
else
    SUDO_CMD=""
    log_info "Running as root"
fi

# Detect package manager and install dependencies
log_info "Detecting package manager..."
if command -v apt-get &> /dev/null; then
    log_success "Detected apt (Debian/Ubuntu)"
    
    # Check if packages need to be installed
    PACKAGES_TO_INSTALL=()
    
    if ! command -v python3 &> /dev/null; then
        PACKAGES_TO_INSTALL+=("python3")
    fi
    
    if ! dpkg -l | grep -q python3-pip; then
        PACKAGES_TO_INSTALL+=("python3-pip")
    fi
    
    if ! dpkg -l | grep -q python3-venv; then
        PACKAGES_TO_INSTALL+=("python3-venv")
    fi
    
    if ! command -v curl &> /dev/null; then
        PACKAGES_TO_INSTALL+=("curl")
    fi
    
    if [ ${#PACKAGES_TO_INSTALL[@]} -gt 0 ]; then
        log_info "Installing system packages: ${PACKAGES_TO_INSTALL[*]}"
        $SUDO_CMD apt-get update -qq
        $SUDO_CMD apt-get install -y -qq "${PACKAGES_TO_INSTALL[@]}" 2>&1 | grep -v "^Selecting\|^Preparing\|^Unpacking\|^Setting up" || true
        log_success "System packages installed"
    else
        log_success "All required system packages already installed"
    fi
    
elif command -v yum &> /dev/null; then
    log_success "Detected yum (CentOS/RHEL)"
    
    PACKAGES_TO_INSTALL=()
    if ! command -v python3 &> /dev/null; then
        PACKAGES_TO_INSTALL+=("python3")
    fi
    if ! rpm -q python3-pip &> /dev/null; then
        PACKAGES_TO_INSTALL+=("python3-pip")
    fi
    if ! command -v curl &> /dev/null; then
        PACKAGES_TO_INSTALL+=("curl")
    fi
    
    if [ ${#PACKAGES_TO_INSTALL[@]} -gt 0 ]; then
        log_info "Installing system packages: ${PACKAGES_TO_INSTALL[*]}"
        $SUDO_CMD yum install -y -q "${PACKAGES_TO_INSTALL[@]}"
        log_success "System packages installed"
    else
        log_success "All required system packages already installed"
    fi
    
elif command -v dnf &> /dev/null; then
    log_success "Detected dnf (Fedora)"
    
    PACKAGES_TO_INSTALL=()
    if ! command -v python3 &> /dev/null; then
        PACKAGES_TO_INSTALL+=("python3")
    fi
    if ! rpm -q python3-pip &> /dev/null; then
        PACKAGES_TO_INSTALL+=("python3-pip")
    fi
    if ! command -v curl &> /dev/null; then
        PACKAGES_TO_INSTALL+=("curl")
    fi
    
    if [ ${#PACKAGES_TO_INSTALL[@]} -gt 0 ]; then
        log_info "Installing system packages: ${PACKAGES_TO_INSTALL[*]}"
        $SUDO_CMD dnf install -y -q "${PACKAGES_TO_INSTALL[@]}"
        log_success "System packages installed"
    else
        log_success "All required system packages already installed"
    fi
else
    log_warning "Package manager not detected - assuming dependencies are installed"
    log_info "Required: python3, pip, curl"
fi

# Verify Python installation
log_info "Verifying Python installation..."
if ! command -v python3 &> /dev/null; then
    log_error "Python 3 not found! Please install Python 3 manually."
    exit 1
fi
PYTHON_VERSION=$(python3 --version)
log_success "Python 3 is available: $PYTHON_VERSION"
echo ""

# ============================================================================
# STEP 2: PYTHON VIRTUAL ENVIRONMENT SETUP
# ============================================================================
log_step "STEP 2: Setting Up Python Virtual Environment"
echo ""

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    log_info "Creating virtual environment..."
    python3 -m venv venv || {
        log_warning "Failed to create venv, trying with --system-site-packages"
        python3 -m venv --system-site-packages venv
    }
    log_success "Virtual environment created"
else
    log_success "Virtual environment already exists"
fi

# Activate virtual environment
log_info "Activating virtual environment..."
source venv/bin/activate
log_success "Virtual environment activated"
echo ""

# ============================================================================
# STEP 3: INSTALL PYTHON DEPENDENCIES
# ============================================================================
log_step "STEP 3: Installing Python Dependencies"
echo ""

log_info "Upgrading pip..."
pip install -q --upgrade pip
log_success "pip upgraded"

log_info "Installing Python packages from requirements.txt..."
pip install -q -r requirements.txt
log_success "All Python dependencies installed"

# Verify critical packages
log_info "Verifying critical packages..."
python3 -c "import fastapi, uvicorn, httpx, pydantic" 2>/dev/null && log_success "All critical packages verified" || {
    log_error "Failed to verify critical packages"
    exit 1
}
echo ""

# ============================================================================
# STEP 4: CONFIGURE CREDENTIALS AND ENVIRONMENT
# ============================================================================
log_step "STEP 4: Configuring Credentials and Environment"
echo ""

# Create data directory
log_info "Setting up data directory..."
mkdir -p data
log_success "Data directory ready"

# Create empty data/tokens.txt if it doesn't exist
if [ ! -f "data/tokens.txt" ]; then
    log_info "Creating data/tokens.txt file..."
    echo "# Tokens will be auto-generated by the token update service" > data/tokens.txt
    log_success "data/tokens.txt created"
else
    log_success "data/tokens.txt already exists"
fi

# Configure K2Think credentials
if [ ! -f "data/accounts.txt" ]; then
    log_info "Setting up K2Think credentials..."

    # Use provided credentials: developer@pixelium.uk / developer123
    DEFAULT_EMAIL="developer@pixelium.uk"
    DEFAULT_PASSWORD="developer123"

    # Check if environment variables override the defaults
    K2_EMAIL="${K2_EMAIL:-$DEFAULT_EMAIL}"
    K2_PASSWORD="${K2_PASSWORD:-$DEFAULT_PASSWORD}"

    echo "{\"email\": \"$K2_EMAIL\", \"password\": \"$K2_PASSWORD\"}" > data/accounts.txt
    log_success "data/accounts.txt created with credentials: $K2_EMAIL"

    export K2_EMAIL
    export K2_PASSWORD
else
    log_success "data/accounts.txt already exists"
    # Load existing credentials for display
    if command -v jq &> /dev/null; then
        EXISTING_EMAIL=$(jq -r '.email' data/accounts.txt 2>/dev/null || echo "unknown")
        log_info "Using existing credentials: $EXISTING_EMAIL"
    else
        log_info "Using existing data/accounts.txt"
    fi
fi
echo ""

# Create .env file
if [ ! -f ".env" ]; then
    log_info "Creating .env configuration file..."
    TIMESTAMP=$(date +%s)
    
    # Enable auto-update since we have accounts.txt
    AUTO_UPDATE="true"
    
    cat > .env << EOF
# API Authentication
VALID_API_KEY=sk-k2think-proxy-$TIMESTAMP

# Set to true to accept any API key (recommended for local development)
ALLOW_ANY_API_KEY=true

# Server Configuration  
# PORT can be overridden by SERVER_PORT environment variable at runtime
PORT=${SERVER_PORT:-7000}

# Token Management
# Set to true if you have accounts.txt with K2 credentials
ENABLE_TOKEN_AUTO_UPDATE=$AUTO_UPDATE

# Unified token file path
TOKENS_FILE=data/tokens.txt

# Optional: Proxy settings (if needed)
# HTTP_PROXY=http://proxy:port
# HTTPS_PROXY=https://proxy:port
EOF
    log_success ".env file created with token auto-update enabled"
else
    log_success ".env file already exists"
    log_info "To enable token auto-update, ensure ENABLE_TOKEN_AUTO_UPDATE=true in .env"
fi
echo ""

# ============================================================================
# STEP 5: START THE API SERVER
# ============================================================================
log_step "STEP 5: Starting API Server"
echo ""

# Load environment variables
if [ -f ".env" ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Prefer SERVER_PORT over .env PORT, fallback to 7000
PORT=${SERVER_PORT:-${PORT:-7000}}
export PORT

# Check if server is already running
if [ -f "data/.server.pid" ]; then
    OLD_PID=$(cat data/.server.pid)
    if ps -p $OLD_PID > /dev/null 2>&1; then
        log_warning "Server already running with PID $OLD_PID on port $PORT"
        echo ""
        read -p "Would you like to restart the server? (y/N): " -n 1 -r
        echo ""
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            log_info "Stopping existing server..."
            kill $OLD_PID 2>/dev/null || true
            sleep 2
            rm data/.server.pid
            log_success "Existing server stopped"
        else
            echo ""
            echo "╔════════════════════════════════════════════════════════╗"
            echo "║         🎉 SERVER ALREADY RUNNING! 🎉                  ║"
            echo "╚════════════════════════════════════════════════════════╝"
            echo ""
            echo "📊 Server Information:"
            echo "   • URL:  http://localhost:$PORT"
            echo "   • PID:  $OLD_PID"
            echo "   • Logs: tail -f server.log"
            echo ""
            echo "📋 Management Commands:"
            echo "   • View logs:   tail -f server.log"
            echo "   • Stop server: kill $OLD_PID"
            echo "   • Test API:    bash scripts/send_request.sh"
            echo ""
            exit 0
        fi
    else
        log_warning "Removing stale PID file"
        rm data/.server.pid
    fi
fi

# Start the server
log_info "Starting K2Think API server on port $PORT..."
nohup python3 src/k2think_proxy.py > server.log 2>&1 &
SERVER_PID=$!

# Save PID to file
echo $SERVER_PID > data/.server.pid
log_success "Server process started with PID $SERVER_PID"

# Wait for server to initialize
log_info "Waiting for server to initialize..."
sleep 3

# Check if server is running and responding
if ps -p $SERVER_PID > /dev/null 2>&1; then
    # Try to connect
    MAX_RETRIES=15
    RETRY=0
    log_info "Checking server health..."
    
    while [ $RETRY -lt $MAX_RETRIES ]; do
        if curl -s http://localhost:${PORT}/ > /dev/null 2>&1; then
            log_success "Server is running and responding!"
            echo ""
            echo "╔════════════════════════════════════════════════════════╗"
            echo "║         🎉 DEPLOYMENT SUCCESSFUL! 🎉                   ║"
            echo "╚════════════════════════════════════════════════════════╝"
            echo ""
            echo "✅ Configuration Summary:"
            echo "   • System dependencies installed"
            echo "   • Python virtual environment created"
            echo "   • All Python packages installed"
            echo "   • Credentials configured (developer@pixelium.uk)"
            echo "   • Environment file created (.env)"
            echo "   • Token auto-update: ENABLED"
            echo ""
            echo "🌐 Server Information:"
            echo "   • Status: RUNNING ✓"
            echo "   • URL:    http://localhost:$PORT"
            echo "   • PID:    $SERVER_PID"
            echo "   • Logs:   server.log"
            echo ""
            
            # Try to get server info
            SERVER_INFO=$(curl -s http://localhost:${PORT}/ 2>/dev/null || echo "")
            if [ ! -z "$SERVER_INFO" ]; then
                echo "🔌 Available Endpoints:"
                echo "   • Base URL:      http://localhost:$PORT"
                echo "   • API Endpoint:  http://localhost:$PORT/v1/chat/completions"
                echo "   • Health Check:  http://localhost:$PORT/"
            fi
            echo ""
            
            echo "📋 Management Commands:"
            echo "   • View logs:     tail -f server.log"
            echo "   • Stop server:   kill $SERVER_PID"
            echo "   • Restart:       bash scripts/setup.sh (choose restart)"
            echo "   • Test API:      bash scripts/send_request.sh"
            echo ""
            
            echo "🚀 Your K2Think API Proxy is ready to use!"
            echo ""
            exit 0
        fi
        RETRY=$((RETRY+1))
        sleep 2
    done
    
    log_warning "Server process running but not responding to HTTP requests"
    echo ""
    echo "📄 Recent logs:"
    tail -20 server.log 2>/dev/null || echo "No logs available yet"
    echo ""
    log_info "Server may still be initializing. Check logs with: tail -f server.log"
    echo ""
    echo "Server PID: $SERVER_PID (saved to data/.server.pid)"
    exit 0
else
    log_error "Server failed to start!"
    echo ""
    echo "📄 Error logs:"
    tail -30 server.log 2>/dev/null || echo "No logs available"
    echo ""
    rm data/.server.pid 2>/dev/null
    exit 1
fi
