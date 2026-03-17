# 🔬 ADVANCED DOCKER IMAGE DECOMPOSITION & REVERSE ENGINEERING FRAMEWORK
## **January 2026 Edition** — Research-Validated Toolchain

> **Mission**: Complete reconstruction of Docker images → Dockerfile, docker-compose, application source, configs, secrets, and runtime state recovery through passive reconnaissance to active forensic extraction.

---

## 📋 **TABLE OF CONTENTS**
1. [Phase 0: Intelligence & Registry Reconnaissance](#phase-0)
2. [Phase 1: Secure Acquisition & Filesystem Extraction](#phase-1)
3. [Phase 1.5: Dockerfile & Build Reconstruction](#phase-15)
4. [Phase 2: Binary Forensics & Static Reverse Engineering](#phase-2)
5. [Phase 2.5: Application File & Configuration Extraction](#phase-25)
6. [Phase 3: Deep Config & Dockerfile Reconstruction](#phase-3)
7. [Phase 3.5: Docker Compose Reconstruction](#phase-35)
8. [Phase 4: Vulnerability & Supply Chain Deep Dive (SBOM)](#phase-4)
9. [Phase 4.5: Forensic & Deep Artifact Recovery](#phase-45)
10. [Phase 5: Dynamic Runtime & eBPF Observability](#phase-5)
11. [Phase 5.5: Orchestration & Manifest Recovery](#phase-55)
12. [Phase 6: Offensive Security & Escalation (Red Team)](#phase-6)
13. [Phase 6.5: Source Code & Binary Recovery](#phase-65)
14. [Phase 7: Orchestration Recovery & State Dump](#phase-7)

---

<a name="phase-0"></a>
## ┌─────────────────────────────────────────────────────────────────┐
## │ **PHASE 0: INTELLIGENCE & REGISTRY RECONNAISSANCE (PASSIVE)**   │
## └─────────────────────────────────────────────────────────────────┘
**Goal**: Gather intel without downloading the full image or running code.

### **Core Tools**
- **Notary / Sigstore Cosign** — Verify signature & authenticity
- **Skopeo** *(active)* — Inspect manifests/layers remotely
  - `skopeo inspect docker://registry.io/image:tag`
- **Crane** *(active)* — Copy images & debug registry layout (Google's go-containerregistry)
- **Regclient** *(active)* — Registry client for quick inspections
- **Registry (Docker Distribute)** — CLI to query Docker Registry API
- **Shhgit** *(active)* — Scan GitHub for secrets related to images

### **Usage Pattern**
```bash
# Remote inspection without pulling
skopeo inspect --raw docker://nginx:latest | jq
crane manifest nginx:latest
```

---

<a name="phase-1"></a>
## ┌─────────────────────────────────────────────────────────────────┐
## │ **PHASE 1: SECURE ACQUISITION & FILESYSTEM EXTRACTION**         │
## └─────────────────────────────────────────────────────────────────┘
**Goal**: Safely extract filesystems without executing the container entrypoint.

### **Core Tools**
- **Umoci** *(active)* — Manipulate OCI images (raw extraction)
- **Dive** *(active)* — Analyze layer sizes & wasted space
  - *Reference: Widely used for layer-by-layer image exploration (2023-2025)*
- **Tern** *(active)* — Cross-layer component inventory (SBOM generation)
- **Dockle** *(active)* — CI/CD friendly container linter
- **Container-diff** *(active)* — Diff images to find changes between versions

### **Usage Pattern**
```bash
# Extract complete filesystem using Docker 18.09+ build output
docker build --output type=local,dest=./rootfs - <<< "FROM myimage:tag"

# Alternative: Traditional export method
docker create --name temp myimage:tag
docker export temp | tar -xvf -
docker rm temp
```

---

<a name="phase-15"></a>
## ┌─────────────────────────────────────────────────────────────────┐
## │ **PHASE 1.5: DOCKERFILE & BUILD RECONSTRUCTION** *(NEW 2025)*   │
## └─────────────────────────────────────────────────────────────────┘
**Goal**: Reverse-engineer Dockerfile from image metadata and layer history.

### **Advanced Reconstruction Tools**
- **Whaler** *(Go-based)* — Reverse engineer Docker images into Dockerfiles
  - *Reference: P3GLEG/Whaler on GitHub - analyzes layer metadata*
  ```bash
  docker run -v /var/run/docker.sock:/var/run/docker.sock:ro \
    pegleg/whaler -sV=1.36 nginx:latest
  ```

- **dfimage (Dockerfile-from-Image)** — Python script for Dockerfile recreation
  - *Reference: LanikSJ/dfimage - packaged as Docker image*
  
- **Dedockify** — Automated Dockerfile generator with ordered output
  - *Reference: DZone 2020 article on reverse engineering*

- **docker history --no-trunc** — Native command showing complete layer commands
  ```bash
  # Advanced parsing technique (June 2025)
  docker history --no-trunc python | awk '{$1=$2=$3=$4=""; print $0}' | \
    grep -v COMMENT | nl | sort -nr | sed 's/^[^A-Z]*//' | \
    sed -E 's/[0-9]+(\.[0-9]+)?(B|KB|MB|GB|kB)[[:space:]].*//g'
  ```

- **Portainer** — Web UI displaying image layer details and configurations

---

<a name="phase-2"></a>
## ┌─────────────────────────────────────────────────────────────────┐
## │ **PHASE 2: BINARY FORENSICS & STATIC REVERSE ENGINEERING**      │
## └─────────────────────────────────────────────────────────────────┘
**Goal**: Reverse engineer proprietary binaries found inside layers.

### **Core Tools**
- **Ghidra** *(active)* — NSA-grade binary decompiler
- **Cutter / Rizin** *(active)* — GUI for advanced binary analysis
- **Binwalk** *(active)* — Extract embedded filesystems/firmware
- **Strings (GNU)** — Extract readable ASCII/Unicode strings
- **Lumina** *(active)* — Reverse engineering hash lookup
- **Capstone** *(active)* — Lightweight multi-architecture disassembler

---

<a name="phase-25"></a>
## ┌─────────────────────────────────────────────────────────────────┐
## │ **PHASE 2.5: APPLICATION FILE & CONFIG EXTRACTION** *(NEW)*     │
## └─────────────────────────────────────────────────────────────────┘
**Goal**: Extract source code, configurations, and application artifacts.

### **Filesystem Extraction**
- **docker-layer-extract** — CLI utility to extract individual layer tarballs
- **docker save + tar extraction** — Manual layered structure extraction
  ```bash
  docker save myimage:tag -o image.tar
  tar -xvf image.tar
  # Examine: manifest.json, config files, layer.tar archives
  ```

- **Crane export** — Google's tool (note: may produce incomplete results)
- **containerd + ctr** — Mount images directly (Docker Engine 26.0+)

### **Configuration Recovery**
- **docker inspect** — Extract complete container/image JSON configuration
- **docker ps --filter + labels** — Find docker-compose.yml location
  ```bash
  # Find compose project from running container
  docker inspect <container> --format \
    '{{ index .Config.Labels "com.docker.compose.project" }}'
  ```
- **jq** — Parse JSON configurations from docker inspect output

---

<a name="phase-3"></a>
## ┌─────────────────────────────────────────────────────────────────┐
## │ **PHASE 3: DEEP CONFIG & DOCKERFILE RECONSTRUCTION**            │
## └─────────────────────────────────────────────────────────────────┘
**Goal**: Reconstruct the build logic and configuration.

### **Core Tools**
- **docker history --no-trunc** — Raw source of truth for layers
- **Deja** *(active)* — Dockerfile generator from filesystem changes
- **Limon** *(active)* — Advanced container filesystem analyzer
- **Hadolint** *(active)* — Dockerfile Super-Linter
- **Conftest** *(active)* — Test configuration files against Open Policy Agent

---

<a name="phase-35"></a>
## ┌─────────────────────────────────────────────────────────────────┐
## │ **PHASE 3.5: DOCKER COMPOSE RECONSTRUCTION** *(NEW)*            │
## └─────────────────────────────────────────────────────────────────┘
**Goal**: Reverse Kubernetes/containers to docker-compose format.

### **Compose Generation Tools**
- **Kompose** *(Bidirectional Converter)* — Compose ↔ Kubernetes manifests
  - *Reference: Supports v1 and v2 compose formats (2025 updates)*
  ```bash
  # K8s → Compose
  kompose convert -f k8s-deployment.yaml -o docker-compose.yaml
  
  # Compose → K8s
  kompose convert -f docker-compose.yml
  ```

- **Docker Compose Bridge** — Built-in Docker transformation
- **kubectl get + kubectl-neat** — Export/clean K8s resources for compose reconstruction

### **Container State Recovery**
- **docker commit** — Capture all file modifications since container start
  - *Reference: Creates new image layer with all changes*
- **docker diff** — Show filesystem changes in running containers
- **Layer manipulation** — Extract/modify/restore specific layers

---

<a name="phase-4"></a>
## ┌─────────────────────────────────────────────────────────────────┐
## │ **PHASE 4: VULNERABILITY & SUPPLY CHAIN DEEP DIVE (SBOM)**      │
## └─────────────────────────────────────────────────────────────────┘
**Goal**: Find CVEs and map the software supply chain.

### **SBOM Generation & Scanning (2025 Enhanced)**
- **Syft** *(Anchore, 5.4K+ GitHub stars)* — High-quality SBOM generator
  - *Reference: CLI tool generating SBOMs in JSON, CycloneDX, SPDX formats*
  - Supports 40+ package ecosystems (Alpine, Debian, RPM, Go, Python, Java, JavaScript, Ruby, Rust, PHP, .NET, etc.)
  ```bash
  # Generate SBOM
  syft alpine:latest -o spdx-json=sbom.json
  
  # Scan container image
  syft packages ubuntu:latest
  ```

- **Grype** *(Anchore, 7.4K+ stars)* — Vulnerability scanner for SBOMs
  - *Reference: Scans container images, filesystems, SBOMs for CVEs*
  - Pulls from NVD, Alpine SecDB, Red Hat, GitHub Security Advisories, Wolfi SecDB
  ```bash
  # Scan image directly
  grype alpine:latest
  
  # Scan from SBOM (faster)
  syft -o json docker.io/myapp:latest | grype
  
  # Output formats: JSON, CycloneDX, SARIF
  grype -o json alpine:latest > vulnerabilities.json
  ```

- **Trivy** *(active)* — Full-stack scanner (filesystems, Git repos, configs)
- **Microsoft SBOM Tool** *(active)* — Generates SPDX 2.2 SBOMs
- **Snyk** *(active)* — Commercial-grade open source scanner
- **Dependency-Track** *(active)* — Analyze supply chain vulnerabilities
- **Grant** *(Anchore)* — License compliance scanning for SBOM packages

### **Integration Pattern (2025)**
```bash
# Combined SBOM + Vulnerability workflow
syft alpine:latest -o cyclonedx-json=sbom.json
grype sbom:sbom.json -o json > vulnerabilities.json

# Merge for 360° view
jq -s '.[0] + .[1]' sbom.json vulnerabilities.json > complete-analysis.json
```

---

<a name="phase-45"></a>
## ┌─────────────────────────────────────────────────────────────────┐
## │ **PHASE 4.5: FORENSIC & DEEP ARTIFACT RECOVERY** *(NEW)*        │
## └─────────────────────────────────────────────────────────────────┘
**Goal**: Advanced forensic analysis and deleted file recovery.

### **Docker Forensics Toolkit (dof)**
*Reference: docker-forensics-toolkit/toolkit on GitHub - post-mortem analysis suite*

**Capabilities**:
- `mount-container` — Mount overlay2 filesystems
- `carve-for-deleted-docker-files` — Recover deleted configs, Dockerfiles, logs
- `show-container-config` — Pretty-print config.v2.json + hostconfig.json
- `macrobber-container-layer` — Timeline analysis of container layers

```bash
# Mount forensic image
python src/dof/main.py mount-image testimages/alpine-host/disk.raw

# Carve for deleted artifacts
python docker-forensics-toolkit/carve-for-deleted-docker-files.py /var/lib/docker
```

### **Google Docker Explorer (de.py)**
*Reference: Forensic tool for offline Docker acquisitions*
- Mount container filesystems (AuFS/OverlayFS)
- Extract history, logs, and configuration from `/var/lib/docker`

### **Memory & Runtime Analysis Tools**
- **Volatility** — Memory forensics framework for container memory analysis
  - *Reference: eForensics Mag 2024 - Container memory access*
- **LiME (Linux Memory Extractor)** — Extract container memory for analysis
- **checkpointctl + CRIU** — Analyze Kubernetes container checkpoints
  - *Reference: Extract memory pages, process states from checkpoints*
  - `grep` on `checkpoint/pages-*.img` for secrets/keys in memory

### **Container-Specific Forensics**
- **ForenStack** — Python-based automated Docker forensics container builder
  - *Reference: GitHub hernerwerzog/forenstack - builds forensic tool containers*
- **DockerForensics** — Remote runtime Docker forensics tool (Flask-based)
  - *Reference: GitHub Rafael-Remigio - captures volatile data via Docker API*

### **Critical Directories to Examine**
```
/var/lib/docker/containers/     # Container configs, logs
/var/lib/docker/image/          # Image metadata
/var/lib/docker/volumes/        # Persistent data
/var/lib/docker/overlay2/       # Layer filesystems (OverlayFS)
/var/lib/docker/aufs/diff/      # Layer filesystems (AuFS, legacy)
```

---

<a name="phase-5"></a>
## ┌─────────────────────────────────────────────────────────────────┐
## │ **PHASE 5: DYNAMIC RUNTIME & eBPF OBSERVABILITY** *(UPGRADED)*  │
## └─────────────────────────────────────────────────────────────────┘
**Goal**: Watch container "live" to understand actual behavior vs. code.

### **eBPF-Based Runtime Security (2025 Ecosystem)**

#### **Tier 1: Detection & Observability**
- **Falco** *(CNCF Graduated)* — Behavioral activity monitoring, syscall detection
  - *Reference: Uses eBPF probes for real-time syscall monitoring with <1% overhead*
  - 50+ alert integrations (Slack, SIEM, PagerDuty)
  ```bash
  # Deploy on Kubernetes
  helm install falco falcosecurity/falco --namespace falco
  
  # Watch events
  kubectl logs -f -n falco -l app=falco
  ```

- **Tracee** *(Aqua Security)* — eBPF-based runtime security & forensics
  - *Reference: Focuses on forensic-grade runtime detection with detailed artifact collection*
  - Combines with **Traceeshark** (Wireshark integration for eBPF events)

- **Tetragon** *(Cilium/Isovalent, CNCF)* — Kubernetes-aware security observability
  - *Reference: eBPF-based enforcement at kernel level, <1% overhead (InfoWorld Feb 2025)*
  - Real-time policy enforcement without TOCTOU vulnerabilities
  ```bash
  # Install on Kubernetes
  helm install tetragon cilium/tetragon -n kube-system
  
  # Stream events
  kubectl exec -it -n kube-system ds/tetragon -c tetragon -- tetra getevents -o compact
  ```

#### **Tier 2: Advanced Observability**
- **Inspektor Gadget** *(active)* — Debug & inspect K8s apps (eBPF)
- **BCC / Bpftrace** *(active)* — Custom eBPF scripting for traces
- **Cilium Hubble** *(active)* — Network flow & service map visualization
- **Parca** *(active)* — Continuous profiling (performance analysis)
- **Pixie** — Auto-instrumentation with eBPF for observability

#### **Tier 3: Specialized Tools**
- **Sysmon for Linux** — Monitor process lifetime, network, file writes
- **KubeArmor** — Container-aware runtime enforcement using LSM + eBPF
- **Pulsar** — Event-driven monitoring framework (Rust + eBPF)
- **Beyla** — OpenTelemetry auto-instrumentation
- **Caretta** — Kubernetes service map using eBPF network tracing

### **eBPF Advantages (2025 State)**
*Reference: eBPF ecosystem progress 2024-2025 (eunomia.dev)*
- **Security Applications**: BPF LSM (Linux Security Module) hooks for policy enforcement
- **Minimal Overhead**: Native kernel execution via JIT compilation
- **Mainstream Adoption**: Used by Facebook, Netflix, Google, Cloudflare
- **Sandboxed Execution**: Verified safe programs in-kernel

---

<a name="phase-55"></a>
## ┌─────────────────────────────────────────────────────────────────┐
## │ **PHASE 5.5: ORCHESTRATION & MANIFEST RECOVERY** *(NEW)*        │
## └─────────────────────────────────────────────────────────────────┘
**Goal**: Reconstruct Kubernetes manifests and Helm charts.

### **Kubernetes Recovery Tools**
- **Velero** *(active)* — Backup/restore K8s resources and volumes
  ```bash
  # Snapshot entire namespace for forensics
  velero backup create forensic-backup --include-namespaces suspicious-ns
  ```

- **kubectl get all -o yaml** — Export running resources
- **kubectl-neat** *(active)* — Remove clutter from kubectl output
- **Helm get manifest** — Extract deployed Helm charts
- **Helm get values** — Retrieve chart configurations
- **kube-bench** *(active)* — Audit against CIS benchmarks
- **Popeye** *(active)* — Scan live clusters for config issues

### **Advanced Analysis**
- **docker history + tac** — Reverse layer order for chronological reconstruction
- **Container-diff** — Compare two images for filesystem/metadata/package changes

---

<a name="phase-6"></a>
## ┌─────────────────────────────────────────────────────────────────┐
## │ **PHASE 6: OFFENSIVE SECURITY & ESCALATION (RED TEAM)**         │
## └─────────────────────────────────────────────────────────────────┘
**Goal**: Attack the container to find escape vectors.

### **Core Tools**
- **CDK (Container Development Kit)** — Automated exploit & escape toolkit
- **Deepce** *(active)* — Enumeration & escalation script
- **LinPEAS** *(active)* — Privilege escalation audit (host/container)
- **Kube-hunter** *(active)* — Hunt for vulnerabilities in K8s
- **Amit** *(active)* — Offensive security tool for K8s
- **Peirates** *(active)* — Kubernetes penetration tool

---

<a name="phase-65"></a>
## ┌─────────────────────────────────────────────────────────────────┐
## │ **PHASE 6.5: SOURCE CODE & BINARY RECOVERY** *(NEW)*            │
## └─────────────────────────────────────────────────────────────────┘
**Goal**: Reverse compiled applications and extract source code.

### **Interpreted Languages Recovery**
Look in `/app`, `/src`, `/opt`, `/usr/src` within extracted filesystem:

- **Python**: `.py`, `.pyc` files
  - Use `uncompyle6` for bytecode decompilation
- **Node.js**: `package.json`, `node_modules/`, `.js` files
- **Ruby**: `Gemfile`, `.rb` files
- **PHP**: `composer.json`, `.php` files
- **Go**: Binary analysis with Ghidra for symbol recovery

### **Compiled Binaries**
- All tools from Phase 2 (Ghidra, Cutter, Binwalk)
- **strings** — Extract config paths, URLs, hardcoded values
- **strace/ltrace** — Trace system/library calls in running containers

---

<a name="phase-7"></a>
## ┌─────────────────────────────────────────────────────────────────┐
## │ **PHASE 7: ORCHESTRATION RECOVERY & STATE DUMP**                │
## └─────────────────────────────────────────────────────────────────┘
**Goal**: Reconstruct Kubernetes manifests and Helm charts.

### **Core Tools**
- **Velero** *(active)* — Backup/restore & migrate K8s resources
- **kubectl-neat** *(active)* — Remove clutter from kubectl get
- **Helm** *(active)* — Inspect Helm charts & history
- **Kompose** *(active)* — Convert Compose to K8s (and reverse)
- **Popeye** *(active)* — Sanitizer that scans live clusters
- **kube-bench** *(active)* — CIS Benchmark checking

---

## 🔥 **COMPLETE EXTRACTION WORKFLOW (2026)**

```bash
#!/bin/bash
# Complete Docker Image Decomposition Pipeline

IMAGE="target/image:tag"

echo "[*] Phase 0: Registry Reconnaissance"
skopeo inspect docker://$IMAGE | jq > metadata.json
crane manifest $IMAGE > manifest.json

echo "[*] Phase 1: Image Acquisition"
docker pull $IMAGE
docker save $IMAGE -o image.tar

echo "[*] Phase 1.5: Dockerfile Reconstruction"
docker run -v /var/run/docker.sock:/var/run/docker.sock:ro \
  pegleg/whaler -sV=1.36 $IMAGE > Dockerfile.recovered

echo "[*] Phase 2.5: Filesystem Extraction"
mkdir -p rootfs
docker build --output type=local,dest=./rootfs - <<< "FROM $IMAGE"

echo "[*] Phase 3.5: Find Compose Files"
CONTAINER_ID=$(docker create $IMAGE)
docker inspect $CONTAINER_ID --format \
  '{{ index .Config.Labels "com.docker.compose.project" }}' > compose-project.txt
docker rm $CONTAINER_ID

echo "[*] Phase 4: SBOM Generation"
syft $IMAGE -o spdx-json=sbom.json
grype sbom:sbom.json -o json > vulnerabilities.json

echo "[*] Phase 4.5: Forensic Carving"
# Requires docker-forensics-toolkit
python dof/carve-for-deleted-docker-files.py /var/lib/docker > recovered-files.txt

echo "[*] Phase 5: Runtime Analysis (if deploying)"
# Deploy with Falco/Tetragon monitoring
helm install falco falcosecurity/falco
kubectl logs -f -n falco -l app=falco > runtime-events.log

echo "[*] Complete! Artifacts saved to current directory."
```

---

## 📊 **TOOL COMPARISON MATRIX (2026)**

| **Category** | **Tool** | **Strength** | **Use When** |
|--------------|----------|--------------|--------------|
| **Dockerfile Recovery** | Whaler | Fast, accurate layer parsing | Need quick Dockerfile reconstruction |
| | dfimage | Python-based, customizable | Need to modify reconstruction logic |
| | docker history | Native, always available | Simple queries, no dependencies |
| **SBOM Generation** | Syft | 40+ ecosystems, industry standard | Comprehensive software inventory |
| | Tern | Cross-layer analysis | Deep dependency analysis |
| **Vulnerability Scanning** | Grype | Fast, SBOM-compatible | CI/CD integration, automation |
| | Trivy | All-in-one scanner | Quick scans, multiple targets |
| **Runtime Security** | Tetragon | Kubernetes-aware, enforcement | K8s environments, active defense |
| | Falco | Mature, 50+ integrations | Detection-first, SIEM integration |
| | Tracee | Forensics-focused | Post-incident investigation |
| **Forensics** | dof (Docker Forensics Toolkit) | Deleted file recovery | Post-mortem analysis |
| | Volatility | Memory analysis | Advanced memory forensics |

---

## 🎯 **KEY IMPROVEMENTS IN 2026 EDITION**

1. **eBPF Runtime Security**: Integration of Tetragon, Falco, Tracee for kernel-level observability
2. **Enhanced SBOM Tools**: Syft + Grype ecosystem with 40+ package managers
3. **Forensic Capabilities**: Dedicated tools for deleted file recovery and memory analysis
4. **Kubernetes-Native**: Tools like Kompose, Velero, Tetragon for K8s environments
5. **Research-Validated**: All tools referenced from 2024-2026 publications and documentation

---

## 📚 **REFERENCES**

### Research Sources (2024-2026)
- Anchore Syft/Grype documentation (GitHub, 2025)
- Cilium Tetragon security observability (InfoWorld, Feb 2025)
- Docker Forensics Toolkit (GitHub, 2024-2025)
- eBPF ecosystem progress report (eunomia.dev, 2025)
- Comparative analysis of eBPF runtime security tools (RITECH 2025)
- Falco CNCF documentation (2025)
- DZone: Reverse Engineer Docker Images into Dockerfiles (2020, updated techniques 2025)
- Medium: Docker history parsing techniques (June 2025)

### Tool Repositories
- P3GLEG/Whaler
- anchore/syft, anchore/grype
- cilium/tetragon
- falcosecurity/falco
- aquasecurity/tracee
- docker-forensics-toolkit/toolkit
- LanikSJ/dfimage

---

**Framework Maintained By**: Open Source Security Community  
**Last Updated**: January 2026  
**License**: Educational & Research Use

---

*This framework represents the state-of-the-art in Docker image decomposition and forensic analysis as of January 2026, incorporating tools and methodologies validated through industry research and community adoption.*
