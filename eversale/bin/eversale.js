#!/usr/bin/env node
/**
 * Eversale CLI - Your AI Employee
 *
 * Complete first-run setup:
 * 1. Copy bundled engine to ~/.eversale/engine
 * 2. Create Python venv and install dependencies
 * 3. Install Playwright browsers
 * 4. Download Rust supervisor (optional acceleration)
 * 5. Pull required Ollama models (qwen2.5, llama3.2, moondream)
 * 6. Run agent
 */

const { spawnSync, spawn, execSync } = require("child_process");
const path = require("path");
const fs = require("fs");
const os = require("os");
const https = require("https");
const readline = require("readline");

// Paths
const EVERSALE_HOME = process.env.EVERSALE_HOME || path.join(os.homedir(), ".eversale");
const BIN_DIR = path.join(EVERSALE_HOME, "bin");
const ENGINE_DIR = path.join(EVERSALE_HOME, "engine");
const VENV_DIR = path.join(EVERSALE_HOME, "venv");
const LOGS_DIR = path.join(EVERSALE_HOME, "logs");
const LICENSE_FILE = path.join(EVERSALE_HOME, "license.key");
const SETUP_MARKER = path.join(EVERSALE_HOME, ".setup-complete");

// Rust binary location
const RUST_BINARY = path.join(BIN_DIR, process.platform === "win32" ? "eversale.exe" : "eversale");

// GitHub release info
const GITHUB_REPO = "eversale/eversale-cli";
const RELEASE_URL = `https://github.com/${GITHUB_REPO}/releases/latest/download`;

// Colors
const RESET = "\x1b[0m";
const GREEN = "\x1b[32m";
const YELLOW = "\x1b[33m";
const RED = "\x1b[31m";
const CYAN = "\x1b[36m";
const DIM = "\x1b[2m";
const BOLD = "\x1b[1m";

function log(msg) { console.log(`${GREEN}[eversale]${RESET} ${msg}`); }
function warn(msg) { console.log(`${YELLOW}[eversale]${RESET} ${msg}`); }
function error(msg) { console.error(`${RED}[eversale]${RESET} ${msg}`); }
function dim(msg) { console.log(`${DIM}${msg}${RESET}`); }
function info(msg) { console.log(`${CYAN}[eversale]${RESET} ${msg}`); }

// Global error handlers for robustness
process.on('uncaughtException', (err) => {
  error(`Uncaught exception: ${err.message}`);
  console.error(err.stack);
  // Don't exit - try to keep running
});

process.on('unhandledRejection', (reason, promise) => {
  error(`Unhandled rejection: ${reason}`);
  // Don't exit - try to keep running
});

// Graceful shutdown on SIGINT (Ctrl+C)
let isShuttingDown = false;
process.on('SIGINT', () => {
  if (isShuttingDown) {
    console.log('\nForce exit');
    process.exit(1);
  }
  isShuttingDown = true;
  console.log(`\n${DIM}Shutting down...${RESET}`);
  process.exit(0);
});

// Animated spinner for loading states (ASCII only - no Unicode)
const SPINNER_FRAMES = ["-", "\\", "|", "/"];
const UPDATE_MESSAGES = [
  "Downloading update",
  "Installing packages",
  "Almost there",
  "Finalizing"
];

function createSpinner() {
  let frameIndex = 0;
  let messageIndex = 0;
  let dots = "";
  let interval;
  const CLEAR_LINE = "\r\x1B[K"; // ANSI escape to clear entire line

  const spin = () => {
    const frame = SPINNER_FRAMES[frameIndex];
    const message = UPDATE_MESSAGES[messageIndex];
    process.stdout.write(`${CLEAR_LINE}${CYAN}${frame}${RESET} ${message}${dots}`);

    frameIndex = (frameIndex + 1) % SPINNER_FRAMES.length;
    dots = dots.length >= 3 ? "" : dots + ".";

    // Change message every ~3 seconds
    if (frameIndex === 0 && dots === "") {
      messageIndex = Math.min(messageIndex + 1, UPDATE_MESSAGES.length - 1);
    }
  };

  return {
    start: () => {
      interval = setInterval(spin, 80);
      spin();
    },
    stop: () => {
      clearInterval(interval);
      process.stdout.write(CLEAR_LINE); // Clear line completely
    }
  };
}

// Async spawn wrapper for npm install with animated spinner
function runNpmInstallWithSpinner(args, options = {}) {
  return new Promise((resolve) => {
    const spinner = createSpinner();
    spinner.start();

    const isWin = process.platform === "win32";
    const child = spawn("npm", args, {
      stdio: "pipe",
      shell: isWin,
      ...options
    });

    let stderr = "";
    child.stderr?.on("data", (data) => { stderr += data.toString(); });

    child.on("close", (code) => {
      spinner.stop();
      resolve({ status: code, stderr });
    });

    child.on("error", (err) => {
      spinner.stop();
      resolve({ status: 1, stderr: err.message });
    });

    // Timeout after 120 seconds
    setTimeout(() => {
      child.kill();
      spinner.stop();
      resolve({ status: 1, stderr: "Timeout" });
    }, 120000);
  });
}

function printBanner() {
  // Minimal banner like Claude Code - just version
  try {
    const pkg = require(path.join(__dirname, "..", "package.json"));
    console.log(`${GREEN}${BOLD}eversale${RESET} v${pkg.version}`);
  } catch (e) {
    console.log(`${GREEN}${BOLD}eversale${RESET}`);
  }
  console.log("");
}

// Find Python 3.10+
function findPython() {
  const isWindows = process.platform === "win32";
  const candidates = isWindows ? [
    // Windows: use py launcher first, then python
    "py",
    "python",
    "python3",
  ] : [
    // Unix/macOS/WSL
    "python3.12",
    "python3.11",
    "python3.10",
    "python3",
    "python",
    "/usr/bin/python3",
    "/usr/local/bin/python3",
    "/opt/homebrew/bin/python3",
  ];

  for (const cmd of candidates) {
    try {
      const result = spawnSync(cmd, ["--version"], { stdio: "pipe", timeout: 5000 });
      if (result.status === 0) {
        const version = result.stdout?.toString() || result.stderr?.toString() || "";
        const match = version.match(/Python (\d+)\.(\d+)/);
        if (match) {
          const major = parseInt(match[1]);
          const minor = parseInt(match[2]);
          if (major >= 3 && minor >= 10) {
            return cmd;
          }
        }
      }
    } catch (e) {}
  }
  return null;
}

