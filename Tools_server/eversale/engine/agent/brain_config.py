"""
Brain Configuration and Component Initialization

This module handles all configuration parsing, default values,
and component initialization for the EnhancedBrain agent.

Extracted from brain_enhanced_v2.py to improve modularity and reduce file size.
"""

import asyncio
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from loguru import logger

# Import required components
# Use GPU LLM client instead of local Ollama
# This routes to RunPod GPU server via eversale.io proxy
try:
    from .gpu_llm_client import OllamaCompatibleClient as OllamaClient
except ImportError:
    from ollama import Client as OllamaClient
from .awareness import AwarenessHub
from .context_memory import ContextMemory
from .dead_mans_switch import DeadMansSwitch
from .resource_limits import ResourceLimiter
from .multi_instance import MultiInstanceCoordinator
from .decision_logger import DecisionLogger
from .adaptive_explorer import AdaptiveExplorer
from .resource_economy import ResourceEconomy
from .resource_monitor import ResourceMonitor
from .survival import SurvivalManager
from .steering import SteeringInput
from .cache import Cache

# Optional deprecated modules (may be deleted in v2.9+)
try:
    from .crash_recovery import CrashRecovery
except ImportError:
    CrashRecovery = None
try:
    from .cascading_recovery import CascadingRecoverySystem
except ImportError:
    CascadingRecoverySystem = None
try:
    from .hallucination_guard import HallucinationGuard
except ImportError:
    HallucinationGuard = None
from .memory_architecture import MemoryArchitecture
from .session_state import SessionState


# ============================================================================
# Default Configuration Constants
# ============================================================================

# LLM Defaults - Dual model architecture:
# - qwen3:8b for text reasoning, tool calling, action execution (fast)
# - UI-TARS (0000/ui-tars-1.5-7b) for vision tasks, UI understanding
DEFAULT_LLM_BASE_URL = 'http://localhost:11434'
DEFAULT_MAIN_MODEL = 'qwen3:8b'
DEFAULT_VISION_MODEL = '0000/ui-tars-1.5-7b:latest'  # UI-TARS for vision
DEFAULT_FAST_MODEL = 'qwen3:8b'
DEFAULT_TEMPERATURE = 0.1
DEFAULT_MAX_ITERATIONS = 25  # Increased for multi-step tasks (checkout flows, forms)

# Dynamic LLM timeout - detect local vs remote mode
def _get_default_llm_timeout_ms():
    """Get timeout based on mode - humans wait longer for remote services."""
    local_marker = Path(__file__).parent.parent / ".eversale-local"
    is_local = local_marker.exists()
    return 30000 if is_local else 120000  # 30s local, 120s remote

DEFAULT_LLM_TIMEOUT_MS = _get_default_llm_timeout_ms()

# Agent Mode Defaults
DEFAULT_MODE = 'build'

# Vision Model Configuration
# UI-TARS is the ONLY vision model - designed specifically for UI understanding
# No fallbacks needed - UI-TARS handles all vision tasks
FAST_VISION_MODELS = [
    '0000/ui-tars-1.5-7b:latest',  # UI-TARS for all vision
]
DEFAULT_FAST_VISION_MODEL = '0000/ui-tars-1.5-7b:latest'

# Visual Targeting Models (for element location)
DEFAULT_TARGETING_MODEL = '0000/ui-tars-1.5-7b:latest'
TARGETING_MODELS = [
    '0000/ui-tars-1.5-7b:latest',  # UI-TARS for all targeting
]

# Agent Defaults
DEFAULT_TASK_TIMEOUT_SECONDS = 1800  # 30 minutes
DEFAULT_CHECKPOINT_INTERVAL_SECONDS = 1800  # 30 minutes
DEFAULT_STEERING_PAUSE_TIMEOUT_SECONDS = 300  # 5 minutes
DEFAULT_DEAD_MANS_TIMEOUT_HOURS = 4.0

# Resource Defaults
DEFAULT_CPU_THRESHOLD = 85
DEFAULT_MEM_THRESHOLD = 85
DEFAULT_GPU_THRESHOLD = 90
DEFAULT_MAX_MEMORY_MB = 4096

# Context Defaults - Increased for 100-300 step sequences
DEFAULT_MAX_CONTEXT_MESSAGES = 100
DEFAULT_COMPACT_THRESHOLD = 80

# Preflight Defaults
DEFAULT_MAX_PREFLIGHT_ATTEMPTS = 3
DEFAULT_PREFLIGHT_RETRY_DELAY = 2

# Improvement Defaults
DEFAULT_REVIEW_INTERVAL = 5
DEFAULT_REVIEW_HISTORY_LEN = 5

# Cache Defaults
DEFAULT_CACHE_DIR = ".cache/llm_responses"
DEFAULT_CACHE_MAX_ITEMS = 500

# MaxSteps Guard - Prevents runaway agentic loops
MAX_AGENTIC_STEPS = 50  # Maximum iterations in main agentic loop
MAX_TOOL_CALLS_PER_STEP = 10  # Maximum tool calls per iteration
FORCE_TEXT_AFTER_MAX = True  # Force text-only response when max steps reached
MAX_STEPS_WARNING_THRESHOLD = 0.8  # Warn at 80% of max steps


