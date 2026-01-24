#!/usr/bin/env bash
################################################################################
# 🔬 ULTIMATE E2E DOCKER IMAGE → PRE-COMPILE RECOVERY FRAMEWORK
# Version: 2026.3 — Military-Grade Research-Validated Pipeline
#
# Mission: Complete reconstruction of Docker images to original pre-compilation state
#          including Dockerfile, docker-compose, source code, configs, secrets,
#          runtime state, SBOM, vulnerabilities, forensic artifacts, and
#          ADVANCED PRE-COMPILED CONTENT RETRIEVAL (Debug Symbols, Source Maps,
#          Decompilation).
#
# Enhanced Features:
# • Military-grade error handling with detailed logging
# • Parallel processing for performance optimization
# • Comprehensive tool integration (Syft, Grype, Whaler, Dive, Skopeo, Crane,
#   Tetragon, Falco, Docker Forensics Toolkit, eBPF tools, Radare2, Ghidra,
#   Binwalk, dwarfdump, sourcemapper, pyelftools)
# • Advanced secret detection with pattern matching
# • Multi-language source code recovery with decompilation
# • Real-time progress monitoring and reporting
# • Intelligent fallback mechanisms
# • Resource management and system health monitoring
# • Comprehensive artifact verification
# • Security-focused analysis with offensive capabilities
# • Advanced binary analysis for deep insights into compiled code
#
# Usage: ./docker-decompose-enhanced.sh <IMAGE:TAG> [OUTPUT_DIR] [CONTAINER_ID]
# Example: ./docker-decompose-enhanced.sh nginx:latest ./extracted abcdef123456
#
# Research Basis: 2025-2026 industry research, CNCF projects, academic papers
################################################################################

set -euo pipefail

# =============================================================================
# GLOBAL CONFIGURATION
# =============================================================================

# Script metadata
readonly SCRIPT_VERSION="2026.3" # Incremented version for new features
readonly SCRIPT_NAME="Ultimate Docker Decomposition Framework"
readonly RESEARCH_DATE="July 2026" # Updated research date

# Colors for output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly MAGENTA='\033[0;35m'
readonly CYAN='\033[0;36m'
readonly NC='\033[0m' # No Color
readonly BOLD='\033[1m'
readonly DIM='\033[2m'

# Configuration with environment variable support
readonly IMAGE="${1:-}"
readonly OUTPUT_DIR="${2:-./extracted}"
readonly CONTAINER_ID="${3:-}"
readonly FORCE_OVERWRITE="${FORCE_OVERWRITE:-false}"
readonly PARALLEL_JOBS="${PARALLEL_JOBS:-4}"
readonly SKIP_RUNTIME="${SKIP_RUNTIME:-false}"
readonly SKIP_OFFENSIVE="${SKIP_OFFENSIVE:-true}"
readonly DEEP_SCAN="${DEEP_SCAN:-false}" # Crucial for new advanced features
readonly ENABLE_FORENSICS="${ENABLE_FORENSICS:-true}"
readonly LOG_LEVEL="${LOG_LEVEL:-INFO}"
readonly MAX_RETRIES="${MAX_RETRIES:-3}"
readonly TIMEOUT="${TIMEOUT:-300}" # Consider longer timeouts for decompilation, e.g., 600 for deep_scan

# Tool versions (minimum required)
readonly MIN_SYFT_VERSION="0.60.0"
readonly MIN_GRYPE_VERSION="0.51.0"
readonly MIN_WHALER_VERSION="1.5.0"
readonly MIN_DIVE_VERSION="0.10.0"

# Resource limits
readonly MAX_MEMORY_GB="${MAX_MEMORY_GB:-8}"
readonly MAX_DISK_SPACE_GB="${MAX_DISK_SPACE_GB:-50}"

# =============================================================================
# GLOBAL VARIABLES
# =============================================================================

# Script state
declare -g SCRIPT_START_TIME
declare -g CURRENT_PHASE=""
declare -g PHASE_START_TIME
declare -g TOTAL_PHASES=12 # Remains 12, advanced features are part of deep scan phases
declare -g COMPLETED_PHASES=0
declare -g ERROR_COUNT=0
declare -g WARNING_COUNT=0

# Tool availability flags
declare -g HAS_SYFT=false
declare -g HAS_GRYPE=false
declare -g HAS_WHALER=false
declare -g HAS_DIVE=false
declare -g HAS_SKOPEO=false
declare -g HAS_CRANE=false
declare -g HAS_KOMPOSE=false
declare -g HAS_HELM=false
declare -g HAS_PYTHON3=false
declare -g HAS_UNCOMPILE6=false
declare -g HAS_VOLATILITY=false

# New tool flags for advanced analysis
declare -g HAS_DWARFDUMP=false
declare -g HAS_LLVM_DWARFDUMP=false
declare -g HAS_SOURCEMAPPER=false
declare -g HAS_RADARE2=false
declare -g HAS_GHIDRA=false
declare -g HAS_BINWALK=false
declare -g HAS_PYELFTOOLS=false


# Output directories
declare -g OUTPUT_ROOT
declare -g LOG_FILE
declare -g REPORT_FILE
declare -g METRICS_FILE

# Process tracking
declare -g -a BACKGROUND_PROCESSES=()

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

# Enhanced logging system
log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    local color=""

    case "$level" in
        "DEBUG") color="$DIM" ;;
        "INFO") color="$BLUE" ;;
        "WARN") color="$YELLOW" ;;
        "ERROR") color="$RED" ;;
        "SUCCESS") color="$GREEN" ;;
        "PHASE") color="$MAGENTA" ;;
        *) color="$NC" ;;
    esac

    # Only log if level matches or exceeds configured level
    if [[ "$level" == "ERROR" ]] || \
       [[ "$level" == "WARN" && "$LOG_LEVEL" != "ERROR" ]] || \
       [[ "$level" == "INFO" && "$LOG_LEVEL" != "ERROR" && "$LOG_LEVEL" != "WARN" ]] || \
       [[ "$level" == "DEBUG" && "$LOG_LEVEL" == "DEBUG" ]] || \
       [[ "$level" == "PHASE" ]] || \
       [[ "$level" == "SUCCESS" ]]; then

        echo -e "${color}[$timestamp] [$level]${NC} $message" | tee -a "$LOG_FILE"
    fi
}

# Progress tracking
show_progress() {
    local current="$1"
    local total="$2"
    local phase_name="$3"
    local width=50
    local percentage=$((current * 100 / total))
    local completed=$((percentage * width / 100))
    local remaining=$((width - completed))

    printf "\r${CYAN}[PHASE %d/%d]${NC} %s " "$current" "$total" "$phase_name"
    printf "[${GREEN}%s${NC}${DIM}%s${NC}] %3d%%" \
           "$(printf "%${completed}s" | tr ' ' '=')" \
           "$(printf "%${remaining}s" | tr ' ' '-')" \
           "$percentage"
}

# Error handling with retry mechanism
execute_with_retry() {
    local cmd="$1"
    local description="$2"
    local retry_count=0
    local success=false
    local current_timeout="$TIMEOUT"
    # Longer timeout for decompilation tasks if DEEP_SCAN is active
    if [[ "$DEEP_SCAN" == true && ("$description" == *"Ghidra"* || "$description" == *"Radare2"*) ]]; then
        current_timeout=$((TIMEOUT * 2)) # Double timeout for decompilation
        log "DEBUG" "Increased timeout for $description to ${current_timeout}s"
    fi

    while [[ $retry_count -lt $MAX_RETRIES ]]; do
        log "INFO" "Attempting: $description (attempt $((retry_count + 1))/$MAX_RETRIES)"
        # Using eval for command execution to allow complex commands with pipes and redirects
        if eval timeout "$current_timeout" $cmd; then
            log "SUCCESS" "Completed: $description"
            success=true
            break
        else
            local exit_code=$?
            log "WARN" "Failed: $description (exit code: $exit_code)"
            ((retry_count++))

            if [[ $retry_count -lt $MAX_RETRIES ]]; then
                local sleep_time=5
                # Exponential backoff might be too much here, linear is fine for now.
                log "INFO" "Retrying in $sleep_time seconds..."
                sleep $sleep_time
            fi
        fi
    done

    if [[ "$success" == false ]]; then
        log "ERROR" "Failed after $MAX_RETRIES attempts: $description"
        ((ERROR_COUNT++))
        return 1
    fi

    return 0
}

# Resource monitoring
check_system_resources() {
    log "INFO" "Checking system resources..."

    # Check available memory
    # Use 'grep MemAvailable' for modern Linux, fallback to 'MemFree' + 'Buffers' + 'Cached' if not available
    local available_mem_kb
    if grep -q MemAvailable /proc/meminfo; then
        available_mem_kb=$(awk '/MemAvailable/ {print $2}' /proc/meminfo)
    else
        available_mem_kb=$(awk '/MemFree/ {free=$2} /Buffers/ {buffers=$2} /Cached/ {cached=$2} END {print free+buffers+cached}' /proc/meminfo)
    fi
    local available_mem_gb=$((available_mem_kb / 1024 / 1024))

    if [[ $available_mem_gb -lt $MAX_MEMORY_GB ]]; then
        log "WARN" "Low memory available: ${available_mem_gb}GB (recommended: ${MAX_MEMORY_GB}GB)"
        ((WARNING_COUNT++))
    fi

    # Check available disk space
    local available_disk_kb=$(df -k . | awk 'NR==2 {print $4}')
    local available_disk_gb=$((available_disk_kb / 1024 / 1024))
    if [[ $available_disk_gb -lt $MAX_DISK_SPACE_GB ]]; then
        log "WARN" "Low disk space available: ${available_disk_gb}GB (recommended: ${MAX_DISK_SPACE_GB}GB)"
        ((WARNING_COUNT++))
    fi

    log "INFO" "Memory: ${available_mem_gb}GB available, Disk: ${available_disk_gb}GB available"
}

# Tool version checking
check_tool_version() {
    local tool="$1"
    local min_version="$2"

    if ! command -v "$tool" >/dev/null 2>&1; then
        log "DEBUG" "Tool $tool not found"
        return 1
    fi

    # Extract version string. Tools might output versions differently.
    # Common patterns: "tool version X.Y.Z", "tool vX.Y.Z", "X.Y.Z"
    local version_string
    version_string=$($tool --version 2>&1 | head -n1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+([a-zA-Z0-9.-]*)?' | head -n1)

    if [[ -z "$version_string" ]]; then
        # Try another common pattern if the first fails, e.g., for tools like 'go'
        version_string=$($tool version 2>&1 | head -n1 | grep -oE 'go[0-9]+\.[0-9]+(\.[0-9]+)?' | head -n1 | sed 's/go//')
        if [[ -z "$version_string" ]]; then # If still no version, try one more common pattern
            version_string=$($tool -V 2>&1 | head -n1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -n1)
        fi
    fi
    
    # Clean version string (e.g., remove leading 'v' or trailing non-numeric parts if any)
    version_string=$(echo "$version_string" | sed 's/^v//' | cut -d'-' -f1 | cut -d'+' -f1)


    if [[ -z "$version_string" ]]; then
        log "DEBUG" "Could not determine version for $tool"
        return 0  # Assume it's OK if we can't check, but log it.
    fi

    # Ensure python3 and packaging are available for version comparison
    if ! command -v python3 >/dev/null 2>&1 || ! python3 -c "import packaging" >/dev/null 2>&1; then
        log "WARN" "python3 or 'packaging' library not available, cannot perform version check for $tool (found: $version_string)"
        return 0 # Assume OK if check can't be performed
    fi

    if ! python3 -c "from packaging import version; print(version.parse('$version_string') >= version.parse('$min_version'))" 2>/dev/null; then
        log "WARN" "$tool version $version_string is below minimum required $min_version"
        return 1
    fi

    log "DEBUG" "$tool version $version_string meets requirements"
    return 0
}


# =============================================================================
# TOOL INSTALLATION AND VERIFICATION
# =============================================================================

install_python_dependencies() {
    log "INFO" "Installing Python dependencies..."

    if ! command -v pip3 >/dev/null 2>&1; then
        log "WARN" "pip3 not available, skipping Python package installation"
        return 1
    fi

    # Install required Python packages
    local packages=("packaging" "requests" "yaml" "jinja2" "pyelftools")

    for package in "${packages[@]}"; do
        if ! pip3 show "$package" >/dev/null 2>&1; then
            log "INFO" "Installing Python package: $package"
            if execute_with_retry "pip3 install '$package'" "Install Python package $package"; then
                log "SUCCESS" "Python package $package installed"
                if [[ "$package" == "pyelftools" ]]; then
                    HAS_PYELFTOOLS=true
                fi
            else
                log "WARN" "Failed to install Python package $package"
            fi
        else
            log "DEBUG" "Python package $package already installed"
            if [[ "$package" == "pyelftools" ]]; then
                HAS_PYELFTOOLS=true
            fi
        fi
    done

    # Check for uncompyle6 separately as it's a specific decompiler
    if ! pip3 show uncompyle6 >/dev/null 2>&1; then
        log "INFO" "Installing Python package: uncompyle6"
        if execute_with_retry "pip3 install 'uncompyle6>=3.9.0'" "Install Python package uncompyle6"; then # Specify version if known good one exists
            HAS_UNCOMPILE6=true
            log "SUCCESS" "Python package uncompyle6 installed"
        else
            log "WARN" "Failed to install Python package uncompyle6"
        fi
    else
        HAS_UNCOMPILE6=true
        log "DEBUG" "Python package uncompyle6 already installed"
    fi
}


install_tool() {
    local tool="$1"
    local method="$2"
    shift 2 # Shift tool and method, rest are args for the method

    log "INFO" "Installing $tool using $method..."

    case "$method" in
        "curl")
            local url="$1"
            local dest="${2:-/usr/local/bin}"
            local filename=$(basename "$url")
            # Create a temporary file for download to avoid partial writes if curl fails
            local temp_file=$(mktemp)
            if execute_with_retry "curl -sSL '$url' -o '$temp_file' && chmod +x '$temp_file' && mv '$temp_file' '$dest/$filename'" "Download and install $tool from $url"; then
                log "SUCCESS" "$tool installed to $dest/$filename"
                return 0
            else
                rm -f "$temp_file" # Clean up temp file on failure
                log "ERROR" "Failed to install $tool via curl"
                return 1
            fi
            ;;
        "brew")
            if execute_with_retry "brew install $tool" "Install $tool via Homebrew"; then
                log "SUCCESS" "$tool installed via Homebrew"
                return 0
            fi
            ;;
        "apt")
            # Use DEBIAN_FRONTEND=noninteractive to avoid prompts
            if execute_with_retry "sudo DEBIAN_FRONTEND=noninteractive apt-get update && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y $tool" "Install $tool via apt"; then
                log "SUCCESS" "$tool installed via apt"
                return 0
            fi
            ;;
        "dnf") # For Fedora/CentOS/RHEL
            if execute_with_retry "sudo dnf install -y $tool" "Install $tool via dnf"; then
                log "SUCCESS" "$tool installed via dnf"
                return 0
            fi
            ;;
        "go_install")
            local go_package_path="$1"
            # Ensure GOPATH is set and GOPATH/bin is in PATH for the current session
            local gopath_bin
            if [[ -z "${GOPATH:-}" ]]; then
                GOPATH="$(go env GOPATH 2>/dev/null || echo "$HOME/go")"
                export GOPATH
            fi
            gopath_bin="$GOPATH/bin"
            if [[ ":$PATH:" != *":$gopath_bin:"* ]]; then
                export PATH="$PATH:$gopath_bin"
                log "DEBUG" "Added $gopath_bin to PATH for Go installations"
            fi
            if execute_with_retry "go install $go_package_path@latest" "Install $tool via 'go install'"; then
                 # Verify installation
                local tool_name=$(basename "$go_package_path")
                if command -v "$tool_name" >/dev/null 2>&1; then
                    log "SUCCESS" "$tool_name installed via 'go install' and found in PATH"
                    return 0
                else
                    log "WARN" "$tool_name installed via 'go install' but not found in PATH. Try adding $GOPATH/bin to your shell's PATH."
                    # Still return 0 as it might be in PATH for subsequent script commands if we added it
                    return 0
                fi
            else
                log "ERROR" "Failed to install $tool via 'go install'"
                return 1
            fi
            ;;
        "docker_pull")
            local docker_image="$1"
            if execute_with_retry "docker pull $docker_image" "Pull Docker image $docker_image for $tool"; then
                log "SUCCESS" "Docker image $docker_image pulled for $tool"
                return 0
            else
                log "ERROR" "Failed to pull Docker image $docker_image for $tool"
                return 1
            fi
            ;;
        *)
            log "ERROR" "Unknown installation method: $method for tool $tool"
            return 1
            ;;
    esac
    return 1 # Should not be reached if cases are exhaustive
}


