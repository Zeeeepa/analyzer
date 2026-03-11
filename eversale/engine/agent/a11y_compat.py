"""
Accessibility Snapshot Compatibility Layer
==========================================

Drop-in replacement for the deprecated ``page.accessibility.snapshot()`` API
that was removed in Playwright 1.47+.

Uses Chrome DevTools Protocol (CDP) ``Accessibility.getFullAXTree`` to build
an identical ``{role, name, children, …}`` dict tree.  Falls back to
``page.locator('body').aria_snapshot()`` when CDP is unavailable.

Usage::

    from agent.a11y_compat import compat_accessibility_snapshot

    # Replaces:  tree = await page.accessibility.snapshot(interesting_only=True)
    tree = await compat_accessibility_snapshot(page, interesting_only=True)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


async def compat_accessibility_snapshot(
    page,
    interesting_only: bool = True,
) -> Optional[Dict[str, Any]]:
    """Return an accessibility tree dict compatible with the old Playwright API.

    Parameters
    ----------
    page : playwright.async_api.Page
        The Playwright page instance.
    interesting_only : bool
        When *True* (the default), skip nodes that the browser marks as
        "ignored / uninteresting" — mirrors the old ``interesting_only``
        argument.

    Returns
    -------
    dict | None
        A nested dict with at least ``role``, ``name``, and optionally
        ``children``, ``value``, ``checked``, ``disabled``, ``expanded``,
        ``selected``, ``level``, ``description``.
    """
    # ---------- primary path: CDP ----------
    try:
        return await _snapshot_via_cdp(page, interesting_only)
    except Exception as exc:
        logger.debug("CDP accessibility snapshot failed (%s), trying fallback", exc)

    # ---------- fallback: aria_snapshot (YAML text) ----------
    try:
        yaml_str = await page.locator("body").aria_snapshot()
        title = ""
        try:
            title = await page.title()
        except Exception:
            pass
        return {
            "role": "RootWebArea",
            "name": title,
            "children": _parse_aria_yaml(yaml_str),
        }
    except Exception as exc2:
        logger.debug("aria_snapshot fallback failed: %s", exc2)

    # ---------- last-resort: JS DOM walk ----------
    try:
        return await _snapshot_via_js(page)
    except Exception as exc3:
        logger.warning("All accessibility snapshot methods failed: %s", exc3)
        return None


# ──────────────────────────────────────────────────────────────────────
# CDP-based implementation
# ──────────────────────────────────────────────────────────────────────

async def _snapshot_via_cdp(
    page,
    interesting_only: bool,
) -> Optional[Dict[str, Any]]:
    """Build the tree using ``Accessibility.getFullAXTree`` over CDP."""
    cdp = await page.context.new_cdp_session(page)
    try:
        result = await cdp.send("Accessibility.getFullAXTree")
    finally:
        try:
            await cdp.detach()
        except Exception:
            pass

    nodes = result.get("nodes", [])
    if not nodes:
        return None

    node_map: Dict[str, Dict[str, Any]] = {}
    children_map: Dict[str, List[str]] = {}
    root_id: Optional[str] = None

    for n in nodes:
        nid = n.get("nodeId")
        if nid is None:
            continue

        child_ids = n.get("childIds", [])
        if child_ids:
            children_map[nid] = child_ids

        if interesting_only and n.get("ignored", False):
            continue

        role_obj = n.get("role", {})
        name_obj = n.get("name", {})

        role_val = (
            role_obj.get("value", "none")
            if isinstance(role_obj, dict)
            else str(role_obj)
        )
        name_val = (
            name_obj.get("value", "")
            if isinstance(name_obj, dict)
            else str(name_obj)
        )

        # Collect properties
        props: Dict[str, Any] = {}
        for prop in n.get("properties", []):
            pname = prop.get("name", "")
            pval = prop.get("value", {})
            props[pname] = pval.get("value") if isinstance(pval, dict) else pval

        entry: Dict[str, Any] = {"role": role_val, "name": name_val}

        if props.get("value"):
            entry["value"] = props["value"]
        if props.get("checked") is not None:
            entry["checked"] = props["checked"]
        if props.get("disabled"):
            entry["disabled"] = True
        if props.get("expanded") is not None:
            entry["expanded"] = props["expanded"]
        if props.get("selected") is not None:
            entry["selected"] = props["selected"]
        if props.get("level") is not None:
            entry["level"] = props["level"]
        desc = n.get("description", {})
        if isinstance(desc, dict) and desc.get("value"):
            entry["description"] = desc["value"]

        node_map[nid] = entry
        if root_id is None:
            root_id = nid

    # If root was filtered out, pick first visible node
    if root_id is None or root_id not in node_map:
        for n in nodes:
            nid = n.get("nodeId")
            if nid and nid in node_map:
                root_id = nid
                break
    if root_id is None:
        return None

    def _build(nid: str, depth: int = 0):
        if depth > 25:
            return None
        node = node_map.get(nid)
        if node is None:
            # Filtered-out node — pass through its children
            cids = children_map.get(nid, [])
            flat: list = []
            for cid in cids:
                child = _build(cid, depth + 1)
                if isinstance(child, list):
                    flat.extend(child)
                elif child is not None:
                    flat.append(child)
            return flat or None

        result = dict(node)
        cids = children_map.get(nid, [])
        if cids:
            children: list = []
            for cid in cids:
                child = _build(cid, depth + 1)
                if isinstance(child, list):
                    children.extend(child)
                elif child is not None:
                    children.append(child)
            if children:
                result["children"] = children
        return result

    return _build(root_id)


# ──────────────────────────────────────────────────────────────────────
# JS-based fallback
# ──────────────────────────────────────────────────────────────────────

_JS_WALK = """() => {
    const IMPLICIT = {
        A: 'link', BUTTON: 'button', INPUT: 'textbox', TEXTAREA: 'textbox',
        SELECT: 'combobox', IMG: 'img', H1: 'heading', H2: 'heading',
        H3: 'heading', H4: 'heading', H5: 'heading', H6: 'heading',
        NAV: 'navigation', MAIN: 'main', HEADER: 'banner', FOOTER: 'contentinfo',
        ASIDE: 'complementary', FORM: 'form', TABLE: 'table', UL: 'list',
        OL: 'list', LI: 'listitem', P: 'paragraph',
    };
    function walk(el, depth) {
        if (depth > 12) return null;
        const tag = el.tagName;
        const role = el.getAttribute('role') || IMPLICIT[tag] || tag.toLowerCase();
        const name = el.getAttribute('aria-label')
            || el.getAttribute('alt')
            || el.getAttribute('title')
            || (el.innerText || '').trim().slice(0, 120)
            || '';
        const node = { role, name };
        if (el.tagName === 'INPUT' && el.type === 'checkbox') node.role = 'checkbox';
        if (el.tagName === 'INPUT' && el.type === 'radio') node.role = 'radio';
        const children = [];
        for (const c of el.children) {
            const ch = walk(c, depth + 1);
            if (ch) children.push(ch);
        }
        if (children.length) node.children = children;
        return node;
    }
    return { role: 'RootWebArea', name: document.title, children: [walk(document.body, 0)] };
}"""


async def _snapshot_via_js(page) -> Optional[Dict[str, Any]]:
    """Walk the DOM with JavaScript and infer ARIA roles."""
    return await page.evaluate(_JS_WALK)


# ──────────────────────────────────────────────────────────────────────
# Minimal YAML-ish parser for aria_snapshot output
# ──────────────────────────────────────────────────────────────────────

def _parse_aria_yaml(yaml_str: str) -> List[Dict[str, Any]]:
    """Very lightweight parser for the YAML returned by aria_snapshot().

    Only handles the flat ``- role "name"`` format emitted by Playwright.
    This is intentionally minimal — CDP is the primary path.
    """
    children: List[Dict[str, Any]] = []
    if not yaml_str:
        return children
    for line in yaml_str.strip().splitlines():
        line = line.strip()
        if not line.startswith("- "):
            continue
        line = line[2:].strip()
        # e.g.  heading "Example Domain" [level=1]
        parts = line.split('"', 2)
        if len(parts) >= 2:
            role = parts[0].strip()
            name = parts[1].strip()
        else:
            role = line.split()[0] if line.split() else "unknown"
            name = ""
        children.append({"role": role.rstrip(":"), "name": name})
    return children