# ============================================================================
# Agent Mode Configuration
# ============================================================================

@dataclass
class AgentMode:
    """
    Agent mode configuration - controls tool permissions and behavior.

    Attributes:
        name: Mode identifier ('build', 'plan', 'review', 'debug', 'docs', 'safe')
        description: Human-readable description
        tool_permissions: Dict mapping tool categories to permission levels
            - write: Allow file write operations (Write tool)
            - edit: Allow file edit operations (Edit tool)
            - bash: Bash command permission ('allow', 'ask', 'deny')
            - browser: Browser automation permission
        allowed_paths: List of path patterns that are allowed for file operations
        allowed_commands: List of bash commands that are whitelisted (empty list = all allowed)
    """
    name: str
    description: str
    tool_permissions: Dict[str, Any]
    allowed_paths: List[str] = field(default_factory=list)
    allowed_commands: List[str] = field(default_factory=list)

    def is_tool_allowed(self, tool_name: str) -> bool:
        """
        Check if a tool is allowed to execute in this mode.

        Args:
            tool_name: Name of the tool to check

        Returns:
            True if tool is allowed, False otherwise
        """
        tool_lower = tool_name.lower()

        # Write permission check
        if 'write' in tool_lower and not self.tool_permissions.get('write', True):
            return False

        # Edit permission check
        if 'edit' in tool_lower and not self.tool_permissions.get('edit', True):
            return False

        # Bash permission check (deny if set to 'deny')
        if 'bash' in tool_lower and self.tool_permissions.get('bash') == 'deny':
            return False

        # Browser permission check
        if 'browser' in tool_lower and not self.tool_permissions.get('browser', True):
            return False

        return True

    def requires_permission(self, tool_name: str) -> bool:
        """
        Check if a tool requires user permission before execution.

        Args:
            tool_name: Name of the tool to check

        Returns:
            True if tool requires permission, False otherwise
        """
        tool_lower = tool_name.lower()

        # Bash requires permission if set to 'ask'
        if 'bash' in tool_lower and self.tool_permissions.get('bash') == 'ask':
            return True

        return False

    def is_path_allowed(self, path: str) -> bool:
        """
        Check if a file path is allowed for operations in this mode.

        Args:
            path: File path to check

        Returns:
            True if path is allowed, False otherwise
        """
        # Empty allowed_paths means all paths are allowed
        if not self.allowed_paths:
            return True

        # Convert path to absolute and normalize
        import os
        abs_path = os.path.abspath(path)

        # Check against allowed patterns
        for pattern in self.allowed_paths:
            # Simple glob-style matching
            if pattern.endswith('/*'):
                # Directory prefix match
                if abs_path.startswith(os.path.abspath(pattern[:-2])):
                    return True
            elif pattern.endswith('/*.md'):
                # File extension match in directory
                dir_path = os.path.abspath(pattern[:-5])
                if abs_path.startswith(dir_path) and abs_path.endswith('.md'):
                    return True
            elif '*' in pattern:
                # Generic glob pattern
                import fnmatch
                if fnmatch.fnmatch(abs_path, os.path.abspath(pattern)):
                    return True
            else:
                # Exact match
                if abs_path == os.path.abspath(pattern):
                    return True

        return False

    def is_command_allowed(self, command: str) -> bool:
        """
        Check if a bash command is allowed in this mode.

        Args:
            command: Command string to check

        Returns:
            True if command is allowed, False otherwise
        """
        # First check if bash is completely denied
        if self.tool_permissions.get('bash') == 'deny':
            return False

        # Empty allowed_commands means all commands are allowed (if bash is allowed)
        if not self.allowed_commands:
            return True

        # Extract the base command (first word)
        base_cmd = command.strip().split()[0] if command.strip() else ''

        # Check if base command is in whitelist
        return base_cmd in self.allowed_commands


