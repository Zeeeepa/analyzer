"""
Batch Repository Analysis Script using Codegen API
==================================================

This script creates Codegen agent runs for multiple repositories sequentially.
Each agent run receives instructions to analyze a repository and save results
to the analyzer repo's github_analysis branch.

Prerequisites:
- pip install codegen

Usage:
    python analyzer.py
"""

import time
import json
from datetime import datetime
from typing import List, Dict
from codegen.agents.agent import Agent

# ============================================================================
# CONFIGURATION
# ============================================================================

# Codegen credentials
ORG_ID = ""
API_TOKEN = "sk-92083737-4e5b-4a48-a2a1-f870a3a096a6"

# Target location for analysis reports (instructions for the agent)
ANALYZER_REPO = "analyzer"
ANALYZER_BRANCH = "github_analysis"
REPORTS_FOLDER = "repos"

# Timing configuration
WAIT_BETWEEN_RUNS = 2  # seconds between creating agent runs

# Repository list
REPOSITORIES = [
    "aigne-framework", "claude-flow", "danmu_api", "voice-noob",
    "devtools-debugger-mcp", "dashcam", "mgrep", "grainchain",
    "Microsoft.Unity.Analyzers", "sj.h", "intelligent-audit-system",
    "Portalis", "DeepWideResearch", "llm-auto-optimizer", "better-ui",
    "vscode-deepscan", "voltagent", "autogenlib", "catwalk",
    "callcenter.js-mcp", "yaak", "comfydeploy", "LEANN", "Deep-Live-Cam",
    "lsp", "ultimate_mcp_server", "computesdk", "odoo", "promptflow",
    "cc-sessions", "cloudflare-manager", "sealos", "hackerai",
    "KiteAi-BOT", "WebAgent", "hacker-scripts", "1Panel", "agentapi",
    "browser-echo", "xianyu-auto-reply", "Paper2Agent", "deep-research",
    "mail01", "astron-rpa", "hyperliquid-trading-bot-rust",
    "harmonyTarget", "FastGPT", "railwaybuildcli", "Antigravity-",
    "mcp-use", "augment-code-patcher", "Matrix-Game", "x", "AntiHunter",
    "PG-Agent", "EvoPresent", "sneaky-rat", "episodic-sdk", "jet_notes",
    "openevolve", "ade", "NTSleuth", "opcode", "Packer-InfoFinder", "api",
    "quicksilver-sdk", "magentic-ui", "auto-mcp", "zerobyte", "memvid",
    "LummaC2-Stealer", "craftdesk", "zen-mcp-server", "cody", "graphiti",
    "Vert-Stealer", "EDR-Freeze", "gmail-gen", "WeKnora", "SWE-agent",
    "chromancer", "semgrep", "ScreenCoder", "Resume-Matcher", "Kosmos",
    "amq2api", "experiments", "vibe-kanban", "gamestudio-subagents",
    "kaiju", "Auditor", "imagesorcery-mcp", "astra-xmod-shim",
    "TinyRecursiveModels", "claude-task-master", "codegen", "wiseflow",
    "neutts-air", "ast-mcp-server", "dspy-micro-agent", "grass-bot",
    "claude-code-sdk-demos", "chrome-extension-remote-scripts",
    "Containers", "PyPhisher2", "chat2api", "airi", "Nettacker",
    "Cheatsheet-God", "faraday", "RustScan", "scapy", "MoneyPrinterTurbo",
    "xyflow", "omarchy", "ai-dev-tasks", "Windows-MCP", "local-operator",
    "claude-context", "RedTeam-Tools", "DllShimmer",
    "ai-web-integration-agent", "neovate-code", "thc-hydra",
    "awesome-web-security", "XianyuAutoAgent", "rep", "sub2api2",
    "dev-browser", "Agent365-python", "automate-faceless-content", "cli",
    "db-studio", "sub2api", "dockmon", "wanix", "llm-schema-registry",
    "llm-observatory", "llm-memory-graph", "kestra",
    "nano-banana-infinimap", "vibesdk", "ai-sre-agent", "repomirror",
    "RepoMaster", "TinyGen-prama-yudistara", "dxt", "dsts", "deepagents",
    "agentic-design-patterns-cn", "uwu", "MediaCrawler", "DBIPatcher",
    "comfy-deploy-python", "bypass-all", "CodeFuse-Embeddings",
    "OpenSpec", "serena", "code-index-mcp", "webscout-mcp",
    "PhoneSploit-Pro", "reconftw", "syncthing", "Cloudflare-agents",
    "Cloudflare-vless-trojan", "AVR-Eval-Agent", "wave", "context7",
    "keychecker", "recce", "commando-vm", "bloop", "script-server",
    "proofofthought", "dasein-core", "auto-coder", "UI-TARS-desktop",
    "arxiver", "infinity-sql", "fastapi_mcp", "tiktok-warmup-bot",
    "hoaxshell", "AllHackingTools", "wm001", "sambanova-webinar",
    "Mindustry", "copilot-cli", "AI-Trader", "forensic-analysis",
    "plangen", "agent-ide", "jet_redis", "vibe-chamber", "llama_deploy",
    "Github-Mev-Bot", "pyrust-bt", "PromptEnhancer", "PromptX", "KAG",
    "supervision", "glint", "fullstack-next-cloudflare",
    "nekro-edge-template", "ottomator-agents", "Flowise", "mcp-aas",
    "zai-api", "MJ", "codegen-ide", "chatgpt.js-chrome-starter",
    "free-augmentcode", "AugmentCode-Free", "droidrun", "cedar-OS",
    "nofx", "devtools", "vex", "dat", "changedetection.io", "dify",
    "n8n-workflows", "surfapp", "CamPhish", "sandbox-runtime",
    "SetupHijack", "Quine", "AutoGPT", "ensemble", "codebase-analytics",
    "mcp-agent", "tools", "osmedeus", "open_deep_research", "anon-kode",
    "linear-client", "Archon", "garak", "SelfEvolvingAgent",
    "AngryOxide", "physionet", "remix-saas", "agents", "agno",
    "Arangodb-graphrag", "genai-toolbox-mcp", "AIPscan",
    "openai-chatkit-advanced-samples", "code-scan-agent", "nishang",
    "openwifi", "fastmcp", "adk-samples", "Legendary_OSINT", "skyvern",
    "PharosTestnet-Bot", "trivy", "windowsvm", "app", "WatchDogKiller",
    "lynlang", "WhatWeb", "Windows-Sandbox-Tools", "vibetest-use",
    "Sn1per", "web-check", "claude-agents", "chatkit-js", "Villain",
    "jet_server", "opencode", "OxyGent", "hint-break",
    "crypto-arbitrage-bot", "resumePolice", "potpie", "cloud-sniper",
    "ultracite", "Awesome-Nano-Banana-images", "ai-goofish-monitor",
    "ZPhisher-Python", "everything-ai-chat", "sdk-python", "Auto_aim",
    "PayloadsAllTheThings", "athena-protocol", "mercury-spec-ops",
    "driflyte-mcp-server", "scancode-toolkit", "thermoptic",
    "jaegis-RAVERSE", "budibase", "xrpl-trading-bot", "intrascribe",
    "gpt-researcher", "ContextAgent", "agent-os", "DeepCode", "MA",
    "Dayflow", "CodeWebChat", "deep-agents-ui", "awesome-llm-apps",
    "Neosgenesis", "once-campfire", "pg_lake", "agent-x", "YPrompt",
    "nightingale", "banana-gen", "TradingAgents-CN", "mcpm.sh", "khoj",
    "vimium", "ControlFlow", "smolagents", "superpowers", "forge",
    "opencode-web", "supermemory-mcp", "guild", "graph-of-thoughts-mcp",
    "clarity", "browserforge", "FluentRead", "rebrowser-patches",
    "sandbox-sdk", "cnpmjs.org", "fantasy", "dexto", "deepwiki-mcp",
    "bolt.diy", "PNT3", "chrome-devtools-mcp", "nekro-agent", "pink",
    "HeadlessX", "mimic-code", "Prompts", "Pharos-Testnet-Bot",
    "MindSearch", "moonfy.github.io", "code2prompt", "Learn-Web-Hacking",
    "context-engineering-intro", "tinygen", "augment-swebench-agent",
    "awesome-hacking", "tinkaton", "Logics-Parsing", "ai-sdk-tools",
    "evolutionary-layering-in-complex-systems-mcp", "glass",
    "awesome-indie-hacker-tools", "vipe", "YouTube-viewbot", "gpoParser",
    "line", "data-core", "dev3000", "continue", "claude-skills",
    "codacy-cli-v2", "rendergit", "ruvvector-service", "sourcebot",
    "Flashloan-Arbitrage-Bot", "-Linux-", "ResourcePoison",
    "softwaredesign-llm-application", "garlic", "code-mode", "frida",
    "botasaurus", "vibecast", "acemcp", "keyleak-detector", "example",
    "devbox-sdk", "crawlee-python", "scalebox-sdk-python",
    "scalebox-sdk-js", "Open-AutoGLM", "devbox-runtime", "Z-Image",
    "cluster-image", "snow-code", "codementor", "aiproxy", "pingora",
    "tambo", "jebmcp", "ay-claude-templates", "agentic-kit",
    "spyder-osint", "embedJs", "code", "claudecodeui", "AgentX",
    "apocalypse-the-server", "ai-mesh", "vibe-coding-cn",
    "daytona-hackday", "scip-python", "repo-converter", "scip-go",
    "scip", "scip-lsp", "ai-born-website", "morphik-core", "MinerU",
    "TrendRadar", "projax", "S1-Parser", "ragforge", "daiv",
    "Mini-Agent", "mini-agent2", "edmunds-claude-code", "registry",
    "Chronos", "Folo", "b0t", "pingoo", "Tacticontainer", "hatch-cython",
    "a2a-client", "auto-coder.web", "pathway", "mcp-code-indexer",
    "advanced-reasoning-mcp", "dreamv", "crypto-trader-bot-with-AI-algo",
    "konbini", "pipedream", "executive-ai-assistant",
    "OpenAI-Compatible-API-Proxy-for-Z", "surf", "maestro",
    "MultiAgentPPT", "qoder-free", "reflex", "FileScopeMCP",
    "gpt_academic", "eliza", "the-markovian-thinker", "pyversity",
    "libraries.io", "terminator", "claude-cookbooks", "LinearRAG",
    "aipyapp", "Memori", "pr-agent", "git_manager",
    "CodegenProjectDashboard", "DeepResearch", "langmem",
    "agentic-flow", "eino", "SurfSense", "AsterMind-ELM", "ag-ui",
    "KODER-extension", "VisoMaster", "nautilus_trader", "ShinkaEvolve",
    "AgentBridge", "plugin-repository", "Microverse", "AsmLdr",
    "synapse-bot", "task", "parse-server", "chrome2moz", "evershop",
    "prompt-manager", "skills", "Fabric", "stagehand",
    "computational-mathematical-discovery-framework", "open-swe",
    "vite-plugin-react", "adk-go", "PraisonAIWP", "flyctl",
    "BifrostMCP", "assets-pieces", "codegen-examples", "AutoRFKiller",
    "vibe-coding-playbook", "unnamed_game_1_v2", "airweave", "Windows",
    "cve-reference-ingest", "bevy", "RAG-Anything",
    "MaliangAINovalWriter", "codegen-api-client", "agent-sandbox",
    "gmailtail", "GeoSpy", "python-keylogger", "claude-code-sdk-python",
    "eslint-plugin-vitest", "Claude-Code-Agent-Creator",
    "clinicaltrialsgov-mcp-server", "SilentButDeadly",
    "chrome-fingerprints", "agentica", "vscode-mcp", "S1-MatAgent",
    "Agent-Interaction-Protocol", "nps", "klaude", "agent-girl",
    "qwen-api", "superinterface", "scrape-it", "call-center-ai",
    "LightRAG", "awesome-claude-skills", "otel", "async-server",
    "TikTok-viewbot", "buttercup", "byzer-llm", "prowler", "PyPhisher",
    "sec-gemini", "BYZER-RETRIEVAL", "notes", "web-eval-agent", "cipher",
    "grok2api", "llm-orchestrator", "graph-sitter", "harmony", "agent",
    "create-llama", "zai-python-sdk", "claude-code-studio",
    "z.ai2api_python", "fuck-u-code", "cameradar", "open_human_ontology",
    "ai-virtual-assistant", "perp-dex-tools", "Decepticon", "drawnix",
    "toolsbox", "resonant-semantic-embedding", "sleepless-agent",
    "dspy.ts", "anubis_offload", "stellar-data-recovery-free", "mcphub",
    "workflow-use", "jet_python_modules", "claude-code-nexus",
    "dilagent", "ATLAS", "Skill_Seekers", "DeepResearchAgent", "nitro",
    "elysia", "pydapter", "nanobrowser", "k2Think2Api",
    "youtu-graphrag", "mcp-lsp", "codacy-mcp-server", "qwen-code",
    "k2think2api2", "Scanners-Box", "OneAPI", "Blank-Grabber",
    "gcli2api", "zai", "mcp-ts-morph", "aikb", "wundr",
    "scip-typescript", "django-repl", "SandboxFusion", "kitex",
    "appdaemon", "fulling", "higress", "complex-agent",
    "tanstack-ai-demo", "awesome-claude-code", "openai-agents-python",
    "JetScripts", "Youtu-agent", "weave", "networking-toolbox",
    "piedpiper", "agentic-context-engine", "aifabrix-builder",
    "llm-policy-engine", "Agentic-Support", "llm-forge",
    "chrome-sandbox", "Agents-for-js", "DeepThinkVLA",
    "claude-code-configs", "sub-agents", "Zero", "ROMA", "PAI-RAG",
    "vulnerablecode", "UserAgent-Switcher", "repo2docker",
    "tokligence-gateway", "growchief", "putout", "agentic-qe", "coconut",
    "devflow", "composio-base-py", "self-modifying-api", "catnip",
    "lscript", "theProtector", "R-Zero", "ZtoApi", "h2ogpt",
    "chatGPTBox", "UltraRAG", "rustransomware", "release-scripts",
    "lsmcp", "Creal-Stealer", "awesome-ai-apps", "code_just",
    "chatkit-python", "agent-framework", "ambient_deep_agents",
    "open-lovable", "llmware", "auto-agent",
    "BlackCap-Grabber-NoDualHook", "coze-studio", "MIRIX",
    "WinUpdateRemover", "sim", "fenrir", "Matrix-3D", "sst",
    "pytest-language-server", "openskills", "claude-code-hub",
    "BettaFish", "BananaFlow-ZHO", "llm-graph-builder", "wandb",
    "typebox", "apex", "PentestGPT2", "autoview", "serena-modular-mcp",
    "runtime", "templates", "cache", "aiinbx-py", "sshgate",
    "gemini-cli-mcp-server", "minio", "composio", "vitest", "maxun",
    "llm-inference-gateway", "antigravity-agent", "specweave",
    "atlas-mcp-server", "llm-council", "daiv-sandbox", "Clavix",
    "droid2api", "jmap-mcp", "EvoAgentX", "gsort-professional",
    "lilypad", "GhostTrack", "ida-cyberchef", "sendgrid-python",
    "smart-tree", "codexist", "Valdi", "agor",
    "AUTO-OPS-AI-DevOps-Agent", "MMCTAgent", "Datus-agent",
    "llm-governance-dashboard", "llm-analytics-hub",
    "llm-config-manager", "wifi-densepose", "PentestGPT", "scancode.io",
    "yolox", "cloudflare-go", "radare2", "SAG", "androguard",
    "video-to-txt", "autobe", "minimal-claude", "Agents-Claude-Code",
    "Droids", "humanlayer", "Real-Time-Voice-Cloning", "open-rube",
    "EDtunnel", "youtube-subscriber-bot", "ByteCaster",
    "etf-data-scrape", "Clean-Coder-AI", "do-rag", "codedog",
    "fast-agent", "TenCyclesofFate", "marvin", "tiktok-bot",
    "Qwen3-Omni", "aiproxy-free", "cert-manager", "image-monitor",
    "hysteria", "mcp-knowledge-graph", "new-api", "NetworkHound",
    "strix", "cnpmcore", "kanbatte", "Antigravity2api", "stratify",
    "examplesnotes", "spyder-osint2", "parse-dashboard", "letta",
    "mcp-chrome", "PrimoAgent", "cocoindex", "prompt-optimizer",
    "textualize-mcp", "autogen", "perfetto", "Codegen_slack",
    "appmap-js", "vlurp", "Nano-Bananary", "flareprox", "dinov3",
    "flint", "dirsearch", "spiderfoot", "crush", "langchain-code",
    "DrissionPage", "SuperClaude", "code-graph-rag",
    "Solana-Heaven-Dex-Trading-Bot", "XCodeReviewer", "ck", "cypress",
    "BillionMail", "FakeCryptoJS", "superpowers-skills", "rift",
    "adk-python", "dot-ai", "apptron", "gemini-chatbotz", "amplifier",
    "GDA-android-reversing-Tool", "ast-read-tools", "joyagent-jdgenie",
    "blaze", "ladybird", "Repo2Run", "DeepAnalyze", "gemini-cli",
    "SecLists", "open-webui", "chatgpt-adapter", "lemonai",
    "CodeFuse-muAgent", "Silent-PDF-Exploit-ZeroTrace-PoC", "bytebot",
    "OpenAlpha_Evolve", "AgentCPM-GUI", "ZeroTrace-Stealer-13-2026",
    "ququ", "leantime", "AgentFlow", "Crypto-Asset-Tracing-Handbook",
    "spec-kit", "ccpm", "VibeVoice", "WSASS", "LuoGen-agent",
    "QwenChat2Api2", "C2PE", "magic", "code-review-mas", "langextract",
    "Bitcoin-wallet-finder", "claude-code-router", "CodeFuse-Query",
    "PandaWiki", "Phantom", "level1-crackmes-solutions", "beam",
    "OneReward", "darkdump", "dyad", "snow-flow", "langchain-sandbox",
    "tracy", "x-agent", "nanochat", "joycode-agent", "ZtoApits",
    "SecretScout", "DecompilerServer", "qwenchat2api", "cloudscraper",
    "theHarvester", "osv-scanner", "claude-relay-service", "KittenTTS",
    "RagaAI-Catalyst", "AWorld", "claude-code-infrastructure-showcase",
    "Bella", "social-analyzer", "winboat", "mcp-crawl4ai-rag",
    "claude-code-requirements-builder", "deepwiki-open", "SonicVale",
    "parlant", "midscene", "x64dbg", "bisheng", "mcporter", "anamorpher",
    "Prompt-Tools", "n8n-terry-guide", "astermind-elm-mcp", "Arsenal",
    "DeepResearchAgent1", "langflow", "agency-agents", "sageread",
    "terminalcp", "coding-agent-template", "SwarmMCP", "ai_demo",
    "launchpad", "xanmod-arm64", "envbuilder", "llm-registry",
    "llm-copilot-agent", "StepFly", "playwright-sandbox",
    "agent-sandbox-skill", "500-AI-Agents-Projects", "reinstall",
    "shadow-clean", "astron-agent", "A2V", "costrict",
    "mcp-access-point",
    "Download-VSIX-From-Visual-Studio-Market-Place", "DreamOmni2",
    "gplay-scraper", "hackingtool", "AutoServe",
    "cognitive-memory-engine", "ubicloud", "simplest-k8s", "docker-elk",
    "exploits", "mcp-client-cli", "Gui", "workflows-mcp-server",
    "mcp-shrimp-task-manager", "screenpipe", "awesome-mcp-servers",
    "claude-init", "uv-cloudflare-workers-example",
    "tsunami-security-scanner", "CredSniper", "CredMaster",
    "Android-Pentesting-Checklist", "claude-code-templates",
    "go-cursor-help", "every-marketplace", "monday_mcp", "st",
    "android-mitm-ssl-interceptor", "mcp-feedback-enhanced",
    "spec-workflow-mcp", "local-openai-api-service", "ida-pro-mcp",
    "PraisonAI-WPcli", "data-formulator", "neuralagent", "social-bro",
    "inkeep_agents", "BambooAI", "code-understanding-mcp", "prompt-kit",
    "cluster-image-docs", "MobileAgent", "MCP", "npm", "workflows-py",
    "liam", "Awesome-Hacking-Resources", "magi", "agent-build",
    "github.gg", "pgmcp", "pipedream-sdk-python", "3x-ui",
    "k2think2api3", "Z.ai2api", "stresser", "griptape", "codegenApp",
    "playwright-mcp", "atlantis-mcp-server", "RD-Agent", "mcp-index",
    "windcode", "SupaBaseEventer", "gut", "rengine", "TT", "DPL",
    "trae-agent", "claudekit-skills", "analyzer", "serv", "CPR",
    "project_tools", "Nn", "codege", "22", "open_codegen", "Comcp",
    "codebase-indexer", "zgsm-backend-deploy", "claude-mem",
    "next-ai-draw-io", "ai-hedge-fund", "public-apis", "vibe-vibe",
    "banana-slides", "awesome-nano-banana-pro-prompts", "RedInk",
    "data-peek", "API-mega-list", "awesome-ai-tools",
    "scraping-apis-for-devs", "ai-agent-tools",
    "authflow-monetize-gpts", "youtube-growth-guide",
    "automate-for-growth", "lovable-for-beginners", "aiflowy",
    "lanhu-mcp", "Fay", "mcp-server", "ruvector", "intelligence-core",
    "research-core", "automation-core", "int3rceptor",
    "infinite-server26", "HackGpt", "ai-data-science-team",
    "sherpa-onnx"
]

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def get_analysis_instructions(repo_name: str) -> str:
    """
    Generate comprehensive analysis instructions for a repository.
    
    This creates a detailed prompt that instructs the agent to:
    1. Use repomix to generate repository overview
    2. Analyze architecture and data flows
    3. Assess autonomous CI/CD suitability
    4. Create improvement roadmap
    5. Identify self-upgrade opportunities
    6. Save the analysis to the analyzer repository
    """
    
    return f"""# REPOSITORY ANALYSIS: {repo_name}

## YOUR TASK

Analyze the repository '{repo_name}' comprehensively and save the analysis report to the analyzer repository.

## CONTEXT

You have access to the repository '{repo_name}' in your workspace. You will analyze it and save your findings to the '{ANALYZER_REPO}' repository on the '{ANALYZER_BRANCH}' branch in the '{REPORTS_FOLDER}' folder.

## STEP 1: Generate Repository Overview Using Repomix

First, install and run repomix to generate a comprehensive overview of the repository:

```bash
cd {repo_name}
npm install -g repomix
repomix . --output repomix-output.txt --style xml --include-empty-directories
```

Read and analyze the repomix output thoroughly to understand:
- File structure and organization
- Code patterns and conventions
- Dependencies and technologies used
- Overall architecture

## STEP 2: Analyze Architecture & Dataflows

### 2.1 Entry Points
Identify and document:
- Main functions and CLI entry points
- API endpoints and web servers  
- Background jobs and event listeners
- Initialization scripts and startup code

### 2.2 Module Structure
Document:
- Top-level modules/packages and their purposes
- Core business logic vs utility modules
- Module boundaries and separation of concerns
- Public vs internal APIs

### 2.3 Data Flow Analysis

**Inputs:** Document all data sources:
- CLI arguments and flags
- Configuration files (JSON, YAML, ENV)
- Environment variables
- API requests (REST, GraphQL, etc.)
- Database queries
- File reads
- External service calls

**Transformations:** Analyze how data is processed:
- Input validation and sanitization
- Business logic operations
- Data mapping and transformation
- Computations and algorithms
- State management patterns

**Outputs:** Document all data destinations:
- Console output and logging
- File writes and exports
- Database updates
- API responses
- External service calls
- Cache updates

**Inter-module Flows:** Map how data moves between modules:
- Function calls and parameter passing
- Shared state management
- Event systems and pub/sub patterns
- Dependency injection

### 2.4 Dependencies
**External Dependencies:**
- Third-party libraries and frameworks
- Version requirements
- Purposes and usage patterns

**Internal Dependencies:**
- Module interdependencies
- Circular dependencies (if any)
- Coupling levels (tight vs loose)

### 2.5 Architecture Patterns
Identify architectural patterns in use:
- MVC, MVVM, or other UI patterns
- Microservices, monolith, or modular monolith
- Layered architecture
- Event-driven patterns
- Design patterns (Factory, Observer, Strategy, etc.)

## STEP 3: Autonomous CI/CD Suitability Assessment

Rate each dimension on a scale of 1-10 with detailed reasoning:

### 3.1 Code Quality & Maintainability (1-10)
Evaluate:
- Code organization and structure
- Naming conventions and readability
- Documentation (inline comments, docstrings)
- Coding standards adherence
- Technical debt indicators
- Code duplication
- Complexity metrics

### 3.2 Test Coverage & Quality (1-10)
Assess:
- Unit test coverage percentage
- Integration test coverage
- End-to-end test coverage
- Test quality and maintainability
- CI/CD automation of tests
- Test documentation

### 3.3 Modularity & Decoupling (1-10)
Analyze:
- Module independence
- Interface definitions
- Dependency management
- Ease of adding new features
- Reusability of components

### 3.4 PRD-to-Implementation Readiness (1-10)
Evaluate:
- Clear domain boundaries
- Spec-friendly architecture
- Feature isolation capabilities
- Requirement traceability
- Documentation alignment with code

### 3.5 Self-Improvement Capability (1-10)
Assess potential for:
- Safe refactoring
- Automated code generation
- Automated dependency upgrades
- Self-monitoring and metrics
- Self-healing capabilities
- Automated validation

### 3.6 CI/CD Readiness (1-10)
Evaluate:
- Build system maturity
- Automated testing in pipeline
- Deployment automation
- Quality gates and checks
- Rollback capabilities

### 3.7 Overall Assessment
Provide:
**Overall Autonomous CI/CD Readiness Score:** [average of above dimensions]  
**Top 5 Strengths:** What the repository does well  
**Top 5 Weaknesses:** Critical areas for improvement  
**10 Actionable Recommendations:** Prioritized improvements

## STEP 4: Continuous Improvement Roadmap

### 4.1 Immediate Improvements (0-3 months)
For each improvement, provide:
- **Title:** Brief name
- **Description:** What needs to be done
- **Impact:** High/Medium/Low
- **Effort:** High/Medium/Low
- **Success Criteria:** How to measure success
- **Implementation Steps:** Concrete actions

### 4.2 Medium-term Improvements (3-6 months)
Focus on:
- Architectural improvements
- CI/CD enhancements
- Automation opportunities
- Performance optimizations

### 4.3 Long-term Vision (6-12 months)
Focus on:
- Major refactoring initiatives
- Advanced automation
- Self-improvement infrastructure
- Scalability enhancements

### 4.4 Quality Gates
Define gates for each phase:
- Entry/exit criteria
- Key metrics to track
- Validation methods
- Rollback plans

### 4.5 User Integration Points
Document:
- How requirements are injected
- Directive paths for new features
- Feedback mechanisms
- User interaction points

## STEP 5: Self-Upgrade Opportunities

### 5.1 Code Generation Opportunities
Identify areas where code can be auto-generated:
- Boilerplate automation
- AI-generated implementations
- Template systems
- Configuration-driven code generation

### 5.2 Self-Analysis Capabilities
Potential for:
- Static analysis tools integration
- Runtime monitoring
- Performance profiling
- Security scanning
- Complexity analysis

### 5.3 Automated Testing Expansion
Opportunities for:
- Automated test generation
- Coverage gap analysis
- Regression detection
- Performance benchmarking
- Fuzz testing

### 5.4 Refactoring Automation
Identify:
- Safe refactoring candidates
- Automated code cleanup
- Dependency optimization
- Code smell detection and fixes

### 5.5 Documentation Automation
Potential for:
- API documentation generation
- Inline code comment generation
- Architecture diagram generation
- Changelog automation
- README generation and updates

## STEP 6: Executive Summary

### 6.1 Repository Overview
- **Name:** {repo_name}
- **Purpose:** What the repository does
- **Tech Stack:** Primary languages, frameworks, tools
- **Size:** Lines of code, file count
- **Team Size Estimate:** Based on commit patterns

### 6.2 Health Score Summary
- **Overall Health Score:** 1-10
- **Key Strengths:** Top 3 things the repo does well
- **Critical Issues:** Top 3 problems that need attention

### 6.3 Recommended Actions
- **Immediate Priorities:** Top 3 actions to take now
- **Expected Impact:** What improvements will result
- **Resource Requirements:** Time and skill needed
- **Timeline:** Estimated completion dates

### 6.4 Autonomous CI/CD Readiness
- **Current Level:** Not Ready / Partially Ready / Ready / Highly Ready
- **Key Blockers:** What's preventing full automation
- **Path Forward:** Steps to achieve readiness
- **Estimated Timeline:** How long to full readiness

## OUTPUT FORMAT

Structure your complete analysis as a well-formatted markdown document with all sections from Steps 2-6. Use clear headings, bullet points, and tables where appropriate. Be specific and actionable in all recommendations.

## CRITICAL: SAVE ANALYSIS REPORT

After completing the analysis, you MUST save it to the analyzer repository. Execute these commands:

```bash
# Navigate to the parent directory
cd ..

# Clone or access the analyzer repository if not already present
# (Assuming it's already in your workspace)

# Navigate to analyzer repository
cd {ANALYZER_REPO}

# Create or checkout the analysis branch
git fetch origin
git checkout -b {ANALYZER_BRANCH} 2>/dev/null || git checkout {ANALYZER_BRANCH}

# Pull latest changes if branch exists remotely
git pull origin {ANALYZER_BRANCH} 2>/dev/null || true

# Create reports folder if it doesn't exist
mkdir -p {REPORTS_FOLDER}

# Save your complete analysis report
cat > {REPORTS_FOLDER}/{repo_name}_analysis.md << 'ANALYSIS_EOF'
[PASTE YOUR COMPLETE ANALYSIS CONTENT HERE - ALL SECTIONS FROM STEP 2-6]
ANALYSIS_EOF

# Add, commit, and push
git add {REPORTS_FOLDER}/{repo_name}_analysis.md
git commit -m "Add comprehensive analysis report for {repo_name}"
git push origin {ANALYZER_BRANCH}
```

**Important Requirements:**
- File MUST be named: `{repo_name}_analysis.md`
- File MUST be saved in: `{ANALYZER_REPO}/{ANALYZER_BRANCH}/{REPORTS_FOLDER}/`
- Analysis MUST include ALL sections (Steps 2-6)
- Analysis MUST be complete and actionable

Begin your analysis of {repo_name} now."""


