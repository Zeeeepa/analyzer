"""
Output Format Handler - Detects and applies user-specified output formats.

This module handles cases where users specify exact output formats in their prompts,
such as:
  - "Format: KEY: value"
  - "Output as: FIELD1: ... FIELD2: ..."
  - Specific line-by-line format templates

The handler:
1. Detects if user specified a format
2. Parses the format template
3. Applies it to extracted results instead of default JSON
"""

import re
from typing import Optional, Dict, Any, List
from loguru import logger


def detect_output_format(prompt: str) -> Optional[Dict[str, Any]]:
    """
    Detect if user specified a custom output format in their prompt.

    Returns format specification dict if found, None otherwise.
    """
    prompt_lower = prompt.lower()

    # Look for format specifications
    format_indicators = [
        # "output format must be exactly these 2 lines: LINE1 then LINE2"
        r'output\s+format\s+must\s+be\s+(?:exactly\s+)?(?:these\s+)?(?:\d+\s+)?lines?[:\s]+(.+?)(?:\n\n|\Z)',
        # "format must be: LINE1 LINE2"
        r'format\s+must\s+be[:\s]+(.+?)(?:\n\n|\Z)',
        # "output must be: LINE1 LINE2"
        r'output\s+must\s+be[:\s]+(.+?)(?:\n\n|\Z)',
        # Standard patterns
        r'format[:\s]+(.+?)(?:\n\n|\Z)',
        r'output\s+(?:as|format)[:\s]+(.+?)(?:\n\n|\Z)',
        r'display\s+(?:as|format)[:\s]+(.+?)(?:\n\n|\Z)',
        r'show\s+(?:as|in format)[:\s]+(.+?)(?:\n\n|\Z)',
    ]

    for pattern in format_indicators:
        match = re.search(pattern, prompt, re.I | re.DOTALL)
        if match:
            format_spec = match.group(1).strip()
            logger.debug(f"[OUTPUT FORMAT] Found format spec: {format_spec[:100]}...")

            # Parse the format template
            template = parse_format_template(format_spec)
            if template:
                logger.info(f"[OUTPUT FORMAT] Detected user format: {len(template['lines'])} lines")
                return {
                    'type': 'template',
                    'template': template,
                    'raw_spec': format_spec
                }
            else:
                logger.debug(f"[OUTPUT FORMAT] Could not parse format template")

    return None


def parse_format_template(format_spec: str) -> Optional[Dict[str, Any]]:
    """
    Parse a format template string into structured format.

    Example input:
        FB_PROSPECT_URL: <url>
        REDDIT: thread=<url> user=<username> profile=<url>
        LINKEDIN: profile=<url> | if_blocked google=<url> linkedin_found=<url>

    Also supports inline format with 'then' separator:
        FB_PROSPECT_URL: <url> then REDDIT: thread=<url> user=<username>

    Returns:
        {
            'lines': [
                {'prefix': 'FB_PROSPECT_URL', 'fields': [{'name': 'url', 'key': None}]},
                {'prefix': 'REDDIT', 'fields': [
                    {'name': 'url', 'key': 'thread'},
                    {'name': 'username', 'key': 'user'},
                    {'name': 'url', 'key': 'profile'}
                ]},
                ...
            ]
        }
    """
    lines = []

    # First, split by 'then' to handle inline formats
    # "FB_PROSPECT_URL: <url> then REDDIT: thread=<url>" -> ["FB_PROSPECT_URL: <url>", "REDDIT: thread=<url>"]
    format_parts = re.split(r'\s+then\s+', format_spec, flags=re.IGNORECASE)

    # Now process each part (which may have newlines)
    all_line_strings = []
    for part in format_parts:
        all_line_strings.extend(part.split('\n'))

    for line in all_line_strings:
        line = line.strip()
        if not line or line.startswith('#'):
            continue

        # Parse line format: PREFIX: field1=<value1> field2=<value2> ...
        match = re.match(r'^([A-Z_]+):\s*(.+)$', line)
        if match:
            prefix = match.group(1)
            fields_part = match.group(2)

            # Parse fields
            fields = []

            # Handle simple single field: "FB_PROSPECT_URL: <url>"
            simple_match = re.match(r'^<(\w+)>$', fields_part.strip())
            if simple_match:
                fields.append({
                    'name': simple_match.group(1),
                    'key': None
                })
            else:
                # Handle key=value pairs: "thread=<url> user=<username>"
                # Split by | first for alternatives
                parts = re.split(r'\s*\|\s*', fields_part)

                for part in parts:
                    part = part.strip()
                    if not part:
                        continue

                    # Look for key=<value> patterns
                    field_matches = re.findall(r'(\w+)=<(\w+)>', part)
                    if field_matches:
                        for key, value_type in field_matches:
                            fields.append({
                                'name': value_type,
                                'key': key
                            })
                    # Also handle standalone <value> patterns
                    standalone_matches = re.findall(r'<(\w+)>', part)
                    for value_type in standalone_matches:
                        if not any(f['name'] == value_type for f in fields):
                            fields.append({
                                'name': value_type,
                                'key': None
                            })

            if fields:
                lines.append({
                    'prefix': prefix,
                    'fields': fields
                })

    if not lines:
        return None

    return {'lines': lines}


