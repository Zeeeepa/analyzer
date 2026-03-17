# Eversale CLI

Your AI Employee - Desktop agent for research, sales, admin, and automation.

## Quick Install

```bash
curl -fsSL https://eversale.io/install.sh | bash
```

Or via npm:

```bash
npm install -g eversale-cli
```

## Getting Started

1. **Run the CLI** - It will prompt for login:
   ```bash
   eversale
   ```

2. **Enter your email** - A magic link will be sent

3. **Enter token from email** - Activates your license

4. **Start automating!**
   ```bash
   eversale "Research Stripe competitors"
   ```

## Requirements

- **Node.js 18+** - For the CLI wrapper
- **Python 3.10+** - For the AI engine
- **License** - Purchase at https://eversale.io/desktop

### Install Python (if needed)

**macOS:**
```bash
brew install python@3.12
```

**Ubuntu/Debian:**
```bash
sudo apt install python3.12 python3.12-venv
```

## Usage

### Interactive Mode
```bash
eversale
```

### One-Shot Mode
```bash
eversale "Research Stripe competitors"
eversale "Find 10 marketing agencies in Miami"
eversale "Scrape product prices from amazon.com"
```

### Commands
```bash
eversale                    # Interactive mode (prompts for login if needed)
eversale "task"             # One-shot task execution
eversale login <email>      # Send login email
eversale activate <token>   # Activate with token from email
eversale logout             # Remove license
eversale --setup            # Re-run setup
eversale --help             # Show help
eversale examples           # Show example prompts
```

### Speed Mode (High-Speed for Internal Tools)

For processing high-volume tasks on internal/safe websites, use **natural language** to activate speed mode for **40-150x performance**:

```bash
# Just say it naturally!
eversale "fast track process 1000 items on the dashboard"
eversale "quickly fill out all the forms"
eversale "turbo mode - export all leads to CSV"
eversale "rush through the admin panel updates"

# All these phrases work:
# fast track, quickly, turbo, speed mode, instant, rapid, asap, rush, go fast
```

**Performance:**
| Operation | Normal | FAST_TRACK | Speedup |
|-----------|--------|------------|---------|
| Mouse move | 150-400ms | <10ms | 40x |
| Type 50 chars | 8-12s | <100ms | 100x |
| 1000 forms | 3-4 hours | 2-3 min | 100x |

**Safety:** FAST_TRACK automatically rejects public sites (Amazon, LinkedIn, etc.) to prevent bot detection. Only use on:
- ✅ localhost, private IPs (192.168.x.x)
- ✅ Internal domains (*.company.local)
- ✅ Admin panels behind auth
- ❌ Never on public e-commerce/social media

## How It Works

1. CLI validates your license against eversale.io
2. AI requests are routed through eversale.io to our GPU servers (RunPod)
3. Browser automation runs locally on your machine
4. Results are saved to `~/.eversale/outputs/`

### Request Flow

```
Your Machine                     Cloud
    ↓                              ↓
eversale CLI → eversale.io → GPU Server (RunPod)
    ↓                              ↓
Playwright ←────────────────── LLM Response
    ↓
Browser actions run locally
```

## Configuration

Configuration is stored at `~/.eversale/engine/config/config.yaml`

Key settings:
- `llm.mode` - "remote" (default, uses eversale.io) or "local" (requires Ollama)
- `browser.headless_default` - Run browser hidden (default: false)

### Using Your Own GPU Endpoint (Pod / Serverless)

The engine supports alternative backends via either:
- `EVERSALE_LLM_URL` env var (always overrides), or
- `llm.allow_custom_endpoint: true` + `llm.base_url: ...` in `~/.eversale/engine/config/config.yaml`.

- **OpenAI-compatible** (vLLM/TGI/etc): set `llm.base_url` to the server root (no `/v1` needed). Example: `http://<host>:8000`
- **Ollama-compatible**: `http://localhost:11434`
- **RunPod Serverless**: set `llm.base_url` to `https://api.runpod.ai/v2/<endpoint_id>` and set `RUNPOD_API_KEY` in your environment

Notes on speed:
- Serverless often has **cold start** latency; to match pod-like speeds, configure your endpoint with a warm worker / minimum workers (provider setting).

## Troubleshooting

**Having issues?** Just tell the agent what's wrong:

```bash
eversale "check my setup"           # Runs health checks
eversale setup                      # Re-runs installation
```

### Common Issues

| Problem | Solution |
|---------|----------|
| Can't login | Check your email for the login link, or run `eversale` again |
| Browser not working | Run `eversale setup` to reinstall |
| Something broken | Run `eversale setup` to fix it |

Need help? Email support@eversale.io or visit https://eversale.io/desktop

## Related Repositories

| Repo | Path | Description |
|------|------|-------------|
| **ev29** | `/mnt/c/ev29/` | Monorepo (web app, CLI, agent backend) |
| **cli** | `/mnt/c/ev29/cli/` | This CLI package (published to npm) |
| **agent-backend** | `/mnt/c/ev29/agent-backend/` | Python servers/workflow runtime; the CLI engine is the single brain (agent-backend shims into `cli/engine/agent`) |

## Infrastructure

| Server | Purpose |
|--------|---------|
| **eversale.io** | Web app, license validation, LLM proxy |
| **RunPod GPU** | LLM inference (RTX A5000) |
| **PostgreSQL** | Database |

## Support

- Website: https://eversale.io/desktop
- Dashboard: https://eversale.io/desktop/success?login=1
- Email: support@eversale.io