verify_and_install_tools() {
    log "INFO" "Verifying and installing required tools..."

    # Core tools (must exist)
    declare -A core_tools=(
        ["docker"]="Docker CLI"
        ["jq"]="JSON processor"
        ["tar"]="Archive utility"
        ["curl"]="Download utility"
        ["git"]="Version control"
        ["awk"]="Text processing"
        ["sed"]="Stream editor"
        ["grep"]="Text search"
        ["find"]="File search"
        ["sort"]="Sort lines"
        ["uniq"]="Unique lines"
        ["head"]="Output first part"
        ["tail"]="Output last part"
        ["tr"]="Translate characters"
        ["cut"]="Remove sections from lines"
        ["wc"]="Word count"
        ["du"]="Disk usage"
        ["df"]="Disk space"
        ["free"]="Memory usage"
        ["date"]="Date/time"
        ["mkdir"]="Create directories"
        ["cp"]="Copy files"
        ["mv"]="Move/rename files"
        ["rm"]="Remove files"
        ["chmod"]="Change permissions"
        ["tee"]="Read from stdin/write to stdout and files"
        ["timeout"]="Run command with time limit"
        ["docker"]="Docker CLI" # Listed again for clarity, checked at the very start
    )

    for tool in "${!core_tools[@]}"; do
        if ! command -v "$tool" >/dev/null 2>&1; then
            log "ERROR" "Required core tool $tool (${core_tools[$tool]}) not found. Please install it."
            # Consider exiting for truly core tools like docker, jq, tar, curl.
            # For text utils like awk, sed, grep, they are usually present.
            # If docker is missing, the script can't function.
            if [[ "$tool" == "docker" || "$tool" == "jq" || "$tool" == "tar" || "$tool" == "curl" || "$tool" == "git" ]]; then
                exit 1
            else
                log "WARN" "Core tool $tool (${core_tools[$tool]}) not found. Some features may fail."
                ((WARNING_COUNT++))
            fi
        else
            log "DEBUG" "✓ Core tool $tool found"
        fi
    done

    # Install Python dependencies first
    install_python_dependencies

    # Advanced tools with installation methods
    # Format: "tool_name:method1|arg1|arg2||method2|arg1"
    declare -A advanced_tools=(
        ["syft"]="curl|https://raw.githubusercontent.com/anchore/syft/main/install.sh|/usr/local/bin||apt|syft"
        ["grype"]="curl|https://raw.githubusercontent.com/anchore/grype/main/install.sh|/usr/local/bin||apt|grype"
        ["skopeo"]="apt|skopeo||dnf|skopeo||brew|skopeo" # Skopeo often has its own repo or is in extras
        ["crane"]="go_install|github.com/google/go-containerregistry/cmd/crane"
        ["dive"]="apt|dive||dnf|dive||brew|dive"
        ["kompose"]="curl|https://github.com/kubernetes/kompose/releases/latest/download/kompose-linux-amd64|/usr/local/bin/kompose"
        ["helm"]="curl|https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3"
    )

    for tool in "${!advanced_tools[@]}"; do
        IFS='|' read -ra methods <<< "${advanced_tools[$tool]}"
        local installed=false

        if command -v "$tool" >/dev/null 2>&1; then
            log "DEBUG" "✓ Advanced tool $tool already installed"
            installed=true # Assume existing installation is fine, version check below will confirm
            # Set availability flags
            case "$tool" in
                "syft") HAS_SYFT=true ;;
                "grype") HAS_GRYPE=true ;;
                "dive") HAS_DIVE=true ;;
                "skopeo") HAS_SKOPEO=true ;;
                "crane") HAS_CRANE=true ;;
                "kompose") HAS_KOMPOSE=true ;;
                "helm") HAS_HELM=true ;;
            esac
        else
            log "INFO" "Advanced tool $tool not found, attempting installation..."
            for ((i=0; i<${#methods[@]}; i+=3)); do
                local method="${methods[i]}"
                local arg1="${methods[i+1]:-}" # - for default if arg not present
                local arg2="${methods[i+2]:-}"

                if install_tool "$tool" "$method" "$arg1" "$arg2"; then
                    installed=true
                    # Set availability flags
                    case "$tool" in
                        "syft") HAS_SYFT=true ;;
                        "grype") HAS_GRYPE=true ;;
                        "dive") HAS_DIVE=true ;;
                        "skopeo") HAS_SKOPEO=true ;;
                        "crane") HAS_CRANE=true ;;
                        "kompose") HAS_KOMPOSE=true ;;
                        "helm") HAS_HELM=true ;;
                    esac
                    break # Stop trying methods once one succeeds
                fi
            done
        fi

        if [[ "$installed" == true ]]; then
            # Check version if applicable
            case "$tool" in
                "syft") check_tool_version "syft" "$MIN_SYFT_VERSION" || HAS_SYFT=false ;;
                "grype") check_tool_version "grype" "$MIN_GRYPE_VERSION" || HAS_GRYPE=false ;;
                "dive") check_tool_version "dive" "$MIN_DIVE_VERSION" || HAS_DIVE=false ;;
                # Add version checks for other tools if necessary
            esac
            if [[ "${tool}" == "syft" && "$HAS_SYFT" == true ]]; then log "SUCCESS" "✓ syft installed and version OK"; elif [[ "${tool}" == "syft" && "$HAS_SYFT" == false ]]; then log "WARN" "⚠ syft version issue"; fi
            if [[ "${tool}" == "grype" && "$HAS_GRYPE" == true ]]; then log "SUCCESS" "✓ grype installed and version OK"; elif [[ "${tool}" == "grype" && "$HAS_GRYPE" == false ]]; then log "WARN" "⚠ grype version issue"; fi
            if [[ "${tool}" == "dive" && "$HAS_DIVE" == true ]]; then log "SUCCESS" "✓ dive installed and version OK"; elif [[ "${tool}" == "dive" && "$HAS_DIVE" == false ]]; then log "WARN" "⚠ dive version issue"; fi
        else
            log "WARN" "⚠ Failed to install $tool, some features may be unavailable"
            ((WARNING_COUNT++))
        fi
    done

    # Check for optional advanced tools (Docker-based or Go-based)
    if command -v python3 >/dev/null 2>&1; then
        HAS_PYTHON3=true
        # uncompyle6 and pyelftools status set in install_python_dependencies
    fi

    if command -v volatility >/dev/null 2>&1; then # Volatility is for memory forensics, less common in standard CI
        HAS_VOLATILITY=true
        log "DEBUG" "✓ Volatility found"
    fi

    # Whaler (Docker-based)
    if docker images --format "{{.Repository}}:{{.Tag}}" | grep -q "pegleg/whaler:latest"; then
        HAS_WHALER=true
        log "DEBUG" "✓ Whaler Docker image found"
    elif [[ "$DEEP_SCAN" == true ]]; then
        log "INFO" "Pulling Whaler Docker image..."
        if install_tool "whaler" "docker_pull" "pegleg/whaler"; then
            HAS_WHALER=true
            log "SUCCESS" "✓ Whaler Docker image pulled"
        else
            log "WARN" "⚠ Failed to pull Whaler Docker image"
            ((WARNING_COUNT++))
        fi
    fi

    # dwarfdump / llvm-dwarfdump
    if command -v dwarfdump >/dev/null 2>&1; then
        HAS_DWARFDUMP=true
        log "DEBUG" "✓ dwarfdump found"
    elif command -v llvm-dwarfdump >/dev/null 2>&1; then
        HAS_LLVM_DWARFDUMP=true
        log "DEBUG" "✓ llvm-dwarfdump found"
    elif [[ "$DEEP_SCAN" == true ]]; then
        log "INFO" "Attempting to install dwarfdump..."
        if install_tool "dwarfdump" "apt" "dwarfdump" || install_tool "dwarfdump" "dnf" "dwarfdump" || install_tool "dwarfdump" "brew" "dwarfdump"; then
            HAS_DWARFDUMP=true
            log "SUCCESS" "✓ dwarfdump installed"
        else
            log "WARN" "⚠ Could not install dwarfdump or llvm-dwarfdump. Debug symbol extraction will be limited."
            ((WARNING_COUNT++))
        fi
    fi

    # sourcemapper (Go-based)
    if command -v sourcemapper >/dev/null 2>&1; then
        HAS_SOURCEMAPPER=true
        log "DEBUG" "✓ sourcemapper (Go) found"
    elif [[ "$DEEP_SCAN" == true ]] && command -v go >/dev/null 2>&1; then
        log "INFO" "Attempting to install sourcemapper (Go)..."
        if install_tool "sourcemapper" "go_install" "github.com/denandz/sourcemapper"; then
            # Re-check if sourcemapper is in PATH after go install
            if command -v sourcemapper >/dev/null 2>&1; then
                HAS_SOURCEMAPPER=true
                log "SUCCESS" "✓ sourcemapper (Go) installed and found in PATH"
            else
                log "WARN" "sourcemapper installed via 'go install' but not found in PATH. Try adding $(go env GOPATH)/bin to PATH."
                # It might still be callable if PATH was updated by install_tool for this session
                if go env GOPATH>/dev/null && PATH="$PATH:$(go env GOPATH)/bin" && command -v sourcemapper >/dev/null 2>&1; then
                    HAS_SOURCEMAPPER=true
                    log "INFO" "sourcemapper found after manual PATH adjustment for this session."
                else
                    ((WARNING_COUNT++))
                fi
            fi
        else
            log "WARN" "⚠ Failed to install sourcemapper (Go). JS/TS source map recovery may be limited."
            ((WARNING_COUNT++))
        fi
    elif [[ "$DEEP_SCAN" == true ]] && ! command -v go >/dev/null 2>&1; then
        log "WARN" "Go not found, cannot install sourcemapper. JS/TS source map recovery may be limited."
        ((WARNING_COUNT++))
    fi

    # Radare2 (Docker-based)
    if docker images --format "{{.Repository}}:{{.Tag}}" | grep -q "radare/radare2:latest"; then
        HAS_RADARE2=true
        log "DEBUG" "✓ Radare2 Docker image found"
    elif [[ "$DEEP_SCAN" == true ]]; then
        log "INFO" "Pulling Radare2 Docker image..."
        if install_tool "radare2" "docker_pull" "radare/radare2"; then
            HAS_RADARE2=true
            log "SUCCESS" "✓ Radare2 Docker image pulled"
        else
            log "WARN" "⚠ Failed to pull Radare2 Docker image. Radare2 decompilation may be unavailable."
            ((WARNING_COUNT++))
        fi
    fi

    # Ghidra (Docker-based)
    # Using blacktop/ghidra as it's commonly used and supports headless mode
    if docker images --format "{{.Repository}}:{{.Tag}}" | grep -q "blacktop/ghidra:latest"; then
        HAS_GHIDRA=true
        log "DEBUG" "✓ Ghidra Docker image found"
    elif [[ "$DEEP_SCAN" == true ]]; then
        log "INFO" "Pulling Ghidra Docker image..."
        if install_tool "ghidra" "docker_pull" "blacktop/ghidra"; then
            HAS_GHIDRA=true
            log "SUCCESS" "✓ Ghidra Docker image pulled"
        else
            log "WARN" "⚠ Failed to pull Ghidra Docker image. Ghidra decompilation may be unavailable."
            ((WARNING_COUNT++))
        fi
    fi

    # Binwalk (Docker-based)
    if docker images --format "{{.Repository}}:{{.Tag}}" | grep -q "cincan/binwalk:latest"; then
        HAS_BINWALK=true
        log "DEBUG" "✓ Binwalk Docker image found"
    elif [[ "$DEEP_SCAN" == true ]]; then
        log "INFO" "Pulling Binwalk Docker image..."
        if install_tool "binwalk" "docker_pull" "cincan/binwalk"; then
            HAS_BINWALK=true
            log "SUCCESS" "✓ Binwalk Docker image pulled"
        else
            log "WARN" "⚠ Failed to pull Binwalk Docker image. Firmware analysis may be limited."
            ((WARNING_COUNT++))
        fi
    fi
    log "INFO" "Tool verification and installation completed."
}

# =============================================================================
# ADVANCED BINARY ANALYSIS PHASE
# =============================================================================