def apply_format_template(data: Any, template: Dict[str, Any]) -> str:
    """
    Apply a format template to extracted data.

    Args:
        data: Extracted data (dict, list of dicts, or JSON-like structure)
        template: Parsed format template

    Returns:
        Formatted output string
    """
    import json

    # Normalize data to dict
    if isinstance(data, str):
        # Try to extract JSON from string
        try:
            data = json.loads(data)
        except:
            # Try to extract first JSON object from string
            json_match = re.search(r'\{[^{}]*\}', data)
            if json_match:
                try:
                    data = json.loads(json_match.group(0))
                except:
                    pass

            # Try to extract JSON array
            if isinstance(data, str):
                json_array_match = re.search(r'\[[^\[\]]*\]', data)
                if json_array_match:
                    try:
                        data = json.loads(json_array_match.group(0))
                    except:
                        pass

            # Still a string - can't parse
            if isinstance(data, str):
                logger.warning("[OUTPUT FORMAT] Data is plain text, cannot apply template")
                return data

    # If data is a list, apply template to each item
    if isinstance(data, list):
        if not data:
            return "No data to format"

        # Check if this is a list of dicts
        if all(isinstance(item, dict) for item in data):
            # Format each item and combine
            formatted_items = []
            for item in data:
                formatted = apply_format_template(item, template)
                formatted_items.append(formatted)
            return '\n\n'.join(formatted_items)
        else:
            # Take first item
            data = data[0]

    if not isinstance(data, dict):
        logger.warning(f"[OUTPUT FORMAT] Data type {type(data)} not supported for templating")
        return str(data)

    # Apply template line by line
    output_lines = []

    for line_spec in template['lines']:
        prefix = line_spec['prefix']
        fields = line_spec['fields']

        # Build values for this line
        values = []

        for field_spec in fields:
            field_name = field_spec['name']
            field_key = field_spec['key']

            # Look for value in data
            value = None

            # Try exact match first
            if field_key:
                # Try exact key match
                if field_key in data:
                    value = data[field_key]
                # Try key variations (snake_case, etc.)
                elif f"{field_key}_url" in data:
                    value = data[f"{field_key}_url"]
                elif f"{field_key}Url" in data:
                    value = data[f"{field_key}Url"]

            # Try field name variants
            if value is None:
                # Define field-specific mappings (more specific first)
                field_mappings = {
                    'url': {
                        'FB_PROSPECT_URL': ['fb_prospect_url', 'fb_url', 'facebook_url'],
                        'MAPS_LISTING_URL': ['maps_url', 'google_maps_url', 'listing_url'],
                        'GMAIL_FINAL_URL': ['gmail_url', 'gmail_final_url'],
                        'ZOHO_FINAL_URL': ['zoho_url', 'zoho_final_url'],
                        'default': ['url', 'link', 'href', 'source_url']
                    },
                    'username': ['username', 'user', 'author', 'name', 'reddit_user'],
                    'thread': ['thread_url', 'thread', 'url'],
                    'profile': ['profile_url', 'profile', 'linkedin_url', 'linkedin'],
                    'google': ['google_url', 'google_search_url'],
                    'linkedin_found': ['linkedin_found_url', 'linkedin_url']
                }

                # Get candidates for this field
                if field_name == 'url' and prefix in field_mappings['url']:
                    # Use prefix-specific URL mapping
                    candidates = field_mappings['url'][prefix]
                elif field_name in field_mappings:
                    candidates = field_mappings[field_name]
                else:
                    candidates = [field_name]

                # Try each candidate
                for candidate in candidates:
                    if candidate in data:
                        value = data[candidate]
                        break

                # Fallback to case-insensitive match
                if value is None:
                    for key in data.keys():
                        if key.lower() == field_name.lower():
                            value = data[key]
                            break

            # Format the value
            if value is not None:
                if field_key:
                    values.append(f"{field_key}={value}")
                else:
                    values.append(str(value))
            else:
                # Field not found
                if field_key:
                    values.append(f"{field_key}=N/A")
                else:
                    values.append("N/A")

        # Combine into line
        line_output = f"{prefix}: {' '.join(values)}"
        output_lines.append(line_output)

    return '\n'.join(output_lines)


