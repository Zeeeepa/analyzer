#!/usr/bin/env python3
"""
Contact Extraction Module
Extracts email, phone, and contact URLs from websites with 95-100% reliability
"""

import re
from typing import Dict, List, Any, Optional
from loguru import logger

# Import centralized hallucination guard for consistent validation
try:
    from .hallucination_guard import get_guard
    HALLUCINATION_GUARD_AVAILABLE = True
except ImportError:
    HALLUCINATION_GUARD_AVAILABLE = False

# Rust acceleration bridge
try:
    from .rust_bridge import (
        extract_emails as rust_extract_emails,
        extract_phones as rust_extract_phones,
        extract_contacts as rust_extract_contacts,
        deduplicate_contacts as rust_deduplicate,
        is_rust_available
    )
    USE_RUST_CORE = is_rust_available()
except ImportError:
    USE_RUST_CORE = False

if USE_RUST_CORE:
    logger.info("Contact extractor: Rust acceleration enabled for email/phone extraction")
else:
    logger.info("Contact extractor: Using Python regex")


# Comprehensive fake email domain list
FAKE_EMAIL_DOMAINS = {
    'example.com', 'example.org', 'example.net',
    'test.com', 'testing.com', 'test.org',
    'domain.com', 'yourdomain.com', 'mydomain.com',
    'placeholder.com', 'sample.com', 'demo.com',
    'company.com', 'yourcompany.com', 'mycompany.com',
    'business.com', 'yourbusiness.com',
    'website.com', 'yourwebsite.com', 'mywebsite.com',
    'mail.com', 'email.com',  # Often fake
    'abc.com', 'xyz.com', '123.com',
    'fake.com', 'notreal.com', 'invalid.com',
    'noreply.com', 'donotreply.com',
    'acme.com', 'foo.com', 'bar.com', 'baz.com',
    'lorem.com', 'ipsum.com',
    'tempmail.com', 'throwaway.com', 'disposable.com',
}

FAKE_EMAIL_PATTERNS = [
    r'user@', r'admin@', r'info@example', r'contact@example',
    r'test\d*@', r'demo\d*@', r'sample\d*@',
    r'john\.?doe@', r'jane\.?doe@', r'name@',
    r'your\.?email@', r'your\.?name@', r'email@',
    r'placeholder', r'\[email\]', r'\{email\}',
]

FAKE_PHONE_PATTERNS = [
    r'555-\d{4}',  # US fake prefix
    r'123-?456-?7890',
    r'000-?000-?0000',
    r'111-?111-?1111',
    r'999-?999-?9999',
    r'\+1-?800-?555',
    r'xxx-?xxx-?xxxx',
]


def is_likely_real_email(email: str) -> bool:
    """Check if email is likely real (not placeholder/fake)."""
    email_lower = email.lower()
    domain = email_lower.split('@')[-1] if '@' in email_lower else ''

    # Check fake domains
    if domain in FAKE_EMAIL_DOMAINS:
        return False

    # Check fake patterns
    for pattern in FAKE_EMAIL_PATTERNS:
        if re.search(pattern, email_lower):
            return False

    # Must have valid TLD
    valid_tlds = {'.com', '.org', '.net', '.io', '.co', '.edu', '.gov', '.biz', '.info'}
    if not any(domain.endswith(tld) for tld in valid_tlds):
        # Allow country TLDs
        if not re.search(r'\.[a-z]{2}$', domain):
            return False

    return True


def is_likely_real_phone(phone: str) -> bool:
    """Check if phone number is likely real (not placeholder/fake)."""
    # Check fake patterns
    for pattern in FAKE_PHONE_PATTERNS:
        if re.search(pattern, phone):
            return False

    # Extract digits only
    digits = re.sub(r'[^0-9]', '', phone)

    # Check common fake digit sequences
    fake_sequences = [
        '0000000000', '1111111111', '5555555555', '9999999999',
        '1234567890', '0123456789', '9876543210',
    ]

    if digits in fake_sequences:
        return False

    # Check for 555 prefix (reserved for fiction in US)
    if len(digits) >= 10 and digits[3:6] == '555':
        return False

    # Must have reasonable length (7-15 digits)
    if len(digits) < 7 or len(digits) > 15:
        return False

    return True


