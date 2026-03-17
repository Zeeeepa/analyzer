"""
Config Validator - Validate configuration with helpful error messages

Features:
- Validate all config files on startup
- Check for common misconfigurations
- Provide helpful fix suggestions
- Validate environment variables
- Check external dependencies (Ollama, Playwright)
"""

import asyncio
import os
import sys
import yaml
import httpx
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from loguru import logger

# Import config loader utilities (or set defaults if module import fails)
try:
    from .config_loader import CONFIG_PATH, PROJECT_ROOT, LOCAL_MARKER, is_local_mode
except ImportError:
    # Fallback for standalone usage
    PROJECT_ROOT = Path(__file__).parent.parent
    CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"
    LOCAL_MARKER = PROJECT_ROOT / ".eversale-local"

    def is_local_mode() -> bool:
        """Check if running in local mode (with Ollama)."""
        return LOCAL_MARKER.exists()


class ValidationType(Enum):
    """Types of validation checks."""
    CONFIG = "config"
    ENVIRONMENT = "environment"
    DEPENDENCY = "dependency"
    NETWORK = "network"
    PERMISSION = "permission"


class Severity(Enum):
    """Severity levels for validation issues."""
    ERROR = "error"      # Must be fixed before running
    WARNING = "warning"  # Should be fixed but not blocking
    INFO = "info"        # Nice to have


@dataclass
class ValidationIssue:
    """Represents a validation issue."""
    type: ValidationType
    severity: Severity
    message: str
    fix_command: Optional[str] = None
    fix_description: Optional[str] = None
    auto_fixable: bool = False