def format_output(prompt: str, result: Any) -> str:
    """
    Main entry point: Format result according to user's prompt specification.

    If user specified a format in their prompt, applies it.
    Otherwise returns result unchanged.

    Args:
        prompt: Original user prompt
        result: Execution result (any type)

    Returns:
        Formatted result string
    """
    # Detect if user wants custom format
    format_spec = detect_output_format(prompt)

    if not format_spec:
        # No custom format - return as-is
        return str(result) if not isinstance(result, str) else result

    # Apply template
    if format_spec['type'] == 'template':
        template = format_spec['template']
        try:
            # MULTI-TASK HANDLING: Check if result is a multi-task summary
            # Pattern: "Goal 1: ... Goal 2: ... Goal 3: ..."
            if isinstance(result, str) and _is_multi_task_result(result):
                formatted = _format_multi_task_result(result, template)
                logger.info(f"[OUTPUT FORMAT] Applied custom format to multi-task result")
                return formatted
            else:
                # Single task result - apply template normally
                formatted = apply_format_template(result, template)
                logger.info(f"[OUTPUT FORMAT] Applied custom format successfully")
                return formatted
        except Exception as e:
            logger.warning(f"[OUTPUT FORMAT] Failed to apply template: {e}")
            # Fallback to original result
            return str(result) if not isinstance(result, str) else result

    # Unknown format type
    return str(result) if not isinstance(result, str) else result


def _is_multi_task_result(result: str) -> bool:
    """
    Detect if result string is a multi-task summary.

    Multi-task summaries have patterns like:
    - "Goal 1: ..."
    - "Task 1: ..."
    - Multiple numbered goals/tasks
    """
    # Look for "Goal N:" or "Task N:" patterns
    goal_pattern = r'(?:^|\n)(?:Goal|Task)\s+\d+:\s+'
    matches = re.findall(goal_pattern, result, re.MULTILINE)

    # If we find 2+ goal/task markers, it's multi-task
    return len(matches) >= 2


