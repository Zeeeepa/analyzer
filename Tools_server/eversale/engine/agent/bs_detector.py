"""
Output Integrity Validator - Self-Verification Protocol

Detects when the agent:
1. Claims task completion without verification
2. Extracts data that doesn't exist on page
3. Reports success despite tool failures
4. Generates non-existent selectors, URLs, or content

Triggers autonomous self-correction when anomalies detected.
"""

import re
from typing import Dict, List, Optional, Tuple
from loguru import logger


class IntegrityValidator:
    """
    Output Integrity Validation Protocol.

    Autonomous verification system that detects and corrects
    hallucinated outputs and unverified claims.
    """

    # Anomaly patterns indicating potential output integrity issues
    HALLUCINATION_PATTERNS = [
        # Fake success claims
        (r'successfully (extracted|clicked|found|navigated)', 'success_claim'),
        (r'I have (extracted|found|completed|done)', 'completion_claim'),
        (r'here (is|are) the (data|results|information)', 'data_claim'),

        # Placeholder data (not real)
        (r'example@', 'fake_email'),
        (r'john\.?doe|jane\.?doe', 'fake_name'),
        (r'123.*street|fake.*address', 'fake_address'),
        (r'\$\d+\.\d{2}(?!\d)', 'suspicious_price'),  # Exact cents often fake
        (r'lorem ipsum', 'placeholder_text'),
        (r'test@test|user@example', 'test_email'),

        # Vague non-answers
        (r'I (could not|couldn\'t|was unable to|cannot) (find|extract|access)', 'admission_of_failure'),
        (r'no (data|results|information) (found|available|visible)', 'no_data'),
        (r'the page (is|appears to be) (empty|blank|loading)', 'empty_page'),
    ]

    # Minimum thresholds for "real" data
    MIN_EXTRACTED_ITEMS = 1
    MIN_TEXT_LENGTH = 10
    SUSPICIOUS_REPETITION_THRESHOLD = 3  # Same value repeated = suspicious

    def __init__(self):
        self.anomaly_count = 0
        self.validations = []

    def verify_output(self,
                      claimed_output: str,
                      actual_page_content: str = None,
                      tool_results: List[Dict] = None,
                      task_type: str = None) -> Tuple[bool, str, str]:
        """
        Validate output integrity against ground truth.

        Returns:
            (is_valid, issue_type, correction_hint)
        """
        issues = []

        # Check 1: Empty or too short output
        if not claimed_output or len(claimed_output.strip()) < 20:
            issues.append(('empty_output', 'Output is empty or too short'))

        # Check 2: Scan for hallucination patterns
        for pattern, issue_type in self.HALLUCINATION_PATTERNS:
            if re.search(pattern, claimed_output, re.IGNORECASE):
                # Found a pattern - but is it actually BS?
                if issue_type == 'success_claim':
                    # Verify against tool results
                    if tool_results and self._check_tool_failures(tool_results):
                        issues.append((issue_type, 'Claims success but tools show failures'))

                elif issue_type in ['fake_email', 'fake_name', 'test_email']:
                    issues.append((issue_type, f'Detected likely placeholder/fake data'))

                elif issue_type == 'admission_of_failure':
                    # Agent admits failure - not BS, but should retry differently
                    issues.append((issue_type, 'Agent admits it failed - needs different approach'))

                elif issue_type == 'no_data':
                    # Verify page wasn't actually empty
                    if actual_page_content and len(actual_page_content) > 500:
                        issues.append((issue_type, 'Claims no data but page has content'))

        # Check 3: Data extraction verification
        if task_type in ['extraction', 'extract', 'scrape']:
            extraction_issues = self._verify_extraction(claimed_output, actual_page_content)
            issues.extend(extraction_issues)

        # Check 4: Suspicious repetition (same data repeated = likely hallucinated)
        repetition_issue = self._check_repetition(claimed_output)
        if repetition_issue:
            issues.append(repetition_issue)

        # Check 5: Cross-reference with page content
        if actual_page_content:
            content_issues = self._cross_reference(claimed_output, actual_page_content)
            issues.extend(content_issues)

        # Determine result
        if issues:
            self.anomaly_count += 1
            issue_types = [i[0] for i in issues]
            issue_messages = [i[1] for i in issues]

            self.validations.append({
                'output_snippet': claimed_output[:100],
                'issues': issues
            })

            correction_hint = self._generate_correction_hint(issues)

            logger.warning(f"[INTEGRITY] Anomalies detected: {issue_types}")
            return False, ', '.join(issue_types), correction_hint

        return True, None, None

    def _check_tool_failures(self, tool_results: List[Dict]) -> bool:
        """Check if any tools actually failed."""
        for result in tool_results:
            content = str(result.get('content', '')).lower()
            if any(err in content for err in ['error', 'failed', 'not found', 'timeout', 'exception']):
                return True
        return False

    def _verify_extraction(self, output: str, page_content: str = None) -> List[Tuple[str, str]]:
        """Verify extraction claims are legitimate."""
        issues = []

        # Look for extracted data patterns
        # If claiming to extract list of items, verify count
        list_patterns = [
            r'(\d+)\s*(items?|results?|entries|records)',
            r'found\s*(\d+)',
            r'extracted\s*(\d+)',
        ]

        for pattern in list_patterns:
            match = re.search(pattern, output, re.IGNORECASE)
            if match:
                claimed_count = int(match.group(1))
                if claimed_count == 0:
                    issues.append(('zero_extraction', 'Claims to have extracted 0 items'))
                elif claimed_count > 100:
                    # Suspiciously high - verify
                    actual_items = output.count('\n') + output.count(',')
                    if actual_items < claimed_count / 2:
                        issues.append(('inflated_count', f'Claims {claimed_count} items but output suggests fewer'))

        return issues

    def _check_repetition(self, output: str) -> Optional[Tuple[str, str]]:
        """Detect suspicious repetition (sign of hallucination)."""
        # Split into lines/items
        lines = [l.strip() for l in output.split('\n') if l.strip()]

        if len(lines) < 3:
            return None

        # Count duplicates
        from collections import Counter
        counts = Counter(lines)

        most_common = counts.most_common(1)
        if most_common and most_common[0][1] >= self.SUSPICIOUS_REPETITION_THRESHOLD:
            repeated = most_common[0][0]
            count = most_common[0][1]
            return ('suspicious_repetition', f'Same value "{repeated[:30]}..." repeated {count} times')

        return None

    def _cross_reference(self, output: str, page_content: str) -> List[Tuple[str, str]]:
        """Cross-reference claimed data with actual page content."""
        issues = []

        # Extract potential data items from output (names, emails, titles, etc.)
        # Check if they exist in page content

        # Email check
        emails_in_output = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', output)
        for email in emails_in_output[:5]:  # Check first 5
            if email.lower() not in page_content.lower():
                # Email not in page - might be hallucinated
                if not any(test in email.lower() for test in ['example', 'test', 'fake', 'sample']):
                    issues.append(('unverified_email', f'Email {email} not found in page content'))

        # URL check
        urls_in_output = re.findall(r'https?://[^\s<>"]+', output)
        for url in urls_in_output[:3]:  # Check first 3
            domain = re.search(r'https?://([^/]+)', url)
            if domain and domain.group(1) not in page_content:
                # Might be hallucinated URL
                pass  # URLs are often not in visible text, skip this check

        return issues

    def _generate_correction_hint(self, issues: List[Tuple[str, str]]) -> str:
        """Generate a hint for how to fix the BS."""
        hints = []

        issue_types = [i[0] for i in issues]

        if 'success_claim' in issue_types or 'completion_claim' in issue_types:
            hints.append("Don't claim success - verify with a screenshot or re-check the page")

        if 'fake_email' in issue_types or 'fake_name' in issue_types or 'test_email' in issue_types:
            hints.append("Extract REAL data from the page, not placeholder examples")

        if 'admission_of_failure' in issue_types or 'no_data' in issue_types:
            hints.append("Try a different approach: scroll down, wait longer, or use different selectors")

        if 'suspicious_repetition' in issue_types:
            hints.append("Data looks repeated/fake - re-extract from actual page elements")

        if 'unverified_email' in issue_types:
            hints.append("Verify extracted data exists on the page before reporting it")

        if 'empty_output' in issue_types:
            hints.append("Provide actual results, not empty response")

        if 'inflated_count' in issue_types:
            hints.append("Count doesn't match actual extracted items - recount")

        return '; '.join(hints) if hints else "Re-verify your output against the actual page"

    def create_correction_prompt(self, original_output: str, issues: str, hint: str) -> str:
        """Create a prompt to trigger autonomous self-correction."""
        return f"""INTEGRITY CORRECTION PROTOCOL ACTIVATED

Output integrity check failed: {issues}

Previous output:
{original_output[:500]}

Issues identified:
- {hint}

Correction protocol:
1. Capture current page state via screenshot
2. Re-extract data from verified page elements
3. Report only confirmed, verifiable data
4. If data unavailable, document reason and adjust approach

Verification required before output. Unverified claims prohibited.
"""

    def get_stats(self) -> Dict:
        """Get integrity validation statistics."""
        return {
            'anomalies_detected': self.anomaly_count,
            'recent_issues': [v['issues'][0][0] for v in self.validations[-5:]] if self.validations else []
        }


# Singleton for easy access
_validator = None

def get_integrity_validator() -> IntegrityValidator:
    """Get the global integrity validator instance."""
    global _validator
    if _validator is None:
        _validator = IntegrityValidator()
    return _validator


# Backward compatibility alias
def get_bs_detector() -> IntegrityValidator:
    """Deprecated: Use get_integrity_validator instead."""
    return get_integrity_validator()