// Check if required packages are installed (venv or user)
function isVenvReady() {
  // First check venv
  const venvPython = path.join(VENV_DIR, process.platform === "win32" ? "Scripts/python.exe" : "bin/python3");
  if (fs.existsSync(venvPython)) {
    try {
      const result = spawnSync(venvPython, ["-c", "import loguru, playwright, yaml"], { stdio: "pipe", timeout: 10000 });
      if (result.status === 0) return true;
    } catch (e) {}
  }

  // Check system Python with --user packages
  const pythonCmd = findPython();
  if (pythonCmd) {
    try {
      const result = spawnSync(pythonCmd, ["-c", "import loguru, playwright, yaml"], { stdio: "pipe", timeout: 10000 });
      if (result.status === 0) return true;
    } catch (e) {}
  }

  return false;
}

// Create venv and install dependencies
function setupPythonEnv(pythonCmd) {
  log("Setting up Python environment...");

  let useVenv = true;
  let pipCmd, pythonExe;

  // Try to create venv
  if (!fs.existsSync(path.join(VENV_DIR, "bin")) && !fs.existsSync(path.join(VENV_DIR, "Scripts"))) {
    info("Creating virtual environment...");
    const result = spawnSync(pythonCmd, ["-m", "venv", VENV_DIR], { stdio: "inherit", timeout: 60000 });
    if (result.status !== 0) {
      warn("Could not create venv, using --user install instead");
      useVenv = false;
    }
  }

  if (useVenv && (fs.existsSync(path.join(VENV_DIR, "bin")) || fs.existsSync(path.join(VENV_DIR, "Scripts")))) {
    pipCmd = path.join(VENV_DIR, process.platform === "win32" ? "Scripts/pip.exe" : "bin/pip");
    pythonExe = path.join(VENV_DIR, process.platform === "win32" ? "Scripts/python.exe" : "bin/python3");

    // Upgrade pip in venv
    info("Upgrading pip...");
    spawnSync(pipCmd, ["install", "--upgrade", "pip"], { stdio: "pipe", timeout: 60000 });
  } else {
    // Use system Python with --user
    useVenv = false;
    pipCmd = pythonCmd;
    pythonExe = pythonCmd;
  }

  // Install requirements
  const reqPath = path.join(ENGINE_DIR, "requirements.txt");
  if (fs.existsSync(reqPath)) {
    info("Installing Python dependencies (this may take a minute)...");
    let installArgs;
    if (useVenv) {
      installArgs = ["install", "-r", reqPath];
      const result = spawnSync(pipCmd, installArgs, { stdio: "inherit", timeout: 300000 });
      if (result.status !== 0) {
        warn("Some dependencies failed to install");
      }
    } else {
      // Use pip with --user flag for system Python
      installArgs = ["-m", "pip", "install", "--user", "-r", reqPath];
      const result = spawnSync(pipCmd, installArgs, { stdio: "inherit", timeout: 300000 });
      if (result.status !== 0) {
        warn("Some dependencies failed to install");
      }
    }
  }

  // Install browser automation (both playwright and patchright for stealth)
  info("Installing browser automation...");
  const isWindows = process.platform === "win32";

  // Install standard playwright browsers
  spawnSync(pythonExe, ["-m", "playwright", "install", "chromium"], {
    stdio: "inherit",
    timeout: 300000,
    shell: isWindows
  });

  // Install patchright browsers (stealth/undetected browser - different version)
  info("Installing stealth browser (patchright)...");
  spawnSync(pythonExe, ["-m", "patchright", "install", "chromium"], {
    stdio: "inherit",
    timeout: 300000,
    shell: isWindows
  });

  // Install Rust core wheel if bundled
  installRustCore(useVenv ? pipCmd : pythonCmd, useVenv);

  log("Python environment ready!");
  return true;
}

// Ensure browsers are installed (can be called independently)
function ensureBrowsers(pythonCmd) {
  const isWindows = process.platform === "win32";

  // Check if chromium is installed for patchright (needs version 1187 specifically)
  const browserPath = process.platform === "win32"
    ? path.join(os.homedir(), "AppData", "Local", "ms-playwright")
    : path.join(os.homedir(), ".cache", "ms-playwright");

  // Patchright needs chromium_headless_shell-1187 specifically
  const patchrightBrowserDir = path.join(browserPath, "chromium_headless_shell-1187");
  const hasPatchrightBrowser = fs.existsSync(patchrightBrowserDir);

  if (!hasPatchrightBrowser) {
    info("Installing stealth browser (first time only)...");

    // First ensure patchright is installed
    spawnSync(pythonCmd, ["-m", "pip", "install", "--user", "-q", "patchright"], {
      stdio: "pipe",
      timeout: 60000,
      shell: isWindows
    });

    // Then install patchright browsers
    const result = spawnSync(pythonCmd, ["-m", "patchright", "install", "chromium"], {
      stdio: "inherit",
      timeout: 300000,
      shell: isWindows
    });

    if (result.status === 0) {
      log("Stealth browser installed");
    } else {
      warn("Could not install stealth browser (will use fallback)");
    }
  } else {
    dim("Stealth browser already installed");
  }
}

// Ensure Ollama models are installed
function ensureOllamaModels() {
  const requiredModels = [
    'qwen2.5:7b-instruct',
    'llama3.2:3b-instruct-q4_0',
    'moondream'  // NEW - fast vision for UI targeting
  ];

  info("Checking Ollama models...");

  for (const model of requiredModels) {
    try {
      // Check if model exists
      const checkResult = spawnSync("ollama", ["list"], { stdio: "pipe", timeout: 10000 });
      if (checkResult.status === 0) {
        const output = checkResult.stdout?.toString() || "";
        if (output.includes(model.split(':')[0])) {
          dim(`  [ok] ${model} already installed`);
          continue;
        }
      }

      // Model not found, try to pull it
      info(`  Pulling ${model}...`);
      const pullResult = spawnSync("ollama", ["pull", model], { stdio: "inherit", timeout: 600000 });
      if (pullResult.status === 0) {
        log(`  [ok] ${model} installed`);
      } else {
        warn(`  Could not pull ${model} (will try on first use)`);
      }
    } catch (e) {
      warn(`  Could not pull ${model}: ${e.message}`);
    }
  }
}

