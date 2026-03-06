"""
Lightweight prompt compiler.

Purpose:
- Make vague prompts behave predictably without bloating the agent.
- Extract operator controls (output format, strictness, no-login rules, time budget)
  and pass them into the LLM fallback as structured JSON.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


def _dedupe_preserve(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for it in items:
        k = it.strip()
        if not k:
            continue
        kl = k.lower()
        if kl in seen:
            continue
        seen.add(kl)
        out.append(k)
    return out


def extract_urls(prompt: str) -> List[str]:
    if not prompt:
        return []
    urls = re.findall(r"https?://[^\s)\]}>\"']+", prompt)
    return _dedupe_preserve(urls)


def extract_output_contract(prompt: str) -> Dict[str, Any]:
    """
    Output rules that should strongly constrain final output.
    """
    p = (prompt or "").lower()
    contract: Dict[str, Any] = {
        "format": None,  # json|csv|markdown|table|text|lines
        "json_only": False,
        "no_extra_text": False,
        "exact_lines": None,
        "https_only": False,
        "include_sources": None,  # bool|None
        "allow_urls": True,
        "allow_usernames": True,
    }

    if any(k in p for k in ("json only", "only json", "return only json")):
        contract["format"] = "json"
        contract["json_only"] = True
        contract["no_extra_text"] = True

    if any(k in p for k in ("csv", "spreadsheet", "google sheet", "sheets")):
        contract["format"] = contract["format"] or "csv"

    if "markdown" in p:
        contract["format"] = "markdown"

    if any(k in p for k in ("table", "tabular")):
        contract["format"] = contract["format"] or "table"

    m = re.search(r"\bexactly\s+(\d{1,3})\s+lines?\b", p)
    if m:
        contract["format"] = contract["format"] or "lines"
        contract["exact_lines"] = int(m.group(1))

    if "no extra text" in p or "nothing else" in p or "no other text" in p:
        contract["no_extra_text"] = True

    # Natural language "output only ..." contracts (common for lead-finding tasks).
    if "no explanations" in p or "no explanation" in p:
        contract["no_extra_text"] = True
        contract["format"] = contract["format"] or "lines"

    # "Output only URLs/usernames, no explanations." -> tokens-only lines.
    if "output only" in p:
        if any(k in p for k in ("url", "urls", "username", "usernames")):
            contract["no_extra_text"] = True
            contract["format"] = contract["format"] or "lines"
        if "username" in p and "url" not in p:
            contract["allow_urls"] = False
        if "url" in p and "username" not in p and "usernames" not in p:
            contract["allow_usernames"] = False

    if "https urls only" in p or "https only" in p:
        contract["https_only"] = True

    if any(k in p for k in ("include sources", "include source urls", "evidence-first", "evidence first")):
        contract["include_sources"] = True
    if any(k in p for k in ("no sources", "don't include sources", "dont include sources")):
        contract["include_sources"] = False

    return contract


def extract_safety_constraints(prompt: str) -> Dict[str, Any]:
    p = (prompt or "").lower()
    constraints: Dict[str, Any] = {
        "public_only": False,
        "no_login": False,
        "no_signup": False,
        "avoid_gated": False,
        "max_retries_per_site": None,
    }

    if any(k in p for k in ("public pages only", "public sites only", "no logins", "don't login", "dont login")):
        constraints["public_only"] = True
        constraints["no_login"] = True
        constraints["avoid_gated"] = True

    if any(k in p for k in ("don't sign in", "dont sign in", "do not sign in")):
        constraints["no_login"] = True
        constraints["avoid_gated"] = True

    if any(k in p for k in ("no signup", "don't sign up", "dont sign up", "do not sign up")):
        constraints["no_signup"] = True
        constraints["avoid_gated"] = True

    m = re.search(r"\bstop\s+after\s+(\d{1,2})\s+failed\s+attempts?\s+per\s+site\b", p)
    if m:
        constraints["max_retries_per_site"] = int(m.group(1))

    return constraints


def extract_task_intent(prompt: str) -> Dict[str, Any]:
    """
    Broad task type guess (heuristics only). This is NOT the workflow router.
    """
    p = (prompt or "").lower()
    intent = {
        "type": "unknown",
        "keywords": [],
    }

    if any(k in p for k in ("warm lead", "warm leads", "prospect", "prospects", "icp", "outreach")):
        intent["type"] = "leads"
    elif any(k in p for k in ("extract", "scrape", "pull", "collect", "copy", "get all", "download")):
        intent["type"] = "extract"
    elif any(k in p for k in ("fill", "submit", "apply", "checkout", "book", "schedule", "register")):
        intent["type"] = "form"
    elif any(k in p for k in ("monitor", "alert", "notify", "watch", "track")):
        intent["type"] = "monitor"
    elif any(k in p for k in ("compare", "versus", "vs", "benchmark")):
        intent["type"] = "compare"

    kws = re.findall(r"[a-z0-9][a-z0-9\\-]{2,}", p)
    intent["keywords"] = _dedupe_preserve(kws)[:25]
    return intent


def compile_prompt(prompt: str) -> Dict[str, Any]:
    urls = extract_urls(prompt)
    return {
        "prompt": prompt,
        "urls": urls,
        "output_contract": extract_output_contract(prompt),
        "constraints": extract_safety_constraints(prompt),
        "intent": extract_task_intent(prompt),
    }


def should_enforce_exact_lines(contract: Dict[str, Any]) -> Optional[int]:
    n = contract.get("exact_lines")
    if isinstance(n, int) and n > 0:
        return n
    return None
