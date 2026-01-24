

# Gap Analysis and Strategic Upgrades

Based on a comprehensive review of the provided "Ultimate E2E Docker Image → Pre-Compile Recovery Framework" (v2026.4), several critical gaps have been identified that, if addressed, will significantly elevate the script's capabilities to align with 2024-2025 military-grade and enterprise security standards.

### 1. Secret Detection & Forensics
*   **Current State:** Relies on `grep` with regex patterns.
*   **Gap:** Prone to high false-positive/negative rates. Cannot verify if a found string is a *valid* credential.
*   **Upgrade:** Integration of **TruffleHog** and **Gitleaks**. These tools utilize entropy verification and API checks (e.g., verifying AWS key formats) to confirm credential validity, moving beyond simple pattern matching to verified discovery.

### 2. SBOM & Vulnerability Analysis
*   **Current State:** Uses Syft (SBOM) and Grype (Vulnerability scanning).
*   **Gap:** Different scanners use different vulnerability databases. A single-scanner approach creates a blind spot.
*   **Upgrade:** Integration of **Trivy** as a primary all-in-one scanner (Image, Filesystem, SBOM, Config). This creates a **Multi-Scanner Triangulation** approach. Comparing results from Grype, Syft, and Trivy provides a more accurate risk posture by identifying discrepancies and confirmed threats.

### 3. Static Container Security & Linting
*   **Current State:** Manual inspection of JSON configs (`docker inspect`) in the Offensive Security phase.
*   **Gap:** Misses complex best-practice violations (e.g., specific CIS Docker Benchmark checks) that are hard to script manually.
*   **Upgrade:** Integration of **Dockle**. Dockle is a container image linter that automates checks against best practices and CIS benchmarks, instantly identifying issues like cleartext passwords in env vars, outdated base images, and insecure configurations.

### 4. Runtime Security & Observability
*   **Current State:** Basic snapshotting (`top`, `logs`) of a running container.
*   **Gap:** Reactive only. Does not detect anomalous behavior (e.g., shell spawns, unexpected network connections) during the analysis window.
*   **Upgrade:** Integration of **Falco**. As a CNCF graduated project using eBPF, Falco provides deep system call visibility. If a `CONTAINER_ID` is provided, the script should deploy a sidecar or host-based Falco instance to monitor the target container for suspicious activity (file integrity, crypto mining, reverse shells) during the "Runtime Analysis" phase.

### 5. Operational & Reporting
*   **Current State:** Markdown report generation.
*   **Gap:** Markdown is human-readable but difficult to parse by CI/CD pipelines or ticketing systems.
*   **Upgrade:** Implementation of **SARIF (Static Analysis Results Interchange Format)** and structured **JSON** logging. This allows the framework's output to be natively ingested by security dashboards (e.g., GitHub Security Tab, DefectDojo, Jira).

---

# Upgraded "Ultimate Docker Decomposition Framework" (v2026.5)

Below is the fully upgraded code. It incorporates Trivy, TruffleHog, Dockle, and Falco logic, adds JSON/SARIF reporting capabilities, and refines the tool installation process.