// Install bundled Rust core wheel for 10-100x performance boost
function installRustCore(pipCmd, useVenv) {
  const wheelsDir = path.join(__dirname, "..", "engine", "rust_wheels");

  if (!fs.existsSync(wheelsDir)) {
    dim("Rust acceleration not bundled (using Python fallback)");
    return false;
  }

  // Find matching wheel for this platform
  const platform = os.platform();
  const arch = os.arch();

  let platformPattern;
  if (platform === "linux") {
    platformPattern = arch === "arm64" ? "manylinux.*aarch64" : "manylinux.*x86_64";
  } else if (platform === "darwin") {
    platformPattern = arch === "arm64" ? "macosx.*arm64" : "macosx.*x86_64";
  } else if (platform === "win32") {
    platformPattern = arch === "arm64" ? "win_arm64" : "win_amd64";
  } else {
    dim("Rust acceleration not available for this platform");
    return false;
  }

  const wheels = fs.readdirSync(wheelsDir).filter(f => f.endsWith(".whl"));

  // Try to find platform-specific wheel, or use abi3 universal wheel
  let wheelPath = null;
  for (const wheel of wheels) {
    if (wheel.match(new RegExp(platformPattern)) || wheel.includes("abi3")) {
      wheelPath = path.join(wheelsDir, wheel);
      break;
    }
  }

  if (!wheelPath) {
    dim("No compatible Rust wheel found (using Python fallback)");
    return false;
  }

  info("Installing Rust acceleration (10-100x faster extraction)...");

  let result;
  if (useVenv) {
    result = spawnSync(pipCmd, ["install", "--force-reinstall", wheelPath], { stdio: "pipe", timeout: 60000 });
  } else {
    result = spawnSync(pipCmd, ["-m", "pip", "install", "--user", "--force-reinstall", wheelPath], { stdio: "pipe", timeout: 60000 });
  }

  if (result.status === 0) {
    log("Rust core installed (eversale_core module ready)");
    return true;
  } else {
    dim("Rust wheel install failed (using Python fallback)");
    return false;
  }
}

// Copy bundled engine
function ensureEngine() {
  const bundledEngine = path.join(__dirname, "..", "engine");
  const versionFile = path.join(ENGINE_DIR, ".version");

  if (!fs.existsSync(bundledEngine)) {
    error("Bundled engine not found!");
    return false;
  }

  let bundledVersion, installedVersion;
  try {
    const pkg = require(path.join(__dirname, "..", "package.json"));
    bundledVersion = pkg.version;
  } catch (e) {
    bundledVersion = "0.0.0";
  }

  try {
    installedVersion = fs.existsSync(versionFile) ? fs.readFileSync(versionFile, "utf8").trim() : "0";
  } catch (e) {
    installedVersion = "0";
  }

  if (bundledVersion === installedVersion && fs.existsSync(path.join(ENGINE_DIR, "run_ultimate.py"))) {
    return true;
  }

  info(`Installing engine v${bundledVersion}...`);
  fs.mkdirSync(ENGINE_DIR, { recursive: true });

  try {
    if (process.platform === "win32") {
      const result = spawnSync("xcopy", ["/E", "/I", "/Y", bundledEngine, ENGINE_DIR], { stdio: "pipe" });
      if (result.status !== 0) {
        throw new Error(`xcopy failed with status ${result.status}`);
      }
    } else {
      const result = spawnSync("cp", ["-r", `${bundledEngine}/.`, `${ENGINE_DIR}/`], { stdio: "pipe" });
      if (result.status !== 0) {
        throw new Error(`cp failed with status ${result.status}`);
      }
    }
    fs.writeFileSync(versionFile, bundledVersion);
    // Also write version.txt to EVERSALE_HOME for Python to read
    fs.writeFileSync(path.join(EVERSALE_HOME, "version.txt"), bundledVersion);
    return true;
  } catch (e) {
    error(`Failed to copy engine: ${e.message}`);
    return false;
  }
}

// Check if Rust binary exists
function hasRustBinary() {
  if (!fs.existsSync(RUST_BINARY)) return false;
  try {
    const result = spawnSync(RUST_BINARY, ["--version"], { stdio: "pipe", timeout: 5000 });
    return result.status === 0;
  } catch (e) {
    return false;
  }
}

// Download Rust binary (optional)
async function downloadRustBinary() {
  const platform = os.platform();
  const arch = os.arch();

  let osName = "linux";
  if (platform === "darwin") osName = "darwin";
  else if (platform === "win32") osName = "windows";

  let archName = "x86_64";
  if (arch === "arm64") archName = "aarch64";

  const binaryName = osName === "windows" ? "eversale.exe" : "eversale";
  const tarballUrl = `${RELEASE_URL}/eversale-${osName}-${archName}.tar.gz`;

  return new Promise((resolve) => {
    const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "eversale-"));
    const tarPath = path.join(tempDir, "eversale.tar.gz");

    const file = fs.createWriteStream(tarPath);
    const request = (url) => {
      https.get(url, { headers: { "User-Agent": "eversale-cli" }, timeout: 30000 }, (response) => {
        if (response.statusCode === 301 || response.statusCode === 302) {
          file.close();
          try { fs.unlinkSync(tarPath); } catch(e) {}
          request(response.headers.location);
          return;
        }

        if (response.statusCode !== 200) {
          file.close();
          resolve(false);
          return;
        }

        response.pipe(file);
        file.on("finish", () => {
          file.close();
          try {
            const result = spawnSync("tar", ["-xzf", tarPath, "-C", tempDir], { stdio: "pipe" });
            if (result.status !== 0) {
              resolve(false);
              return;
            }
            const possiblePaths = [
              path.join(tempDir, "bin", binaryName),
              path.join(tempDir, binaryName),
            ];
            for (const srcPath of possiblePaths) {
              if (fs.existsSync(srcPath)) {
                fs.mkdirSync(BIN_DIR, { recursive: true });
                fs.copyFileSync(srcPath, RUST_BINARY);
                if (osName !== "windows") fs.chmodSync(RUST_BINARY, 0o755);
                fs.rmSync(tempDir, { recursive: true, force: true });
                resolve(true);
                return;
              }
            }
            resolve(false);
          } catch (e) {
            resolve(false);
          }
        });
      }).on("error", () => {
        file.close();
        resolve(false);
      }).on("timeout", () => {
        file.close();
        resolve(false);
      });
    };
    request(tarballUrl);
  });
}