def create_agent_run(agent: Agent, repo_name: str, run_number: int, total_runs: int) -> Dict:
    """
    Create a single agent run for repository analysis.
    
    Args:
        agent: Initialized Codegen Agent instance
        repo_name: Name of the repository to analyze
        run_number: Current run number (for logging)
        total_runs: Total number of runs (for logging)
    
    Returns:
        Dictionary with run information including task ID and status
    """
    instructions = get_analysis_instructions(repo_name)
    
    print(f"[{run_number}/{total_runs}] Creating agent run for: {repo_name}")
    
    try:
        # Create the agent run with the comprehensive instructions
        task = agent.run(
            prompt=instructions,
            repo_id=repo_name  # Assuming repo_id is the repo name
        )
        
        result = {
            "repo_name": repo_name,
            "task_id": task.id if hasattr(task, 'id') else 'unknown',
            "status": task.status if hasattr(task, 'status') else 'unknown',
            "created_at": datetime.now().isoformat(),
            "success": True
        }
        
        print(f"  ✓ Task created - ID: {result['task_id']}, Status: {result['status']}")
        return result
        
    except Exception as e:
        error_result = {
            "repo_name": repo_name,
            "task_id": None,
            "status": "error",
            "error": str(e),
            "created_at": datetime.now().isoformat(),
            "success": False
        }
        print(f"  ✗ Error creating task: {str(e)}")
        return error_result


