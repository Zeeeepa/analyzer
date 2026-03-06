"""
Eversale Agent - Your AI Employee

Desktop agent that runs research, sales, admin, customer ops,
spreadsheets, logistics, and more. Runs forever until you cancel.
"""

# =============================================================================
# LOGGING CONFIGURATION - Must be FIRST before any other imports
# =============================================================================
import os
import sys

# Only configure if not already done
if not os.environ.get('EVERSALE_LOGGING_CONFIGURED'):
    _DEBUG_MODE = '--debug' in sys.argv or '-d' in sys.argv or os.environ.get('EVERSALE_DEBUG', '').lower() in ('1', 'true')

    from loguru import logger
    logger.remove()  # Remove default stderr handler

    # Create logs directory
    from pathlib import Path
    _log_dir = Path(os.environ.get('EVERSALE_HOME', os.path.expanduser('~/.eversale'))) / 'logs'
    _log_dir.mkdir(parents=True, exist_ok=True)

    # File logging always enabled
    logger.add(str(_log_dir / 'eversale.log'), rotation="10 MB", level="DEBUG")

    # stderr logging only in debug mode - production output stays clean
    if _DEBUG_MODE:
        logger.add(sys.stderr, level="DEBUG", format="<dim>{time:HH:mm:ss}</dim> | {message}")

    # Signal to submodules not to add handlers
    os.environ['EVERSALE_LOGGING_CONFIGURED'] = '1'
# =============================================================================

# Legacy brain import - optional (deprecated modules may be deleted)
try:
    from .brain_enhanced_v2 import EnhancedBrain, create_enhanced_brain
except ImportError as e:
    EnhancedBrain = None
    create_enhanced_brain = None
    import warnings
    warnings.warn(f"EnhancedBrain not available (use SimpleAgent instead): {e}")

from .mcp_client import MCPClient
from .scheduler import TaskScheduler
from .health_check import HealthWriter, start_health_monitoring, stop_health_monitoring, is_agent_alive
from .output_path import get_output_folder, save_csv, save_output
from .ui import EversaleUI, ui
from .output_format_handler import detect_output_format, format_output

# A11y-first browser automation (v2.9+)
from .a11y_browser import A11yBrowser, Snapshot, ActionResult, ElementRef, create_browser
from .simple_agent import SimpleAgent, AgentResult, run_task
from . import a11y_config

# HTN Planning for complex multi-step tasks
try:
    from .planning_agent import PlanningAgent, quick_plan_and_execute, Plan, PlanStep
    from .complexity_detector import is_complex_task, get_complexity_score
except ImportError as e:
    PlanningAgent = None
    quick_plan_and_execute = None
    Plan = None
    PlanStep = None
    is_complex_task = None
    get_complexity_score = None
    import warnings
    warnings.warn(f"HTN Planning not available: {e}")

# UI-TARS patterns for enhanced reliability
try:
    from .ui_tars_integration import UITarsEnhancer, enhance_brain_config
    from .ui_tars_patterns import RetryConfig, ConversationContext, retry_with_timeout
except ImportError as e:
    UITarsEnhancer = None
    enhance_brain_config = None
    RetryConfig = None
    ConversationContext = None
    retry_with_timeout = None
    import warnings
    warnings.warn(f"UI-TARS patterns not available: {e}")

# History pruning for token management
try:
    from .history_pruner import HistoryPruner, prune_screenshots_from_history
except ImportError as e:
    HistoryPruner = None
    prune_screenshots_from_history = None
    import warnings
    warnings.warn(f"History pruning not available: {e}")

# AGI-like reasoning for smarter execution
try:
    from .agi_reasoning import (
        AGIReasoning, get_agi_reasoning, SelfHealingLoop,
        reason_before_action, verify_action_success, get_smart_correction
    )
except ImportError as e:
    AGIReasoning = None
    get_agi_reasoning = None
    SelfHealingLoop = None
    reason_before_action = None
    verify_action_success = None
    get_smart_correction = None
    import warnings
    warnings.warn(f"AGI reasoning not available: {e}")

# AGI Core - Full Cognitive Architecture
try:
    from .agi_core import (
        CognitiveEngine, get_cognitive_engine, think_before_act,
        get_historical_success_rate, WorkingMemory, EpisodicMemory,
        CognitiveState
    )
except ImportError as e:
    CognitiveEngine = None
    get_cognitive_engine = None
    think_before_act = None
    get_historical_success_rate = None
    WorkingMemory = None
    EpisodicMemory = None
    CognitiveState = None
    import warnings
    warnings.warn(f"AGI Core not available: {e}")

__all__ = [
    "EnhancedBrain",
    "create_enhanced_brain",
    "MCPClient",
    "TaskScheduler",
    "HealthWriter",
    "start_health_monitoring",
    "stop_health_monitoring",
    "is_agent_alive",
    "get_output_folder",
    "save_csv",
    "save_output",
    "EversaleUI",
    "ui",
    "detect_output_format",
    "format_output",
    # A11y browser automation
    "A11yBrowser",
    "Snapshot",
    "ActionResult",
    "ElementRef",
    "create_browser",
    "SimpleAgent",
    "AgentResult",
    "run_task",
    "a11y_config",
    # HTN Planning
    "PlanningAgent",
    "quick_plan_and_execute",
    "Plan",
    "PlanStep",
    "is_complex_task",
    "get_complexity_score",
    # UI-TARS patterns
    "UITarsEnhancer",
    "enhance_brain_config",
    "RetryConfig",
    "ConversationContext",
    "retry_with_timeout",
    # History pruning
    "HistoryPruner",
    "prune_screenshots_from_history",
    # AGI reasoning
    "AGIReasoning",
    "get_agi_reasoning",
    "SelfHealingLoop",
    "reason_before_action",
    "verify_action_success",
    "get_smart_correction",
    # AGI Core - Cognitive Architecture
    "CognitiveEngine",
    "get_cognitive_engine",
    "think_before_act",
    "get_historical_success_rate",
    "WorkingMemory",
    "EpisodicMemory",
    "CognitiveState",
]
