"""
Hallucination Guard - Prevents fake/made-up data from being returned

This module provides multiple layers of protection:
1. Pattern detection for known fake data
2. Source verification for all outputs
3. LLM response validation
4. Data provenance tracking

Recent Improvements (December 2024 Audit):
- Added LLM instruction leakage detection (38 regex patterns)
- Expanded disposable email domain list (93 domains)
- Added more fake data patterns (names, companies, addresses)
- Enhanced data provenance tracking with metadata and confidence scores
"""

import re
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from loguru import logger


# Disposable/temporary email domains that real prospects rarely use
# These domains allow anonymous, temporary email addresses and are often used for spam or fake signups
DISPOSABLE_EMAIL_DOMAINS = [
    # Major disposable email services
    "guerrillamail.com",
    "guerrillamail.org",
    "guerrillamail.net",
    "guerrillamail.biz",
    "guerrillamail.de",
    "sharklasers.com",
    "grr.la",
    "pokemail.net",
    "spam4.me",
    "tempmail.com",
    "temp-mail.org",
    "temp-mail.io",
    "10minutemail.com",
    "10minutemail.net",
    "20minutemail.com",
    "mailinator.com",
    "mailinator2.com",
    "trashmail.com",
    "trashmail.net",
    "throwaway.email",
    "throwawaymail.com",
    "getnada.com",
    "fakeinbox.com",
    "yopmail.com",
    "yopmail.fr",
    "maildrop.cc",
    "dispostable.com",
    "mintemail.com",
    "tempinbox.com",
    "fakemailgenerator.com",
    "emailondeck.com",
    "mohmal.com",
    "mytemp.email",
    "tempmail.net",
    "temp-mail.com",
    "mailnesia.com",
    "mailcatch.com",
    "incognitomail.com",
    "burnermail.io",
    "spamgourmet.com",
    "anonbox.net",
    # Additional disposable services (2025 update)
    "mail.tm",
    "internxt.com",
    "duck.com",
    "simplelogin.com",
    "anonaddy.com",
    "33mail.com",
    "sneakemail.com",
    "mailforspam.com",
    "getairmail.com",
    "airmail.cc",
    "guerrillamailblock.com",
    "spam.la",
    "mx0.wwwnew.eu",
    "tmpnator.live",
    "email-fake.com",
    "dropmail.me",
    "emltmp.com",
    "tmpmail.net",
    "tmpmail.org",
    "moakt.com",
    "moakt.cc",
    "moakt.ws",
    "tmail.ws",
    "cloudns.nz",
    "guerrillamail.info",
    "pokemail.com",
    "spambox.us",
    "speedgmail.com",
    "mail-temporaire.fr",
    "mvrht.com",
    "instant-mail.de",
    "harakirimail.com",
    "trashmail.de",
    "damnthespam.com",
    "wh4f.org",
    "wp.pl",
    "cr.cloudns.asia",
    "armyspy.com",
    "cuvox.de",
    "dayrep.com",
    "einrot.com",
    "fleckens.hu",
    "gustr.com",
    "jourrapide.com",
    "rhyta.com",
    "superrito.com",
    "teleworm.us",
    "mailsac.com",
    "maildax.com",
    "owlymail.com",
    "ethereal.email",
    "mailtrap.io",
]