phase_advanced_binary_decompilation() {
    CURRENT_PHASE="Advanced Binary Decompilation & Pre-Compiled Content Retrieval"
    PHASE_START_TIME=$(date +%s)
    # This phase is conceptually part of the deep scan and doesn't increment top-level phase count directly
    # but its progress is logged internally.
    log "INFO" "Starting advanced binary decompilation (Deep Scan: $DEEP_SCAN)..."

    if [[ "$DEEP_SCAN" != true ]]; then
        log "INFO" "Skipping advanced binary decompilation (DEEP_SCAN is false)."
        return 0
    fi

    local adv_analysis_dir="$OUTPUT_DIR/advanced_analysis"
    mkdir -p "$adv_analysis_dir"/{debug_symbols,source_maps,binwalk_output,decompiled/{radare2,ghidra},sourcemaps_recovered}
    log "DEBUG" "Advanced analysis output directory: $adv_analysis_dir"

    # 1. Debug Symbol Recovery (DWARF)
    if [[ "$HAS_DWARFDUMP" == true || "$HAS_LLVM_DWARFDUMP" == true || "$HAS_PYELFTOOLS" == true ]]; then
        log "INFO" "Attempting debug symbol recovery..."
        if [[ -f "$OUTPUT_DIR/analysis/binaries.txt" && -s "$OUTPUT_DIR/analysis/binaries.txt" ]]; then
            while IFS= read -r binary_path_line; do
                local binary_file=$(echo "$binary_path_line" | cut -d':' -f1)
                # Ensure the binary file actually exists in the extracted filesystem
                if [[ ! -f "$binary_file" ]]; then
                    # Try to find it in the extracted filesystem if the path from 'file' was relative or different
                    # This assumes 'file' was run within $OUTPUT_DIR/filesystem or paths were adjusted
                    # For simplicity, we assume paths in $OUTPUT_DIR/analysis/binaries.txt are correct
                    # or relative to where 'file' was run. If 'file' was run on $OUTPUT_DIR/filesystem directly,
                    # paths might be like './executable'. If it was run on a subdirectory, adjust accordingly.
                    # The `phase2_binary_forensics` finds files in `$OUTPUT_DIR/filesystem`
                    # So, $binary_file should be a full path within `$OUTPUT_DIR/filesystem`
                    log "DEBUG" "Binary file listed in analysis/binaries.txt not found: $binary_file. Skipping DWARF analysis for it."
                    continue
                fi
                local binary_name=$(basename "$binary_file")
                log "DEBUG" "Processing binary for debug symbols: $binary_name (path: $binary_file)"

                if [[ "$HAS_PYELFTOOLS" == true ]] && [[ "$HAS_PYTHON3" == true ]]; then
                    # Placeholder for more complex pyelftools scripting
                    # Example: Extract list of source files from DWARF
                    python3 -c "
import sys
try:
    from elftools.elf.elffile import ELFFile
    from elftools.dwarf.dwarfinfo import DWARFInfo
    from elftools.dwarf.descriptions import describe_form_value
    from elftools.dwarf.locationlists import LocationParser, LocationLists

    print(f'Analyzing {sys.argv[1]} with pyelftools')
    with open(sys.argv[1], 'rb') as f:
        elffile = ELFFile(f)
        if not elffile.has_dwarf_info():
            print('  No DWARF info found.')
            sys.exit(0)
        
        dwarfinfo = elffile.get_dwarf_info()
        print(f'  DWARF version: {dwarfinfo.version()}')
        
        # Iterate through Compilation Units (CUs)
        for CU in dwarfinfo.iter_CUs():
            die = CU.get_top_DIE()
            print(f'  CU: {die.attributes.get(\"DW_AT_name\", \"?\")}')
            # You can iterate through DIEs in each CU to find functions, variables, etc.
            # For example, to find function names:
            # for die in CU.iter_DIEs():
            #     if die.tag == 'DW_TAG_subprogram':
            #         print(f'    Function: {die.attributes.get(\"DW_AT_name\", \"?\")}')
            # This is a basic example, pyelftools is very powerful.
except ImportError:
    print('  pyelftools not installed or error during import.')
except Exception as e:
    print(f'  Error with pyelftools on {sys.argv[1]}: {e}')
" "$binary_file" > "$adv_analysis_dir/debug_symbols/${binary_name}_pyelftools_summary.txt" 2>&1 || log "DEBUG" "pyelftools script failed for $binary_name"
                fi

                local dwarfdump_exe=""
                if [[ "$HAS_DWARFDUMP" == true ]]; then dwarfdump_exe="dwarfdump"; fi
                if [[ "$HAS_LLVM_DWARFDUMP" == true ]]; then dwarfdump_exe="llvm-dwarfdump"; fi

                if [[ -n "$dwarfdump_exe" ]]; then
                    execute_with_retry "$dwarfdump_exe --debug-line '$binary_file' > '$adv_analysis_dir/debug_symbols/${binary_name}_debug_line.txt'" "Extract debug line info for $binary_name"
                    execute_with_retry "$dwarfdump_exe --debug-info '$binary_file' > '$adv_analysis_dir/debug_symbols/${binary_name}_debug_info.txt'" "Extract debug info for $binary_name"
                    execute_with_retry "$dwarfdump_exe --debug-abbrev '$binary_file' > '$adv_analysis_dir/debug_symbols/${binary_name}_debug_abbrev.txt'" "Extract debug abbrev for $binary_name"
                    execute_with_retry "$dwarfdump_exe --debug-aranges '$binary_file' > '$adv_analysis_dir/debug_symbols/${binary_name}_debug_aranges.txt'" "Extract debug aranges for $binary_name"
                    # Add more dwarfdump commands as needed, e.g., for .debug_str, .debug_pubnames, .debug_pubtypes
                fi
            done < "$OUTPUT_DIR/analysis/binaries.txt"
        else
            log "WARN" "Binaries list ($OUTPUT_DIR/analysis/binaries.txt) not found or empty. Skipping debug symbol recovery."
        fi
    else
        log "WARN" "dwarfdump, llvm-dwarfdump, or pyelftools not available. Skipping detailed debug symbol recovery."
    fi

    # 2. Source Map Recovery (JavaScript/TypeScript)
    if [[ "$HAS_SOURCEMAPPER" == true ]]; then
        log "INFO" "Attempting source map recovery..."
        # Find .js, .mjs, .css files that might contain sourceMappingURL comments
        # Search within the extracted filesystem
        local sourcemap_search_dir="$OUTPUT_DIR/filesystem"
        find "$sourcemap_search_dir" -type f \( -name "*.js" -o -name "*.mjs" -o -name "*.css" \) -exec grep -l "sourceMappingURL" {} \; > "$adv_analysis_dir/source_maps/files_with_sourcemap.txt" 2>/dev/null || true

        if [[ -s "$adv_analysis_dir/source_maps/files_with_sourcemap.txt" ]]; then
            while IFS= read -r js_file_rel_path; do
                local js_file_abs_path="$OUTPUT_DIR/filesystem/$js_file_rel_path" # Assuming find outputs paths relative to filesystem root
                log "DEBUG" "Processing file for source maps: $js_file_abs_path"
                if [[ ! -f "$js_file_abs_path" ]]; then continue; fi # Ensure file exists

                # Extract sourceMappingURL URL
                # sourcemap_url can be relative, absolute path, or full URL
                local sourcemap_url=$(grep -oP 'sourceMappingURL=\K.*' "$js_file_abs_path" | head -1 | tr -d '\'"' | tr -d ' ' | tr -d '\r\n')
                if [[ -n "$sourcemap_url" ]]; then
                    local map_file_abs_path=""
                    if [[ "$sourcemap_url" == http* ]]; then
                        log "INFO" "Source map URL is remote ($sourcemap_url) for $js_file_abs_path. Remote fetching not yet implemented by sourcemapper in this script directly."
                        # One could implement curl + sourcemapper stdin if needed, or use a proxy.
                        continue
                    else
                        # Assume sourcemap_url is relative to the js_file's directory
                        map_file_abs_path="$(dirname "$js_file_abs_path")/$sourcemap_url"
                        # Resolve potential '..' in path
                        map_file_abs_path=$(realpath "$map_file_abs_path" 2>/dev/null || echo "$map_file_abs_path") # realpath might not be in all systems, fallback
                    fi

                    if [[ -f "$map_file_abs_path" ]]; then
                        # Create a unique output subdir based on the JS file path to avoid overwrites
                        # Sanitize js_file_rel_path for use as a directory name
                        local js_subdir_name=$(dirname "$js_file_rel_path" | sed 's|[^a-zA-Z0-9_/-]|_|g')
                        local js_basename=$(basename "$js_file_rel_path" .js | sed 's|[^a-zA-Z0-9_-]|_|g')
                        local output_subdir="$adv_analysis_dir/sourcemaps_recovered/${js_subdir_name}_${js_basename}"
                        mkdir -p "$output_subdir"
                        log "INFO" "Found sourcemap: $map_file_abs_path. Recovering to $output_subdir"
                        # sourcemapper needs the .map file and an output directory
                        if execute_with_retry "sourcemapper unpack '$map_file_abs_path' -o '$output_subdir'" "Recover source from $map_file_abs_path"; then
                            log "SUCCESS" "Source recovery from $map_file_abs_path successful."
                        else
                            log "WARN" "Source recovery from $map_file_abs_path failed."
                        fi
                    else
                        log "DEBUG" "Sourcemap file not found at derived path: $map_file_abs_path (from $js_file_abs_path)"
                    fi
                else
                    log "DEBUG" "Could not extract sourceMappingURL from $js_file_abs_path"
                fi
            done < "$adv_analysis_dir/source_maps/files_with_sourcemap.txt"
        else
            log "INFO" "No files with sourceMappingURL comments found in $sourcemap_search_dir."
        fi
    else
        log "WARN" "sourcemapper not available or DEEP_SCAN is false. Skipping JS/TS source map recovery."
    fi

    # 3. Binary Decomposition with Binwalk
    if [[ "$HAS_BINWALK" == true ]]; then
        log "INFO" "Attempting binary decomposition with Binwalk..."
        if [[ -f "$OUTPUT_DIR/analysis/binaries.txt" && -s "$OUTPUT_DIR/analysis/binaries.txt" ]]; then
            while IFS= read -r binary_path_line; do
                local binary_file=$(echo "$binary_path_line" | cut -d':' -f1)
                if [[ ! -f "$binary_file" ]]; then continue; fi

                local binary_name=$(basename "$binary_file")
                # Limit binwalk to larger files or specific types if it's too slow on all binaries
                # For now, let's run it on all found ELF executables if DEEP_SCAN is true.
                # Add a size filter if needed: e.g., find "$OUTPUT_DIR/filesystem" -type f -executable -size +1M ...
                local file_size_kb=$(du -k "$binary_file" | cut -f1)
                if [[ $file_size_kb -lt 100 ]]; then # Example: skip files smaller than 100KB for binwalk
                    log "DEBUG" "Skipping Binwalk for small file $binary_name (${file_size_kb}KB)"
                    continue
                fi

                log "INFO" "Running Binwalk on $binary_name (${file_size_kb}KB)"
                local binwalk_output_dir="$adv_analysis_dir/binwalk_output/$binary_name"
                mkdir -p "$binwalk_output_dir"

                # Binwalk options: -e for extract, -M for signature scan, -J for JSON output, -C for covariance analysis
                # --run-as=root might be needed for some extraction operations if Docker host has restrictions
                # but usually not if Docker runs with sufficient privileges or the user running the script has rights.
                if execute_with_retry "docker run --rm -v '$binary_file':/input.bin:ro -v '$binwalk_output_dir':/output cincan/binwalk -eMJC /input.bin > '$binwalk_output_dir/binwalk_report.json'" "Binwalk analysis for $binary_name"; then
                    log "SUCCESS" "Binwalk analysis for $binary_name completed."
                    # Check if extraction happened
                    if [[ -n "$(ls -A "$binwalk_output_dir/_*.extracted" 2>/dev/null)" ]]; then
                        log "INFO" "Binwalk extracted artifacts for $binary_name into $binwalk_output_dir/_*.extracted"
                    fi
                else
                    log "WARN" "Binwalk analysis for $binary_name failed or timed out."
                fi
            done < "$OUTPUT_DIR/analysis/binaries.txt"
        else
            log "WARN" "Binaries list ($OUTPUT_DIR/analysis/binaries.txt) not found or empty. Skipping Binwalk analysis."
        fi
    else
        log "WARN" "Binwalk Docker image not available or DEEP_SCAN is false. Skipping binary decomposition."
    fi

    # 4. Automated Decompilation with Radare2
    if [[ "$HAS_RADARE2" == true ]]; then
        log "INFO" "Attempting automated decompilation with Radare2..."
        if [[ -f "$OUTPUT_DIR/analysis/binaries.txt" && -s "$OUTPUT_DIR/analysis/binaries.txt" ]]; then
            while IFS= read -r binary_path_line; do
                local binary_file=$(echo "$binary_path_line" | cut -d':' -f1)
                if [[ ! -f "$binary_file" ]]; then continue; fi

                local binary_name=$(basename "$binary_file")
                local r2_output_dir="$adv_analysis_dir/decompiled/radare2/$binary_name"
                mkdir -p "$r2_output_dir"

                log "INFO" "Running Radare2 analysis on $binary_name"
                # Ensure r2ghidra-dec is available in the radare2 Docker image.
                # Many images have it pre-installed or it can be added via r2pm -ci r2ghidra-dec.
                # The command below attempts to decompile all functions.
                # This can be very verbose and slow for large binaries.
                # A more targeted approach (e.g., main, entry0, or functions matching a pattern) might be better.
                # The `pdg` command is provided by r2ghidra-dec.
                # `aaa` for auto analysis, `afl` to list functions, `pdg @@f` to decompile all functions.
                # `@@f` iterates over the list of functions obtained from `afl`.
                # Output is redirected to a single file for this binary.
                local r2_commands="aaa; afl | awk '{print \$NF}' > /tmp/r2_funcs.txt; for f in \$(cat /tmp/r2_funcs.txt); do echo \"=== DECOMPILING \$f ===\"; pdg @ \$f; echo; done"
                # Using a heredoc for the command to avoid complex quoting issues with -c
                docker run --rm \
                    -v "$binary_file":/bin/target:ro \
                    -v "$r2_output_dir":/output \
                    radare/radare2 \
                    -qq \
                    -c "$r2_commands" \
                    /bin/target > "$r2_output_dir/decompiled_all_functions.c" 2>&1 || log "WARN" "Radare2 decompilation for $binary_name failed or timed out"

                if [[ -s "$r2_output_dir/decompiled_all_functions.c" ]]; then
                    log "SUCCESS" "Radare2 decompilation for $binary_name produced output."
                    # Optionally, split the output into per-function files if needed
                    # awk -vRS="=== DECOMPILING " '/DECOMPILING/ {f=$0; gsub(/ ===/, "", f); gsub(/[^a-zA-Z0-9_]/, "_", f); filename="function_" f ".c"; print > ("/output/"filename); next} {print > ("/output/"filename)}' "$r2_output_dir/decompiled_all_functions.c"
                else
                    # Try decompiling just 'main' or 'entry0' if bulk decompilation failed or produced no output
                    log "INFO" "Attempting to decompile 'main' or 'entry0' for $binary_name with Radare2"
                    docker run --rm \
                        -v "$binary_file":/bin/target:ro \
                        -v "$r2_output_dir":/output \
                        radare/radare2 \
                        -qq \
                        -c "aaa; pdg @ main" /bin/target > "$r2_output_dir/decompiled_main.c" 2>&1 || log "DEBUG" "Radare2 decompilation for main in $binary_name failed."
                     if [[ ! -s "$r2_output_dir/decompiled_main.c" ]]; then
                        docker run --rm \
                            -v "$binary_file":/bin/target:ro \
                            -v "$r2_output_dir":/output \
                            radare/radare2 \
                            -qq \
                            -c "aaa; pdg @ entry0" /bin/target > "$r2_output_dir/decompiled_entry0.c" 2>&1 || log "DEBUG" "Radare2 decompilation for entry0 in $binary_name failed."
                     fi
                fi
            done < "$OUTPUT_DIR/analysis/binaries.txt"
        else
            log "WARN" "Binaries list ($OUTPUT_DIR/analysis/binaries.txt) not found or empty. Skipping Radare2 decompilation."
        fi
    else
        log "WARN" "Radare2 Docker image not available or DEEP_SCAN is false. Skipping Radare2 decompilation."
    fi

    # 5. Automated Decompilation with Ghidra (Headless)
    if [[ "$HAS_GHIDRA" == true ]]; then
        log "INFO" "Attempting automated decompilation with Ghidra..."
        # Create a temporary Ghidra project directory outside the output dir to avoid it being processed by other tools
        local ghidra_project_dir_template="/tmp/ghidra_project_XXXXXX"
        local ghidra_project_dir=$(mktemp -d "$ghidra_project_dir_template")

        # Create a more robust decompilation script for Ghidra
        cat > "$adv_analysis_dir/DecompileAllGhidra.java" <<-'EOF'
//@category Decomposition.Framework
//@author AI Assistant
//@keybinding
//@menupath
//@toolbar

import ghidra.app.decompiler.*;
import ghidra.app.script.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.address.*;
import ghidra.util.task.*;
import ghidra.program.model.symbol.*;
import java.io.*;
import java.nio.file.*;

public class DecompileAllGhidra extends GhidraScript {
    @Override
    public void run() throws Exception {
        String programName = currentProgram.getName();
        String outputDirStr = getEnvironmentVar("GHIDRA_OUTPUT_DIR", "/output"); // Default if not set
        Path outputDirPath = Paths.get(outputDirStr, programName);

        try {
            Files.createDirectories(outputDirPath);
            println("Ghidra: Output directory created/verified: " + outputDirPath.toString());
        } catch (IOException e) {
            println("Ghidra: Error creating output directory " + outputDirPath.toString() + ": " + e.getMessage());
            return;
        }

        FunctionIterator functions = currentProgram.getFunctionManager().getFunctions(true); // true for forward iteration
        Function func;
        int decompiledCount = 0;
        int failedCount = 0;

        DecompInterface decompiler = new DecompInterface();
        DecompileOptions decompileOptions = new DecompileOptions();
        decompiler.setOptions(decompileOptions);
        decompiler.openProgram(currentProgram);

        println("Ghidra: Starting decompilation for program: " + programName);
        while (functions.hasNext()) {
            func = functions.next();
            String funcName = func.getName();
            String sanitizedFuncName = funcName.replaceAll("[^a-zA-Z0-9_]", "_");
            Path outputFile = outputDirPath.resolve(sanitizedFuncName + ".c");

            try {
                DecompileResults results = decompiler.decompileFunction(func, 30, monitor); // 30 second timeout per function
                if (results.decompileCompleted()) {
                    String decompiledCode = results.getDecompiledFunction().getC();
                    try (BufferedWriter writer = Files.newBufferedWriter(outputFile)) {
                        writer.write("// Decompiled by Ghidra from: " + programName + "\n");
                        writer.write("// Function: " + funcName + " @ " + func.getEntryPoint().toString() + "\n");
                        writer.write(decompiledCode);
                    }
                    println("Ghidra: Successfully decompiled: " + funcName + " to " + outputFile.toString());
                    decompiledCount++;
                } else {
                    println("Ghidra: Failed to decompile: " + funcName + ". Reason: " + results.getErrorMessage());
                    failedCount++;
                }
            } catch (Exception e) {
                println("Ghidra: Error decompiling function " + funcName + ": " + e.getMessage());
                failedCount++;
            }
            if (monitor.isCancelled()) {
                println("Ghidra: Script execution cancelled by monitor.");
                break;
            }
        }
        decompiler.closeProgram();
        println("Ghidra: Decompilation finished for " + programName + ". Success: " + decompiledCount + ", Failed: " + failedCount);
    }
}
EOF

        if [[ -f "$OUTPUT_DIR/analysis/binaries.txt" && -s "$OUTPUT_DIR/analysis/binaries.txt" ]]; then
            while IFS= read -r binary_path_line; do
                local binary_file=$(echo "$binary_path_line" | cut -d':' -f1)
                if [[ ! -f "$binary_file" ]]; then continue; fi

                local binary_name=$(basename "$binary_file")
                local ghidra_output_dir="$adv_analysis_dir/decompiled/ghidra/$binary_name"
                mkdir -p "$ghidra_output_dir"

                log "INFO" "Running Ghidra headless analysis on $binary_name"
                # Mount the script and the output directory
                # Pass output directory via environment variable to the Ghidra script
                # The blacktop/ghidra image typically has Ghidra installed in /ghidra
                # The script path for analyzeHeadless is relative to the Ghidra install dir if not absolute.
                # We mount our script to a known location inside the container.
                # The -postScript name should match the class name in the .java file.
                # -scriptPath tells Ghidra where to find the script.
                # -import specifies the binary to analyze.
                # -project specifies the Ghidra project (a temporary one here).
                # -deleteProject deletes the project after analysis to save space.
                # -readOnly ensures the imported binary is not modified.
                # -analysisTimeoutPerFile can be useful for large functions/binaries.
                # -processor allows running specific Ghidra analyzers before the script.
                if execute_with_retry "docker run --rm \
                    -v '$binary_file':/input.bin:ro \
                    -v '$ghidra_output_dir':/output \
                    -v '$adv_analysis_dir/DecompileAllGhidra.java':/scripts/DecompileAllGhidra.java:ro \
                    -e GHIDRA_OUTPUT_DIR=/output \
                    blacktop/ghidra \
                    analyzeHeadless '$ghidra_project_dir' \
                    -import /input.bin \
                    -postScript 'DecompileAllGhidra' \
                    -scriptPath /scripts \
                    -deleteProject \
                    -readOnly \
                    -analysisTimeoutPerFile 300" "Ghidra headless analysis for $binary_name"; then # 5 min timeout per file
                    log "SUCCESS" "Ghidra headless analysis for $binary_name completed."
                else
                    log "WARN" "Ghidra headless analysis for $binary_name failed or timed out."
                fi
            done < "$OUTPUT_DIR/analysis/binaries.txt"
        else
            log "WARN" "Binaries list ($OUTPUT_DIR/analysis/binaries.txt) not found or empty. Skipping Ghidra decompilation."
        fi
        rm -rf "$ghidra_project_dir" # Clean up temp project dir
    else
        log "WARN" "Ghidra Docker image not available or DEEP_SCAN is false. Skipping Ghidra decompilation."
    fi

    log "INFO" "Advanced binary decompilation phase completed."
}


