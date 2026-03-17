"""
Tool Name Corrector Module

Validates and corrects tool calls, fixing hallucinated or wrong tool names.
Extracted from brain_enhanced_v2.py to reduce file size.
"""

from typing import Dict, List, Set, Optional
from loguru import logger


# Map of common hallucinated/wrong tool names to correct ones
TOOL_CORRECTIONS = {
    # Navigation variations
    'navigate': 'playwright_navigate',
    'goto': 'playwright_navigate',
    'go_to': 'playwright_navigate',
    'browser_navigate': 'playwright_navigate',
    'open_url': 'playwright_navigate',
    'visit': 'playwright_navigate',
    'browse': 'playwright_navigate',
    # Text/content extraction
    'get_text': 'playwright_get_text',
    'get_element_text': 'playwright_get_text',
    'extract_text': 'playwright_get_text',
    'read_page': 'playwright_get_markdown',
    'get_page': 'playwright_get_markdown',
    'get_content': 'playwright_get_markdown',
    'page_content': 'playwright_get_markdown',
    # Snapshot variations
    'snapshot': 'playwright_snapshot',
    'get_snapshot': 'playwright_snapshot',
    'page_snapshot': 'playwright_snapshot',
    'accessibility': 'playwright_snapshot',
    # Click variations
    'click': 'playwright_click',
    'click_element': 'playwright_click',
    'press': 'playwright_click',
    # Fill variations
    'fill': 'playwright_fill',
    'type': 'playwright_fill',
    'input': 'playwright_fill',
    'enter_text': 'playwright_fill',
    # Screenshot
    'screenshot': 'playwright_screenshot',
    'take_screenshot': 'playwright_screenshot',
    'capture': 'playwright_screenshot',
    # Extract variations
    'extract': 'playwright_llm_extract',
    'llm_extract': 'playwright_llm_extract',
    'extract_data': 'playwright_llm_extract',
    'scrape': 'playwright_llm_extract',
    # Contacts
    'find_contacts': 'playwright_find_contacts',
    'get_contacts': 'playwright_find_contacts',
    'extract_contacts': 'playwright_extract_entities',
    'get_emails': 'playwright_extract_entities',
}


def validate_tool_calls(
    tool_calls: List[Dict],
    available_tools: Optional[Set[str]] = None
) -> List[Dict]:
    """
    Validate and correct tool calls - fix hallucinated tool names.

    Args:
        tool_calls: List of tool call dictionaries
        available_tools: Set of available tool names (optional)

    Returns:
        List of corrected tool calls (invalid ones removed)
    """
    if not tool_calls:
        return tool_calls

    available = available_tools or set()
    corrected = []

    for tc in tool_calls:
        func = tc.get('function', {})
        name = func.get('name', '')

        # Check if tool exists
        if available and name not in available:
            # Try to correct the name
            corrected_name = TOOL_CORRECTIONS.get(name.lower())
            if corrected_name and (not available or corrected_name in available):
                logger.info(f"Corrected tool name: {name} -> {corrected_name}")
                func['name'] = corrected_name
            elif name.lower() in TOOL_CORRECTIONS:
                # Even if not in available_tools, use the correction
                corrected_name = TOOL_CORRECTIONS[name.lower()]
                logger.info(f"Corrected tool name: {name} -> {corrected_name}")
                func['name'] = corrected_name
            else:
                # Skip invalid tools entirely
                logger.warning(f"Skipping unknown tool: {name}")
                continue

        corrected.append(tc)

    return corrected


def get_corrected_name(name: str) -> Optional[str]:
    """
    Get the corrected tool name if the original is hallucinated.

    Args:
        name: Original tool name

    Returns:
        Corrected name or None if no correction available
    """
    return TOOL_CORRECTIONS.get(name.lower())
