"""
SDR-1 Self-Play Training System

Like AlphaGo's self-play, but for web automation:
- Generates diverse tasks
- Executes and learns from outcomes
- Updates strategy playbook
- Continuously improves
"""

from .task_generator import TaskGenerator, TrainingTask
from .self_play_engine import SelfPlayEngine, TrainingSession, TaskResult

__all__ = [
    'TaskGenerator',
    'TrainingTask',
    'SelfPlayEngine',
    'TrainingSession',
    'TaskResult'
]