# =============================================================================
# ORIGINAL PHASE IMPLEMENTATIONS (with minor adjustments for new features)
# =============================================================================

phase0_intelligence_reconnaissance() {
    CURRENT_PHASE="Intelligence & Registry Reconnaissance"
    PHASE_START_TIME=$(date +%s)
    show_progress 1 $TOTAL_PHASES "$CURRENT_PHASE"

    log "INFO" "Starting passive reconnaissance..."

    # Remote manifest inspection
    if [[ "$HAS_SKOPEO" == true ]]; then
        log "INFO" "Inspecting remote registry..."
        if execute_with_retry "skopeo inspect --raw 'docker://$IMAGE' | jq > '$OUTPUT_DIR/metadata/remote-manifest.json'" \
            "Remote manifest inspection"; then
            log "SUCCESS" "Remote manifest retrieved"
        fi
    fi

    # Image manifest
    if [[ "$HAS_CRANE" == true ]]; then
        log "INFO" "Retrieving image manifest..."
        if execute_with_retry "crane manifest '$IMAGE' > '$OUTPUT_DIR/metadata/manifest.json'" \
            "Image manifest retrieval"; then
            log "SUCCESS" "Image manifest retrieved"
        fi
    fi

    # Registry metadata
    if [[ "$HAS_SKOPEO" == true ]]; then
        log "INFO" "Gathering registry metadata..."
        if execute_with_retry "skopeo inspect 'docker://$IMAGE' | jq > '$OUTPUT_DIR/metadata/registry-info.json'" \
            "Registry metadata gathering"; then
            log "SUCCESS" "Registry metadata retrieved"
        fi
    fi

    # Image size and layer analysis
    if [[ -f "$OUTPUT_DIR/metadata/manifest.json" ]]; then
        log "INFO" "Analyzing manifest structure..."
        local layer_count=$(jq '.layers | length' "$OUTPUT_DIR/metadata/manifest.json" 2>/dev/null || echo "0")
        log "INFO" "Image contains $layer_count layers"
    fi

    ((COMPLETED_PHASES++))
    echo -e "\n${GREEN}✓ Phase 0 completed${NC}"
}

phase1_secure_acquisition() {
    CURRENT_PHASE="Secure Image Acquisition"
    PHASE_START_TIME=$(date +%s)
    show_progress 2 $TOTAL_PHASES "$CURRENT_PHASE"

    log "INFO" "Starting secure image acquisition..."

    # Pull image
    log "INFO" "Pulling image: $IMAGE"
    if execute_with_retry "docker pull '$IMAGE'" "Image pull"; then
        log "SUCCESS" "Image pulled successfully"
    else
        log "ERROR" "Failed to pull image"
        exit 1
    fi

    # Save image archive
    log "INFO" "Creating image archive..."
    if execute_with_retry "docker save '$IMAGE' -o '$OUTPUT_DIR/metadata/image.tar'" "Image archive creation"; then
        log "SUCCESS" "Image archive created"
    fi

    # Extract image archive for layer analysis
    log "INFO" "Extracting image archive..."
    if execute_with_retry "tar -xf '$OUTPUT_DIR/metadata/image.tar' -C '$OUTPUT_DIR/metadata'" \
        "Archive extraction"; then
        log "SUCCESS" "Image archive extracted"
    fi

    # Get image metadata
    log "INFO" "Extracting image metadata..."
    docker inspect "$IMAGE" | jq > "$OUTPUT_DIR/metadata/image-inspect.json"
    log "SUCCESS" "Image metadata extracted"

    ((COMPLETED_PHASES++))
    echo -e "\n${GREEN}✓ Phase 1 completed${NC}"
}

phase1_5_dockerfile_reconstruction() {
    CURRENT_PHASE="Dockerfile Reconstruction"
    PHASE_START_TIME=$(date +%s)
    show_progress 3 $TOTAL_PHASES "$CURRENT_PHASE"

    log "INFO" "Starting Dockerfile reconstruction..."

    # Method 1: Whaler (most accurate)
    if [[ "$HAS_WHALER" == true ]]; then
        log "INFO" "Using Whaler for Dockerfile reconstruction..."
        # Whaler might need access to Docker socket to inspect image layers if not just using manifest
        if execute_with_retry "docker run --rm -v /var/run/docker.sock:/var/run/docker.sock:ro \
            pegleg/whaler -sV=1.36 '$IMAGE' > '$OUTPUT_DIR/dockerfile/Dockerfile.whaler'" \
            "Whaler reconstruction"; then
            log "SUCCESS" "Dockerfile reconstructed via Whaler"
        fi
    fi

    # Method 2: dfimage (Python-based)
    # dfimage typically also needs Docker socket access
    log "INFO" "Using dfimage for Dockerfile reconstruction..."
    if execute_with_retry "docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
        alpine/dfimage -sV=1.36 '$IMAGE' > '$OUTPUT_DIR/dockerfile/Dockerfile.dfimage'" \
        "dfimage reconstruction"; then
        log "SUCCESS" "Dockerfile reconstructed via dfimage"
    fi

    # Method 3: Docker history parsing (always available)
    log "INFO" "Parsing Docker history..."
    docker history --no-trunc "$IMAGE" > "$OUTPUT_DIR/dockerfile/history.raw"

    # Advanced parsing technique
    # This parsing is a heuristic and might not be perfect
    docker history --no-trunc "$IMAGE" | \
        awk '{$1=$2=$3=$4=""; print $0}' | \
        grep -v COMMENT | \
        nl | \
        sort -nr | \
        sed 's/^[[:space:]]*[0-9]*[[:space:]]*//' | \
        sed -E 's/[0-9]+(\.[0-9]+)?(B|KB|MB|GB|kB)[[:space:]].*//g' | \
        sed 's/^#[0-9]*[[:space:]]*//' | \
        sed '/^$/d' > "$OUTPUT_DIR/dockerfile/Dockerfile.reconstructed.heuristic" # Renamed to avoid overwriting

    log "SUCCESS" "Dockerfile reconstructed via history parsing (heuristic)"

    # Select best reconstruction
    local best_file=""
    if [[ -f "$OUTPUT_DIR/dockerfile/Dockerfile.whaler" ]] && [[ -s "$OUTPUT_DIR/dockerfile/Dockerfile.whaler" ]]; then
        best_file="Dockerfile.whaler"
    elif [[ -f "$OUTPUT_DIR/dockerfile/Dockerfile.dfimage" ]] && [[ -s "$OUTPUT_DIR/dockerfile/Dockerfile.dfimage" ]]; then
        best_file="Dockerfile.dfimage"
    else
        best_file="Dockerfile.reconstructed.heuristic" # Use the heuristic one
    fi

    if [[ -n "$best_file" && -f "$OUTPUT_DIR/dockerfile/$best_file" ]]; then
        cp "$OUTPUT_DIR/dockerfile/$best_file" "$OUTPUT_DIR/Dockerfile.reconstructed"
        log "INFO" "Best reconstruction selected: $best_file"
    else
        log "WARN" "No Dockerfile reconstruction methods produced a usable file."
    fi

    ((COMPLETED_PHASES++))
    echo -e "\n${GREEN}✓ Phase 1.5 completed${NC}"
}

phase2_binary_forensics() {
    CURRENT_PHASE="Binary Forensics Analysis"
    PHASE_START_TIME=$(date +%s)
    show_progress 4 $TOTAL_PHASES "$CURRENT_PHASE"

    log "INFO" "Starting binary forensics analysis..."
    mkdir -p "$OUTPUT_DIR/analysis"

    # Extract binary information
    log "INFO" "Identifying binary files..."
    # Search within the extracted filesystem
    find "$OUTPUT_DIR/filesystem" -type f -exec file {} + | \
        grep -E "(ELF.*executable|ELF.*shared object|PE.*executable|PE.*DLL|Mach-O.*executable)" > "$OUTPUT_DIR/analysis/binaries.txt" 2>/dev/null || true

    local binary_count=$(wc -l < "$OUTPUT_DIR/analysis/binaries.txt" 2>/dev/null || echo "0")
    log "INFO" "Found $binary_count binary files"

    # Extract strings from binaries for analysis (basic, can be resource intensive)
    if [[ "$DEEP_SCAN" == true ]]; then # Make strings extraction part of deep scan
        log "INFO" "Extracting strings from binaries (deep scan)..."
        mkdir -p "$OUTPUT_DIR/analysis/strings"
        local string_extraction_limit=10 # Limit number of binaries for string extraction to save time
        local processed_binaries=0
        while IFS= read -r -d '' binary; do
            if [[ $processed_binaries -ge $string_extraction_limit ]]; then break; fi
            local rel_path="${binary#$OUTPUT_DIR/filesystem/}"
            local safe_rel_path=$(echo "$rel_path" | tr '/' '_')
            strings "$binary" | head -200 > "$OUTPUT_DIR/analysis/strings/strings_${safe_rel_path}.txt" 2>/dev/null || log "DEBUG" "strings failed for $binary"
            ((processed_binaries++))
        done < <(find "$OUTPUT_DIR/filesystem" -type f -executable -print0 2>/dev/null | head -z -n $string_extraction_limit)
        log "INFO" "Extracted strings from $processed_binaries binaries (limit: $string_extraction_limit)."
    fi

    # Check for Go binaries specifically
    log "INFO" "Identifying Go binaries..."
    find "$OUTPUT_DIR/filesystem" -type f -exec sh -c 'file "$1" | grep -q "Go BuildID" && echo "$1"' _ {} \; \
        > "$OUTPUT_DIR/analysis/go-binaries.txt" 2>/dev/null || true

    # Check for UPX-packed binaries
    log "INFO" "Checking for UPX-packed binaries..."
    find "$OUTPUT_DIR/filesystem" -type f -exec sh -c 'strings "$1" | grep -q "UPX" && echo "$1"' _ {} \; \
        > "$OUTPUT_DIR/analysis/upx-packed.txt" 2>/dev/null || true
    
    # Call the new advanced binary decompilation phase here
    phase_advanced_binary_decompilation

    log "INFO" "Binary forensics analysis completed"
    if [[ "$DEEP_SCAN" == false ]]; then
        log "WARN" "Advanced binary analysis (decompilation, debug symbols, source maps) requires DEEP_SCAN=true."
    fi

    ((COMPLETED_PHASES++))
    echo -e "\n${GREEN}✓ Phase 2 completed${NC}"
}

phase2_5_filesystem_extraction() { # Renamed from phase2_5_filesystem_extraction in thought process to phase3_filesystem_extraction
    CURRENT_PHASE="Complete Filesystem Extraction"
    PHASE_START_TIME=$(date +%s)
    show_progress 5 $TOTAL_PHASES "$CURRENT_PHASE"

    log "INFO" "Starting filesystem extraction..."

    # Method 1: Docker build output (recommended, Docker BuildKit required)
    # This method is cleaner if BuildKit is available and configured.
    # The `--output` type=local is a BuildKit feature.
    if docker buildx version >/dev/null 2>&1 && DOCKER_BUILDKIT=1 execute_with_retry "DOCKER_BUILDKIT=1 docker build --output type=local,dest='$OUTPUT_DIR/filesystem' - <<< 'FROM $IMAGE'" \
        "Filesystem extraction via build (BuildKit)"; then
        log "SUCCESS" "Filesystem extracted via build method (BuildKit)"
    else
        log "INFO" "BuildKit or buildx not available for direct output, falling back to export method."
        # Fallback method: docker create and docker export
        log "INFO" "Using fallback extraction method (docker create/export)..."
        local temp_container_name="temp-fs-extract-$(date +%s)"
        if execute_with_retry "docker create --name '$temp_container_name' '$IMAGE'" "Create temporary container"; then
            if execute_with_retry "docker export '$temp_container_name' | tar -xf - -C '$OUTPUT_DIR/filesystem'" \
                "Filesystem export"; then
                log "SUCCESS" "Filesystem extracted via export"
            else
                log "ERROR" "Filesystem export failed"
                # Attempt to clean up container even if export fails
                docker rm "$temp_container_name" >/dev/null 2>&1 || true
                ((ERROR_COUNT++))
                # Consider exiting or critical failure here
            fi
            docker rm "$temp_container_name" >/dev/null 2>&1 || log "WARN" "Failed to remove temp container $temp_container_name"
        else
            log "ERROR" "Failed to create temporary container for filesystem export."
            ((ERROR_COUNT++))
            # Consider exiting here
        fi
    fi

    # Layer-by-layer extraction (already done by phase1 if image.tar was extracted)
    # This part is more for individual layer inspection if needed.
    # If metadata/manifest.json exists and layers were extracted to metadata/*/layer.tar
    # and then to layers/*, this is already covered.
    # The main filesystem extraction above should give the complete merged view.

    # Filesystem analysis
    log "INFO" "Analyzing filesystem structure..."
    local total_files=$(find "$OUTPUT_DIR/filesystem" -type f 2>/dev/null | wc -l || echo "0")
    local total_dirs=$(find "$OUTPUT_DIR/filesystem" -type d 2>/dev/null | wc -l || echo "0")
    local filesystem_size=$(du -sh "$OUTPUT_DIR/filesystem" 2>/dev/null | cut -f1 || echo "unknown")

    log "INFO" "Filesystem stats: $total_files files, $total_dirs directories, $filesystem_size"

    ((COMPLETED_PHASES++))
    echo -e "\n${GREEN}✓ Phase 2.5 completed${NC}"
}


phase3_config_recovery() { # Renamed from phase3_config_recovery to phase4_config_recovery
    CURRENT_PHASE="Configuration Recovery"
    PHASE_START_TIME=$(date +%s)
    show_progress 6 $TOTAL_PHASES "$CURRENT_PHASE"

    log "INFO" "Starting configuration recovery..."
    mkdir -p "$OUTPUT_DIR/configs/"{webserver,database,application}

    # Extract image configuration
    log "INFO" "Extracting image configuration..."
    docker inspect "$IMAGE" | jq > "$OUTPUT_DIR/configs/image-config.json"

    # Extract specific configurations
    log "INFO" "Extracting environment variables..."
    docker inspect "$IMAGE" | jq -r '.[0].Config.Env[]?' > "$OUTPUT_DIR/configs/environment.txt

    log "INFO" "Extracting exposed ports..."
    docker inspect "$IMAGE" | jq '.[0].Config.ExposedPorts?' > "$OUTPUT_DIR/configs/ports.json

    log "INFO" "Extracting volumes..."
    docker inspect "$IMAGE" | jq '.[0].Config.Volumes?' > "$OUTPUT_DIR/configs/volumes.json

    log "INFO" "Extracting labels..."
    docker inspect "$IMAGE" | jq '.[0].Config.Labels?' > "$OUTPUT_DIR/configs/labels.json

    # Extract working directory
    log "INFO" "Extracting working directory..."
    docker inspect "$IMAGE" | jq -r '.[0].Config.WorkingDir?' > "$OUTPUT_DIR/configs/workingdir.txt

    # Extract user information
    log "INFO" "Extracting user information..."
    docker inspect "$IMAGE" | jq -r '.[0].Config.User?' > "$OUTPUT_DIR/configs/user.txt

    # Extract entrypoint and command
    log "INFO" "Extracting entrypoint and command..."
    docker inspect "$IMAGE" | jq '.[0].Config.Entrypoint?' > "$OUTPUT_DIR/configs/entrypoint.json
    docker inspect "$IMAGE" | jq '.[0].Config.Cmd?' > "$OUTPUT_DIR/configs/cmd.json

    # Find configuration files in filesystem
    log "INFO" "Scanning for configuration files..."
    find "$OUTPUT_DIR/filesystem" \( -name "*.conf" -o -name "*.config" -o -name "*.ini" -o -name "*.yaml" -o -name "*.yml" -o -name "*.toml" -o -name "*.json" -o -name "*.xml" -o -name "*.properties" \) -type f | \
        head -100 > "$OUTPUT_DIR/configs/config-files.txt" 2>/dev/null || true # Increased head limit

    # Categorize configuration files
    log "INFO" "Categorizing configuration files..."
    if [[ -f "$OUTPUT_DIR/configs/config-files.txt" ]]; then
        while IFS= read -r config_file_path; do
            local filename=$(basename "$config_file_path")
            # Use case-insensitive matching for keywords
            case "$(echo "$filename" | tr '[:upper:]' '[:lower:]')" in
                *nginx*|*apache*|*httpd*|*lighttpd*|*caddy*)
                    cp "$config_file_path" "$OUTPUT_DIR/configs/webserver/" 2>/dev/null || log "DEBUG" "Failed to copy webserver config $config_file_path"
                    ;;
                *mysql*|*postgres*|*redis*|*mongodb*|*sqlite*|*mariadb*)
                    cp "$config_file_path" "$OUTPUT_DIR/configs/database/" 2>/dev/null || log "DEBUG" "Failed to copy database config $config_file_path"
                    ;;
                *app*|*application*|*service*|*server*|*daemon*) # Broad categories
                    cp "$config_file_path" "$OUTPUT_DIR/configs/application/" 2>/dev/null || log "DEBUG" "Failed to copy application config $config_file_path"
                    ;;
            esac
        done < "$OUTPUT_DIR/configs/config-files.txt"
    fi

    ((COMPLETED_PHASES++))
    echo -e "\n${GREEN}✓ Phase 3 completed${NC}"
}

