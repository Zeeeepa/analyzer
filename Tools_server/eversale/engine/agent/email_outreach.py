"""
Email Outreach - Optimized for speed, accuracy, and token efficiency.

Key optimizations:
1. Template-based emails (no LLM per email)
2. Batch processing with deduplication
3. Smart personalization from existing data
4. Rate limiting to avoid spam flags
5. Verification before sending
6. Progress tracking
"""

import asyncio
import re
import csv
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from loguru import logger


@dataclass
class EmailTemplate:
    """Pre-defined email template for fast generation."""
    name: str
    subject: str
    body: str
    variables: List[str] = field(default_factory=list)

    def render(self, data: Dict[str, str]) -> Dict[str, str]:
        """Render template with data. Fast string replacement, no LLM."""
        subject = self.subject
        body = self.body

        for var in self.variables:
            placeholder = f"{{{var}}}"
            value = data.get(var, f"[{var}]")
            subject = subject.replace(placeholder, str(value))
            body = body.replace(placeholder, str(value))

        return {"subject": subject, "body": body}


@dataclass
class Lead:
    """Lead with normalized data."""
    email: str
    name: str = ""
    company: str = ""
    website: str = ""
    source: str = ""
    tech_stack: List[str] = field(default_factory=list)
    warm_signal: str = ""
    score: int = 0
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def first_name(self) -> str:
        """Extract first name."""
        if self.name:
            return self.name.split()[0]
        return ""

    @property
    def personalization_hook(self) -> str:
        """Generate a personalization hook from available data."""
        if self.tech_stack:
            return f"I noticed you're using {self.tech_stack[0]}"
        if self.warm_signal:
            return f"I saw your post about {self.warm_signal}"
        if self.source == "fb_ads":
            return "I came across your ads"
        return "I came across your company"


@dataclass
class EmailResult:
    """Result of email operation."""
    lead: Lead
    success: bool
    email_sent: Optional[Dict[str, str]] = None
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


# Pre-built templates - no LLM needed
TEMPLATES = {
    "cold_intro": EmailTemplate(
        name="cold_intro",
        subject="Quick question about {company}",
        body="""Hi {first_name},

{personalization}. I wanted to reach out because we help companies like {company} [VALUE PROP].

Would you be open to a quick 15-minute chat this week?

Best,
[Your Name]""",
        variables=["first_name", "company", "personalization"]
    ),

    "cold_casual": EmailTemplate(
        name="cold_casual",
        subject="Hey from [Your Company]",
        body="""Hey {first_name}!

{personalization} and thought you might be interested in how we're helping companies [VALUE PROP].

No pressure - just thought it might be worth a quick chat if you're curious.

Cheers,
[Your Name]""",
        variables=["first_name", "personalization"]
    ),

    "follow_up_1": EmailTemplate(
        name="follow_up_1",
        subject="Re: Quick question about {company}",
        body="""Hi {first_name},

Just following up on my previous email. I know you're busy, but I think this could be valuable for {company}.

Would a 10-minute call work this week?

Best,
[Your Name]""",
        variables=["first_name", "company"]
    ),

    "follow_up_2": EmailTemplate(
        name="follow_up_2",
        subject="Re: Quick question about {company}",
        body="""Hi {first_name},

Last follow-up from me. If now isn't the right time, no worries - just let me know and I'll check back in a few months.

But if there's interest, I'd love to show you what we can do for {company}.

Best,
[Your Name]""",
        variables=["first_name", "company"]
    ),

    "warm_intro": EmailTemplate(
        name="warm_intro",
        subject="{personalization} - can we chat?",
        body="""Hi {first_name},

{personalization}. Really interesting perspective!

We're working on something that might be relevant - would love to get your thoughts.

Free for a quick call this week?

Best,
[Your Name]""",
        variables=["first_name", "personalization"]
    ),
}