# Agent mode configurations
AGENT_MODES = {
    'build': AgentMode(
        name='build',
        description='Full access mode - can write, edit, and execute bash commands',
        tool_permissions={
            'write': True,
            'edit': True,
            'bash': 'allow',
            'browser': True
        },
        allowed_paths=[],  # All paths allowed
        allowed_commands=[]  # All commands allowed
    ),
    'plan': AgentMode(
        name='plan',
        description='Read-only mode - can read and analyze but not modify files or execute bash',
        tool_permissions={
            'write': False,
            'edit': False,
            'bash': 'ask',
            'browser': True
        },
        allowed_paths=[],  # All paths allowed for reading
        allowed_commands=[]  # No commands by default (ask mode)
    ),
    'review': AgentMode(
        name='review',
        description='Code review mode - read-only access with safe diagnostic commands',
        tool_permissions={
            'write': False,
            'edit': False,
            'bash': 'allow',  # But limited to safe commands via whitelist
            'browser': True
        },
        allowed_paths=[],  # All paths allowed for reading
        allowed_commands=[
            'git', 'diff', 'grep', 'find', 'cat', 'head', 'tail', 'less',
            'ls', 'tree', 'wc', 'file', 'stat', 'du',
            'npm', 'npx', 'pytest', 'cargo', 'go',  # Test/lint runners
            'eslint', 'tsc', 'mypy', 'flake8', 'pylint', 'ruff',
            'echo', 'printf', 'date', 'pwd', 'which'
        ]
    ),
    'debug': AgentMode(
        name='debug',
        description='Debug mode - read access with diagnostic commands, no file writes',
        tool_permissions={
            'write': False,
            'edit': False,
            'bash': 'allow',  # Limited to diagnostic commands
            'browser': True
        },
        allowed_paths=[],  # All paths allowed for reading
        allowed_commands=[
            # Version control
            'git',
            # File inspection
            'cat', 'head', 'tail', 'less', 'more', 'grep', 'find', 'ls', 'tree',
            'file', 'stat', 'du', 'wc', 'diff',
            # Process inspection
            'ps', 'top', 'htop', 'pgrep', 'lsof', 'netstat', 'ss',
            # System info
            'uname', 'hostname', 'uptime', 'df', 'free', 'env', 'printenv',
            # Network diagnostics
            'ping', 'traceroute', 'curl', 'wget', 'nc', 'telnet', 'host', 'dig', 'nslookup',
            # Log viewing
            'journalctl', 'dmesg', 'tail',
            # Language-specific debuggers
            'node', 'python', 'python3', 'gdb', 'lldb', 'strace', 'ltrace',
            # Package managers (list/query only)
            'npm', 'pip', 'cargo', 'go',
            # Test runners (dry-run/list tests)
            'pytest', 'jest', 'mocha', 'cargo',
            # Utilities
            'echo', 'printf', 'date', 'pwd', 'which', 'whereis', 'whoami'
        ]
    ),
    'docs': AgentMode(
        name='docs',
        description='Documentation mode - can only write to docs/ and markdown files',
        tool_permissions={
            'write': True,  # But limited by allowed_paths
            'edit': True,   # But limited by allowed_paths
            'bash': 'deny',
            'browser': False
        },
        allowed_paths=[
            'docs/*',
            '*.md',
            'README.md',
            'CHANGELOG.md',
            'CONTRIBUTING.md',
            'LICENSE.md',
            'doc/*',
            'documentation/*',
            '.github/*.md'
        ],
        allowed_commands=[]  # No bash commands allowed
    ),
    'safe': AgentMode(
        name='safe',
        description='Maximum safety mode - whitelist of tools only, no bash, restricted paths',
        tool_permissions={
            'write': False,
            'edit': False,
            'bash': 'deny',
            'browser': False
        },
        allowed_paths=[
            # Only allow reading from common safe directories
            'docs/*',
            '*.md',
            'README.md',
            'tests/*',
            'examples/*'
        ],
        allowed_commands=[]  # No bash commands allowed
    )
}


def get_agent_mode(mode_name: str = None) -> AgentMode:
    """
    Get agent mode configuration by name.

    Args:
        mode_name: Name of the mode ('build', 'plan', etc.).
                   Defaults to DEFAULT_MODE if not specified.

    Returns:
        AgentMode configuration object

    Raises:
        ValueError: If mode_name is not found in AGENT_MODES
    """
    if mode_name is None:
        mode_name = DEFAULT_MODE

    mode_name = mode_name.lower()

    if mode_name not in AGENT_MODES:
        available = ', '.join(AGENT_MODES.keys())
        raise ValueError(f"Unknown agent mode '{mode_name}'. Available modes: {available}")

    return AGENT_MODES[mode_name]


# ============================================================================
# Optional Module Availability Flags
# ============================================================================

def check_optional_modules() -> Dict[str, bool]:
    """Check availability of optional modules."""
    flags = {}

    # Email outreach
    try:
        from .email_outreach import EmailOutreach
        flags['email_outreach'] = True
    except ImportError:
        flags['email_outreach'] = False

    # Multi-tab
    try:
        from .multi_tab import TabManager
        flags['multi_tab'] = True
    except ImportError:
        flags['multi_tab'] = False

    # Strategic planner
    try:
        from .strategic_planner import get_strategic_planner
        flags['strategic_planner'] = True
    except ImportError:
        flags['strategic_planner'] = False

    # Skill library
    if os.environ.get('EVERSALE_DISABLE_SKILLS', '').lower() in ('1', 'true', 'yes'):
        flags['skill_library'] = False
    else:
        try:
            from .skill_library import SkillLibrary
            flags['skill_library'] = True
        except (ImportError, MemoryError):
            flags['skill_library'] = False

    # Reflexion
    try:
        from .reflexion import ReflexionEngine
        flags['reflexion'] = True
    except ImportError:
        flags['reflexion'] = False

    # Intent detector
    try:
        from .intent_detector import IntentDetector
        flags['intent_detector'] = True
    except ImportError:
        flags['intent_detector'] = False

    # Capability router
    try:
        from .capability_router import CapabilityRouter
        flags['capability_router'] = True
    except ImportError:
        flags['capability_router'] = False

    return flags