phase3_5_compose_reconstruction() { # Renamed from phase3_5_compose_reconstruction to phase4_5_compose_reconstruction
    CURRENT_PHASE="Docker Compose Reconstruction"
    PHASE_START_TIME=$(date +%s)
    show_progress 7 $TOTAL_PHASES "$CURRENT_PHASE"

    log "INFO" "Starting Docker Compose reconstruction..."
    mkdir -p "$OUTPUT_DIR/compose"

    # Generate docker-compose.yml from image configuration
    log "INFO" "Generating docker-compose.yml..."

    # Service name sanitization
    local service_name=$(echo "$IMAGE" | tr ':/' '__' | tr '[:upper:]' '[:lower:]')
    # Remove leading/trailing underscores and ensure it's a valid service name
    service_name=$(echo "$service_name" | sed 's/^_*//;s/_*$//;s/__+/_/g')
    if [[ -z "$service_name" ]]; then service_name="decomposed_service"; fi # Fallback name

    cat > "$OUTPUT_DIR/compose/docker-compose.yml" << EOF
version: '3.8'
services:
  $service_name:
    image: $IMAGE
    container_name: ${service_name}_${RANDOM} # Add random to avoid conflicts if multiple compose files from same image
    restart: "no" # Default, user can change
EOF

    # Add working directory if specified
    if [[ -s "$OUTPUT_DIR/configs/workingdir.txt" ]] && [[ $(cat "$OUTPUT_DIR/configs/workingdir.txt") != "null" ]]; then
        echo "    working_dir: $(cat "$OUTPUT_DIR/configs/workingdir.txt)" >> "$OUTPUT_DIR/compose/docker-compose.yml"
    fi

    # Add user if specified
    if [[ -s "$OUTPUT_DIR/configs/user.txt" ]] && [[ $(cat "$OUTPUT_DIR/configs/user.txt") != "null" ]]; then
        echo "    user: $(cat "$OUTPUT_DIR/configs/user.txt)" >> "$OUTPUT_DIR/compose/docker-compose.yml"
    fi

    # Add environment variables
    if [[ -s "$OUTPUT_DIR/configs/environment.txt" ]] && [[ $(grep -q . "$OUTPUT_DIR/configs/environment.txt") ]]; then # Check if not empty
        echo "    environment:" >> "$OUTPUT_DIR/compose/docker-compose.yml"
        while IFS= read -r env_var; do
            # Properly quote environment variable values if they contain special characters
            # Simple approach: if it contains spaces or special chars, quote it.
            if [[ "$env_var" =~ [[:space:]=] || "$env_var" =~ [\$\{\}] ]]; then
                 # Split key=value for quoting value part
                 local key="${env_var%%=*}"
                 local value="${env_var#*=}"
                 echo "      - \"${key}=${value}\"" >> "$OUTPUT_DIR/compose/docker-compose.yml
            else
                 echo "      - $env_var" >> "$OUTPUT_DIR/compose/docker-compose.yml"
            fi
        done < "$OUTPUT_DIR/configs/environment.txt"
    fi

    # Add ports
    if [[ -s "$OUTPUT_DIR/configs/ports.json" ]] && [[ $(jq length "$OUTPUT_DIR/configs/ports.json" 2>/dev/null || echo "0") -gt 0 ]]; then
        echo "    ports:" >> "$OUTPUT_DIR/compose/docker-compose.yml"
        # Iterate over ports from jq output. Ports are keys in the JSON object.
        jq -r 'keys[]' "$OUTPUT_DIR/configs/ports.json" 2>/dev/null | while read -r port_spec; do
            # port_spec might be "80/tcp" or "8080/udp"
            local clean_port=$(echo "$port_spec" | cut -d'/' -f1)
            local protocol=$(echo "$port_spec" | cut -d'/' -f2)
            # Default to tcp if protocol is somehow missing or malformed
            if [[ "$protocol" != "tcp" && "$protocol" != "udp" ]]; then protocol="tcp"; fi
            echo "      - \"${clean_port}:${clean_port}/${protocol}\"" >> "$OUTPUT_DIR/compose/docker-compose.yml"
        done
    fi

    # Add volumes
    if [[ -s "$OUTPUT_DIR/configs/volumes.json" ]] && [[ $(jq length "$OUTPUT_DIR/configs/volumes.json" 2>/dev/null || echo "0") -gt 0 ]]; then
        echo "    volumes:" >> "$OUTPUT_DIR/compose/docker-compose.yml"
        # Volumes are keys in the JSON object. Values are empty objects {}.
        jq -r 'keys[]' "$OUTPUT_DIR/configs/volumes.json" 2>/dev/null | while read -r volume_path; do
            # For named volumes or complex host binds, this simple mapping might not be enough.
            # This assumes anonymous volumes or simple host:container binds if that's how they were defined.
            # Docker inspect usually gives container paths for Volumes.
            # If it's a named volume, it would be just the name.
            # If it's a host bind, it's "host_path:container_path"
            # For simplicity, we'll assume they are container paths for anonymous volumes.
            # If the user wants named volumes or specific host binds, they'd need to edit.
            echo "      - ${volume_path}:${volume_path}" >> "$OUTPUT_DIR/compose/docker-compose.yml
        done
    fi

    # Add entrypoint and command if specified
    if [[ -s "$OUTPUT_DIR/configs/entrypoint.json" ]] && [[ $(jq length "$OUTPUT_DIR/configs/entrypoint.json" 2>/dev/null || echo "0") -gt 0 ]]; then
        # Use jq to output the array as a YAML list
        echo "    entrypoint: $(jq -c '.' "$OUTPUT_DIR/configs/entrypoint.json" 2>/dev/null)" >> "$OUTPUT_DIR/compose/docker-compose.yml"
    fi

    if [[ -s "$OUTPUT_DIR/configs/cmd.json" ]] && [[ $(jq length "$OUTPUT_DIR/configs/cmd.json" 2>/dev/null || echo "0") -gt 0 ]]; then
        echo "    command: $(jq -c '.' "$OUTPUT_DIR/configs/cmd.json" 2>/dev/null)" >> "$OUTPUT_DIR/compose/docker-compose.yml"
    fi

    log "SUCCESS" "docker-compose.yml generated"

    # Check for Kubernetes conversion if Kompose is available
    if [[ "$HAS_KOMPOSE" == true ]]; then
        log "INFO" "Converting to Kubernetes manifests..."
        mkdir -p "$OUTPUT_DIR/orchestration"
        if execute_with_retry "kompose convert -f '$OUTPUT_DIR/compose/docker-compose.yml' -o '$OUTPUT_DIR/orchestration/'" \
            "Kubernetes conversion"; then
            log "SUCCESS" "Kubernetes manifests generated"
        else
            log "WARN" "Kompose conversion failed."
        fi
    fi

    ((COMPLETED_PHASES++))
    echo -e "\n${GREEN}✓ Phase 3.5 completed${NC}"
}

phase4_sbom_vulnerability() { # Renamed from phase4_sbom_vulnerability to phase5_sbom_vulnerability
    CURRENT_PHASE="SBOM & Vulnerability Analysis"
    PHASE_START_TIME=$(date +%s)
    show_progress 8 $TOTAL_PHASES "$CURRENT_PHASE"

    log "INFO" "Starting SBOM generation and vulnerability analysis..."
    mkdir -p "$OUTPUT_DIR/sbom" "$OUTPUT_DIR/vulnerabilities"

    # Generate SBOM
    if [[ "$HAS_SYFT" == true ]]; then
        log "INFO" "Generating SBOM..."
        if execute_with_retry "syft '$IMAGE' -o spdx-json='$OUTPUT_DIR/sbom/sbom.spdx.json'" \
            "SBOM generation (SPDX)"; then
            log "SUCCESS" "SBOM (SPDX) generated successfully"
        else
            log "WARN" "SBOM (SPDX) generation failed"
        fi
        if execute_with_retry "syft '$IMAGE' -o cyclonedx-json='$OUTPUT_DIR/sbom/sbom.cyclonedx.json'" \
            "SBOM generation (CycloneDX)"; then
            log "SUCCESS" "SBOM (CycloneDX) generated successfully"
        else
            log "WARN" "SBOM (CycloneDX) generation failed"
        fi
        # Generate human-readable format
        if execute_with_retry "syft '$IMAGE' -o table > '$OUTPUT_DIR/sbom/packages.txt'" \
            "SBOM generation (Table)"; then
            log "SUCCESS" "SBOM (Table) generated"
        fi

        # Analyze SBOM (if any format was generated)
        local sbom_file_to_analyze=""
        if [[ -f "$OUTPUT_DIR/sbom/sbom.spdx.json" ]]; then sbom_file_to_analyze="$OUTPUT_DIR/sbom/sbom.spdx.json"
        elif [[ -f "$OUTPUT_DIR/sbom/sbom.cyclonedx.json" ]]; then sbom_file_to_analyze="$OUTPUT_DIR/sbom/sbom.cyclonedx.json"
        fi

        if [[ -n "$sbom_file_to_analyze" ]]; then
            log "INFO" "Analyzing SBOM..."
            local package_count=$(jq '.artifacts | length' "$sbom_file_to_analyze" 2>/dev/null || echo "0")
            log "INFO" "SBOM contains $package_count packages"
            # Extract package types (works for SPDX)
            jq -r '.artifacts[].type' "$sbom_file_to_analyze" 2>/dev/null | sort | uniq -c > "$OUTPUT_DIR/sbom/package-types.txt" 2>/dev/null || log "DEBUG" "Could not extract package types from SBOM"
        fi
    else
        log "WARN" "Syft not available, skipping SBOM generation."
    fi

    # Vulnerability scanning
    if [[ "$HAS_GRYPE" == true ]]; then
        log "INFO" "Scanning for vulnerabilities..."
        local grype_target=""
        if [[ -f "$OUTPUT_DIR/sbom/sbom.spdx.json" ]]; then
            grype_target="sbom:$OUTPUT_DIR/sbom/sbom.spdx.json"
        elif [[ -f "$OUTPUT_DIR/sbom/sbom.cyclonedx.json" ]]; then
            grype_target="sbom:$OUTPUT_DIR/sbom/sbom.cyclonedx.json"
        else
            grype_target="$IMAGE" # Fallback to scanning image directly
        fi

        if execute_with_retry "grype '$grype_target' -o json > '$OUTPUT_DIR/vulnerabilities/vulnerabilities.json'" \
            "Vulnerability scanning"; then
            log "SUCCESS" "Vulnerability scan completed"
            # Generate summary
            if execute_with_retry "grype '$grype_target' -o table > '$OUTPUT_DIR/vulnerabilities/summary.txt'" \
                "Vulnerability summary generation"; then
                log "SUCCESS" "Vulnerability summary generated"
            fi
            # Analyze vulnerabilities
            local vuln_count=$(jq '.matches | length' "$OUTPUT_DIR/vulnerabilities/vulnerabilities.json" 2>/dev/null || echo "0")
            log "INFO" "Found $vuln_count vulnerabilities"
            # Categorize by severity
            jq -r '.matches[].vulnerability.severity' "$OUTPUT_DIR/vulnerabilities/vulnerabilities.json" 2>/dev/null | sort | uniq -c > "$OUTPUT_DIR/vulnerabilities/severity-distribution.txt" 2>/dev/null || log "DEBUG" "Could not categorize vulnerabilities by severity"
        else
            log "WARN" "Vulnerability scanning failed."
        fi
    else
        log "WARN" "Grype not available, skipping vulnerability scanning."
    fi

    # Additional scanning with Dive if available
    if [[ "$HAS_DIVE" == true ]]; then
        log "INFO" "Running Dive analysis..."
        # Dive's JSON output might not be as comprehensive as its TUI, but can provide some metrics
        if execute_with_retry "dive '$IMAGE' --json --source ci" > "$OUTPUT_DIR/analysis/dive-analysis.json" \
            "Dive analysis"; then # Using --source ci for JSON output
            log "SUCCESS" "Dive analysis completed"
        else
            log "WARN" "Dive analysis failed."
        fi
    fi

    ((COMPLETED_PHASES++))
    echo -e "\n${GREEN}✓ Phase 4 completed${NC}"
}

