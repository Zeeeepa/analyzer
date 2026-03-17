#!/usr/bin/env python3
"""
Apply incremental snapshot changes to agentic_browser.py
"""

# Read the file
with open('/mnt/c/ev29/cli/engine/agent/agentic_browser.py', 'r') as f:
    lines = f.readlines()

# Find the __init__ method and add snapshot state variables
init_found = False
for i, line in enumerate(lines):
    if 'self.element_refs = {}  # ref_id -> selector mapping' in line:
        # Insert after this line
        insert_pos = i + 2  # After self.kimi = None line
        if 'self.kimi = None' in lines[i + 1]:
            # Insert the new lines
            new_lines = [
                '\n',
                '        # Incremental snapshot state (Playwright MCP-style)\n',
                '        self._previous_snapshot = None\n',
                "        self._snapshot_mode = 'incremental'  # or 'full'\n",
                '\n'
            ]
            lines[insert_pos:insert_pos] = new_lines
            init_found = True
            break

if init_found:
    print(" [1/3] Added snapshot state variables to __init__")
else:
    print("WARNING: Could not find __init__ location")

# Find navigate method and add reset_snapshot() call
navigate_found = False
for i, line in enumerate(lines):
    if 'async def navigate(self, url: str) -> Dict:' in line:
        # Find the return statement
        for j in range(i, min(i + 15, len(lines))):
            if 'return {"action": "navigate"' in lines[j]:
                # Insert before return
                insert_lines = [
                    '        # Reset snapshot state on new page\n',
                    '        self.reset_snapshot()\n'
                ]
                lines[j:j] = insert_lines
                navigate_found = True
                break
        break

if navigate_found:
    print(" [2/3] Added reset_snapshot() call to navigate()")
else:
    print("WARNING: Could not find navigate() method")