# Module availability (cached)
_MODULE_FLAGS: Optional[Dict[str, bool]] = None

def get_module_flags() -> Dict[str, bool]:
    """Get cached module availability flags."""
    global _MODULE_FLAGS
    if _MODULE_FLAGS is None:
        _MODULE_FLAGS = check_optional_modules()
    return _MODULE_FLAGS


# ============================================================================
# Configuration Dataclass
# ============================================================================

@dataclass
class BrainConfig:
    """
    Configuration container for EnhancedBrain.

    Parses raw config dict and provides typed access to all settings
    with sensible defaults.
    """
    # LLM settings
    llm_base_url: str = DEFAULT_LLM_BASE_URL
    llm_fallback_url: str = DEFAULT_LLM_BASE_URL
    main_model: str = DEFAULT_MAIN_MODEL
    vision_model: str = DEFAULT_VISION_MODEL
    fast_model: str = DEFAULT_FAST_MODEL
    temperature: float = DEFAULT_TEMPERATURE
    max_iterations: int = DEFAULT_MAX_ITERATIONS
    llm_timeout: float = DEFAULT_LLM_TIMEOUT_MS / 1000

    # Agent settings
    task_timeout: int = DEFAULT_TASK_TIMEOUT_SECONDS
    checkpoint_interval: int = DEFAULT_CHECKPOINT_INTERVAL_SECONDS
    steering_pause_timeout: int = DEFAULT_STEERING_PAUSE_TIMEOUT_SECONDS
    dead_mans_timeout_hours: float = DEFAULT_DEAD_MANS_TIMEOUT_HOURS
    steering_enabled: bool = True

    # Context settings
    max_context_messages: int = DEFAULT_MAX_CONTEXT_MESSAGES
    compact_threshold: int = DEFAULT_COMPACT_THRESHOLD

    # Preflight settings
    max_preflight_attempts: int = DEFAULT_MAX_PREFLIGHT_ATTEMPTS
    preflight_retry_delay: int = DEFAULT_PREFLIGHT_RETRY_DELAY

    # Improvement settings
    review_interval: int = DEFAULT_REVIEW_INTERVAL
    review_history_len: int = DEFAULT_REVIEW_HISTORY_LEN

    # Instance settings
    instance_id: Optional[str] = None

    # Email settings
    email_config: Dict[str, Any] = field(default_factory=dict)

    # Agent mode
    agent_mode: str = DEFAULT_MODE

    # Raw config reference
    raw_config: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> 'BrainConfig':
        """Create BrainConfig from raw config dictionary."""
        llm = config.get('llm', {})
        agent = config.get('agent', {})

        # Determine LLM base URL based on mode
        llm_mode = llm.get('mode', 'local')
        if llm_mode == 'remote':
            base_url = llm.get('remote_url', llm.get('base_url', DEFAULT_LLM_BASE_URL))
        else:
            base_url = llm.get('local_url', llm.get('base_url', DEFAULT_LLM_BASE_URL))

        return cls(
            # LLM settings
            llm_base_url=base_url,
            llm_fallback_url=llm.get('fallback_url', DEFAULT_LLM_BASE_URL),
            main_model=llm.get('main_model', DEFAULT_MAIN_MODEL),
            vision_model=llm.get('vision_model', DEFAULT_VISION_MODEL),
            fast_model=llm.get('fast_model', llm.get('router_model', DEFAULT_FAST_MODEL)),
            temperature=llm.get('temperature', DEFAULT_TEMPERATURE),
            max_iterations=llm.get('max_iterations', DEFAULT_MAX_ITERATIONS),
            llm_timeout=llm.get('timeout_ms', DEFAULT_LLM_TIMEOUT_MS) / 1000,

            # Agent settings
            task_timeout=agent.get('task_timeout_seconds', DEFAULT_TASK_TIMEOUT_SECONDS),
            checkpoint_interval=agent.get('checkpoint_interval_seconds', DEFAULT_CHECKPOINT_INTERVAL_SECONDS),
            steering_pause_timeout=agent.get('steering_pause_timeout_seconds', DEFAULT_STEERING_PAUSE_TIMEOUT_SECONDS),
            dead_mans_timeout_hours=config.get('dead_mans_timeout_hours', DEFAULT_DEAD_MANS_TIMEOUT_HOURS),
            steering_enabled=config.get('steering_enabled', True),

            # Context settings
            max_context_messages=config.get('max_context_messages', DEFAULT_MAX_CONTEXT_MESSAGES),
            compact_threshold=config.get('compact_threshold', DEFAULT_COMPACT_THRESHOLD),

            # Preflight settings
            max_preflight_attempts=config.get('max_preflight_attempts', DEFAULT_MAX_PREFLIGHT_ATTEMPTS),
            preflight_retry_delay=config.get('preflight_retry_delay', DEFAULT_PREFLIGHT_RETRY_DELAY),

            # Improvement settings
            review_interval=config.get('improvement_review_interval', DEFAULT_REVIEW_INTERVAL),
            review_history_len=config.get('improvement_review_history', DEFAULT_REVIEW_HISTORY_LEN),

            # Instance settings
            instance_id=config.get('instance_id'),

            # Email settings
            email_config=config.get('email', {}),

            # Agent mode
            agent_mode=config.get('agent_mode', agent.get('mode', DEFAULT_MODE)),

            # Raw config
            raw_config=config,
        )


