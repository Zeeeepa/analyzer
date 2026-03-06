"""
Negative Example Learning - Learn from verified failures.

Your 153 verified failures are training gold. This module:
1. Stores failed selectors with working alternatives
2. Tracks site-specific failures
3. Quarantines unreliable sites
4. Injects "don't do this" into prompts
"""

import json
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from pathlib import Path
from loguru import logger


@dataclass
class FailedSelector:
    """A selector that failed with its working alternative."""
    failed_selector: str
    site: str
    working_selector: Optional[str]
    failure_reason: str
    failure_count: int = 1
    last_failed: str = ""

    def __post_init__(self):
        if not self.last_failed:
            self.last_failed = datetime.now().isoformat()


@dataclass
class QuarantinedSite:
    """A site that's too flaky to train on."""
    domain: str
    reason: str
    failure_count: int
    last_attempt: str
    quarantine_until: str  # ISO timestamp
    consecutive_failures: int = 0


@dataclass
class NegativeExample:
    """A verified failure for learning."""
    task_prompt: str
    task_category: str
    site: str
    failed_output: str
    failure_reason: str
    ground_truth_evidence: Dict
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


class NegativeExampleStore:
    """
    Stores and retrieves negative examples for learning.

    Learning from failure is often more valuable than learning from success.
    """

    # Sites that are fundamentally broken for automation
    QUARANTINED_SITES = {
        "httpbin.org": "Frequent 503 errors, unreliable for training",
        "stackoverflow.com": "CAPTCHA walls on automated access",
        "producthunt.com": "Cloudflare challenges block automation",
        "glassdoor.com": "Aggressive bot detection",
        "indeed.com": "CAPTCHA and rate limiting",
        "yelp.com": "Aggressive anti-scraping",
    }

    # Quarantine duration for dynamically detected flaky sites
    QUARANTINE_HOURS = 24

    # Failure threshold before quarantine
    FAILURE_THRESHOLD = 5

    def __init__(self, storage_dir: Path = None):
        self.storage_dir = storage_dir or Path("training/negative_examples")
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # Storage files
        self.selectors_file = self.storage_dir / "failed_selectors.json"
        self.quarantine_file = self.storage_dir / "quarantined_sites.json"
        self.examples_file = self.storage_dir / "negative_examples.json"

        # In-memory data
        self.failed_selectors: Dict[str, FailedSelector] = {}
        self.quarantined_sites: Dict[str, QuarantinedSite] = {}
        self.negative_examples: List[NegativeExample] = []

        # Site failure tracking for dynamic quarantine
        self.site_failures: Dict[str, int] = {}

        self._load_all()

    def _load_all(self):
        """Load all data from disk."""
        self._load_selectors()
        self._load_quarantine()
        self._load_examples()

    def _load_selectors(self):
        """Load failed selectors."""
        if self.selectors_file.exists():
            try:
                with open(self.selectors_file) as f:
                    data = json.load(f)
                    for key, val in data.items():
                        self.failed_selectors[key] = FailedSelector(**val)
            except Exception as e:
                logger.warning(f"Could not load failed selectors: {e}")

    def _load_quarantine(self):
        """Load quarantined sites."""
        if self.quarantine_file.exists():
            try:
                with open(self.quarantine_file) as f:
                    data = json.load(f)
                    for domain, val in data.items():
                        self.quarantined_sites[domain] = QuarantinedSite(**val)
            except Exception as e:
                logger.warning(f"Could not load quarantine: {e}")

        # Add hardcoded quarantine
        for domain, reason in self.QUARANTINED_SITES.items():
            if domain not in self.quarantined_sites:
                self.quarantined_sites[domain] = QuarantinedSite(
                    domain=domain,
                    reason=reason,
                    failure_count=999,  # Permanent
                    last_attempt="",
                    quarantine_until="2099-12-31T00:00:00",
                    consecutive_failures=999
                )

    def _load_examples(self):
        """Load negative examples."""
        if self.examples_file.exists():
            try:
                with open(self.examples_file) as f:
                    data = json.load(f)
                    self.negative_examples = [NegativeExample(**ex) for ex in data[-500:]]  # Keep last 500
            except Exception as e:
                logger.warning(f"Could not load negative examples: {e}")

    def _save_selectors(self):
        """Save failed selectors."""
        try:
            data = {k: asdict(v) for k, v in self.failed_selectors.items()}
            with open(self.selectors_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save selectors: {e}")

    def _save_quarantine(self):
        """Save quarantine list."""
        try:
            data = {k: asdict(v) for k, v in self.quarantined_sites.items()}
            with open(self.quarantine_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save quarantine: {e}")

    def _save_examples(self):
        """Save negative examples."""
        try:
            data = [asdict(ex) for ex in self.negative_examples[-500:]]
            with open(self.examples_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save examples: {e}")

    def is_site_quarantined(self, domain: str) -> bool:
        """Check if a site is quarantined."""
        # Normalize domain
        domain = domain.lower().replace('www.', '')

        if domain in self.quarantined_sites:
            quarantine = self.quarantined_sites[domain]

            # Check if quarantine has expired
            try:
                until = datetime.fromisoformat(quarantine.quarantine_until)
                if datetime.now() > until:
                    # Quarantine expired, remove it (unless it's hardcoded)
                    if domain not in self.QUARANTINED_SITES:
                        del self.quarantined_sites[domain]
                        self._save_quarantine()
                        return False
            except:
                pass

            return True

        return False

    def get_quarantine_reason(self, domain: str) -> Optional[str]:
        """Get the reason a site is quarantined."""
        domain = domain.lower().replace('www.', '')

        if domain in self.quarantined_sites:
            return self.quarantined_sites[domain].reason
        return None

    def record_site_failure(self, domain: str, error: str):
        """
        Record a site failure. Auto-quarantine after threshold.
        """
        domain = domain.lower().replace('www.', '')

        # Increment failure count
        self.site_failures[domain] = self.site_failures.get(domain, 0) + 1

        # Check threshold
        if self.site_failures[domain] >= self.FAILURE_THRESHOLD:
            if domain not in self.quarantined_sites:
                # Auto-quarantine
                quarantine_until = datetime.now() + timedelta(hours=self.QUARANTINE_HOURS)
                self.quarantined_sites[domain] = QuarantinedSite(
                    domain=domain,
                    reason=f"Auto-quarantined: {error[:100]}",
                    failure_count=self.site_failures[domain],
                    last_attempt=datetime.now().isoformat(),
                    quarantine_until=quarantine_until.isoformat(),
                    consecutive_failures=self.site_failures[domain]
                )
                self._save_quarantine()
                logger.warning(f"[QUARANTINE] Auto-quarantined {domain}: {error[:50]}")

    def record_site_success(self, domain: str):
        """Record a site success - resets failure counter."""
        domain = domain.lower().replace('www.', '')
        self.site_failures[domain] = 0

    def record_selector_failure(self,
                                 selector: str,
                                 site: str,
                                 reason: str,
                                 working_alternative: str = None):
        """
        Record a selector failure with optional working alternative.

        This builds the "don't use this selector" database.
        """
        key = f"{site}:{selector}"

        if key in self.failed_selectors:
            self.failed_selectors[key].failure_count += 1
            self.failed_selectors[key].last_failed = datetime.now().isoformat()
            if working_alternative:
                self.failed_selectors[key].working_selector = working_alternative
        else:
            self.failed_selectors[key] = FailedSelector(
                failed_selector=selector,
                site=site,
                working_selector=working_alternative,
                failure_reason=reason
            )

        self._save_selectors()
        logger.info(f"[NEGATIVE] Recorded selector failure: {selector} on {site}")

    def add_negative_example(self,
                              task_prompt: str,
                              task_category: str,
                              site: str,
                              failed_output: str,
                              failure_reason: str,
                              evidence: Dict):
        """
        Add a verified failure as a negative example.

        These are gold for learning what NOT to do.
        """
        example = NegativeExample(
            task_prompt=task_prompt,
            task_category=task_category,
            site=site,
            failed_output=failed_output[:500],
            failure_reason=failure_reason,
            ground_truth_evidence=evidence
        )

        self.negative_examples.append(example)
        self._save_examples()

        # Also record site failure
        self.record_site_failure(site, failure_reason)

        logger.info(f"[NEGATIVE] Added negative example for {site}: {failure_reason[:50]}")

    def get_failed_selectors_for_site(self, site: str) -> List[FailedSelector]:
        """Get all failed selectors for a site."""
        site = site.lower()
        return [
            fs for key, fs in self.failed_selectors.items()
            if fs.site.lower() == site
        ]

    def get_working_alternative(self, selector: str, site: str) -> Optional[str]:
        """Get a working alternative for a failed selector."""
        key = f"{site}:{selector}"
        if key in self.failed_selectors:
            return self.failed_selectors[key].working_selector
        return None

    def get_negative_examples_for_category(self,
                                            category: str,
                                            site: str = None,
                                            limit: int = 5) -> List[NegativeExample]:
        """Get negative examples for prompt injection."""
        examples = [
            ex for ex in self.negative_examples
            if ex.task_category == category
            and (site is None or ex.site == site)
        ]

        # Return most recent
        return examples[-limit:]

    def format_for_prompt(self, site: str, category: str) -> str:
        """
        Format negative examples for injection into LLM prompt.

        This teaches the model what NOT to do.
        """
        lines = []

        # Add failed selectors
        failed = self.get_failed_selectors_for_site(site)
        if failed:
            lines.append("KNOWN BROKEN SELECTORS (do NOT use these):")
            for fs in failed[:10]:
                lines.append(f"  ✗ {fs.failed_selector} - {fs.failure_reason[:50]}")
                if fs.working_selector:
                    lines.append(f"    → Use instead: {fs.working_selector}")
            lines.append("")

        # Add negative examples
        examples = self.get_negative_examples_for_category(category, site, limit=3)
        if examples:
            lines.append("PREVIOUS FAILURES ON THIS SITE (avoid these mistakes):")
            for ex in examples:
                lines.append(f"  ✗ Task: {ex.task_prompt[:50]}...")
                lines.append(f"    Failed because: {ex.failure_reason[:80]}")
            lines.append("")

        return "\n".join(lines) if lines else ""

    def get_stats(self) -> Dict:
        """Get negative example stats."""
        return {
            'failed_selectors': len(self.failed_selectors),
            'quarantined_sites': len(self.quarantined_sites),
            'negative_examples': len(self.negative_examples),
            'hardcoded_quarantine': len(self.QUARANTINED_SITES),
            'dynamic_quarantine': len(self.quarantined_sites) - len(self.QUARANTINED_SITES)
        }


# Singleton
_store = None

def get_negative_store() -> NegativeExampleStore:
    """Get global negative example store."""
    global _store
    if _store is None:
        _store = NegativeExampleStore()
    return _store