@dataclass
class ValidationReport:
    """Validation report with all checks."""
    passed: List[str] = field(default_factory=list)
    issues: List[ValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> List[ValidationIssue]:
        """Get all error-level issues."""
        return [i for i in self.issues if i.severity == Severity.ERROR]

    @property
    def warnings(self) -> List[ValidationIssue]:
        """Get all warning-level issues."""
        return [i for i in self.issues if i.severity == Severity.WARNING]

    @property
    def infos(self) -> List[ValidationIssue]:
        """Get all info-level issues."""
        return [i for i in self.issues if i.severity == Severity.INFO]

    @property
    def has_errors(self) -> bool:
        """Check if there are any errors."""
        return len(self.errors) > 0

    @property
    def has_warnings(self) -> bool:
        """Check if there are any warnings."""
        return len(self.warnings) > 0

    def add_pass(self, check: str):
        """Add a passing check."""
        self.passed.append(check)

    def add_issue(self, issue: ValidationIssue):
        """Add a validation issue."""
        self.issues.append(issue)


class ConfigValidator:
    """Validates Eversale configuration."""

    def __init__(self):
        self.report = ValidationReport()

    async def validate_all(self, auto_fix: bool = False) -> ValidationReport:
        """
        Run all validation checks.

        Args:
            auto_fix: Attempt to automatically fix issues

        Returns:
            ValidationReport with results
        """
        logger.info("Running configuration validation...")

        # Run all validation checks
        self._validate_config_file()
        self._validate_environment()
        await self._validate_dependencies(auto_fix)
        await self._validate_network()
        self._validate_permissions()

        # Log summary
        self._log_summary()

        return self.report

    def _validate_config_file(self):
        """Validate config/config.yaml exists and is valid."""
        # Check if file exists
        if not CONFIG_PATH.exists():
            self.report.add_issue(ValidationIssue(
                type=ValidationType.CONFIG,
                severity=Severity.ERROR,
                message=f"Config file not found: {CONFIG_PATH}",
                fix_command="cp config/config.yaml.example config/config.yaml",
                fix_description="Create config file from example template",
                auto_fixable=False
            ))
            return

        # Check if file is valid YAML
        try:
            with open(CONFIG_PATH) as f:
                config = yaml.safe_load(f)

            if not isinstance(config, dict):
                self.report.add_issue(ValidationIssue(
                    type=ValidationType.CONFIG,
                    severity=Severity.ERROR,
                    message="Config file is not a valid YAML dictionary",
                    fix_description="Check config/config.yaml for syntax errors"
                ))
                return

            self.report.add_pass("Config file exists and is valid YAML")

            # Validate required sections
            self._validate_config_sections(config)

        except yaml.YAMLError as e:
            self.report.add_issue(ValidationIssue(
                type=ValidationType.CONFIG,
                severity=Severity.ERROR,
                message=f"Config file YAML syntax error: {e}",
                fix_description="Fix YAML syntax in config/config.yaml"
            ))
        except Exception as e:
            self.report.add_issue(ValidationIssue(
                type=ValidationType.CONFIG,
                severity=Severity.ERROR,
                message=f"Error reading config file: {e}",
                fix_description="Check file permissions on config/config.yaml"
            ))

    def _validate_config_sections(self, config: Dict[str, Any]):
        """Validate required config sections and values."""
        # Required sections
        required_sections = ['agent', 'llm', 'browser', 'timing', 'logging']

        for section in required_sections:
            if section not in config:
                self.report.add_issue(ValidationIssue(
                    type=ValidationType.CONFIG,
                    severity=Severity.ERROR,
                    message=f"Missing required config section: {section}",
                    fix_description=f"Add '{section}:' section to config/config.yaml"
                ))
            else:
                self.report.add_pass(f"Config section '{section}' exists")

        # Validate agent section
        if 'agent' in config:
            agent = config['agent']

            # Check timeout values
            if 'timeout_seconds' in agent:
                timeout = agent['timeout_seconds']
                if not isinstance(timeout, (int, float)) or timeout <= 0:
                    self.report.add_issue(ValidationIssue(
                        type=ValidationType.CONFIG,
                        severity=Severity.ERROR,
                        message=f"agent.timeout_seconds must be > 0, got: {timeout}",
                        fix_description="Set agent.timeout_seconds to a positive number"
                    ))

            if 'task_timeout_seconds' in agent:
                timeout = agent['task_timeout_seconds']
                if not isinstance(timeout, (int, float)) or timeout <= 0:
                    self.report.add_issue(ValidationIssue(
                        type=ValidationType.CONFIG,
                        severity=Severity.ERROR,
                        message=f"agent.task_timeout_seconds must be > 0, got: {timeout}",
                        fix_description="Set agent.task_timeout_seconds to a positive number"
                    ))

        # Validate LLM section
        if 'llm' in config:
            llm = config['llm']

            # Check for required LLM fields
            if 'base_url' not in llm:
                self.report.add_issue(ValidationIssue(
                    type=ValidationType.CONFIG,
                    severity=Severity.ERROR,
                    message="Missing llm.base_url in config",
                    fix_description="Add llm.base_url to config/config.yaml"
                ))

            if 'main_model' not in llm:
                self.report.add_issue(ValidationIssue(
                    type=ValidationType.CONFIG,
                    severity=Severity.WARNING,
                    message="Missing llm.main_model in config",
                    fix_description="Add llm.main_model to config/config.yaml"
                ))

            # Check temperature range
            if 'temperature' in llm:
                temp = llm['temperature']
                if not isinstance(temp, (int, float)) or not (0 <= temp <= 2):
                    self.report.add_issue(ValidationIssue(
                        type=ValidationType.CONFIG,
                        severity=Severity.WARNING,
                        message=f"llm.temperature should be 0-2, got: {temp}",
                        fix_description="Set llm.temperature between 0 and 2"
                    ))

        # Validate browser section
        if 'browser' in config:
            browser = config['browser']

            # Check timeout values
            for timeout_key in ['nav_timeout', 'operation_timeout']:
                if timeout_key in browser:
                    timeout = browser[timeout_key]
                    if not isinstance(timeout, (int, float)) or timeout <= 0:
                        self.report.add_issue(ValidationIssue(
                            type=ValidationType.CONFIG,
                            severity=Severity.ERROR,
                            message=f"browser.{timeout_key} must be > 0, got: {timeout}",
                            fix_description=f"Set browser.{timeout_key} to a positive number (milliseconds)"
                        ))

    def _validate_environment(self):
        """Validate environment variables."""
        # Check if .env file exists
        env_path = PROJECT_ROOT / ".env"
        if not env_path.exists():
            self.report.add_issue(ValidationIssue(
                type=ValidationType.ENVIRONMENT,
                severity=Severity.WARNING,
                message=".env file not found (using defaults)",
                fix_command="cp .env.example .env",
                fix_description="Create .env file from example template",
                auto_fixable=False
            ))
        else:
            self.report.add_pass(".env file exists")

        # Check for local mode marker
        if LOCAL_MARKER.exists():
            self.report.add_pass("Running in LOCAL mode (Ollama)")

            # In local mode, check OLLAMA_BASE_URL
            ollama_url = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
            if not ollama_url.startswith('http'):
                self.report.add_issue(ValidationIssue(
                    type=ValidationType.ENVIRONMENT,
                    severity=Severity.ERROR,
                    message=f"Invalid OLLAMA_BASE_URL: {ollama_url}",
                    fix_description="Set OLLAMA_BASE_URL to a valid URL (e.g., http://localhost:11434)"
                ))
        else:
            self.report.add_pass("Running in REMOTE mode (eversale.io)")

        # Check optional environment variables
        browser_profile = os.getenv('EVERSALE_BROWSER_PROFILE')
        if browser_profile:
            profile_path = Path(browser_profile)
            if not profile_path.exists():
                self.report.add_issue(ValidationIssue(
                    type=ValidationType.ENVIRONMENT,
                    severity=Severity.WARNING,
                    message=f"EVERSALE_BROWSER_PROFILE path does not exist: {browser_profile}",
                    fix_description="Remove EVERSALE_BROWSER_PROFILE or set to a valid browser profile directory"
                ))

        # Check output directory
        output_dir = os.getenv('EVERSALE_OUTPUT_DIR')
        if output_dir:
            output_path = Path(output_dir)
            if not output_path.exists():
                self.report.add_issue(ValidationIssue(
                    type=ValidationType.ENVIRONMENT,
                    severity=Severity.INFO,
                    message=f"EVERSALE_OUTPUT_DIR does not exist: {output_dir}",
                    fix_command=f"mkdir -p {output_dir}",
                    fix_description="Create output directory",
                    auto_fixable=True
                ))

    async def _validate_dependencies(self, auto_fix: bool = False):
        """Validate external dependencies."""
        # Check Python packages
        await self._check_python_packages()

        # Check Ollama (if in local mode)
        if is_local_mode():
            await self._check_ollama(auto_fix)

        # Check Playwright browsers
        await self._check_playwright(auto_fix)

    async def _check_python_packages(self):
        """Check if required Python packages are importable."""
        required_packages = [
            ('yaml', 'pyyaml'),
            ('httpx', 'httpx'),
            ('playwright', 'playwright'),
            ('loguru', 'loguru'),
            ('dotenv', 'python-dotenv'),
            ('rich', 'rich'),
            ('psutil', 'psutil'),
        ]

        for import_name, package_name in required_packages:
            try:
                __import__(import_name)
                self.report.add_pass(f"Python package '{package_name}' is available")
            except ImportError:
                self.report.add_issue(ValidationIssue(
                    type=ValidationType.DEPENDENCY,
                    severity=Severity.ERROR,
                    message=f"Required Python package '{package_name}' not found",
                    fix_command=f"pip install {package_name}",
                    fix_description=f"Install {package_name}",
                    auto_fixable=True
                ))

        # Check optional packages
        optional_packages = [
            ('patchright', 'patchright'),
            ('curl_cffi', 'curl_cffi'),
            ('scipy', 'scipy'),
            ('numpy', 'numpy'),
        ]

        for import_name, package_name in optional_packages:
            try:
                __import__(import_name)
                self.report.add_pass(f"Optional package '{package_name}' is available")
            except ImportError:
                self.report.add_issue(ValidationIssue(
                    type=ValidationType.DEPENDENCY,
                    severity=Severity.INFO,
                    message=f"Optional package '{package_name}' not found (enhanced features disabled)",
                    fix_command=f"pip install {package_name}",
                    fix_description=f"Install {package_name} for enhanced features",
                    auto_fixable=True
                ))

    async def _check_ollama(self, auto_fix: bool = False):
        """Check if Ollama is running and has required models."""
        # Check if ollama command exists
        try:
            result = subprocess.run(
                ['which', 'ollama'],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode != 0:
                self.report.add_issue(ValidationIssue(
                    type=ValidationType.DEPENDENCY,
                    severity=Severity.ERROR,
                    message="Ollama not installed",
                    fix_command="curl -fsSL https://ollama.com/install.sh | sh",
                    fix_description="Install Ollama from https://ollama.com",
                    auto_fixable=False
                ))
                return

            self.report.add_pass("Ollama is installed")

        except Exception as e:
            self.report.add_issue(ValidationIssue(
                type=ValidationType.DEPENDENCY,
                severity=Severity.ERROR,
                message=f"Error checking Ollama installation: {e}",
                fix_description="Ensure Ollama is installed and in PATH"
            ))
            return

        # Check if Ollama is running
        ollama_url = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{ollama_url}/api/tags", timeout=5.0)

                if response.status_code == 200:
                    self.report.add_pass("Ollama is running and accessible")

                    # Check for required models
                    models_data = response.json()
                    available_models = [m['name'] for m in models_data.get('models', [])]

                    # Load config to get required models
                    try:
                        with open(CONFIG_PATH) as f:
                            config = yaml.safe_load(f) or {}

                        required_models = []
                        llm_config = config.get('llm', {})

                        if 'main_model' in llm_config:
                            required_models.append(llm_config['main_model'])
                        if 'fast_model' in llm_config:
                            required_models.append(llm_config['fast_model'])
                        if 'vision_model' in llm_config:
                            required_models.append(llm_config['vision_model'])

                        # Check each required model
                        for model in required_models:
                            if model and model not in available_models:
                                if auto_fix:
                                    logger.info(f"Auto-fixing: Pulling model {model}...")
                                    try:
                                        subprocess.run(
                                            ['ollama', 'pull', model],
                                            check=True,
                                            timeout=300  # 5 minutes
                                        )
                                        self.report.add_pass(f"Auto-fixed: Pulled model '{model}'")
                                    except Exception as e:
                                        self.report.add_issue(ValidationIssue(
                                            type=ValidationType.DEPENDENCY,
                                            severity=Severity.ERROR,
                                            message=f"Failed to pull model '{model}': {e}",
                                            fix_command=f"ollama pull {model}",
                                            fix_description=f"Pull required model",
                                            auto_fixable=True
                                        ))
                                else:
                                    self.report.add_issue(ValidationIssue(
                                        type=ValidationType.DEPENDENCY,
                                        severity=Severity.ERROR,
                                        message=f"Required model '{model}' not found in Ollama",
                                        fix_command=f"ollama pull {model}",
                                        fix_description=f"Pull required model",
                                        auto_fixable=True
                                    ))
                            elif model:
                                self.report.add_pass(f"Model '{model}' is available")

                    except Exception as e:
                        logger.warning(f"Could not check required models: {e}")

                else:
                    self.report.add_issue(ValidationIssue(
                        type=ValidationType.DEPENDENCY,
                        severity=Severity.ERROR,
                        message=f"Ollama returned error: HTTP {response.status_code}",
                        fix_description="Check Ollama service status"
                    ))

        except httpx.ConnectError:
            self.report.add_issue(ValidationIssue(
                type=ValidationType.DEPENDENCY,
                severity=Severity.ERROR,
                message=f"Ollama not running at {ollama_url}",
                fix_command="ollama serve",
                fix_description="Start Ollama service",
                auto_fixable=False
            ))
        except httpx.TimeoutException:
            self.report.add_issue(ValidationIssue(
                type=ValidationType.DEPENDENCY,
                severity=Severity.ERROR,
                message=f"Ollama connection timeout at {ollama_url}",
                fix_description="Check if Ollama is running and network is accessible"
            ))
        except Exception as e:
            self.report.add_issue(ValidationIssue(
                type=ValidationType.DEPENDENCY,
                severity=Severity.ERROR,
                message=f"Error connecting to Ollama: {e}",
                fix_description="Check Ollama installation and service status"
            ))

    async def _check_playwright(self, auto_fix: bool = False):
        """Check if Playwright browsers are installed."""
        # Try to find python command
        python_cmd = 'python3' if subprocess.run(['which', 'python3'], capture_output=True).returncode == 0 else 'python'

        try:
            # Check if playwright command exists
            result = subprocess.run(
                [python_cmd, '-m', 'playwright', '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode != 0:
                self.report.add_issue(ValidationIssue(
                    type=ValidationType.DEPENDENCY,
                    severity=Severity.ERROR,
                    message="Playwright CLI not available",
                    fix_command="pip install playwright",
                    fix_description="Install Playwright",
                    auto_fixable=True
                ))
                return

            self.report.add_pass("Playwright CLI is available")

        except Exception as e:
            self.report.add_issue(ValidationIssue(
                type=ValidationType.DEPENDENCY,
                severity=Severity.ERROR,
                message=f"Error checking Playwright: {e}",
                fix_description="Ensure Playwright is installed"
            ))
            return

        # Check if browsers are installed using playwright install --dry-run
        try:
            # Use subprocess to check browser installation (avoids async issues)
            result = subprocess.run(
                [python_cmd, '-m', 'playwright', 'install', '--dry-run', 'chromium'],
                capture_output=True,
                text=True,
                timeout=10
            )

            # Check if output indicates browsers are already installed
            if result.returncode == 0:
                output = result.stdout + result.stderr
                if 'already installed' in output.lower() or 'up to date' in output.lower():
                    self.report.add_pass("Playwright Chromium browser is installed")
                elif 'would download' in output.lower() or 'missing' in output.lower():
                    # Browser not installed
                    if auto_fix:
                        logger.info("Auto-fixing: Installing Playwright browsers...")
                        try:
                            subprocess.run(
                                [python_cmd, '-m', 'playwright', 'install', 'chromium'],
                                check=True,
                                timeout=300
                            )
                            self.report.add_pass("Auto-fixed: Installed Playwright Chromium")
                        except Exception as e:
                            self.report.add_issue(ValidationIssue(
                                type=ValidationType.DEPENDENCY,
                                severity=Severity.ERROR,
                                message=f"Failed to install Playwright browsers: {e}",
                                fix_command=f"{python_cmd} -m playwright install chromium",
                                fix_description="Install Playwright browsers",
                                auto_fixable=True
                            ))
                    else:
                        self.report.add_issue(ValidationIssue(
                            type=ValidationType.DEPENDENCY,
                            severity=Severity.ERROR,
                            message="Playwright browsers not installed",
                            fix_command=f"{python_cmd} -m playwright install",
                            fix_description="Install Playwright browsers",
                            auto_fixable=True
                        ))
                else:
                    # Assume installed if we can't determine
                    self.report.add_pass("Playwright appears to be configured")
            else:
                self.report.add_issue(ValidationIssue(
                    type=ValidationType.DEPENDENCY,
                    severity=Severity.WARNING,
                    message=f"Could not verify Playwright browser installation: {result.stderr[:100]}",
                    fix_command=f"{python_cmd} -m playwright install",
                    fix_description="Install Playwright browsers to be safe"
                ))

        except FileNotFoundError:
            self.report.add_issue(ValidationIssue(
                type=ValidationType.DEPENDENCY,
                severity=Severity.ERROR,
                message="Playwright package not installed",
                fix_command=f"pip install playwright && {python_cmd} -m playwright install",
                fix_description="Install Playwright and browsers",
                auto_fixable=True
            ))
        except Exception as e:
            self.report.add_issue(ValidationIssue(
                type=ValidationType.DEPENDENCY,
                severity=Severity.WARNING,
                message=f"Error checking Playwright browsers: {e}",
                fix_command=f"{python_cmd} -m playwright install",
                fix_description="Install Playwright browsers",
                auto_fixable=True
            ))

    async def _validate_network(self):
        """Validate network connectivity."""
        # Check if we can reach the LLM endpoint
        if is_local_mode():
            # Test Ollama connection
            ollama_url = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
            await self._test_url(ollama_url, "Ollama endpoint")
        else:
            # Test remote endpoint
            await self._test_url("https://eversale.io/api/llm", "Remote LLM endpoint")

        # Test general internet connectivity
        await self._test_url("https://www.google.com", "Internet connectivity")

    async def _test_url(self, url: str, description: str):
        """Test if a URL is reachable."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=10.0, follow_redirects=True)

                if response.status_code < 500:
                    self.report.add_pass(f"{description} is reachable")
                else:
                    self.report.add_issue(ValidationIssue(
                        type=ValidationType.NETWORK,
                        severity=Severity.WARNING,
                        message=f"{description} returned error: HTTP {response.status_code}",
                        fix_description=f"Check service status for {url}"
                    ))

        except httpx.ConnectError:
            self.report.add_issue(ValidationIssue(
                type=ValidationType.NETWORK,
                severity=Severity.ERROR,
                message=f"Cannot connect to {description} at {url}",
                fix_description=f"Check network connection and service availability"
            ))
        except httpx.TimeoutException:
            self.report.add_issue(ValidationIssue(
                type=ValidationType.NETWORK,
                severity=Severity.WARNING,
                message=f"{description} connection timeout at {url}",
                fix_description="Check network connectivity"
            ))
        except Exception as e:
            self.report.add_issue(ValidationIssue(
                type=ValidationType.NETWORK,
                severity=Severity.WARNING,
                message=f"Error testing {description}: {e}",
                fix_description=f"Check network settings and {url} availability"
            ))

    def _validate_permissions(self):
        """Validate file and directory permissions."""
        # Check if we can write to output directory
        output_dir = os.getenv('EVERSALE_OUTPUT_DIR', str(Path.home() / 'Desktop' / 'AI_Agent_Output'))
        output_path = Path(output_dir)

        try:
            output_path.mkdir(parents=True, exist_ok=True)

            # Try to write a test file
            test_file = output_path / '.eversale_test'
            test_file.write_text('test')
            test_file.unlink()

            self.report.add_pass(f"Output directory is writable: {output_dir}")

        except PermissionError:
            self.report.add_issue(ValidationIssue(
                type=ValidationType.PERMISSION,
                severity=Severity.ERROR,
                message=f"No write permission for output directory: {output_dir}",
                fix_command=f"chmod +w {output_dir}",
                fix_description="Grant write permissions to output directory",
                auto_fixable=False
            ))
        except Exception as e:
            self.report.add_issue(ValidationIssue(
                type=ValidationType.PERMISSION,
                severity=Severity.WARNING,
                message=f"Error checking output directory permissions: {e}",
                fix_description=f"Check permissions for {output_dir}"
            ))

        # Check if config directory is writable (for potential updates)
        config_dir = CONFIG_PATH.parent

        try:
            if not config_dir.exists():
                self.report.add_issue(ValidationIssue(
                    type=ValidationType.PERMISSION,
                    severity=Severity.ERROR,
                    message=f"Config directory does not exist: {config_dir}",
                    fix_command=f"mkdir -p {config_dir}",
                    fix_description="Create config directory",
                    auto_fixable=True
                ))
            elif not os.access(config_dir, os.W_OK):
                self.report.add_issue(ValidationIssue(
                    type=ValidationType.PERMISSION,
                    severity=Severity.WARNING,
                    message=f"Config directory is not writable: {config_dir}",
                    fix_description="This may prevent config updates"
                ))
            else:
                self.report.add_pass("Config directory is writable")

        except Exception as e:
            logger.warning(f"Error checking config directory permissions: {e}")

    def _log_summary(self):
        """Log validation summary."""
        logger.info("=" * 60)
        logger.info("CONFIGURATION VALIDATION SUMMARY")
        logger.info("=" * 60)

        # Log passed checks
        if self.report.passed:
            logger.success(f"✓ {len(self.report.passed)} checks passed")

        # Log errors
        if self.report.errors:
            logger.error(f"✗ {len(self.report.errors)} errors found (MUST FIX)")
            for issue in self.report.errors:
                logger.error(f"  • {issue.message}")
                if issue.fix_command:
                    logger.error(f"    Fix: {issue.fix_command}")
                elif issue.fix_description:
                    logger.error(f"    Fix: {issue.fix_description}")

        # Log warnings
        if self.report.warnings:
            logger.warning(f"⚠ {len(self.report.warnings)} warnings (SHOULD FIX)")
            for issue in self.report.warnings:
                logger.warning(f"  • {issue.message}")
                if issue.fix_command:
                    logger.warning(f"    Fix: {issue.fix_command}")
                elif issue.fix_description:
                    logger.warning(f"    Fix: {issue.fix_description}")

        # Log info
        if self.report.infos:
            logger.info(f"ℹ {len(self.report.infos)} info items (OPTIONAL)")
            for issue in self.report.infos:
                logger.info(f"  • {issue.message}")
                if issue.fix_command:
                    logger.info(f"    Fix: {issue.fix_command}")

        logger.info("=" * 60)

        # Exit if there are errors
        if self.report.has_errors:
            logger.error("Cannot start Eversale due to configuration errors. Fix the issues above and try again.")
            return False

        if self.report.has_warnings:
            logger.warning("Eversale can start but some features may not work correctly.")

        if not self.report.errors and not self.report.warnings:
            logger.success("All validation checks passed! ✨")

        return True


async def validate_config(auto_fix: bool = False, exit_on_error: bool = True) -> Tuple[bool, ValidationReport]:
    """
    Validate configuration and optionally auto-fix issues.

    Args:
        auto_fix: Attempt to automatically fix issues
        exit_on_error: Exit if there are errors

    Returns:
        Tuple of (success, ValidationReport)
    """
    validator = ConfigValidator()
    report = await validator.validate_all(auto_fix=auto_fix)

    success = not report.has_errors

    if not success and exit_on_error:
        sys.exit(1)

    return success, report


async def quick_validate() -> bool:
    """
    Quick validation for startup - only checks critical issues.
    Non-blocking, returns True if can proceed, False if critical errors.

    This is designed to be called at agent startup for fast validation.
    """
    report = ValidationReport()

    # Check 1: Config file exists
    if not CONFIG_PATH.exists():
        logger.error(f"Config file not found: {CONFIG_PATH}")
        logger.error("Fix: Create config/config.yaml from template")
        return False

    # Check 2: Config file is valid YAML
    try:
        with open(CONFIG_PATH) as f:
            config = yaml.safe_load(f)
        if not isinstance(config, dict):
            logger.error("Config file is not a valid YAML dictionary")
            return False
    except Exception as e:
        logger.error(f"Config file error: {e}")
        return False

    # Check 3: In local mode, check if Ollama is accessible
    if is_local_mode():
        ollama_url = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{ollama_url}/api/tags", timeout=2.0)
                if response.status_code != 200:
                    logger.warning(f"Ollama may not be running at {ollama_url}")
                    logger.warning("Starting anyway - will fail if models are needed")
        except Exception:
            logger.warning(f"Cannot reach Ollama at {ollama_url}")
            logger.warning("Fix: Start Ollama with 'ollama serve'")
            # Don't fail - maybe not needed for this task

    logger.success("Quick validation passed ✓")
    return True


def validate_on_startup(skip: bool = False):
    """
    Synchronous wrapper for startup validation.
    Call this at the beginning of brain initialization.

    Args:
        skip: Skip validation (for testing/debugging)

    Returns:
        True if validation passed or skipped, False if critical errors
    """
    if skip or os.getenv('EVERSALE_SKIP_VALIDATION', '').lower() in ('1', 'true', 'yes'):
        logger.info("Skipping startup validation (EVERSALE_SKIP_VALIDATION=true)")
        return True

    logger.info("Running startup validation...")

    try:
        # Run quick validation
        success = asyncio.run(quick_validate())
        return success
    except Exception as e:
        logger.error(f"Validation error: {e}")
        logger.warning("Proceeding anyway - this may cause issues")
        return True  # Don't block startup on validation errors


async def main():
    """CLI entry point for config validation."""
    import argparse

    parser = argparse.ArgumentParser(description="Validate Eversale configuration")
    parser.add_argument('--auto-fix', action='store_true', help="Attempt to automatically fix issues")
    parser.add_argument('--no-exit', action='store_true', help="Don't exit on errors")
    parser.add_argument('--quick', action='store_true', help="Run quick validation only")
    args = parser.parse_args()

    if args.quick:
        success = await quick_validate()
        return 0 if success else 1

    success, report = await validate_config(
        auto_fix=args.auto_fix,
        exit_on_error=not args.no_exit
    )

    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
