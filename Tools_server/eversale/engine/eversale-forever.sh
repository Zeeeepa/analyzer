#!/bin/bash
#
# Eversale Forever - Auto-restarting wrapper
#
# Usage:
#   ./eversale-forever.sh [args...]
#
# Examples:
#   ./eversale-forever.sh
#   ./eversale-forever.sh "Research Stripe"
#   ./eversale-forever.sh --interactive
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"

exec "$PYTHON" "$SCRIPT_DIR/auto_restart.py" "$@"