# ============================================================================
# Component Initializer
# ============================================================================

class ComponentInitializer:
    """
    Handles initialization of all EnhancedBrain components.

    This class encapsulates the complex initialization logic,
    providing graceful fallbacks for optional components.
    """

    def __init__(self, config: BrainConfig, mcp_client):
        self.config = config
        self.mcp = mcp_client
        self.module_flags = get_module_flags()

    def create_ollama_client(self) -> OllamaClient:
        """Create and configure Ollama client."""
        # Get license key from environment or license file for GPU LLM proxy auth
        license_key = None
        try:
            from .license_validator import get_license_key
            license_key = get_license_key()
            if license_key:
                logger.debug("License key loaded for GPU LLM authentication")
        except Exception as e:
            logger.debug(f"Could not load license key: {e}")

        client = OllamaClient(host=self.config.llm_base_url, license_key=license_key)
        if self.config.llm_base_url != DEFAULT_LLM_BASE_URL:
            logger.info(f"Using remote LLM server: {self.config.llm_base_url}")
        return client

    def init_memory_architecture(self) -> Optional[MemoryArchitecture]:
        """Initialize memory architecture with graceful fallback."""
        try:
            arch = MemoryArchitecture(working_capacity=50, auto_consolidate=True)
            logger.info("Memory architecture initialized")
            return arch
        except Exception as e:
            logger.warning(f"Memory architecture initialization failed: {e}")
            return None

    def init_awareness(self) -> AwarenessHub:
        """Initialize awareness hub."""
        return AwarenessHub()

    def init_cache(self) -> Cache:
        """Initialize LLM response cache."""
        return Cache(cache_dir=DEFAULT_CACHE_DIR, max_items=DEFAULT_CACHE_MAX_ITEMS)

    def init_survival(self) -> SurvivalManager:
        """Initialize survival manager."""
        return SurvivalManager()

    def init_crash_recovery(self):
        """Initialize crash recovery."""
        if CrashRecovery is None:
            logger.warning("CrashRecovery not available (deprecated in v2.9+)")
            return None
        return CrashRecovery()

    def init_dead_mans_switch(self) -> Optional[DeadMansSwitch]:
        """Initialize dead man's switch with graceful fallback."""
        try:
            switch = DeadMansSwitch(timeout_hours=self.config.dead_mans_timeout_hours)
            switch.start_monitoring()
            return switch
        except Exception as e:
            logger.warning(f"Dead man's switch disabled: {e}")
            return None

    def init_resource_limiter(self) -> Optional[ResourceLimiter]:
        """Initialize resource limiter with graceful fallback."""
        try:
            limiter = ResourceLimiter()
            limiter.start_monitoring()
            return limiter
        except Exception as e:
            logger.warning(f"Resource limiter disabled: {e}")
            return None

    def init_coordinator(self) -> Optional[MultiInstanceCoordinator]:
        """Initialize multi-instance coordinator with graceful fallback."""
        try:
            coordinator = MultiInstanceCoordinator(
                instance_id=self.config.instance_id
            )
            coordinator.register()
            return coordinator
        except Exception as e:
            logger.warning(f"Multi-instance coordination disabled: {e}")
            return None

    def init_hallucination_guard(self):
        """Initialize hallucination guard with graceful fallback."""
        if HallucinationGuard is None:
            logger.warning("HallucinationGuard not available (deprecated in v2.9+)")
            return None
        try:
            return HallucinationGuard(strict_mode=True)
        except Exception as e:
            logger.warning(f"Hallucination guard disabled: {e}")
            return None

    def init_resource_monitor(self) -> ResourceMonitor:
        """Initialize resource monitor."""
        monitor = ResourceMonitor(
            cpu_threshold=DEFAULT_CPU_THRESHOLD,
            mem_threshold=DEFAULT_MEM_THRESHOLD,
            gpu_threshold=DEFAULT_GPU_THRESHOLD
        )
        monitor.enforce_memory_limit(max_mb=DEFAULT_MAX_MEMORY_MB)
        return monitor

    def init_decision_logger(self) -> DecisionLogger:
        """Initialize decision logger."""
        return DecisionLogger()

    def init_session_state(self, decision_logger: DecisionLogger,
                           awareness: AwarenessHub,
                           survival: SurvivalManager) -> SessionState:
        """Initialize session state."""
        return SessionState(
            decision_logger=decision_logger,
            awareness=awareness,
            survival=survival
        )

    def init_adaptive_explorer(self) -> AdaptiveExplorer:
        """Initialize adaptive explorer."""
        return AdaptiveExplorer()

    def init_resource_economy(self) -> Optional[ResourceEconomy]:
        """Initialize resource economy with graceful fallback."""
        try:
            return ResourceEconomy()
        except Exception as e:
            logger.warning(f"Resource economy disabled: {e}")
            return None

    def init_cascading_recovery(self):
        """Initialize cascading recovery system with graceful fallback."""
        if CascadingRecoverySystem is None:
            logger.warning("CascadingRecoverySystem not available (deprecated in v2.9+)")
            return None
        try:
            system = CascadingRecoverySystem(
                memory_path=Path("memory/cascading_recovery.json"),
                enable_learning=True
            )
            logger.info("Cascading recovery system initialized")
            return system
        except Exception as e:
            logger.warning(f"Cascading recovery system disabled: {e}")
            return None

    def init_intent_detector(self):
        """Initialize intent detector with graceful fallback."""
        if not self.module_flags.get('intent_detector'):
            return None
        try:
            from .intent_detector import IntentDetector
            return IntentDetector()
        except Exception as e:
            logger.error(f"Failed to initialize intent detector: {e}")
            return None

    def init_capability_router(self):
        """Initialize capability router with graceful fallback."""
        if not self.module_flags.get('capability_router'):
            return None
        try:
            from .capability_router import CapabilityRouter
            return CapabilityRouter()
        except Exception as e:
            logger.error(f"Failed to initialize capability router: {e}")
            return None

    def init_email_outreach(self):
        """Initialize email outreach with graceful fallback."""
        if not self.module_flags.get('email_outreach'):
            return None
        try:
            from .email_outreach import EmailOutreach
            outreach = EmailOutreach(self.config.email_config)
            logger.info("Email outreach module initialized")
            return outreach
        except Exception as e:
            logger.warning(f"Email outreach disabled: {e}")
            return None

    def init_strategic_planner(self):
        """Initialize strategic planner with graceful fallback."""
        if not self.module_flags.get('strategic_planner'):
            return None
        try:
            from .strategic_planner import get_strategic_planner
            planner = get_strategic_planner(self.config.raw_config)
            logger.info("Strategic planner initialized")
            return planner
        except Exception as e:
            logger.debug(f"Strategic planner disabled: {e}")
            return None

    def init_reflexion(self):
        """Initialize reflexion engine with graceful fallback."""
        if not self.module_flags.get('reflexion'):
            return None
        try:
            from .reflexion import ReflexionEngine
            engine = ReflexionEngine(self.config.raw_config)
            logger.info("Reflexion self-improvement system initialized")
            return engine
        except Exception as e:
            logger.warning(f"Reflexion system initialization failed: {e}")
            return None

    def init_context_memory(self) -> ContextMemory:
        """Initialize context memory."""
        return ContextMemory()

    def init_steering(self) -> SteeringInput:
        """Initialize steering input."""
        return SteeringInput()

    def init_organism(self, survival, awareness, reflexion, memory_arch, ollama_client):
        """Initialize the organism core - the nervous system that connects everything."""
        try:
            from .organism_core import init_organism
            organism = init_organism(
                survival_manager=survival,
                awareness_hub=awareness,
                reflexion_engine=reflexion,
                memory_arch=memory_arch,
                llm_client=ollama_client,
                fast_model=self.config.fast_model,
                mission="EverSale customers succeed because of me"
            )
            logger.info("Organism core initialized - nervous system active")
            return organism
        except Exception as e:
            logger.warning(f"Organism initialization failed: {e}")
            return None

    async def init_siao_core(self, organism, memory_arch, ollama_client):
        """Initialize the SIAO core - the complete AGI architecture with all 9 components."""
        try:
            from .siao_core import init_siao_core, SIAOConfig
            siao = await init_siao_core(
                base_organism=organism,
                memory_arch=memory_arch,
                llm_client=ollama_client,
                fast_model=self.config.fast_model,
                config=SIAOConfig(
                    sleep_threshold=1000,
                    enable_dreams=True,
                    investigation_on_idle=True
                )
            )
            logger.info("SIAO core initialized - all 9 AGI components active")
            return siao
        except Exception as e:
            logger.warning(f"SIAO core initialization failed (using base organism): {e}")
            return None


