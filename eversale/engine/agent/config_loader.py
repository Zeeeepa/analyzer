"""
Config Loader - CLI Version (Remote GPU Server)
"""

import os
import asyncio
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, TypeVar, Callable
from functools import lru_cache, wraps
from loguru import logger

T = TypeVar('T')

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"
BROWSER_OPT_CONFIG_PATH = Path(__file__).parent / "config" / "browser_optimizations.yaml"
LOCAL_MARKER = PROJECT_ROOT / ".eversale-local"

# Model name mapping: remote -> local Ollama
# Maps GPU server model names to local Ollama model names
LOCAL_MODEL_MAPPING = {
    "qwen3:8b": "qwen3:8b",
    "moondream:latest": "moondream:latest",
    "glm-5": "glm-5",
    "0000/ui-tars-1.5-7b:latest": "glm-5",
}


def is_local_mode() -> bool:
    """Check if running in local development mode (with Ollama).

    CLI users ALWAYS use remote mode (licensed API via eversale.io).
    Local mode only available when .eversale-local marker file exists.
    """
    return LOCAL_MARKER.exists()


def is_cli_mode() -> bool:
    """Check if running as CLI user (not development).

    CLI users must use remote API - they don't have local Ollama.
    """
    return not LOCAL_MARKER.exists()


@lru_cache(maxsize=1)
def load_config() -> Dict[str, Any]:
    """Load configuration from YAML file."""
    try:
        with open(CONFIG_PATH) as f:
            config = yaml.safe_load(f) or {}
    except FileNotFoundError:
        config = {}
    except yaml.YAMLError:
        config = {}

    # Default behavior:
    # - Development: allow local Ollama via `.eversale-local`
    # - CLI: default to remote via eversale.io
    #
    # Advanced override (for self-hosting / custom GPU backends):
    # - `EVERSALE_LLM_URL` env var always wins
    # - or set `llm.allow_custom_endpoint: true` + `llm.base_url: ...` in config
    config.setdefault('llm', {})

    if is_local_mode():
        # Development mode - allow local Ollama, but respect env var overrides
        config['llm']['mode'] = 'local'
        
        # Check for env var override — prioritize OPENAI_BASE_URL for personal API key usage
        env_url = (os.environ.get('OPENAI_BASE_URL') or os.environ.get('ANTHROPIC_BASE_URL') or os.environ.get('EVERSALE_LLM_URL') or '').strip()
        if env_url:
            config['llm']['base_url'] = env_url
            # Also set mode to remote if using a remote URL
            if 'localhost' not in env_url and '127.0.0.1' not in env_url:
                config['llm']['mode'] = 'remote'
        else:
            config['llm']['base_url'] = 'http://localhost:11434'

        # Propagate OPENAI_MODEL / OPENAI_MODEL_VISION env vars into config
        # so brain_config.py picks up the correct model names for remote APIs
        _env_model = os.environ.get('OPENAI_MODEL', '').strip()
        _env_vision = os.environ.get('OPENAI_MODEL_VISION', '').strip()
        if _env_model:
            config['llm']['main_model'] = _env_model
            config['llm']['fast_model'] = _env_model
            config['llm']['tool_calling_model'] = _env_model
        if _env_vision:
            config['llm']['vision_model'] = _env_vision
            config['llm']['web_vision_model'] = _env_vision

        # Map remote model names to local Ollama model names (only when NOT overridden)
        if not _env_model:
            llm_config = config.get('llm', {})
            model_keys = ['main_model', 'fast_model', 'tool_calling_model', 'vision_model', 'web_vision_model']
            for key in model_keys:
                if key in llm_config:
                    remote_model = llm_config[key]
                    local_model = LOCAL_MODEL_MAPPING.get(remote_model, remote_model)
                    llm_config[key] = local_model
    else:
        # CLI mode - remote by default
        config['llm']['mode'] = 'remote'

        # Priority for LLM URL:
        # 1. EVERSALE_LLM_URL env var (highest)
        # 2. remote_url from config.yaml (for direct GPU access)
        # 3. base_url from config.yaml (if allow_custom_endpoint)
        # 4. Default eversale.io proxy
        env_url = (os.environ.get('OPENAI_BASE_URL') or os.environ.get('ANTHROPIC_BASE_URL') or os.environ.get('EVERSALE_LLM_URL') or '').strip()
        remote_url = config['llm'].get('remote_url', '').strip()

        if env_url:
            config['llm']['base_url'] = env_url
        elif remote_url:
            # Use remote_url from config.yaml (direct GPU endpoint)
            config['llm']['base_url'] = remote_url
        elif config['llm'].get('allow_custom_endpoint') and config['llm'].get('base_url'):
            # Keep user-supplied base_url
            pass
        else:
            # Default to eversale.io proxy
            config['llm']['base_url'] = os.environ.get('OPENAI_BASE_URL', os.environ.get('ANTHROPIC_BASE_URL', 'https://api.z.ai/api/coding/paas/v4'))

        # Propagate OPENAI_MODEL / OPENAI_MODEL_VISION env vars into config
        # so brain_config.py picks up the correct model names for remote APIs
        _env_model = os.environ.get('OPENAI_MODEL', '').strip()
        _env_vision = os.environ.get('OPENAI_MODEL_VISION', '').strip()
        if _env_model:
            config['llm']['main_model'] = _env_model
            config['llm']['fast_model'] = _env_model
            config['llm']['tool_calling_model'] = _env_model
        if _env_vision:
            config['llm']['vision_model'] = _env_vision
            config['llm']['web_vision_model'] = _env_vision

    return config


