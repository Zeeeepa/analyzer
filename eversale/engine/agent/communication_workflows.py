"""
Communication Workflows - Unified entry point for all communication-related workflows.

Consolidates:
- Workflow A: Email/Inbox Triage (from capabilities.py)
- Workflow C: Support Ticket Classification (from capabilities.py)
- Email Outreach: Cold email campaigns (from email_outreach.py)
- Gmail/Outlook browser automation

This module provides a single import point for all communication functionality.
"""

import asyncio
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from loguru import logger

# Re-export from capabilities
from .capabilities import (
    Capabilities,
    CapabilityResult,
    caps,
    admin_triage,
    custops_tickets,
)

# Re-export from email_outreach
from .email_outreach import (
    EmailOutreach,
    EmailTemplate,
    EmailResult,
    Lead,
    TEMPLATES,
    compose_cold_emails,
    preview_email,
)


@dataclass
class CommunicationResult:
    """Unified result type for communication workflows."""
    success: bool
    workflow: str  # 'A', 'C', 'outreach', 'gmail', 'zendesk'
    output: str
    data: Any = None
    emails_processed: int = 0
    emails_sent: int = 0
    tickets_processed: int = 0
    files_created: List[str] = field(default_factory=list)
    error: str = ""


class CommunicationWorkflows:
    """
    Unified interface for all communication workflows.

    Workflows:
    - A: Email inbox triage and reply drafting
    - C: Support ticket classification and responses
    - Outreach: Cold email campaign management
    - Gmail: Direct Gmail automation via browser
    - Zendesk: Support ticket system integration
    """

    def __init__(self, config: Optional[Dict] = None, browser=None):
        """
        Initialize communication workflows.

        Args:
            config: Optional configuration dict
            browser: Optional browser instance for Gmail/Zendesk automation
        """
        self.config = config or {}
        self.browser = browser
        self.capabilities = Capabilities()
        self.email_outreach = EmailOutreach(config)
        self._stats = {
            'emails_triaged': 0,
            'tickets_classified': 0,
            'emails_sent': 0,
            'drafts_created': 0,
        }

    # =========================================================================
    # Workflow A: Email/Inbox Triage
    # =========================================================================

    def triage_inbox(self, emails: Union[str, List[Dict]]) -> CommunicationResult:
        """
        Workflow A: Triage inbox emails - categorize by priority and draft replies.

        Args:
            emails: Raw email text or list of email dicts with keys:
                   - from: sender email/name
                   - subject: email subject
                   - body: email body text

        Returns:
            CommunicationResult with triaged emails and draft replies

        Example:
            >>> result = comm.triage_inbox([
            ...     {"from": "boss@company.com", "subject": "Urgent: Q4 Review", "body": "Need the report ASAP"},
            ...     {"from": "newsletter@spam.com", "subject": "Weekly Deals", "body": "Check out..."}
            ... ])
            >>> print(result.output)
        """
        result = self.capabilities.admin_triage_inbox(emails)

        emails_count = len(result.data) if result.data else 0
        self._stats['emails_triaged'] += emails_count

        return CommunicationResult(
            success=result.success,
            workflow='A',
            output=result.output,
            data=result.data,
            emails_processed=emails_count,
            error=result.error
        )

    def draft_reply(self, email: Dict, tone: str = "professional") -> CommunicationResult:
        """
        Draft a reply to a single email.

        Args:
            email: Email dict with from, subject, body
            tone: Reply tone - 'professional', 'friendly', 'formal'

        Returns:
            CommunicationResult with draft reply
        """
        email_text = f"From: {email.get('from', '')}\nSubject: {email.get('subject', '')}\n{email.get('body', '')}"

        reply_result = self.capabilities.processor.draft_reply(email_text, tone=tone)

        if reply_result.success:
            self._stats['drafts_created'] += 1
            draft = reply_result.data.get('reply', '')
            return CommunicationResult(
                success=True,
                workflow='A',
                output=f"**Draft Reply:**\n\n{draft}",
                data={'draft': draft, 'tone': tone}
            )

        return CommunicationResult(
            success=False,
            workflow='A',
            output="",
            error="Failed to generate reply"
        )

    async def process_gmail_inbox(self, limit: int = 10) -> CommunicationResult:
        """
        Process Gmail inbox via browser automation.

        Requires browser instance with logged-in Gmail session.

        Args:
            limit: Max emails to process

        Returns:
            CommunicationResult with processed emails
        """
        if not self.browser:
            return CommunicationResult(
                success=False,
                workflow='gmail',
                output="",
                error="Browser not available. Please provide browser instance."
            )

        try:
            # Navigate to Gmail
            await self.browser.navigate("https://mail.google.com/mail/u/0/#inbox")
            await asyncio.sleep(2)

            # Check if logged in
            page_content = await self.browser.page.content()
            if "Sign in" in page_content:
                return CommunicationResult(
                    success=False,
                    workflow='gmail',
                    output="",
                    error="Gmail not logged in. Please login to Gmail first."
                )

            # Extract email subjects from inbox
            emails = await self.browser.page.query_selector_all('tr.zA')
            extracted = []

            for i, email_row in enumerate(emails[:limit]):
                try:
                    subject_el = await email_row.query_selector('.bog')
                    sender_el = await email_row.query_selector('.yP, .zF')
                    snippet_el = await email_row.query_selector('.y2')

                    subject = await subject_el.text_content() if subject_el else ""
                    sender = await sender_el.text_content() if sender_el else ""
                    snippet = await snippet_el.text_content() if snippet_el else ""

                    extracted.append({
                        'from': sender.strip(),
                        'subject': subject.strip(),
                        'body': snippet.strip()
                    })
                except Exception as e:
                    logger.debug(f"Failed to extract email {i}: {e}")
                    continue

            if not extracted:
                return CommunicationResult(
                    success=True,
                    workflow='gmail',
                    output="Inbox is empty or no emails found.",
                    data=[],
                    emails_processed=0
                )

            # Triage the extracted emails
            triage_result = self.triage_inbox(extracted)

            return CommunicationResult(
                success=True,
                workflow='gmail',
                output=f"**Gmail Inbox Processed**\n\n{triage_result.output}",
                data=triage_result.data,
                emails_processed=len(extracted)
            )

        except Exception as e:
            logger.error(f"Gmail processing failed: {e}")
            return CommunicationResult(
                success=False,
                workflow='gmail',
                output="",
                error=str(e)
            )

    # =========================================================================
    # Workflow C: Support Ticket Classification
    # =========================================================================

    def classify_tickets(self, tickets: Union[str, List[Dict]]) -> CommunicationResult:
        """
        Workflow C: Classify support tickets and draft responses.

        Args:
            tickets: Ticket text (separated by ---) or list of ticket dicts with:
                    - id: ticket ID
                    - content/body: ticket content

        Returns:
            CommunicationResult with classified tickets and draft replies

        Example:
            >>> result = comm.classify_tickets([
            ...     {"id": "T-001", "content": "I can't login to my account"},
            ...     {"id": "T-002", "content": "How do I upgrade my plan?"}
            ... ])
        """
        result = self.capabilities.custops_classify_tickets(tickets)

        tickets_count = len(result.data) if result.data else 0
        self._stats['tickets_classified'] += tickets_count

        return CommunicationResult(
            success=result.success,
            workflow='C',
            output=result.output,
            data=result.data,
            tickets_processed=tickets_count,
            error=result.error
        )

    async def process_zendesk_queue(self, limit: int = 10) -> CommunicationResult:
        """
        Process Zendesk support queue via browser automation.

        Requires browser instance with logged-in Zendesk session.

        Args:
            limit: Max tickets to process

        Returns:
            CommunicationResult with processed tickets
        """
        if not self.browser:
            return CommunicationResult(
                success=False,
                workflow='zendesk',
                output="",
                error="Browser not available. Please provide browser instance."
            )

        try:
            # This would need the actual Zendesk subdomain
            zendesk_url = self.config.get('zendesk_url', 'https://your-company.zendesk.com/agent')
            await self.browser.navigate(zendesk_url)
            await asyncio.sleep(2)

            # Check if logged in
            page_content = await self.browser.page.content()
            if "Sign in" in page_content or "Log in" in page_content:
                return CommunicationResult(
                    success=False,
                    workflow='zendesk',
                    output="",
                    error="Zendesk not logged in. Please login first."
                )

            # Extract tickets from queue
            # Note: Selectors may vary based on Zendesk version
            ticket_rows = await self.browser.page.query_selector_all('[data-test-id="ticket-list-item"]')
            extracted = []

            for i, row in enumerate(ticket_rows[:limit]):
                try:
                    subject_el = await row.query_selector('[data-test-id="ticket-subject"]')
                    requester_el = await row.query_selector('[data-test-id="ticket-requester"]')

                    subject = await subject_el.text_content() if subject_el else ""
                    requester = await requester_el.text_content() if requester_el else ""

                    extracted.append({
                        'id': f"ZD-{i+1}",
                        'content': subject.strip(),
                        'requester': requester.strip()
                    })
                except Exception as e:
                    logger.debug(f"Failed to extract ticket {i}: {e}")
                    continue

            if not extracted:
                return CommunicationResult(
                    success=True,
                    workflow='zendesk',
                    output="No tickets in queue.",
                    data=[],
                    tickets_processed=0
                )

            # Classify the tickets
            classify_result = self.classify_tickets(extracted)

            return CommunicationResult(
                success=True,
                workflow='zendesk',
                output=f"**Zendesk Queue Processed**\n\n{classify_result.output}",
                data=classify_result.data,
                tickets_processed=len(extracted)
            )

        except Exception as e:
            logger.error(f"Zendesk processing failed: {e}")
            return CommunicationResult(
                success=False,
                workflow='zendesk',
                output="",
                error=str(e)
            )

    # =========================================================================
    # Email Outreach Campaigns
    # =========================================================================

    def prepare_outreach(
        self,
        leads: List[Dict],
        template: str = "cold_intro"
    ) -> CommunicationResult:
        """
        Prepare cold email outreach campaign.

        Args:
            leads: List of lead dicts with email, name, company, etc.
            template: Template name - 'cold_intro', 'cold_casual', 'warm_intro',
                     'follow_up_1', 'follow_up_2'

        Returns:
            CommunicationResult with composed emails ready for review/sending

        Example:
            >>> leads = [
            ...     {"email": "john@acme.com", "name": "John Smith", "company": "Acme Corp"},
            ...     {"email": "jane@tech.io", "name": "Jane Doe", "company": "Tech Inc"}
            ... ]
            >>> result = comm.prepare_outreach(leads, template="cold_intro")
        """
        # Normalize and compose
        normalized = self.email_outreach.normalize_leads(leads)
        composed = self.email_outreach.compose_batch(normalized, template)

        # Export for review
        if composed:
            export_path = self.email_outreach.export_for_review(composed)

            output = f"**Outreach Campaign Prepared**\n\n"
            output += f"- Leads processed: {len(leads)}\n"
            output += f"- Valid emails: {len(normalized)}\n"
            output += f"- Emails composed: {len(composed)}\n"
            output += f"- Template: {template}\n"
            output += f"- Exported to: {export_path}\n\n"
            output += "**Preview (first email):**\n"
            if composed:
                first = composed[0]
                output += f"To: {first['to']}\n"
                output += f"Subject: {first['subject']}\n"
                output += f"Body:\n{first['body'][:300]}..."

            return CommunicationResult(
                success=True,
                workflow='outreach',
                output=output,
                data=composed,
                emails_processed=len(composed),
                files_created=[export_path]
            )

        return CommunicationResult(
            success=False,
            workflow='outreach',
            output="",
            error="No valid leads to compose emails for"
        )

    async def send_outreach(
        self,
        emails: List[Dict],
        provider: str = "gmail",
        dry_run: bool = True
    ) -> CommunicationResult:
        """
        Send outreach emails via browser automation.

        Args:
            emails: List of email dicts from prepare_outreach
            provider: 'gmail' or 'outlook'
            dry_run: If True, don't actually send (preview only)

        Returns:
            CommunicationResult with send results
        """
        if not self.browser:
            return CommunicationResult(
                success=False,
                workflow='outreach',
                output="",
                error="Browser not available"
            )

        if dry_run:
            output = "**DRY RUN - No emails sent**\n\n"
            output += f"Would send {len(emails)} emails via {provider}:\n\n"
            for i, email in enumerate(emails[:5], 1):
                output += f"{i}. To: {email['to']} | Subject: {email['subject'][:40]}...\n"
            if len(emails) > 5:
                output += f"... and {len(emails) - 5} more\n"

            return CommunicationResult(
                success=True,
                workflow='outreach',
                output=output,
                data=emails,
                emails_processed=len(emails)
            )

        # Actually send
        results = await self.email_outreach.send_batch(
            emails,
            browser=self.browser,
            provider=provider
        )

        sent_count = sum(1 for r in results if r.success)
        failed_count = len(results) - sent_count

        self._stats['emails_sent'] += sent_count

        output = f"**Outreach Campaign Results**\n\n"
        output += f"- Sent: {sent_count}\n"
        output += f"- Failed: {failed_count}\n"
        output += f"- Provider: {provider}\n"

        return CommunicationResult(
            success=sent_count > 0,
            workflow='outreach',
            output=output,
            data=[{'lead': r.lead.email, 'success': r.success, 'error': r.error} for r in results],
            emails_sent=sent_count,
            emails_processed=len(results)
        )

    def create_sequence(
        self,
        lead: Dict,
        steps: int = 3,
        delays_days: List[int] = None
    ) -> CommunicationResult:
        """
        Create multi-step email sequence for a lead.

        Args:
            lead: Lead dict with email, name, company
            steps: Number of emails in sequence (1-3)
            delays_days: Days between each email [0, 3, 7]

        Returns:
            CommunicationResult with email sequence
        """
        normalized = self.email_outreach.normalize_leads([lead])
        if not normalized:
            return CommunicationResult(
                success=False,
                workflow='outreach',
                output="",
                error="Invalid lead data"
            )

        sequence = self.email_outreach.generate_sequence(
            normalized[0],
            steps=steps,
            delays=delays_days
        )

        output = f"**Email Sequence Created**\n\n"
        output += f"Lead: {normalized[0].email}\n\n"

        for email in sequence:
            output += f"**Step {email['step']}** (scheduled: {email['scheduled_for'][:10]})\n"
            output += f"Subject: {email['subject']}\n"
            output += f"Template: {email['template']}\n\n"

        return CommunicationResult(
            success=True,
            workflow='outreach',
            output=output,
            data=sequence,
            emails_processed=len(sequence)
        )

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def get_stats(self) -> Dict[str, Any]:
        """Get communication workflow statistics."""
        return {
            **self._stats,
            'outreach_stats': self.email_outreach.get_stats()
        }

    def add_template(self, name: str, subject: str, body: str, variables: List[str] = None):
        """
        Add a custom email template.

        Args:
            name: Template name
            subject: Subject line with {variables}
            body: Body text with {variables}
            variables: List of variable names used
        """
        template = EmailTemplate(
            name=name,
            subject=subject,
            body=body,
            variables=variables or []
        )
        self.email_outreach.add_template(name, template)


