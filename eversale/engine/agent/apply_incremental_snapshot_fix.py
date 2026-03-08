#!/usr/bin/env python3
"""
Apply incremental snapshot fix to agentic_browser.py
"""

import re

# Read the file
with open('/mnt/c/ev29/cli/engine/agent/agentic_browser.py', 'r') as f:
    content = f.read()

# Find and replace the section
old_section = r'''        # Build ref map and text output
        lines = \[f"Page: \{title\}", f"URL: \{url\}", ""\]

        if not unique_elements:
            lines\.append\("No interactive elements found"\)
        else:
            for el in unique_elements:
                ref = el\['ref'\]
                role = el\['role'\]
                name = el\['name'\]
                value = el\.get\('value', ''\)

                # Store ref mapping for click/type actions
                self\.element_refs\[ref\] = el\.get\('locator', f'text="\{name\}"'\)

                # Format like Playwright MCP: "- role 'name' \[ref=X\]"
                if value:
                    lines\.append\(f"- \{role\} \\"\{name\}\\" \[ref=\{ref\}\] value=\\"\{value\}\\""\)
                else:
                    lines\.append\(f"- \{role\} \\"\{name\}\\" \[ref=\{ref\}\]"\)

        return "
"\.join\(lines\)'''

new_section = '''        # Convert to dict keyed by ref for diffing
        current_snapshot = {}
        for el in unique_elements:
            ref = el['ref']
            current_snapshot[ref] = el
            # Store ref mapping for click/type actions
            self.element_refs[ref] = el.get('locator', f'text="{el["name"]}"')

        # Decide if we show full or incremental
        if mode == 'full' or self._previous_snapshot is None:
            # Full snapshot
            self._previous_snapshot = current_snapshot
            return self._format_full_snapshot(current_snapshot, title, url)

        # Incremental mode - show diff
        diff = self._diff_snapshots(self._previous_snapshot, current_snapshot)
        self._previous_snapshot = current_snapshot
        return self._format_incremental_snapshot(diff, title, url)'''

# Replace
content_new = re.sub(old_section, new_section, content, flags=re.MULTILINE | re.DOTALL)

if content != content_new:
    print("Replacement successful!")
    # Write back
    with open('/mnt/c/ev29/cli/engine/agent/agentic_browser.py', 'w') as f:
        f.write(content_new)
    print("File updated.")
else:
    print("Pattern not found or already applied.")