def save_run_log(runs: List[Dict], filename: str = "agent_runs_log.json"):
    """
    Save the log of all agent runs to a JSON file.
    
    Args:
        runs: List of run information dictionaries
        filename: Output filename for the log
    """
    with open(filename, 'w') as f:
        json.dump({
            "total_runs": len(runs),
            "successful_runs": sum(1 for r in runs if r['success']),
            "failed_runs": sum(1 for r in runs if not r['success']),
            "created_at": datetime.now().isoformat(),
            "runs": runs
        }, f, indent=2)
    print(f"\n✓ Run log saved to {filename}")


# ============================================================================
# MAIN EXECUTION
# ============================================================================


def main():
    """
    Main execution function that creates agent runs for all repositories.
    """
    print("=" * 80)
    print("CODEGEN BATCH REPOSITORY ANALYZER")
    print("=" * 80)
    print(f"\nConfiguration:")
    print(f"  Organization ID: {ORG_ID}")
    print(f"  API Token: {API_TOKEN[:20]}...")
    print(f"  Target Repo: {ANALYZER_REPO}")
    print(f"  Target Branch: {ANALYZER_BRANCH}")
    print(f"  Reports Folder: {REPORTS_FOLDER}")
    print(f"  Wait Between Runs: {WAIT_BETWEEN_RUNS}s")
    print(f"  Total Repositories: {len(REPOSITORIES)}")
    print(f"  Estimated Runtime: {len(REPOSITORIES) * WAIT_BETWEEN_RUNS}s ({len(REPOSITORIES) * WAIT_BETWEEN_RUNS / 60:.1f} minutes)")
    print("\n" + "=" * 80)
    
    # Initialize the Codegen agent
    print("\nInitializing Codegen agent...")
    try:
        agent = Agent(
            org_id=ORG_ID,
            token=API_TOKEN
        )
        print("✓ Agent initialized successfully")
    except Exception as e:
        print(f"✗ Failed to initialize agent: {str(e)}")
        return
    
    # Track all runs
    runs = []
    start_time = time.time()
    
    print(f"\nStarting batch creation of {len(REPOSITORIES)} agent runs...")
    print("=" * 80 + "\n")
    
    # Create agent runs for each repository
    for idx, repo_name in enumerate(REPOSITORIES, 1):
        # Create the agent run
        run_info = create_agent_run(agent, repo_name, idx, len(REPOSITORIES))
        runs.append(run_info)
        
        # Wait before creating the next run (except after the last one)
        if idx < len(REPOSITORIES):
            time.sleep(WAIT_BETWEEN_RUNS)
    
    # Calculate statistics
    elapsed_time = time.time() - start_time
    successful_runs = sum(1 for r in runs if r['success'])
    failed_runs = sum(1 for r in runs if not r['success'])
    
    # Print summary
    print("\n" + "=" * 80)
    print("EXECUTION SUMMARY")
    print("=" * 80)
    print(f"\nTotal Runs Created: {len(runs)}")
    print(f"  ✓ Successful: {successful_runs}")
    print(f"  ✗ Failed: {failed_runs}")
    print(f"\nExecution Time: {elapsed_time:.1f}s ({elapsed_time/60:.1f} minutes)")
    print(f"Average Time per Run: {elapsed_time/len(runs):.2f}s")
    
    # Save the log
    save_run_log(runs)
    
    print("\n" + "=" * 80)
    print("BATCH EXECUTION COMPLETE")
    print("=" * 80)
    print(f"\nAll agent runs have been created. Check the Codegen dashboard to monitor progress.")
    print(f"Analysis reports will be saved to: {ANALYZER_REPO}/{ANALYZER_BRANCH}/{REPORTS_FOLDER}/")
    print("\n✓ Done!")


if __name__ == "__main__":
    main()