# Known fake/placeholder patterns that should NEVER appear in real outputs
# NOTE: example.com/org/net are REAL, official IANA reserved domains - NOT fake
# See: https://www.iana.org/domains/reserved - They ARE valid for testing
FAKE_PATTERNS = {
    # Fake emails - patterns that indicate LLM hallucination
    "emails": [
        # Common placeholder domains (NOT including IANA reserved domains)
        r"fake\.com$",
        r"placeholder\.com$",
        r"domain\.com$",
        r"yourcompany\.com$",
        r"company\.com$",
        r"email\.com$",
        # Disposable email services
        r"tempmail\.com$",
        r"mailinator\.com$",
        r"guerrillamail\.com$",
        r"throwaway\.com$",
        r"fakeinbox\.com$",
        r"sharklasers\.com$",
        r"yopmail\.com$",
        r"10minutemail\.com$",
        r"trashmail\.com$",
        r"dispostable\.com$",
        r"temp-mail\.org$",
        # Common fake prefixes
        r"^fake@",
        r"^placeholder@",
        r"^asdf@",
        r"^qwerty@",
        r"^aaa@",
        r"^xxx@",
        r"^contact@example",
        r"^noreply@example",
        r"^no-reply@example",
        r"^donotreply@",
        # Common fake names in emails (only with fake domains)
        r"john\.doe@",
        r"jane\.doe@",
        r"john\.smith@(?:example|test|fake|sample|placeholder)",  # Only catch with fake domains
        r"jane\.smith@(?:example|test|fake|sample|placeholder)",  # Only catch with fake domains
        r"test\.user@",
        r"sample\.user@",
    ],
    # Fake phones - expanded with international formats
    "phones": [
        # US fake patterns
        r"555[-.\s]?\d{3}[-.\s]?\d{4}",  # Classic fake US numbers with 555
        r"\(555\)[-.\s]?\d{3}[-.\s]?\d{4}",  # (555) 123-4567 format
        r"\d{3}[-.\s]?555[-.\s]?\d{4}",  # 555 in middle
        r"\(\d{3}\)[-.\s]?555",  # (xxx) 555-xxxx format
        r"\+1[-.\s]?555",
        r"123[-.\s]?456[-.\s]?7890",
        r"098[-.\s]?765[-.\s]?4321",  # Reverse sequential
        r"000[-.\s]?000[-.\s]?0000",
        r"111[-.\s]?111[-.\s]?1111",
        r"222[-.\s]?222[-.\s]?2222",
        r"333[-.\s]?333[-.\s]?3333",
        r"444[-.\s]?444[-.\s]?4444",
        r"666[-.\s]?666[-.\s]?6666",
        r"777[-.\s]?777[-.\s]?7777",
        r"888[-.\s]?888[-.\s]?8888",
        r"999[-.\s]?999[-.\s]?9999",
        r"1234567890",
        r"0000000000",
        r"1111111111",
        r"5551234567",  # Exact 555 pattern
        # UK fake patterns
        r"\+44[-.\s]?7700[-.\s]?900\d*",  # UK Ofcom reserved (with optional trailing digits)
        r"07700[-.\s]?900[-.\s]?\d{0,3}",  # UK test numbers
        r"02079[-.\s]?460[-.\s]?\d{0,3}",  # UK TV/drama numbers
        # Australian fake patterns
        r"\+61[-.\s]?4[-.\s]?9999",  # Australian placeholder
        r"0491\s*570\s*006",  # Australian test (with spaces)
        # International generic fakes
        r"\+1[-.\s]?800[-.\s]?555",  # Toll-free 555
        r"\+0[-.\s]?000",  # Invalid country code
        r"\+99[-.\s]?\d",  # Invalid country code 99
        # Sequential patterns (any country)
        r"(\d)\1{9}",  # 10 same digits
        r"0123456789",
        r"9876543210",
        r"0987654321",
    ],
    # Fake names (common placeholders) - expanded
    "names": [
        r"^John Doe$",
        r"^Jane Doe$",
        r"^John Smith$",
        r"^Jane Smith$",
        r"^Test User$",
        r"^Sample User$",
        r"^Demo User$",
        r"^Placeholder$",
        r"^Lorem Ipsum$",
        r"^Foo Bar$",
        r"^Alice Bob$",
        r"^Bob Alice$",
        r"^First Last$",
        r"^Firstname Lastname$",
        r"^Your Name$",
        r"^Customer Name$",
        r"^N/A$",
        r"^TBD$",
        r"^Unknown$",
        r"^Anonymous$",
        r"^XXXX",  # Redacted pattern
        r"^Name Here$",
        r"^Enter Name$",
        r"^Test Test$",
        r"^Example Person$",
        r"^Person \d+$",  # Person 1, Person 2
        r"^User \d+$",  # User 1, User 2
        r"^Admin$",
        r"^Administrator$",
        r"^Test Admin$",
        r"^Default User$",
    ],
    # Fake companies - expanded
    "companies": [
        r"^Acme Corp",
        r"^Acme Inc",
        r"^Acme Ltd",
        r"^Example Corp",
        r"^Example Inc",
        r"^Test Company",
        r"^Test Corp",
        r"^Sample Inc",
        r"^Sample Company",
        r"^Placeholder LLC",
        r"^Placeholder Inc",
        r"^Foo Industries",
        r"^Foo Corp",
        r"^Bar Inc",
        r"^Widget Co$",
        r"^Widgets Inc",
        r"^Demo Company",
        r"^Demo Corp",
        r"^Fake Company",
        r"^Your Company",
        r"^Company Name$",
        r"^ABC Company",
        r"^XYZ Corp",
        r"^123 Industries",
        r"^Lorem Corp",
        r"^Ipsum Inc",
        r"^Contoso",  # Microsoft placeholder
        r"^Fabrikam",  # Microsoft placeholder
        r"^Northwind",  # Microsoft placeholder
        r"^Adventure Works",  # Microsoft placeholder
        r"^Fourth Coffee",  # Microsoft placeholder
        r"^Tailspin Toys",  # Microsoft placeholder
        r"^Wingtip Toys",  # Microsoft placeholder
        r"^Trey Research",  # Microsoft placeholder
        r"^Proseware",  # Microsoft placeholder
        r"^Generic Co$",
        r"^Generic Inc$",
        r"^Generic LLC$",
        r"^Default Company$",
        r"^Company \d+$",  # Company 1, Company 2
        r"^Business Name$",
        r"^Enter Company$",
    ],
    # Fake URLs - only patterns that indicate LLM hallucination
    # NOTE: example.com/org/net are REAL, official IANA test domains - NOT fake
    # They're valid URLs for testing and should not be blocked
    "urls": [
        r"placeholder\.com",
        r"fake\.com",
        r"yourwebsite\.com",
        r"yourdomain\.com",
        r"mywebsite\.com",
        r"website\.com$",
        r"domain\.tld$",
        r"foo\.bar$",
        r"test\.local$",
        r"dev\.local$",
        # Only block private/local IPs if they appear in extracted data
        # r"localhost",  # Valid for local testing
        # r"127\.0\.0\.1",  # Valid for local testing
    ],
    # Fake addresses - expanded
    "addresses": [
        r"123 Main St",
        r"456 Oak Ave",
        r"789 Elm St",
        r"123 Test Street",
        r"1234 Street",
        r"Sample Address",
        r"Placeholder City",
        r"Anytown",
        r"Nowhere",
        r"123 Fake St",
        r"00000",  # Fake ZIP
        r"12345",  # Common test ZIP
        r"99999",  # Fake ZIP
        r"XXXXX",  # Redacted
        r"Your Address",
        r"Address Line",
        r"Street Address",
        r"City, State",
        r"City, ST 00000",
        r"1600 Pennsylvania Ave",  # Famous address
        r"221B Baker St",  # Fictional address
        r"742 Evergreen Terrace",  # Simpsons
        r"Platform 9 3/4",  # Harry Potter
        r"Address \d+$",  # Address 1, Address 2
        r"Default Address",
        r"Enter Address",
    ],
    # Fake social security numbers
    "ssn": [
        r"000[-\s]?\d{2}[-\s]?\d{4}",  # Invalid SSN
        r"\d{3}[-\s]?00[-\s]?\d{4}",  # Invalid SSN
        r"\d{3}[-\s]?\d{2}[-\s]?0000",  # Invalid SSN
        r"123[-\s]?45[-\s]?6789",
        r"111[-\s]?11[-\s]?1111",
        r"999[-\s]?99[-\s]?9999",
        r"078[-\s]?05[-\s]?1120",  # Famous fake SSN (Woolworth wallet)
    ],
    # Fake credit card numbers (for test detection)
    "credit_cards": [
        r"4111[-\s]?1111[-\s]?1111[-\s]?1111",  # Visa test
        r"5500[-\s]?0000[-\s]?0000[-\s]?0004",  # MC test
        r"3400[-\s]?0000[-\s]?0000[-\s]?009",  # Amex test
        r"0000[-\s]?0000[-\s]?0000[-\s]?0000",
        r"1234[-\s]?5678[-\s]?9012[-\s]?3456",
    ],
}

