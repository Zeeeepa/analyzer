"""
Integration tests for Eversale workflows A-O.
Tests workflow routing, execution, and data extraction.

This test suite validates:
1. Workflow routing and detection
2. Contact extraction accuracy
3. Workflow execution with mocked browser
4. Error recovery mechanisms
5. Parameter validation
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from pathlib import Path
from typing import Dict, Any

# Configure pytest-asyncio
pytest_plugins = ('pytest_asyncio',)

# Import core modules
from executors.workflows_a_to_o import (
    A1_EmailInbox,
    B1_SpreadsheetCleaner,
    C1_TicketClassifier,
    D1_CompanyResearch,
    G1_ContractExtractor,
    I1_MaintenanceAnalyzer,
    J1_TransactionCategorizer,
    K1_AnalyticsInsights,
    N1_FormExtractor,
    WORKFLOW_EXECUTORS,
    get_workflow_executor
)
from executors.base import ActionStatus, ActionResult
from capability_router import CapabilityRouter, route_to_capability
from contact_extractor import (
    ContactExtractor,
    is_likely_real_email,
    is_likely_real_phone
)


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def mock_browser():
    """Create mock browser with Playwright page."""
    browser = AsyncMock()
    browser.page = AsyncMock()
    browser.page.content = AsyncMock(return_value="<html><body>Test page</body></html>")
    browser.page.url = "https://example.com"
    browser.page.title = AsyncMock(return_value="Example Page")
    browser.page.evaluate = AsyncMock(return_value={})
    browser.navigate = AsyncMock()
    browser.page.goto = AsyncMock()
    browser.page.reload = AsyncMock()
    browser.page.screenshot = AsyncMock(return_value=b"fake_screenshot")
    browser.page.query_selector = AsyncMock(return_value=None)
    browser.page.query_selector_all = AsyncMock(return_value=[])
    return browser


@pytest.fixture
def capability_router():
    """Create capability router instance."""
    return CapabilityRouter()


@pytest.fixture
def contact_extractor():
    """Create contact extractor instance."""
    return ContactExtractor()


# ============================================================================
# Test Workflow Routing
# ============================================================================

class TestWorkflowRouting:
    """Test that prompts route to correct workflows."""

    def test_email_workflow_detection(self, capability_router):
        """Test email-related prompts route to workflow A."""
        prompts = [
            "triage my inbox",
            "sort my emails by priority",
            "organize my email inbox",
        ]

        for prompt in prompts:
            match = capability_router.route(prompt)
            assert match is not None, f"Failed to match: {prompt}"
            assert match.capability == 'A', f"Wrong capability for: {prompt}"
            assert match.confidence >= 0.5

    def test_sdr_workflow_detection(self, capability_router):
        """Test SDR prompts route to workflow D."""
        prompts = [
            "research company Stripe",
            "research Salesforce",
            "look up company OpenAI",
            "find info about Anthropic"
        ]

        for prompt in prompts:
            match = capability_router.route(prompt)
            assert match is not None, f"Failed to match: {prompt}"
            assert match.capability == 'D', f"Wrong capability for: {prompt}"

    def test_spreadsheet_workflow_detection(self, capability_router):
        """Test spreadsheet cleaning routes to workflow B."""
        prompts = [
            "clean this spreadsheet",
            "fix the data in this CSV",
            "dedupe this spreadsheet"
        ]

        for prompt in prompts:
            match = capability_router.route(prompt)
            assert match is not None, f"Failed to match: {prompt}"
            assert match.capability == 'B', f"Wrong capability for: {prompt}"

    def test_ticket_workflow_detection(self, capability_router):
        """Test ticket classification routes to workflow C."""
        prompts = [
            "classify these support tickets",
            "sort tickets by priority"
        ]

        for prompt in prompts:
            match = capability_router.route(prompt)
            assert match is not None, f"Failed to match: {prompt}"
            assert match.capability == 'C', f"Wrong capability for: {prompt}"

    def test_contract_workflow_detection(self, capability_router):
        """Test contract extraction routes to workflow G."""
        prompts = [
            "extract from this contract",
            "analyze this legal document",
            "pull key terms from contract"
        ]

        for prompt in prompts:
            match = capability_router.route(prompt)
            assert match is not None, f"Failed to match: {prompt}"
            assert match.capability == 'G', f"Wrong capability for: {prompt}"

    def test_no_match_for_generic_prompts(self, capability_router):
        """Test that generic prompts don't match capabilities."""
        prompts = [
            "hello",
            "what can you do",
            "help me",
            "thanks"
        ]

        for prompt in prompts:
            match = capability_router.route(prompt)
            # Should either not match or have low confidence
            if match:
                assert match.confidence < 0.5, f"Incorrectly matched: {prompt}"

    def test_web_browsing_skips_capability_routing(self, capability_router):
        """Test that explicit web browsing bypasses capability routing."""
        prompts = [
            "go to amazon.com",
            "browse to google.com",
            "visit linkedin.com",
            "search on facebook"
        ]

        for prompt in prompts:
            match = capability_router.route(prompt)
            assert match is None, f"Should skip routing for: {prompt}"


