"""
Data Validator - Validate extracted emails, phones, URLs, and other data

Features:
- Email validation (format + MX record check)
- Phone validation (format + country detection)
- URL validation (format + reachability check)
- Company name validation (not placeholder)
- Deduplication with fuzzy matching

This validator ensures that extracted leads are real, actionable data
and filters out hallucinated, fake, or duplicate entries.

Usage:
    from agent.data_validator import DataValidator, validate_leads

    validator = DataValidator()

    # Validate single items
    email_result = validator.validate_email("john@example.com")
    phone_result = validator.validate_phone("+1-555-123-4567")

    # Validate batch of leads
    leads = [
        {"email": "john@acme.com", "company": "Acme Corp"},
        {"email": "jane@acme.com", "company": "Acme Inc"}
    ]
    validated, report = validator.validate_leads(leads)

    # Report shows: duplicates removed, fake emails filtered, etc.
"""

import re
import asyncio
from typing import Dict, List, Any, Optional, Tuple, Set
from dataclasses import dataclass, field
from urllib.parse import urlparse
from loguru import logger

# Import existing infrastructure (use try/except to handle import issues)
try:
    from agent.hallucination_guard import (
        HallucinationGuard,
        DISPOSABLE_EMAIL_DOMAINS,
        FAKE_PATTERNS
    )
    from agent.rust_bridge import extract_emails, extract_phones, USE_RUST_CORE
except ImportError:
    # Direct import when used standalone
    from hallucination_guard import (
        HallucinationGuard,
        DISPOSABLE_EMAIL_DOMAINS,
        FAKE_PATTERNS
    )
    from rust_bridge import extract_emails, extract_phones, USE_RUST_CORE

# Optional dependencies for enhanced validation
try:
    import aiodns
    HAS_AIODNS = True
except ImportError:
    HAS_AIODNS = False
    logger.debug("aiodns not available - MX record validation disabled")

try:
    import phonenumbers
    HAS_PHONENUMBERS = True
except ImportError:
    HAS_PHONENUMBERS = False
    logger.debug("phonenumbers not available - E.164 normalization disabled")

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False
    logger.debug("aiohttp not available - URL reachability check disabled")

# Try to use Rust similarity for fuzzy matching
try:
    import eversale_core
    HAS_RUST_SIMILARITY = USE_RUST_CORE
    logger.debug("Rust similarity available for fuzzy matching")
except (ImportError, AttributeError):
    HAS_RUST_SIMILARITY = False
    logger.debug("Rust similarity not available - using Python difflib")

# Fallback to Python difflib if Rust not available
if not HAS_RUST_SIMILARITY:
    from difflib import SequenceMatcher


# ==============================================================================
# VALIDATION RESULTS
# ==============================================================================

@dataclass
class ValidationResult:
    """Result of validating a single data item."""
    is_valid: bool
    value: Optional[str] = None  # Normalized/cleaned value
    issues: List[str] = field(default_factory=list)
    confidence: float = 1.0  # 0.0-1.0 confidence score
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BatchValidationReport:
    """Report from batch validation of leads."""
    total_input: int = 0
    total_output: int = 0
    duplicates_removed: int = 0
    fake_emails_removed: int = 0
    fake_phones_removed: int = 0
    fake_companies_removed: int = 0
    invalid_urls_removed: int = 0
    disposable_emails_removed: int = 0
    domain_dedup_count: int = 0  # Companies merged by domain
    fuzzy_dedup_count: int = 0  # Companies merged by fuzzy matching
    issues: List[str] = field(default_factory=list)

    def summary(self) -> str:
        """Generate human-readable summary."""
        lines = [
            f"Validation Summary:",
            f"  Input: {self.total_input} leads",
            f"  Output: {self.total_output} leads ({self.total_output/self.total_input*100:.1f}% kept)" if self.total_input > 0 else "  Output: 0 leads",
            f"  Removed:",
            f"    - {self.duplicates_removed} exact duplicates",
            f"    - {self.fake_emails_removed} fake emails",
            f"    - {self.disposable_emails_removed} disposable emails",
            f"    - {self.fake_phones_removed} fake phones",
            f"    - {self.fake_companies_removed} fake companies",
            f"    - {self.invalid_urls_removed} invalid URLs",
            f"  Deduplication:",
            f"    - {self.domain_dedup_count} companies merged by domain",
            f"    - {self.fuzzy_dedup_count} companies merged by fuzzy matching"
        ]
        if self.issues:
            lines.append(f"  Issues: {len(self.issues)}")
            for issue in self.issues[:5]:  # Show first 5
                lines.append(f"    - {issue}")
            if len(self.issues) > 5:
                lines.append(f"    ... and {len(self.issues) - 5} more")
        return "\n".join(lines)


