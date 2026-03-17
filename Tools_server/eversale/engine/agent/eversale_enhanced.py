#!/usr/bin/env python3
"""
Eversale Enhanced - Unified Integration Layer
==============================================

Master integration file that connects all enhanced Eversale modules into a cohesive,
production-grade AI agent system. This is the single entry point for using all
advanced capabilities.

Integrated Modules:
-------------------
1. DOM Distillation (dom_distillation.py) - Semantic page understanding
2. HTN Planning (planning_agent.py) - Hierarchical task decomposition
3. Reflexion (reflexion.py) - Self-improvement through reflection
4. Enhanced Stealth (stealth_enhanced.py) - Advanced anti-bot evasion
5. Skill Library (skill_library.py) - Voyager-style skill acquisition
6. Visual Grounding (visual_grounding.py) - Vision-based element finding
7. Cascading Recovery (cascading_recovery.py) - 10-level error recovery
8. Memory Architecture (memory_architecture.py) - Multi-layer memory system
9. Workflows (workflows.py) - Pre-built task orchestration
10. Agent Network (agent_network.py) - Multi-agent coordination

Architecture:
-------------
    Enhanced Brain (extends brain_enhanced_v2.py)
           |
           +-- Planning Layer (HTN)
           +-- Perception Layer (DOM + Vision)
           +-- Action Layer (Skills + Stealth)
           +-- Recovery Layer (Cascading)
           +-- Learning Layer (Reflexion + Memory)
           +-- Coordination Layer (Multi-agent)

Action Loop:
------------
User Request → Plan (HTN) → Perceive (DOM/Vision) → Select Skill →
Execute with Stealth → Recover on Error (Cascade) → Reflect (Reflexion) →
Store Experience (Memory) → Learn Skill (Library) → Report

Factory Functions:
------------------
- create_enhanced_brain() - Full featured (all modules)
- create_minimal_brain() - Basic features only
- create_stealth_brain() - Anti-bot focused
- create_enterprise_brain() - Full + compliance & monitoring

Author: Eversale AI
Version: 2.0.0
Date: 2025-12-02
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable, Tuple, Set, Awaitable
from dataclasses import dataclass, field, asdict
from enum import Enum

import yaml
from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Import base brain
try:
    from .brain_enhanced_v2 import (  # type: ignore
        EnhancedBrain,
        ActionResult,
        ForeverTaskState,
        create_enhanced_brain as create_base_brain
    )
    BrainEnhancedV2 = EnhancedBrain
    BASE_BRAIN_AVAILABLE = True
except Exception as import_error:
    BASE_BRAIN_AVAILABLE = False

    class BrainEnhancedV2:
        """Fallback placeholder when the real brain implementation is unavailable."""

        async def run(self, prompt: str) -> str:
            return f"(stub) Unable to run prompt: {prompt}"

    @dataclass
    class ActionResult:
        success: bool
        data: Any = None
        error: str = ""
        screenshot: bytes = None

    ForeverTaskState = object  # type: ignore
    create_base_brain = lambda *args, **kwargs: None  # type: ignore
    logger.error(
        "brain_enhanced_v2.py not available - cannot create enhanced brain",
        exc_info=import_error
    )

from .mcp_client import MCPClient

# Import new LocalLLaMA architecture components (SmartBrain)
try:
    from .smart_brain import (
        SmartBrain,
        SmartResult,
        IntentDetector,
        TaskType,
        run_task as smart_run_task
    )
    SMART_BRAIN_AVAILABLE = True
except ImportError as smart_import_error:
    SMART_BRAIN_AVAILABLE = False
    logger.warning("SmartBrain not available", exc_info=smart_import_error)

try:
    from .dual_llm_orchestrator import DualLLMOrchestrator
    DUAL_LLM_AVAILABLE = True
except ImportError:
    DUAL_LLM_AVAILABLE = False

try:
    from .web_daemon import WebDaemon
    WEB_DAEMON_AVAILABLE = True
except ImportError:
    WEB_DAEMON_AVAILABLE = False

try:
    from .worker_loop import WorkerLoop, WorkerJob
    WORKER_LOOP_AVAILABLE = True
except ImportError:
    WORKER_LOOP_AVAILABLE = False

try:
    from .tool_wrappers import ToolRegistry, ToolWrapper
    TOOL_WRAPPERS_AVAILABLE = True
except ImportError:
    TOOL_WRAPPERS_AVAILABLE = False

try:
    from .compressed_dom import DOMCompressor
    COMPRESSED_DOM_AVAILABLE = True
except ImportError:
    COMPRESSED_DOM_AVAILABLE = False

try:
    from .browser_tool_schemas import BROWSER_TOOL_SCHEMAS, validate_tool_call
    BROWSER_TOOL_SCHEMAS_AVAILABLE = True
except ImportError:
    BROWSER_TOOL_SCHEMAS_AVAILABLE = False

# Import enhanced modules
# DEPRECATED: dom_distillation module removed in v2.9 - functionality moved to accessibility_element_finder
try:
    from .dom_distillation import (
        DOMDistillationEngine,
        DistillationMode,
        AccessibilityNode,
        ElementInfo,
        DOMSnapshot
    )
    DOM_DISTILLATION_AVAILABLE = True
except ImportError as distillation_error:
    DOM_DISTILLATION_AVAILABLE = False
    logger.debug("DOM distillation not available (removed in v2.9)", exc_info=distillation_error)

try:
    from .planning_agent import (
        PlanningAgent,
        Plan,
        PlanStep,
        PlanStatus,
        PlanCritic,
        PlanExecutor,
        PlanTemplate
    )
    PLANNING_AVAILABLE = True
except ImportError:
    PLANNING_AVAILABLE = False
    logger.warning("HTN planning not available")

try:
    from .reflexion import (
        ReflexionEngine,
        ReflexionMemory,
        TaskAttempt,
        SelfReflection,
        ReflectionType,
        ReflexionMetrics
    )
    REFLEXION_AVAILABLE = True
except ImportError as reflexion_error:
    REFLEXION_AVAILABLE = False
    logger.warning("Reflexion not available", exc_info=reflexion_error)

try:
    from .stealth_enhanced import (
        EnhancedStealthSession,
        FingerprintManager,
        ProxyManager,
        BehaviorMimicry,
        DetectionResponse,
        SiteProfile,
        get_stealth_session
    )
    STEALTH_AVAILABLE = True
except ImportError as stealth_error:
    STEALTH_AVAILABLE = False
    logger.warning("Enhanced stealth not available", exc_info=stealth_error)

try:
    from .skill_library import (
        SkillLibrary,
        Skill,
        SkillCategory,
        SkillRetriever,
        SkillComposer,
        SkillValidator
    )
    SKILL_LIBRARY_AVAILABLE = True
except ImportError:
    SKILL_LIBRARY_AVAILABLE = False
    logger.warning("Skill library not available")

try:
    from .visual_grounding import (
        VisualGroundingEngine,
        GroundingStrategy,
        ElementType,
        VisualElement
    )
    VISUAL_GROUNDING_AVAILABLE = True
except ImportError as grounding_error:
    VISUAL_GROUNDING_AVAILABLE = False
    logger.warning("Visual grounding not available", exc_info=grounding_error)

# DEPRECATED: cascading_recovery module removed in v2.9 - use reliability_core instead
try:
    from .cascading_recovery import (
        CascadingRecoverySystem,
        RecoveryLevel,
        RecoveryContext,
        ErrorCategory
    )
    CASCADING_RECOVERY_AVAILABLE = True
except ImportError as recovery_error:
    CASCADING_RECOVERY_AVAILABLE = False
    # Create stub classes for graceful degradation
    class CascadingRecoverySystem:
        """Stub for removed cascading_recovery - use reliability_core instead."""
        def __init__(self, *args, **kwargs):
            logger.debug("CascadingRecoverySystem stub (removed in v2.9)")
        async def attempt_recovery(self, context, page=None, retry_action=None):
            """Stub recovery - just retry once."""
            if retry_action:
                try:
                    return {"recovered": True, "level": 0, "result": await retry_action()}
                except Exception:
                    pass
            return {"recovered": False, "level": 0, "error": "Recovery not available"}

    class RecoveryContext:
        """Stub for removed RecoveryContext."""
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    RecoveryLevel = None
    ErrorCategory = None
    logger.debug("Cascading recovery not available (removed in v2.9) - using stubs")

try:
    from .memory_architecture import (
        MemoryArchitecture,
        WorkingMemory,
        EpisodicMemory,
        SemanticMemory,
        SkillMemory
    )
    MEMORY_ARCHITECTURE_AVAILABLE = True
except ImportError as memory_error:
    MEMORY_ARCHITECTURE_AVAILABLE = False
    logger.warning("Memory architecture not available", exc_info=memory_error)

try:
    from .workflows import WorkflowEngine, WorkflowStep, WorkflowResult
    WORKFLOWS_AVAILABLE = True
except ImportError:
    WORKFLOWS_AVAILABLE = False
    logger.warning("Workflows not available")

try:
    from .agent_network import AgentNetwork
    AGENT_NETWORK_AVAILABLE = True
except ImportError:
    AGENT_NETWORK_AVAILABLE = False
    logger.warning("Agent network not available")

console = Console()


# ==============================================================================
# CONFIGURATION
# ==============================================================================

@dataclass
class EversaleConfig:
    """Unified configuration for all Eversale modules."""

    # Core settings
    model_name: str = "qwen2.5-coder:32b"
    max_steps: int = 100
    timeout: int = 300

    # Feature flags
    enable_dom_distillation: bool = True
    enable_planning: bool = True
    enable_reflexion: bool = True
    enable_stealth: bool = True
    enable_skill_library: bool = True
    enable_visual_grounding: bool = True
    enable_cascading_recovery: bool = True
    enable_memory_architecture: bool = True
    enable_workflows: bool = True
    enable_agent_network: bool = False  # Optional for multi-agent

    # DOM distillation settings
    dom_mode: str = "HYBRID"  # TEXT_ONLY, INPUT_FIELDS, ALL_CONTENT, HYBRID
    dom_max_tokens: int = 4000

    # Planning settings
    planning_max_depth: int = 5
    planning_validate: bool = True

    # Reflexion settings
    reflexion_max_attempts: int = 5
    reflexion_store_trajectory: bool = True

    # Stealth settings
    stealth_profile: str = "MODERATE"  # MINIMAL, MODERATE, AGGRESSIVE
    stealth_rotate_fingerprint: bool = True

    # Skill library settings
    skill_max_library_size: int = 1000
    skill_auto_learn: bool = True

    # Visual grounding settings
    visual_confidence_threshold: float = 0.7
    visual_fallback_enabled: bool = True

    # Recovery settings
    recovery_max_level: int = 10
    recovery_learn_patterns: bool = True

    # Memory settings
    memory_working_size: int = 50
    memory_consolidate_interval: int = 100  # steps
    memory_compression_ratio: int = 10

    # Performance settings
    parallel_enabled: bool = True
    streaming_enabled: bool = True

    # Monitoring settings
    telemetry_enabled: bool = True
    health_check_interval: int = 60  # seconds

    # Logging settings
    log_level: str = "INFO"
    log_decisions: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EversaleConfig':
        """Create config from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    @classmethod
    def from_file(cls, path: Path) -> 'EversaleConfig':
        """Load config from JSON file."""
        try:
            with open(path) as f:
                data = json.load(f)
            return cls.from_dict(data)
        except Exception as e:
            logger.warning(f"Failed to load config from {path}: {e}")
            return cls()

    def save(self, path: Path):
        """Save config to JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)


# ==============================================================================
# ENHANCED BRAIN CLASS
# ==============================================================================

class EversaleBrainEnhanced(BrainEnhancedV2):
    """
    Enhanced brain that extends BrainEnhancedV2 with all new capabilities.

    This is the master orchestrator that coordinates:
    - Planning (HTN decomposition)
    - Perception (DOM + Vision)
    - Action (Skills + Stealth)
    - Recovery (Cascading error handling)
    - Learning (Reflexion + Memory)
    - Coordination (Multi-agent)
    """

    def __init__(
        self,
        config: Optional[EversaleConfig] = None,
        mcp_client: Optional[Any] = None,
        awareness_hub: Optional[Any] = None,
        base_config: Optional[Dict[str, Any]] = None,
        base_executor: Optional[Callable[[str], Awaitable[ActionResult]]] = None,
        **kwargs
    ):
        """
        Initialize enhanced brain with all modules.

        Args:
            config: Configuration object
            mcp_client: MCP client for Playwright
            awareness_hub: Awareness hub for monitoring
            **kwargs: Additional args for base brain
        """
        if not BASE_BRAIN_AVAILABLE:
            raise RuntimeError("brain_enhanced_v2.py is required for EversaleBrainEnhanced")

        # Store enhanced config profile
        self.settings = config or EversaleConfig()

        # Build base configuration for underlying brain
        self._base_config = base_config or self._build_base_config(self.settings)
        self._awareness_adapter = awareness_hub
        self._mcp_client = mcp_client or MCPClient()

        # Initialize base brain with required config + MCP client
        super().__init__(
            config=self._base_config,
            mcp_client=self._mcp_client
        )

        # Execution helpers
        self._base_executor = base_executor or self._default_base_executor
        self._last_dom_snapshot: Optional[DOMSnapshot] = None
        self._active_stealth_sessions: Dict[int, Any] = {}

        # Initialize enhanced modules
        self._init_modules()

        # Module availability flags
        self.modules_available = {
            "dom_distillation": DOM_DISTILLATION_AVAILABLE and self.settings.enable_dom_distillation,
            "planning": PLANNING_AVAILABLE and self.settings.enable_planning,
            "reflexion": REFLEXION_AVAILABLE and self.settings.enable_reflexion,
            "stealth": STEALTH_AVAILABLE and self.settings.enable_stealth,
            "skill_library": SKILL_LIBRARY_AVAILABLE and self.settings.enable_skill_library,
            "visual_grounding": VISUAL_GROUNDING_AVAILABLE and self.settings.enable_visual_grounding,
            "cascading_recovery": CASCADING_RECOVERY_AVAILABLE and self.settings.enable_cascading_recovery,
            "memory_architecture": MEMORY_ARCHITECTURE_AVAILABLE and self.settings.enable_memory_architecture,
            "workflows": WORKFLOWS_AVAILABLE and self.settings.enable_workflows,
            "agent_network": AGENT_NETWORK_AVAILABLE and self.settings.enable_agent_network,
            # New LocalLLaMA architecture components
            "smart_brain": SMART_BRAIN_AVAILABLE,
            "dual_llm": DUAL_LLM_AVAILABLE,
            "web_daemon": WEB_DAEMON_AVAILABLE,
            "worker_loop": WORKER_LOOP_AVAILABLE,
            "tool_wrappers": TOOL_WRAPPERS_AVAILABLE,
            "compressed_dom": COMPRESSED_DOM_AVAILABLE,
            "browser_tool_schemas": BROWSER_TOOL_SCHEMAS_AVAILABLE,
        }

        # SmartBrain delegate (initialized lazily for natural language auto-routing)
        self._smart_brain: Optional[SmartBrain] = None
        self._smart_brain_enabled = SMART_BRAIN_AVAILABLE

        # Performance metrics
        self.metrics = {
            "total_tasks": 0,
            "successful_tasks": 0,
            "failed_tasks": 0,
            "total_steps": 0,
            "total_recoveries": 0,
            "total_reflections": 0,
            "skills_learned": 0,
            "plans_created": 0,
            "start_time": datetime.now().isoformat(),
        }

        logger.info(f"Enhanced brain initialized with modules: {[k for k, v in self.modules_available.items() if v]}")

    def _build_base_config(self, settings: EversaleConfig) -> Dict[str, Any]:
        """Load base brain configuration from YAML template."""
        template_path = Path("config/config.yaml")
        config_data: Dict[str, Any] = {}

        if template_path.exists():
            try:
                with open(template_path) as f:
                    loaded = yaml.safe_load(f) or {}
                    if isinstance(loaded, dict):
                        config_data = loaded
            except Exception as exc:
                logger.warning(f"Failed to load {template_path}: {exc}")

        # Ensure required sections exist
        config_data.setdefault("agent", {})
        config_data.setdefault("llm", {})

        config_data["agent"].setdefault("max_iterations", settings.max_steps)
        config_data["agent"].setdefault("timeout_seconds", settings.timeout)
        config_data["llm"].setdefault("main_model", settings.model_name)
        config_data["llm"].setdefault("temperature", 0.1)

        return config_data

    async def _default_base_executor(self, prompt: str) -> ActionResult:
        """Call the underlying base brain and wrap response as ActionResult."""
        try:
            output = await super().run(prompt)
            return ActionResult(success=True, data={"output": output})
        except Exception as exc:
            logger.error(f"Base executor failed: {exc}")
            return ActionResult(success=False, error=str(exc))

    async def _prepare_playwright_page(self) -> Optional[Any]:
        """
        Ensure the Playwright page is ready and enhanced with stealth/DOM context.
        Returns the active page if available.
        """
        if not getattr(self, "mcp", None):
            return None

        playwright_server = getattr(self.mcp, "servers", {}).get("playwright") if hasattr(self.mcp, "servers") else None
        if not playwright_server:
            return None

        client = playwright_server.get("client")
        if not client:
            return None

        page = None
        try:
            if hasattr(client, "_ensure_page"):
                await client._ensure_page()
            page = getattr(client, "page", None)
        except Exception as exc:
            logger.debug(f"Playwright page preparation skipped: {exc}")
            return None

        if not page:
            return None

        # Apply stealth once per page
        if self.settings.enable_stealth and self.stealth and not getattr(page, "_enhanced_stealth_ready", False):
            try:
                session = get_stealth_session(page)
                await session.inject_fingerprint()
                page._enhanced_stealth_ready = True
                self._active_stealth_sessions[id(page)] = session
                logger.debug("Stealth fingerprint injected for page")
            except Exception as exc:
                logger.warning(f"Failed to apply stealth session: {exc}")

        # Capture DOM snapshot for reasoning
        if self.settings.enable_dom_distillation and self.dom_distiller:
            try:
                self._last_dom_snapshot = await self.dom_distiller.distill_page(
                    page,
                    self.dom_distillation_mode
                )
            except Exception as exc:
                logger.debug(f"DOM distillation skipped: {exc}")

        return page


    def _init_modules(self):
        """Initialize all enhanced modules based on config."""

        # DOM Distillation
        if DOM_DISTILLATION_AVAILABLE and self.settings.enable_dom_distillation:
            try:
                mode_map = {
                    "TEXT_ONLY": DistillationMode.TEXT_ONLY,
                    "INPUT_FIELDS": DistillationMode.INPUT_FIELDS,
                    "ALL_CONTENT": DistillationMode.ALL_CONTENT,
                    "HYBRID": DistillationMode.HYBRID,
                }
                self.dom_distiller = DOMDistillationEngine()
                self.dom_distillation_mode = mode_map.get(
                    self.settings.dom_mode,
                    DistillationMode.HYBRID
                )
                self.dom_max_tokens = self.settings.dom_max_tokens
                logger.info(
                    f"DOM distillation initialized (mode: {self.settings.dom_mode})"
                )
            except Exception as e:
                logger.error(f"Failed to initialize DOM distillation: {e}")
                self.dom_distiller = None
                self.dom_distillation_mode = None
        else:
            self.dom_distiller = None
            self.dom_distillation_mode = None

        # HTN Planning
        self._planning_max_depth = self.settings.planning_max_depth
        if PLANNING_AVAILABLE and self.settings.enable_planning:
            try:
                self.planner = PlanningAgent()
                logger.info("HTN planning initialized")
            except Exception as e:
                logger.error(f"Failed to initialize planning: {e}")
                self.planner = None
        else:
            self.planner = None

        # Reflexion
        if REFLEXION_AVAILABLE and self.settings.enable_reflexion:
            try:
                reflexion_config = {
                    "llm": {
                        "main_model": self.settings.model_name
                    },
                    "reflexion": {
                        "max_attempts": self.settings.reflexion_max_attempts,
                        "reflection_threshold": 0.6,
                    }
                }
                self.reflexion = ReflexionEngine(reflexion_config)
                logger.info("Reflexion initialized")
            except Exception as e:
                logger.error(f"Failed to initialize reflexion: {e}")
                self.reflexion = None
        else:
            self.reflexion = None

        # Enhanced Stealth
        if STEALTH_AVAILABLE and self.settings.enable_stealth:
            try:
                self.stealth = {
                    "session_factory": get_stealth_session,
                    "profile": self.settings.stealth_profile,
                    "fingerprint_manager": FingerprintManager(),
                    "proxy_manager": ProxyManager(proxies=[]),
                }
                logger.info(
                    f"Enhanced stealth toolkit initialized (profile: {self.settings.stealth_profile})"
                )
            except Exception as e:
                logger.error(f"Failed to initialize stealth: {e}")
                self.stealth = None
        else:
            self.stealth = None

        # Skill Library
        if SKILL_LIBRARY_AVAILABLE and self.settings.enable_skill_library:
            try:
                self.skill_library = SkillLibrary()
                logger.info("Skill library initialized")
            except Exception as e:
                logger.error(f"Failed to initialize skill library: {e}")
                self.skill_library = None
        else:
            self.skill_library = None

        # Visual Grounding
        if VISUAL_GROUNDING_AVAILABLE and self.settings.enable_visual_grounding:
            try:
                default_strategy = GroundingStrategy.HYBRID
                self.visual_grounding = VisualGroundingEngine(
                    default_strategy=default_strategy
                )
                # Store preferred parameters for downstream calls
                self.visual_grounding.confidence_threshold = self.settings.visual_confidence_threshold
                self.visual_grounding.fallback_enabled = self.settings.visual_fallback_enabled
                logger.info("Visual grounding initialized")
            except Exception as e:
                logger.error(f"Failed to initialize visual grounding: {e}")
                self.visual_grounding = None
        else:
            self.visual_grounding = None

        # Cascading Recovery
        if CASCADING_RECOVERY_AVAILABLE and self.settings.enable_cascading_recovery:
            try:
                self.recovery = CascadingRecoverySystem(
                    enable_learning=self.settings.recovery_learn_patterns
                )
                logger.info("Cascading recovery initialized")
            except Exception as e:
                logger.error(f"Failed to initialize recovery: {e}")
                self.recovery = None
        else:
            self.recovery = None

        # Memory Architecture
        if MEMORY_ARCHITECTURE_AVAILABLE and self.settings.enable_memory_architecture:
            try:
                working_capacity = max(10, self.settings.memory_working_size)
                self.memory_arch = MemoryArchitecture(
                    working_capacity=working_capacity,
                    auto_consolidate=True
                )
                logger.info("Memory architecture initialized")
            except Exception as e:
                logger.error(f"Failed to initialize memory architecture: {e}")
                self.memory_arch = None
        else:
            self.memory_arch = None

        # Workflows
        if WORKFLOWS_AVAILABLE and self.settings.enable_workflows:
            try:
                self.workflow_engine = WorkflowEngine()
                logger.info("Workflow engine initialized")
            except Exception as e:
                logger.error(f"Failed to initialize workflows: {e}")
                self.workflow_engine = None
        else:
            self.workflow_engine = None

        # Agent Network
        if AGENT_NETWORK_AVAILABLE and self.settings.enable_agent_network:
            try:
                self.agent_network = AgentNetwork()
                logger.info("Agent network initialized")
            except Exception as e:
                logger.error(f"Failed to initialize agent network: {e}")
                self.agent_network = None
        else:
            self.agent_network = None

    async def execute_enhanced(
        self,
        prompt: str,
        use_planning: bool = True,
        use_reflexion: bool = True,
        max_steps: Optional[int] = None
    ) -> ActionResult:
        """
        Execute task with full enhanced capabilities.

        Enhanced action loop:
        1. Plan task with HTN (if enabled)
        2. For each step:
           a. Perceive page state (DOM + Vision)
           b. Select skill from library
           c. Execute with stealth
           d. Recover on errors (cascading)
           e. Reflect on outcome (reflexion)
           f. Update memory
           g. Learn new skills
        3. Return result

        Args:
            prompt: User request
            use_planning: Whether to use HTN planning
            use_reflexion: Whether to use reflexion loop
            max_steps: Max steps (overrides config)

        Returns:
            ActionResult with success status and data
        """
        self.metrics["total_tasks"] += 1
        task_start = time.time()

        try:
            logger.info(f"Starting enhanced execution: {prompt}")

            # Step 1: Create plan if planning enabled
            plan = None
            if use_planning and self.planner:
                logger.info("Creating HTN plan...")
                plan = await self.planner.plan(
                    prompt,
                    max_depth=self._planning_max_depth
                )
                if plan:
                    self.metrics["plans_created"] += 1
                    logger.info(f"Plan created with {len(plan.steps)} steps")
                else:
                    logger.warning("Planning failed, falling back to direct execution")

            # Step 2: Execute with reflexion if enabled
            if use_reflexion and self.reflexion:
                logger.info("Executing with reflexion loop...")
                result = await self._execute_with_reflexion(prompt, plan, max_steps)
            else:
                logger.info("Executing without reflexion...")
                result = await self._execute_direct(prompt, plan, max_steps)

            # Update metrics
            if result.success:
                self.metrics["successful_tasks"] += 1
            else:
                self.metrics["failed_tasks"] += 1

            elapsed = time.time() - task_start
            logger.info(f"Task completed in {elapsed:.2f}s - Success: {result.success}")

            return result

        except Exception as e:
            logger.error(f"Enhanced execution failed: {e}", exc_info=True)
            self.metrics["failed_tasks"] += 1
            return ActionResult(
                success=False,
                error=f"Enhanced execution error: {str(e)}"
            )

    async def _get_smart_brain(self) -> Optional['SmartBrain']:
        """Lazily initialize SmartBrain for natural language processing."""
        if not self._smart_brain_enabled or not SMART_BRAIN_AVAILABLE:
            return None

        if self._smart_brain is None:
            try:
                # Get page from MCP client if available
                page = None
                if self._mcp_client:
                    try:
                        page = await self._mcp_client.get_page() if hasattr(self._mcp_client, 'get_page') else None
                    except Exception:
                        pass

                self._smart_brain = await SmartBrain.create(
                    mcp_client=self._mcp_client,
                    page=page,
                    config=self._base_config
                )
                logger.info("SmartBrain initialized for natural language routing")
            except Exception as e:
                logger.warning(f"Failed to initialize SmartBrain: {e}")
                self._smart_brain_enabled = False
                return None

        return self._smart_brain

    async def run_smart(self, user_input: str) -> ActionResult:
        """
        Intelligent natural language task runner.

        This is the primary entry point for natural language commands.
        It automatically:
        1. Detects task intent (web research, browser automation, etc.)
        2. Routes to appropriate handler (SmartBrain, enhanced execution, or direct)
        3. Uses optimal LLM (vision for planning, fast for execution)
        4. Records trace for ML training

        Args:
            user_input: Natural language task description

        Returns:
            ActionResult with success status and data
        """
        self.metrics["total_tasks"] += 1
        task_start = time.time()

        try:
            # Try SmartBrain first for intelligent routing
            smart_brain = await self._get_smart_brain()

            if smart_brain:
                logger.info(f"SmartBrain handling: {user_input[:100]}...")
                result = await smart_brain.run(user_input)

                # Convert SmartResult to ActionResult
                action_result = ActionResult(
                    success=result.success,
                    data={
                        "output": result.output,
                        "task_type": result.task_type.value if result.task_type else "unknown",
                        "trace_id": result.trace_id,
                        "steps_taken": result.steps_taken,
                    },
                    error=result.error
                )

                if result.success:
                    self.metrics["successful_tasks"] += 1
                else:
                    self.metrics["failed_tasks"] += 1

                elapsed = time.time() - task_start
                logger.info(f"SmartBrain task completed in {elapsed:.2f}s - Success: {result.success}")
                return action_result

            # Fallback to enhanced execution
            logger.info("SmartBrain not available, using enhanced execution")
            return await self.execute_enhanced(user_input)

        except Exception as e:
            logger.error(f"Smart execution failed: {e}", exc_info=True)
            self.metrics["failed_tasks"] += 1
            return ActionResult(
                success=False,
                error=f"Smart execution error: {str(e)}"
            )

    async def run(self, prompt: str) -> str:
        """
        Main entry point - auto-routes based on input.

        Override of base brain's run method to add SmartBrain routing.
        For natural language, uses SmartBrain. For direct commands, uses base.

        Args:
            prompt: User input (natural language or direct command)

        Returns:
            String response
        """
        # DIRECT PATTERNS: Fast-path for known patterns (Gmail, Maps, etc.)
        # This bypasses SmartBrain for simple navigation tasks
        try:
            if hasattr(self, '_try_direct_patterns'):
                direct_result = await self._try_direct_patterns(prompt)
                if direct_result:
                    return direct_result
        except Exception as e:
            logger.debug(f"Direct patterns check failed: {e}")

        # Try SmartBrain first for natural language
        if self._smart_brain_enabled and SMART_BRAIN_AVAILABLE:
            result = await self.run_smart(prompt)
            if result.success:
                output = result.data.get("output", "") if result.data else ""
                return output if output else "Task completed successfully"
            else:
                # Fall through to base brain on SmartBrain failure
                logger.info("SmartBrain failed, falling back to base brain")

        # Fallback to base brain
        return await super().run(prompt)

    async def _execute_with_reflexion(
        self,
        prompt: str,
        plan: Optional[Plan],
        max_steps: Optional[int]
    ) -> ActionResult:
        """Execute with reflexion self-improvement loop."""

        if not self.reflexion:
            return await self._execute_direct(prompt, plan, max_steps)

        attempt = 0
        best_result = None
        attempts_log: List[TaskAttempt] = []
        reflections: List[SelfReflection] = []
        current_prompt = prompt

        while attempt < self.settings.reflexion_max_attempts:
            attempt += 1
            logger.info(f"Reflexion attempt {attempt}/{self.settings.reflexion_max_attempts}")

            start_time = time.time()
            result = await self._execute_direct(current_prompt, plan, max_steps)
            duration = time.time() - start_time

            # Record attempt for reflection
            attempts_log.append(TaskAttempt(
                attempt_number=attempt,
                action="execute_plan" if plan else "direct_execute",
                observation=self._summarize_action_result(result),
                success=result.success,
                execution_time=duration,
                timestamp=datetime.now().isoformat(),
                tool_calls=[],
                errors=[result.error] if result.error else []
            ))

            if result.success:
                logger.info(f"Task succeeded on attempt {attempt}")
                return result

            if not best_result or (result.data and len(str(result.data)) > len(str(best_result.data))):
                best_result = result

            # Generate reflection feedback
            reflection = await self._generate_reflection(prompt, attempts_log, reflections)
            if reflection:
                reflections.append(reflection)
                self.metrics["total_reflections"] += 1
                logger.info(f"Reflection generated: {reflection.what_to_do_next}")
                current_prompt = self._apply_reflection_guidance(prompt, reflection)
            else:
                logger.warning("Reflexion module did not return feedback; reusing original prompt")
                current_prompt = prompt

            if attempt >= self.settings.reflexion_max_attempts:
                logger.warning("Max reflexion attempts reached, returning best result")
                return best_result or result

        return best_result or ActionResult(success=False, error="No successful execution")

    async def _execute_direct(
        self,
        prompt: str,
        plan: Optional[Plan],
        max_steps: Optional[int]
    ) -> ActionResult:
        """Execute task directly using base brain with enhancements."""

        # Prepare browser context with stealth + DOM snapshot
        await self._prepare_playwright_page()

        # If we have a plan, execute it step by step
        if plan and self.planner:
            return await self._execute_plan(plan, max_steps)

        # Otherwise, delegate to base executor
        result = await self._base_executor(prompt)

        # Capture post-action DOM snapshot for diffing
        await self._prepare_playwright_page()

        return result

    async def _generate_reflection(
        self,
        task_prompt: str,
        attempts_log: List[TaskAttempt],
        reflections: List[SelfReflection]
    ) -> Optional[SelfReflection]:
        """Generate a reflection using the Reflexion engine helper."""
        if not self.reflexion or not hasattr(self.reflexion, "reflection_generator"):
            return None

        try:
            return await self.reflexion.reflection_generator.generate_reflection(
                task_prompt=task_prompt,
                task_category="general",
                attempts=attempts_log,
                success=False,
                previous_reflections=reflections
            )
        except Exception as exc:
            logger.warning(f"Reflexion generation failed: {exc}")
            return None

    def _apply_reflection_guidance(self, prompt: str, reflection: SelfReflection) -> str:
        """Augment prompt with actionable reflection guidance."""
        guidance_parts = [
            "Self-reflection insight:",
            f"What happened: {reflection.what_happened}",
            f"Why it happened: {reflection.why_it_happened}",
            f"Next strategy: {reflection.what_to_do_next}",
        ]
        guidance = "\n".join(guidance_parts)
        return f"{prompt}\n\n{guidance}"

    def _summarize_action_result(self, result: ActionResult) -> str:
        """Create a compact textual summary for Reflexion attempts."""
        if result.success:
            payload = result.data if result.data is not None else "No data"
            return f"Success: {str(payload)[:500]}"

        error_msg = result.error or "Unknown error"
        data_snippet = ""
        if result.data:
            data_snippet = f" | Data: {str(result.data)[:200]}"
        return f"Failure: {error_msg}{data_snippet}"

    async def _execute_plan(
        self,
        plan: Plan,
        max_steps: Optional[int]
    ) -> ActionResult:
        """Execute a hierarchical plan step by step."""

        logger.info(f"Executing plan: {plan.goal}")
        results = []

        for step_id, step in plan.steps.items():
            logger.info(f"Executing step {step_id}: {step.description}")

            try:
                # Execute step (this will use enhanced capabilities)
                step_result = await self._execute_step(step)
                results.append(step_result)

                is_required = getattr(step, "required", True)
                if not step_result.success and is_required:
                    logger.error(f"Required step failed: {step.description}")
                    return ActionResult(
                        success=False,
                        error=f"Plan execution failed at step: {step.description}",
                        data={"completed_steps": results}
                    )

            except Exception as e:
                logger.error(f"Step execution error: {e}")
                is_required = getattr(step, "required", True)
                if is_required:
                    return ActionResult(
                        success=False,
                        error=f"Step error: {str(e)}",
                        data={"completed_steps": results}
                    )

        return ActionResult(
            success=True,
            data={"plan_results": results, "plan_id": plan.plan_id}
        )

    async def _execute_step(self, step: PlanStep) -> ActionResult:
        """Execute a single plan step with all enhancements."""

        self.metrics["total_steps"] += 1

        try:
            # Check if we have a skill for this step
            skill = None
            if self.skill_library:
                skills = await self.skill_library.retrieve_skills(step.description)
                if skills:
                    skill = skills[0]
                    logger.info(f"Using skill: {skill.name}")

            # Execute with base brain
            # The enhanced perception, action, and recovery happen automatically
            # through our overridden methods
            await self._prepare_playwright_page()
            result = await self._base_executor(step.description)
            await self._prepare_playwright_page()

            # Learn from successful execution
            if result.success and self.skill_library and self.settings.skill_auto_learn:
                await self._learn_skill_from_execution(step, result)

            return result

        except Exception as e:
            logger.error(f"Step execution failed: {e}")

            # Try cascading recovery
            if self.recovery:
                logger.info("Attempting cascading recovery...")
                recovery_context = RecoveryContext(
                    action="plan_step",
                    arguments={"step": step.to_dict()},
                    error=e if isinstance(e, Exception) else Exception(str(e)),
                    attempt_number=step.retry_count + 1,
                    page_url=None,
                    page_state=None,
                    checkpoint_data=None
                )

                async def retry_action(**kwargs):
                    """Retry the same plan step via base brain execution."""
                    return await self._base_executor(step.description)

                recovery_result = await self.recovery.attempt_recovery(
                    context=recovery_context,
                    page=None,
                    retry_action=retry_action
                )
                self.metrics["total_recoveries"] += 1

                if recovery_result.get("recovered"):
                    logger.info(
                        f"Recovery succeeded at level {recovery_result.get('level')}"
                    )
                    return ActionResult(
                        success=True,
                        data=recovery_result.get("result")
                    )
                if recovery_result.get("partial_results"):
                    return ActionResult(
                        success=False,
                        data=recovery_result.get("partial_results"),
                        error=recovery_result.get("message", "Partial recovery only")
                    )

            return ActionResult(success=False, error=str(e))

    async def _learn_skill_from_execution(self, step: PlanStep, result: ActionResult):
        """Extract and learn a new skill from successful execution."""

        try:
            if not self.skill_library:
                return

            # Extract skill from execution
            skill = await self.skill_library.extract_skill(
                task_description=step.description,
                execution_trace=result.data or {},
                success=True
            )

            if skill:
                self.metrics["skills_learned"] += 1
                logger.info(f"Learned new skill: {skill.name}")

        except Exception as e:
            logger.warning(f"Failed to learn skill: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive status of all modules."""

        status = {
            "brain": "enhanced",
            "version": "2.0.0",
            "timestamp": datetime.now().isoformat(),
            "modules": self.modules_available.copy(),
            "metrics": self.metrics.copy(),
            "config": self.settings.to_dict(),
        }

        # Add module-specific status
        if self.skill_library:
            status["skill_library"] = {
                "total_skills": len(self.skill_library.skills) if hasattr(self.skill_library, 'skills') else 0
            }

        if self.reflexion:
            status["reflexion"] = {
                "total_reflections": self.metrics["total_reflections"]
            }

        if self.planner:
            status["planner"] = {
                "total_plans": self.metrics["plans_created"]
            }

        if self.recovery:
            status["recovery"] = {
                "total_recoveries": self.metrics["total_recoveries"]
            }

        return status

    def print_status(self):
        """Print comprehensive status to console."""

        status = self.get_status()

        # Create status table
        table = Table(title="Eversale Enhanced Status", show_header=True, header_style="bold cyan")
        table.add_column("Module", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Details", style="dim")

        # Add rows
        for module, enabled in status["modules"].items():
            status_str = "✓ Enabled" if enabled else "✗ Disabled"
            style = "green" if enabled else "red"

            details = ""
            if module == "skill_library" and enabled:
                details = f"{status.get('skill_library', {}).get('total_skills', 0)} skills"
            elif module == "planning" and enabled:
                details = f"{status.get('planner', {}).get('total_plans', 0)} plans"
            elif module == "reflexion" and enabled:
                details = f"{status.get('reflexion', {}).get('total_reflections', 0)} reflections"
            elif module == "cascading_recovery" and enabled:
                details = f"{status.get('recovery', {}).get('total_recoveries', 0)} recoveries"

            table.add_row(module, f"[{style}]{status_str}[/{style}]", details)

        console.print(table)

        # Print metrics
        metrics_table = Table(title="Performance Metrics", show_header=True, header_style="bold yellow")
        metrics_table.add_column("Metric", style="yellow")
        metrics_table.add_column("Value", style="white")

        for key, value in status["metrics"].items():
            if key != "start_time":
                metrics_table.add_row(key.replace("_", " ").title(), str(value))

        console.print(metrics_table)


# ==============================================================================
# FACTORY FUNCTIONS
# ==============================================================================

def create_enhanced_brain(
    config: Optional[EversaleConfig] = None,
    mcp_client: Optional[Any] = None,
    awareness_hub: Optional[Any] = None,
    **kwargs
) -> EversaleBrainEnhanced:
    """
    Create fully-featured enhanced brain with all capabilities.

    This is the recommended brain for production use. Includes:
    - HTN planning for complex tasks
    - Reflexion for self-improvement
    - Enhanced stealth for anti-bot
    - Skill library for learning
    - Visual grounding for element finding
    - Cascading recovery for resilience
    - Advanced memory architecture

    Args:
        config: Configuration object (uses defaults if None)
        mcp_client: MCP client for Playwright
        awareness_hub: Awareness hub for monitoring
        **kwargs: Additional args for base brain

    Returns:
        EversaleBrainEnhanced instance
    """
    if not config:
        config = EversaleConfig()
        # Enable all features
        config.enable_dom_distillation = True
        config.enable_planning = True
        config.enable_reflexion = True
        config.enable_stealth = True
        config.enable_skill_library = True
        config.enable_visual_grounding = True
        config.enable_cascading_recovery = True
        config.enable_memory_architecture = True
        config.enable_workflows = True

    return EversaleBrainEnhanced(
        config=config,
        mcp_client=mcp_client,
        awareness_hub=awareness_hub,
        **kwargs
    )


def create_minimal_brain(
    config: Optional[EversaleConfig] = None,
    mcp_client: Optional[Any] = None,
    awareness_hub: Optional[Any] = None,
    **kwargs
) -> EversaleBrainEnhanced:
    """
    Create minimal brain with only essential features.

    Good for simple tasks or resource-constrained environments.
    Includes only:
    - Basic DOM understanding
    - Basic recovery
    - No planning, reflexion, or skill learning

    Args:
        config: Configuration object
        mcp_client: MCP client
        awareness_hub: Awareness hub
        **kwargs: Additional args

    Returns:
        EversaleBrainEnhanced with minimal features
    """
    if not config:
        config = EversaleConfig()

    # Disable advanced features
    config.enable_planning = False
    config.enable_reflexion = False
    config.enable_skill_library = False
    config.enable_memory_architecture = False
    config.enable_agent_network = False

    # Keep essential features
    config.enable_dom_distillation = True
    config.enable_cascading_recovery = True
    config.enable_visual_grounding = True

    return EversaleBrainEnhanced(
        config=config,
        mcp_client=mcp_client,
        awareness_hub=awareness_hub,
        **kwargs
    )


def create_stealth_brain(
    config: Optional[EversaleConfig] = None,
    mcp_client: Optional[Any] = None,
    awareness_hub: Optional[Any] = None,
    **kwargs
) -> EversaleBrainEnhanced:
    """
    Create brain optimized for anti-bot evasion.

    Use this when working with sites that have strong bot detection
    (LinkedIn, Facebook, Amazon, etc.).

    Features:
    - Aggressive stealth profile
    - Enhanced fingerprinting
    - Behavioral mimicry
    - Request pattern normalization
    - All other features enabled

    Args:
        config: Configuration object
        mcp_client: MCP client
        awareness_hub: Awareness hub
        **kwargs: Additional args

    Returns:
        EversaleBrainEnhanced with aggressive stealth
    """
    if not config:
        config = EversaleConfig()

    # Aggressive stealth settings
    config.enable_stealth = True
    config.stealth_profile = "AGGRESSIVE"
    config.stealth_rotate_fingerprint = True

    # Enable all other features
    config.enable_dom_distillation = True
    config.enable_planning = True
    config.enable_reflexion = True
    config.enable_skill_library = True
    config.enable_visual_grounding = True
    config.enable_cascading_recovery = True
    config.enable_memory_architecture = True

    return EversaleBrainEnhanced(
        config=config,
        mcp_client=mcp_client,
        awareness_hub=awareness_hub,
        **kwargs
    )


def create_enterprise_brain(
    config: Optional[EversaleConfig] = None,
    mcp_client: Optional[Any] = None,
    awareness_hub: Optional[Any] = None,
    **kwargs
) -> EversaleBrainEnhanced:
    """
    Create enterprise-grade brain with full monitoring and compliance.

    Recommended for production deployments where monitoring,
    logging, and reliability are critical.

    Features:
    - All capabilities enabled
    - Enhanced telemetry
    - Decision logging
    - Health monitoring
    - Agent network for coordination

    Args:
        config: Configuration object
        mcp_client: MCP client
        awareness_hub: Awareness hub
        **kwargs: Additional args

    Returns:
        EversaleBrainEnhanced for enterprise use
    """
    if not config:
        config = EversaleConfig()

    # Enable all features
    config.enable_dom_distillation = True
    config.enable_planning = True
    config.enable_reflexion = True
    config.enable_stealth = True
    config.enable_skill_library = True
    config.enable_visual_grounding = True
    config.enable_cascading_recovery = True
    config.enable_memory_architecture = True
    config.enable_workflows = True
    config.enable_agent_network = True

    # Enhanced monitoring
    config.telemetry_enabled = True
    config.health_check_interval = 30  # More frequent health checks
    config.log_level = "DEBUG"
    config.log_decisions = True

    # Increased reliability
    config.recovery_max_level = 10
    config.recovery_learn_patterns = True
    config.reflexion_max_attempts = 5

    return EversaleBrainEnhanced(
        config=config,
        mcp_client=mcp_client,
        awareness_hub=awareness_hub,
        **kwargs
    )


def create_smart_brain(
    config: Optional[EversaleConfig] = None,
    mcp_client: Optional[Any] = None,
    awareness_hub: Optional[Any] = None,
    **kwargs
) -> EversaleBrainEnhanced:
    """
    Create brain optimized for natural language understanding.

    Uses SmartBrain as the primary router for all tasks, providing:
    - Automatic intent detection from natural language
    - Intelligent task routing (web research, browser automation, etc.)
    - Dual-LLM architecture (vision plans, fast executes)
    - Trace collection for ML training
    - Self-healing browser execution

    This is the recommended brain for conversational interfaces
    and natural language task execution.

    Args:
        config: Configuration object
        mcp_client: MCP client for browser automation
        awareness_hub: Awareness hub for monitoring
        **kwargs: Additional args

    Returns:
        EversaleBrainEnhanced with SmartBrain routing enabled
    """
    if not config:
        config = EversaleConfig()

    # Enable SmartBrain-critical features
    config.enable_dom_distillation = True
    config.enable_visual_grounding = True
    config.enable_cascading_recovery = True

    # Enable learning features
    config.enable_skill_library = True
    config.enable_memory_architecture = True

    # Disable heavyweight planning (SmartBrain handles routing)
    config.enable_planning = False
    config.enable_reflexion = False  # SmartBrain has self-healing

    # Enable workflows and network for complex tasks
    config.enable_workflows = True
    config.enable_agent_network = False  # Optional

    return EversaleBrainEnhanced(
        config=config,
        mcp_client=mcp_client,
        awareness_hub=awareness_hub,
        **kwargs
    )


async def create_smart_brain_async(
    mcp_client: Optional[Any] = None,
    page: Optional[Any] = None,
    config: Optional[Dict] = None,
) -> 'SmartBrain':
    """
    Create a standalone SmartBrain instance for direct use.

    This bypasses EversaleBrainEnhanced and creates SmartBrain directly.
    Useful for lightweight deployments or testing.

    Args:
        mcp_client: MCP client for browser automation
        page: Playwright page (if available)
        config: Configuration dictionary

    Returns:
        SmartBrain instance ready for use
    """
    if not SMART_BRAIN_AVAILABLE:
        raise RuntimeError("SmartBrain module not available")

    return await SmartBrain.create(
        mcp_client=mcp_client,
        page=page,
        config=config
    )


# ==============================================================================
# HEALTH MONITORING
# ==============================================================================

class HealthMonitor:
    """Monitors health of all modules in enhanced brain."""

    def __init__(self, brain: EversaleBrainEnhanced):
        self.brain = brain
        self.last_check = None
        self.health_history = []

    async def check_health(self) -> Dict[str, Any]:
        """Run comprehensive health check on all modules."""

        health = {
            "timestamp": datetime.now().isoformat(),
            "overall_status": "healthy",
            "modules": {},
            "metrics": self.brain.metrics.copy(),
        }

        # Check each module
        for module_name, enabled in self.brain.modules_available.items():
            if not enabled:
                health["modules"][module_name] = {"status": "disabled"}
                continue

            try:
                module_health = await self._check_module(module_name)
                health["modules"][module_name] = module_health

                if module_health.get("status") == "unhealthy":
                    health["overall_status"] = "degraded"

            except Exception as e:
                logger.error(f"Health check failed for {module_name}: {e}")
                health["modules"][module_name] = {"status": "error", "error": str(e)}
                health["overall_status"] = "degraded"

        self.last_check = health
        self.health_history.append(health)

        # Keep only last 100 checks
        if len(self.health_history) > 100:
            self.health_history = self.health_history[-100:]

        return health

    async def _check_module(self, module_name: str) -> Dict[str, Any]:
        """Check health of a specific module."""

        status = {"status": "healthy"}

        try:
            # Module-specific health checks
            if module_name == "skill_library" and self.brain.skill_library:
                skills = self.brain.skill_library.skills if hasattr(self.brain.skill_library, 'skills') else []
                status["total_skills"] = len(skills)
                status["status"] = "healthy" if len(skills) > 0 else "degraded"

            elif module_name == "reflexion" and self.brain.reflexion:
                status["total_reflections"] = self.brain.metrics.get("total_reflections", 0)

            elif module_name == "planning" and self.brain.planner:
                status["total_plans"] = self.brain.metrics.get("plans_created", 0)

            elif module_name == "cascading_recovery" and self.brain.recovery:
                status["total_recoveries"] = self.brain.metrics.get("total_recoveries", 0)

            elif module_name == "memory_architecture" and self.brain.memory_arch:
                # Check memory usage
                if hasattr(self.brain.memory_arch, 'working_memory'):
                    wm = self.brain.memory_arch.working_memory
                    status["working_memory_size"] = len(wm.memories) if hasattr(wm, 'memories') else 0

        except Exception as e:
            status["status"] = "error"
            status["error"] = str(e)

        return status

    def print_health(self):
        """Print health status to console."""

        if not self.last_check:
            console.print("[yellow]No health check performed yet[/yellow]")
            return

        health = self.last_check

        # Overall status
        status_color = {
            "healthy": "green",
            "degraded": "yellow",
            "unhealthy": "red",
        }.get(health["overall_status"], "white")

        console.print(Panel(
            f"[{status_color}]{health['overall_status'].upper()}[/{status_color}]",
            title="Overall Health",
            border_style=status_color
        ))

        # Module health
        table = Table(title="Module Health", show_header=True, header_style="bold cyan")
        table.add_column("Module", style="cyan")
        table.add_column("Status", style="white")
        table.add_column("Details", style="dim")

        for module, info in health["modules"].items():
            status = info.get("status", "unknown")
            color = {
                "healthy": "green",
                "degraded": "yellow",
                "unhealthy": "red",
                "disabled": "dim",
                "error": "red"
            }.get(status, "white")

            details = []
            for key, value in info.items():
                if key != "status" and key != "error":
                    details.append(f"{key}: {value}")

            details_str = ", ".join(details) if details else ""
            if info.get("error"):
                details_str = f"Error: {info['error']}"

            table.add_row(
                module,
                f"[{color}]{status}[/{color}]",
                details_str
            )

        console.print(table)


# ==============================================================================
# INITIALIZATION HELPERS
# ==============================================================================

async def initialize_enhanced_system(
    config_path: Optional[Path] = None,
    mcp_client: Optional[Any] = None,
    awareness_hub: Optional[Any] = None
) -> Tuple[EversaleBrainEnhanced, HealthMonitor]:
    """
    Initialize complete enhanced system with health monitoring.

    This is the recommended way to start Eversale Enhanced.

    Args:
        config_path: Path to config file (uses defaults if None)
        mcp_client: MCP client for Playwright
        awareness_hub: Awareness hub for monitoring

    Returns:
        Tuple of (brain, health_monitor)
    """
    # Load config
    if config_path and config_path.exists():
        config = EversaleConfig.from_file(config_path)
        logger.info(f"Loaded config from {config_path}")
    else:
        config = EversaleConfig()
        logger.info("Using default config")

    # Create brain
    brain = create_enhanced_brain(
        config=config,
        mcp_client=mcp_client,
        awareness_hub=awareness_hub
    )

    # Create health monitor
    monitor = HealthMonitor(brain)

    # Run initial health check
    await monitor.check_health()

    logger.info("Enhanced system initialized successfully")

    return brain, monitor


def get_module_status() -> Dict[str, bool]:
    """
    Get availability status of all modules.

    Useful for debugging and diagnostics.

    Returns:
        Dictionary of module availability
    """
    return {
        "base_brain": BASE_BRAIN_AVAILABLE,
        "dom_distillation": DOM_DISTILLATION_AVAILABLE,
        "planning": PLANNING_AVAILABLE,
        "reflexion": REFLEXION_AVAILABLE,
        "stealth": STEALTH_AVAILABLE,
        "skill_library": SKILL_LIBRARY_AVAILABLE,
        "visual_grounding": VISUAL_GROUNDING_AVAILABLE,
        "cascading_recovery": CASCADING_RECOVERY_AVAILABLE,
        "memory_architecture": MEMORY_ARCHITECTURE_AVAILABLE,
        "workflows": WORKFLOWS_AVAILABLE,
        "agent_network": AGENT_NETWORK_AVAILABLE,
        # LocalLLaMA architecture components
        "smart_brain": SMART_BRAIN_AVAILABLE,
        "dual_llm": DUAL_LLM_AVAILABLE,
        "web_daemon": WEB_DAEMON_AVAILABLE,
        "worker_loop": WORKER_LOOP_AVAILABLE,
        "tool_wrappers": TOOL_WRAPPERS_AVAILABLE,
        "compressed_dom": COMPRESSED_DOM_AVAILABLE,
        "browser_tool_schemas": BROWSER_TOOL_SCHEMAS_AVAILABLE,
    }


def print_module_status():
    """Print module availability status to console."""

    status = get_module_status()

    table = Table(title="Eversale Enhanced - Module Availability", show_header=True)
    table.add_column("Module", style="cyan")
    table.add_column("Available", style="white")
    table.add_column("Status", style="dim")

    for module, available in status.items():
        color = "green" if available else "red"
        status_str = "✓ Available" if available else "✗ Not Available"

        table.add_row(
            module,
            f"[{color}]{available}[/{color}]",
            status_str
        )

    console.print(table)


# ==============================================================================
# MAIN (for testing)
# ==============================================================================

async def main():
    """Test the enhanced brain system."""

    console.print(Panel(
        "[bold cyan]Eversale Enhanced - Unified Integration Layer[/bold cyan]\n"
        "Testing all modules and capabilities",
        border_style="cyan"
    ))

    # Print module status
    print_module_status()

    # Initialize system
    console.print("\n[yellow]Initializing enhanced system...[/yellow]")
    brain, monitor = await initialize_enhanced_system()

    # Print status
    console.print("\n[yellow]Brain Status:[/yellow]")
    brain.print_status()

    # Check health
    console.print("\n[yellow]Running health check...[/yellow]")
    await monitor.check_health()
    monitor.print_health()

    # Test execution (without actual MCP client for now)
    console.print("\n[yellow]Testing execution (dry run)...[/yellow]")
    console.print("[dim]Skipping actual execution (requires MCP client)[/dim]")

    console.print("\n[green]✓ Enhanced system test complete![/green]")


if __name__ == "__main__":
    asyncio.run(main())