// Full first-run setup
async function runSetup() {
  printBanner();
  log("First-time setup starting...");
  console.log("");

  // Create directories
  fs.mkdirSync(EVERSALE_HOME, { recursive: true });
  fs.mkdirSync(BIN_DIR, { recursive: true });
  fs.mkdirSync(ENGINE_DIR, { recursive: true });
  fs.mkdirSync(LOGS_DIR, { recursive: true });

  // 1. Check Python
  const pythonCmd = findPython();
  if (!pythonCmd) {
    error("Python 3.10+ not found!");
    console.log("");
    console.log("Please install Python:");
    if (process.platform === "darwin") {
      console.log("  brew install python@3.12");
      console.log("");
      console.log("Or download from: https://www.python.org/downloads/");
    } else if (process.platform === "linux") {
      console.log("  sudo apt install python3.12 python3.12-venv python3-pip");
    } else if (process.platform === "win32") {
      console.log("");
      console.log("  1. Download Python from: https://www.python.org/downloads/");
      console.log("  2. Run the installer");
      console.log(`  3. ${BOLD}IMPORTANT:${RESET} Check "Add Python to PATH" during install`);
      console.log("  4. Restart PowerShell and run 'eversale' again");
      console.log("");
      console.log("Or use winget:");
      console.log("  winget install Python.Python.3.12");
    } else {
      console.log("  Download from https://www.python.org/downloads/");
    }
    console.log("");
    process.exit(1);
  }
  log(`Found Python: ${pythonCmd}`);

  // 2. Copy engine
  if (!ensureEngine()) {
    error("Failed to install engine");
    process.exit(1);
  }

  // 3. Setup Python venv and dependencies
  if (!isVenvReady()) {
    setupPythonEnv(pythonCmd);
  } else {
    log("Python environment already configured");
    // Still ensure browsers are installed even if Python is ready
    ensureBrowsers(pythonCmd);
  }

  // 4. Try to download Rust binary (optional, don't fail if unavailable)
  info("Checking for Rust acceleration...");
  const rustOk = await downloadRustBinary();
  if (rustOk) {
    log("Rust supervisor installed (faster execution)");
  } else {
    dim("Rust acceleration not available (using Python mode)");
  }

  // NOTE: Ollama models NOT needed - CLI uses remote GPU server at eversale.io
  // Local Ollama is only for development/testing
  dim("Using remote AI server (eversale.io)");

  // Mark setup complete
  fs.writeFileSync(SETUP_MARKER, new Date().toISOString());

  console.log("");
  log("Setup complete!");
  console.log("");
  dim(`Engine: ${ENGINE_DIR}`);
  dim(`Python: ${VENV_DIR}`);
  dim(`Logs:   ${LOGS_DIR}`);
  console.log("");

  return true;
}

// Check if setup is needed
function needsSetup() {
  if (!fs.existsSync(SETUP_MARKER)) return true;
  if (!fs.existsSync(path.join(ENGINE_DIR, "run_ultimate.py"))) return true;
  if (!isVenvReady()) return true;
  return false;
}

// Run the agent
function runAgent(args) {
  const runnerPath = path.join(ENGINE_DIR, "run_ultimate.py");

  // Prefer Rust binary if available
  if (hasRustBinary()) {
    dim("Using Rust supervisor");
    const child = spawn(RUST_BINARY, args, {
      stdio: "inherit",
      env: { ...process.env, EVERSALE_HOME }
    });
    child.on("exit", (code) => process.exit(code ?? 0));
    return;
  }

  // Fall back to Python
  const isWindows = process.platform === "win32";
  let pythonPath = path.join(VENV_DIR, isWindows ? "Scripts/python.exe" : "bin/python3");
  if (!fs.existsSync(pythonPath)) {
    pythonPath = findPython() || (isWindows ? "python" : "python3");
  }

  if (!fs.existsSync(runnerPath)) {
    error("Engine not found. Try: eversale --setup");
    process.exit(1);
  }

  // Use correct path separator for PYTHONPATH (: on Unix, ; on Windows)
  const pathSep = isWindows ? ";" : ":";
  const pythonPathEnv = `${ENGINE_DIR}${pathSep}${process.env.PYTHONPATH || ""}`;

  const child = spawn(pythonPath, [runnerPath, ...args], {
    cwd: ENGINE_DIR,
    stdio: "inherit",
    shell: isWindows,  // Use shell on Windows for better compatibility
    env: {
      ...process.env,
      EVERSALE_HOME,
      PYTHONPATH: pythonPathEnv,
    }
  });

  child.on("exit", (code, signal) => {
    if (signal) process.kill(process.pid, signal);
    else process.exit(code ?? 0);
  });
}