# ==============================================================================
# DATA VALIDATOR
# ==============================================================================

class DataValidator:
    """
    Validates extracted data to ensure quality and remove fakes/duplicates.

    Features:
    1. Email validation: format, disposable domains, optional MX check
    2. Phone validation: format, normalization to E.164, fake pattern detection
    3. URL validation: format, protocol normalization, optional reachability
    4. Company validation: not placeholder, length checks, normalization
    5. Deduplication: exact + fuzzy matching + domain-based

    Example:
        validator = DataValidator(check_mx_records=True)

        # Validate single email
        result = validator.validate_email("john@acme.com")
        if result.is_valid:
            print(f"Valid email: {result.value}")

        # Validate batch of leads
        leads = [{"email": "...", "company": "..."}, ...]
        validated, report = validator.validate_leads(leads)
        print(report.summary())
    """

    def __init__(
        self,
        check_mx_records: bool = False,
        check_url_reachability: bool = False,
        fuzzy_threshold: float = 0.85,
        use_rust: bool = True
    ):
        """
        Initialize validator.

        Args:
            check_mx_records: If True, validate email domains via DNS MX lookup (slower)
            check_url_reachability: If True, check if URLs are reachable (slower)
            fuzzy_threshold: Similarity threshold for fuzzy deduplication (0.0-1.0)
            use_rust: If True, use Rust acceleration when available
        """
        self.check_mx_records = check_mx_records and HAS_AIODNS
        self.check_url_reachability = check_url_reachability and HAS_AIOHTTP
        self.fuzzy_threshold = fuzzy_threshold
        self.use_rust = use_rust and HAS_RUST_SIMILARITY

        # Initialize hallucination guard
        self.hallucination_guard = HallucinationGuard(strict_mode=True)

        # Compile regex patterns for performance
        self._email_regex = re.compile(
            r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        )
        self._url_regex = re.compile(
            r'^https?://[^\s<>"\']+$'
        )

        # Corporate domain indicators (higher confidence)
        self._corporate_tlds = {
            '.com', '.org', '.net', '.co', '.io', '.ai', '.tech',
            '.biz', '.info', '.app', '.dev', '.cloud', '.work'
        }

        # Company suffix patterns for normalization
        self._company_suffixes = re.compile(
            r'\s+(Inc\.?|LLC|Ltd\.?|Limited|Corp\.?|Corporation|Co\.?|Company|LLP|LP|PLC|GmbH|AG|SA|SAS|BV|NV)$',
            re.IGNORECASE
        )

        logger.info(
            f"DataValidator initialized - "
            f"MX check: {self.check_mx_records}, "
            f"URL check: {self.check_url_reachability}, "
            f"Fuzzy threshold: {self.fuzzy_threshold}, "
            f"Rust: {self.use_rust}"
        )

    # ==========================================================================
    # EMAIL VALIDATION
    # ==========================================================================

    def validate_email(
        self,
        email: str,
        check_mx: Optional[bool] = None
    ) -> ValidationResult:
        """
        Validate an email address.

        Checks:
        1. Format (regex)
        2. Not in disposable domains list
        3. Not matching fake patterns
        4. Optional: MX record exists (DNS lookup)

        Args:
            email: Email address to validate
            check_mx: Override instance setting for MX check

        Returns:
            ValidationResult with is_valid, normalized value, and issues
        """
        issues = []
        email = email.strip().lower()

        # 1. Format check
        if not self._email_regex.match(email):
            return ValidationResult(
                is_valid=False,
                value=None,
                issues=["Invalid email format"],
                confidence=0.0
            )

        # Extract domain
        try:
            domain = email.split('@')[1]
        except IndexError:
            return ValidationResult(
                is_valid=False,
                value=None,
                issues=["Cannot extract domain from email"],
                confidence=0.0
            )

        # 2. Check disposable domains
        if domain in DISPOSABLE_EMAIL_DOMAINS:
            return ValidationResult(
                is_valid=False,
                value=None,
                issues=[f"Disposable email domain: {domain}"],
                confidence=0.0,
                metadata={"domain": domain, "disposable": True}
            )

        # 3. Check fake patterns
        for pattern in FAKE_PATTERNS.get("emails", []):
            if re.search(pattern, email, re.IGNORECASE):
                return ValidationResult(
                    is_valid=False,
                    value=None,
                    issues=[f"Fake email pattern detected: {pattern}"],
                    confidence=0.0
                )

        # 4. Calculate confidence based on domain
        confidence = self._calculate_email_confidence(email, domain)

        # 5. Optional MX record check (async, so we skip in sync method)
        # Use validate_email_async for MX checking
        check_mx = check_mx if check_mx is not None else self.check_mx_records
        if check_mx:
            issues.append("MX check requires async method (use validate_email_async)")

        return ValidationResult(
            is_valid=True,
            value=email,
            issues=issues,
            confidence=confidence,
            metadata={"domain": domain}
        )

    async def validate_email_async(
        self,
        email: str,
        check_mx: Optional[bool] = None
    ) -> ValidationResult:
        """
        Async version with MX record validation.

        Args:
            email: Email address to validate
            check_mx: Override instance setting for MX check

        Returns:
            ValidationResult
        """
        # Run sync validation first
        result = self.validate_email(email, check_mx=False)
        if not result.is_valid:
            return result

        # MX record check if enabled
        check_mx = check_mx if check_mx is not None else self.check_mx_records
        if check_mx and HAS_AIODNS:
            domain = result.metadata.get("domain")
            mx_valid = await self._check_mx_record(domain)
            if not mx_valid:
                return ValidationResult(
                    is_valid=False,
                    value=None,
                    issues=result.issues + [f"No MX record found for domain: {domain}"],
                    confidence=0.0,
                    metadata=result.metadata
                )

        return result

    def _calculate_email_confidence(self, email: str, domain: str) -> float:
        """
        Calculate confidence score for an email (0.0-1.0).

        Higher confidence for:
        - Corporate TLDs (.com, .io, etc.)
        - Non-generic local parts (not info@, contact@, etc.)
        - Longer, more specific domains
        """
        confidence = 0.7  # Base confidence

        # Corporate TLD bonus
        for tld in self._corporate_tlds:
            if domain.endswith(tld):
                confidence += 0.15
                break

        # Non-generic local part bonus
        local_part = email.split('@')[0]
        generic_locals = {'info', 'contact', 'admin', 'support', 'sales', 'hello'}
        if local_part not in generic_locals:
            confidence += 0.1

        # Specific domain bonus (not just "company.com")
        if len(domain.split('.')[0]) > 5:  # Domain name > 5 chars
            confidence += 0.05

        return min(confidence, 1.0)

    async def _check_mx_record(self, domain: str) -> bool:
        """Check if domain has MX records (email server configured)."""
        if not HAS_AIODNS:
            return True  # Assume valid if can't check

        try:
            resolver = aiodns.DNSResolver()
            await resolver.query(domain, 'MX')
            return True
        except Exception as e:
            logger.debug(f"MX lookup failed for {domain}: {e}")
            return False

    # ==========================================================================
    # PHONE VALIDATION
    # ==========================================================================

    def validate_phone(
        self,
        phone: str,
        country: Optional[str] = None
    ) -> ValidationResult:
        """
        Validate a phone number.

        Checks:
        1. Format (multiple patterns)
        2. Not matching fake patterns (555-xxxx, etc.)
        3. Normalize to E.164 format if phonenumbers available
        4. Detect country from prefix

        Args:
            phone: Phone number to validate
            country: ISO country code (e.g., "US") for parsing hint

        Returns:
            ValidationResult
        """
        issues = []
        phone_normalized = phone.strip()

        # 1. Check fake patterns first
        for pattern in FAKE_PATTERNS.get("phones", []):
            if re.search(pattern, phone_normalized, re.IGNORECASE):
                return ValidationResult(
                    is_valid=False,
                    value=None,
                    issues=[f"Fake phone pattern detected: {pattern}"],
                    confidence=0.0
                )

        # 2. Basic format validation
        digits = re.sub(r'\D', '', phone_normalized)
        if len(digits) < 7 or len(digits) > 15:
            return ValidationResult(
                is_valid=False,
                value=None,
                issues=[f"Invalid phone length: {len(digits)} digits"],
                confidence=0.0
            )

        # 3. Parse and normalize with phonenumbers library if available
        metadata = {}
        if HAS_PHONENUMBERS:
            try:
                parsed = phonenumbers.parse(phone_normalized, country)
                if phonenumbers.is_valid_number(parsed):
                    # Normalize to E.164 format
                    phone_normalized = phonenumbers.format_number(
                        parsed,
                        phonenumbers.PhoneNumberFormat.E164
                    )
                    metadata['country'] = phonenumbers.region_code_for_number(parsed)
                    metadata['type'] = phonenumbers.number_type(parsed)
                    metadata['e164'] = phone_normalized
                else:
                    issues.append("Phone number format invalid per phonenumbers library")
            except phonenumbers.NumberParseException as e:
                issues.append(f"Cannot parse phone number: {e}")
        else:
            # Basic normalization without library
            phone_normalized = f"+{digits}" if not digits.startswith('1') else f"+1{digits}"
            metadata['note'] = "Basic normalization (phonenumbers library not available)"

        confidence = 0.8 if not issues else 0.6

        return ValidationResult(
            is_valid=True,
            value=phone_normalized,
            issues=issues,
            confidence=confidence,
            metadata=metadata
        )

    # ==========================================================================
    # URL VALIDATION
    # ==========================================================================

    def validate_url(
        self,
        url: str,
        check_reachability: Optional[bool] = None
    ) -> ValidationResult:
        """
        Validate a URL.

        Checks:
        1. Format (protocol + domain)
        2. Protocol normalization (add https if missing)
        3. Not matching fake patterns
        4. Optional: Reachability check (HEAD request)

        Args:
            url: URL to validate
            check_reachability: Override instance setting

        Returns:
            ValidationResult
        """
        issues = []
        url_normalized = url.strip()

        # Add protocol if missing
        if not url_normalized.startswith(('http://', 'https://')):
            url_normalized = f"https://{url_normalized}"

        # 1. Format check
        try:
            parsed = urlparse(url_normalized)
            if not parsed.scheme or not parsed.netloc:
                return ValidationResult(
                    is_valid=False,
                    value=None,
                    issues=["Invalid URL format - missing scheme or netloc"],
                    confidence=0.0
                )
        except Exception as e:
            return ValidationResult(
                is_valid=False,
                value=None,
                issues=[f"URL parse error: {e}"],
                confidence=0.0
            )

        # 2. Check fake patterns
        for pattern in FAKE_PATTERNS.get("urls", []):
            if re.search(pattern, url_normalized, re.IGNORECASE):
                return ValidationResult(
                    is_valid=False,
                    value=None,
                    issues=[f"Fake URL pattern detected: {pattern}"],
                    confidence=0.0
                )

        # 3. Extract domain for metadata
        domain = parsed.netloc
        metadata = {
            "domain": domain,
            "scheme": parsed.scheme,
            "path": parsed.path
        }

        # 4. Reachability check (async, so skip in sync method)
        check_reachability = check_reachability if check_reachability is not None else self.check_url_reachability
        if check_reachability:
            issues.append("Reachability check requires async method (use validate_url_async)")

        return ValidationResult(
            is_valid=True,
            value=url_normalized,
            issues=issues,
            confidence=0.9,
            metadata=metadata
        )

    async def validate_url_async(
        self,
        url: str,
        check_reachability: Optional[bool] = None
    ) -> ValidationResult:
        """
        Async version with reachability check.

        Args:
            url: URL to validate
            check_reachability: Override instance setting

        Returns:
            ValidationResult
        """
        # Run sync validation first
        result = self.validate_url(url, check_reachability=False)
        if not result.is_valid:
            return result

        # Reachability check if enabled
        check_reachability = check_reachability if check_reachability is not None else self.check_url_reachability
        if check_reachability and HAS_AIOHTTP:
            reachable = await self._check_url_reachability(result.value)
            if not reachable:
                return ValidationResult(
                    is_valid=False,
                    value=None,
                    issues=result.issues + [f"URL not reachable: {result.value}"],
                    confidence=0.0,
                    metadata=result.metadata
                )

        return result

    async def _check_url_reachability(self, url: str, timeout: int = 5) -> bool:
        """Check if URL is reachable via HEAD request."""
        if not HAS_AIOHTTP:
            return True  # Assume reachable if can't check

        try:
            async with aiohttp.ClientSession() as session:
                async with session.head(url, timeout=timeout, allow_redirects=True) as response:
                    return response.status < 400
        except Exception as e:
            logger.debug(f"URL reachability check failed for {url}: {e}")
            return False

    # ==========================================================================
    # COMPANY VALIDATION
    # ==========================================================================

    def validate_company(self, company: str) -> ValidationResult:
        """
        Validate a company name.

        Checks:
        1. Not a placeholder (Acme, Test, Example)
        2. Not too short (<2 chars) or too long (>100 chars)
        3. Normalize (strip Inc, LLC, etc for matching)

        Args:
            company: Company name to validate

        Returns:
            ValidationResult with normalized company name
        """
        issues = []
        company_normalized = company.strip()

        # 1. Length check
        if len(company_normalized) < 2:
            return ValidationResult(
                is_valid=False,
                value=None,
                issues=["Company name too short"],
                confidence=0.0
            )

        if len(company_normalized) > 100:
            return ValidationResult(
                is_valid=False,
                value=None,
                issues=["Company name too long"],
                confidence=0.0
            )

        # 2. Check fake patterns
        for pattern in FAKE_PATTERNS.get("companies", []):
            if re.search(pattern, company_normalized, re.IGNORECASE):
                return ValidationResult(
                    is_valid=False,
                    value=None,
                    issues=[f"Fake company pattern detected: {pattern}"],
                    confidence=0.0
                )

        # 3. Normalize - remove common suffixes for deduplication
        company_base = self._company_suffixes.sub('', company_normalized).strip()

        return ValidationResult(
            is_valid=True,
            value=company_normalized,
            issues=issues,
            confidence=0.9,
            metadata={
                "normalized": company_base,
                "original": company
            }
        )

    # ==========================================================================
    # DEDUPLICATION
    # ==========================================================================

    def deduplicate_leads(
        self,
        leads: List[Dict[str, Any]],
        fuzzy_company_match: bool = True
    ) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
        """
        Deduplicate leads using exact + fuzzy matching.

        Strategies:
        1. Exact email match
        2. Exact phone match
        3. Domain-based company match (john@acme.com = jane@acme.com)
        4. Fuzzy company name match (Levenshtein distance)

        Args:
            leads: List of lead dictionaries
            fuzzy_company_match: Enable fuzzy matching for company names

        Returns:
            Tuple of (unique_leads, stats_dict)
        """
        stats = {
            "exact_duplicates": 0,
            "domain_duplicates": 0,
            "fuzzy_duplicates": 0
        }

        seen_emails = set()
        seen_phones = set()
        seen_domains = set()
        seen_companies = []  # List of (normalized_name, lead_dict) for fuzzy matching

        unique_leads = []

        for lead in leads:
            email = lead.get('email', '').lower().strip()
            phone = lead.get('phone', '').strip()
            company = lead.get('company', '').strip()

            # 1. Exact email match
            if email and email in seen_emails:
                stats["exact_duplicates"] += 1
                continue

            # 2. Exact phone match
            if phone and phone in seen_phones:
                stats["exact_duplicates"] += 1
                continue

            # 3. Domain-based dedup (same company if same email domain)
            domain = None
            if email and '@' in email:
                domain = email.split('@')[1]
                if domain in seen_domains:
                    stats["domain_duplicates"] += 1
                    continue

            # 4. Fuzzy company match
            if fuzzy_company_match and company:
                # Normalize company name
                company_normalized = self._company_suffixes.sub('', company).strip().lower()

                # Check similarity with existing companies
                is_duplicate = False
                for existing_company, _ in seen_companies:
                    similarity = self._calculate_similarity(company_normalized, existing_company)
                    if similarity >= self.fuzzy_threshold:
                        stats["fuzzy_duplicates"] += 1
                        is_duplicate = True
                        break

                if is_duplicate:
                    continue

                seen_companies.append((company_normalized, lead))

            # Not a duplicate - add to unique leads
            unique_leads.append(lead)
            if email:
                seen_emails.add(email)
            if phone:
                seen_phones.add(phone)
            if domain:
                seen_domains.add(domain)

        return unique_leads, stats

    def _calculate_similarity(self, s1: str, s2: str) -> float:
        """
        Calculate string similarity (0.0-1.0).

        Uses Rust if available (faster), otherwise Python difflib.
        """
        if self.use_rust and HAS_RUST_SIMILARITY:
            try:
                # Use Jaro-Winkler for company name matching (better for short strings)
                return eversale_core.string_similarity(s1, s2, "jaro_winkler")
            except Exception as e:
                logger.warning(f"Rust similarity failed, falling back to Python: {e}")

        # Python fallback using difflib
        return SequenceMatcher(None, s1, s2).ratio()

    # ==========================================================================
    # BATCH VALIDATION
    # ==========================================================================

    def validate_leads(
        self,
        leads: List[Dict[str, Any]],
        deduplicate: bool = True,
        fuzzy_dedup: bool = True
    ) -> Tuple[List[Dict[str, Any]], BatchValidationReport]:
        """
        Validate and clean a batch of leads.

        Process:
        1. Validate each field (email, phone, company, url)
        2. Remove leads with fake/invalid data
        3. Normalize values
        4. Deduplicate (exact + fuzzy)
        5. Generate report

        Args:
            leads: List of lead dictionaries with keys like:
                   {email, phone, company, url, name, ...}
            deduplicate: If True, remove duplicates
            fuzzy_dedup: If True, use fuzzy matching for deduplication

        Returns:
            Tuple of (validated_leads, report)

        Example:
            leads = [
                {"email": "john@acme.com", "company": "Acme Corp"},
                {"email": "fake@fake.com", "company": "Test Company"}
            ]
            validated, report = validator.validate_leads(leads)
            print(report.summary())
        """
        report = BatchValidationReport(total_input=len(leads))
        validated = []

        for lead in leads:
            issues = []
            cleaned_lead = {}

            # Validate email
            if 'email' in lead and lead['email']:
                email_result = self.validate_email(lead['email'])
                if not email_result.is_valid:
                    report.fake_emails_removed += 1
                    if email_result.metadata.get('disposable'):
                        report.disposable_emails_removed += 1
                    issues.extend(email_result.issues)
                    continue  # Skip lead entirely if email is fake
                cleaned_lead['email'] = email_result.value
                cleaned_lead['email_confidence'] = email_result.confidence

            # Validate phone
            if 'phone' in lead and lead['phone']:
                phone_result = self.validate_phone(lead['phone'])
                if not phone_result.is_valid:
                    report.fake_phones_removed += 1
                    issues.extend(phone_result.issues)
                    # Don't skip lead, just remove phone
                else:
                    cleaned_lead['phone'] = phone_result.value
                    if phone_result.metadata.get('country'):
                        cleaned_lead['phone_country'] = phone_result.metadata['country']

            # Validate company
            if 'company' in lead and lead['company']:
                company_result = self.validate_company(lead['company'])
                if not company_result.is_valid:
                    report.fake_companies_removed += 1
                    issues.extend(company_result.issues)
                    continue  # Skip lead if company is fake
                cleaned_lead['company'] = company_result.value
                cleaned_lead['company_normalized'] = company_result.metadata.get('normalized')

            # Validate URL
            if 'url' in lead and lead['url']:
                url_result = self.validate_url(lead['url'])
                if not url_result.is_valid:
                    report.invalid_urls_removed += 1
                    issues.extend(url_result.issues)
                    # Don't skip lead, just remove URL
                else:
                    cleaned_lead['url'] = url_result.value
                    cleaned_lead['domain'] = url_result.metadata.get('domain')

            # Copy other fields as-is
            for key, value in lead.items():
                if key not in cleaned_lead and key not in {'email', 'phone', 'company', 'url'}:
                    cleaned_lead[key] = value

            # Add to validated list
            validated.append(cleaned_lead)
            if issues:
                report.issues.extend(issues)

        # Deduplication
        if deduplicate:
            original_count = len(validated)
            validated, dedup_stats = self.deduplicate_leads(validated, fuzzy_company_match=fuzzy_dedup)
            report.duplicates_removed = dedup_stats.get("exact_duplicates", 0)
            report.domain_dedup_count = dedup_stats.get("domain_duplicates", 0)
            report.fuzzy_dedup_count = dedup_stats.get("fuzzy_duplicates", 0)

        report.total_output = len(validated)

        logger.info(f"Validated {report.total_input} leads -> {report.total_output} unique/valid leads")

        return validated, report

    async def validate_leads_async(
        self,
        leads: List[Dict[str, Any]],
        deduplicate: bool = True,
        fuzzy_dedup: bool = True,
        check_mx: bool = False,
        check_urls: bool = False
    ) -> Tuple[List[Dict[str, Any]], BatchValidationReport]:
        """
        Async version with MX record and URL reachability checks.

        Args:
            leads: List of lead dictionaries
            deduplicate: If True, remove duplicates
            fuzzy_dedup: If True, use fuzzy matching
            check_mx: If True, validate email MX records
            check_urls: If True, check URL reachability

        Returns:
            Tuple of (validated_leads, report)
        """
        report = BatchValidationReport(total_input=len(leads))
        validated = []

        for lead in leads:
            issues = []
            cleaned_lead = {}

            # Validate email (async)
            if 'email' in lead and lead['email']:
                email_result = await self.validate_email_async(lead['email'], check_mx=check_mx)
                if not email_result.is_valid:
                    report.fake_emails_removed += 1
                    if email_result.metadata.get('disposable'):
                        report.disposable_emails_removed += 1
                    issues.extend(email_result.issues)
                    continue
                cleaned_lead['email'] = email_result.value
                cleaned_lead['email_confidence'] = email_result.confidence

            # Validate phone (sync)
            if 'phone' in lead and lead['phone']:
                phone_result = self.validate_phone(lead['phone'])
                if not phone_result.is_valid:
                    report.fake_phones_removed += 1
                    issues.extend(phone_result.issues)
                else:
                    cleaned_lead['phone'] = phone_result.value
                    if phone_result.metadata.get('country'):
                        cleaned_lead['phone_country'] = phone_result.metadata['country']

            # Validate company (sync)
            if 'company' in lead and lead['company']:
                company_result = self.validate_company(lead['company'])
                if not company_result.is_valid:
                    report.fake_companies_removed += 1
                    issues.extend(company_result.issues)
                    continue
                cleaned_lead['company'] = company_result.value
                cleaned_lead['company_normalized'] = company_result.metadata.get('normalized')

            # Validate URL (async)
            if 'url' in lead and lead['url']:
                url_result = await self.validate_url_async(lead['url'], check_reachability=check_urls)
                if not url_result.is_valid:
                    report.invalid_urls_removed += 1
                    issues.extend(url_result.issues)
                else:
                    cleaned_lead['url'] = url_result.value
                    cleaned_lead['domain'] = url_result.metadata.get('domain')

            # Copy other fields
            for key, value in lead.items():
                if key not in cleaned_lead and key not in {'email', 'phone', 'company', 'url'}:
                    cleaned_lead[key] = value

            validated.append(cleaned_lead)
            if issues:
                report.issues.extend(issues)

        # Deduplication (sync)
        if deduplicate:
            validated, dedup_stats = self.deduplicate_leads(validated, fuzzy_company_match=fuzzy_dedup)
            report.duplicates_removed = dedup_stats.get("exact_duplicates", 0)
            report.domain_dedup_count = dedup_stats.get("domain_duplicates", 0)
            report.fuzzy_dedup_count = dedup_stats.get("fuzzy_duplicates", 0)

        report.total_output = len(validated)

        logger.info(f"Validated {report.total_input} leads -> {report.total_output} unique/valid leads")

        return validated, report