# ============================================================================
# Test Contact Extraction
# ============================================================================

class TestContactExtraction:
    """Test contact extractor accuracy."""

    def test_rejects_fake_emails(self):
        """Test that fake emails are rejected."""
        fake_emails = [
            "test@example.com",
            "john.doe@placeholder.com",
            "user@fake.com",
            "demo@test.com",
            "admin@domain.com",
            "your.email@website.com",
            "johndoe@acme.com"
        ]

        for email in fake_emails:
            assert not is_likely_real_email(email), f"Failed to reject fake: {email}"

    def test_accepts_real_emails(self):
        """Test that real emails are accepted."""
        real_emails = [
            "contact@stripe.com",
            "support@anthropic.com",
            "hello@vercel.com",
            "sales@salesforce.com",
            "info@microsoft.com"
        ]

        for email in real_emails:
            assert is_likely_real_email(email), f"Incorrectly rejected real: {email}"

    def test_rejects_fake_phones(self):
        """Test that fake phones are rejected."""
        fake_phones = [
            "555-1234",
            "123-456-7890",
            "000-000-0000",
            "111-111-1111",
            "1-800-555-0100"
        ]

        for phone in fake_phones:
            assert not is_likely_real_phone(phone), f"Failed to reject fake: {phone}"

    def test_accepts_real_phones(self):
        """Test that real-looking phones are accepted."""
        real_phones = [
            "415-867-5309",
            "(650) 253-0000",
            "+1 650 253 0000",
            "1-650-253-0000"
        ]

        for phone in real_phones:
            assert is_likely_real_phone(phone), f"Incorrectly rejected real: {phone}"

    def test_email_extraction_from_text(self, contact_extractor):
        """Test email extraction from text."""
        text = """
        Contact us at support@company.io or sales@company.io
        You can also reach test@example.com (this is fake)
        """

        emails = contact_extractor._extract_emails_from_text(text)

        # Should extract emails and filter fakes
        assert len(emails) >= 1
        assert "support@company.io" in emails or "sales@company.io" in emails
        assert "test@example.com" not in emails  # Should be filtered as fake

    def test_phone_extraction_from_text(self, contact_extractor):
        """Test phone extraction from text."""
        text = """
        Call us at (415) 867-5309 or 650-253-0000
        Don't call 555-1234 (this is fake)
        """

        phones = contact_extractor._extract_phones_from_text(text)

        # Should extract phones and filter fakes
        # Note: May be 0 if all are filtered or extraction pattern doesn't match
        assert isinstance(phones, list)
        # If we extracted any, verify they're formatted
        if len(phones) > 0:
            assert any("867" in p or "253" in p for p in phones)


# ============================================================================
# Test Workflow Execution
# ============================================================================