// AGENTIC MODE: Run general-purpose browser automation (default)
async function runAgenticBrowser(prompt) {
  const agenticPath = path.join(ENGINE_DIR, "agent", "agentic_browser.py");

  // Ensure engine is installed
  ensureEngine();

  // Check agentic_browser.py exists
  if (!fs.existsSync(agenticPath)) {
    error("Agentic browser module not found. Try: eversale --setup");
    process.exit(1);
  }

  // Find Python
  const isWindows = process.platform === "win32";
  let pythonPath = path.join(VENV_DIR, isWindows ? "Scripts/python.exe" : "bin/python3");
  if (!fs.existsSync(pythonPath)) {
    pythonPath = findPython() || (isWindows ? "python" : "python3");
  }

  console.log(`${GREEN}${BOLD}eversale${RESET} agent mode`);
  console.log("");

  // Get version from package.json for passing to Python
  let pkgVersion = "2.1.172";
  try {
    const pkgPath = path.join(__dirname, "..", "package.json");
    if (fs.existsSync(pkgPath)) {
      pkgVersion = JSON.parse(fs.readFileSync(pkgPath, "utf8")).version || pkgVersion;
    }
  } catch (e) { /* ignore */ }

  return new Promise((resolve, reject) => {
    // Pass prompt via env var to avoid Windows shell escaping issues with |, <, >, etc.
    const child = spawn(pythonPath, ["-m", "agent.agentic_browser"], {
      cwd: ENGINE_DIR,
      stdio: "inherit",
      shell: isWindows,
      env: {
        ...process.env,
        EVERSALE_HOME,
        EVERSALE_PROMPT: prompt,
        EVERSALE_VERSION: pkgVersion,
        PYTHONPATH: ENGINE_DIR,
      }
    });

    child.on("exit", (code) => {
      if (code === 0) resolve();
      else reject(new Error(`Task exited with code ${code}`));
    });

    child.on("error", (err) => {
      reject(new Error(`Agentic browser failed: ${err.message}`));
    });
  });
}

// FAST MODE: Run site-specific extraction (--fast flag)
async function runFastExtract(prompt) {
  const fastExtractPath = path.join(ENGINE_DIR, "agent", "fast_extract.py");

  // Ensure engine is installed
  ensureEngine();

  // Check fast_extract.py exists
  if (!fs.existsSync(fastExtractPath)) {
    error("Fast extract module not found. Try: eversale --setup");
    process.exit(1);
  }

  // Find Python
  const isWindows = process.platform === "win32";
  let pythonPath = path.join(VENV_DIR, isWindows ? "Scripts/python.exe" : "bin/python3");
  if (!fs.existsSync(pythonPath)) {
    pythonPath = findPython() || (isWindows ? "python" : "python3");
  }

  console.log(`${GREEN}${BOLD}eversale${RESET} fast extract mode`);
  console.log("");

  // Get version from package.json for passing to Python
  let pkgVersion = "2.1.172";
  try {
    const pkgPath = path.join(__dirname, "..", "package.json");
    if (fs.existsSync(pkgPath)) {
      pkgVersion = JSON.parse(fs.readFileSync(pkgPath, "utf8")).version || pkgVersion;
    }
  } catch (e) { /* ignore */ }

  return new Promise((resolve, reject) => {
    // Pass prompt via env var to avoid Windows shell escaping issues with |, <, >, etc.
    const child = spawn(pythonPath, [fastExtractPath], {
      cwd: ENGINE_DIR,
      stdio: "inherit",
      shell: isWindows,
      env: {
        ...process.env,
        EVERSALE_HOME,
        EVERSALE_PROMPT: prompt,
        EVERSALE_VERSION: pkgVersion,
        PYTHONPATH: ENGINE_DIR,
      }
    });

    child.on("exit", (code) => {
      if (code === 0) resolve();
      else reject(new Error(`Fast extract exited with code ${code}`));
    });

    child.on("error", (err) => {
      reject(new Error(`Fast extract failed: ${err.message}`));
    });
  });
}

// Check for updates and auto-update synchronously
async function checkForUpdates() {
  if (process.env.EVERSALE_SKIP_UPDATE_CHECK === "1") return;
  return new Promise((resolve) => {
    try {
      const pkg = require(path.join(__dirname, "..", "package.json"));
      const currentVersion = pkg.version;

      // Quick npm registry check (timeout 5s)
      const req = https.get(
        "https://registry.npmjs.org/eversale-cli/latest",
        { timeout: 5000 },
        (res) => {
          let data = "";
          res.on("data", (chunk) => (data += chunk));
          res.on("end", async () => {
            try {
              const latest = JSON.parse(data);
              if (latest.version && latest.version !== currentVersion) {
                // Compare semver (simple comparison)
                const latestParts = latest.version.split(".").map(Number);
                const currentParts = currentVersion.split(".").map(Number);

                let needsUpdate = false;
                for (let i = 0; i < 3; i++) {
                  if ((latestParts[i] || 0) > (currentParts[i] || 0)) {
                    needsUpdate = true;
                    break;
                  } else if ((latestParts[i] || 0) < (currentParts[i] || 0)) {
                    break;
                  }
                }

                if (needsUpdate) {
                  console.log("");
                  console.log(`${YELLOW}[update]${RESET} New version ${latest.version} available (current: ${currentVersion})`);

                  const isMac = process.platform === "darwin";
                  const isLinux = process.platform === "linux";

                  // Try normal install first with animated spinner
                  let updateResult = await runNpmInstallWithSpinner(["install", "-g", "eversale-cli@latest"]);

                  // If failed on Unix, try with sudo (common permission issue)
                  if (updateResult.status !== 0 && (isLinux || isMac)) {
                    const stderr = updateResult.stderr || "";
                    if (stderr.includes("EACCES") || stderr.includes("permission denied")) {
                      console.log(`${DIM}Trying with elevated permissions...${RESET}`);
                      updateResult = spawnSync("sudo", ["npm", "install", "-g", "eversale-cli@latest"], {
                        stdio: "inherit",
                        timeout: 120000
                      });
                    }
                  }

                  if (updateResult.status === 0) {
                    console.log(`${GREEN}[update]${RESET} Updated to v${latest.version}!`);

                    // Force reinstall engine from new package
                    const versionFile = path.join(ENGINE_DIR, ".version");
                    try {
                      // Delete version marker to force engine reinstall
                      if (fs.existsSync(versionFile)) {
                        fs.unlinkSync(versionFile);
                      }
                    } catch (e) {}

                    console.log(`${GREEN}[update]${RESET} Relaunching to apply update...`);
                    console.log("");

                    const relaunchedEnv = { ...process.env, EVERSALE_SKIP_UPDATE_CHECK: "1" };
                    const relaunchArgs = process.argv.slice(2);

                    // Prefer invoking the installed CLI entrypoint (so we pick up new shims/paths).
                    // On Windows, use a shell so `eversale` resolves to the updated `.cmd` shim.
                    let relaunchResult = spawnSync(
                      "eversale",
                      relaunchArgs,
                      { stdio: "inherit", env: relaunchedEnv, shell: process.platform === "win32" }
                    );

                    // Fallback: directly invoke this script path via node (works when the file is updated in-place).
                    if (relaunchResult.error) {
                      relaunchResult = spawnSync(
                        process.execPath,
                        [__filename, ...relaunchArgs],
                        { stdio: "inherit", env: relaunchedEnv }
                      );
                    }

                    process.exit(relaunchResult.status ?? 1);
                  } else {
                    warn("Update failed, continuing with current version");
                    if (process.platform === "win32") {
                      dim("Run manually: npm install -g eversale-cli@latest");
                    } else {
                      dim("Run manually: sudo npm install -g eversale-cli@latest");
                    }
                    console.log("");
                  }
                }
              }
            } catch (e) {}
            resolve();
          });
        }
      );
      req.on("error", () => resolve());
      req.on("timeout", () => { req.destroy(); resolve(); });
    } catch (e) {
      resolve();
    }
  });
}