# Convenience instance
comm = CommunicationWorkflows()


# Quick access functions
def triage_inbox(emails) -> CommunicationResult:
    """Workflow A: Triage inbox emails."""
    return comm.triage_inbox(emails)


def classify_tickets(tickets) -> CommunicationResult:
    """Workflow C: Classify support tickets."""
    return comm.classify_tickets(tickets)


def prepare_outreach(leads, template="cold_intro") -> CommunicationResult:
    """Prepare cold email outreach."""
    return comm.prepare_outreach(leads, template)


def draft_reply(email, tone="professional") -> CommunicationResult:
    """Draft a reply to an email."""
    return comm.draft_reply(email, tone)


# Async functions for browser automation
async def process_gmail(browser, limit=10) -> CommunicationResult:
    """Process Gmail inbox via browser."""
    workflow = CommunicationWorkflows(browser=browser)
    return await workflow.process_gmail_inbox(limit)


async def process_zendesk(browser, config=None, limit=10) -> CommunicationResult:
    """Process Zendesk queue via browser."""
    workflow = CommunicationWorkflows(config=config, browser=browser)
    return await workflow.process_zendesk_queue(limit)


async def send_emails(browser, emails, provider="gmail", dry_run=True) -> CommunicationResult:
    """Send outreach emails via browser."""
    workflow = CommunicationWorkflows(browser=browser)
    return await workflow.send_outreach(emails, provider, dry_run)