def _format_multi_task_result(result: str, template: Dict[str, Any]) -> str:
    """
    Format a multi-task result where each task's data should be formatted separately.

    Args:
        result: Multi-task summary string with "Goal 1: ..., Goal 2: ..." format
        template: Format template to apply to each task's result

    Returns:
        Formatted output with each task properly separated and formatted
    """
    import json

    # Split result into task sections
    # Pattern: "Goal N:" or "Task N:"
    task_pattern = r'((?:Goal|Task)\s+\d+):\s*([^\n]+(?:\n(?!(?:Goal|Task)\s+\d+:)[^\n]+)*)'
    task_matches = re.findall(task_pattern, result, re.MULTILINE)

    if not task_matches:
        # Couldn't parse - return as-is
        logger.warning("[OUTPUT FORMAT] Could not parse multi-task result")
        return result

    formatted_tasks = []

    for task_label, task_result in task_matches:
        task_result = task_result.strip()

        # Try to extract structured data from task result
        # Look for URLs, key-value pairs, JSON, etc.
        task_data = _extract_data_from_task_result(task_result)

        if task_data:
            # Apply template to this task's data
            # Use selective template application - only show lines with data
            try:
                formatted_data = _apply_selective_template(task_data, template)
                if formatted_data.strip():
                    formatted_tasks.append(f"{task_label}:\n{formatted_data}")
                else:
                    # No relevant data - keep original
                    formatted_tasks.append(f"{task_label}: {task_result}")
            except Exception as e:
                logger.warning(f"[OUTPUT FORMAT] Failed to format {task_label}: {e}")
                # Keep original
                formatted_tasks.append(f"{task_label}: {task_result}")
        else:
            # No structured data found - keep original
            formatted_tasks.append(f"{task_label}: {task_result}")

    # Combine all formatted tasks
    return '\n\n'.join(formatted_tasks)


def _apply_selective_template(data: Dict[str, Any], template: Dict[str, Any]) -> str:
    """
    Apply template but only show lines where data is actually present.

    This prevents showing "N/A" for fields that don't apply to this task.

    Args:
        data: Extracted data dict
        template: Format template

    Returns:
        Formatted string with only relevant lines
    """
    output_lines = []

    for line_spec in template['lines']:
        prefix = line_spec['prefix']
        fields = line_spec['fields']

        # Check if this line has ANY data before including it
        has_data = False
        values = []

        for field_spec in fields:
            field_name = field_spec['name']
            field_key = field_spec['key']

            # Look for value in data (same logic as apply_format_template)
            value = None

            # Try exact match first
            if field_key:
                if field_key in data:
                    value = data[field_key]
                elif f"{field_key}_url" in data:
                    value = data[f"{field_key}_url"]
                elif f"{field_key}Url" in data:
                    value = data[f"{field_key}Url"]

            # Try field name variants
            if value is None:
                # Define field-specific mappings
                field_mappings = {
                    'url': {
                        'FB_PROSPECT_URL': ['fb_prospect_url', 'fb_url', 'facebook_url'],
                        'MAPS_LISTING_URL': ['maps_url', 'google_maps_url', 'listing_url'],
                        'GMAIL_FINAL_URL': ['gmail_url', 'gmail_final_url'],
                        'ZOHO_FINAL_URL': ['zoho_url', 'zoho_final_url'],
                        'URL': ['url', 'link', 'href', 'source_url'],  # Generic URL
                        'default': ['url', 'link', 'href', 'source_url']
                    },
                    'username': ['username', 'user', 'author', 'name', 'reddit_user'],
                    'thread': ['thread_url', 'thread', 'url'],
                    'profile': ['profile_url', 'profile', 'linkedin_url', 'linkedin'],
                    'google': ['google_url', 'google_search_url'],
                    'linkedin_found': ['linkedin_found_url', 'linkedin_url']
                }

                # Get candidates for this field
                if field_name == 'url' and prefix in field_mappings['url']:
                    # Use prefix-specific URL mapping ONLY
                    candidates = field_mappings['url'][prefix]
                elif field_name == 'url':
                    # Generic URL prefix - only use generic URL fields
                    candidates = ['url', 'link', 'href', 'source_url']
                elif field_name in field_mappings:
                    candidates = field_mappings[field_name]
                else:
                    candidates = [field_name]

                # Try each candidate
                for candidate in candidates:
                    if candidate in data:
                        value = data[candidate]
                        break

                # Fallback to case-insensitive match
                if value is None:
                    for key in data.keys():
                        if key.lower() == field_name.lower():
                            value = data[key]
                            break

            if value is not None:
                has_data = True
                if field_key:
                    values.append(f"{field_key}={value}")
                else:
                    values.append(str(value))
            else:
                # No value - don't add to values list
                pass

        # Only add line if we found data
        if has_data:
            line_output = f"{prefix}: {' '.join(values)}"
            output_lines.append(line_output)

    return '\n'.join(output_lines)