def get_timing(key: str, service: Optional[str] = None, default: float = 1.0) -> float:
    config = load_config()
    if service:
        service_timing = config.get('service_timing', {}).get(service.lower(), {})
        if key in service_timing:
            return float(service_timing[key])
    timing = config.get('timing', {})
    return float(timing.get(key, default))


def get_browser_setting(key: str, default: Any = None) -> Any:
    return load_config().get('browser', {}).get(key, default)


def get_llm_setting(key: str, default: Any = None) -> Any:
    return load_config().get('llm', {}).get(key, default)


def get_agent_setting(key: str, default: Any = None) -> Any:
    return load_config().get('agent', {}).get(key, default)


def get_validator_setting(key: str, default: Any = None) -> Any:
    return load_config().get('validator', {}).get(key, default)


def get_hallucination_guard_setting(key: str, default: Any = None) -> Any:
    return load_config().get('hallucination_guard', {}).get(key, default)


@lru_cache(maxsize=1)
def load_browser_optimizations() -> Dict[str, Any]:
    """Load browser optimization configuration from YAML file.

    Supports environment variable overrides:
    - EVERSALE_SNAPSHOT_FIRST=false - Disable snapshot-first
    - EVERSALE_TOKEN_BUDGET=4000 - Lower token budget
    - EVERSALE_CDP_PORT=9333 - Different CDP port
    - EVERSALE_OPTIMIZATION_ENABLED=false - Disable all optimizations
    """
    try:
        with open(BROWSER_OPT_CONFIG_PATH) as f:
            config = yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.warning(f"Browser optimization config not found at {BROWSER_OPT_CONFIG_PATH}, using defaults")
        config = {}
    except yaml.YAMLError as e:
        logger.error(f"Failed to parse browser optimization config: {e}")
        config = {}

    # Apply environment variable overrides
    optimization = config.setdefault('optimization', {})

    # Master switch
    if os.environ.get('EVERSALE_OPTIMIZATION_ENABLED'):
        optimization['enabled'] = os.environ.get('EVERSALE_OPTIMIZATION_ENABLED').lower() in ('true', '1', 'yes')

    # Snapshot-first overrides
    if os.environ.get('EVERSALE_SNAPSHOT_FIRST'):
        snapshot_first = optimization.setdefault('snapshot_first', {})
        snapshot_first['enabled'] = os.environ.get('EVERSALE_SNAPSHOT_FIRST').lower() in ('true', '1', 'yes')

    # Token budget override
    if os.environ.get('EVERSALE_TOKEN_BUDGET'):
        token_optimizer = optimization.setdefault('token_optimizer', {})
        try:
            token_optimizer['token_budget'] = int(os.environ.get('EVERSALE_TOKEN_BUDGET'))
        except ValueError:
            logger.warning(f"Invalid EVERSALE_TOKEN_BUDGET value: {os.environ.get('EVERSALE_TOKEN_BUDGET')}")

    # CDP port override
    if os.environ.get('EVERSALE_CDP_PORT'):
        cdp = optimization.setdefault('cdp', {})
        try:
            cdp['default_port'] = int(os.environ.get('EVERSALE_CDP_PORT'))
        except ValueError:
            logger.warning(f"Invalid EVERSALE_CDP_PORT value: {os.environ.get('EVERSALE_CDP_PORT')}")

    # DevTools override
    if os.environ.get('EVERSALE_DEVTOOLS_ENABLED'):
        devtools = optimization.setdefault('devtools', {})
        devtools['enabled'] = os.environ.get('EVERSALE_DEVTOOLS_ENABLED').lower() in ('true', '1', 'yes')

    return config


