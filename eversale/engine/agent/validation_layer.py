#!/usr/bin/env python3
"""
Validation Layer - Anti-hallucination checks for function calls and data
Prevents models from inventing URLs, data, or nonsensical parameters
"""

import re
from typing import Dict, List, Any, Optional, Tuple
from urllib.parse import urlparse
from loguru import logger


class ValidationLayer:
    """Validates function calls and catches hallucinations"""

    def __init__(self):
        # Known valid domains (whitelist for common sites)
        self.known_domains = {
            'facebook.com',
            'google.com',
            'linkedin.com',
            'twitter.com',
            'instagram.com',
            'youtube.com',
            'wikipedia.org',
            'github.com',
            'amazon.com',
            'ebay.com',
            'reddit.com',
            'stackoverflow.com',
        }

        # Suspicious patterns that indicate hallucination
        self.hallucination_patterns = [
            r'example\.com',
            r'test\.com',
            r'placeholder',
            r'your[-_]?url',
            r'website[-_]?here',
            r'\$\{.*\}',  # Template variables
            r'\{.*\}',    # Curly brace placeholders
            r'UNKNOWN',
            r'TODO',
            r'FIXME',
        ]

        # Blocked keywords in text (hallucination indicators)
        self.hallucination_keywords = [
            'color palette',
            'designer',
            'typography',
            'font family',
            'css style',
            'lorem ipsum',
            'placeholder text',
            'sample data',
            'example text',
        ]

    def validate_call(
        self,
        function: str,
        arguments: Dict[str, Any],
        context: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate a function call
        Returns: (is_valid, error_message)
        """

        # 1. Validate URL if present
        if 'url' in arguments:
            valid, error = self._validate_url(arguments['url'], context)
            if not valid:
                return False, error

        # 2. Validate selector if present
        if 'selector' in arguments:
            valid, error = self._validate_selector(arguments['selector'])
            if not valid:
                return False, error

        # 3. Validate text/value fields
        for key in ['value', 'text', 'content']:
            if key in arguments:
                valid, error = self._validate_text(arguments[key])
                if not valid:
                    return False, error

        # 4. Validate script if present (for evaluate)
        if 'script' in arguments:
            valid, error = self._validate_script(arguments['script'])
            if not valid:
                return False, error

        return True, None

    def _validate_url(self, url: str, context: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """Validate URL is real and not hallucinated"""

        # Check for placeholder patterns
        url_lower = url.lower()
        for pattern in self.hallucination_patterns:
            if re.search(pattern, url_lower):
                return False, f"URL appears to be a placeholder: {url}"

        # Parse URL
        try:
            parsed = urlparse(url)
        except Exception as e:
            return False, f"Invalid URL format: {url}"

        # Must have scheme
        if not parsed.scheme:
            return False, f"URL missing protocol (http/https): {url}"

        # Must have netloc (domain)
        if not parsed.netloc:
            return False, f"URL missing domain: {url}"

        # Check for obviously fake domains
        fake_indicators = ['localhost', '127.0.0.1', '0.0.0.0']
        if any(indicator in parsed.netloc for indicator in fake_indicators):
            logger.warning(f"URL uses local address: {url}")
            # Allow but warn

        # Validate domain format (basic check)
        domain = parsed.netloc.lower()
        if not re.match(r'^[a-z0-9.-]+\.[a-z]{2,}$', domain):
            # Check if it's a known domain without subdomain
            if domain not in self.known_domains:
                return False, f"URL domain looks suspicious: {domain}"

        # If we have context, check if URL is mentioned
        if context:
            # URL should be related to context or be a known site
            domain_parts = domain.split('.')
            main_domain = '.'.join(domain_parts[-2:]) if len(domain_parts) >= 2 else domain

            # Check if domain mentioned in context
            if main_domain not in context.lower() and domain not in self.known_domains:
                logger.warning(f"URL {url} not mentioned in context, might be hallucinated")
                # Don't block, just warn - model might be inferring correctly

        return True, None

    def _validate_selector(self, selector: str) -> Tuple[bool, Optional[str]]:
        """Validate CSS selector is reasonable"""

        if not selector or not selector.strip():
            return False, "Selector is empty"

        selector = selector.strip()

        # Check for placeholder patterns
        for pattern in self.hallucination_patterns:
            if re.search(pattern, selector, re.IGNORECASE):
                return False, f"Selector appears to be a placeholder: {selector}"

        # Basic CSS selector validation
        # Should contain at least one of: tag, class, id, attribute
        valid_patterns = [
            r'^[a-z][\w-]*',           # Tag: div, button
            r'\.[a-z][\w-]*',          # Class: .button
            r'#[a-z][\w-]*',           # ID: #submit
            r'\[[a-z][\w-]*',          # Attribute: [type="submit"]
            r'::[a-z][\w-]*',          # Pseudo-element: ::before
            r':[a-z][\w-]*',           # Pseudo-class: :hover
        ]

        if not any(re.search(pattern, selector, re.IGNORECASE) for pattern in valid_patterns):
            return False, f"Selector doesn't look like valid CSS: {selector}"

        # Check for suspicious content
        if any(word in selector.lower() for word in ['placeholder', 'example', 'your-']):
            return False, f"Selector contains placeholder text: {selector}"

        return True, None

    def _validate_text(self, text: str) -> Tuple[bool, Optional[str]]:
        """Validate text content is not hallucinated"""

        if not isinstance(text, str):
            return False, f"Text must be string, got {type(text)}"

        text_lower = text.lower()

        # Check for hallucination keywords
        for keyword in self.hallucination_keywords:
            if keyword in text_lower:
                return False, f"Text contains hallucinated content: '{keyword}'"

        # Check for placeholder patterns
        for pattern in self.hallucination_patterns:
            if re.search(pattern, text_lower):
                return False, f"Text contains placeholder pattern: {text}"

        return True, None

    def _validate_script(self, script: str) -> Tuple[bool, Optional[str]]:
        """Validate JavaScript for evaluate"""

        if not script or not script.strip():
            return False, "Script is empty"

        script_lower = script.lower()

        # Block dangerous operations
        dangerous_patterns = [
            r'document\.cookie',
            r'localStorage\.clear',
            r'sessionStorage\.clear',
            r'\.remove\(\)',
            r'delete\s+',
            r'drop\s+table',
        ]

        for pattern in dangerous_patterns:
            if re.search(pattern, script_lower):
                logger.warning(f"Script contains potentially dangerous operation: {pattern}")
                # Don't block but warn

        # Check for placeholders
        for pattern in self.hallucination_patterns:
            if re.search(pattern, script_lower):
                return False, f"Script contains placeholder: {script}"

        return True, None

    def validate_response_text(self, text: str) -> Tuple[bool, List[str]]:
        """
        Validate model's text response for hallucinations
        Returns: (is_valid, list_of_issues)
        """
        issues = []

        text_lower = text.lower()

        # Check for hallucination keywords
        for keyword in self.hallucination_keywords:
            if keyword in text_lower:
                issues.append(f"Response contains hallucinated topic: '{keyword}'")

        # Check if response is talking about unrelated topics
        unrelated_topics = [
            'design',
            'aesthetic',
            'visual',
            'artwork',
            'illustration',
            'graphic',
            'branding',
        ]

        # Count unrelated topic mentions
        unrelated_count = sum(1 for topic in unrelated_topics if topic in text_lower)
        if unrelated_count >= 3:
            issues.append(f"Response discussing unrelated topics (design/aesthetics)")

        return len(issues) == 0, issues

    def should_allow_url(self, url: str, user_prompt: str) -> bool:
        """
        Determine if a URL should be allowed based on user prompt
        More lenient check for URLs explicitly mentioned by user
        """
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # Always allow if user explicitly mentioned the domain
        if domain in user_prompt.lower():
            return True

        # Always allow known domains
        domain_parts = domain.split('.')
        main_domain = '.'.join(domain_parts[-2:]) if len(domain_parts) >= 2 else domain
        if main_domain in self.known_domains:
            return True

        # Check for placeholder patterns (never allow)
        for pattern in self.hallucination_patterns:
            if re.search(pattern, url.lower()):
                return False

        # Unknown domain but valid format - allow with warning
        logger.warning(f"Allowing unknown but valid domain: {domain}")
        return True

    def extract_issues(self, text: str) -> List[str]:
        """
        Extract all validation issues from text
        Used for debugging/logging
        """
        issues = []

        # Check for hallucination indicators
        text_lower = text.lower()

        for keyword in self.hallucination_keywords:
            if keyword in text_lower:
                issues.append(f"Hallucination keyword: '{keyword}'")

        for pattern in self.hallucination_patterns:
            matches = re.finditer(pattern, text_lower)
            for match in matches:
                issues.append(f"Placeholder pattern: '{match.group()}'")

        return issues


# Singleton instance
validator = ValidationLayer()


def validate_function_call(
    function: str,
    arguments: Dict[str, Any],
    context: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    """Convenience function for validation"""
    return validator.validate_call(function, arguments, context)


def is_hallucinated(text: str) -> bool:
    """Quick check if text contains hallucinations"""
    valid, _ = validator.validate_response_text(text)
    return not valid