// Handle --version
function showVersion() {
  try {
    const pkg = require(path.join(__dirname, "..", "package.json"));
    console.log(`eversale-cli ${pkg.version}`);
  } catch (e) {
    console.log("eversale-cli (version unknown)");
  }
}

// Handle --help - comprehensive but clean
function showHelp() {
  printBanner();
  console.log(`${BOLD}Usage:${RESET} eversale [options] [prompt]`);
  console.log("");
  console.log(`${BOLD}Commands:${RESET}`);
  console.log("  (no args)                  Interactive mode");
  console.log("  <prompt>                   Run task (natural language)");
  console.log("  activate <token>           Activate license");
  console.log("  update                     Check for and install updates");
  console.log("  examples                   Show example prompts");
  console.log("");
  console.log(`${BOLD}Recording (beta):${RESET}`);
  console.log('  record "<goal>"            Start recording session');
  console.log('  replay "<id>"              Replay saved recording');
  console.log("");
  console.log(`${BOLD}Login:${RESET}`);
  console.log("  In interactive mode, type: login <service>");
  console.log("  Services: gmail, linkedin, twitter, facebook, outlook");
  console.log("  Logins persist in ~/.eversale/browser-profile/");
  console.log("");
  console.log(`${BOLD}Update:${RESET}`);
  console.log("  eversale update            Auto-update to latest version");
  console.log("  npm update -g eversale-cli Manual npm update");
  console.log("");
  console.log(`${BOLD}Options:${RESET}`);
  console.log("  --fast                     Fast extraction (site-specific, no AI)");
  console.log("  --full                     Full orchestration (scheduling, recording)");
  console.log("  --setup                    Force re-run setup");
  console.log("  --version, -v              Show version");
  console.log("  --help, -h                 Show this help");
  console.log("");
  console.log(`${BOLD}Advanced:${RESET}`);
  console.log('  record "<goal>"            Start recording session');
  console.log('  replay "<id>"              Replay saved recording');
  console.log('  schedule "<when>: <task>"  Schedule recurring task');
  console.log("");
  console.log(`${BOLD}Examples:${RESET}`);
  console.log(`  eversale "go to google and search AI news"    ${DIM}# Agentic (default)${RESET}`);
  console.log(`  eversale "fill out contact form on example.com"`);
  console.log(`  eversale "log into linkedin and find sales managers"`);
  console.log(`  eversale --fast "fb ads booked meetings"      ${DIM}# Fast extract${RESET}`);
  console.log(`  eversale --full "every day at 9am check email" ${DIM}# Full orchestration${RESET}`);
  console.log("");
}

// Show examples
function showExamples() {
  printBanner();
  console.log(`${BOLD}Example Prompts${RESET}`);
  console.log("");
  console.log("Research:");
  console.log('  eversale "Research top 10 CRM software companies"');
  console.log('  eversale "Find YC startups in the AI space"');
  console.log("");
  console.log("Lead Generation:");
  console.log('  eversale "Find leads from Facebook Ads Library for dog food"');
  console.log('  eversale "Extract emails from company websites in my CSV"');
  console.log("");
  console.log("Email:");
  console.log('  eversale "Summarize unread emails in Gmail"');
  console.log('  eversale "Draft replies to important emails"');
  console.log("");
  console.log("Automation:");
  console.log('  eversale "Fill out the contact form on example.com"');
  console.log('  eversale "Post this update to LinkedIn"');
  console.log("");
}

// Heuristic: detect natural-language scheduling phrases
function isSchedulePrompt(prompt) {
  const p = prompt.toLowerCase();
  const hasEvery = /every\s+\d+\s+(minute|min|hour|day|week)/.test(p);
  const hasDaily = p.includes("daily") || p.includes("every day");
  const hasWeekly = p.includes("every monday") || p.includes("every tuesday") || p.includes("every wednesday") ||
    p.includes("every thursday") || p.includes("every friday") || p.includes("every saturday") || p.includes("every sunday");
  const hasForever = p.includes("forever");
  const hasAtTime = /every\s+\w+\s+at\s+\d/.test(p);
  return hasEvery || hasDaily || hasWeekly || hasForever || hasAtTime;
}

// Heuristic: detect natural-language recording phrases
function isRecordPrompt(prompt) {
  const p = prompt.toLowerCase().trim();
  return p.startsWith("record ") || p.startsWith("start recording") || p.startsWith("recording ");
}

