"""
Tool Call Parser - Extract tool calls from LLM responses

Since we're using smaller models (Llama 3.1 8B), we need robust parsing
that handles imperfect formatting.
"""

import re
from typing import List, Dict, Any
from loguru import logger


class ToolCallParser:
    """Parse tool calls from LLM text responses"""

    def extract_tool_calls(self, response: str) -> List[Dict[str, Any]]:
        """
        Extract tool calls from agent response

        Expected format:
        TOOL: tool_name
        PARAMS:
        param1: value1
        param2: value2
        END_TOOL

        Returns:
            List of {tool: str, params: dict}
        """

        tool_calls = []

        # Pattern to match tool calls
        pattern = r'TOOL:\s*(\w+)\s*\nPARAMS:\s*\n(.*?)\nEND_TOOL'

        matches = re.finditer(pattern, response, re.DOTALL | re.IGNORECASE)

        for match in matches:
            tool_name = match.group(1).strip()
            params_text = match.group(2).strip()

            # Parse parameters
            params = self._parse_params(params_text)

            tool_calls.append({
                "tool": tool_name,
                "params": params
            })

            logger.debug(f"Parsed tool call: {tool_name} with {len(params)} params")

        return tool_calls

    def _parse_params(self, params_text: str) -> Dict[str, Any]:
        """
        Parse parameter block

        Format:
        param1: value1
        param2: value2
        multi_line_param: |
          line1
          line2
        """

        params = {}
        current_param = None
        current_value = []
        in_multiline = False

        for line in params_text.split('\n'):
            line = line.rstrip()

            # Check if this is a new parameter
            if ':' in line and not in_multiline:
                # Save previous param
                if current_param:
                    params[current_param] = '\n'.join(current_value).strip()

                # Parse new param
                parts = line.split(':', 1)
                current_param = parts[0].strip()
                value = parts[1].strip() if len(parts) > 1 else ""

                # Check for multiline indicator
                if value == '|':
                    in_multiline = True
                    current_value = []
                else:
                    current_value = [value]
                    in_multiline = False

            elif in_multiline:
                # Accumulate multiline value
                current_value.append(line)

            elif current_param:
                # Continue previous value
                current_value.append(line)

        # Save last param
        if current_param:
            params[current_param] = '\n'.join(current_value).strip()

        # Type conversion
        params = self._convert_types(params)

        return params

    def _convert_types(self, params: Dict[str, str]) -> Dict[str, Any]:
        """Convert string values to appropriate types"""

        converted = {}

        for key, value in params.items():
            # Try to convert to appropriate type
            if value.lower() == 'true':
                converted[key] = True
            elif value.lower() == 'false':
                converted[key] = False
            elif value.lower() == 'null' or value.lower() == 'none':
                converted[key] = None
            elif value.isdigit():
                converted[key] = int(value)
            else:
                try:
                    converted[key] = float(value)
                except ValueError:
                    converted[key] = value

        return converted


    def has_completion_signal(self, response: str) -> bool:
        """Check if agent signals task completion"""

        completion_markers = [
            "TASK COMPLETE",
            "DONE",
            "FINISHED",
            "COMPLETED"
        ]

        response_upper = response.upper()

        return any(marker in response_upper for marker in completion_markers)
