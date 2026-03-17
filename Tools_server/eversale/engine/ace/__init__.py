"""
ACE (Agentic Context Engineering) - Lightweight playbook-based learning for SDR-1
Enables the agent to learn from successes and failures without fine-tuning.
"""

from .playbook import Playbook, Strategy
from .reflector import Reflector
from .injector import StrategyInjector

__all__ = ['Playbook', 'Strategy', 'Reflector', 'StrategyInjector']