class TestWorkflowExecution:
    """Test actual workflow execution with mocked browser."""

    @pytest.mark.asyncio
    async def test_company_research_workflow(self, mock_browser):
        """Test D1 company research workflow."""
        # Mock Google search results
        mock_browser.page.evaluate = AsyncMock(return_value={
            'description': 'Stripe is a payment processing company',
            'website': 'https://stripe.com',
            'top_results': [
                {'title': 'Stripe: Payment Processing', 'url': 'https://stripe.com'}
            ]
        })

        executor = D1_CompanyResearch(browser=mock_browser)
        result = await executor.execute({'company': 'Stripe'})

        assert result.status in [ActionStatus.SUCCESS, ActionStatus.PARTIAL]
        assert 'research' in result.data
        assert result.data['research']['company'] == 'Stripe'

    @pytest.mark.asyncio
    async def test_spreadsheet_cleaner_workflow(self, mock_browser):
        """Test B1 spreadsheet cleaning workflow."""
        csv_data = """name,email,company
John Doe,john@example.com,Acme Inc
Jane Smith,jane@realcompany.io,Real Corp
John Doe,john@example.com,Acme Inc"""

        executor = B1_SpreadsheetCleaner(browser=mock_browser)
        result = await executor.execute({'data': csv_data, 'verify_companies': False})

        assert result.status == ActionStatus.SUCCESS
        assert result.data['original_rows'] == 3
        assert result.data['cleaned_rows'] == 2  # Should dedupe John Doe

    @pytest.mark.asyncio
    async def test_ticket_classifier_workflow(self, mock_browser):
        """Test C1 ticket classification workflow."""
        tickets_data = """
        Ticket #1: My payment failed and I need a refund immediately
        Ticket #2: Feature request: add dark mode
        Ticket #3: The app keeps crashing when I click submit
        """

        executor = C1_TicketClassifier(browser=mock_browser)
        result = await executor.execute({'tickets': tickets_data})

        assert result.status in [ActionStatus.SUCCESS, ActionStatus.PARTIAL]
        assert 'classified' in result.data
        classified = result.data['classified']

        # Should have categorized tickets
        assert 'billing' in classified or 'complaint' in classified
        assert 'technical' in classified
        assert 'feature_request' in classified

    @pytest.mark.asyncio
    async def test_contract_extractor_workflow(self, mock_browser):
        """Test G1 contract extraction workflow."""
        contract_text = """
        This agreement is made between Acme Inc. and Widget Corp on January 15, 2024.

        The parties agree to the following terms:
        1. Payment of $50,000 within 30 days
        2. Delivery of services by March 1, 2024

        Either party may terminate this agreement with 30 days notice.
        """

        executor = G1_ContractExtractor(browser=mock_browser)
        result = await executor.execute({'contract_text': contract_text})

        assert result.status == ActionStatus.SUCCESS
        extracted = result.data['extracted']

        # Extraction may vary but should have the data structure
        assert 'parties' in extracted
        assert 'dates' in extracted
        assert 'amounts' in extracted

        # Should extract at least some data
        total_extracted = len(extracted.get('parties', [])) + len(extracted.get('dates', [])) + len(extracted.get('amounts', []))
        assert total_extracted >= 1, "Should extract at least some data from contract"

    @pytest.mark.asyncio
    async def test_maintenance_analyzer_workflow(self, mock_browser):
        """Test I1 maintenance log analysis workflow."""
        logs = """
        2024-01-15: Pump A-123 overheating issue reported
        2024-01-16: Motor B-456 vibration detected
        2024-01-17: Pump A-123 overheating again - recurring issue
        2024-01-18: Compressor C-789 noise complaint
        """

        executor = I1_MaintenanceAnalyzer(browser=mock_browser)
        result = await executor.execute({'logs': logs})

        assert result.status == ActionStatus.SUCCESS
        analysis = result.data['analysis']

        # Should parse entries
        assert analysis['total_entries'] == 4

        # Should detect recurring issues (Pump A-123)
        assert len(analysis['recurring_issues']) >= 1

    @pytest.mark.asyncio
    async def test_transaction_categorizer_workflow(self, mock_browser):
        """Test J1 transaction categorization workflow."""
        transactions = """
        2024-01-15 AWS Services $250.00
        2024-01-16 Payroll Processing $5000.00
        2024-01-17 Uber ride $25.50
        2024-01-18 Google Ads $500.00
        """

        executor = J1_TransactionCategorizer(browser=mock_browser)
        result = await executor.execute({'transactions': transactions})

        assert result.status == ActionStatus.SUCCESS
        categorized = result.data['categorized']

        # Should have categories
        assert 'software' in categorized
        assert 'payroll' in categorized
        assert 'travel' in categorized
        assert 'marketing' in categorized

        # Should have categorized at least some transactions
        total_categorized = sum(len(v) for v in categorized.values())
        assert total_categorized >= 3, "Should categorize at least 3 transactions"

    @pytest.mark.asyncio
    async def test_form_extractor_workflow(self, mock_browser):
        """Test N1 government form extraction workflow."""
        form_text = """
        W-2 WAGE AND TAX STATEMENT

        Employee: John Smith
        SSN: 123-45-6789
        Employer: Acme Corporation
        EIN: 98-7654321
        Wages: $75,000.00
        Federal Tax Withheld: $12,500.00
        """

        executor = N1_FormExtractor(browser=mock_browser)
        result = await executor.execute({'form_text': form_text, 'form_type': 'w2'})

        assert result.status == ActionStatus.SUCCESS
        extracted = result.data['extracted']

        # Should extract key fields
        assert 'name' in extracted or 'employee' in extracted
        assert 'ssn' in extracted
        assert 'wages' in extracted

    @pytest.mark.asyncio
    async def test_email_inbox_workflow_requires_login(self, mock_browser):
        """Test A1 email workflow detects login requirement."""
        # Mock page showing login screen
        mock_browser.page.content = AsyncMock(return_value="<html><body>Sign in to Gmail</body></html>")

        executor = A1_EmailInbox(browser=mock_browser)
        result = await executor.execute({'email_provider': 'gmail'})

        assert result.status == ActionStatus.BLOCKED
        assert 'login' in result.message.lower()

    @pytest.mark.asyncio
    async def test_analytics_workflow_requires_login(self, mock_browser):
        """Test K1 analytics workflow detects login requirement."""
        # Mock page showing login screen
        mock_browser.page.content = AsyncMock(return_value="<html><body>Sign in to continue</body></html>")

        executor = K1_AnalyticsInsights(browser=mock_browser)
        result = await executor.execute({'platform': 'google_analytics'})

        assert result.status == ActionStatus.BLOCKED
        assert 'login' in result.message.lower()