// Main
async function main() {
  const args = process.argv.slice(2);

  // Flag-based shortcuts
  const recordFlagIndex = args.findIndex(a => a === "--record");
  if (recordFlagIndex >= 0 && args[recordFlagIndex + 1]) {
    const goal = args.slice(recordFlagIndex + 1).join(" ");
    await runAgent(["interactive", "record", goal]);
    return;
  }

  const replayFlagIndex = args.findIndex(a => a === "--replay");
  if (replayFlagIndex >= 0 && args[replayFlagIndex + 1]) {
    // Support optional --replay-input path
    let target = args[replayFlagIndex + 1];
    let inputPath = null;
    const inputIdx = args.findIndex(a => a === "--replay-input");
    if (inputIdx >= 0 && args[inputIdx + 1]) {
      inputPath = args[inputIdx + 1];
    }
    const replayArgs = ["interactive", "replay", target];
    if (inputPath) {
      replayArgs.push("--input", inputPath);
    }
    await runAgent(replayArgs);
    return;
  }

  const scheduleFlagIndex = args.findIndex(a => a === "--schedule");
  if (scheduleFlagIndex >= 0 && args[scheduleFlagIndex + 1]) {
    const schedPrompt = args.slice(scheduleFlagIndex + 1).join(" ");
    await runAgent(["interactive", "schedule", schedPrompt]);
    return;
  }

  // Top-level record/replay/schedule commands (map to interactive equivalents)
  if (args[0] === "record" && args[1]) {
    await runAgent(["interactive", "record", args.slice(1).join(" ")]);
    return;
  }

  if (args[0] === "replay" && args[1]) {
    await runAgent(["interactive", "replay", args.slice(1).join(" ")]);
    return;
  }

  if (args[0] === "schedule" && args[1]) {
    await runAgent(["interactive", "schedule", args.slice(1).join(" ")]);
    return;
  }

  // Handle activate command
  if (args[0] === "activate" && args[1]) {
    const token = args[1];
    try {
      // Ensure directory exists
      fs.mkdirSync(EVERSALE_HOME, { recursive: true });
      // Save the license key
      fs.writeFileSync(LICENSE_FILE, token.trim());
      log(`License activated successfully!`);
      log(`License saved to: ${LICENSE_FILE}`);
      console.log("");
      log("You can now run: eversale \"your task here\"");
      return;
    } catch (e) {
      error(`Failed to save license: ${e.message}`);
      process.exit(1);
    }
  }

  // Handle flags
  if (args.includes("--version") || args.includes("-v")) {
    showVersion();
    return;
  }

  if (args.includes("--help") || args.includes("-h")) {
    showHelp();
    return;
  }

  if (args.includes("--setup")) {
    await runSetup();
    return;
  }

  if (args.includes("--setup-silent")) {
    try {
      fs.mkdirSync(EVERSALE_HOME, { recursive: true });
      ensureEngine();
    } catch (e) {}
    return;
  }

  if (args[0] === "examples") {
    showExamples();
    return;
  }

  // Manual update command
  if (args[0] === "update") {
    log("Checking for updates...");
    // Force update check by temporarily unsetting the skip flag
    const originalSkip = process.env.EVERSALE_SKIP_UPDATE_CHECK;
    delete process.env.EVERSALE_SKIP_UPDATE_CHECK;
    await checkForUpdates();
    process.env.EVERSALE_SKIP_UPDATE_CHECK = originalSkip;
    // If we get here, no update was needed (otherwise checkForUpdates exits after update)
    try {
      const pkg = require(path.join(__dirname, "..", "package.json"));
      log(`Already on latest version (${pkg.version})`);
    } catch (e) {
      log("Already on latest version");
    }
    return;
  }

  // Check for updates (quick, non-blocking check)
  await checkForUpdates();

  // Ensure engine exists
  ensureEngine();

  // License check - only for commands that need it
  const hasLicense = true; // Local mode - license bypassed

  // FULL MODE: Use old orchestration layer (scheduling, recording, complex multi-step)
  const fullFlagIndex = args.findIndex(a => a === "--full");
  if (fullFlagIndex >= 0) {
    if (!hasLicense) {
      error("License required. Run: eversale activate <token>");
      process.exit(1);
    }
    const fullArgs = args.filter((a, i) => i !== fullFlagIndex);
    if (needsSetup()) {
      await runSetup();
    }
    runAgent(fullArgs);
    return;
  }

  // FAST MODE: Site-specific extraction (no AI needed)
  const fastFlagIndex = args.findIndex(a => a === "--fast");
  if (fastFlagIndex >= 0) {
    const fastArgs = args.filter((a, i) => i !== fastFlagIndex);
    const fastPrompt = fastArgs.filter(a => !a.startsWith("--")).join(" ");
    if (fastPrompt) {
      await runFastExtract(fastPrompt);
      return;
    }
  }

  // Interactive mode (no args) - prompt for task
  if (args.length === 0) {
    if (!hasLicense) {
      error("License required. Run: eversale activate <token>");
      process.exit(1);
    }
    // Load package.json for version (with fallback)
    let pkgVersion = "2.1.161";
    try {
      const pkg = require(path.join(__dirname, "..", "package.json"));
      pkgVersion = pkg.version;
    } catch (e) {
      // Use fallback version
    }
    // Show interactive prompt with banner (OpenCode-style clean layout)
    console.log("");
    console.log(`${GREEN}${BOLD}`);
    console.log("███████╗██╗   ██╗███████╗██████╗ ███████╗ █████╗ ██╗     ███████╗");
    console.log("██╔════╝██║   ██║██╔════╝██╔══██╗██╔════╝██╔══██╗██║     ██╔════╝");
    console.log("█████╗  ██║   ██║█████╗  ██████╔╝███████╗███████║██║     █████╗  ");
    console.log("██╔══╝  ╚██╗ ██╔╝██╔══╝  ██╔══██╗╚════██║██╔══██║██║     ██╔══╝  ");
    console.log("███████╗ ╚████╔╝ ███████╗██║  ██║███████║██║  ██║███████╗███████╗");
    console.log("╚══════╝  ╚═══╝  ╚══════╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚══════╝╚══════╝");
    console.log(`${RESET}`);

    // Status bar (OpenCode style)
    console.log(`${DIM}${"-".repeat(68)}${RESET}`);
    console.log(`${DIM}  v${pkgVersion}  ${RESET}${CYAN}|${RESET}${DIM}  Agentic browser runtime${RESET}`);
    console.log(`${DIM}${"-".repeat(68)}${RESET}`);
    console.log("");

    // Tips section (OpenCode style)
    console.log(`${DIM}  Tips:${RESET}`);
    console.log(`${DIM}  - Multi-task: "find 1 reddit user; find 1 fb advertiser"${RESET}`);
    console.log(`${DIM}  - Learns from every task - gets smarter over time${RESET}`);
    console.log(`${DIM}  - Type ${RESET}${CYAN}help${RESET}${DIM} for commands, ${RESET}${CYAN}clear${RESET}${DIM} to reset screen${RESET}`);
    console.log("");

    const rl = readline.createInterface({
      input: process.stdin,
      output: process.stdout
    });

    // Handle readline errors gracefully
    rl.on('error', (err) => {
      error(`Input error: ${err.message}`);
    });

    // Handle unexpected close (e.g., pipe closed)
    rl.on('close', () => {
      console.log(`\n${DIM}Session ended${RESET}`);
      process.exit(0);
    });

    // Interactive loop - line-based with multi-line paste support.
    // Pasting multi-line prompts previously caused each line to run as a separate task; instead,
    // we debounce input and submit the whole paste as ONE prompt.
    rl.setPrompt(`${CYAN}>${RESET} `);

    let pendingLines = [];
    let flushTimer = null;
    let isRunningTask = false;
    const queuedPrompts = [];

    const printHelp = () => {
      console.log(`${CYAN}Commands:${RESET}`);
      console.log(`  ${DIM}exit, quit, q${RESET}  - Exit interactive mode`);
      console.log(`  ${DIM}help, ?${RESET}       - Show this help`);
      console.log(`  ${DIM}clear${RESET}         - Clear screen`);
      console.log(`  ${DIM}version${RESET}       - Show version`);
      console.log(`  ${DIM}update${RESET}        - Check for updates`);
      console.log(`  ${DIM}<any prompt>${RESET}  - Run browser task (multi-line paste supported)`);
      console.log("");
    };

    const runPrompt = async (promptText) => {
      // If a task is already running, queue it (stdin is shared with the child process).
      if (isRunningTask) {
        queuedPrompts.push(promptText);
        return;
      }

      isRunningTask = true;
      rl.pause(); // Let the child process own stdin during execution.

      try {
        await runAgenticBrowser(promptText);
        console.log(`${GREEN}Task completed${RESET}`);
      } catch (err) {
        error(`Task failed: ${err.message}`);
        console.log(`${DIM}You can try again or type 'exit' to quit${RESET}`);
      } finally {
        isRunningTask = false;
        rl.resume();
        console.log("");

        // Drain any queued prompts (from paste/typing during execution)
        if (queuedPrompts.length > 0) {
          const next = queuedPrompts.shift();
          // Schedule asynchronously so prompt output renders cleanly first.
          setTimeout(() => runPrompt(next), 0);
          return;
        }

        rl.prompt();
      }
    };

    const flushPending = async () => {
      if (flushTimer) {
        clearTimeout(flushTimer);
        flushTimer = null;
      }

      const text = pendingLines.join("\n").trim();
      pendingLines = [];

      if (!text) {
        rl.prompt();
        return;
      }

      // Single-line commands (only treat as commands when NOT multi-line)
      if (!text.includes("\n")) {
        const cmd = text.trim();

        if (cmd === 'exit' || cmd === 'quit' || cmd === 'q') {
          console.log(`${DIM}Goodbye!${RESET}`);
          rl.close();
          return;
        }

        if (cmd === 'help' || cmd === '?') {
          printHelp();
          rl.prompt();
          return;
        }

        if (cmd === 'clear' || cmd === 'cls') {
          console.clear();
          rl.prompt();
          return;
        }

        if (cmd === 'version' || cmd === 'v') {
          console.log(`eversale-cli ${pkgVersion}`);
          rl.prompt();
          return;
        }

        if (cmd === 'update') {
          log("Checking for updates...");
          const originalSkip = process.env.EVERSALE_SKIP_UPDATE_CHECK;
          delete process.env.EVERSALE_SKIP_UPDATE_CHECK;
          await checkForUpdates();
          process.env.EVERSALE_SKIP_UPDATE_CHECK = originalSkip;
          log(`Already on latest version (${pkgVersion})`);
          rl.prompt();
          return;
        }
      }

      await runPrompt(text);
    };

    const scheduleFlush = () => {
      if (flushTimer) clearTimeout(flushTimer);
      // Debounce to group multi-line pastes into a single prompt.
      flushTimer = setTimeout(() => {
        flushPending().catch((err) => {
          error(`Interactive mode error: ${err.message}`);
          rl.prompt();
        });
      }, 120);
    };

    rl.on('line', (line) => {
      const t = (line || '');

      // Fast path for exit/help/etc when nothing is buffered.
      if (pendingLines.length === 0) {
        const cmd = t.trim();
        if (cmd === 'exit' || cmd === 'quit' || cmd === 'q') {
          console.log(`${DIM}Goodbye!${RESET}`);
          rl.close();
          return;
        }
        if (cmd === 'help' || cmd === '?') {
          printHelp();
          rl.prompt();
          return;
        }
      }

      pendingLines.push(t);

      // If the user entered an empty line and we already have content, flush immediately.
      if (t.trim() === '' && pendingLines.some((l) => l.trim() !== '')) {
        flushPending().catch((err) => {
          error(`Interactive mode error: ${err.message}`);
          rl.prompt();
        });
        return;
      }

      scheduleFlush();
    });

    rl.prompt();
    return;
  }

  // Schedule/record shortcuts - need full orchestration
  const prompt = args.filter(a => !a.startsWith("--")).join(" ");
  if (isSchedulePrompt(prompt) || isRecordPrompt(prompt)) {
    if (!hasLicense) {
      error("License required for scheduling. Run: eversale activate <token>");
      process.exit(1);
    }
    if (needsSetup()) {
      await runSetup();
    }
    if (isSchedulePrompt(prompt)) {
      runAgent(["interactive", "schedule", prompt]);
    } else {
      runAgent(["interactive", "record", prompt]);
    }
    return;
  }

  // DEFAULT: Agentic browser (general purpose autonomous agent)
  // Requires license for LLM calls
  if (prompt) {
    if (!hasLicense) {
      error("License required. Run: eversale activate <token>");
      process.exit(1);
    }
    await runAgenticBrowser(prompt);
    return;
  }

  // Fallback
  runAgent(args);
}

main().catch(err => {
  error(err.message);
  process.exit(1);
});