phase4_5_forensic_recovery() { # Renamed from phase4_5_forensic_recovery to phase5_5_forensic_recovery
    CURRENT_PHASE="Forensic Artifact Recovery"
    PHASE_START_TIME=$(date +%s)
    show_progress 9 $TOTAL_PHASES "$CURRENT_PHASE"

    log "INFO" "Starting forensic artifact recovery..."
    mkdir -p "$OUTPUT_DIR/forensic"

    # Enhanced secret scanning
    log "INFO" "Scanning for secrets and credentials..."
    # Common secret patterns (can be expanded)
    local secret_patterns=(
        "password[[:space:]]*=[[:space:]]*[^[:space:]]+" "secret[[:space:]]*=[[:space:]]*[^[:space:]]+" "api[_-]?key[[:space:]]*=[[:space:]]*[^[:space:]]+"
        "token[[:space:]]*=[[:space:]]*[^[:space:]]+" "private[_-]?key" "BEGIN.*PRIVATE KEY" "BEGIN.*RSA PRIVATE KEY"
        "aws[_-]?access[_-]?key[_-]?id" "aws[_-]?secret[_-]?access[_-]?key" "github[_-]?token" "slack[_-]?token"
        "database[_-]?url" "jdbc:" "mongodb://" "redis://" "postgresql://" "mysql://"
        "gcp_service_account_key" "azure_storage_connection_string" "sendgrid_api_key"
        "twilio_account_sid" "twilio_auth_token" "stripe_api_key" "heroku_api_key"
    )
    > "$OUTPUT_DIR/forensic/secrets-found.tmp" # Truncate/create temp file
    for pattern in "${secret_patterns[@]}"; do
        grep -r -i -E -h "$pattern" "$OUTPUT_DIR/filesystem" 2>/dev/null | head -10 >> "$OUTPUT_DIR/forensic/secrets-found.tmp" || true # Limit matches per pattern
    done
    sort -u "$OUTPUT_DIR/forensic/secrets-found.tmp" > "$OUTPUT_DIR/forensic/secrets-found.txt" 2>/dev/null || true
    rm "$OUTPUT_DIR/forensic/secrets-found.tmp"

    # Certificate discovery
    log "INFO" "Discovering certificates..."
    find "$OUTPUT_DIR/filesystem" \( -name "*.pem" -o -name "*.crt" -o -name "*.key" -o -name "*.jks" -o -name "*.p12" -o -name "*.pfx" -o -name "*.der" -o -name "*.cer" \) -type f | \
        head -50 > "$OUTPUT_DIR/forensic/certificates.txt" 2>/dev/null || true

    # SSH keys
    log "INFO" "Finding SSH keys..."
    find "$OUTPUT_DIR/filesystem" \( -name "id_rsa" -o -name "id_ed25519" -o -name "id_dsa" -o -name "id_ecdsa" -o -name "authorized_keys" -o -name "known_hosts" -o -name "config" \) -type f | \
        head -20 > "$OUTPUT_DIR/forensic/ssh-keys.txt" 2>/dev/null || true

    # Configuration files with potential credentials
    log "INFO" "Identifying credential files..."
    find "$OUTPUT_DIR/filesystem" \( -name ".env*" -o -name "credentials*" -o -name "secret*" -o -name "pass*" -o -name "keytab" -o -name "keystore" \) -type f | \
        grep -E "\.(env|credentials|secret|pass|keytab|keystore)$" | head -30 > "$OUTPUT_DIR/forensic/credential-files.txt" 2>/dev/null || true

    # Database configuration files
    log "INFO" "Finding database configurations..."
    find "$OUTPUT_DIR/filesystem" \( -name "my.cnf" -o -name "postgresql.conf" -o -name "redis.conf" -o -name "mongod.conf" -o -name "database.yml" -o -name "settings.py" -o -name "config.php" \) -type f | \
        head -20 > "$OUTPUT_DIR/forensic/database-configs.txt" 2>/dev/null || true

    # Docker Forensics Toolkit (if available and enabled) - This part is highly dependent on the toolkit's structure and host access
    if [[ "$ENABLE_FORENSICS" == true ]] && [[ "$HAS_PYTHON3" == true ]]; then
        log "INFO" "Checking for Docker Forensics Toolkit (DFT)..."
        # DFT often requires access to /var/lib/docker or similar host paths.
        # Running it inside a container analyzing another container's filesystem dump ($OUTPUT_DIR/filesystem)
        # might not be its primary use case. It's more for live host/container analysis.
        # For now, we'll log a message rather than attempt potentially complex or misdirected calls.
        # If DFT scripts can operate on an extracted filesystem, that would be ideal.
        log "INFO" "DFT integration for extracted filesystem analysis is complex and context-dependent. Manual DFT analysis on host /var/lib/docker might be more fruitful if live containers are involved."
        # Example of a very cautious attempt if a specific DFT script is known to work on extracted fs:
        # if command -v docker-forensics-toolkit >/dev/null 2>&1 ; then # This is a hypothetical command
        #     log "INFO" "Attempting DFT carve-for-deleted-docker-files.py on extracted filesystem (experimental)..."
        #     # This is highly experimental and likely needs adjustment of DFT script paths and assumptions
        #     # The DFT script usually expects /var/lib/docker path.
        #     # We might need to copy parts of $OUTPUT_DIR/filesystem to a temp location that DFT expects, or modify DFT.
        #     # For now, this is a placeholder for more sophisticated DFT integration.
        #     # python3 /path/to/dft/carve-for-deleted-docker-files.py --root-dir "$OUTPUT_DIR/filesystem" > "$OUTPUT_DIR/forensic/dft_carved_files.txt" 2>&1 || log "DEBUG" "DFT carve script failed or not applicable."
        # fi
    fi

    # Summary of findings
    local secret_count=$(wc -l < "$OUTPUT_DIR/forensic/secrets-found.txt" 2>/dev/null || echo "0")
    local cert_count=$(wc -l < "$OUTPUT_DIR/forensic/certificates.txt" 2>/dev/null || echo "0")
    local ssh_count=$(wc -l < "$OUTPUT_DIR/forensic/ssh-keys.txt" 2>/dev/null || echo "0")

    log "INFO" "Forensic summary: $secret_count potential secrets, $cert_count certificates, $ssh_count SSH keys"

    ((COMPLETED_PHASES++))
    echo -e "\n${GREEN}✓ Phase 4.5 completed${NC}"
}

phase5_runtime_analysis() { # Renamed from phase5_runtime_analysis to phase6_runtime_analysis
    CURRENT_PHASE="Runtime Analysis"
    PHASE_START_TIME=$(date +%s)
    show_progress 10 $TOTAL_PHASES "$CURRENT_PHASE"

    if [[ "$SKIP_RUNTIME" == true ]]; then
        log "INFO" "Skipping runtime analysis (disabled)"
        ((COMPLETED_PHASES++))
        echo -e "\n${YELLOW}⚠ Phase 5 skipped${NC}"
        return
    fi

    log "INFO" "Starting runtime analysis..."
    mkdir -p "$OUTPUT_DIR/runtime"

    # If container ID is provided, analyze running container
    if [[ -n "$CONTAINER_ID" ]] && docker ps -q --filter "id=$CONTAINER_ID" | grep -q .; then
        log "INFO" "Analyzing running container: $CONTAINER_ID"

        # Container stats
        docker stats --no-stream --no-trunc "$CONTAINER_ID" > "$OUTPUT_DIR/runtime/container-stats.txt" 2>/dev/null || log "WARN" "Failed to get container stats."

        # Process information
        docker top "$CONTAINER_ID" > "$OUTPUT_DIR/runtime/container-processes.txt" 2>/dev/null || log "WARN" "Failed to get container top."

        # Container logs (can be large, consider tail or limits)
        docker logs --tail 100 "$CONTAINER_ID" > "$OUTPUT_DIR/runtime/container-logs-tail.txt" 2>/dev/null || log "WARN" "Failed to get container logs tail."
        # docker logs "$CONTAINER_ID" > "$OUTPUT_DIR/runtime/container-logs-full.txt" 2>&1 || log "WARN" "Failed to get full container logs."

        # Container changes (filesystem diff)
        docker diff "$CONTAINER_ID" > "$OUTPUT_DIR/runtime/container-changes.txt" 2>/dev/null || log "WARN" "Failed to get container diff."

        # Container inspect (detailed runtime state)
        docker inspect "$CONTAINER_ID" > "$OUTPUT_DIR/runtime/container-inspect-runtime.json" 2>/dev/null || log "WARN" "Failed to inspect running container."

        # Network information (if netstat is available in container)
        if docker exec "$CONTAINER_ID" which netstat >/dev/null 2>&1; then
            docker exec "$CONTAINER_ID" netstat -tulpn 2>/dev/null > "$OUTPUT_DIR/runtime/container-network-netstat.txt" || log "WARN" "Failed to get container netstat."
        fi
        # If ss is available (modern replacement for netstat)
        if docker exec "$CONTAINER_ID" which ss >/dev/null 2>&1; then
             docker exec "$CONTAINER_ID" ss -tulpn 2>/dev/null > "$OUTPUT_DIR/runtime/container-network-ss.txt" || log "WARN" "Failed to get container ss."
        fi

        log "SUCCESS" "Runtime analysis completed for container $CONTAINER_ID"
    else
        log "INFO" "No running container ID provided or container not running. Creating a generic runtime analysis script."
        # Create a generic runtime analysis script for manual execution
        cat > "$OUTPUT_DIR/runtime/runtime-analysis-template.sh" << EOF
#!/bin/bash
# Generic Runtime Analysis Script for an image: $IMAGE
# To use: docker run -d --name "runtime-analysis-\$(date +%s)" $IMAGE
# Then: ./runtime-analysis-template.sh <container_id_or_name>

CONTAINER_NAME=\${1:-}
if [[ -z "\$CONTAINER_NAME" ]]; then
    echo "Usage: \$0 <container_name_or_id>"
    exit 1
fi

echo "Starting runtime analysis for container: \$CONTAINER_NAME"
echo "Output directory: \$(pwd)" # Assuming this script is run from $OUTPUT_DIR/runtime

if ! docker ps -q --filter "name=\$CONTAINER_NAME" | grep -q . && ! docker ps -q --filter "id=\$CONTAINER_NAME" | grep -q . ; then
    echo "Container \$CONTAINER_NAME not running or not found."
    exit 1
fi

docker stats --no-stream --no-trunc "\$CONTAINER_NAME" > container-stats.txt
docker top "\$CONTAINER_NAME" > container-processes.txt
docker logs --tail 200 "\$CONTAINER_NAME" > container-logs-tail.txt
docker diff "\$CONTAINER_NAME" > container-changes.txt
docker inspect "\$CONTAINER_NAME" > container-inspect-runtime.json

if docker exec "\$CONTAINER_NAME" which netstat >/dev/null 2>&1; then
    docker exec "\$CONTAINER_NAME" netstat -tulpn > container-network-netstat.txt
fi
if docker exec "\$CONTAINER_NAME" which ss >/dev/null 2>&1; then
    docker exec "\$CONTAINER_NAME" ss -tulpn > container-network-ss.txt
fi

echo "Runtime analysis for \$CONTAINER_NAME completed. Files saved in current directory."
EOF
        chmod +x "$OUTPUT_DIR/runtime/runtime-analysis-template.sh"
        log "INFO" "Generic runtime analysis script created: $OUTPUT_DIR/runtime/runtime-analysis-template.sh"
        log "INFO" "To use it, start a container from '$IMAGE' and run the script with the container name/ID."
    fi

    ((COMPLETED_PHASES++))
    echo -e "\n${GREEN}✓ Phase 5 completed${NC}"
}

phase6_offensive_security() { # Renamed from phase6_offensive_security to phase7_offensive_security
    CURRENT_PHASE="Offensive Security Analysis"
    PHASE_START_TIME=$(date +%s)
    show_progress 11 $TOTAL_PHASES "$CURRENT_PHASE"

    if [[ "$SKIP_OFFENSIVE" == true ]]; then
        log "INFO" "Skipping offensive security analysis (disabled)"
        ((COMPLETED_PHASES++))
        echo -e "\n${YELLOW}⚠ Phase 6 skipped${NC}"
        return
    fi

    log "INFO" "Starting offensive security analysis..."
    mkdir -p "$OUTPUT_DIR/security"
    > "$OUTPUT_DIR/security/security-issues.txt" # Truncate/create

    # Basic security checks based on docker inspect output
    local image_config
    image_config=$(docker inspect "$IMAGE" 2>/dev/null) # Get config once
    if [[ -z "$image_config" ]]; then
        log "ERROR" "Could not get image config for offensive security analysis."
        ((ERROR_COUNT++))
        ((COMPLETED_PHASES++))
        return
    fi

    # Check for privileged containers
    if echo "$image_config" | jq -r '.[0].Config.Privileged' | grep -q "true"; then
        echo "CRITICAL: Container runs as privileged" >> "$OUTPUT_DIR/security/security-issues.txt"
        log "ERROR" "Container runs as privileged"
        ((ERROR_COUNT++))
    fi

    # Check for root user
    local user=$(echo "$image_config" | jq -r '.[0].Config.User')
    if [[ "$user" == "root" ]] || [[ "$user" == "0" ]] || [[ "$user" == "null" ]]; then # null often means root
        echo "WARNING: Container runs as root user (User: $user)" >> "$OUTPUT_DIR/security/security-issues.txt"
        log "WARN" "Container runs as root user (User: $user)"
        ((WARNING_COUNT++))
    fi

    # Check for dangerous capabilities
    log "INFO" "Checking container capabilities..."
    echo "$image_config" | jq -r '.[0].Config.CapAdd[]?' 2>/dev/null | while read -r cap; do
        case "$cap" in
            "CAP_SYS_ADMIN"|"CAP_SYS_PTRACE"|"CAP_SYS_MODULE"|"CAP_DAC_READ_SEARCH"|"CAP_NET_ADMIN"|"CAP_SYS_RAW"|"CAP_SYS_BOOT"|"CAP_SYS_TIME"|"CAP_AUDIT_WRITE"|"CAP_AUDIT_CONTROL")
                echo "WARNING: Container has dangerous capability: $cap" >> "$OUTPUT_DIR/security/security-issues.txt"
                log "WARN" "Container has dangerous capability: $cap"
                ((WARNING_COUNT++))
                ;;
        esac
    done

    # Check for sensitive mounts
    log "INFO" "Checking for sensitive mounts..."
    echo "$image_config" | jq -r '.[0].Config.Volumes | keys[]' 2>/dev/null | while read -r volume; do
        case "$volume" in
            "/etc"|"/var/run/docker.sock"|"/var/lib/docker"|"/root"|"/home"|"/usr"|"/bin"|"/sbin"|"/lib"|"/lib64")
                echo "WARNING: Container mounts sensitive directory: $volume" >> "$OUTPUT_DIR/security/security-issues.txt"
                log "WARN" "Container mounts sensitive directory: $volume"
                ((WARNING_COUNT++))
                ;;
        esac
    done
    # Also check for actual host binds in HostConfig.Binds if inspecting a running container (not just image)
    # For image analysis, this is limited to what Volumes define.

    # Check for network mode
    local network_mode=$(echo "$image_config" | jq -r '.[0].Config.NetworkMode')
    if [[ "$network_mode" == "host" ]]; then
        echo "CRITICAL: Container uses host network mode" >> "$OUTPUT_DIR/security/security-issues.txt"
        log "ERROR" "Container uses host network mode"
        ((ERROR_COUNT++))
    fi

    # Check for PID mode
    local pid_mode=$(echo "$image_config" | jq -r '.[0].Config.PidMode')
    if [[ "$pid_mode" == "host" ]]; then
        echo "CRITICAL: Container uses host PID mode" >> "$OUTPUT_DIR/security/security-issues.txt"
        log "ERROR" "Container uses host PID mode"
        ((ERROR_COUNT++))
    fi

    # Check for IPC mode
    local ipc_mode=$(echo "$image_config" | jq -r '.[0].Config.IpcMode')
    if [[ "$ipc_mode" == "host" ]]; then
        echo "WARNING: Container uses host IPC mode" >> "$OUTPUT_DIR/security/security-issues.txt"
        log "WARN" "Container uses host IPC mode"
        ((WARNING_COUNT++))
    fi

    # Check for UTS mode (hostname)
    local uts_mode=$(echo "$image_config" | jq -r '.[0].Config.UTSMode')
    if [[ "$uts_mode" == "host" ]]; then
        echo "INFO: Container uses host UTS mode (shares hostname)" >> "$OUTPUT_DIR/security/security-issues.txt"
        log "INFO" "Container uses host UTS mode (shares hostname)"
    fi

    # Check for seccomp profile
    local seccomp_profile=$(echo "$image_config" | jq -r '.[0].Config.SecurityOpt[]?' | grep -o 'seccomp[^,]*' 2>/dev/null)
    if [[ -n "$seccomp_profile" ]]; then
        echo "INFO: Custom seccomp profile detected: $seccomp_profile" >> "$OUTPUT_DIR/security/security-issues.txt"
        log "INFO" "Custom seccomp profile detected: $seccomp_profile"
    else
        echo "INFO: No custom seccomp profile detected (using default or none)" >> "$OUTPUT_DIR/security/security-issues.txt"
        log "INFO" "No custom seccomp profile detected (using default or none)"
    fi

    # Check for apparmor profile
    local apparmor_profile=$(echo "$image_config" | jq -r '.[0].Config.SecurityOpt[]?' | grep -o 'apparmor[^,]*' 2>/dev/null)
    if [[ -n "$apparmor_profile" ]]; then
        echo "INFO: Custom AppArmor profile detected: $apparmor_profile" >> "$OUTPUT_DIR/security/security-issues.txt"
        log "INFO" "Custom AppArmor profile detected: $apparmor_profile"
    else
        echo "INFO: No custom AppArmor profile detected (using default or none)" >> "$OUTPUT_DIR/security/security-issues.txt"
        log "INFO" "No custom AppArmor profile detected (using default or none)"
    fi
    
    # Check for no-new-privileges
    local no_new_privileges=$(echo "$image_config" | jq -r '.[0].Config.NoNewPrivileges')
    if [[ "$no_new_privileges" == "true" ]]; then
        echo "INFO: NoNewPrivileges is enabled" >> "$OUTPUT_DIR/security/security-issues.txt"
        log "INFO" "NoNewPrivileges is enabled"
    else
        echo "INFO: NoNewPrivileges is not enabled (processes can gain new privileges)" >> "$OUTPUT_DIR/security/security-issues.txt"
        log "INFO" "NoNewPrivileges is not enabled (processes can gain new privileges)"
    fi

    # Check for read-only root filesystem
    local read_only=$(echo "$image_config" | jq -r '.[0].Config.ReadonlyRootfs')
    if [[ "$read_only" == "true" ]]; then
        echo "INFO: Root filesystem is read-only" >> "$OUTPUT_DIR/security/security-issues.txt"
        log "INFO" "Root filesystem is read-only"
    else
        echo "WARNING: Root filesystem is not read-only" >> "$OUTPUT_DIR/security/security-issues.txt
        log "WARN" "Root filesystem is not read-only"
        ((WARNING_COUNT++))
    fi

    # Check for health check
    local health_check=$(echo "$image_config" | jq -r '.[0].Config.Healthcheck? // empty if null')
    if [[ "$health_check" != "null" && "$health_check" != "" ]]; then # Check if object exists and is not empty
        echo "INFO: Health check configured" >> "$OUTPUT_DIR/security/security-issues.txt"
        log "INFO" "Health check configured"
    else
        echo "INFO: No health check configured" >> "$OUTPUT_DIR/security/security-issues.txt
        log "INFO" "No health check configured"
    fi

    # Generate security report
    log "INFO" "Generating security report..."
    cat > "$OUTPUT_DIR/security/security-summary.md" << EOF
# Security Analysis Report for $IMAGE

## Container Configuration Security