# Phrases that indicate LLM hallucination - expanded
HALLUCINATION_PHRASES = [
    # Capability denial phrases
    "I don't have access to",
    "I cannot browse",
    "I'm unable to",
    "I cannot actually",
    "I cannot verify",
    "I don't have the ability",
    "I apologize, but I cannot",
    "I'm not able to",
    "I can't actually",
    "I do not have the capability",
    "beyond my capabilities",
    # AI self-reference phrases
    "As an AI",
    "As a language model",
    "As an artificial",
    "I am an AI",
    "I'm just an AI",
    "my training data",
    "based on my training",
    "my knowledge cutoff",
    "my training ended",
    # LLM instruction leakage patterns (system prompt fragments)
    "You are a helpful assistant",
    "Your task is to",
    "You should follow these instructions",
    "Claude is an AI",
    "Anthropic's AI assistant",
    "You are Claude",
    "system message",
    "system prompt",
    "assistant mode",
    "instruction following",
    "according to my instructions",
    "as per my guidelines",
    "following my training",
    "based on the prompt",
    "the user requested",
    "here are the instructions",
    "my programming dictates",
    "I was instructed to",
    "my system instructions",
    "according to my system",
    "per my configuration",
    "as configured",
    "reasoning step",
    "chain of thought",
    "let me think",
    "thinking out loud",
    "<thinking>",
    "</thinking>",
    "<output>",
    "</output>",
    "scratchpad",
    "internal monologue",
    # Placeholder/example indicators
    "hypothetically",
    "for example purposes",
    "as a placeholder",
    "simulated response",
    "mock data",
    "dummy data",
    "sample data for illustration",
    "for demonstration",
    "this is an example",
    "here's a sample",
    "placeholder text",
    "lorem ipsum",
    # Uncertainty hedging that suggests fabrication
    "I would imagine",
    "I would guess",
    "I believe it might",
    "probably something like",
    "it could be something like",
    "typically might be",
    "generally would be",
    # Fabrication admission phrases
    "I made up",
    "I fabricated",
    "I invented",
    "I generated",
    "fictional example",
    "not real data",
    "not actual data",
    "illustrative purposes",
    # Deflection phrases
    "you should verify",
    "please confirm",
    "I recommend checking",
    "double-check this information",
]