# Find get_snapshot and add helper methods + modify implementation
snapshot_found = False
for i, line in enumerate(lines):
    if '# SNAPSHOT - Get page state with element refs (like Playwright MCP)' in line:
        # Insert helper methods before get_snapshot
        helper_methods = '''
    def reset_snapshot(self):
        """Reset snapshot state for new page."""
        self._previous_snapshot = None

    def _element_unchanged(self, old: Dict, new: Dict) -> bool:
        """Check if element is unchanged between snapshots."""
        return (old.get('type') == new.get('type') and
                old.get('text') == new.get('text') and
                old.get('placeholder') == new.get('placeholder') and
                old.get('value') == new.get('value') and
                old.get('label') == new.get('label') and
                old.get('href') == new.get('href'))

    def _diff_snapshots(self, old_snapshot: Dict, new_snapshot: Dict) -> Dict:
        """Compare snapshots and mark unchanged elements."""
        diff = {}

        for ref_id, new_info in new_snapshot.items():
            if ref_id in old_snapshot:
                old_info = old_snapshot[ref_id]
                if self._element_unchanged(old_info, new_info):
                    diff[ref_id] = {**new_info, 'status': 'unchanged'}
                else:
                    diff[ref_id] = {**new_info, 'status': 'changed'}
            else:
                diff[ref_id] = {**new_info, 'status': 'new'}

        # Mark removed elements
        for ref_id in old_snapshot:
            if ref_id not in new_snapshot:
                diff[ref_id] = {**old_snapshot[ref_id], 'status': 'removed'}

        return diff

    def _format_element(self, ref: str, el: Dict, status: str = None) -> str:
        """Format a single element for display."""
        status_tag = f" [{status}]" if status else ""

        if el['type'] == 'button':
            return f"  [{ref}] button \\"{el['text']}\\"{status_tag}"
        elif el['type'] == 'link':
            return f"  [{ref}] link \\"{el['text']}\\"{status_tag}"
        elif el['type'] == 'input':
            val = f" = \\"{el['value']}\\"" if el.get('value') else ""
            return f"  [{ref}] input ({el['placeholder']}){val}{status_tag}"
        elif el['type'] == 'dropdown':
            return f"  [{ref}] dropdown ({el['label']}){status_tag}"
        else:
            return f"  [{ref}] {el.get('type', 'unknown')}{status_tag}"

    def _format_snapshot(self, elements_dict: Dict, title: str, url: str) -> str:
        """Format full snapshot as text."""
        lines = [f"Page: {title}", f"URL: {url}", "", "Elements:"]

        for ref, el in elements_dict.items():
            lines.append(self._format_element(ref, el))

        return "\\n".join(lines)

    def _format_incremental_snapshot(self, diff: Dict, title: str, url: str) -> str:
        """Format incremental snapshot showing only changes."""
        lines = [f"Page: {title}", f"URL: {url}", "", "Elements:"]

        # Show in order: new, changed, unchanged, removed
        new_items = [(ref, el) for ref, el in diff.items() if el.get('status') == 'new']
        changed_items = [(ref, el) for ref, el in diff.items() if el.get('status') == 'changed']
        unchanged_items = [(ref, el) for ref, el in diff.items() if el.get('status') == 'unchanged']
        removed_items = [(ref, el) for ref, el in diff.items() if el.get('status') == 'removed']

        for ref, el in new_items:
            lines.append(self._format_element(ref, el, 'new'))

        for ref, el in changed_items:
            lines.append(self._format_element(ref, el, 'changed'))

        for ref, el in unchanged_items:
            lines.append(self._format_element(ref, el, 'unchanged'))

        for ref, el in removed_items:
            lines.append(f"  [{ref}] [removed]")

        return "\\n".join(lines)

'''
        # Insert methods after the comment line
        lines.insert(i + 2, helper_methods)

        # Now find and update get_snapshot signature and beginning
        for j in range(i, len(lines)):
            if 'async def get_snapshot(self) -> str:' in lines[j]:
                lines[j] = '    async def get_snapshot(self, mode: str = None) -> str:\n'
                # Update docstring
                for k in range(j + 1, j + 10):
                    if '"""' in lines[k] and 'Get page snapshot' in lines[k]:
                        lines.insert(k + 2, '\n        Args:\n            mode: \\'full\\' or \\'incremental\\' (default: uses self._snapshot_mode)\n')
                        break
                # Add mode handling after docstring
                for k in range(j, j + 20):
                    if 'self.element_refs = {}' in lines[k]:
                        lines.insert(k, '        mode = mode or self._snapshot_mode\n\n')
                        break
                break

        # Find and replace the formatting section at the end of get_snapshot
        for j in range(i, len(lines)):
            if '# Build ref map and text output' in lines[j]:
                # Find the return statement
                return_idx = None
                for k in range(j, j + 30):
                    if 'return "\\n".join(lines)' in lines[k] or 'return "' in lines[k]:
                        return_idx = k
                        break

                if return_idx:
                    # Replace everything from "# Build ref map" to return
                    new_code = '''        # Convert elements list to dict keyed by ref
        current_snapshot = {el['ref']: el for el in elements}

        # Decide if we show full or incremental
        if mode == 'full' or self._previous_snapshot is None:
            # Full snapshot
            self._previous_snapshot = current_snapshot
            return self._format_snapshot(current_snapshot, title, url)

        # Incremental mode - show diff
        diff = self._diff_snapshots(self._previous_snapshot, current_snapshot)
        self._previous_snapshot = current_snapshot
        return self._format_incremental_snapshot(diff, title, url)
'''
                    lines[j:return_idx + 1] = [new_code]
                break

        snapshot_found = True
        break

if snapshot_found:
    print(" [3/3] Added helper methods and updated get_snapshot()")
else:
    print("WARNING: Could not find snapshot section")

# Write back
with open('/mnt/c/ev29/cli/engine/agent/agentic_browser.py', 'w') as f:
    f.writelines(lines)

print("\n✓ All changes applied successfully!")
