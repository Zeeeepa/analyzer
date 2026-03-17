"""
Pre-Execution Validator
Validates actions BEFORE they execute (like Claude Code's Haiku safety check).

Key insight from Claude Code:
- Send commands to a FAST model (Haiku) before execution
- Validates safety, correctness, and appropriateness
- Fail-closed: Unknown commands require approval

This catches mistakes BEFORE they happen, not after.

Integration with Hallucination Guard:
- Validates data-producing actions for hallucination patterns
- Checks confidence scores from LLM extractions
- Combines safety validation with data quality validation
- Provides unified ALLOW/DENY/MODIFY logic
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
import re
import logging

logger = logging.getLogger(__name__)

# Import hallucination guard for data validation
try:
    import agent.hallucination_guard as hallucination_guard_module
    HallucinationGuard = hallucination_guard_module.HallucinationGuard
    HallucinationValidationResult = hallucination_guard_module.ValidationResult
    HALLUCINATION_GUARD_AVAILABLE = True
except ImportError as e:
    logger.warning(f"hallucination_guard module not available - hallucination checks disabled: {e}")
    HALLUCINATION_GUARD_AVAILABLE = False
    HallucinationGuard = None
    HallucinationValidationResult = None

# Import config loader for settings
try:
    import agent.config_loader as config_loader_module
    get_validator_setting = config_loader_module.get_validator_setting
    get_hallucination_guard_setting = config_loader_module.get_hallucination_guard_setting
except ImportError as e:
    logger.warning(f"config_loader module not available - using default settings: {e}")
    def get_validator_setting(key: str, default: Any = None) -> Any:
        return default
    def get_hallucination_guard_setting(key: str, default: Any = None) -> Any:
        return default

class ValidationResult(Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRES_APPROVAL = "requires_approval"
    MODIFY = "modify"  # Allow with modifications

@dataclass
class ValidationOutput:
    """Result of pre-execution validation."""
    result: ValidationResult
    reason: str
    modified_action: Optional[Dict] = None
    risk_level: str = "low"  # low, medium, high, critical
    suggestions: List[str] = field(default_factory=list)
    # Enhanced fields for hallucination detection
    hallucination_issues: List[str] = field(default_factory=list)
    data_confidence: Optional[float] = None  # 0.0-1.0
    data_provenance: Optional[Dict[str, Any]] = None
    cleaned_data: Optional[Any] = None

class PreExecutionValidator:
    """
    Validates actions before execution.

    Checks:
    1. Safety - Is this action dangerous?
    2. Correctness - Will this likely work?
    3. Appropriateness - Is this what the user wants?
    4. Efficiency - Is there a better way?

    Usage:
        validator = PreExecutionValidator()
        result = validator.validate(action, context)

        if result.result == ValidationResult.ALLOW:
            execute(action)
        elif result.result == ValidationResult.MODIFY:
            execute(result.modified_action)
        elif result.result == ValidationResult.REQUIRES_APPROVAL:
            if await ask_user(result.reason):
                execute(action)
    """

    # Dangerous patterns that should be blocked or require approval
    DANGEROUS_PATTERNS = {
        # System commands
        r'\brm\s+-rf\b': ("DENY", "Recursive delete is dangerous"),
        r'\bsudo\b': ("REQUIRES_APPROVAL", "Requires elevated privileges"),
        r'\b(chmod|chown)\s+777\b': ("DENY", "Insecure permissions"),
        r'\bformat\b.*\b(c:|d:)\b': ("DENY", "Disk formatting"),

        # Web actions
        r'\bdelete.*account\b': ("REQUIRES_APPROVAL", "Account deletion"),
        r'\b(purchase|buy|order|checkout)\b': ("REQUIRES_APPROVAL", "Financial action"),
        r'\bpayment\b': ("REQUIRES_APPROVAL", "Payment action"),
        r'\b(password|credential|api.?key|secret)\b': ("REQUIRES_APPROVAL", "Sensitive data"),

        # Email/messaging
        r'\bsend.*email.*all\b': ("REQUIRES_APPROVAL", "Mass email"),
        r'\breply.*all\b': ("REQUIRES_APPROVAL", "Reply all"),
    }

    # Always allowed patterns
    SAFE_PATTERNS = {
        r'^playwright_navigate$',
        r'^playwright_click$',
        r'^playwright_fill$',
        r'^playwright_snapshot$',
        r'^playwright_screenshot$',
        r'^playwright_get_markdown$',
        r'^playwright_scroll$',
    }

    def __init__(
        self,
        use_llm_validation: bool = None,
        enable_hallucination_guard: bool = None,
        hallucination_strict_mode: bool = None
    ):
        """
        Initialize the pre-execution validator.

        Args:
            use_llm_validation: Enable LLM-based validation (None = use config)
            enable_hallucination_guard: Enable hallucination detection (None = use config)
            hallucination_strict_mode: Strict mode for hallucination (None = use config)
        """
        # Load from config if not specified
        if use_llm_validation is None:
            use_llm_validation = get_validator_setting('use_llm_validation', False)
        if enable_hallucination_guard is None:
            enable_hallucination_guard = get_hallucination_guard_setting('enabled', True)
        if hallucination_strict_mode is None:
            hallucination_strict_mode = get_hallucination_guard_setting('strict_mode', True)

        self.use_llm_validation = use_llm_validation
        self.enable_hallucination_guard = enable_hallucination_guard and HALLUCINATION_GUARD_AVAILABLE
        self.min_confidence_threshold = get_hallucination_guard_setting('min_confidence_threshold', 0.5)
        self.validate_llm_outputs = get_hallucination_guard_setting('validate_llm_outputs', True)
        self.validate_extracted_data = get_hallucination_guard_setting('validate_extracted_data', True)
        self.approval_cache: Dict[str, bool] = {}
        self.validation_history: List[ValidationOutput] = []

        # Initialize hallucination guard if enabled
        self.hallucination_guard = None
        if self.enable_hallucination_guard:
            self.hallucination_guard = HallucinationGuard(strict_mode=hallucination_strict_mode)
            logger.info(
                f"Hallucination guard enabled - "
                f"strict_mode={hallucination_strict_mode}, "
                f"min_confidence={self.min_confidence_threshold}"
            )
        else:
            if not HALLUCINATION_GUARD_AVAILABLE:
                logger.warning("Hallucination guard not available - module import failed")
            else:
                logger.info("Hallucination guard disabled by configuration")

    def validate(self, action: Dict, context: Optional[Dict] = None) -> ValidationOutput:
        """
        Validate an action before execution.

        Args:
            action: The action to validate (tool_name, parameters)
            context: Current task context for smarter validation

        Returns:
            ValidationOutput with decision and reasoning
        """
        tool_name = action.get("name", action.get("tool", ""))
        params = action.get("parameters", action.get("args", {}))

        # Check if always safe
        if self._is_safe_action(tool_name):
            return ValidationOutput(
                result=ValidationResult.ALLOW,
                reason="Known safe action",
                risk_level="low"
            )

        # Check for dangerous patterns
        danger_result = self._check_dangerous_patterns(tool_name, params)
        if danger_result:
            return danger_result

        # Check parameter validity
        param_result = self._validate_parameters(tool_name, params)
        if param_result.result != ValidationResult.ALLOW:
            return param_result

        # Check for common mistakes
        mistake_result = self._check_common_mistakes(tool_name, params, context)
        if mistake_result:
            return mistake_result

        # Default: allow with low risk
        return ValidationOutput(
            result=ValidationResult.ALLOW,
            reason="No issues detected",
            risk_level="low"
        )

    def validate_action_output(
        self,
        action: Dict,
        output_data: Any,
        context: Optional[Dict] = None
    ) -> ValidationOutput:
        """
        Validate action output for hallucination after execution.

        This is called AFTER an action produces data to check for hallucinated content.
        Integrates with hallucination_guard for comprehensive validation.

        Args:
            action: The action that was executed
            output_data: The data produced by the action
            context: Execution context with metadata

        Returns:
            ValidationOutput with hallucination check results
        """
        tool_name = action.get("name", action.get("tool", ""))
        params = action.get("parameters", action.get("args", {}))

        # If hallucination guard is disabled, skip data validation
        if not self.enable_hallucination_guard or not self.hallucination_guard:
            return ValidationOutput(
                result=ValidationResult.ALLOW,
                reason="Hallucination guard disabled",
                risk_level="low"
            )

        # Only validate actions that produce data
        if not self._is_data_producing_action(tool_name):
            return ValidationOutput(
                result=ValidationResult.ALLOW,
                reason="Action does not produce data requiring validation",
                risk_level="low"
            )

        # Extract metadata from context
        source_url = None
        page_title = None
        extraction_method = None
        confidence_score = None
        metadata = {}

        if context:
            source_url = context.get("url") or context.get("source_url")
            page_title = context.get("page_title")
            extraction_method = context.get("extraction_method")
            confidence_score = context.get("confidence_score")
            metadata = context.get("metadata", {})

        # Also check params for URL
        if not source_url:
            source_url = params.get("url") or params.get("source_url")

        # Determine data type from tool name or context
        data_type = self._infer_data_type(tool_name, params, output_data)

        # Run hallucination guard validation
        try:
            hallucination_result = self.hallucination_guard.validate_output(
                data=output_data,
                source_tool=tool_name,
                source_url=source_url,
                data_type=data_type,
                page_title=page_title,
                extraction_method=extraction_method,
                confidence_score=confidence_score,
                metadata=metadata
            )

            # Calculate combined confidence score
            combined_confidence = self._calculate_combined_confidence(
                hallucination_result,
                confidence_score
            )

            # Determine validation result based on hallucination check
            if hallucination_result.is_valid:
                # Check if confidence meets threshold
                if combined_confidence < self.min_confidence_threshold:
                    return ValidationOutput(
                        result=ValidationResult.REQUIRES_APPROVAL,
                        reason=f"Data confidence ({combined_confidence:.2f}) below threshold ({self.min_confidence_threshold})",
                        risk_level="medium",
                        hallucination_issues=[],
                        data_confidence=combined_confidence,
                        data_provenance=self._build_provenance_dict(hallucination_result),
                        cleaned_data=hallucination_result.cleaned_data,
                        suggestions=["Low confidence data - manual review recommended"]
                    )

                return ValidationOutput(
                    result=ValidationResult.ALLOW,
                    reason="Data validation passed - no hallucination detected",
                    risk_level="low",
                    hallucination_issues=[],
                    data_confidence=combined_confidence,
                    data_provenance=self._build_provenance_dict(hallucination_result),
                    cleaned_data=hallucination_result.cleaned_data
                )
            else:
                # Hallucination detected
                issues = hallucination_result.issues
                severity = self._assess_hallucination_severity(issues)

                # Determine if we should DENY or MODIFY
                if severity == "critical":
                    return ValidationOutput(
                        result=ValidationResult.DENY,
                        reason=f"Critical hallucination detected: {'; '.join(issues[:3])}",
                        risk_level="critical",
                        hallucination_issues=issues,
                        data_confidence=combined_confidence,
                        data_provenance=self._build_provenance_dict(hallucination_result)
                    )
                elif severity == "high" and hallucination_result.cleaned_data:
                    # Can modify by using cleaned data
                    return ValidationOutput(
                        result=ValidationResult.MODIFY,
                        reason=f"Hallucination detected but data can be cleaned: {'; '.join(issues[:2])}",
                        risk_level="high",
                        hallucination_issues=issues,
                        data_confidence=combined_confidence,
                        data_provenance=self._build_provenance_dict(hallucination_result),
                        cleaned_data=hallucination_result.cleaned_data,
                        suggestions=["Using sanitized data with hallucinated content removed"]
                    )
                else:
                    # Medium/low severity - require approval
                    return ValidationOutput(
                        result=ValidationResult.REQUIRES_APPROVAL,
                        reason=f"Potential hallucination detected: {'; '.join(issues[:2])}",
                        risk_level="medium",
                        hallucination_issues=issues,
                        data_confidence=combined_confidence,
                        data_provenance=self._build_provenance_dict(hallucination_result),
                        suggestions=["Review data carefully before using"]
                    )

        except Exception as e:
            logger.error(f"Hallucination guard validation failed: {e}", exc_info=True)
            return ValidationOutput(
                result=ValidationResult.REQUIRES_APPROVAL,
                reason=f"Hallucination validation error: {str(e)}",
                risk_level="high",
                suggestions=["Manual review required due to validation error"]
            )

    def _is_safe_action(self, tool_name: str) -> bool:
        """Check if action is in the safe list."""
        for pattern in self.SAFE_PATTERNS:
            if re.match(pattern, tool_name):
                return True
        return False

    def _check_dangerous_patterns(self, tool_name: str, params: Dict) -> Optional[ValidationOutput]:
        """Check for dangerous patterns in action or parameters."""
        # Combine all text to check
        text_to_check = f"{tool_name} {str(params)}".lower()

        for pattern, (result_type, reason) in self.DANGEROUS_PATTERNS.items():
            if re.search(pattern, text_to_check, re.IGNORECASE):
                return ValidationOutput(
                    result=ValidationResult[result_type],
                    reason=reason,
                    risk_level="high" if result_type == "DENY" else "medium"
                )

        return None

    def _validate_parameters(self, tool_name: str, params: Dict) -> ValidationOutput:
        """Validate parameter correctness."""
        issues = []

        # Check for empty required parameters
        if tool_name == "playwright_navigate":
            url = params.get("url", "")
            if not url:
                issues.append("URL is required for navigation")
            elif not url.startswith(("http://", "https://")):
                return ValidationOutput(
                    result=ValidationResult.MODIFY,
                    reason="URL should include protocol",
                    modified_action={"name": tool_name, "parameters": {**params, "url": f"https://{url}"}},
                    risk_level="low",
                    suggestions=["Added https:// prefix"]
                )

        if tool_name == "playwright_fill":
            if not params.get("value") and not params.get("text"):
                issues.append("No text provided for fill action")

        if tool_name == "playwright_click":
            if not params.get("selector") and not params.get("element"):
                issues.append("No selector or element specified for click")

        if issues:
            return ValidationOutput(
                result=ValidationResult.DENY,
                reason="; ".join(issues),
                risk_level="medium"
            )

        return ValidationOutput(
            result=ValidationResult.ALLOW,
            reason="Parameters valid",
            risk_level="low"
        )

    def _check_common_mistakes(self, tool_name: str, params: Dict,
                               context: Optional[Dict]) -> Optional[ValidationOutput]:
        """Check for common mistakes."""
        suggestions = []

        # Clicking without waiting
        if tool_name == "playwright_click" and context:
            last_action = context.get("last_action", {})
            if last_action.get("name") == "playwright_navigate":
                suggestions.append("Consider waiting for page load after navigation")

        # Filling without clearing
        if tool_name == "playwright_fill":
            if params.get("clear", None) is None:
                suggestions.append("Consider adding clear=True to clear existing text")

        if suggestions:
            return ValidationOutput(
                result=ValidationResult.ALLOW,  # Allow but suggest
                reason="Action allowed with suggestions",
                risk_level="low",
                suggestions=suggestions
            )

        return None

    def request_approval(self, action: Dict, reason: str) -> Tuple[bool, str]:
        """
        Request user approval for action.
        Returns (approved, response).

        In production, this would show a UI prompt.
        """
        cache_key = f"{action.get('name')}:{reason}"

        # Check cache
        if cache_key in self.approval_cache:
            cached = self.approval_cache[cache_key]
            return cached, "Using cached approval"

        # For now, log and allow (in production, would prompt user)
        logger.warning(f"[PRE-VALIDATE] Action requires approval: {reason}")
        logger.warning(f"[PRE-VALIDATE] Action: {action}")

        # Default to requiring explicit approval
        return False, "Approval required"

    def validate_batch(self, actions: List[Dict], context: Optional[Dict] = None) -> List[ValidationOutput]:
        """Validate multiple actions at once."""
        results = []
        current_context = context or {}

        for i, action in enumerate(actions):
            result = self.validate(action, current_context)
            results.append(result)

            # Update context for next validation
            current_context["last_action"] = action
            current_context["action_index"] = i

        return results

    def get_validation_summary(self) -> Dict:
        """Get summary of recent validations."""
        total = len(self.validation_history)
        if total == 0:
            return {"total": 0}

        allowed = sum(1 for v in self.validation_history if v.result == ValidationResult.ALLOW)
        denied = sum(1 for v in self.validation_history if v.result == ValidationResult.DENY)
        modified = sum(1 for v in self.validation_history if v.result == ValidationResult.MODIFY)
        approval_needed = sum(1 for v in self.validation_history if v.result == ValidationResult.REQUIRES_APPROVAL)

        # Hallucination-specific stats
        hallucination_detected = sum(1 for v in self.validation_history if v.hallucination_issues)
        avg_confidence = None
        confidence_scores = [v.data_confidence for v in self.validation_history if v.data_confidence is not None]
        if confidence_scores:
            avg_confidence = sum(confidence_scores) / len(confidence_scores)

        return {
            "total": total,
            "allowed": allowed,
            "denied": denied,
            "modified": modified,
            "approval_needed": approval_needed,
            "allow_rate": allowed / total,
            "hallucination_detected": hallucination_detected,
            "average_confidence": avg_confidence
        }

    def _is_data_producing_action(self, tool_name: str) -> bool:
        """
        Check if action produces data that should be validated for hallucination.

        Actions that extract data from web pages, APIs, or use LLMs should be validated.
        """
        data_producing_patterns = [
            r'extract',
            r'scrape',
            r'parse',
            r'get.*data',
            r'get.*entities',
            r'get.*text',
            r'get.*markdown',
            r'llm',
            r'generate',
            r'summarize',
            r'analyze',
        ]

        tool_lower = tool_name.lower()
        for pattern in data_producing_patterns:
            if re.search(pattern, tool_lower):
                return True

        return False

    def _infer_data_type(self, tool_name: str, params: Dict, output_data: Any) -> Optional[str]:
        """
        Infer the type of data being produced for targeted validation.

        Returns: "emails", "phones", "companies", "names", "urls", etc.
        """
        tool_lower = tool_name.lower()

        # Check tool name patterns
        if "email" in tool_lower:
            return "emails"
        if "phone" in tool_lower or "tel" in tool_lower:
            return "phones"
        if "company" in tool_lower or "organization" in tool_lower:
            return "companies"
        if "name" in tool_lower or "contact" in tool_lower:
            return "names"
        if "url" in tool_lower or "link" in tool_lower:
            return "urls"
        if "address" in tool_lower:
            return "addresses"

        # Check parameter hints
        if params:
            param_str = str(params).lower()
            if "email" in param_str:
                return "emails"
            if "phone" in param_str:
                return "phones"

        # Check output data structure
        if isinstance(output_data, dict):
            keys_lower = [k.lower() for k in output_data.keys()]
            if "email" in keys_lower or "emails" in keys_lower:
                return "emails"
            if "phone" in keys_lower or "phones" in keys_lower:
                return "phones"
            if "company" in keys_lower:
                return "companies"

        # Default: no specific type
        return None

    def _calculate_combined_confidence(
        self,
        hallucination_result: Any,
        extraction_confidence: Optional[float]
    ) -> float:
        """
        Calculate combined confidence score from hallucination check and extraction confidence.

        Args:
            hallucination_result: Result from hallucination guard
            extraction_confidence: Confidence from the extraction process (0.0-1.0)

        Returns:
            Combined confidence score (0.0-1.0)
        """
        # Start with extraction confidence or default
        if extraction_confidence is not None:
            base_confidence = extraction_confidence
        else:
            base_confidence = 0.8  # Assume good confidence if not specified

        # Reduce confidence based on hallucination issues
        if not hallucination_result.is_valid:
            issue_count = len(hallucination_result.issues)

            # Each issue reduces confidence
            # Critical issues (instruction leakage, missing provenance) reduce more
            critical_patterns = ["instruction leakage", "missing provenance", "no source"]
            critical_issues = sum(1 for issue in hallucination_result.issues
                                  if any(pattern in issue.lower() for pattern in critical_patterns))

            # Reduce by 0.2 per critical issue, 0.1 per regular issue
            confidence_reduction = (critical_issues * 0.2) + ((issue_count - critical_issues) * 0.1)
            base_confidence = max(0.0, base_confidence - confidence_reduction)

        # Source confidence boost
        if hasattr(hallucination_result, 'source') and hallucination_result.source:
            source = hallucination_result.source
            if source.confidence_score is not None:
                # Average with source confidence
                base_confidence = (base_confidence + source.confidence_score) / 2

        return round(base_confidence, 2)

    def _build_provenance_dict(self, hallucination_result: Any) -> Dict[str, Any]:
        """Build provenance dictionary from hallucination result."""
        if not hasattr(hallucination_result, 'source') or not hallucination_result.source:
            return {}

        source = hallucination_result.source
        return {
            "tool_name": source.tool_name,
            "timestamp": source.timestamp.isoformat() if source.timestamp else None,
            "url": source.url,
            "page_title": source.page_title,
            "extraction_method": source.extraction_method,
            "confidence_score": source.confidence_score,
            "verification_attempts": source.verification_attempts,
            "fallback_used": source.fallback_used,
            "metadata": source.metadata
        }

    def _assess_hallucination_severity(self, issues: List[str]) -> str:
        """
        Assess the severity of hallucination issues.

        Returns: "critical", "high", "medium", or "low"
        """
        critical_patterns = [
            "instruction leakage",
            "missing provenance",
            "no source tool",
            "fake email",
            "fake phone",
            "disposable email"
        ]

        high_patterns = [
            "hallucination phrase",
            "fake company",
            "fake name",
            "low confidence"
        ]

        # Check for critical issues
        for issue in issues:
            issue_lower = issue.lower()
            if any(pattern in issue_lower for pattern in critical_patterns):
                return "critical"

        # Check for high severity issues
        for issue in issues:
            issue_lower = issue.lower()
            if any(pattern in issue_lower for pattern in high_patterns):
                return "high"

        # Medium severity if multiple issues
        if len(issues) > 2:
            return "medium"

        # Low severity otherwise
        return "low"

    def get_hallucination_stats(self) -> Dict[str, Any]:
        """
        Get statistics about hallucination detection.

        Returns summary of hallucination guard performance.
        """
        if not self.enable_hallucination_guard or not self.hallucination_guard:
            return {
                "enabled": False,
                "message": "Hallucination guard is not enabled"
            }

        # Get provenance summary from hallucination guard
        provenance_summary = self.hallucination_guard.get_provenance_summary()

        # Add validation stats
        validations_with_issues = [v for v in self.validation_history if v.hallucination_issues]

        return {
            "enabled": True,
            "strict_mode": self.hallucination_guard.strict_mode,
            "total_data_validations": len([v for v in self.validation_history if v.data_confidence is not None]),
            "hallucinations_detected": len(validations_with_issues),
            "provenance_summary": provenance_summary,
            "recent_issues": [
                {
                    "issues": v.hallucination_issues[:3],
                    "confidence": v.data_confidence,
                    "result": v.result.value
                }
                for v in validations_with_issues[-5:]  # Last 5 issues
            ]
        }


# Global instance
_validator: Optional[PreExecutionValidator] = None

def get_validator() -> PreExecutionValidator:
    """Get global pre-execution validator."""
    global _validator
    if _validator is None:
        _validator = PreExecutionValidator()
    return _validator