# ==============================================================================
# CONVENIENCE FUNCTIONS
# ==============================================================================

# Global validator instance
_validator = None

def get_validator(**kwargs) -> DataValidator:
    """Get or create global validator instance."""
    global _validator
    if _validator is None:
        _validator = DataValidator(**kwargs)
    return _validator


def validate_leads(
    leads: List[Dict[str, Any]],
    **kwargs
) -> Tuple[List[Dict[str, Any]], BatchValidationReport]:
    """
    Convenience function to validate leads using global validator.

    Example:
        from agent.data_validator import validate_leads

        leads = [{"email": "...", "company": "..."}, ...]
        validated, report = validate_leads(leads)
        print(report.summary())
    """
    return get_validator().validate_leads(leads, **kwargs)


async def validate_leads_async(
    leads: List[Dict[str, Any]],
    **kwargs
) -> Tuple[List[Dict[str, Any]], BatchValidationReport]:
    """
    Async convenience function with MX/URL checks.

    Example:
        validated, report = await validate_leads_async(
            leads,
            check_mx=True,
            check_urls=True
        )
    """
    return await get_validator().validate_leads_async(leads, **kwargs)


# ==============================================================================
# EXPORTS
# ==============================================================================

__all__ = [
    'DataValidator',
    'ValidationResult',
    'BatchValidationReport',
    'validate_leads',
    'validate_leads_async',
    'get_validator'
]
