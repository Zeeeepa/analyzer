#!/usr/bin/env node
/**
 * Eversale CLI Postinstall
 *
 * Downloads the Rust binary and core library for the current platform.
 * Falls back to pure Python if Rust binaries are unavailable.
 */

const { execSync, spawnSync } = require("child_process");
const https = require("https");
const fs = require("fs");
const path = require("path");
const os = require("os");
const { createWriteStream, mkdirSync, existsSync, chmodSync } = fs;

// Paths
const EVERSALE_HOME = process.env.EVERSALE_HOME || path.join(os.homedir(), ".eversale");
const BIN_DIR = path.join(EVERSALE_HOME, "bin");
const ENGINE_DIR = path.join(EVERSALE_HOME, "engine");
const VENV_DIR = path.join(EVERSALE_HOME, "venv");

// GitHub release info
const GITHUB_REPO = "eversale/eversale-cli";
const RELEASE_URL = `https://github.com/${GITHUB_REPO}/releases/latest/download`;

// Colors
const GREEN = "\x1b[32m";
const YELLOW = "\x1b[33m";
const DIM = "\x1b[2m";
const RESET = "\x1b[0m";

function log(msg) { console.log(`${GREEN}[eversale]${RESET} ${msg}`); }
function warn(msg) { console.log(`${YELLOW}[eversale]${RESET} ${msg}`); }
function dim(msg) { console.log(`${DIM}${msg}${RESET}`); }

// Detect platform
function getPlatform() {
  const platform = os.platform();
  const arch = os.arch();

  let osName = "linux";
  if (platform === "darwin") osName = "darwin";
  else if (platform === "win32") osName = "windows";

  let archName = "x86_64";
  if (arch === "arm64") archName = "aarch64";
  else if (arch === "arm") archName = "armv7";

  return { os: osName, arch: archName };
}

// Download file
function downloadFile(url, dest) {
  return new Promise((resolve, reject) => {
    const file = createWriteStream(dest);

    const request = (url) => {
      https.get(url, { headers: { "User-Agent": "eversale-cli" } }, (response) => {
        // Handle redirects
        if (response.statusCode === 301 || response.statusCode === 302) {
          file.close();
          fs.unlinkSync(dest);
          request(response.headers.location);
          return;
        }

        if (response.statusCode !== 200) {
          file.close();
          fs.unlinkSync(dest);
          reject(new Error(`HTTP ${response.statusCode}`));
          return;
        }

        response.pipe(file);
        file.on("finish", () => {
          file.close();
          resolve();
        });
      }).on("error", (err) => {
        file.close();
        fs.unlinkSync(dest);
        reject(err);
      });
    };

    request(url);
  });
}

// Extract tarball
function extractTar(tarPath, destDir) {
  try {
    execSync(`tar -xzf "${tarPath}" -C "${destDir}"`, { stdio: "pipe" });
    return true;
  } catch (e) {
    return false;
  }
}

// Download Rust binary
async function downloadRustBinary() {
  const { os: osName, arch } = getPlatform();
  const binaryName = osName === "windows" ? "eversale.exe" : "eversale";
  const tarballUrl = `${RELEASE_URL}/eversale-${osName}-${arch}.tar.gz`;

  log("Downloading Rust binary...");
  dim(`URL: ${tarballUrl}`);

  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "eversale-"));
  const tarPath = path.join(tempDir, "eversale.tar.gz");

  try {
    await downloadFile(tarballUrl, tarPath);

    if (!extractTar(tarPath, tempDir)) {
      throw new Error("Failed to extract tarball");
    }

    // Find and move binary
    const possiblePaths = [
      path.join(tempDir, "bin", binaryName),
      path.join(tempDir, binaryName),
      path.join(tempDir, `eversale-${osName}-${arch}`, binaryName),
    ];

    for (const srcPath of possiblePaths) {
      if (existsSync(srcPath)) {
        mkdirSync(BIN_DIR, { recursive: true });
        const destPath = path.join(BIN_DIR, binaryName);
        fs.copyFileSync(srcPath, destPath);
        if (osName !== "windows") {
          chmodSync(destPath, 0o755);
        }
        log(`Rust binary installed: ${destPath}`);
        return true;
      }
    }

    throw new Error("Binary not found in tarball");
  } catch (e) {
    dim(`Rust binary not available: ${e.message}`);
    return false;
  } finally {
    // Cleanup
    try {
      fs.rmSync(tempDir, { recursive: true, force: true });
    } catch (e) {}
  }
}

// Download Rust core library (Python wheel)
async function downloadRustCore() {
  const { os: osName, arch } = getPlatform();
  const wheelUrl = `${RELEASE_URL}/eversale_core-${osName}-${arch}.whl`;

  log("Downloading Rust acceleration library...");

  const tempWheel = path.join(os.tmpdir(), `eversale_core-${Date.now()}.whl`);

  try {
    await downloadFile(wheelUrl, tempWheel);

    // Try to install with pip
    const pipPath = path.join(VENV_DIR, process.platform === "win32" ? "Scripts/pip.exe" : "bin/pip");

    if (existsSync(pipPath)) {
      const result = spawnSync(pipPath, ["install", tempWheel], { stdio: "pipe" });
      if (result.status === 0) {
        log("Rust acceleration enabled");
        return true;
      }
    }

    // Try system pip
    const result = spawnSync("pip3", ["install", "--user", tempWheel], { stdio: "pipe" });
    if (result.status === 0) {
      log("Rust acceleration enabled (user install)");
      return true;
    }

    throw new Error("pip install failed");
  } catch (e) {
    dim(`Rust acceleration not available: ${e.message}`);
    dim("Python fallback will be used");
    return false;
  } finally {
    try {
      fs.unlinkSync(tempWheel);
    } catch (e) {}
  }
}

// Copy bundled engine
function copyBundledEngine() {
  const bundledEngine = path.join(__dirname, "..", "engine");

  if (!existsSync(bundledEngine)) {
    return false;
  }

  log("Installing Python engine...");
  mkdirSync(ENGINE_DIR, { recursive: true });

  try {
    if (process.platform === "win32") {
      execSync(`xcopy /E /I /Y "${bundledEngine}" "${ENGINE_DIR}"`, { stdio: "pipe" });
    } else {
      execSync(`cp -r "${bundledEngine}"/* "${ENGINE_DIR}/"`, { stdio: "pipe" });
    }
    log("Python engine installed");
    return true;
  } catch (e) {
    warn(`Failed to copy engine: ${e.message}`);
    return false;
  }
}

// Main
async function main() {
  console.log("");
  log("Eversale postinstall starting...");

  // Create directories
  mkdirSync(EVERSALE_HOME, { recursive: true });
  mkdirSync(BIN_DIR, { recursive: true });
  mkdirSync(ENGINE_DIR, { recursive: true });

  // Copy bundled Python engine
  copyBundledEngine();

  // Try to download Rust components (optional)
  const rustBinaryOk = await downloadRustBinary();
  const rustCoreOk = await downloadRustCore();

  // Summary
  console.log("");
  if (rustBinaryOk) {
    log("Rust supervisor: enabled");
  } else {
    dim("Rust supervisor: not available (using Node.js)");
  }

  if (rustCoreOk) {
    log("Rust acceleration: enabled");
  } else {
    dim("Rust acceleration: not available (using Python)");
  }

  console.log("");
  log("Postinstall complete!");
  console.log("");
}

main().catch(err => {
  warn(`Postinstall warning: ${err.message}`);
  dim("Eversale will work with Python-only mode");
  process.exit(0); // Don't fail npm install
});