def _extract_data_from_task_result(task_result: str) -> Optional[Dict[str, Any]]:
    """
    Extract structured data from a task result string.

    Looks for:
    - URLs (extracts and categorizes by context)
    - Key-value pairs (name=value)
    - JSON objects
    - Common patterns like "Found N at URL"

    Returns:
        Dict with extracted data, or None if no structured data found
    """
    import json

    data = {}

    # Try to extract JSON first
    try:
        json_match = re.search(r'\{[^{}]*\}', task_result)
        if json_match:
            parsed = json.loads(json_match.group(0))
            if isinstance(parsed, dict):
                return parsed
    except:
        pass

    # Extract URLs
    url_pattern = r'(https?://[^\s\)\]\,]+)'
    urls = re.findall(url_pattern, task_result)

    # Categorize URLs by domain/context
    for url in urls:
        if 'facebook.com' in url or 'fb.com' in url:
            data['fb_prospect_url'] = url
        elif 'reddit.com' in url:
            if '/user/' in url:
                data['profile_url'] = url
            elif '/r/' in url or '/comments/' in url:
                data['thread_url'] = url
            else:
                data['url'] = url
        elif 'linkedin.com' in url:
            data['profile_url'] = url
        elif 'google.com/maps' in url or 'maps.google.com' in url:
            data['maps_url'] = url
        elif 'mail.google.com' in url:
            data['gmail_url'] = url
        elif 'zoho.com' in url:
            data['zoho_url'] = url
        else:
            # Generic URL
            if 'url' not in data:
                data['url'] = url

    # Extract usernames/names
    # Pattern: "user=X" or "username: X" or similar
    username_patterns = [
        r'(?:user|username|author)[:=]\s*([^\s,\|\)]+)',
        r'u/([a-zA-Z0-9_-]+)',  # Reddit username
    ]
    for pattern in username_patterns:
        match = re.search(pattern, task_result, re.IGNORECASE)
        if match:
            data['username'] = match.group(1)
            break

    # Extract advertiser names from FB Ads results
    # Pattern: "Found N FB advertiser(s): NAME"
    fb_match = re.search(r'Found\s+\d+\s+FB\s+advertiser.*?:\s*([^\n]+)', task_result, re.IGNORECASE)
    if fb_match:
        data['advertiser_name'] = fb_match.group(1).strip()

    # If we found any data, return it
    return data if data else None


# Test
if __name__ == "__main__":
    # Test format detection
    prompt1 = """
Find Reddit users discussing lead generation. Format:
FB_PROSPECT_URL: <url>
REDDIT: thread=<url> user=<username> profile=<url>
LINKEDIN: profile=<url> | if_blocked google=<url> linkedin_found=<url>
MAPS_LISTING_URL: <url>
GMAIL_FINAL_URL: <url>
ZOHO_FINAL_URL: <url>
"""

    format_spec = detect_output_format(prompt1)
    print("Detected format:", format_spec)

    # Test format application
    sample_data = {
        'url': 'https://reddit.com/r/test/123',
        'username': 'test_user',
        'profile_url': 'https://www.reddit.com/user/test_user',
        'thread_url': 'https://reddit.com/r/test/123',
    }

    if format_spec:
        output = apply_format_template(sample_data, format_spec['template'])
        print("\nFormatted output:")
        print(output)