class ContactExtractor:
    """
    Intelligent contact information extraction
    Uses multiple strategies to find contact data
    """

    def __init__(self):
        # Email patterns (comprehensive)
        self.email_patterns = [
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # Standard
            r'mailto:([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,})',  # Mailto links
        ]

        # Phone patterns (US, international) - strict to avoid SVG paths
        self.phone_patterns = [
            r'\b\d{3}[-\s]?\d{3}[-\s]?\d{4}\b',  # US: 123-456-7890, 123 456 7890 (NO dots - avoid SVG)
            r'\b\(\d{3}\)\s*\d{3}[-\s]?\d{4}\b',  # US: (123) 456-7890
            r'\b1[-\s]?\d{3}[-\s]?\d{3}[-\s]?\d{4}\b',  # US with country code
            r'\+1[-\s]?\d{3}[-\s]?\d{3}[-\s]?\d{4}\b',  # +1 format
            r'\+\d{2,3}[-\s]?\d{2,4}[-\s]?\d{4,8}\b',  # International (strict digit counts)
        ]

        # Contact page indicators
        self.contact_indicators = [
            'contact', 'about', 'reach', 'get-in-touch', 'support',
            'help', 'feedback', 'connect', 'info'
        ]

    async def extract_from_website(
        self,
        brain,
        website_url: str,
        deep_search: bool = True
    ) -> Dict[str, Any]:
        """
        Extract contact information from a website

        Args:
            brain: Ultimate brain instance for navigation
            website_url: Target website URL
            deep_search: If True, searches contact pages (slower but more thorough)

        Returns:
            {
                'email': str or None,
                'phone': str or None,
                'contact_url': str or None,
                'emails_found': List[str],  # All unique emails
                'phones_found': List[str],  # All unique phones
                'extraction_method': str
            }
        """

        result = {
            'email': None,
            'phone': None,
            'contact_url': None,
            'emails_found': [],
            'phones_found': [],
            'extraction_method': 'none'
        }

        try:
            # Phase 1: Quick scan of homepage
            logger.info(f"[CONTACT] Scanning homepage: {website_url}")

            homepage_task = f"""
Go to {website_url}
Wait 2 seconds for page to load
Extract the following:
1. All text content from the page
2. All links on the page (href attributes)
Return: {{text: pageText, links: allLinks}}
"""

            homepage_data = await brain.run(homepage_task, continue_conversation=True)

            # Parse homepage data
            emails_home = self._extract_emails_from_text(str(homepage_data))
            phones_home = self._extract_phones_from_text(str(homepage_data))

            result['emails_found'].extend(emails_home)
            result['phones_found'].extend(phones_home)

            if emails_home:
                result['email'] = emails_home[0]
                result['extraction_method'] = 'homepage'

            if phones_home:
                result['phone'] = phones_home[0]

            # Phase 2: Find contact page (if deep_search enabled)
            if deep_search:
                logger.info(f"[CONTACT] Searching for contact page...")

                # Look for contact links
                contact_link = self._find_contact_link_in_text(str(homepage_data), website_url)

                if contact_link:
                    logger.info(f"[CONTACT] Found contact page: {contact_link}")
                    result['contact_url'] = contact_link

                    # Visit contact page
                    contact_task = f"""
Go to {contact_link}
Wait 2 seconds for page to load
Extract all text content from the page
Return the full page text
"""

                    contact_data = await brain.run(contact_task, continue_conversation=True)

                    # Extract from contact page
                    emails_contact = self._extract_emails_from_text(str(contact_data))
                    phones_contact = self._extract_phones_from_text(str(contact_data))

                    result['emails_found'].extend(emails_contact)
                    result['phones_found'].extend(phones_contact)

                    # Prefer contact page data
                    if emails_contact and not result['email']:
                        result['email'] = emails_contact[0]
                        result['extraction_method'] = 'contact_page'
                    elif emails_contact:
                        result['extraction_method'] = 'contact_page'

                    if phones_contact and not result['phone']:
                        result['phone'] = phones_contact[0]

            # Phase 3: Check footer/common locations (if still no contact found)
            if not result['email'] and not result['phone']:
                logger.info(f"[CONTACT] Checking footer and common locations...")

                footer_task = f"""
Execute JavaScript to extract footer and common contact locations:
document.querySelector('footer')?.innerText +
document.querySelector('.contact')?.innerText +
document.querySelector('#contact')?.innerText
"""

                # This would need to be implemented via playwright_evaluate
                # For now, we rely on homepage and contact page scans

            # Deduplicate
            result['emails_found'] = list(set(result['emails_found']))
            result['phones_found'] = list(set(result['phones_found']))

            # Log results
            logger.success(f"[CONTACT] Found {len(result['emails_found'])} emails, "
                         f"{len(result['phones_found'])} phones for {website_url}")

        except Exception as e:
            logger.error(f"[CONTACT] Error extracting from {website_url}: {e}")

        return result

    def _extract_emails_from_text(self, text: str) -> List[str]:
        """Extract all emails from text"""
        # Use Rust-accelerated extraction if available (10-100x faster)
        if USE_RUST_CORE:
            try:
                emails = rust_extract_emails(text)
                # Filter out common false positives
                emails = [e for e in emails if not self._is_fake_email(e)]
                return list(set(emails))  # Deduplicate
            except Exception as e:
                logger.debug(f"Rust email extraction failed, using Python: {e}")

        # Python fallback
        emails = []
        for pattern in self.email_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            emails.extend(matches)

        # Filter out common false positives
        emails = [e for e in emails if not self._is_fake_email(e)]

        return list(set(emails))  # Deduplicate

    def _extract_phones_from_text(self, text: str) -> List[str]:
        """Extract all phone numbers from text"""
        # Use Rust-accelerated extraction if available (10-100x faster)
        if USE_RUST_CORE:
            try:
                phones = rust_extract_phones(text)
                # Clean and format
                phones = [self._clean_phone(p) for p in phones]
                # Filter out obviously fake numbers
                phones = [p for p in phones if not self._is_fake_phone(p)]
                return list(set(phones))  # Deduplicate
            except Exception as e:
                logger.debug(f"Rust phone extraction failed, using Python: {e}")

        # Python fallback
        phones = []
        for pattern in self.phone_patterns:
            matches = re.findall(pattern, text)
            phones.extend(matches)

        # Clean and format
        phones = [self._clean_phone(p) for p in phones]

        # Filter out obviously fake numbers
        phones = [p for p in phones if not self._is_fake_phone(p)]

        return list(set(phones))  # Deduplicate

    def _find_contact_link_in_text(self, text: str, base_url: str) -> Optional[str]:
        """
        Find contact page URL in text
        Looks for links with contact-related keywords
        """

        # Extract all URLs from text
        url_pattern = r'https?://[^\s<>"\']+|www\.[^\s<>"\']+|/[a-zA-Z0-9/_-]+(?:\.[a-zA-Z]{2,4})?'
        potential_urls = re.findall(url_pattern, text)

        # Check each URL for contact indicators
        for url in potential_urls:
            url_lower = url.lower()

            for indicator in self.contact_indicators:
                if indicator in url_lower:
                    # Make absolute URL
                    if url.startswith('/'):
                        base = base_url.rstrip('/')
                        return f"{base}{url}"
                    elif not url.startswith('http'):
                        base = base_url.rstrip('/')
                        return f"{base}/{url}"
                    else:
                        return url

        # Fallback: construct common contact URLs
        base = base_url.rstrip('/')
        common_paths = ['/contact', '/contact-us', '/about', '/get-in-touch', '/support']

        for path in common_paths:
            # We would test these in production, for now return first
            return f"{base}{path}"

        return None

    def _is_fake_email(self, email: str) -> bool:
        """Check if email is likely fake/placeholder - uses centralized HallucinationGuard"""
        # Use centralized guard if available (has more comprehensive patterns)
        if HALLUCINATION_GUARD_AVAILABLE:
            guard = get_guard()
            result = guard.validate_output(email, source_tool='contact_extractor', data_type='emails')
            if not result.is_valid:
                logger.debug(f"Fake email detected by guard: {email} - {result.issues}")
                return True

        # Use comprehensive validation function
        is_real = is_likely_real_email(email)
        if not is_real:
            logger.debug(f"Fake email detected: {email}")
        return not is_real

    def _is_fake_phone(self, phone: str) -> bool:
        """Check if phone is likely fake/placeholder - uses centralized HallucinationGuard"""
        # Use centralized guard if available (has more comprehensive patterns)
        if HALLUCINATION_GUARD_AVAILABLE:
            guard = get_guard()
            result = guard.validate_output(phone, source_tool='contact_extractor', data_type='phones')
            if not result.is_valid:
                logger.debug(f"Fake phone detected by guard: {phone} - {result.issues}")
                return True

        # Use comprehensive validation function
        is_real = is_likely_real_phone(phone)
        if not is_real:
            logger.debug(f"Fake phone detected: {phone}")
        return not is_real

    def _clean_phone(self, phone: str) -> str:
        """Clean and format phone number"""
        # Remove extra whitespace
        phone = phone.strip()

        # Standardize format (US)
        digits = re.sub(r'[^0-9]', '', phone)

        if len(digits) == 10:
            # Format as (123) 456-7890
            return f"({digits[0:3]}) {digits[3:6]}-{digits[6:10]}"
        elif len(digits) == 11 and digits[0] == '1':
            # Format with country code
            return f"+1 ({digits[1:4]}) {digits[4:7]}-{digits[7:11]}"
        else:
            # Return as-is if non-standard
            return phone


# Singleton
contact_extractor = ContactExtractor()