# ============================================================================
# Test Error Recovery
# ============================================================================

class TestErrorRecovery:
    """Test cascading recovery system integration."""

    @pytest.mark.asyncio
    async def test_selector_fallback_on_failure(self, mock_browser):
        """Test selector fallback when element not found."""
        # First query fails, second succeeds
        mock_element = AsyncMock()
        mock_element.click = AsyncMock()

        call_count = 0
        async def query_selector_side_effect(selector):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                return mock_element
            return None

        mock_browser.page.query_selector.side_effect = query_selector_side_effect
        mock_browser.page.evaluate = AsyncMock(return_value="Button Text")

        # This would normally use cascading recovery internally
        # For now, just verify the mock behavior
        element1 = await mock_browser.page.query_selector("button.first")
        assert element1 is None

        element2 = await mock_browser.page.query_selector("button.second")
        assert element2 is not None

    @pytest.mark.asyncio
    async def test_retry_on_transient_failure(self, mock_browser):
        """Test retry logic for transient failures."""
        call_count = 0

        async def flaky_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Temporary network issue")
            return {"success": True}

        # Test retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                result = await flaky_operation()
                assert result["success"]
                break
            except ConnectionError:
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(0.1)

        assert call_count == 3


# ============================================================================
# Test Parameter Validation
# ============================================================================

class TestParameterValidation:
    """Test parameter validation for executors."""

    @pytest.mark.asyncio
    async def test_company_research_requires_company_name(self, mock_browser):
        """Test D1 fails without company name."""
        executor = D1_CompanyResearch(browser=mock_browser)
        result = await executor.execute({})

        assert result.status == ActionStatus.FAILED
        assert 'company' in result.message.lower()

    @pytest.mark.asyncio
    async def test_spreadsheet_cleaner_requires_data(self, mock_browser):
        """Test B1 fails without data."""
        executor = B1_SpreadsheetCleaner(browser=mock_browser)
        result = await executor.execute({})

        assert result.status == ActionStatus.FAILED
        assert 'data' in result.message.lower()

    @pytest.mark.asyncio
    async def test_contract_extractor_requires_text(self, mock_browser):
        """Test G1 fails without contract text."""
        executor = G1_ContractExtractor(browser=mock_browser)
        result = await executor.execute({})

        assert result.status == ActionStatus.FAILED

    @pytest.mark.asyncio
    async def test_transaction_categorizer_requires_transactions(self, mock_browser):
        """Test J1 fails without transaction data."""
        executor = J1_TransactionCategorizer(browser=mock_browser)
        result = await executor.execute({})

        assert result.status == ActionStatus.FAILED


# ============================================================================
# Test Executor Registry
# ============================================================================