def initialize_all_components(config: BrainConfig, mcp_client) -> Dict[str, Any]:
    """
    Initialize all brain components and return them as a dictionary.

    This is a convenience function that initializes all components
    in the correct order and returns them for assignment.

    Args:
        config: BrainConfig instance
        mcp_client: MCP client instance

    Returns:
        Dictionary with all initialized components
    """
    init = ComponentInitializer(config, mcp_client)

    # Initialize core components
    awareness = init.init_awareness()
    survival = init.init_survival()
    decision_logger = init.init_decision_logger()
    ollama_client = init.create_ollama_client()
    memory_arch = init.init_memory_architecture()
    reflexion = init.init_reflexion()

    # Initialize session state (depends on core components)
    session_state = init.init_session_state(decision_logger, awareness, survival)

    # Initialize organism - the nervous system connecting all organs
    organism = init.init_organism(survival, awareness, reflexion, memory_arch, ollama_client)

    return {
        # Ollama client
        'ollama_client': ollama_client,

        # Core components
        'awareness': awareness,
        'survival': survival,
        'decision_logger': decision_logger,
        'session_state': session_state,

        # Memory
        'context_memory': init.init_context_memory(),
        'memory_arch': memory_arch,
        'cache': init.init_cache(),

        # Recovery & monitoring
        'crash_recovery': init.init_crash_recovery(),
        'dead_mans_switch': init.init_dead_mans_switch(),
        'resource_limiter': init.init_resource_limiter(),
        'coordinator': init.init_coordinator(),
        'hallucination_guard': init.init_hallucination_guard(),
        'resource_monitor': init.init_resource_monitor(),
        'cascading_recovery': init.init_cascading_recovery(),

        # Helpers
        'adaptive_explorer': init.init_adaptive_explorer(),
        'resource_economy': init.init_resource_economy(),

        # Optional modules
        'intent_detector': init.init_intent_detector(),
        'capability_router': init.init_capability_router(),
        'email_outreach': init.init_email_outreach(),
        'strategic_planner': init.init_strategic_planner(),
        'reflexion': reflexion,

        # Steering
        'steering': init.init_steering(),

        # Organism - the nervous system
        'organism': organism,
    }


