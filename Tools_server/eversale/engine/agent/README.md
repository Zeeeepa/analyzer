# Browser Automation Engine Architecture

## Core Mandate: Domain Agnosticism
The core engine (`agentic_browser.py`, `recovery_engine.py`) must remain **domain-agnostic**. Branching logic based on site names (e.g., `if "facebook" in url`) is strictly prohibited in the engine's control flow.

### Rules for Developers:
1. **Engine is Code, Websites are Data:** All platform-specific knowledge (keywords, base URLs, selectors) must live in `platform_data.py` or `failure_modes.py` (SiteHints).
2. **Template Purity:** Workflows (`workflow_*`) must use engine wrappers (`self.click()`, `self.type()`) instead of raw Playwright `page` calls to ensure auto-recovery remains active.
3. **Regex Purity:** Always use raw strings (`r"..."`) for regex to prevent syntax warnings.

## Enforcement (CI Jobs)
These rules are automatically enforced by the following jobs in `.github/workflows/ci-browser.yml`:
*   **Architecture & Parity (Fast):** Runs AST-based checks for domain branching and template purity.
*   **Real DOM Parity (Smoke):** Verifies specialized extractors against golden HTML fixtures using real Playwright.