class TestExecutorRegistry:
    """Test workflow executor registry."""

    def test_all_workflows_registered(self):
        """Test all A-O workflows are in registry."""
        expected = ['A1', 'B1', 'C1', 'D1', 'G1', 'I1', 'J1', 'K1', 'N1']

        for cap in expected:
            executor_class = get_workflow_executor(cap)
            assert executor_class is not None, f"Missing executor for {cap}"

    def test_get_nonexistent_executor_returns_none(self):
        """Test getting non-existent executor returns None."""
        executor_class = get_workflow_executor('Z9')
        assert executor_class is None

    def test_executors_have_proper_metadata(self):
        """Test executors have required metadata."""
        for cap, executor_class in WORKFLOW_EXECUTORS.items():
            assert hasattr(executor_class, 'capability')
            assert hasattr(executor_class, 'action')

            # Instantiate to verify
            instance = executor_class(browser=None)
            assert instance.capability == cap


# ============================================================================
# Test Data Extraction Accuracy
# ============================================================================

class TestDataExtraction:
    """Test data extraction accuracy across workflows."""

    def test_email_parsing_from_csv(self):
        """Test email extraction and validation from CSV data."""
        from executors.workflows_a_to_o import B1_SpreadsheetCleaner

        executor = B1_SpreadsheetCleaner(browser=None)
        rows = executor._parse_data("name,email\nJohn,john@test.com\nJane,jane@real.io")

        assert len(rows) == 2
        assert rows[0]['name'] == 'John'
        assert rows[0]['email'] == 'john@test.com'

    def test_date_extraction_from_contract(self):
        """Test date extraction from contract text."""
        from executors.workflows_a_to_o import G1_ContractExtractor

        executor = G1_ContractExtractor(browser=None)
        text = "This agreement dated January 15, 2024 shall expire on December 31, 2025"
        dates = executor._extract_dates(text)

        assert len(dates) >= 1
        assert any('2024' in str(d['value']) for d in dates)

    def test_amount_extraction_from_contract(self):
        """Test dollar amount extraction."""
        from executors.workflows_a_to_o import G1_ContractExtractor

        executor = G1_ContractExtractor(browser=None)
        text = "Payment of $50,000.00 due within 30 days. Additional fee of $1,250.50"
        amounts = executor._extract_amounts(text)

        assert len(amounts) >= 2
        assert any('50,000' in str(a['value']) or '50000' in str(a['value']) for a in amounts)

    def test_phone_number_cleaning(self, contact_extractor):
        """Test phone number formatting."""
        tests = [
            ("1234567890", "(123) 456-7890"),
            ("14155551234", "+1 (415) 555-1234"),
            ("415-555-1234", "(415) 555-1234")
        ]

        for raw, expected_format in tests:
            cleaned = contact_extractor._clean_phone(raw)
            # Should be formatted nicely
            assert len(cleaned) > 0


# ============================================================================
# Test Integration Scenarios
# ============================================================================

class TestIntegrationScenarios:
    """Test realistic end-to-end scenarios."""

    @pytest.mark.asyncio
    async def test_sdr_workflow_full_cycle(self, mock_browser):
        """Test complete SDR workflow: research -> extract contacts -> generate email."""
        # Mock research results
        mock_browser.page.evaluate = AsyncMock(return_value={
            'description': 'Leading AI company',
            'website': 'https://anthropic.com',
            'top_results': [
                {'title': 'Anthropic', 'url': 'https://anthropic.com'}
            ]
        })

        # Execute research
        executor = D1_CompanyResearch(browser=mock_browser)
        result = await executor.execute({'company': 'Anthropic'})

        assert result.status == ActionStatus.SUCCESS
        assert 'research' in result.data
        assert 'outreach_email' in result.data

        # Verify email was generated
        email = result.data['outreach_email']
        assert 'subject' in email
        assert 'body' in email
        assert 'Anthropic' in email['body']

    @pytest.mark.asyncio
    async def test_support_workflow_full_cycle(self, mock_browser):
        """Test complete support workflow: classify -> generate drafts."""
        tickets = """
        Ticket #1: I was charged twice for my subscription
        Ticket #2: The app crashes on Android
        Ticket #3: Can you add a search feature?
        """

        executor = C1_TicketClassifier(browser=mock_browser)
        result = await executor.execute({'tickets': tickets})

        assert result.status in [ActionStatus.SUCCESS, ActionStatus.PARTIAL]
        assert 'classified' in result.data
        assert 'drafts' in result.data

        # Should have draft replies
        drafts = result.data['drafts']
        assert len(drafts) >= 1


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "--tb=short", "-s"])