# ============================================================================
# Agent Mode Tests
# ============================================================================

def test_agent_modes():
    """
    Comprehensive test suite for all agent modes.

    Tests:
    1. All modes are properly configured
    2. Tool permissions work correctly
    3. Path restrictions work correctly
    4. Command whitelisting works correctly
    5. Mode retrieval works correctly
    """
    print("\n========== Testing Agent Modes ==========\n")

    # Test 1: All modes exist and are properly configured
    print("Test 1: Mode Configuration")
    expected_modes = ['build', 'plan', 'review', 'debug', 'docs', 'safe']
    for mode_name in expected_modes:
        assert mode_name in AGENT_MODES, f"Mode '{mode_name}' not found"
        mode = AGENT_MODES[mode_name]
        assert mode.name == mode_name, f"Mode name mismatch: {mode.name} != {mode_name}"
        assert mode.description, f"Mode '{mode_name}' missing description"
        assert isinstance(mode.tool_permissions, dict), f"Mode '{mode_name}' has invalid tool_permissions"
        print(f"  ✓ {mode_name}: {mode.description}")

    # Test 2: Build mode (full access)
    print("\nTest 2: Build Mode (Full Access)")
    build_mode = AGENT_MODES['build']
    assert build_mode.is_tool_allowed('write'), "Build mode should allow write"
    assert build_mode.is_tool_allowed('edit'), "Build mode should allow edit"
    assert build_mode.is_tool_allowed('bash'), "Build mode should allow bash"
    assert build_mode.is_tool_allowed('browser'), "Build mode should allow browser"
    assert build_mode.is_path_allowed('/any/path/file.py'), "Build mode should allow all paths"
    assert build_mode.is_command_allowed('rm -rf /'), "Build mode should allow all commands"
    print("  ✓ Build mode has full access")

    # Test 3: Plan mode (read-only)
    print("\nTest 3: Plan Mode (Read-Only)")
    plan_mode = AGENT_MODES['plan']
    assert not plan_mode.is_tool_allowed('write'), "Plan mode should deny write"
    assert not plan_mode.is_tool_allowed('edit'), "Plan mode should deny edit"
    assert plan_mode.requires_permission('bash'), "Plan mode should ask for bash permission"
    assert plan_mode.is_tool_allowed('browser'), "Plan mode should allow browser"
    print("  ✓ Plan mode is read-only")

    # Test 4: Review mode (safe commands only)
    print("\nTest 4: Review Mode (Safe Commands)")
    review_mode = AGENT_MODES['review']
    assert not review_mode.is_tool_allowed('write'), "Review mode should deny write"
    assert not review_mode.is_tool_allowed('edit'), "Review mode should deny edit"
    assert review_mode.is_tool_allowed('bash'), "Review mode should allow bash"
    assert review_mode.is_command_allowed('git diff'), "Review mode should allow git diff"
    assert review_mode.is_command_allowed('npm test'), "Review mode should allow npm test"
    assert not review_mode.is_command_allowed('rm -rf /'), "Review mode should deny destructive commands"
    assert not review_mode.is_command_allowed('sudo systemctl'), "Review mode should deny sudo"
    print("  ✓ Review mode allows safe commands only")
    print(f"  ✓ Whitelisted commands: {len(review_mode.allowed_commands)}")

    # Test 5: Debug mode (diagnostic commands)
    print("\nTest 5: Debug Mode (Diagnostic Commands)")
    debug_mode = AGENT_MODES['debug']
    assert not debug_mode.is_tool_allowed('write'), "Debug mode should deny write"
    assert not debug_mode.is_tool_allowed('edit'), "Debug mode should deny edit"
    assert debug_mode.is_command_allowed('git status'), "Debug mode should allow git status"
    assert debug_mode.is_command_allowed('ps aux'), "Debug mode should allow ps"
    assert debug_mode.is_command_allowed('curl http://api.example.com'), "Debug mode should allow curl"
    assert not debug_mode.is_command_allowed('rm file.txt'), "Debug mode should deny rm"
    assert not debug_mode.is_command_allowed('chmod 777'), "Debug mode should deny chmod"
    print("  ✓ Debug mode allows diagnostic commands")
    print(f"  ✓ Whitelisted commands: {len(debug_mode.allowed_commands)}")

    # Test 6: Docs mode (documentation only)
    print("\nTest 6: Docs Mode (Documentation Only)")
    docs_mode = AGENT_MODES['docs']
    assert docs_mode.is_tool_allowed('write'), "Docs mode should allow write"
    assert docs_mode.is_tool_allowed('edit'), "Docs mode should allow edit"
    assert not docs_mode.is_tool_allowed('bash'), "Docs mode should deny bash"
    assert not docs_mode.is_tool_allowed('browser'), "Docs mode should deny browser"

    # Test path restrictions for docs mode
    # Note: These tests use current directory as base for path resolution
    import os
    cwd = os.getcwd()

    # Should allow markdown files
    assert docs_mode.is_path_allowed('README.md'), "Docs mode should allow README.md"
    assert docs_mode.is_path_allowed('CHANGELOG.md'), "Docs mode should allow CHANGELOG.md"

    # Should not allow non-docs files
    test_py_path = os.path.join(cwd, 'test.py')
    assert not docs_mode.is_path_allowed(test_py_path), "Docs mode should deny .py files"

    print("  ✓ Docs mode restricts to documentation files")
    print(f"  ✓ Allowed path patterns: {len(docs_mode.allowed_paths)}")

    # Test 7: Safe mode (maximum restrictions)
    print("\nTest 7: Safe Mode (Maximum Restrictions)")
    safe_mode = AGENT_MODES['safe']
    assert not safe_mode.is_tool_allowed('write'), "Safe mode should deny write"
    assert not safe_mode.is_tool_allowed('edit'), "Safe mode should deny edit"
    assert not safe_mode.is_tool_allowed('bash'), "Safe mode should deny bash"
    assert not safe_mode.is_tool_allowed('browser'), "Safe mode should deny browser"
    assert not safe_mode.is_command_allowed('git status'), "Safe mode should deny all commands"

    # Should only allow reading from safe directories
    assert safe_mode.is_path_allowed('README.md'), "Safe mode should allow README.md"

    print("  ✓ Safe mode has maximum restrictions")

    # Test 8: Mode retrieval
    print("\nTest 8: Mode Retrieval")
    mode = get_agent_mode('build')
    assert mode.name == 'build', "get_agent_mode should return correct mode"

    mode = get_agent_mode()  # Should return default
    assert mode.name == DEFAULT_MODE, "get_agent_mode should return default mode"

    try:
        get_agent_mode('invalid_mode')
        assert False, "get_agent_mode should raise ValueError for invalid mode"
    except ValueError as e:
        assert 'Unknown agent mode' in str(e), "Error message should indicate unknown mode"

    print("  ✓ Mode retrieval works correctly")

    # Test 9: Permission checking
    print("\nTest 9: Permission Checking")
    review_mode = AGENT_MODES['review']
    assert not review_mode.requires_permission('read'), "Review mode shouldn't require permission for read"

    plan_mode = AGENT_MODES['plan']
    assert plan_mode.requires_permission('bash'), "Plan mode should require permission for bash"

    print("  ✓ Permission checking works correctly")

    # Summary
    print("\n========== All Tests Passed ==========\n")
    print(f"Total modes tested: {len(AGENT_MODES)}")
    print(f"Available modes: {', '.join(AGENT_MODES.keys())}")
    print("\nMode Summary:")
    for mode_name, mode in AGENT_MODES.items():
        permissions = []
        if mode.tool_permissions.get('write'):
            permissions.append('write')
        if mode.tool_permissions.get('edit'):
            permissions.append('edit')
        bash_perm = mode.tool_permissions.get('bash')
        if bash_perm == 'allow':
            permissions.append('bash')
        elif bash_perm == 'ask':
            permissions.append('bash(ask)')
        if mode.tool_permissions.get('browser'):
            permissions.append('browser')

        restrictions = []
        if mode.allowed_paths:
            restrictions.append(f"{len(mode.allowed_paths)} path patterns")
        if mode.allowed_commands:
            restrictions.append(f"{len(mode.allowed_commands)} commands")

        restriction_str = f" [{', '.join(restrictions)}]" if restrictions else ""
        print(f"  {mode_name:8s}: {', '.join(permissions) if permissions else 'read-only'}{restriction_str}")

    return True


if __name__ == '__main__':
    # Run tests when module is executed directly
    test_agent_modes()