# Additional instruction leakage patterns for dedicated detection
INSTRUCTION_LEAKAGE_PATTERNS = [
    # Direct instruction references
    r"my instructions (?:are|were|say|tell)",
    r"I (?:was|am) (?:told|instructed|programmed|configured) to",
    r"according to (?:my|the) (?:instructions|guidelines|rules|policy)",
    r"the (?:system|prompt|instruction) (?:says|tells|requires)",
    r"my (?:role|purpose) is to",
    r"I (?:must|should|need to) follow (?:these|the|my) (?:instructions|rules|guidelines)",
    # System prompt fragments
    r"you are (?:a|an) (?:helpful|AI|assistant|agent)",
    r"your (?:task|job|role|purpose) is to",
    r"(?:always|never) (?:refuse|decline|reject) (?:requests|to)",
    r"you (?:must|should|will) (?:not|never) (?:discuss|reveal|share)",
    r"remember that you",
    r"keep in mind that",
    r"it'?s important (?:to note|that) you",
    # Role descriptions leaking
    r"as (?:a|an) AI (?:assistant|agent|model|language model)",
    r"I'?m (?:designed|built|created|trained) (?:to|by)",
    r"my capabilities (?:include|are|allow)",
    r"I have been (?:designed|programmed|trained|instructed) to",
    # Policy/guideline mentions
    r"(?:according to|following|per) (?:my|the|our) (?:policy|policies|guidelines)",
    r"company policy (?:states|requires|dictates)",
    r"our guidelines (?:state|require|say)",
    r"Anthropic'?s? (?:policy|policies|guidelines|values)",
    r"OpenAI'?s? (?:policy|policies|guidelines|values)",
    # Internal reasoning leakage
    r"</?(?:thinking|reasoning|scratchpad|internal|output|response)>",
    r"(?:step \d+|first|second|third|finally),?\s*(?:I will|I should|let'?s)",
    r"internal (?:thought|reasoning|monologue|dialogue)",
    r"chain[- ]of[- ]thought",
    r"my reasoning is",
    r"let me (?:think|reason|consider) (?:about|through)",
    # Configuration/system details
    r"my (?:parameters|settings|configuration|system)",
    r"(?:temperature|top_p|max_tokens|model) (?:is set|setting|parameter)",
    r"I'?m running on",
    r"my model (?:version|name|type) is",
    r"GPT-[0-9]",
    r"Claude [0-9]",
    # Explicit instruction formatting
    r"instruction\s*\d+:",
    r"rule\s*\d+:",
    r"guideline\s*\d+:",
    r"step\s*\d+:",
]


@dataclass
class DataSource:
    """Tracks the source of data for provenance."""
    tool_name: str
    timestamp: datetime
    url: Optional[str] = None
    selector: Optional[str] = None
    raw_response: Optional[str] = None
    # Enhanced provenance tracking
    page_title: Optional[str] = None
    extraction_method: Optional[str] = None  # css, xpath, llm, regex, api
    confidence_score: Optional[float] = None  # 0.0-1.0
    verification_attempts: int = 0
    fallback_used: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    """Result of validation check."""
    is_valid: bool
    issues: List[str] = field(default_factory=list)
    cleaned_data: Any = None
    source: Optional[DataSource] = None


