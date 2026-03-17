"""
Complexity Detector - Identifies tasks requiring HTN planning.

Determines if a task is complex enough to warrant hierarchical planning
via the planning_agent instead of direct execution.

Use HTN planning for:
- Multi-step tasks across multiple URLs
- Multi-platform workflows (LinkedIn + Email + CRM)
- Tasks requiring complex coordination
- Tasks with many dependencies and branches

Skip HTN planning for:
- Simple single-action tasks
- Single-goal prompts with clear templates
- Tasks better handled by goal sequencer (sequential goals)
"""

import re
from typing import Optional, Dict
from loguru import logger


def is_complex_task(prompt: str, config: Optional[Dict] = None) -> bool:
    """
    Detect if a task needs HTN (Hierarchical Task Network) planning.

    Args:
        prompt: User's task request
        config: Optional configuration dict

    Returns:
        True if task should use HTN planning_agent, False otherwise

    Examples of complex tasks:
        - "Research 10 companies, extract contacts, and upload to HubSpot"
        - "Monitor LinkedIn for new posts, extract leads, send emails via Gmail"
        - "Find competitors on Product Hunt, scrape their websites, compile report"
        - "Automate workflow: search Google Maps, extract business info, validate emails"

    Examples of simple tasks (skip planning):
        - "Go to gmail.com and read my inbox" (single URL, template match)
        - "Search Google for Python tutorials" (single action)
        - "Screenshot this page" (trivial)
        - "Do X then Y then Z" (goal sequencer handles this)
    """
    config = config or {}
    prompt_lower = prompt.lower()

    # Check if planning is disabled in config
    if not config.get("planning", {}).get("enabled", True):
        return False

    # Multi-platform indicators (LinkedIn + Email, Google + CRM, etc.)
    platforms = [
        'linkedin', 'gmail', 'email', 'hubspot', 'salesforce',
        'google maps', 'facebook', 'twitter', 'instagram',
        'product hunt', 'crm', 'slack', 'outlook'
    ]
    platform_count = sum(1 for p in platforms if p in prompt_lower)
    if platform_count >= 2:
        logger.info(f"[COMPLEXITY] Multi-platform task detected ({platform_count} platforms)")
        return True

    # Multiple URL indicators
    multi_url_patterns = [
        'multiple sites', 'several sites', 'multiple pages',
        'multiple urls', 'visit all', 'visit each',
        'across sites', 'different sites', 'various sites'
    ]
    if any(pattern in prompt_lower for pattern in multi_url_patterns):
        logger.info("[COMPLEXITY] Multiple URL task detected")
        return True

    # Complex workflow indicators (research + action + reporting)
    workflow_phases = 0
    if any(kw in prompt_lower for kw in ['research', 'find', 'search for', 'look up', 'discover']):
        workflow_phases += 1
    if any(kw in prompt_lower for kw in ['extract', 'scrape', 'collect', 'gather', 'compile']):
        workflow_phases += 1
    if any(kw in prompt_lower for kw in ['send', 'email', 'upload', 'save', 'export', 'report']):
        workflow_phases += 1

    if workflow_phases >= 2:
        logger.info(f"[COMPLEXITY] Multi-phase workflow detected ({workflow_phases} phases)")
        return True

    # Automation/workflow keywords
    automation_keywords = [
        'automate workflow', 'automation', 'pipeline',
        'multi-step', 'complex task', 'orchestrate',
        'coordinate', 'integrate with', 'sync with'
    ]
    if any(kw in prompt_lower for kw in automation_keywords):
        logger.info("[COMPLEXITY] Automation workflow detected")
        return True

    # Large batch operations
    batch_indicators = [
        'batch', 'bulk', 'all', 'every', 'each',
        'comprehensive', 'exhaustive', 'complete list'
    ]
    batch_count = sum(1 for kw in batch_indicators if kw in prompt_lower)

    # Check for numeric quantities
    import re
    numbers = re.findall(r'\b(\d+)\b', prompt_lower)
    has_large_quantity = any(int(n) >= 10 for n in numbers if n.isdigit())

    if batch_count >= 2 or (batch_count >= 1 and has_large_quantity):
        logger.info("[COMPLEXITY] Large batch operation detected")
        return True

    # Dependency/conditional logic
    conditional_keywords = [
        'if', 'when', 'unless', 'depending on', 'based on',
        'fallback', 'otherwise', 'alternative', 'or else'
    ]
    if any(kw in prompt_lower for kw in conditional_keywords):
        logger.info("[COMPLEXITY] Conditional logic detected")
        return True

    # Parallel execution opportunities
    parallel_keywords = [
        'in parallel', 'simultaneously', 'at the same time',
        'concurrently', 'async', 'background'
    ]
    if any(kw in prompt_lower for kw in parallel_keywords):
        logger.info("[COMPLEXITY] Parallel execution detected")
        return True

    # Skip planning for tasks better handled by other systems
    # Goal sequencer handles "do X then Y then Z"
    if ' then ' in prompt_lower and prompt_lower.count(' then ') >= 2:
        logger.debug("[COMPLEXITY] Sequential goals detected - goal sequencer should handle")
        return False

    # Goal sequencer handles period/newline-separated multi-goal prompts
    # Like "Go to X. Go to Y. Go to Z." or "Go to X\nGo to Y"
    action_verbs = ['go to', 'navigate to', 'visit', 'open', 'search', 'find', 'check', 'output']
    action_count = sum(1 for verb in action_verbs if verb in prompt_lower)
    sentence_count = len(re.findall(r'[.!]\s*(?:go|navigate|visit|open|search|find|check|output)', prompt_lower, re.I))
    newline_goals = len(re.findall(r'\n\s*(?:go|navigate|visit|open|search|find|check|output)', prompt_lower, re.I))
    if action_count >= 3 or sentence_count >= 2 or newline_goals >= 2:
        logger.debug(f"[COMPLEXITY] Multi-goal prompt detected (actions={action_count}, sentences={sentence_count}, newlines={newline_goals}) - goal sequencer should handle")
        return False

    # Templates handle specific patterns (Gmail, Maps, etc.)
    template_patterns = [
        'go to gmail', 'check gmail', 'read gmail',
        'search google maps', 'find on maps',
        'screenshot', 'describe page'
    ]
    if any(pattern in prompt_lower for pattern in template_patterns):
        logger.debug("[COMPLEXITY] Template pattern detected - skip planning")
        return False

    # Default: not complex
    logger.debug("[COMPLEXITY] Task is not complex - skip HTN planning")
    return False


