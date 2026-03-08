"""
Ground Truth Validator - Real verification, not vibes.

Validates that agent actions actually happened and extractions contain real data.
No more confident bullshitting - either the data exists or it doesn't.
"""

import re
import json
from typing import Dict, List, Optional, Tuple, Any
from urllib.parse import urlparse
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from loguru import logger


@dataclass
class ValidationResult:
    """Result of ground truth validation."""
    is_valid: bool
    validation_type: str
    confidence: float  # 0.0 to 1.0
    details: str
    evidence: Dict = field(default_factory=dict)


@dataclass
class ReviewItem:
    """Item queued for human review."""
    task_prompt: str
    claimed_output: str
    page_snapshot: str
    validation_result: ValidationResult
    timestamp: str
    reviewed: bool = False
    human_verdict: Optional[bool] = None


class GroundTruthValidator:
    """
    Validates agent outputs against actual page state.

    No more self-reported success. Either the data is there or it isn't.
    """

    # Sampling rate for human review queue
    REVIEW_SAMPLE_RATE = 0.05  # 5% of "successes" go to review

    def __init__(self):
        self.validation_count = 0
        self.pass_count = 0
        self.fail_count = 0

        # Human review queue
        self.review_queue: List[ReviewItem] = []
        self.review_queue_path = Path("training/review_queue.json")
        self._load_review_queue()

        # Calibration stats from human reviews
        self.false_positive_rate = 0.0
        self.false_negative_rate = 0.0

    def verify_extraction(self,
                          extracted_data: Any,
                          page_content: str,
                          task_type: str = None) -> ValidationResult:
        """
        Verify extracted data actually exists in the page.

        Args:
            extracted_data: What the agent claims to have extracted
            page_content: Actual page text/DOM content
            task_type: Type of extraction for specialized validation

        Returns:
            ValidationResult with pass/fail and evidence
        """
        self.validation_count += 1

        # Normalize page content for matching
        page_lower = page_content.lower() if page_content else ""

        # Check 1: Empty extraction
        if not extracted_data:
            self.fail_count += 1
            return ValidationResult(
                is_valid=False,
                validation_type="extraction",
                confidence=1.0,
                details="Empty extraction - no data returned",
                evidence={"extracted": None, "page_length": len(page_content) if page_content else 0}
            )

        # Check 2: Extract is just error message
        if isinstance(extracted_data, str):
            error_indicators = ['error', 'failed', 'could not', 'unable', 'not found', 'exception']
            if any(ind in extracted_data.lower() for ind in error_indicators):
                self.fail_count += 1
                return ValidationResult(
                    is_valid=False,
                    validation_type="extraction",
                    confidence=0.9,
                    details="Extraction contains error message, not data",
                    evidence={"extracted": extracted_data[:200]}
                )

        # Check 3: Verify extracted items exist in page
        items_to_verify = self._extract_verifiable_items(extracted_data)

        if not items_to_verify:
            # Can't verify - no concrete items found
            # This is suspicious but not definitive failure
            return ValidationResult(
                is_valid=False,
                validation_type="extraction",
                confidence=0.6,
                details="No verifiable data items found in extraction",
                evidence={"extracted_type": type(extracted_data).__name__}
            )

        # Verify each item exists in page
        verified_count = 0
        failed_items = []

        for item in items_to_verify[:10]:  # Check first 10
            item_lower = item.lower().strip()
            if len(item_lower) < 3:
                continue  # Too short to verify

            if item_lower in page_lower:
                verified_count += 1
            else:
                # Try fuzzy match for slight variations
                if self._fuzzy_match(item_lower, page_lower):
                    verified_count += 1
                else:
                    failed_items.append(item)

        total_checked = min(len(items_to_verify), 10)
        if total_checked == 0:
            self.fail_count += 1
            return ValidationResult(
                is_valid=False,
                validation_type="extraction",
                confidence=0.7,
                details="No items long enough to verify",
                evidence={"items": items_to_verify[:5]}
            )

        verification_rate = verified_count / total_checked

        if verification_rate >= 0.9:  # 90% of items verified - strict threshold to prevent hallucinations
            self.pass_count += 1
            return ValidationResult(
                is_valid=True,
                validation_type="extraction",
                confidence=verification_rate,
                details=f"Verified {verified_count}/{total_checked} items exist in page",
                evidence={"verified": verified_count, "total": total_checked}
            )
        else:
            self.fail_count += 1
            return ValidationResult(
                is_valid=False,
                validation_type="extraction",
                confidence=1.0 - verification_rate,
                details=f"Only {verified_count}/{total_checked} items found in page - likely hallucinated",
                evidence={"failed_items": failed_items[:5], "verified": verified_count}
            )

    def verify_navigation(self,
                          intended_url: str,
                          actual_url: str,
                          page_title: str = None) -> ValidationResult:
        """
        Verify navigation actually went to intended destination.

        Catches the URL confusion bug where agent navigates somewhere
        but ends up on a different page.
        """
        self.validation_count += 1

        if not intended_url or not actual_url:
            self.fail_count += 1
            return ValidationResult(
                is_valid=False,
                validation_type="navigation",
                confidence=1.0,
                details="Missing URL data for verification",
                evidence={"intended": intended_url, "actual": actual_url}
            )

        # Parse URLs
        intended_parsed = urlparse(intended_url.lower())
        actual_parsed = urlparse(actual_url.lower())

        # Extract domains (handle www variants)
        intended_domain = intended_parsed.netloc.replace('www.', '')
        actual_domain = actual_parsed.netloc.replace('www.', '')

        # Check 1: Domain must match
        if intended_domain != actual_domain:
            self.fail_count += 1
            return ValidationResult(
                is_valid=False,
                validation_type="navigation",
                confidence=1.0,
                details=f"Domain mismatch: intended {intended_domain}, got {actual_domain}",
                evidence={"intended": intended_url, "actual": actual_url}
            )

        # Check 2: Path should reasonably match (for specific pages)
        intended_path = intended_parsed.path.strip('/')
        actual_path = actual_parsed.path.strip('/')

        # If intended was specific page, actual should match
        if intended_path and len(intended_path) > 1:
            # Allow for redirects to similar pages
            path_match = (
                actual_path == intended_path or
                actual_path.startswith(intended_path) or
                intended_path in actual_path
            )

            if not path_match:
                # Might be a redirect - partial failure
                self.pass_count += 1  # Still count as pass if domain matched
                return ValidationResult(
                    is_valid=True,
                    validation_type="navigation",
                    confidence=0.7,
                    details=f"Domain correct but path differs (possible redirect)",
                    evidence={"intended_path": intended_path, "actual_path": actual_path}
                )

        self.pass_count += 1
        return ValidationResult(
            is_valid=True,
            validation_type="navigation",
            confidence=1.0,
            details="Navigation verified - correct destination",
            evidence={"domain": actual_domain, "path": actual_path}
        )

    def verify_action(self,
                      action_type: str,
                      action_params: Dict,
                      before_state: str,
                      after_state: str) -> ValidationResult:
        """
        Verify an action (click, type, etc.) actually had effect.

        Compares page state before and after to detect if anything changed.
        """
        self.validation_count += 1

        if not before_state or not after_state:
            # Can't verify without state comparison
            return ValidationResult(
                is_valid=True,  # Assume valid if we can't check
                validation_type="action",
                confidence=0.5,
                details="Cannot verify - missing state data",
                evidence={"action": action_type}
            )

        # Check if page state changed
        state_changed = before_state != after_state

        if action_type in ['click', 'type', 'fill', 'submit']:
            # These actions SHOULD change something
            if state_changed:
                self.pass_count += 1
                return ValidationResult(
                    is_valid=True,
                    validation_type="action",
                    confidence=0.9,
                    details=f"Action '{action_type}' caused page state change",
                    evidence={"state_changed": True}
                )
            else:
                self.fail_count += 1
                return ValidationResult(
                    is_valid=False,
                    validation_type="action",
                    confidence=0.8,
                    details=f"Action '{action_type}' had no effect - element may not exist",
                    evidence={"state_changed": False, "params": action_params}
                )

        # For other actions (scroll, hover), state change is optional
        self.pass_count += 1
        return ValidationResult(
            is_valid=True,
            validation_type="action",
            confidence=0.7,
            details=f"Action '{action_type}' executed (effect not required)",
            evidence={"state_changed": state_changed}
        )

    def _extract_verifiable_items(self, data: Any) -> List[str]:
        """Extract concrete strings that can be verified against page."""
        items = []

        if isinstance(data, str):
            # Extract meaningful phrases (not just keywords)
            # Split by common delimiters
            parts = re.split(r'[,\n\r\t|•\-]', data)
            for part in parts:
                cleaned = part.strip()
                if len(cleaned) >= 5 and not self._is_boilerplate(cleaned):
                    items.append(cleaned)

        elif isinstance(data, list):
            for item in data:
                if isinstance(item, str) and len(item) >= 5:
                    items.append(item.strip())
                elif isinstance(item, dict):
                    # Extract values from dict
                    for v in item.values():
                        if isinstance(v, str) and len(v) >= 5:
                            items.append(v.strip())

        elif isinstance(data, dict):
            for v in data.values():
                if isinstance(v, str) and len(v) >= 5:
                    items.append(v.strip())

        return items

    def _is_boilerplate(self, text: str) -> bool:
        """Check if text is boilerplate/template, not real data."""
        boilerplate = [
            'successfully', 'extracted', 'found', 'completed',
            'the data', 'the results', 'here are', 'i have',
            'error', 'failed', 'could not'
        ]
        text_lower = text.lower()
        return any(bp in text_lower for bp in boilerplate)

    def _fuzzy_match(self, needle: str, haystack: str, threshold: float = 0.95) -> bool:
        """Check if needle approximately exists in haystack."""
        # Critical fields require exact matches
        if self._is_critical_field(needle):
            logger.debug(f"[VALIDATOR] Critical field detected, requiring exact match: {needle[:50]}")
            return needle in haystack

        # Simple word overlap check
        needle_words = set(needle.split())

        # Check if most words appear somewhere in haystack
        matches = sum(1 for w in needle_words if w in haystack)

        if len(needle_words) == 0:
            return False

        match_rate = matches / len(needle_words)
        if match_rate >= threshold and match_rate < 1.0:
            logger.info(f"[VALIDATOR] Fuzzy match used: {match_rate:.2%} similarity for '{needle[:50]}'")

        return match_rate >= threshold

    def _is_critical_field(self, text: str) -> bool:
        """Check if text contains critical data that requires exact matching."""
        # Email pattern
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        if re.search(email_pattern, text):
            return True

        # Phone number pattern (various formats)
        phone_pattern = r'(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}'
        if re.search(phone_pattern, text):
            return True

        # SSN pattern
        ssn_pattern = r'\b\d{3}-\d{2}-\d{4}\b'
        if re.search(ssn_pattern, text):
            return True

        # Credit card pattern
        cc_pattern = r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b'
        if re.search(cc_pattern, text):
            return True

        return False

    def queue_for_review(self,
                         task_prompt: str,
                         claimed_output: str,
                         page_snapshot: str,
                         validation_result: ValidationResult):
        """Add item to human review queue for calibration."""
        item = ReviewItem(
            task_prompt=task_prompt,
            claimed_output=claimed_output[:500],
            page_snapshot=page_snapshot[:1000] if page_snapshot else "",
            validation_result=validation_result,
            timestamp=datetime.now().isoformat()
        )

        self.review_queue.append(item)
        self._save_review_queue()

        logger.debug(f"[VALIDATOR] Queued item for review (queue size: {len(self.review_queue)})")

    def should_sample_for_review(self) -> bool:
        """Determine if this result should be sampled for human review."""
        import random
        return random.random() < self.REVIEW_SAMPLE_RATE

    def _load_review_queue(self):
        """Load existing review queue from disk."""
        if self.review_queue_path.exists():
            try:
                with open(self.review_queue_path) as f:
                    data = json.load(f)
                    # Reconstruct ReviewItems
                    for item_data in data:
                        val_data = item_data.pop('validation_result', {})
                        validation = ValidationResult(**val_data) if val_data else None
                        item = ReviewItem(**item_data, validation_result=validation)
                        self.review_queue.append(item)
            except Exception as e:
                logger.warning(f"Could not load review queue: {e}")

    def _save_review_queue(self):
        """Save review queue to disk."""
        try:
            self.review_queue_path.parent.mkdir(parents=True, exist_ok=True)

            data = []
            for item in self.review_queue[-100:]:  # Keep last 100
                item_dict = {
                    'task_prompt': item.task_prompt,
                    'claimed_output': item.claimed_output,
                    'page_snapshot': item.page_snapshot,
                    'validation_result': {
                        'is_valid': item.validation_result.is_valid,
                        'validation_type': item.validation_result.validation_type,
                        'confidence': item.validation_result.confidence,
                        'details': item.validation_result.details,
                        'evidence': item.validation_result.evidence
                    } if item.validation_result else None,
                    'timestamp': item.timestamp,
                    'reviewed': item.reviewed,
                    'human_verdict': item.human_verdict
                }
                data.append(item_dict)

            with open(self.review_queue_path, 'w') as f:
                json.dump(data, f, indent=2)

        except Exception as e:
            logger.warning(f"Could not save review queue: {e}")

    def get_stats(self) -> Dict:
        """Get validation statistics."""
        total = self.validation_count
        return {
            'total_validations': total,
            'passed': self.pass_count,
            'failed': self.fail_count,
            'pass_rate': self.pass_count / total if total > 0 else 0,
            'review_queue_size': len(self.review_queue),
            'pending_reviews': sum(1 for r in self.review_queue if not r.reviewed)
        }


# Singleton
_validator = None

def get_ground_truth_validator() -> GroundTruthValidator:
    """Get global ground truth validator instance."""
    global _validator
    if _validator is None:
        _validator = GroundTruthValidator()
    return _validator