class HallucinationGuard:
    """
    Guards against hallucinated/fake data in agent outputs.

    Usage:
        guard = HallucinationGuard()
        result = guard.validate_output(data, source_tool="playwright_extract_entities")
        if not result.is_valid:
            logger.warning(f"Potential hallucination detected: {result.issues}")
    """

    def __init__(self, strict_mode: bool = True):
        """
        Initialize the guard.

        Args:
            strict_mode: If True, fail on ANY suspicious pattern. If False, only warn.
        """
        self.strict_mode = strict_mode
        self._sources: Dict[str, DataSource] = {}
        self._validation_log: List[Dict] = []

    def validate_output(
        self,
        data: Any,
        source_tool: Optional[str] = None,
        source_url: Optional[str] = None,
        data_type: Optional[str] = None,
        is_user_input: bool = False,
        page_title: Optional[str] = None,
        extraction_method: Optional[str] = None,
        confidence_score: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ValidationResult:
        """
        Validate output data for hallucination patterns.

        Args:
            data: The data to validate (string, dict, or list)
            source_tool: The tool that produced this data
            source_url: The URL the data came from
            data_type: Type of data (email, phone, company, etc.)
            is_user_input: If True, skip URL validation (user explicitly requested this URL)
            page_title: Title of the page data was extracted from
            extraction_method: Method used to extract (css, xpath, llm, regex, api)
            confidence_score: Confidence in the extraction (0.0-1.0)
            metadata: Additional provenance metadata

        Returns:
            ValidationResult with is_valid, issues, and cleaned_data
        """
        # Skip validation for user-provided navigation URLs
        # example.com is a legitimate IANA-reserved domain users may want to visit
        if is_user_input and data_type == "urls":
            source = DataSource(
                tool_name=source_tool or "user_input",
                timestamp=datetime.now(),
                url=source_url,
                raw_response=str(data)[:500] if data else None,
                page_title=page_title,
                extraction_method=extraction_method or "user_provided",
                confidence_score=1.0,
                metadata=metadata or {}
            )
            return ValidationResult(is_valid=True, source=source)
        issues = []
        cleaned_data = data

        # Record source with enhanced provenance
        source = DataSource(
            tool_name=source_tool or "unknown",
            timestamp=datetime.now(),
            url=source_url,
            raw_response=str(data)[:500] if data else None,
            page_title=page_title,
            extraction_method=extraction_method,
            confidence_score=confidence_score,
            metadata=metadata or {}
        )

        # Check for missing provenance data (red flag for hallucination)
        if not source_tool:
            issues.append("Missing provenance: No source tool specified")
        # Only require URL for navigation tools - other browser tools operate on current page
        NAVIGATION_TOOLS = {'playwright_navigate', 'playwright_get_markdown', 'browser_navigate'}
        if source_tool and source_tool in NAVIGATION_TOOLS and not source_url:
            issues.append("Missing provenance: Navigation tool used but no URL provided")
        # Skip URL check for tools that operate on current page (evaluate, click, fill, snapshot, etc.)
        if extraction_method == "llm" and confidence_score and confidence_score < 0.5:
            issues.append(f"Low confidence LLM extraction: {confidence_score:.2f}")

        # Check for None/empty
        if data is None:
            return ValidationResult(is_valid=True, source=source)

        # Convert to string for pattern matching
        data_str = str(data) if not isinstance(data, str) else data

        # Check for hallucination phrases in LLM responses
        for phrase in HALLUCINATION_PHRASES:
            if phrase.lower() in data_str.lower():
                issues.append(f"Hallucination phrase detected: '{phrase}'")

        # Check for fake patterns based on data type
        if data_type:
            patterns = FAKE_PATTERNS.get(data_type, [])
            for pattern in patterns:
                if re.search(pattern, data_str, re.IGNORECASE):
                    issues.append(f"Fake {data_type} pattern detected: {pattern}")
        else:
            # Check all pattern types
            for dtype, patterns in FAKE_PATTERNS.items():
                for pattern in patterns:
                    if re.search(pattern, data_str, re.IGNORECASE):
                        issues.append(f"Fake {dtype} pattern detected: {pattern}")

        # Check for LLM instruction leakage (SECURITY CRITICAL)
        leakage_result = self._detect_instruction_leakage(data_str)
        if not leakage_result.is_valid:
            issues.extend(leakage_result.issues)
            # Log security event for instruction leakage attempts
            logger.warning(
                f"SECURITY: LLM instruction leakage detected - "
                f"Tool: {source_tool}, URL: {source_url}, "
                f"Issues: {leakage_result.issues}"
            )
            # Sanitize the output if leakage detected
            if leakage_result.cleaned_data and isinstance(data, str):
                cleaned_data = leakage_result.cleaned_data
                logger.info(f"Output sanitized to remove instruction leakage")

        # Validate structured data
        if isinstance(data, dict):
            cleaned_data, dict_issues = self._validate_dict(data)
            issues.extend(dict_issues)
        elif isinstance(data, list):
            cleaned_data, list_issues = self._validate_list(data)
            issues.extend(list_issues)

        # Log validation with full provenance
        self._validation_log.append({
            "timestamp": datetime.now().isoformat(),
            "source_tool": source_tool,
            "source_url": source_url,
            "page_title": page_title,
            "extraction_method": extraction_method,
            "confidence_score": confidence_score,
            "data_type": data_type,
            "issues": issues,
            "is_valid": len(issues) == 0,
            "metadata": metadata or {}
        })

        is_valid = len(issues) == 0 if self.strict_mode else True

        if issues:
            logger.warning(f"Hallucination guard found issues: {issues}")

        return ValidationResult(
            is_valid=is_valid,
            issues=issues,
            cleaned_data=cleaned_data,
            source=source
        )

    def _validate_dict(self, data: Dict) -> Tuple[Dict, List[str]]:
        """Validate dictionary data and clean fake values."""
        issues = []
        cleaned = {}

        for key, value in data.items():
            key_lower = key.lower()

            # Check email fields
            if "email" in key_lower:
                email_value = str(value)
                # Check for disposable email domains first (more specific message)
                if self._is_disposable_email(email_value):
                    issues.append(f"Disposable/temporary email domain in field '{key}': {email_value} - Real prospects rarely use these services")
                    continue
                # Check for other fake email patterns
                if self._is_fake_email(email_value):
                    issues.append(f"Fake email in field '{key}': {email_value}")
                    continue

            # Check phone fields
            if "phone" in key_lower or "tel" in key_lower:
                if self._is_fake_phone(str(value)):
                    issues.append(f"Fake phone in field '{key}': {value}")
                    continue

            # Check name fields
            if key_lower in ["name", "contact_name", "person", "full_name"]:
                if self._is_fake_name(str(value)):
                    issues.append(f"Fake name in field '{key}': {value}")
                    continue

            # Check company fields
            if "company" in key_lower or "organization" in key_lower:
                if self._is_fake_company(str(value)):
                    issues.append(f"Fake company in field '{key}': {value}")
                    continue

            # Check URL fields
            if "url" in key_lower or "link" in key_lower or "href" in key_lower:
                if self._is_fake_url(str(value)):
                    issues.append(f"Fake URL in field '{key}': {value}")
                    continue

            # Check SSN fields
            if "ssn" in key_lower or "social_security" in key_lower or "social security" in key_lower:
                if self._is_fake_ssn(str(value)):
                    issues.append(f"Fake SSN in field '{key}': {value}")
                    continue

            # Check credit card fields
            if "card" in key_lower or "credit" in key_lower or "cc_" in key_lower:
                if self._is_fake_credit_card(str(value)):
                    issues.append(f"Test credit card in field '{key}': {value}")
                    continue

            # Check address fields
            if "address" in key_lower or "street" in key_lower:
                if self._is_fake_address(str(value)):
                    issues.append(f"Fake address in field '{key}': {value}")
                    continue

            # Recursively validate nested structures
            if isinstance(value, dict):
                nested_cleaned, nested_issues = self._validate_dict(value)
                issues.extend(nested_issues)
                cleaned[key] = nested_cleaned
            elif isinstance(value, list):
                nested_cleaned, nested_issues = self._validate_list(value)
                issues.extend(nested_issues)
                cleaned[key] = nested_cleaned
            else:
                cleaned[key] = value

        return cleaned, issues

    def _validate_list(self, data: List) -> Tuple[List, List[str]]:
        """Validate list data and filter out fake values."""
        issues = []
        cleaned = []

        for item in data:
            if isinstance(item, dict):
                nested_cleaned, nested_issues = self._validate_dict(item)
                if not nested_issues:  # Only keep items without issues
                    cleaned.append(nested_cleaned)
                issues.extend(nested_issues)
            elif isinstance(item, str):
                # Check if string looks like email/phone/etc
                if "@" in item:
                    # Check for disposable email first (more specific)
                    if self._is_disposable_email(item):
                        issues.append(f"Disposable/temporary email in list: {item} - Real prospects rarely use these services")
                    elif self._is_fake_email(item):
                        issues.append(f"Fake email in list: {item}")
                    else:
                        cleaned.append(item)
                elif self._looks_like_phone(item) and self._is_fake_phone(item):
                    issues.append(f"Fake phone in list: {item}")
                else:
                    cleaned.append(item)
            else:
                cleaned.append(item)

        return cleaned, issues

    def _is_fake_email(self, email: str) -> bool:
        """Check if email matches known fake patterns."""
        email = email.lower().strip()
        for pattern in FAKE_PATTERNS["emails"]:
            if re.search(pattern, email, re.IGNORECASE):
                return True

        # Check for disposable/temporary email domains
        if self._is_disposable_email(email):
            return True

        return False

    def _is_disposable_email(self, email: str) -> bool:
        """
        Check if email uses a disposable/temporary email domain.

        Real prospects rarely use guerrillamail, tempmail, etc.
        These are red flags for hallucinated or fake data.

        Args:
            email: Email address to check

        Returns:
            True if email uses a disposable domain, False otherwise
        """
        email = email.lower().strip()

        # Extract domain from email
        if "@" not in email:
            return False

        try:
            domain = email.split("@")[1].strip()
        except (IndexError, AttributeError):
            return False

        # Check against known disposable domains
        if domain in DISPOSABLE_EMAIL_DOMAINS:
            logger.warning(f"Disposable email domain detected: {email} (domain: {domain})")
            return True

        return False

    def _is_fake_phone(self, phone: str) -> bool:
        """Check if phone matches known fake patterns."""
        # Normalize phone
        digits = re.sub(r'\D', '', phone)
        phone_normalized = phone.strip()

        for pattern in FAKE_PATTERNS["phones"]:
            if re.search(pattern, phone_normalized, re.IGNORECASE):
                return True

        # Check digit patterns
        if digits in ["1234567890", "0000000000", "1111111111", "9999999999"]:
            return True

        return False

    def _is_fake_name(self, name: str) -> bool:
        """Check if name matches known fake patterns."""
        for pattern in FAKE_PATTERNS["names"]:
            if re.search(pattern, name.strip(), re.IGNORECASE):
                return True
        return False

    def _is_fake_company(self, company: str) -> bool:
        """Check if company matches known fake patterns."""
        for pattern in FAKE_PATTERNS["companies"]:
            if re.search(pattern, company.strip(), re.IGNORECASE):
                return True
        return False

    def _is_fake_url(self, url: str) -> bool:
        """Check if URL matches known fake patterns."""
        for pattern in FAKE_PATTERNS["urls"]:
            if re.search(pattern, url.strip(), re.IGNORECASE):
                return True
        return False

    def _looks_like_phone(self, text: str) -> bool:
        """Check if text looks like a phone number."""
        digits = re.sub(r'\D', '', text)
        return len(digits) >= 7 and len(digits) <= 15

    def _is_fake_ssn(self, ssn: str) -> bool:
        """Check if SSN matches known fake patterns."""
        for pattern in FAKE_PATTERNS.get("ssn", []):
            if re.search(pattern, ssn.strip(), re.IGNORECASE):
                return True
        return False

    def _is_fake_credit_card(self, card: str) -> bool:
        """Check if credit card matches known test patterns."""
        for pattern in FAKE_PATTERNS.get("credit_cards", []):
            if re.search(pattern, card.strip(), re.IGNORECASE):
                return True
        return False

    def _is_fake_address(self, address: str) -> bool:
        """Check if address matches known fake patterns."""
        for pattern in FAKE_PATTERNS.get("addresses", []):
            if re.search(pattern, address.strip(), re.IGNORECASE):
                return True
        return False

    def _detect_instruction_leakage(self, text: str) -> ValidationResult:
        """
        Detect if LLM output contains leaked system instructions or prompts.

        This checks for:
        - Direct instruction references ("my instructions are")
        - System prompt fragments ("You are a helpful assistant")
        - Role descriptions ("As an AI assistant")
        - Policy/guideline mentions
        - Internal reasoning tags (<thinking>, etc.)
        - Configuration details

        Args:
            text: The output text to check for instruction leakage

        Returns:
            ValidationResult with detected issues and optionally sanitized output
        """
        issues = []
        leaked_patterns = []

        # Check for instruction leakage patterns
        for pattern in INSTRUCTION_LEAKAGE_PATTERNS:
            matches = re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                leaked_text = match.group(0)
                leaked_patterns.append(leaked_text)
                issues.append(
                    f"Instruction leakage detected: '{leaked_text[:100]}...' "
                    f"(pattern: {pattern[:50]}...)"
                )
                logger.error(
                    f"SECURITY ALERT: LLM instruction leakage - "
                    f"Pattern: {pattern}, Leaked: '{leaked_text[:100]}'"
                )

        # Sanitize output if leakage detected
        sanitized_text = text
        if leaked_patterns:
            sanitized_text = self._sanitize_instruction_leakage(text, leaked_patterns)
            logger.info(
                f"Sanitized {len(leaked_patterns)} instruction leakage occurrence(s) "
                f"from output"
            )

        return ValidationResult(
            is_valid=len(issues) == 0,
            issues=issues,
            cleaned_data=sanitized_text if leaked_patterns else text
        )

    def _sanitize_instruction_leakage(
        self,
        text: str,
        leaked_patterns: List[str]
    ) -> str:
        """
        Sanitize output by removing or redacting leaked instructions.

        Strategy:
        1. Remove XML-style tags completely (<thinking>, etc.)
        2. Redact instruction references with [REDACTED]
        3. Remove sentences containing policy/guideline leaks

        Args:
            text: Original text with leakage
            leaked_patterns: List of leaked pattern matches to sanitize

        Returns:
            Sanitized text with instruction leakage removed/redacted
        """
        sanitized = text

        # Remove XML-style internal reasoning tags and their content
        xml_tag_pattern = r"</?(?:thinking|reasoning|scratchpad|internal|output|response)>.*?</(?:thinking|reasoning|scratchpad|internal|output|response)>"
        sanitized = re.sub(xml_tag_pattern, "", sanitized, flags=re.IGNORECASE | re.DOTALL)

        # Remove standalone XML tags
        standalone_tag_pattern = r"</?(?:thinking|reasoning|scratchpad|internal|output|response)>"
        sanitized = re.sub(standalone_tag_pattern, "", sanitized, flags=re.IGNORECASE)

        # Redact sentences containing instruction leakage
        # Split by sentence boundaries
        sentences = re.split(r'([.!?]\s+)', sanitized)
        sanitized_sentences = []

        for i, sentence in enumerate(sentences):
            # Check if this sentence contains any leaked patterns
            contains_leak = False
            for pattern in INSTRUCTION_LEAKAGE_PATTERNS:
                if re.search(pattern, sentence, re.IGNORECASE):
                    contains_leak = True
                    break

            if contains_leak:
                # Redact the sentence
                if sentence.strip() and not re.match(r'^[.!?]\s*$', sentence):
                    sanitized_sentences.append("[REDACTED: Instruction leakage removed]")
                    # Preserve sentence boundary if next item is punctuation
                    if i + 1 < len(sentences) and re.match(r'^[.!?]', sentences[i + 1]):
                        sanitized_sentences.append(". ")
            else:
                sanitized_sentences.append(sentence)

        sanitized = ''.join(sanitized_sentences)

        # Clean up multiple consecutive redactions
        sanitized = re.sub(
            r'(\[REDACTED: Instruction leakage removed\][.!?]?\s*){2,}',
            '[REDACTED: Instruction leakage removed]. ',
            sanitized
        )

        # Clean up whitespace
        sanitized = re.sub(r'\s+', ' ', sanitized)
        sanitized = sanitized.strip()

        return sanitized

    def validate_llm_response(self, response: str, expected_source: str = None) -> ValidationResult:
        """
        Specifically validate LLM-generated responses for hallucination.

        Args:
            response: The LLM response text
            expected_source: What source the data should come from (e.g., "browser", "file")

        Returns:
            ValidationResult
        """
        issues = []

        # First, check for instruction leakage (critical security issue)
        leakage_result = self._detect_instruction_leakage(response)
        if not leakage_result.is_valid:
            issues.extend(leakage_result.issues)
            # Use sanitized version for further checks
            response = leakage_result.cleaned_data or response

        # Check for explicit hallucination indicators
        for phrase in HALLUCINATION_PHRASES:
            if phrase.lower() in response.lower():
                issues.append(f"LLM hallucination indicator: '{phrase}'")

        # Check if LLM is admitting it can't do something but provides data anyway
        cant_patterns = [
            r"I (?:cannot|can't|don't have).+but.+(?:here|example|sample)",
            r"(?:hypothetically|theoretically).+would be",
            r"if I could.+it would",
        ]
        for pattern in cant_patterns:
            if re.search(pattern, response, re.IGNORECASE):
                issues.append(f"LLM contradiction detected: claims inability but provides data")

        # Check for fabricated statistics without source
        stat_patterns = [
            r"\d+%\s+of\s+(?:users|customers|people|companies)",
            r"(?:approximately|about|around)\s+\d+\s+(?:million|thousand|billion)",
            r"studies show",
            r"research indicates",
            r"according to (?:experts|studies|research)",
        ]
        for pattern in stat_patterns:
            if re.search(pattern, response, re.IGNORECASE):
                if expected_source and "search" not in expected_source.lower():
                    issues.append(f"Unsourced statistic detected - may be hallucinated")

        is_valid = len(issues) == 0 if self.strict_mode else True

        return ValidationResult(
            is_valid=is_valid,
            issues=issues,
            cleaned_data=response if is_valid else None
        )

    def require_source(self, data: Any, source_tool: str, source_url: str) -> ValidationResult:
        """
        Require that data has a verifiable source.

        For critical operations, use this to ensure data came from a real tool call.
        """
        if not source_tool:
            return ValidationResult(
                is_valid=False,
                issues=["No source tool specified - data origin unknown"]
            )

        if not source_url and source_tool.startswith("playwright_"):
            return ValidationResult(
                is_valid=False,
                issues=["Browser tool used but no URL specified - data origin unverifiable"]
            )

        # Validate the data itself
        return self.validate_output(data, source_tool, source_url)

    def get_validation_log(self) -> List[Dict]:
        """Get the validation log for debugging."""
        return self._validation_log.copy()

    def clear_log(self):
        """Clear the validation log."""
        self._validation_log.clear()

    def get_provenance_summary(self) -> Dict[str, Any]:
        """
        Get a summary of data provenance across all validations.

        Returns:
            Dictionary with provenance statistics and insights
        """
        if not self._validation_log:
            return {
                "total_validations": 0,
                "sources_by_tool": {},
                "extraction_methods": {},
                "missing_provenance_count": 0,
                "low_confidence_count": 0
            }

        sources_by_tool = {}
        extraction_methods = {}
        missing_provenance = 0
        low_confidence = 0

        for entry in self._validation_log:
            tool = entry.get("source_tool", "unknown")
            sources_by_tool[tool] = sources_by_tool.get(tool, 0) + 1

            method = entry.get("extraction_method", "unknown")
            extraction_methods[method] = extraction_methods.get(method, 0) + 1

            if not tool or tool == "unknown":
                missing_provenance += 1

            confidence = entry.get("confidence_score")
            if confidence is not None and confidence < 0.5:
                low_confidence += 1

        return {
            "total_validations": len(self._validation_log),
            "sources_by_tool": sources_by_tool,
            "extraction_methods": extraction_methods,
            "missing_provenance_count": missing_provenance,
            "low_confidence_count": low_confidence,
            "validation_failures": sum(1 for e in self._validation_log if not e["is_valid"])
        }


# Global instance for easy access
_guard = None

def get_guard(strict_mode: bool = True) -> HallucinationGuard:
    """Get or create the global hallucination guard."""
    global _guard
    if _guard is None:
        _guard = HallucinationGuard(strict_mode=strict_mode)
    return _guard


def validate_output(data: Any, **kwargs) -> ValidationResult:
    """Convenience function to validate output using global guard."""
    return get_guard().validate_output(data, **kwargs)


def validate_llm_response(response: str, **kwargs) -> ValidationResult:
    """Convenience function to validate LLM response using global guard."""
    return get_guard().validate_llm_response(response, **kwargs)