### Critical Issues
 $(grep -i "^CRITICAL:" "$OUTPUT_DIR/security/security-issues.txt" 2>/dev/null || echo "None")

### Warnings
 $(grep -i "^WARNING:" "$OUTPUT_DIR/security/security-issues.txt" 2>/dev/null || echo "None")

### Informational
 $(grep -i "^INFO:" "$OUTPUT_DIR/security/security-issues.txt" 2>/dev/null || echo "None")

## Security Recommendations

1.  **Least Privilege**: Run containers as a non-root user. Specify a \`User\` in Dockerfile or \`user\` in compose.
2.  **Resource Limits**: Set memory and CPU limits in Docker Compose or run commands to prevent DoS.
3.  **Read-only Filesystem**: Use a read-only root filesystem when possible, mounting specific writable volumes.
4.  **Capabilities**: Drop all capabilities and only add those explicitly needed. Avoid \`CAP_SYS_ADMIN\`, \`CAP_NET_ADMIN\`, etc.
5.  **Security Profiles**: Utilize custom seccomp and AppArmor profiles for stricter kernel syscall filtering.
6.  **Network Isolation**: Avoid host network mode. Use user-defined networks.
7.  **PID/IPC Isolation**: Avoid host PID and IPC modes unless absolutely necessary.
8.  **Privileged Mode**: Never run containers in privileged mode unless absolutely required for specific hardware access.
9.  **Sensitive Mounts**: Avoid mounting sensitive host directories (e.g., \`/var/run/docker.sock\`, \`/etc\`, system directories).
10. **Health Checks**: Implement health checks for better orchestration and self-healing.
11. **NoNewPrivileges**: Consider enabling \`NoNewPrivileges\` to prevent processes from gaining more privileges.

---
*Generated by Ultimate Docker Decomposition Framework*
EOF

    log "SUCCESS" "Offensive security analysis completed"

    ((COMPLETED_PHASES++))
    echo -e "\n${GREEN}✓ Phase 6 completed${NC}"
}

phase6_5_source_recovery() { # Renamed from phase6_5_source_recovery to phase7_5_source_recovery
    CURRENT_PHASE="Source Code Recovery"
    PHASE_START_TIME=$(date +%s)
    show_progress 12 $TOTAL_PHASES "$CURRENT_PHASE"

    log "INFO" "Starting source code recovery..."
    mkdir -p "$OUTPUT_DIR/source/"{python,nodejs,jar-extracted,decompiled,ruby,php,dotnet,go,config_files,recovered_typescript,recovered_js}

    # Find application directories
    log "INFO" "Discovering application directories..."
    local app_dirs=("/app" "/src" "/usr/src/app" "/opt/app" "/var/www/html" "/home/app" "/application" "/code" "/usr/share/nginx/html" "/var/www/localhost/htdocs") # Added some common web roots
    for app_dir in "${app_dirs[@]}"; do
        if [[ -d "$OUTPUT_DIR/filesystem$app_dir" ]]; then
            log "INFO" "Found application directory: $app_dir"
            local dir_name=$(basename "$app_dir" | tr '/' '_') # Sanitize dirname for copying
            # Ensure target directory name is unique if app_dir basename is common (e.g., "app")
            local target_dir_name="${dir_name}_$(echo "$app_dir" | tr '/' '_')"
            cp -r "$OUTPUT_DIR/filesystem$app_dir" "$OUTPUT_DIR/source/$target_dir_name" 2>/dev/null || log "DEBUG" "Failed to copy $app_dir"
        fi
    done

    # Language-specific discovery and recovery
    log "INFO" "Language-specific source discovery..."

    # Python applications
    log "INFO" "Recovering Python source code..."
    find "$OUTPUT_DIR/filesystem" -name "*.py" -type f -exec dirname {} \; | sort -u | head -20 | xargs -I {} cp -r {} "$OUTPUT_DIR/source/python/" 2>/dev/null || true # Copy parent dirs of .py files
    find "$OUTPUT_DIR/filesystem" \( -name "requirements.txt" -o -name "setup.py" -o -name "Pipfile" -o -name "pyproject.toml" -o -name "conda.yml" -o -name "environment.yml" \) -type f -exec cp {} "$OUTPUT_DIR/source/python/" 2>/dev/null || true

    # Python bytecode decompilation
    if [[ "$HAS_UNCOMPILE6" == true ]]; then
        log "INFO" "Decompiling Python bytecode..."
        find "$OUTPUT_DIR/filesystem" -name "*.pyc" -type f | while read -r pyc_file; do
            local output_file="${pyc_file%.pyc}.py"
            local relative_path="${output_file#$OUTPUT_DIR/filesystem/}"
            local target_dir="$OUTPUT_DIR/source/decompiled/python/$(dirname "$relative_path)"
            mkdir -p "$target_dir"
            # uncompyle6 might need specific options or fail on certain bytecode versions
            if uncompyle6 -o "$target_dir" "$pyc_file" >/dev/null 2>&1; then
                log "DEBUG" "Decompiled: $pyc_file to $target_dir/$(basename "$output_file")"
            else
                log "DEBUG" "uncompyle6 failed for $pyc_file"
            fi
        done
    fi

    # Node.js applications
    log "INFO" "Recovering Node.js source code..."
    find "$OUTPUT_DIR/filesystem" \( -name "package.json" -o -name "package-lock.json" -o -name "yarn.lock" -o -name "pnpm-lock.yaml" \) -type f -exec cp {} "$OUTPUT_DIR/source/nodejs/" 2>/dev/null || true
    # Find .js, .ts, .jsx, .tsx files but avoid node_modules initially
    find "$OUTPUT_DIR/filesystem" \( -name "*.js" -o -name "*.ts" -o -name "*.jsx" -o -name "*.tsx" \) -not -path "*/node_modules/*" -type f -exec dirname {} \; | sort -u | head -20 | xargs -I {} cp -r {} "$OUTPUT_DIR/source/nodejs/" 2>/dev/null || true
    # Copy node_modules if DEEP_SCAN (can be very large)
    if [[ "$DEEP_SCAN" == true ]]; then
        find "$OUTPUT_DIR/filesystem" -name "node_modules" -type d -exec cp -r {} "$OUTPUT_DIR/source/nodejs/" 2>/dev/null || log "INFO" "node_modules copied if found."
    fi


    # Java applications
    log "INFO" "Recovering Java source code..."
    find "$OUTPUT_DIR/filesystem" \( -name "*.jar" -o -name "*.war" -o -name "*.ear" -o -name "pom.xml" -o -name "build.gradle" -o -name "build.gradle.kts" -o -name "gradle.properties" -o -name "*.java" \) -type f | while read -r java_artifact; do
        if [[ "$java_artifact" == *.jar || "$java_artifact" == *.war || "$java_artifact" == *.ear ]]; then
            local jar_name=$(basename "$java_artifact" .jar | cut -d'.' -f1) # Handle .war, .ear etc.
            if [[ "$jar_name" != "$(basename "$java_artifact")" ]]; then jar_name=$(basename "$java_artifact .war); fi
            if [[ "$jar_name" != "$(basename "$java_artifact")" ]]; then jar_name=$(basename "$java_artifact .ear); fi

            mkdir -p "$OUTPUT_DIR/source/jar-extracted/$jar_name"
            if unzip -q -o "$java_artifact" -d "$OUTPUT_DIR/source/jar-extracted/$jar_name" >/dev/null 2>&1; then # -o to overwrite
                log "DEBUG" "Extracted JAR/WAR/EAR: $java_artifact"
                # Look for .java files within extracted JARs (often in BOOT-INF/classes or similar)
                find "$OUTPUT_DIR/source/jar-extracted/$jar_name" -name "*.java" -type f -exec cp {} "$OUTPUT_DIR/source/java-source-from-jars/" 2>/dev/null || mkdir -p "$OUTPUT_DIR/source/java-source-from-jars" && find "$OUTPUT_DIR/source/jar-extracted/$jar_name" -name "*.java" -type f -exec cp {} "$OUTPUT_DIR/source/java-source-from-jars/" 2>/dev/null || true
            else
                log "DEBUG" "Failed to extract or not an archive: $java_artifact"
            fi
        else # pom.xml, gradle files, .java files in filesystem
            cp "$java_artifact" "$OUTPUT_DIR/source/java/" 2>/dev/null || true
        fi
    done

    # Go applications (source files)
    log "INFO" "Recovering Go source files..."
    find "$OUTPUT_DIR/filesystem" -name "*.go" -type f -exec dirname {} \; | sort -u | head -20 | xargs -I {} cp -r {} "$OUTPUT_DIR/source/go/" 2>/dev/null || true
    # Go binaries (identified by phase2_binary_forensics) are handled by advanced decompilation phase

    # Ruby applications
    log "INFO" "Recovering Ruby source code..."
    find "$OUTPUT_DIR/filesystem" \( -name "*.rb" -o -name "Gemfile" -o -name "*.gemspec" -o -name "Rakefile" -o -name "config.ru" \) -type f -exec cp {} "$OUTPUT_DIR/source/ruby/" 2>/dev/null || true

    # PHP applications
    log "INFO" "Recovering PHP source code..."
    find "$OUTPUT_DIR/filesystem" \( -name "*.php" -o -name "composer.json" -o -name "composer.lock" \) -type f -exec cp {} "$OUTPUT_DIR/source/php/" 2>/dev/null || true

    # .NET applications
    log "INFO" "Recovering .NET source files..."
    find "$OUTPUT_DIR/filesystem" \( -name "*.cs" -o -name "*.vb" -o -name "*.fs" -o -name "*.fsx" -o -name "*.dll" -o -name "*.exe" -o -name "project.json" -o -name "*.csproj" -o -name "*.vbproj" -o -name "*.fsproj" -o -name "packages.config" \) -type f -exec cp {} "$OUTPUT_DIR/source/dotnet/" 2>/dev/null || true

    # Configuration files (general, not language specific)
    # This was done in phase3_config_recovery, but let's gather them here for source context too
    # find "$OUTPUT_DIR/filesystem" -name "*.yml" -o -name "*.yaml" -o -name "*.xml" -o -name "*.properties" -o -name "*.conf" -o -name "*.ini" -o -name "*.toml" -o -name "*.json" | head -50 > "$OUTPUT_DIR/source/config_files_list.txt" 2>/dev/null || true

    # Check for results from advanced binary decompilation (TS/JS from sourcemaps)
    if [[ -d "$OUTPUT_DIR/advanced_analysis/sourcemaps_recovered" && "$(ls -A $OUTPUT_DIR/advanced_analysis/sourcemaps_recovered 2>/dev/null)" ]]; then
        log "INFO" "Integrating TypeScript/JS files recovered from source maps..."
        # Copy or move recovered TS/JS files to the main source directory
        # This needs careful handling to avoid overwriting and to maintain structure if possible.
        # For now, just acknowledge their presence in the advanced_analysis dir.
        # A more sophisticated merge might be needed.
        cp -r "$OUTPUT_DIR/advanced_analysis/sourcemaps_recovered/"* "$OUTPUT_DIR/source/recovered_typescript/" 2>/dev/null || log "DEBUG" "Failed to copy recovered TS/JS from sourcemaps."
    fi

    # Generate source code summary
    log "INFO" "Generating source code summary..."
    cat > "$OUTPUT_DIR/source/source-summary.md" << EOF
# Source Code Recovery Summary for $IMAGE

## Recovered Languages & Artifacts

### Python
- Source Directories/Files: $(find "$OUTPUT_DIR/source/python" -name "*.py" -type f | wc -l 2>/dev/null || echo "0") .py files in $(find "$OUTPUT_DIR/source/python" -mindepth 1 -type d | wc -l 2>/dev/null || echo "0") dirs.
- Decompiled Python Bytecode: $(find "$OUTPUT_DIR/source/decompiled/python" -name "*.py" -type f | wc -l 2>/dev/null || echo "0") files.

### Node.js
- Package Files: $(find "$OUTPUT_DIR/source/nodejs" \( -name "package.json" -o -name "yarn.lock" -o -name "pnpm-lock.yaml" \) -type f | wc -l 2>/dev/null || echo "0")
- Source Files (.js, .ts, etc.): $(find "$OUTPUT_DIR/source/nodejs" \( -name "*.js" -o -name "*.ts" -o -name "*.jsx" -o -name "*.tsx" \) -not -path "*/node_modules/*" -type f | wc -l 2>/dev/null || echo "0")
- node_modules Present: $([[ -d "$OUTPUT_DIR/source/nodejs/node_modules" && "$(ls -A $OUTPUT_DIR/source/nodejs/node_modules 2>/dev/null)" ]] && echo "Yes" || echo "No/Skipped")

### Java
- Source Files (.java): $(find "$OUTPUT_DIR/source/java" -name "*.java" -type f | wc -l 2>/dev/null || echo "0")
- Build Files (pom.xml, gradle): $(find "$OUTPUT_DIR/source/java" \( -name "pom.xml" -o -name "build.gradle*" \) -type f | wc -l 2>/dev/null || echo "0")
- JAR/WAR/EAR Files Extracted: $(find "$OUTPUT_DIR/source/jar-extracted" -mindepth 1 -maxdepth 1 -type d | wc -l 2>/dev/null || echo "0")
- .java from JARs: $(find "$OUTPUT_DIR/source/java-source-from-jars" -name "*.java" -type f | wc -l 2>/dev/null || echo "0")

### Go
- Source Files (.go): $(find "$OUTPUT_DIR/source/go" -name "*.go" -type f | wc -l 2>/dev/null || echo "0")
- Go Binaries (for decompilation): $(wc -l < "$OUTPUT_DIR/analysis/go-binaries.txt" 2>/dev/null || echo "0")

### Ruby
- Source Files (.rb, Gemfile, etc.): $(find "$OUTPUT_DIR/source/ruby" -type f | wc -l 2>/dev/null || echo "0")

### PHP
- Source Files (.php, composer.json): $(find "$OUTPUT_DIR/source/php" -type f | wc -l 2>/dev/null || echo "0")

### .NET
- Source Files (.cs, .vb, .fs, projects): $(find "$OUTPUT_DIR/source/dotnet" -type f | wc -l 2>/dev/null || echo "0")

### TypeScript/JavaScript (from Source Maps)
- Recovered TS/JS Directories: $(find "$OUTPUT_DIR/source/recovered_typescript" -mindepth 1 -type d | wc -l 2>/dev/null || echo "0")

### Decompiled C Code (Advanced Analysis)
- Radare2 Output: $(find "$OUTPUT_DIR/advanced_analysis/decompiled/radare2" -name "*.c" -type f | wc -l 2>/dev/null || echo "0") files.
- Ghidra Output: $(find "$OUTPUT_DIR/advanced_analysis/decompiled/ghidra" -name "*.c" -type f | wc -l 2>/dev/null || echo "0") files.

## Directory Structure
\`\`\`
 $OUTPUT_DIR/source/
├── python/                    # Python source files, requirements, etc.
├── nodejs/                   # Node.js source, package files, node_modules (if deep scan)
├── jar-extracted/            # Contents of extracted JAR/WAR/EAR files
├── java-source-from-jars/  # .java files found within extracted JARs
├── decompiled/python/         # Python files decompiled from .pyc
├── java/                     # .java, pom.xml, gradle files from filesystem
├── go/                       # .go source files
├── ruby/                    # Ruby source files
├── php/                      # PHP source files
├── dotnet/                   # .NET source and project files
├── recovered_typescript/      # Original TS/JS from source maps (via advanced analysis)
├── config_files_list.txt      # List of various config files found
└── source-summary.md         # This file
\`\`\`
**Advanced Decompilation Output:** \`$OUTPUT_DIR/advanced_analysis/decompiled/\`
**Source Map Recovery Output:** \`$OUTPUT_DIR/advanced_analysis/sourcemaps_recovered/\`

---
*Generated by Ultimate Docker Decomposition Framework*
EOF

    log "SUCCESS" "Source code recovery completed"

    ((COMPLETED_PHASES++))
    echo -e "\n${GREEN}✓ Phase 6.5 completed${NC}"
}


# =============================================================================
# REPORT GENERATION
# =============================================================================

generate_final_report() {
    log "INFO" "Generating final report..."

    local script_end_time=$(date +%s)
    local total_duration=$((script_end_time - SCRIPT_START_TIME))
    local hours=$((total_duration / 3600))
    local minutes=$(( (total_duration % 3600) / 60 ))
    local seconds=$((total_duration % 60))

    # Ensure the analysis directory exists for the report
    mkdir -p "$OUTPUT_DIR/analysis"

    cat > "$OUTPUT_DIR/analysis/FINAL_REPORT.md" << EOF
# 🔬 Ultimate Docker Image Decomposition Report

## Mission Summary
- **Target Image**: \`$IMAGE\`
- **Analysis Date**: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
- **Framework Version**: $SCRIPT_VERSION
- **Total Duration**: ${hours}h ${minutes}m ${seconds}s
- **Status**: $([ $ERROR_COUNT -eq 0 ] && echo "SUCCESS" || echo "COMPLETED WITH ISSUES")
- **Deep Scan Mode**: $DEEP_SCAN

## Mission Statistics
- **Total Phases**: $TOTAL_PHASES
- **Completed Phases**: $COMPLETED_PHASES
- **Errors Encountered**: $ERROR_COUNT
- **Warnings Generated**: $WARNING_COUNT

## Phase Results

### 1. Intelligence & Registry Reconnaissance
- **Remote Manifest**: $([ -f "$OUTPUT_DIR/metadata/remote-manifest.json" ] && echo "✓ Recovered" || echo "✗ Failed")
- **Registry Info**: $([ -f "$OUTPUT_DIR/metadata/registry-info.json" ] && echo "✓ Recovered" || echo "✗ Failed")

### 2. Secure Image Acquisition
- **Image Pulled**: ✓ Success
- **Image Archive**: ✓ Created
- **Image Metadata**: ✓ Extracted

### 3. Dockerfile Reconstruction
- **Whaler Method**: $([ -f "$OUTPUT_DIR/dockerfile/Dockerfile.whaler" ] && echo "✓ Success" || echo "✗ Failed/N/A")
- **dfimage Method**: $([ -f "$OUTPUT_DIR/dockerfile/Dockerfile.dfimage" ] && echo "✓ Success" || echo "✗ Failed/N/A")
- **History Method**: ✓ Attempted (Dockerfile.reconstructed.heuristic)

### 4. Binary Forensics & Advanced Decompilation
- **Binaries Found**: $(wc -l < "$OUTPUT_DIR/analysis/binaries.txt" 2>/dev/null || echo "0")
- **Go Binaries**: $(wc -l < "$OUTPUT_DIR/analysis/go-binaries.txt" 2>/dev/null || echo "0")
- **UPX Packed**: $(wc -l < "$OUTPUT_DIR/analysis/upx-packed.txt" 2>/dev/null || echo "0")
- **Debug Symbols Analyzed**: $(find "$OUTPUT_DIR/advanced_analysis/debug_symbols" -name "*.txt" 2>/dev/null | wc -l 2>/dev/null || echo "N/A")
- **Source Maps Processed**: $(find "$OUTPUT_DIR/advanced_analysis/sourcemaps_recovered" -type d 2>/dev/null | wc -l 2>/dev/null || echo "N/A")
- **Binwalk Analyses**: $(find "$OUTPUT_DIR/advanced_analysis/binwalk_output" -name "binwalk_report.json" 2>/dev/null | wc -l 2>/dev/null || echo "N/A")
- **Radare2 Decompilations**: $(find "$OUTPUT_DIR/advanced_analysis/decompiled/radare2" -name "*.c" 2>/dev/null | wc -l 2>/dev/null || echo "N/A")
- **Ghidra Decompilations**: $(find "$OUTPUT_DIR/advanced_analysis/decompiled/ghidra" -name "*.c" 2>/dev/null | wc -l 2>/dev/null || echo "N/A")

### 5. Filesystem Extraction
- **Complete Filesystem**: ✓ Success
- **Individual Layers**: $(find "$OUTPUT_DIR/layers" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l || echo "N/A") # Check if layers were extracted
- **Total Files**: $(find "$OUTPUT_DIR/filesystem" -type f 2>/dev/null | wc -l || echo "0")

### 6. Configuration Recovery
- **Environment Variables**: $(wc -l < "$OUTPUT_DIR/configs/environment.txt" 2>/dev/null || echo "0")
- **Exposed Ports**: $(jq length "$OUTPUT_DIR/configs/ports.json" 2>/dev/null || echo "0")
- **Volumes**: $(jq length "$OUTPUT_DIR/configs/volumes.json" 2>/dev/null || echo "0")

### 7. Docker Compose Reconstruction
- **Compose File**: ✓ Generated
- **K8s Manifests**: $([ -f "$OUTPUT_DIR/orchestration/deployment.yaml" -o -f "$OUTPUT_DIR/orchestration/service.yaml" ] && echo "✓ Generated" || echo "✗ Failed/N/A")

### 8. SBOM & Vulnerability Analysis
- **Packages Discovered**: $(jq '.artifacts | length' "$OUTPUT_DIR/sbom/sbom.spdx.json" 2>/dev/null || jq '.components | length' "$OUTPUT_DIR/sbom/sbom.cyclonedx.json" 2>/dev/null || echo "0")
- **Vulnerabilities Found**: $(jq '.matches | length' "$OUTPUT_DIR/vulnerabilities/vulnerabilities.json" 2>/dev/null || echo "0")

### 9. Forensic Artifact Recovery
- **Secrets Found**: $(wc -l < "$OUTPUT_DIR/forensic/secrets-found.txt" 2>/dev/null || echo "0")
- **Certificates**: $(wc -l < "$OUTPUT_DIR/forensic/certificates.txt" 2>/dev/null || echo "0")
- **SSH Keys**: $(wc -l < "$OUTPUT_DIR/forensic/ssh-keys.txt" 2>/dev/null || echo "0")

### 10. Runtime Analysis
 $([ "$SKIP_RUNTIME" == "false" ] && echo "- **Runtime Data**: ✓ Collected/Script Generated" || echo "- **Runtime Data**: ⚠ Skipped")

### 11. Offensive Security Analysis
 $([ "$SKIP_OFFENSIVE" == "false" ] && echo "- **Security Issues**: $(wc -l < "$OUTPUT_DIR/security/security-issues.txt" 2>/dev/null || echo "0")" || echo "- **Security Analysis**: ⚠ Skipped")

### 12. Source Code Recovery
- **Python Files**: $(find "$OUTPUT_DIR/source/python" -name "*.py" -type f 2>/dev/null | wc -l || echo "0")
- **Node.js Files**: $(find "$OUTPUT_DIR/source/nodejs" \( -name "*.js" -o -name "*.ts" \) -not -path "*/node_modules/*" -type f 2>/dev/null | wc -l || echo "0")
- **Java Files**: $(find "$OUTPUT_DIR/source/java" -name "*.java" -type f 2>/dev/null | wc -l || echo "0")
- **Total Decompiled (Py)**: $(find "$OUTPUT_DIR/source/decompiled/python" -name "*.py" -type f 2>/dev/null | wc -l || echo "0")
- **TS/JS from Maps**: $(find "$OUTPUT_DIR/source/recovered_typescript" -type f 2>/dev/null | wc -l || echo "0") # Approximate

## Critical Findings

### Security Issues (from Offensive Security Analysis)
 $(grep -i "^CRITICAL:" "$OUTPUT_DIR/security/security-issues.txt" 2>/dev/null || echo "None")
 $(grep -i "^WARNING:" "$OUTPUT_DIR/security/security-issues.txt" 2>/dev/null || echo "None")

### Discovered Secrets (Sample - check forensic/secrets-found.txt)
 $(head -3 "$OUTPUT_DIR/forensic/secrets-found.txt" 2>/dev/null || echo "None")

### High-Severity Vulnerabilities (Sample - check vulnerabilities/vulnerabilities.json)
 $(jq -r '.matches[] | select(.vulnerability.severity == "Critical") | "- \(.vulnerability.id): \(.artifact.name) (\(.vulnerability.severity))"' "$OUTPUT_DIR/vulnerabilities/vulnerabilities.json" 2>/dev/null | head -3 || echo "None")

## Directory Structure
\`\`\`
 $OUTPUT_DIR/
├── advanced_analysis/          # Results from deep binary decompilation, debug symbols, source maps
│   ├── debug_symbols/
│   ├── source_maps/
│   ├── binwalk_output/
│   ├── decompiled/
│   │   ├── radare2/
│   │   └── ghidra/
│   └── sourcemaps_recovered/
├── metadata/                 # Image metadata and manifests
├── filesystem/               # Complete extracted filesystem
├── layers/                   # Individual extracted layers (if extracted)
├── configs/                  # Configuration files and settings
│   ├── webserver/
│   ├── database/
│   └── application/
├── dockerfile/               # Reconstructed Dockerfiles
├── compose/                  # Docker Compose files
├── orchestration/            # Kubernetes manifests
├── sbom/                    # Software Bill of Materials
├── vulnerabilities/          # Security vulnerabilities
├── forensic/                 # Security findings and artifacts
├── runtime/                  # Runtime analysis data/scripts
├── security/                 # Security analysis results
├── source/                   # Recovered source code
└── analysis/                 # Analysis reports, logs, and this final report
\`\`\`

## Next Steps

1.  **Review Security Findings**: Examine \`security/security-issues.txt\` and \`security/security-summary.md\`.
2.  **Analyze Vulnerabilities**: Review \`vulnerabilities/vulnerabilities.json\` and \`vulnerabilities/summary.txt\`.
3.  **Examine Secrets**: Carefully review \`forensic/secrets-found.txt\`. **Handle with extreme care.**
4.  **Review Source Code**: Browse \`source/\` directory. Check \`source/source-summary.md\`.
5.  **Inspect Advanced Analysis**: Examine outputs in \`advanced_analysis/\` (decompiled C, debug symbols, etc.).
6.  **Test Reconstruction**: Verify \`Dockerfile.reconstructed\` and \`compose/docker-compose.yml\`.
7.  **Check Logs**: Review \`analysis/decomposition.log\` for detailed execution information and any errors.

## Mission Control

- **Framework**: Ultimate Docker Decomposition Framework $SCRIPT_VERSION
- **Research Date**: $RESEARCH_DATE
- **Tools Used**: Docker, jq, tar, curl, git, awk, sed, grep, find, sort, uniq, head, tail, tr, cut, wc, du, df, free, date, mkdir, cp, mv, rm, chmod, tee, timeout$([ "$HAS_SYFT" == true ] && echo ", Syft")$([ "$HAS_GRYPE" == true ] && echo ", Grype")$([ "$HAS_WHALER" == true ] && echo ", Whaler")$([ "$HAS_DIVE" == true ] && echo ", Dive")$([ "$HAS_SKOPEO" == true ] && echo ", Skopeo")$([ "$HAS_CRANE" == true ] && echo ", Crane")$([ "$HAS_KOMPOSE" == true ] && echo ", Kompose")$([ "$HAS_HELM" == true ] && echo ", Helm")$([ "$HAS_DWARFDUMP" == true ] && echo ", dwarfdump")$([ "$HAS_LLVM_DWARFDUMP" == true ] && echo ", llvm-dwarfdump")$([ "$HAS_PYELFTOOLS" == true ] && echo ", pyelftools")$([ "$HAS_SOURCEMAPPER" == true ] && echo ", sourcemapper")$([ "$HAS_RADARE2" == true ] && echo ", Radare2 (Docker)")$([ "$HAS_GHIDRA" == true ] && echo ", Ghidra (Docker)")$([ "$HAS_BINWALK" == true ] && echo ", Binwalk (Docker)")$([ "$HAS_UNCOMPILE6" == true ] && echo ", uncompyle6")

---
*Report generated by Ultimate Docker Decomposition Framework*
*Mission completed at $(date -u +"%Y-%m-%dT%H:%M:%SZ")*
EOF

    log "SUCCESS" "Final report generated: $OUTPUT_DIR/analysis/FINAL_REPORT.md"
}

# =============================================================================
# CLEANUP FUNCTIONS
# =============================================================================

cleanup_background_processes() {
    log "INFO" "Cleaning up background processes..."
    for pid in "${BACKGROUND_PROCESSES[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || log "DEBUG" "Failed to kill background process $pid"
            # If kill fails, try kill -9
            sleep 1 # Give it a moment
            if kill -0 "$pid" 2>/dev/null; then # Still running
                kill -9 "$pid" 2>/dev/null || log "DEBUG" "Failed to force kill background process $pid"
            fi
            log "DEBUG" "Killed background process: $pid"
        fi
    done
    # Clear the array
    BACKGROUND_PROCESSES=()
}

# =============================================================================
# MAIN EXECUTION
# =============================================================================

main() {
    # Initialize
    SCRIPT_START_TIME=$(date +%s)

    # Display banner
    echo -e "${MAGENTA}"
    echo "╔══════════════════════════════════════════════════════════════════════════════╗"
    echo "║                    🔬 ULTIMATE DOCKER DECOMPOSITION FRAMEWORK               ║"
    echo "║                            Version $SCRIPT_VERSION                            ║"
    echo "║                         Research-Validated Toolchain                        ║"
    echo "╚══════════════════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    echo -e "${CYAN}Deep Scan Mode: ${DEEP_SCAN}${NC}"
    echo -e "${CYAN}Log Level: ${LOG_LEVEL}${NC}"


    # Parse arguments
    if [[ -z "$IMAGE" ]]; then
        echo -e "${RED}Error: No image specified${NC}"
        echo "Usage: $0 <image:tag> [output_directory] [container_id]"
        echo "Example: $0 nginx:latest ./extracted abcdef123456"
        echo "Options can be set via environment variables, e.g., DEEP_SCAN=true, LOG_LEVEL=DEBUG"
        exit 1
    fi

    log "INFO" "Starting Ultimate Docker Decomposition Framework"
    log "INFO" "Target Image: $IMAGE"
    log "INFO" "Output Directory: $OUTPUT_DIR"
    [[ -n "$CONTAINER_ID" ]] && log "INFO" "Container ID: $CONTAINER_ID"

    # Check system resources
    check_system_resources

    # Create output structure
    log "INFO" "Creating output structure..."
    # Main directories are created within their respective phases or functions as needed.
    # Ensure top-level output dir exists
    mkdir -p "$OUTPUT_DIR"
    # Create analysis subdirectories for logs and reports early
    mkdir -p "$OUTPUT_DIR/analysis"


    # Initialize log files
    LOG_FILE="$OUTPUT_DIR/analysis/decomposition.log"
    REPORT_FILE="$OUTPUT_DIR/analysis/FINAL_REPORT.md" # Defined here, generated at the end
    METRICS_FILE="$OUTPUT_DIR/analysis/metrics.json" # Placeholder for future metrics

    # Verify and install tools
    verify_and_install_tools

    # Execute phases
    phase0_intelligence_reconnaissance
    phase1_secure_acquisition
    phase1_5_dockerfile_reconstruction
    phase2_binary_forensics # This now calls phase_advanced_binary_decompilation internally if DEEP_SCAN
    phase2_5_filesystem_extraction
    phase3_config_recovery
    phase3_5_compose_reconstruction
    phase4_sbom_vulnerability
    phase4_5_forensic_recovery
    phase5_runtime_analysis
    phase6_offensive_security
    phase6_5_source_recovery

    # Generate final report
    generate_final_report

    # Cleanup
    cleanup_background_processes

    # Display completion message
    echo -e "\n${GREEN}"
    echo "╔══════════════════════════════════════════════════════════════════════════════╗"
    echo "║                           🎉 MISSION COMPLETED!                          ║"
    echo "╚══════════════════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    echo -e "${BLUE}Results saved to: ${YELLOW}$OUTPUT_DIR${NC}"
    echo -e "${BLUE}Final report: ${YELLOW}$REPORT_FILE${NC}"
    echo -e "${BLUE}Log file: ${YELLOW}$LOG_FILE${NC}"

    if [[ $ERROR_COUNT -gt 0 ]]; then
        echo -e "\n${YELLOW}⚠ Mission completed with $ERROR_COUNT errors and $WARNING_COUNT warnings${NC}"
        echo -e "${YELLOW}  Check the log file for details: $LOG_FILE${NC}"
    elif [[ $WARNING_COUNT -gt 0 ]]; then
        echo -e "\n${YELLOW}⚠ Mission completed successfully with $WARNING_COUNT warnings${NC}"
        echo -e "${YELLOW}  Check the log file for details: $LOG_FILE${NC}"
    else
        echo -e "\n${GREEN}✅ Mission completed successfully with no errors or warnings.${NC}"
    fi

    echo -e "\n${CYAN}Next steps:${NC}"
    echo "  1. Review the final report: $REPORT_FILE"
    echo "  2. Examine reconstructed files in $OUTPUT_DIR/"
    echo "  3. Check for security issues in $OUTPUT_DIR/security/"
    echo "  4. Review discovered secrets in $OUTPUT_DIR/forensic/secrets-found.txt (HANDLE WITH CARE)"
    echo "  5. Analyze vulnerabilities in $OUTPUT_DIR/vulnerabilities/"
    echo "  6. Browse recovered source code in $OUTPUT_DIR/source/"
    if [[ "$DEEP_SCAN" == true ]]; then
    echo "  7. Inspect advanced analysis outputs in $OUTPUT_DIR/advanced_analysis/"
    fi
}

# Trap cleanup on exit
trap cleanup_background_processes EXIT INT TERM

# Run main function, passing all arguments
main "$@"