def get_optimization_setting(key: str, default: Any = None) -> Any:
    """Get browser optimization setting by key path.

    Examples:
        get_optimization_setting('optimization.enabled')
        get_optimization_setting('optimization.snapshot_first.enabled')
        get_optimization_setting('optimization.token_optimizer.token_budget')
    """
    config = load_browser_optimizations()
    keys = key.split('.')
    value = config
    for k in keys:
        if isinstance(value, dict):
            value = value.get(k, default)
        else:
            return default
    return value if value is not None else default


def is_optimization_enabled() -> bool:
    """Check if browser optimizations are enabled globally."""
    return get_optimization_setting('optimization.enabled', True)


def is_snapshot_first_enabled() -> bool:
    """Check if snapshot-first mode is enabled."""
    if not is_optimization_enabled():
        return False
    return get_optimization_setting('optimization.snapshot_first.enabled', True)


def is_token_optimizer_enabled() -> bool:
    """Check if token optimizer is enabled."""
    if not is_optimization_enabled():
        return False
    return get_optimization_setting('optimization.token_optimizer.enabled', True)


def is_devtools_enabled() -> bool:
    """Check if DevTools hooks are enabled."""
    if not is_optimization_enabled():
        return False
    return get_optimization_setting('optimization.devtools.enabled', True)


def is_cdp_enabled() -> bool:
    """Check if CDP/session reuse is enabled."""
    if not is_optimization_enabled():
        return False
    return get_optimization_setting('optimization.cdp.auto_detect', True)


def get_token_budget() -> int:
    """Get token budget for snapshot optimization."""
    return get_optimization_setting('optimization.token_optimizer.token_budget', 8000)


def get_cdp_port() -> int:
    """Get CDP port for Chrome connection."""
    return get_optimization_setting('optimization.cdp.default_port', 9222)


def matches_trigger(user_input: str, trigger_category: str) -> bool:
    """Check if user input matches a natural language trigger.

    Uses fuzzy matching - all words from trigger must appear in user input.

    Args:
        user_input: User's input text
        trigger_category: Category from triggers section (use_cdp, extract_links, etc.)

    Returns:
        True if input matches any trigger in the category
    """
    config = load_browser_optimizations()
    triggers = config.get('triggers', {}).get(trigger_category, [])
    user_input_lower = user_input.lower()

    for trigger in triggers:
        trigger_lower = trigger.lower()
        # First try exact substring match
        if trigger_lower in user_input_lower:
            return True
        # Then try fuzzy match - all words from trigger must appear
        trigger_words = trigger_lower.split()
        if all(word in user_input_lower for word in trigger_words):
            return True

    return False


def reload_config():
    load_config.cache_clear()
    load_browser_optimizations.cache_clear()


def is_fast_mode() -> bool:
    return get_browser_setting('fast_mode', True)


def is_headless() -> bool:
    return get_browser_setting('headless_default', True)


def get_login_required_sites() -> list:
    return get_browser_setting('login_required_sites', [])


class Timing:
    @staticmethod
    def loop_delay() -> float:
        return get_timing('loop_delay', default=2.0)

    @staticmethod
    def nav_delay(service: Optional[str] = None) -> float:
        return get_timing('nav_delay', service=service, default=2.0)

    @staticmethod
    def click_delay(service: Optional[str] = None) -> float:
        return get_timing('click_delay', service=service, default=0.5)

    @staticmethod
    def content_load_delay(service: Optional[str] = None) -> float:
        return get_timing('content_load_delay', service=service, default=3.0)

    @staticmethod
    def dynamic_content_delay() -> float:
        return get_timing('dynamic_content_delay', default=1.0)

    @staticmethod
    def retry_delay() -> float:
        return get_timing('retry_delay', default=10.0)

    @staticmethod
    def typing_delay_range() -> tuple:
        config = load_config()
        timing = config.get('timing', {})
        return (timing.get('typing_delay_min', 50), timing.get('typing_delay_max', 150))


class Timeouts:
    @staticmethod
    def navigation() -> int:
        return get_browser_setting('nav_timeout', 20000)

    @staticmethod
    def operation() -> int:
        return get_browser_setting('operation_timeout', 60000)

    @staticmethod
    def screenshot() -> int:
        return get_browser_setting('screenshot_timeout', 10000)

    @staticmethod
    def idle() -> int:
        return get_browser_setting('idle_timeout', 3000)


async def with_timeout(coro, timeout_ms: int = None, default: Any = None, operation: str = "operation"):
    if timeout_ms is None:
        timeout_ms = Timeouts.operation()
    try:
        return await asyncio.wait_for(coro, timeout=timeout_ms / 1000)
    except asyncio.TimeoutError:
        return default
    except Exception:
        return default