def get_complexity_score(prompt: str) -> float:
    """
    Calculate a complexity score from 0.0 (trivial) to 1.0 (very complex).

    This can be used to select planning depth or resource allocation.

    Args:
        prompt: User's task request

    Returns:
        Complexity score (0.0-1.0)
    """
    prompt_lower = prompt.lower()
    score = 0.0

    # Platform diversity (0-0.3)
    platforms = [
        'linkedin', 'gmail', 'email', 'hubspot', 'salesforce',
        'google maps', 'facebook', 'twitter', 'instagram',
        'product hunt', 'crm', 'slack', 'outlook'
    ]
    platform_count = sum(1 for p in platforms if p in prompt_lower)
    score += min(platform_count * 0.15, 0.3)

    # Workflow phases (0-0.3)
    phases = 0
    if any(kw in prompt_lower for kw in ['research', 'find', 'search for', 'look up']):
        phases += 1
    if any(kw in prompt_lower for kw in ['extract', 'scrape', 'collect', 'gather']):
        phases += 1
    if any(kw in prompt_lower for kw in ['send', 'email', 'upload', 'save', 'export']):
        phases += 1
    score += min(phases * 0.1, 0.3)

    # Batch size (0-0.2)
    import re
    numbers = re.findall(r'\b(\d+)\b', prompt_lower)
    if numbers:
        max_num = max(int(n) for n in numbers if n.isdigit() and int(n) < 1000)
        if max_num >= 100:
            score += 0.2
        elif max_num >= 50:
            score += 0.15
        elif max_num >= 10:
            score += 0.1

    # Conditional logic (0-0.1)
    if any(kw in prompt_lower for kw in ['if', 'when', 'unless', 'depending on']):
        score += 0.1

    # Parallel execution (0-0.1)
    if any(kw in prompt_lower for kw in ['in parallel', 'simultaneously', 'concurrently']):
        score += 0.1

    return min(score, 1.0)