class EmailOutreach:
    """
    Optimized email outreach system.

    Design principles:
    - Token efficient: Template-based, no LLM per email
    - Fast: Batch processing, async operations
    - Accurate: Deduplication, validation, verification
    - Tasteful: Rate limiting, personalization, not spammy
    """

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.rate_limit = config.get("emails_per_hour", 50) if config else 50
        self.delay_between = config.get("delay_seconds", 5) if config else 5
        self.sent_emails: List[str] = []  # Track sent to avoid duplicates
        self.templates = TEMPLATES.copy()
        self._load_sent_history()

    def _load_sent_history(self):
        """Load previously sent emails to avoid duplicates."""
        history_file = Path("memory/sent_emails.json")
        if history_file.exists():
            try:
                data = json.loads(history_file.read_text())
                self.sent_emails = data.get("emails", [])
            except:
                pass

    def _save_sent_history(self):
        """Persist sent email history."""
        history_file = Path("memory/sent_emails.json")
        history_file.parent.mkdir(parents=True, exist_ok=True)
        history_file.write_text(json.dumps({
            "emails": self.sent_emails[-1000:],  # Keep last 1000
            "updated": datetime.now().isoformat()
        }))

    def add_template(self, name: str, template: EmailTemplate):
        """Add custom template."""
        self.templates[name] = template

    def normalize_leads(self, raw_leads: List[Dict]) -> List[Lead]:
        """
        Normalize raw lead data into Lead objects.
        Handles various input formats efficiently.
        """
        normalized = []
        seen_emails = set(self.sent_emails)

        for raw in raw_leads:
            # Extract email - try multiple field names
            email = raw.get("email") or raw.get("contact_email") or ""
            if not email and isinstance(raw.get("emails"), list) and raw.get("emails"):
                email = raw["emails"][0] or ""

            if not email or not self._is_valid_email(email):
                continue

            email = email.lower().strip()

            # Skip duplicates
            if email in seen_emails:
                continue
            seen_emails.add(email)

            # Extract name
            name = raw.get("name") or raw.get("contact_name") or ""
            if not name and email:
                # Try to extract from email
                local = email.split("@")[0]
                if "." in local:
                    parts = local.split(".")
                    name = " ".join(p.capitalize() for p in parts[:2])

            # Create Lead
            lead = Lead(
                email=email,
                name=name,
                company=raw.get("company") or raw.get("company_name") or "",
                website=raw.get("website") or raw.get("url") or "",
                source=raw.get("source") or "",
                tech_stack=raw.get("tech_stack") or raw.get("techStack") or [],
                warm_signal=raw.get("warm_signal") or raw.get("warmSignalCategory") or "",
                score=raw.get("score") or 0,
                extra=raw
            )

            normalized.append(lead)

        return normalized

    def _is_valid_email(self, email: str) -> bool:
        """Quick email validation."""
        if not email or "@" not in email:
            return False
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

    def select_template(self, lead: Lead) -> EmailTemplate:
        """Select best template based on lead data."""
        # Warm leads get warm template
        if lead.warm_signal or lead.score >= 70:
            return self.templates["warm_intro"]

        # Default to cold intro
        return self.templates["cold_intro"]

    def compose_email(self, lead: Lead, template_name: Optional[str] = None) -> Dict[str, str]:
        """
        Compose email for a lead using template.
        No LLM calls - pure string replacement.
        """
        template = (
            self.templates.get(template_name) if template_name
            else self.select_template(lead)
        )

        data = {
            "first_name": lead.first_name or "there",
            "name": lead.name or "there",
            "company": lead.company or "your company",
            "personalization": lead.personalization_hook,
            "website": lead.website,
            "tech": lead.tech_stack[0] if lead.tech_stack else "",
        }

        return template.render(data)

    def compose_batch(
        self,
        leads: List[Lead],
        template_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Compose emails for multiple leads efficiently.
        Returns list of {lead, email} dicts.
        """
        results = []

        for lead in leads:
            email = self.compose_email(lead, template_name)
            results.append({
                "lead": lead,
                "to": lead.email,
                "subject": email["subject"],
                "body": email["body"],
                "template": template_name or "auto"
            })

        return results

    async def send_email(
        self,
        email: Dict[str, str],
        browser=None,
        provider: str = "gmail"
    ) -> EmailResult:
        """
        Send a single email via browser automation.

        Uses browser to interact with email provider.
        Rate-limited and validated.
        """
        lead = email.get("lead") or Lead(email=email["to"])

        # Check if already sent
        if email["to"] in self.sent_emails:
            return EmailResult(
                lead=lead,
                success=False,
                error="Already sent to this email"
            )

        if not browser:
            return EmailResult(
                lead=lead,
                success=False,
                error="Browser not available"
            )

        try:
            if provider == "gmail":
                success = await self._send_via_gmail(browser, email)
            else:
                success = await self._send_via_outlook(browser, email)

            if success:
                self.sent_emails.append(email["to"])
                self._save_sent_history()

                return EmailResult(
                    lead=lead,
                    success=True,
                    email_sent=email
                )
            else:
                return EmailResult(
                    lead=lead,
                    success=False,
                    error="Failed to send via provider"
                )

        except Exception as e:
            logger.error(f"Email send failed: {e}")
            return EmailResult(
                lead=lead,
                success=False,
                error=str(e)
            )

    async def _send_via_gmail(self, browser, email: Dict) -> bool:
        """Send email via Gmail compose."""
        try:
            # Navigate to Gmail compose
            await browser.navigate("https://mail.google.com/mail/u/0/#inbox?compose=new")
            await asyncio.sleep(2)

            # Check if logged in
            page_text = await browser.page.content()
            if "Sign in" in page_text:
                logger.warning("Gmail not logged in")
                return False

            # Fill compose form
            await browser.page.fill('input[name="to"]', email["to"])
            await asyncio.sleep(0.3)

            await browser.page.fill('input[name="subjectbox"]', email["subject"])
            await asyncio.sleep(0.3)

            # Find and fill body
            body_selector = 'div[aria-label="Message Body"]'
            await browser.page.click(body_selector)
            await browser.page.fill(body_selector, email["body"])
            await asyncio.sleep(0.3)

            # Click send (Ctrl+Enter or button)
            await browser.page.keyboard.press("Control+Enter")
            await asyncio.sleep(2)

            logger.info(f"Email sent to {email['to']}")
            return True

        except Exception as e:
            logger.error(f"Gmail send failed: {e}")
            return False

    async def _send_via_outlook(self, browser, email: Dict) -> bool:
        """Send email via Outlook compose."""
        try:
            await browser.navigate("https://outlook.live.com/mail/0/deeplink/compose")
            await asyncio.sleep(2)

            page_text = await browser.page.content()
            if "Sign in" in page_text:
                logger.warning("Outlook not logged in")
                return False

            # Fill compose form
            await browser.page.fill('input[aria-label="To"]', email["to"])
            await asyncio.sleep(0.3)

            await browser.page.fill('input[aria-label="Add a subject"]', email["subject"])
            await asyncio.sleep(0.3)

            body_selector = 'div[aria-label="Message body"]'
            await browser.page.click(body_selector)
            await browser.page.fill(body_selector, email["body"])
            await asyncio.sleep(0.3)

            # Click send
            await browser.page.click('button[aria-label="Send"]')
            await asyncio.sleep(2)

            logger.info(f"Email sent to {email['to']}")
            return True

        except Exception as e:
            logger.error(f"Outlook send failed: {e}")
            return False

    async def send_batch(
        self,
        emails: List[Dict],
        browser=None,
        provider: str = "gmail",
        on_progress: Optional[Callable] = None
    ) -> List[EmailResult]:
        """
        Send batch of emails with rate limiting.

        Args:
            emails: List of email dicts from compose_batch
            browser: Browser instance
            provider: Email provider
            on_progress: Callback(sent, total, result)

        Returns:
            List of EmailResult
        """
        results = []
        total = len(emails)

        for i, email in enumerate(emails):
            # Rate limiting
            if i > 0:
                await asyncio.sleep(self.delay_between)

            # Check hourly limit
            if len(results) >= self.rate_limit:
                logger.warning(f"Rate limit reached ({self.rate_limit}/hour)")
                break

            result = await self.send_email(email, browser, provider)
            results.append(result)

            if on_progress:
                on_progress(i + 1, total, result)

        return results

    def generate_sequence(
        self,
        lead: Lead,
        steps: int = 3,
        delays: List[int] = None
    ) -> List[Dict]:
        """
        Generate email sequence for a lead.

        Args:
            lead: Lead object
            steps: Number of emails in sequence
            delays: Days between each email

        Returns:
            List of scheduled emails
        """
        delays = delays or [0, 3, 7]
        templates = ["cold_intro", "follow_up_1", "follow_up_2"]

        sequence = []
        base_date = datetime.now()

        for i in range(min(steps, len(templates))):
            delay = delays[i] if i < len(delays) else delays[-1]
            send_date = base_date + timedelta(days=delay)

            email = self.compose_email(lead, templates[i])

            sequence.append({
                "step": i + 1,
                "to": lead.email,
                "subject": email["subject"],
                "body": email["body"],
                "template": templates[i],
                "scheduled_for": send_date.isoformat(),
                "status": "pending"
            })

        return sequence

    def export_for_review(
        self,
        emails: List[Dict],
        filepath: Optional[str] = None
    ) -> str:
        """
        Export composed emails for human review before sending.

        Returns path to exported file.
        """
        if not filepath:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filepath = f"output/emails_for_review_{timestamp}.csv"

        Path(filepath).parent.mkdir(parents=True, exist_ok=True)

        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=[
                "to", "subject", "body", "template", "status"
            ])
            writer.writeheader()

            for email in emails:
                writer.writerow({
                    "to": email.get("to", ""),
                    "subject": email.get("subject", ""),
                    "body": email.get("body", "").replace("\n", "\\n"),
                    "template": email.get("template", ""),
                    "status": "pending"
                })

        logger.info(f"Exported {len(emails)} emails to {filepath}")
        return filepath

    def get_stats(self) -> Dict[str, Any]:
        """Get outreach statistics."""
        return {
            "total_sent": len(self.sent_emails),
            "templates_available": list(self.templates.keys()),
            "rate_limit": self.rate_limit,
            "delay_between": self.delay_between
        }


# Convenience functions
def compose_cold_emails(leads: List[Dict], template: str = "cold_intro") -> List[Dict]:
    """Quick batch compose."""
    outreach = EmailOutreach()
    normalized = outreach.normalize_leads(leads)
    return outreach.compose_batch(normalized, template)


def preview_email(lead_data: Dict, template: str = "cold_intro") -> Dict[str, str]:
    """Preview a single email."""
    outreach = EmailOutreach()
    normalized = outreach.normalize_leads([lead_data])
    if normalized:
        return outreach.compose_email(normalized[0], template)
    return {"subject": "", "body": ""}