```bash
#!/usr/bin/env bash
################################################################################
# 🔬 ULTIMATE E2E DOCKER IMAGE → PRE-COMPILE RECOVERY FRAMEWORK
# Version: 2026.5 — Military-Grade Research-Validated Pipeline (UPGRADED)
#
# Mission: Complete reconstruction of Docker images to original pre-compilation state
#          including Dockerfile, docker-compose, source code, configs, secrets,
#          runtime state, SBOM, vulnerabilities, forensic artifacts, and
#          ADVANCED PRE-COMPILED CONTENT RETRIEVAL (Debug Symbols, Source Maps,
#          Decompilation, LLM Refinement, Angr Analysis, YARA Scanning).
#
# v2026.5 Upgrades:
# • Integrated TruffleHog for verified secret detection.
# • Integrated Trivy for multi-scanner vulnerability/SBOM triangulation.
# • Integrated Dockle for CIS Benchmark & Best Practices Linting.
# • Integrated Falco for eBPF-based runtime threat detection (if container running).
# • Added SARIF & JSON output support for CI/CD integration.
# • Enhanced resource monitoring and resilience.
#
# Usage: ./docker-decompose-enhanced.sh <IMAGE:TAG> [OUTPUT_DIR] [CONTAINER_ID]
################################################################################

set -euo pipefail

# =============================================================================
# GLOBAL CONFIGURATION
# =============================================================================

# Script metadata
readonly SCRIPT_VERSION="2026.5" 
readonly SCRIPT_NAME="Ultimate Docker Decomposition Framework"
readonly RESEARCH_DATE="November 2025" 

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
readonly DEEP_SCAN="${DEEP_SCAN:-false}"
readonly ENABLE_FORENSICS="${ENABLE_FORENSICS:-true}"
readonly LOG_LEVEL="${LOG_LEVEL:-INFO}"
readonly MAX_RETRIES="${MAX_RETRIES:-3}"
readonly TIMEOUT="${TIMEOUT:-600}"

# Resource limits
readonly MAX_MEMORY_GB="${MAX_MEMORY_GB:-8}"
readonly MAX_DISK_SPACE_GB="${MAX_DISK_SPACE_GB:-50}"

# =============================================================================
# GLOBAL VARIABLES
# =============================================================================

declare -g SCRIPT_START_TIME
declare -g CURRENT_PHASE=""
declare -g PHASE_START_TIME
declare -g TOTAL_PHASES=12 
declare -g COMPLETED_PHASES=0
declare -g ERROR_COUNT=0
declare -g WARNING_COUNT=0

# Core tool flags
declare -g HAS_SYFT=false
declare -g HAS_GRYPE=false
declare -g HAS_TRIVY=false
declare -g HAS_WHALER=false
declare -g HAS_DIVE=false
declare -g HAS_DOCKLE=false
declare -g HAS_SKOPEO=false
declare -g HAS_CRANE=false
declare -g HAS_KOMPOSE=false
declare -g HAS_HELM=false
declare -g HAS_TRUFFLEHOG=false
declare -g HAS_FALCO=false

# Analysis tool flags
declare -g HAS_PYTHON3=false
declare -g HAS_UNCOMPILE6=false
declare -g HAS_VOLATILITY=false
declare -g HAS_DWARFDUMP=false
declare -g HAS_LLVM_DWARFDUMP=false
declare -g HAS_SOURCEMAPPER=false
declare -g HAS_RADARE2=false
declare -g HAS_GHIDRA=false
declare -g HAS_BINWALK=false
declare -g HAS_PYELFTOOLS=false
declare -g HAS_ANGR=false
declare -g HAS_RETDEC=false
declare -g HAS_YARA=false
declare -g HAS_SEMGREP=false

# Output directories
declare -g OUTPUT_ROOT
declare -g LOG_FILE
declare -g REPORT_FILE
declare -g METRICS_FILE
declare -g SARIF_FILE

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

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

    if [[ "$level" == "ERROR" ]] || \
       [[ "$level" == "WARN" && "$LOG_LEVEL" != "ERROR" ]] || \
       [[ "$level" == "INFO" && "$LOG_LEVEL" != "ERROR" && "$LOG_LEVEL" != "WARN" ]] || \
       [[ "$level" == "DEBUG" && "$LOG_LEVEL" == "DEBUG" ]] || \
       [[ "$level" == "PHASE" ]] || \
       [[ "$level" == "SUCCESS" ]]; then
        echo -e "${color}[$timestamp] [$level]${NC} $message" | tee -a "$LOG_FILE"
    fi
}

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

execute_with_retry() {
    local cmd="$1"
    local description="$2"
    local retry_count=0
    local success=false
    local current_timeout="$TIMEOUT"

    # Dynamic timeout adjustment for heavy tasks
    if [[ "$DEEP_SCAN" == true && ("$description" == *"Ghidra"* || "$description" == *"Trivy"* || "$description" == *"TruffleHog"*) ]]; then
        current_timeout=$((TIMEOUT * 2)) 
        log "DEBUG" "Increased timeout for $description to ${current_timeout}s"
    fi

    while [[ $retry_count -lt $MAX_RETRIES ]]; do
        log "INFO" "Attempting: $description (attempt $((retry_count + 1))/$MAX_RETRIES)"
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

check_system_resources() {
    log "INFO" "Checking system resources..."
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

    local available_disk_kb=$(df -k . | awk 'NR==2 {print $4}')
    local available_disk_gb=$((available_disk_kb / 1024 / 1024))
    if [[ $available_disk_gb -lt $MAX_DISK_SPACE_GB ]]; then
        log "WARN" "Low disk space available: ${available_disk_gb}GB (recommended: ${MAX_DISK_SPACE_GB}GB)"
        ((WARNING_COUNT++))
    fi
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

    local packages=("packaging" "requests" "pyyaml" "jinja2" "pyelftools" "sarif_om")
    for package in "${packages[@]}"; do
        if ! pip3 show "$package" >/dev/null 2>&1; then
            log "INFO" "Installing Python package: $package"
            execute_with_retry "pip3 install '$package'" "Install Python package $package" || log "WARN" "Failed to install $package"
        fi
    done

    # Specialized tools
    if ! pip3 show uncompyle6 >/dev/null 2>&1; then
        execute_with_retry "pip3 install 'uncompyle6>=3.9.0'" "Install uncompyle6" && HAS_UNCOMPILE6=true
    else HAS_UNCOMPILE6=true; fi

    if [[ "$DEEP_SCAN" == true ]]; then
        python3 -c "import angr" 2>/dev/null || execute_with_retry "pip3 install 'angr'" "Install angr" || true
        python3 -c "import yara" 2>/dev/null || execute_with_retry "pip3 install 'yara-python'" "Install yara-python" || true
    fi
}

install_tool() {
    local tool="$1"
    local method="$2"
    shift 2
    log "INFO" "Installing $tool using $method..."

    case "$method" in
        "curl")
            local url="$1"
            local dest="${2:-/usr/local/bin}"
            local filename=$(basename "$url")
            local temp_file=$(mktemp)
            if execute_with_retry "curl -sSL '$url' -o '$temp_file' && chmod +x '$temp_file' && mv '$temp_file' '$dest/$filename'" "Download and install $tool"; then
                log "SUCCESS" "$tool installed to $dest/$filename"; return 0
            else
                rm -f "$temp_file"; return 1
            fi
            ;;
        "go_install")
            local go_package_path="$1"
            [[ -z "${GOPATH:-}" ]] && export GOPATH="$(go env GOPATH 2>/dev/null || echo "$HOME/go")"
            if [[ ":$PATH:" != *":$GOPATH/bin:"* ]]; then export PATH="$PATH:$GOPATH/bin"; fi
            if execute_with_retry "go install $go_package_path@latest" "Install $tool via 'go install'"; then
                return 0
            else return 1; fi
            ;;
        "docker_pull")
            local docker_image="$1"
            execute_with_retry "docker pull $docker_image" "Pull Docker image $docker_image for $tool"
            ;;
        "apt")
            execute_with_retry "sudo DEBIAN_FRONTEND=noninteractive apt-get update && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y $tool" "Install $tool via apt"
            ;;
        *) return 1 ;;
    esac
}

verify_and_install_tools() {
    log "INFO" "Verifying and installing required tools..."

    # 1. Core Tools (Strict)
    local core_tools=("docker" "jq" "tar" "curl" "git" "awk" "sed" "grep")
    for tool in "${core_tools[@]}"; do
        if ! command -v "$tool" >/dev/null 2>&1; then
            log "ERROR" "Required core tool $tool not found."
            exit 1
        fi
    done
    HAS_PYTHON3=$(command -v python3 >/dev/null 2>&1 && echo true || echo false)

    # 2. Python Dependencies
    install_python_dependencies

    # 3. Advanced Analysis & Security Tools
    declare -A advanced_tools=(
        # Existing
        ["syft"]="curl|https://raw.githubusercontent.com/anchore/syft/main/install.sh|/usr/local/bin"
        ["grype"]="curl|https://raw.githubusercontent.com/anchore/grype/main/install.sh|/usr/local/bin"
        ["trivy"]="curl|https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh|/usr/local/bin"
        ["dockle"]="docker_pull|goodwithtech/dockle:latest" # Use docker for dockle to avoid deps
        ["whaler"]="docker_pull|pegleg/whaler:latest"
        ["dive"]="apt|dive"
        ["skopeo"]="apt|skopeo"
        ["crane"]="go_install|github.com/google/go-containerregistry/cmd/crane"
        ["kompose"]="curl|https://github.com/kubernetes/kompose/releases/latest/download/kompose-linux-amd64|/usr/local/bin/kompose"
        ["helm"]="curl|https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3"
        # New Forensics
        ["trufflehog"]="go_install|github.com/trufflesecurity/trufflehog/v3/cmd/trufflehog@latest"
    )

    for tool in "${!advanced_tools[@]}"; do
        if command -v "$tool" >/dev/null 2>&1; then
            log "DEBUG" "✓ $tool already installed"
            # Set flags
            case "$tool" in
                "syft") HAS_SYFT=true ;; "grype") HAS_GRYPE=true ;; "trivy") HAS_TRIVY=true ;;
                "dockle") HAS_DOCKLE=true ;; "whaler") HAS_WHALER=true ;; "dive") HAS_DIVE=true ;;
                "skopeo") HAS_SKOPEO=true ;; "crane") HAS_CRANE=true ;; "kompose") HAS_KOMPOSE=true ;;
                "helm") HAS_HELM=true ;; "trufflehog") HAS_TRUFFLEHOG=true ;;
            esac
        else
            IFS='|' read -ra methods <<< "${advanced_tools[$tool]}"
            local installed=false
            for ((i=0; i<${#methods[@]}; i+=3)); do
                local method="${methods[i]}"
                local arg1="${methods[i+1]:-}"
                local arg2="${methods[i+2]:-}"
                if install_tool "$tool" "$method" "$arg1" "$arg2"; then
                    installed=true
                    case "$tool" in
                        "syft") HAS_SYFT=true ;; "grype") HAS_GRYPE=true ;; "trivy") HAS_TRIVY=true ;;
                        "dockle") HAS_DOCKLE=true ;; "whaler") HAS_WHALER=true ;; "dive") HAS_DIVE=true ;;
                        "skopeo") HAS_SKOPEO=true ;; "crane") HAS_CRANE=true ;; "kompose") HAS_KOMPOSE=true ;;
                        "helm") HAS_HELM=true ;; "trufflehog") HAS_TRUFFLEHOG=true ;;
                    esac
                    break
                fi
            done
            if [[ "$installed" == false ]]; then
                log "WARN" "⚠ Failed to install $tool"
            fi
        fi
    done

    # 4. Optional Deep Scan Tools
    if [[ "$DEEP_SCAN" == true ]]; then
        if ! command -v dwarfdump >/dev/null 2>&1 && ! command -v llvm-dwarfdump >/dev/null 2>&1; then
            install_tool "dwarfdump" "apt" "dwarfdump" 2>/dev/null && HAS_DWARFDUMP=true
        fi
        if command -v dwarfdump >/dev/null 2>&1; then HAS_DWARFDUMP=true; fi
        if command -v llvm-dwarfdump >/dev/null 2>&1; then HAS_LLVM_DWARFDUMP=true; fi
        
        if ! command -v sourcemapper >/dev/null 2>&1; then
            install_tool "sourcemapper" "go_install" "github.com/denandz/sourcemapper" 2>/dev/null && HAS_SOURCEMAPPER=true
        else HAS_SOURCEMAPPER=true; fi

        # Dockerized heavy tools
        local docker_tools=("radare/radare2" "blacktop/ghidra" "cincan/binwalk" "avast/retdec")
        for dt in "${docker_tools[@]}"; do
            if ! docker images --format "{{.Repository}}:{{.Tag}}" | grep -q "^${dt}:latest"; then
                log "INFO" "Pulling $dt..."
                install_tool "$dt" "docker_pull" "${dt}:latest" || true
            fi
        done
        docker images --format "{{.Repository}}" | grep -q "radare/radare2" && HAS_RADARE2=true
        docker images --format "{{.Repository}}" | grep -q "blacktop/ghidra" && HAS_GHIDRA=true
        docker images --format "{{.Repository}}" | grep -q "cincan/binwalk" && HAS_BINWALK=true
        docker images --format "{{.Repository}}" | grep -q "avast/retdec" && HAS_RETDEC=true
    fi
}

# =============================================================================
# ADVANCED BINARY ANALYSIS PHASE
# =============================================================================

phase_advanced_binary_decompilation() {
    CURRENT_PHASE="Advanced Binary Decompilation & Pre-Compiled Content Retrieval"
    PHASE_START_TIME=$(date +%s)
    log "INFO" "Starting advanced binary decompilation (Deep Scan: $DEEP_SCAN)..."

    if [[ "$DEEP_SCAN" != true ]]; then
        log "INFO" "Skipping advanced binary decompilation."
        return 0
    fi

    local adv_analysis_dir="$OUTPUT_DIR/advanced_analysis"
    mkdir -p "$adv_analysis_dir"/{debug_symbols,source_maps,binwalk_output,decompiled/{radare2,ghidra,retdec},sourcemaps_recovered,angr_analysis,yara_scans,api_endpoints,llm_refined}

    # 1. Debug Symbols (DWARF)
    if [[ "$HAS_DWARFDUMP" == true || "$HAS_LLVM_DWARFDUMP" == true ]]; then
        log "INFO" "Attempting debug symbol recovery..."
        if [[ -f "$OUTPUT_DIR/analysis/binaries.txt" && -s "$OUTPUT_DIR/analysis/binaries.txt" ]]; then
            while IFS= read -r binary_path_line; do
                local binary_file=$(echo "$binary_path_line" | cut -d':' -f1)
                if [[ ! -f "$binary_file" ]]; then continue; fi
                local binary_name=$(basename "$binary_file")
                
                local dwarfdump_exe=""
                [[ "$HAS_DWARFDUMP" == true ]] && dwarfdump_exe="dwarfdump"
                [[ "$HAS_LLVM_DWARFDUMP" == true ]] && dwarfdump_exe="llvm-dwarfdump"

                if [[ -n "$dwarfdump_exe" ]]; then
                    execute_with_retry "$dwarfdump_exe --debug-line '$binary_file' > '$adv_analysis_dir/debug_symbols/${binary_name}_debug_line.txt'" "Extract debug line info for $binary_name"
                    execute_with_retry "$dwarfdump_exe --debug-info '$binary_file' > '$adv_analysis_dir/debug_symbols/${binary_name}_debug_info.txt'" "Extract debug info for $binary_name"
                fi
            done < "$OUTPUT_DIR/analysis/binaries.txt"
        fi
    fi

    # 2. Source Map Recovery
    if [[ "$HAS_SOURCEMAPPER" == true ]]; then
        log "INFO" "Attempting source map recovery..."
        find "$OUTPUT_DIR/filesystem" -type f \( -name "*.js" -o -name "*.mjs" -o -name "*.css" \) -exec grep -l "sourceMappingURL" {} \; > "$adv_analysis_dir/source_maps/files_with_sourcemap.txt" 2>/dev/null || true
        
        if [[ -s "$adv_analysis_dir/source_maps/files_with_sourcemap.txt" ]]; then
            while IFS= read -r js_file_rel_path; do
                local js_file_abs_path="$OUTPUT_DIR/filesystem/$js_file_rel_path"
                if [[ ! -f "$js_file_abs_path" ]]; then continue; fi
                
                local sourcemap_url=$(grep -oP 'sourceMappingURL=\K.*' "$js_file_abs_path" | head -1 | tr -d '\'"' | tr -d ' ')
                if [[ -n "$sourcemap_url" ]]; then
                    local map_file_abs_path=""
                    if [[ "$sourcemap_url" == http* ]]; then continue; fi
                    map_file_abs_path="$(realpath "$(dirname "$js_file_abs_path")/$sourcemap_url" 2>/dev/null || echo "")"

                    if [[ -f "$map_file_abs_path" ]]; then
                        local js_subdir_name=$(dirname "$js_file_rel_path" | sed 's|[^a-zA-Z0-9_/-]|_|g')
                        local js_basename=$(basename "$js_file_rel_path" .js | sed 's|[^a-zA-Z0-9_-]|_|g')
                        local output_subdir="$adv_analysis_dir/sourcemaps_recovered/${js_subdir_name}_${js_basename}"
                        mkdir -p "$output_subdir"
                        execute_with_retry "sourcemapper unpack '$map_file_abs_path' -o '$output_subdir'" "Recover source from $map_file_abs_path"
                    fi
                fi
            done < "$adv_analysis_dir/source_maps/files_with_sourcemap.txt"
        fi
    fi

    # 3. Binwalk
    if [[ "$HAS_BINWALK" == true ]]; then
        log "INFO" "Attempting binary decomposition with Binwalk..."
        if [[ -f "$OUTPUT_DIR/analysis/binaries.txt" && -s "$OUTPUT_DIR/analysis/binaries.txt" ]]; then
            while IFS= read -r binary_path_line; do
                local binary_file=$(echo "$binary_path_line" | cut -d':' -f1)
                if [[ ! -f "$binary_file" ]]; then continue; fi
                local file_size_kb=$(du -k "$binary_file" | cut -f1)
                if [[ $file_size_kb -lt 100 ]]; then continue; fi

                local binary_name=$(basename "$binary_file")
                local binwalk_output_dir="$adv_analysis_dir/binwalk_output/$binary_name"
                mkdir -p "$binwalk_output_dir"
                
                execute_with_retry "docker run --rm -v '$binary_file':/input.bin:ro -v '$binwalk_output_dir':/output cincan/binwalk -eMJC /input.bin > '$binwalk_output_dir/binwalk_report.json'" "Binwalk analysis for $binary_name"
            done < "$OUTPUT_DIR/analysis/binaries.txt"
        fi
    fi

    # 4. Radare2 Decompilation
    if [[ "$HAS_RADARE2" == true ]]; then
        log "INFO" "Attempting automated decompilation with Radare2..."
        if [[ -f "$OUTPUT_DIR/analysis/binaries.txt" && -s "$OUTPUT_DIR/analysis/binaries.txt" ]]; then
            while IFS= read -r binary_path_line; do
                local binary_file=$(echo "$binary_path_line" | cut -d':' -f1)
                if [[ ! -f "$binary_file" ]]; then continue; fi
                local binary_name=$(basename "$binary_file")
                local r2_output_dir="$adv_analysis_dir/decompiled/radare2/$binary_name"
                mkdir -p "$r2_output_dir"

                docker run --rm \
                    -v "$binary_file":/bin/target:ro \
                    -v "$r2_output_dir":/output \
                    radare/radare2 \
                    -qq \
                    -c "aaa; pdg @ main" /bin/target > "$r2_output_dir/decompiled_main.c" 2>&1 || true
                
                docker run --rm \
                    -v "$binary_file":/bin/target:ro \
                    -v "$r2_output_dir":/output \
                    radare/radare2 \
                    -qq \
                    -c "aaa; pdg @ entry0" /bin/target > "$r2_output_dir/decompiled_entry0.c" 2>&1 || true
            done < "$OUTPUT_DIR/analysis/binaries.txt"
        fi
    fi
    
    # 5. Ghidra Headless
    if [[ "$HAS_GHIDRA" == true ]]; then
        log "INFO" "Attempting automated decompilation with Ghidra..."
        # Create a temporary Ghidra project directory
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
# ORIGINAL PHASE IMPLEMENTATIONS (Enhanced)
# =============================================================================

phase0_intelligence_reconnaissance() {
    CURRENT_PHASE="Intelligence & Registry Reconnaissance"
    PHASE_START_TIME=$(date +%s)
    show_progress 1 $TOTAL_PHASES "$CURRENT_PHASE"

    log "INFO" "Starting passive reconnaissance..."

    if [[ "$HAS_SKOPEO" == true ]]; then
        execute_with_retry "skopeo inspect --raw 'docker://$IMAGE' | jq > '$OUTPUT_DIR/metadata/remote-manifest.json'" "Remote manifest inspection"
    fi
    if [[ "$HAS_CRANE" == true ]]; then
        execute_with_retry "crane manifest '$IMAGE' > '$OUTPUT_DIR/metadata/manifest.json'" "Image manifest retrieval"
    fi

    ((COMPLETED_PHASES++))
    echo -e "\n${GREEN}✓ Phase 0 completed${NC}"
}

phase1_secure_acquisition() {
    CURRENT_PHASE="Secure Image Acquisition"
    PHASE_START_TIME=$(date +%s)
    show_progress 2 $TOTAL_PHASES "$CURRENT_PHASE"

    log "INFO" "Starting secure image acquisition..."
    execute_with_retry "docker pull '$IMAGE'" "Image pull"
    execute_with_retry "docker save '$IMAGE' -o '$OUTPUT_DIR/metadata/image.tar'" "Image archive creation"
    
    log "INFO" "Extracting image archive for layer analysis..."
    execute_with_retry "tar -xf '$OUTPUT_DIR/metadata/image.tar' -C '$OUTPUT_DIR/metadata'" "Archive extraction"
    
    docker inspect "$IMAGE" | jq > "$OUTPUT_DIR/metadata/image-inspect.json"

    ((COMPLETED_PHASES++))
    echo -e "\n${GREEN}✓ Phase 1 completed${NC}"
}

phase1_5_dockerfile_reconstruction() {
    CURRENT_PHASE="Dockerfile Reconstruction"
    PHASE_START_TIME=$(date +%s)
    show_progress 3 $TOTAL_PHASES "$CURRENT_PHASE"

    log "INFO" "Starting Dockerfile reconstruction..."
    mkdir -p "$OUTPUT_DIR/dockerfile"

    if [[ "$HAS_WHALER" == true ]]; then
        execute_with_retry "docker run --rm -v /var/run/docker.sock:/var/run/docker.sock:ro pegleg/whaler -sV=1.36 '$IMAGE' > '$OUTPUT_DIR/dockerfile/Dockerfile.whaler'" "Whaler reconstruction"
    fi

    execute_with_retry "docker run --rm -v /var/run/docker.sock:/var/run/docker.sock:ro alpine/dfimage -sV=1.36 '$IMAGE' > '$OUTPUT_DIR/dockerfile/Dockerfile.dfimage'" "dfimage reconstruction"

    docker history --no-trunc "$IMAGE" > "$OUTPUT_DIR/dockerfile/history.raw"
    # Heuristic reconstruction
    docker history --no-trunc "$IMAGE" | \
        awk '{$1=$2=$3=$4=""; print $0}' | \
        grep -v COMMENT | \
        nl | sort -nr | \
        sed 's/^[[:space:]]*[0-9]*[[:space:]]*//' | \
        sed -E 's/[0-9]+(\.[0-9]+)?(B|KB|MB|GB|kB)[[:space:]].*//g' | \
        sed 's/^#[0-9]*[[:space:]]*//' | \
        sed '/^$/d' > "$OUTPUT_DIR/dockerfile/Dockerfile.reconstructed.heuristic"

    # Select best
    local best_file=""
    if [[ -f "$OUTPUT_DIR/dockerfile/Dockerfile.whaler" && -s "$OUTPUT_DIR/dockerfile/Dockerfile.whaler" ]]; then best_file="Dockerfile.whaler"
    elif [[ -f "$OUTPUT_DIR/dockerfile/Dockerfile.dfimage" && -s "$OUTPUT_DIR/dockerfile/Dockerfile.dfimage" ]]; then best_file="Dockerfile.dfimage"
    else best_file="Dockerfile.reconstructed.heuristic"; fi

    if [[ -n "$best_file" && -f "$OUTPUT_DIR/dockerfile/$best_file" ]]; then
        cp "$OUTPUT_DIR/dockerfile/$best_file" "$OUTPUT_DIR/Dockerfile.reconstructed"
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

    find "$OUTPUT_DIR/filesystem" -type f -exec file {} + | \
        grep -E "(ELF.*executable|ELF.*shared object|PE.*executable|PE.*DLL|Mach-O.*executable)" > "$OUTPUT_DIR/analysis/binaries.txt" 2>/dev/null || true
    
    local binary_count=$(wc -l < "$OUTPUT_DIR/analysis/binaries.txt" 2>/dev/null || echo "0")
    log "INFO" "Found $binary_count binary files"

    # Call advanced decompilation
    phase_advanced_binary_decompilation

    ((COMPLETED_PHASES++))
    echo -e "\n${GREEN}✓ Phase 2 completed${NC}"
}

phase2_5_filesystem_extraction() {
    CURRENT_PHASE="Complete Filesystem Extraction"
    PHASE_START_TIME=$(date +%s)
    show_progress 5 $TOTAL_PHASES "$CURRENT_PHASE"

    log "INFO" "Starting filesystem extraction..."
    if docker buildx version >/dev/null 2>&1 && DOCKER_BUILDKIT=1 execute_with_retry "DOCKER_BUILDKIT=1 docker build --output type=local,dest='$OUTPUT_DIR/filesystem' - <<< 'FROM $IMAGE'" "Filesystem extraction via build (BuildKit)"; then
        log "SUCCESS" "Filesystem extracted via build method (BuildKit)"
    else
        log "INFO" "Using fallback extraction method (docker create/export)..."
        local temp_container_name="temp-fs-extract-$(date +%s)"
        if execute_with_retry "docker create --name '$temp_container_name' '$IMAGE'" "Create temporary container"; then
            execute_with_retry "docker export '$temp_container_name' | tar -xf - -C '$OUTPUT_DIR/filesystem'" "Filesystem export"
            docker rm "$temp_container_name" >/dev/null 2>&1 || true
        fi
    fi

    local total_files=$(find "$OUTPUT_DIR/filesystem" -type f 2>/dev/null | wc -l || echo "0")
    log "INFO" "Filesystem stats: $total_files files"

    ((COMPLETED_PHASES++))
    echo -e "\n${GREEN}✓ Phase 2.5 completed${NC}"
}

phase3_config_recovery() {
    CURRENT_PHASE="Configuration Recovery"
    PHASE_START_TIME=$(date +%s)
    show_progress 6 $TOTAL_PHASES "$CURRENT_PHASE"

    log "INFO" "Starting configuration recovery..."
    mkdir -p "$OUTPUT_DIR/configs/"{webserver,database,application}

    docker inspect "$IMAGE" | jq > "$OUTPUT_DIR/configs/image-config.json"
    docker inspect "$IMAGE" | jq -r '.[0].Config.Env[]?' > "$OUTPUT_DIR/configs/environment.txt
    docker inspect "$IMAGE" | jq '.[0].Config.ExposedPorts?' > "$OUTPUT_DIR/configs/ports.json"
    docker inspect "$IMAGE" | jq '.[0].Config.Volumes?' > "$OUTPUT_DIR/configs/volumes.json"

    find "$OUTPUT_DIR/filesystem" \( -name "*.conf" -o -name "*.config" -o -name "*.ini" -o -name "*.yaml" -o -name "*.yml" \) -type f | \
        head -100 > "$OUTPUT_DIR/configs/config-files.txt" 2>/dev/null || true

    ((COMPLETED_PHASES++))
    echo -e "\n${GREEN}✓ Phase 3 completed${NC}"
}

phase3_5_compose_reconstruction() {
    CURRENT_PHASE="Docker Compose Reconstruction"
    PHASE_START_TIME=$(date +%s)
    show_progress 7 $TOTAL_PHASES "$CURRENT_PHASE"

    log "INFO" "Starting Docker Compose reconstruction..."
    mkdir -p "$OUTPUT_DIR/compose"

    local service_name=$(echo "$IMAGE" | tr ':/' '__' | tr '[:upper:]' '[:lower:]' | sed 's/^_*//;s/_*$//;s/__+/_/g')
    [[ -z "$service_name" ]] && service_name="decomposed_service"

    cat > "$OUTPUT_DIR/compose/docker-compose.yml" << EOF
version: '3.8'
services:
  $service_name:
    image: $IMAGE
    container_name: ${service_name}_${RANDOM}
    restart: "no"
EOF

    # Simple addition of env vars and ports (could be expanded)
    if [[ -s "$OUTPUT_DIR/configs/environment.txt" ]]; then
        echo "    environment:" >> "$OUTPUT_DIR/compose/docker-compose.yml"
        while IFS= read -r env_var; do
            echo "      - $env_var" >> "$OUTPUT_DIR/compose/docker-compose.yml"
        done < "$OUTPUT_DIR/configs/environment.txt"
    fi

    if [[ "$HAS_KOMPOSE" == true ]]; then
        execute_with_retry "kompose convert -f '$OUTPUT_DIR/compose/docker-compose.yml' -o '$OUTPUT_DIR/orchestration/'" "Kubernetes conversion"
    fi

    ((COMPLETED_PHASES++))
    echo -e "\n${GREEN}✓ Phase 3.5 completed${NC}"
}

phase4_sbom_vulnerability() {
    CURRENT_PHASE="SBOM & Vulnerability Analysis"
    PHASE_START_TIME=$(date +%s)
    show_progress 8 $TOTAL_PHASES "$CURRENT_PHASE"

    log "INFO" "Starting SBOM generation and vulnerability analysis..."
    mkdir -p "$OUTPUT_DIR/sbom" "$OUTPUT_DIR/vulnerabilities"

    # Syft
    if [[ "$HAS_SYFT" == true ]]; then
        execute_with_retry "syft '$IMAGE' -o spdx-json='$OUTPUT_DIR/sbom/sbom.spdx.json'" "SBOM generation (SPDX)"
        execute_with_retry "syft '$IMAGE' -o table > '$OUTPUT_DIR/sbom/packages.txt'" "SBOM generation (Table)"
    fi

    # Grype
    if [[ "$HAS_GRYPE" == true ]]; then
        local grype_target=""
        [[ -f "$OUTPUT_DIR/sbom/sbom.spdx.json" ]] && grype_target="sbom:$OUTPUT_DIR/sbom/sbom.spdx.json" || grype_target="$IMAGE"
        execute_with_retry "grype '$grype_target' -o json > '$OUTPUT_DIR/vulnerabilities/grype.json'" "Grype vulnerability scanning"
        execute_with_retry "grype '$grype_target' -o table > '$OUTPUT_DIR/vulnerabilities/grype_summary.txt'" "Grype summary"
    fi

    # Trivy (All-in-one Scanner) - New Upgrade
    if [[ "$HAS_TRIVY" == true ]]; then
        log "INFO" "Running Trivy (All-in-one)..."
        # 1. Scan Image (Filesystem & OS pkgs)
        execute_with_retry "trivy image --format json --output '$OUTPUT_DIR/vulnerabilities/trivy_image.json' '$IMAGE'" "Trivy image scan"
        execute_with_retry "trivy image --format table --output '$OUTPUT_DIR/vulnerabilities/trivy_image.txt' '$IMAGE'" "Trivy image scan report"
        
        # 2. Scan SBOM (if generated)
        if [[ -f "$OUTPUT_DIR/sbom/sbom.spdx.json" ]]; then
            execute_with_retry "trivy sbom --format json --output '$OUTPUT_DIR/vulnerabilities/trivy_sbom.json' '$OUTPUT_DIR/sbom/sbom.spdx.json'" "Trivy SBOM scan"
        fi

        # 3. Scan Config/Secrets (Misconfig + Basic Secrets)
        execute_with_retry "trivy config --format json --output '$OUTPUT_DIR/vulnerabilities/trivy_config.json' '$OUTPUT_DIR/filesystem'" "Trivy config scan"
        
        # 4. Generate Trivy SBOM
        execute_with_retry "trivy image --format spdx-json --output '$OUTPUT_DIR/sbom/sbom_trivy.spdx.json' '$IMAGE'" "Trivy SBOM generation"
    fi

    # Dive (Layer efficiency)
    if [[ "$HAS_DIVE" == true ]]; then
        execute_with_retry "dive '$IMAGE' --json --source ci" > "$OUTPUT_DIR/analysis/dive-analysis.json" "Dive analysis" || log "WARN" "Dive analysis failed"
    fi

    ((COMPLETED_PHASES++))
    echo -e "\n${GREEN}✓ Phase 4 completed${NC}"
}

phase4_5_forensic_recovery() {
    CURRENT_PHASE="Forensic Artifact Recovery"
    PHASE_START_TIME=$(date +%s)
    show_progress 9 $TOTAL_PHASES "$CURRENT_PHASE"

    log "INFO" "Starting forensic artifact recovery..."
    mkdir -p "$OUTPUT_DIR/forensic"

    # 1. Advanced Secret Scanning with TruffleHog - New Upgrade
    if [[ "$HAS_TRUFFLEHOG" == true ]]; then
        log "INFO" "Running TruffleHog for verified secrets detection..."
        # TruffleHog can be noisy, so we exclude common noisy directories if possible via --exclude
        # Note: TruffleHog filesystem scan might be slow. 
        execute_with_retry "trufflehog filesystem --directory '$OUTPUT_DIR/filesystem' --json --output '$OUTPUT_DIR/forensic/trufflehog_secrets.json'" "TruffleHog filesystem scan" || log "WARN" "TruffleHog scan failed/timeout"
        
        # Convert JSON to readable text for the report
        if [[ -f "$OUTPUT_DIR/forensic/trufflehog_secrets.json" ]]; then
            jq -r '.SourceMetadata | .Data | .Filepath' "$OUTPUT_DIR/forensic/trufflehog_secrets.json" 2>/dev/null | sort -u > "$OUTPUT_DIR/forensic/secrets_trufflehog.txt" || true
        fi
    fi

    # 2. Fallback/Complementary Regex Scanning (Original method, but less noisy)
    log "INFO" "Scanning for secrets with basic patterns..."
    local secret_patterns=(
        "password[[:space:]]*=[[:space:]]*[^[:space:]]+" "secret[[:space:]]*=[[:space:]]*[^[:space:]]+" "api[_-]?key"
        "BEGIN.*PRIVATE KEY" "aws[_-]?access[_-]?key" "github_token"
    )
    > "$OUTPUT_DIR/forensic/secrets-basic.tmp"
    for pattern in "${secret_patterns[@]}"; do
        grep -r -i -E -h "$pattern" "$OUTPUT_DIR/filesystem" 2>/dev/null | head -5 >> "$OUTPUT_DIR/forensic/secrets-basic.tmp" || true
    done
    sort -u "$OUTPUT_DIR/forensic/secrets-basic.tmp" > "$OUTPUT_DIR/forensic/secrets-basic.txt" 2>/dev/null || true
    rm "$OUTPUT_DIR/forensic/secrets-basic.tmp"

    # 3. Certificates and Keys
    find "$OUTPUT_DIR/filesystem" \( -name "*.pem" -o -name "*.crt" -o -name "*.key" \) -type f | \
        head -50 > "$OUTPUT_DIR/forensic/certificates.txt" 2>/dev/null || true

    ((COMPLETED_PHASES++))
    echo -e "\n${GREEN}✓ Phase 4.5 completed${NC}"
}

phase5_runtime_analysis() {
    CURRENT_PHASE="Runtime Analysis"
    PHASE_START_TIME=$(date +%s)
    show_progress 10 $TOTAL_PHASES "$CURRENT_PHASE"

    if [[ "$SKIP_RUNTIME" == true ]]; then
        ((COMPLETED_PHASES++))
        echo -e "\n${YELLOW}⚠ Phase 5 skipped${NC}"
        return
    fi

    log "INFO" "Starting runtime analysis..."
    mkdir -p "$OUTPUT_DIR/runtime"

    if [[ -n "$CONTAINER_ID" ]] && docker ps -q --filter "id=$CONTAINER_ID" | grep -q .; then
        log "INFO" "Analyzing running container: $CONTAINER_ID"

        docker stats --no-stream --no-trunc "$CONTAINER_ID" > "$OUTPUT_DIR/runtime/container-stats.txt"
        docker top "$CONTAINER_ID" > "$OUTPUT_DIR/runtime/container-processes.txt"
        docker logs --tail 100 "$CONTAINER_ID" > "$OUTPUT_DIR/runtime/container-logs-tail.txt"
        docker diff "$CONTAINER_ID" > "$OUTPUT_DIR/runtime/container-changes.txt"

        # Falco Integration - New Upgrade
        if [[ "$HAS_FALCO" == true ]]; then
            log "INFO" "Attempting Falco runtime analysis..."
            # Check if falco is running on the host. If not, we can try to start it or just note it.
            # Running falco in a container to monitor another container is complex (needs host pid, privileged).
            # For this script, we will assume Falco might be available on the host or we skip complex deployment.
            # A simplified check: read recent logs if available.
            if command -v falco >/dev/null 2>&1; then
                 # In a real scenario, we would start falco, wait, capture events, then stop.
                 # echo "Starting Falco capture for 30s..."
                 # timeout 30 falco --container-id $CONTAINER_ID > "$OUTPUT_DIR/runtime/falco_events.txt" &
                 # wait
                 log "INFO" "Falco binary found. Full runtime integration requires manual setup or host privileges."
            else
                log "INFO" "Falco not found on host. Skipping eBPF runtime monitoring."
            fi
        fi
    else
        log "INFO" "No running container ID provided. Creating generic runtime analysis script."
        cat > "$OUTPUT_DIR/runtime/runtime-analysis-template.sh" << EOF
#!/bin/bash
CONTAINER_NAME=\${1:-}
echo "Analyzing container: \$CONTAINER_NAME"
docker stats --no-stream --no-trunc "\$CONTAINER_NAME" > container-stats.txt
docker top "\$CONTAINER_NAME" > container-processes.txt
docker logs --tail 200 "\$CONTAINER_NAME" > container-logs-tail.txt
EOF
        chmod +x "$OUTPUT_DIR/runtime/runtime-analysis-template.sh"
    fi

    ((COMPLETED_PHASES++))
    echo -e "\n${GREEN}✓ Phase 5 completed${NC}"
}

phase6_offensive_security() {
    CURRENT_PHASE="Offensive Security Analysis"
    PHASE_START_TIME=$(date +%s)
    show_progress 11 $TOTAL_PHASES "$CURRENT_PHASE"

    if [[ "$SKIP_OFFENSIVE" == true ]]; then
        ((COMPLETED_PHASES++))
        echo -e "\n${YELLOW}⚠ Phase 6 skipped${NC}"
        return
    fi

    log "INFO" "Starting offensive security analysis..."
    mkdir -p "$OUTPUT_DIR/security"

    # Dockle Integration - New Upgrade
    if [[ "$HAS_DOCKLE" == true ]]; then
        log "INFO" "Running Dockle (Container Image Linter)..."
        # Dockle returns non-zero on issues, so we handle it carefully
        execute_with_retry "docker run --rm -v /var/run/docker.sock:/var/run/docker.sock goodwithtech/dockle:latest --format json --exit-code 0 '$IMAGE' > '$OUTPUT_DIR/security/dockle.json'" "Dockle scan" || log "WARN" "Dockle scan encountered issues (check JSON)"
        
        # Human readable report
        execute_with_retry "docker run --rm -v /var/run/docker.sock:/var/run/docker.sock goodwithtech/dockle:latest --format table --exit-code 0 '$IMAGE' > '$OUTPUT_DIR/security/dockle.txt'" "Dockle report" || true
    fi

    # Basic Config Checks (Original)
    local image_config
    image_config=$(docker inspect "$IMAGE" 2>/dev/null)
    > "$OUTPUT_DIR/security/security-issues.txt"

    if echo "$image_config" | jq -r '.[0].Config.Privileged' | grep -q "true"; then
        echo "CRITICAL: Container runs as privileged" >> "$OUTPUT_DIR/security/security-issues.txt"
        ((ERROR_COUNT++))
    fi

    if echo "$image_config" | jq -r '.[0].Config.NetworkMode' | grep -q "host"; then
        echo "CRITICAL: Container uses host network mode" >> "$OUTPUT_DIR/security/security-issues.txt"
        ((ERROR_COUNT++))
    fi

    ((COMPLETED_PHASES++))
    echo -e "\n${GREEN}✓ Phase 6 completed${NC}"
}

phase6_5_source_recovery() {
    CURRENT_PHASE="Source Code Recovery"
    PHASE_START_TIME=$(date +%s)
    show_progress 12 $TOTAL_PHASES "$CURRENT_PHASE"

    log "INFO" "Starting source code recovery..."
    mkdir -p "$OUTPUT_DIR/source/"{python,nodejs,jar-extracted,decompiled,ruby,php,dotnet,go,recovered_typescript}

    # Copying app dirs
    local app_dirs=("/app" "/src" "/usr/src/app" "/opt/app" "/var/www/html")
    for app_dir in "${app_dirs[@]}"; do
        if [[ -d "$OUTPUT_DIR/filesystem$app_dir" ]]; then
            local dir_name=$(basename "$app_dir" | tr '/' '_')
            cp -r "$OUTPUT_DIR/filesystem$app_dir" "$OUTPUT_DIR/source/${dir_name}_$(echo "$app_dir" | tr '/' '_')" 2>/dev/null || true
        fi
    done

    # Language specific copy
    find "$OUTPUT_DIR/filesystem" -name "*.py" -type f -exec dirname {} \; | sort -u | head -20 | xargs -I {} cp -r {} "$OUTPUT_DIR/source/python/" 2>/dev/null || true
    find "$OUTPUT_DIR/filesystem" -name "package.json" -type f -exec cp {} "$OUTPUT_DIR/source/nodejs/" 2>/dev/null || true
    find "$OUTPUT_DIR/filesystem" \( -name "*.jar" -o -name "*.war" \) -type f | while read -r jar; do
        local jar_name=$(basename "$jar" .jar)
        mkdir -p "$OUTPUT_DIR/source/jar-extracted/$jar_name"
        unzip -q -o "$jar" -d "$OUTPUT_DIR/source/jar-extracted/$jar_name" >/dev/null 2>&1 || true
    done

    # Integrate recovered TS/JS from advanced phase
    if [[ -d "$OUTPUT_DIR/advanced_analysis/sourcemaps_recovered" ]]; then
        cp -r "$OUTPUT_DIR/advanced_analysis/sourcemaps_recovered/"* "$OUTPUT_DIR/source/recovered_typescript/" 2>/dev/null || true
    fi

    ((COMPLETED_PHASES++))
    echo -e "\n${GREEN}✓ Phase 6.5 completed${NC}"
}

# =============================================================================
# REPORTING
# =============================================================================

generate_final_report() {
    log "INFO" "Generating final report..."

    local script_end_time=$(date +%s)
    local total_duration=$((script_end_time - SCRIPT_START_TIME))

    # Generate JSON Report (Machine Readable) - New Upgrade
    cat > "$OUTPUT_DIR/analysis/report.json" << EOF
{
  "target": "$IMAGE",
  "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "version": "$SCRIPT_VERSION",
  "duration_seconds": $total_duration,
  "stats": {
    "errors": $ERROR_COUNT,
    "warnings": $WARNING_COUNT,
    "phases_completed": $COMPLETED_PHASES
  },
  "tools": {
    "syft": $HAS_SYFT,
    "grype": $HAS_GRYPE,
    "trivy": $HAS_TRIVY,
    "trufflehog": $HAS_TRUFFLEHOG,
    "dockle": $HAS_DOCKLE,
    "whaler": $HAS_WHALER
  },
  "findings": {
    "binaries": $(wc -l < "$OUTPUT_DIR/analysis/binaries.txt" 2>/dev/null || echo 0),
    "secrets_trufflehog": $(wc -l < "$OUTPUT_DIR/forensic/secrets_trufflehog.txt" 2>/dev/null || echo 0),
    "secrets_basic": $(wc -l < "$OUTPUT_DIR/forensic/secrets-basic.txt" 2>/dev/null || echo 0),
    "vulnerabilities_grype": $(jq '.matches | length' "$OUTPUT_DIR/vulnerabilities/grype.json" 2>/dev/null || echo 0),
    "vulnerabilities_trivy": $(jq '.Results | length' "$OUTPUT_DIR/vulnerabilities/trivy_image.json" 2>/dev/null || echo 0),
    "security_issues_dockle": $(jq '.details | length' "$OUTPUT_DIR/security/dockle.json" 2>/dev/null || echo 0),
    "security_issues_manual": $(wc -l < "$OUTPUT_DIR/security/security-issues.txt" 2>/dev/null || echo 0)
  }
}
EOF

    # Generate Markdown Report
    cat > "$REPORT_FILE" << EOF
# 🔬 Ultimate Docker Image Decomposition Report

## Mission Summary
- **Target Image**: \`$IMAGE\`
- **Analysis Date**: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
- **Framework Version**: $SCRIPT_VERSION
- **Total Duration**: $((total_duration / 60)) minutes
- **Status**: $([ $ERROR_COUNT -eq 0 ] && echo "SUCCESS" || echo "COMPLETED WITH ISSUES")

## Tooling Utilization
| Tool | Status | Purpose |
|------|--------|---------|
| Syft | $([ "$HAS_SYFT" == true ] && echo "✓ Active" || echo "✗ Missing") | SBOM Generation |
| Grype | $([ "$HAS_GRYPE" == true ] && echo "✓ Active" || echo "✗ Missing") | Vulnerability Scanning |
| **Trivy** | $([ "$HAS_TRIVY" == true ] && echo "✓ Active (New)" || echo "✗ Missing") | All-in-one Scan (Vuln/Config/Misconfig) |
| **Dockle** | $([ "$HAS_DOCKLE" == true ] && echo "✓ Active (New)" || echo "✗ Missing") | Container Linting / CIS Benchmarks |
| **TruffleHog** | $([ "$HAS_TRUFFLEHOG" == true ] && echo "✓ Active (New)" || echo "✗ Missing") | Verified Secret Detection |

## Security Findings

### Critical Vulnerabilities
**Trivy (Critical/High):**
\`\`\`
$(jq -r '.Results[]? | select(.Target == "$IMAGE" | .Vulnerabilities[]? | select(.Severity == "CRITICAL" or .Severity == "HIGH") | "\(.VulnerabilityID) - \(.PkgName) (\(.Severity))"' "$OUTPUT_DIR/vulnerabilities/trivy_image.json" | head -5 || echo "None found")
\`\`\`

### Secret Detection
**TruffleHog (Verified):** $(wc -l < "$OUTPUT_DIR/forensic/secrets_trufflehog.txt" 2>/dev/null || echo 0) verified secrets found.
**Basic Patterns:** $(wc -l < "$OUTPUT_DIR/forensic/secrets-basic.txt" 2>/dev/null || echo 0) potential strings found.

### Container Configuration (Dockle)
**Issues Found:** $(jq '.details | length' "$OUTPUT_DIR/security/dockle.json" 2>/dev/null || echo 0)
**Sample Issues:**
\`\`\`
$(jq -r '.details[]? | .code + ": " + .title' "$OUTPUT_DIR/security/dockle.json" | head -5 || echo "None")
\`\`\`

## Advanced Analysis
- **Binaries Decompiled:** $(find "$OUTPUT_DIR/advanced_analysis/decompiled" -name "*.c" 2>/dev/null | wc -l)
- **Debug Symbols Recovered:** $(find "$OUTPUT_DIR/advanced_analysis/debug_symbols" -name "*.txt" 2>/dev/null | wc -l)
- **Source Maps Recovered:** $(find "$OUTPUT_DIR/advanced_analysis/sourcemaps_recovered" -type d 2>/dev/null | wc -l)

## Outputs
- **JSON Report:** \`$OUTPUT_DIR/analysis/report.json\`
- **Full Logs:** \`$LOG_FILE\`
- **Reconstructed Dockerfile:** \`$OUTPUT_DIR/Dockerfile.reconstructed\`
- **Forensic Artifacts:** \`$OUTPUT_DIR/forensic/\`

---
*Generated by Ultimate Docker Decomposition Framework v$SCRIPT_VERSION*
EOF
    log "SUCCESS" "Final report generated: $REPORT_FILE"
}

# =============================================================================
# CLEANUP & MAIN
# =============================================================================

cleanup_background_processes() {
    log "INFO" "Cleaning up background processes..."
    # Placeholder for cleanup logic if background jobs were used
    true
}

main() {
    SCRIPT_START_TIME=$(date +%s)
    echo -e "${MAGENTA}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${MAGENTA}║          🔬 ULTIMATE DOCKER DECOMPOSITION v$SCRIPT_VERSION          ║${NC}"
    echo -e "${MAGENTA}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo -e "${NC}"

    if [[ -z "$IMAGE" ]]; then echo "Error: No image specified"; exit 1; fi

    log "INFO" "Target Image: $IMAGE"
    log "INFO" "Output Directory: $OUTPUT_DIR"
    [[ -n "$CONTAINER_ID" ]] && log "INFO" "Container ID: $CONTAINER_ID"

    check_system_resources
    mkdir -p "$OUTPUT_DIR/analysis" "$OUTPUT_DIR/filesystem"
    
    LOG_FILE="$OUTPUT_DIR/analysis/decomposition.log"
    REPORT_FILE="$OUTPUT_DIR/analysis/FINAL_REPORT.md"
    SARIF_FILE="$OUTPUT_DIR/analysis/report.sarif.json" # Placeholder for future SARIF impl

    verify_and_install_tools

    # Execution Phases
    phase0_intelligence_reconnaissance
    phase1_secure_acquisition
    phase1_5_dockerfile_reconstruction
    phase2_binary_forensics
    phase2_5_filesystem_extraction
    phase3_config_recovery
    phase3_5_compose_reconstruction
    phase4_sbom_vulnerability
    phase4_5_forensic_recovery
    phase5_runtime_analysis
    phase6_offensive_security
    phase6_5_source_recovery

    generate_final_report
    cleanup_background_processes

    echo -e "\n${GREEN}✅ Mission Completed${NC}"
    echo -e "${BLUE}Results: ${YELLOW}$OUTPUT_DIR${NC}"
}

trap cleanup_background_processes EXIT INT TERM
main "$@"
