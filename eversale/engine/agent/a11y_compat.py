"""Playwright Accessibility Compatibility Layer.

Playwright 1.48+ removed ``page.accessibility.snapshot()``.
This module provides a drop-in replacement using either:
  1. ``locator('body').aria_snapshot()``  (Playwright 1.49+)
  2. CDP ``Accessibility.getFullAXTree`` fallback

Usage::

    from agent.a11y_compat import get_accessibility_snapshot
    snapshot = await get_accessibility_snapshot(page)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from loguru import logger


async def get_accessibility_snapshot(
    page: Any,
    *,
    interesting_only: bool = True,
) -> Optional[Dict]:
    """Get an accessibility snapshot from a Playwright page.

    Tries the legacy ``page.accessibility.snapshot()`` first (Playwright < 1.48),
    then falls back to ``locator.aria_snapshot()`` parsed into the legacy dict
    format, and finally tries CDP.

    Returns a dict compatible with the old ``page.accessibility.snapshot()``
    format, or *None* on failure.
    """

    # ── Attempt 1: legacy API (Playwright < 1.48) ──────────────────────
    if hasattr(page, "accessibility"):
        try:
            result = await page.accessibility.snapshot(interesting_only=interesting_only)
            if result:
                return result
        except Exception:
            pass  # Fall through to modern approach

    # ── Attempt 2: aria_snapshot() (Playwright 1.49+) ──────────────────
    try:
        raw = await page.locator("body").aria_snapshot()
        if raw:
            return _parse_aria_snapshot_to_dict(raw, page)
    except Exception as exc:
        logger.debug(f"aria_snapshot fallback failed: {exc}")

    # ── Attempt 3: CDP fallback ────────────────────────────────────────
    try:
        cdp = await page.context.new_cdp_session(page)
        tree = await cdp.send("Accessibility.getFullAXTree")
        await cdp.detach()
        if tree and "nodes" in tree:
            return _cdp_tree_to_dict(tree)
    except Exception as exc:
        logger.debug(f"CDP accessibility fallback failed: {exc}")

    return None


# ── Helpers ────────────────────────────────────────────────────────────


def _parse_aria_snapshot_to_dict(raw: str, page: Any) -> Dict:
    """Convert ``aria_snapshot()`` YAML-like text into the legacy dict format.

    The legacy format is::

        {
            "role": "WebArea",
            "name": "...",
            "children": [
                {"role": "heading", "name": "...", "level": 1},
                {"role": "link", "name": "...", "children": [...]},
                ...
            ]
        }
    """
    lines = raw.strip().split("\n")
    root: Dict[str, Any] = {
        "role": "WebArea",
        "name": getattr(page, "url", ""),
        "children": [],
    }

    stack: List[tuple] = [(root, -1)]  # (node, indent_level)

    for line in lines:
        stripped = line.lstrip("- ")
        indent = len(line) - len(line.lstrip())

        node = _parse_aria_line(stripped)
        if not node:
            continue

        # Pop stack until we find a parent with smaller indent
        while len(stack) > 1 and stack[-1][1] >= indent:
            stack.pop()

        parent = stack[-1][0]
        if "children" not in parent:
            parent["children"] = []
        parent["children"].append(node)
        stack.append((node, indent))

    return root


def _parse_aria_line(line: str) -> Optional[Dict]:
    """Parse a single aria_snapshot line like ``heading "Example" [level=1]``."""
    import re

    if not line.strip():
        return None

    # Pattern: role "name" [attrs] or role: text
    m = re.match(r'^(\w+)\s*"([^"]*)"(?:\s*\[(.+)\])?', line)
    if m:
        node: Dict[str, Any] = {"role": m.group(1), "name": m.group(2)}
        if m.group(3):
            _parse_attrs(node, m.group(3))
        return node

    # Pattern: role: text
    m = re.match(r'^(\w+):\s*(.*)', line)
    if m:
        return {"role": m.group(1), "name": m.group(2).strip()}

    # Pattern: /url: or /value:  (metadata, skip)
    if line.startswith("/"):
        return None

    # Plain text
    return {"role": "text", "name": line.strip()}


def _parse_attrs(node: Dict, attrs_str: str) -> None:
    """Parse ``[level=1]`` style attributes into a node dict."""
    import re
    for pair in re.findall(r'(\w+)=([^\s,\]]+)', attrs_str):
        key, val = pair
        try:
            node[key] = int(val)
        except ValueError:
            node[key] = val


def _cdp_tree_to_dict(tree: Dict) -> Dict:
    """Convert CDP ``Accessibility.getFullAXTree`` response to legacy format."""
    nodes = tree.get("nodes", [])
    if not nodes:
        return {"role": "WebArea", "name": "", "children": []}

    # Build lookup by nodeId
    lookup: Dict[str, Dict] = {}
    for n in nodes:
        nid = n.get("nodeId", "")
        role_val = n.get("role", {}).get("value", "none")
        name_val = n.get("name", {}).get("value", "")
        entry: Dict[str, Any] = {"role": role_val, "name": name_val}

        # Copy relevant properties
        for prop in n.get("properties", []):
            pname = prop.get("name", "")
            pval = prop.get("value", {}).get("value")
            if pname in ("level", "checked", "expanded", "selected", "disabled"):
                entry[pname] = pval

        lookup[nid] = entry

    # Build tree from parent-child relationships
    for n in nodes:
        nid = n.get("nodeId", "")
        children_ids = n.get("childIds", [])
        if children_ids and nid in lookup:
            lookup[nid]["children"] = [
                lookup[cid] for cid in children_ids if cid in lookup
            ]

    # Root is typically the first node
    root_id = nodes[0].get("nodeId", "")
    return lookup.get(root_id, {"role": "WebArea", "name": "", "children": []})

