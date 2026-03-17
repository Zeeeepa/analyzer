#!/bin/bash
# start.sh - Start K2Think API server
# Prerequisite: setup.sh must have been run first

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info() { echo -e "${BLUE}ℹ️  $1${NC}"; }
log_success() { echo -e "${GREEN}✅ $1${NC}"; }
log_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
log_error() { echo -e "${RED}❌ $1${NC}"; }

echo ""
echo "🚀 K2Think API - Start Server"
echo "=============================="
echo ""

# Check if setup was run
if [ ! -d "venv" ] || [ ! -f ".env" ]; then
    log_error "Setup not complete!"
    echo ""
    echo "Please run setup first:"
    echo "   bash scripts/setup.sh"
    echo ""
    exit 1
fi

# Activate virtual environment
log_info "Activating virtual environment..."
source venv/bin/activate
log_success "Virtual environment activated"
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
        log_warning "Server already running with PID $OLD_PID"
        echo ""
        echo "📊 Server Information:"
        echo "   • URL: http://localhost:$PORT"
        echo "   • PID: $OLD_PID"
        echo "   • Logs: tail -f server.log"
        echo ""
        echo "To restart:"
        echo "   1. Stop: kill $OLD_PID"
        echo "   2. Start: bash scripts/start.sh"
        echo ""
        exit 0
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
log_success "Server started with PID $SERVER_PID"
echo ""

# Wait for server to initialize
log_info "Waiting for server to initialize..."
sleep 3

# Check if server is running
if ps -p $SERVER_PID > /dev/null 2>&1; then
    # Try to connect
    MAX_RETRIES=15
    RETRY=0
    while [ $RETRY -lt $MAX_RETRIES ]; do
        if curl -s http://localhost:${PORT}/ > /dev/null 2>&1; then
            log_success "Server is running and responding!"
            echo ""
            echo "╔════════════════════════════════════════════════════════╗"
            echo "║           🎉 SERVER STARTED! 🎉                        ║"
            echo "╚════════════════════════════════════════════════════════╝"
            echo ""
            echo "📊 Server Information:"
            echo "   • URL:  http://localhost:$PORT"
            echo "   • PID:  $SERVER_PID"
            echo "   • Logs: server.log"
            echo ""
            
            # Try to get server info
            SERVER_INFO=$(curl -s http://localhost:${PORT}/ 2>/dev/null || echo "")
            if [ ! -z "$SERVER_INFO" ]; then
                echo "🔌 API Endpoints:"
                echo "$SERVER_INFO" | python3 -m json.tool 2>/dev/null | head -20 || echo "   Base: http://localhost:$PORT/v1"
            fi
            echo ""
            
            echo "📋 Management Commands:"
            echo "   • View logs:   tail -f server.log"
            echo "   • Stop server: kill $SERVER_PID"
            echo "   • Test API:    bash scripts/send_request.sh"
            echo ""
            exit 0
        fi
        RETRY=$((RETRY+1))
        sleep 2
    done
    
    log_warning "Server process running but not responding to HTTP requests"
    echo ""
    echo "📄 Recent logs:"
    tail -20 server.log
    echo ""
    log_info "Server may still be initializing. Check logs with: tail -f server.log"
    exit 0
else
    log_error "Server failed to start!"
    echo ""
    echo "📄 Error logs:"
    tail -30 server.log
    echo ""
    rm data/.server.pid
    exit 1
fi

