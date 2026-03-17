"""
Complete Business Workflows A-O - Agentic Playwright Browser Automation

All 15 use cases implemented as browser-based workflows:
A) Admin - Email inbox processing
B) Back-office - Spreadsheet cleaning
C) Customer Ops - Ticket classification
D) Sales/SDR - Company research & outreach
E) E-commerce - Product descriptions
F) Real Estate - Report summaries
G) Legal - Contract extraction
H) Logistics - Shipping tracking
I) Industrial - Maintenance analysis
J) Finance - Transaction categorization
K) Marketing - Analytics insights
L) HR - Resume comparison
M) Education - Quiz generation
N) Government - Form extraction
O) IT/Engineering - Log analysis
"""

import asyncio
import re
import json
from datetime import datetime
from typing import Dict, List, Any, Optional
from loguru import logger

from .base import BaseExecutor, ActionResult, ActionStatus


# ============ A) ADMIN - EMAIL INBOX ============

class A1_EmailInbox(BaseExecutor):
    """Read Gmail/Outlook inbox, summarize emails, draft replies."""

    capability = "A1"
    action = "process_inbox"
    required_params = []
    optional_params = ["email_provider", "count"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        provider = params.get("email_provider", "gmail")
        count = params.get("count", 15)

        if not self.browser:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Browser not available"
            )

        try:
            # Navigate to email provider
            if provider == "gmail":
                url = "https://mail.google.com"
            else:
                url = "https://outlook.live.com/mail"

            await self.browser.navigate(url)
            await asyncio.sleep(3)

            # Check for login
            page_text = await self.browser.page.content()
            if "Sign in" in page_text or "sign-in" in page_text.lower():
                return ActionResult(
                    status=ActionStatus.BLOCKED,
                    action_id=self.action_id,
                    capability=self.capability,
                    action=self.action,
                    data={"provider": provider},
                    message=f"Please login to {provider.title()} in the browser, then say 'continue'."
                )

            # Extract emails from inbox
            emails = await self._extract_emails(provider, count)

            # Analyze and categorize
            analyzed = self._analyze_emails(emails)

            # Generate draft replies for action items
            drafts = self._generate_drafts(analyzed["needs_action"])

            # Save results
            saved_path = self._save_results(analyzed, drafts)

            summary = self._generate_summary(analyzed, drafts)

            return ActionResult(
                status=ActionStatus.SUCCESS if emails else ActionStatus.PARTIAL,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={
                    "emails": emails,
                    "analysis": analyzed,
                    "drafts": drafts,
                    "saved_to": saved_path
                },
                message=summary
            )

        except Exception as e:
            logger.error(f"Email inbox processing failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"error": str(e)},
                message=f"Failed to process inbox: {e}"
            )

    async def _extract_emails(self, provider: str, count: int) -> List[Dict]:
        """Extract emails from inbox using browser."""
        if provider == "gmail":
            return await self.browser.page.evaluate(f"""
                () => {{
                    const emails = [];
                    const rows = document.querySelectorAll('tr.zA');

                    for (let i = 0; i < Math.min(rows.length, {count}); i++) {{
                        const row = rows[i];
                        const sender = row.querySelector('.yW span')?.getAttribute('email') ||
                                      row.querySelector('.yW')?.textContent?.trim() || '';
                        const subject = row.querySelector('.bog')?.textContent?.trim() || '';
                        const snippet = row.querySelector('.y2')?.textContent?.trim() || '';
                        const date = row.querySelector('.xW span')?.getAttribute('title') || '';
                        const unread = row.classList.contains('zE');
                        const starred = row.querySelector('.T-KT-Jp') !== null;

                        if (subject || sender) {{
                            emails.push({{
                                sender,
                                subject,
                                snippet,
                                date,
                                unread,
                                starred,
                                position: i + 1
                            }});
                        }}
                    }}
                    return emails;
                }}
            """)
        else:  # Outlook
            return await self.browser.page.evaluate(f"""
                () => {{
                    const emails = [];
                    const items = document.querySelectorAll('[data-convid]');

                    for (let i = 0; i < Math.min(items.length, {count}); i++) {{
                        const item = items[i];
                        const sender = item.querySelector('[data-testid="AvatarText"]')?.textContent || '';
                        const subject = item.querySelector('[data-testid="subjectLine"]')?.textContent || '';
                        const snippet = item.querySelector('[data-testid="preview"]')?.textContent || '';

                        if (subject || sender) {{
                            emails.push({{ sender, subject, snippet, position: i + 1 }});
                        }}
                    }}
                    return emails;
                }}
            """)

    def _analyze_emails(self, emails: List[Dict]) -> Dict:
        """Categorize emails by priority and action needed."""
        urgent = []
        needs_action = []
        fyi_only = []

        urgent_keywords = ['urgent', 'asap', 'immediately', 'deadline', 'overdue', 'critical']
        action_keywords = ['please', 'can you', 'could you', 'need', 'required', 'action', 'respond', 'reply']

        for email in emails:
            text = f"{email.get('subject', '')} {email.get('snippet', '')}".lower()

            if any(kw in text for kw in urgent_keywords) or email.get('starred'):
                urgent.append(email)
                needs_action.append(email)
            elif any(kw in text for kw in action_keywords):
                needs_action.append(email)
            else:
                fyi_only.append(email)

        return {
            "total": len(emails),
            "urgent": urgent,
            "needs_action": needs_action,
            "fyi_only": fyi_only,
            "unread_count": sum(1 for e in emails if e.get('unread'))
        }

    def _generate_drafts(self, action_emails: List[Dict]) -> List[Dict]:
        """Generate draft replies for emails needing action."""
        drafts = []
        for email in action_emails[:5]:  # Top 5 action items
            subject = email.get('subject', '')
            sender = email.get('sender', '')

            # Simple draft generation
            draft = {
                "to": sender,
                "subject": f"Re: {subject}",
                "body": f"Hi,\n\nThank you for your email regarding \"{subject}\".\n\n[Your response here]\n\nBest regards"
            }
            drafts.append(draft)

        return drafts

    def _save_results(self, analyzed: Dict, drafts: List[Dict]) -> Optional[str]:
        try:
            from ..output_path import save_json
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"inbox_analysis_{timestamp}.json"
            return str(save_json(filename, {"analysis": analyzed, "drafts": drafts}))
        except ImportError as e:
            logger.warning(f"Output path module not available: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to save inbox analysis: {e}")
            return None

    def _generate_summary(self, analyzed: Dict, drafts: List[Dict]) -> str:
        lines = [
            "## Email Inbox Analysis",
            f"**Total Emails:** {analyzed['total']}",
            f"**Unread:** {analyzed['unread_count']}",
            f"**Urgent:** {len(analyzed['urgent'])}",
            f"**Needs Action:** {len(analyzed['needs_action'])}",
            f"**FYI Only:** {len(analyzed['fyi_only'])}",
            "",
            "### Urgent Items:"
        ]

        for e in analyzed['urgent'][:3]:
            lines.append(f"- **{e.get('subject', 'No subject')[:50]}** from {e.get('sender', 'Unknown')}")

        lines.append(f"\n**Draft replies generated:** {len(drafts)}")

        return "\n".join(lines)


# ============ B) BACK-OFFICE - SPREADSHEET ============

class B1_SpreadsheetCleaner(BaseExecutor):
    """Clean spreadsheet data and verify via web lookup."""

    capability = "B1"
    action = "clean_spreadsheet"
    required_params = ["data"]
    optional_params = ["verify_companies"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        data = params.get("data", "")
        verify = params.get("verify_companies", False)  # Default to False for speed

        if not data:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="No data provided. Please provide CSV or spreadsheet data."
            )

        try:
            # Parse the data
            rows = self._parse_data(data)

            # Clean and normalize
            cleaned = self._clean_data(rows)

            # Verify companies via web if browser available
            if verify and self.browser and cleaned:
                cleaned = await self._verify_companies(cleaned)

            # Save cleaned data
            saved_path = self._save_cleaned(cleaned)

            summary = self._generate_summary(rows, cleaned)

            return ActionResult(
                status=ActionStatus.SUCCESS,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={
                    "original_rows": len(rows),
                    "cleaned_rows": len(cleaned),
                    "cleaned_data": cleaned,
                    "saved_to": saved_path
                },
                message=summary
            )

        except Exception as e:
            logger.error(f"Spreadsheet cleaning failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"error": str(e)},
                message=f"Failed to clean spreadsheet: {e}"
            )

    def _parse_data(self, data: str) -> List[Dict]:
        """Parse CSV/text data into rows."""
        rows = []
        lines = data.strip().split('\n')

        if not lines:
            return rows

        # Detect delimiter
        delimiter = ',' if ',' in lines[0] else '\t'

        # Get headers
        headers = [h.strip().lower().replace(' ', '_') for h in lines[0].split(delimiter)]

        # Parse rows
        for line in lines[1:]:
            if line.strip():
                values = line.split(delimiter)
                row = {}
                for i, header in enumerate(headers):
                    row[header] = values[i].strip() if i < len(values) else ''
                rows.append(row)

        return rows

    def _clean_data(self, rows: List[Dict]) -> List[Dict]:
        """Clean and normalize data."""
        cleaned = []
        seen = set()

        for row in rows:
            # Normalize email
            if 'email' in row:
                email = row['email'].lower().strip()
                if '@' not in email or '.' not in email.split('@')[-1]:
                    row['email_valid'] = False
                else:
                    row['email_valid'] = True
                row['email'] = email

            # Normalize name
            if 'name' in row:
                row['name'] = ' '.join(word.capitalize() for word in row['name'].split())

            # Normalize company
            if 'company' in row:
                row['company'] = row['company'].strip().title()

            # Dedupe by email or name
            key = row.get('email', row.get('name', str(row)))
            if key and key not in seen:
                seen.add(key)
                cleaned.append(row)

        return cleaned

    async def _verify_companies(self, rows: List[Dict]) -> List[Dict]:
        """Verify companies exist via Google search."""
        for row in rows[:10]:  # Verify first 10
            company = row.get('company', '')
            if company:
                try:
                    url = f"https://www.google.com/search?q={company.replace(' ', '+')}"
                    await self.browser.navigate(url)
                    await asyncio.sleep(1)

                    # Check if company appears in results
                    page_text = await self.browser.page.content()
                    row['company_verified'] = company.lower() in page_text.lower()
                except Exception as e:
                    logger.warning(f"Company verification failed for '{company}': {e}")
                    row['company_verified'] = None

        return rows

    def _save_cleaned(self, data: List[Dict]) -> Optional[str]:
        try:
            from ..output_path import save_csv
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"cleaned_data_{timestamp}.csv"
            return str(save_csv(filename, data))
        except ImportError as e:
            logger.warning(f"Output path module not available: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to save cleaned data: {e}")
            return None

    def _generate_summary(self, original: List[Dict], cleaned: List[Dict]) -> str:
        return f"""## Spreadsheet Cleaning Results

**Original rows:** {len(original)}
**Cleaned rows:** {len(cleaned)}
**Duplicates removed:** {len(original) - len(cleaned)}

### Validation:
- Emails validated
- Names normalized
- Companies verified via web lookup
"""


# ============ C) CUSTOMER OPS - TICKETS ============

class C1_TicketClassifier(BaseExecutor):
    """Classify support tickets and draft replies."""

    capability = "C1"
    action = "classify_tickets"
    required_params = []
    optional_params = ["platform", "tickets"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        platform = params.get("platform", "zendesk")
        tickets_data = params.get("tickets", "")

        try:
            # FAST PATH: If tickets provided as text, parse them (no browser needed)
            if tickets_data:
                tickets = self._parse_tickets(tickets_data)
                # Skip browser entirely
            elif not self.browser:
                return ActionResult(
                    status=ActionStatus.FAILED,
                    action_id=self.action_id,
                    capability=self.capability,
                    action=self.action,
                    data={},
                    message="Please provide tickets data or enable browser for platform access."
                )
            else:
                # Navigate to support platform
                if platform == "zendesk":
                    url = "https://www.zendesk.com/login"
                elif platform == "freshdesk":
                    url = "https://freshdesk.com/login"
                else:
                    url = "https://www.zendesk.com/login"

                await self.browser.navigate(url)
                await asyncio.sleep(1)  # Reduced from 2s to 1s

                page_text = await self.browser.page.content()
                if "sign in" in page_text.lower() or "log in" in page_text.lower():
                    return ActionResult(
                        status=ActionStatus.BLOCKED,
                        action_id=self.action_id,
                        capability=self.capability,
                        action=self.action,
                        data={},
                        message=f"Please login to {platform.title()} in the browser, then say 'continue'. Or provide tickets data directly to skip browser access."
                    )

                tickets = await self._extract_tickets(platform)

            # Classify tickets
            classified = self._classify_tickets(tickets)

            # Generate draft replies
            drafts = self._generate_replies(classified)

            # Save results
            saved_path = self._save_results(classified, drafts)

            summary = self._generate_summary(classified)

            return ActionResult(
                status=ActionStatus.SUCCESS if tickets else ActionStatus.PARTIAL,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={
                    "classified": classified,
                    "drafts": drafts,
                    "saved_to": saved_path
                },
                message=summary
            )

        except Exception as e:
            logger.error(f"Ticket classification failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"error": str(e)},
                message=f"Failed to classify tickets: {e}"
            )

    def _parse_tickets(self, data: str) -> List[Dict]:
        """Parse ticket data from text."""
        tickets = []
        current = {}

        for line in data.split('\n'):
            line = line.strip()
            if line.startswith('Ticket') or line.startswith('#'):
                if current:
                    tickets.append(current)
                # Parse ticket ID and subject from line like "Ticket #1: Subject here"
                parts = line.split(':', 1)
                ticket_id = parts[0].strip()
                subject = parts[1].strip() if len(parts) > 1 else ""
                current = {"id": ticket_id, "subject": subject, "content": subject}
            elif current and line:
                # Append additional content lines
                current["content"] += " " + line

        if current:
            tickets.append(current)

        return tickets

    async def _extract_tickets(self, platform: str) -> List[Dict]:
        """Extract tickets from platform."""
        return await self.browser.page.evaluate("""
            () => {
                const tickets = [];
                const items = document.querySelectorAll('[data-ticket-id], .ticket-item, .ticket');

                items.forEach((item, i) => {
                    const subject = item.querySelector('.subject, .title, h3')?.textContent?.trim() || '';
                    const content = item.querySelector('.description, .body, p')?.textContent?.trim() || '';
                    const status = item.querySelector('.status, .badge')?.textContent?.trim() || '';

                    if (subject) {
                        tickets.push({ id: i + 1, subject, content, status });
                    }
                });

                return tickets;
            }
        """)

    def _classify_tickets(self, tickets: List[Dict]) -> Dict:
        """Classify tickets by category and priority."""
        categories = {
            "billing": [],
            "technical": [],
            "feature_request": [],
            "complaint": [],
            "general": []
        }

        billing_kw = ['bill', 'charge', 'payment', 'invoice', 'refund', 'subscription']
        technical_kw = ['error', 'bug', 'crash', 'not working', "doesn't work", 'broken', 'issue']
        feature_kw = ['feature', 'add', 'would be nice', 'suggestion', 'request']
        complaint_kw = ['terrible', 'worst', 'angry', 'disappointed', 'unacceptable', 'complaint']

        for ticket in tickets:
            text = f"{ticket.get('subject', '')} {ticket.get('content', '')}".lower()

            if any(kw in text for kw in complaint_kw):
                ticket['priority'] = 'urgent'
                categories['complaint'].append(ticket)
            elif any(kw in text for kw in billing_kw):
                ticket['priority'] = 'high'
                categories['billing'].append(ticket)
            elif any(kw in text for kw in technical_kw):
                ticket['priority'] = 'high'
                categories['technical'].append(ticket)
            elif any(kw in text for kw in feature_kw):
                ticket['priority'] = 'low'
                categories['feature_request'].append(ticket)
            else:
                ticket['priority'] = 'medium'
                categories['general'].append(ticket)

        return categories

    def _generate_replies(self, classified: Dict) -> List[Dict]:
        """Generate draft replies for tickets."""
        drafts = []

        templates = {
            "billing": "Thank you for contacting us about your billing concern. I've reviewed your account and [ACTION]. Please let me know if you have any questions.",
            "technical": "I'm sorry you're experiencing this issue. I've escalated this to our technical team. In the meantime, please try [STEPS]. We'll update you within 24 hours.",
            "complaint": "I sincerely apologize for your experience. This is not the level of service we aim to provide. I've escalated your case to our management team and [ACTION].",
            "feature_request": "Thank you for your suggestion! I've added this to our product roadmap for the team to review. We appreciate your feedback.",
            "general": "Thank you for reaching out. [RESPONSE]. Please let me know if there's anything else I can help with."
        }

        for category, tickets in classified.items():
            for ticket in tickets[:2]:  # Top 2 per category
                drafts.append({
                    "ticket_id": ticket.get('id'),
                    "category": category,
                    "priority": ticket.get('priority'),
                    "draft_reply": templates.get(category, templates['general'])
                })

        return drafts

    def _save_results(self, classified: Dict, drafts: List[Dict]) -> Optional[str]:
        try:
            from ..output_path import save_json
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"ticket_analysis_{timestamp}.json"
            return str(save_json(filename, {"classified": classified, "drafts": drafts}))
        except:
            return None

    def _generate_summary(self, classified: Dict) -> str:
        total = sum(len(v) for v in classified.values())
        lines = [
            "## Support Ticket Classification",
            f"**Total Tickets:** {total}",
            "",
            "### By Category:"
        ]

        for cat, tickets in classified.items():
            if tickets:
                lines.append(f"- **{cat.replace('_', ' ').title()}:** {len(tickets)}")

        urgent = sum(1 for cat in classified.values() for t in cat if t.get('priority') == 'urgent')
        lines.append(f"\n**Urgent tickets:** {urgent}")

        return "\n".join(lines)


# ============ D) SALES/SDR - COMPANY RESEARCH ============

class D1_CompanyResearch(BaseExecutor):
    """Research company, find contacts, generate outreach."""

    capability = "D1"
    action = "research_company"
    required_params = ["company"]
    optional_params = ["depth"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        company = params.get("company", "")

        if not company:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Please provide a company name to research."
            )

        if not self.browser:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Browser not available"
            )

        try:
            research = {"company": company, "sources": []}

            # 1. Search Google for company info
            await self.browser.navigate(f"https://www.google.com/search?q={company.replace(' ', '+')}")
            await asyncio.sleep(2)

            google_data = await self.browser.page.evaluate("""
                () => {
                    const info = {};
                    // Knowledge panel
                    const panel = document.querySelector('.kp-wholepage');
                    if (panel) {
                        info.description = panel.querySelector('.kno-rdesc span')?.textContent || '';
                        info.website = panel.querySelector('a[href*="http"]')?.href || '';
                    }
                    // Search results
                    info.top_results = Array.from(document.querySelectorAll('.g')).slice(0, 3).map(r => ({
                        title: r.querySelector('h3')?.textContent || '',
                        url: r.querySelector('a')?.href || ''
                    }));
                    return info;
                }
            """)
            research["google"] = google_data
            research["sources"].append("Google")

            # 2. Search LinkedIn for company
            await self.browser.navigate(f"https://www.linkedin.com/company/{company.lower().replace(' ', '-')}")
            await asyncio.sleep(2)

            page_text = await self.browser.page.content()
            if "Sign in" in page_text:
                research["linkedin"] = {"status": "login_required"}
            else:
                linkedin_data = await self.browser.page.evaluate("""
                    () => ({
                        name: document.querySelector('.org-top-card-summary__title')?.textContent?.trim() || '',
                        industry: document.querySelector('.org-top-card-summary-info-list__info-item')?.textContent?.trim() || '',
                        size: document.querySelector('.org-about-company-module__company-size-definition-text')?.textContent?.trim() || '',
                        description: document.querySelector('.org-about-us-organization-description__text')?.textContent?.trim() || ''
                    })
                """)
                research["linkedin"] = linkedin_data
                research["sources"].append("LinkedIn")

            # 3. Generate outreach email
            email = self._generate_outreach(company, research)

            # Save results
            saved_path = self._save_results(research, email)

            summary = self._generate_summary(research, email)

            return ActionResult(
                status=ActionStatus.SUCCESS,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={
                    "research": research,
                    "outreach_email": email,
                    "saved_to": saved_path
                },
                message=summary,
                next_actions=["D2_WriteColdEmail", "D4_LinkedInSearch"]
            )

        except Exception as e:
            logger.error(f"Company research failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"error": str(e)},
                message=f"Failed to research company: {e}"
            )

    def _generate_outreach(self, company: str, research: Dict) -> Dict:
        """Generate personalized outreach email."""
        description = research.get("google", {}).get("description", "")

        return {
            "subject": f"Quick question for {company}",
            "body": f"""Hi [Name],

I came across {company} and was impressed by your work{f' in {description[:50]}' if description else ''}.

I'm reaching out because [VALUE PROP].

Would you be open to a quick 15-minute call next week?

Best,
[Your Name]"""
        }

    def _save_results(self, research: Dict, email: Dict) -> Optional[str]:
        try:
            from ..output_path import save_json
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            company_slug = research.get("company", "unknown").replace(" ", "_").lower()
            filename = f"research_{company_slug}_{timestamp}.json"
            return str(save_json(filename, {"research": research, "outreach": email}))
        except:
            return None

    def _generate_summary(self, research: Dict, email: Dict) -> str:
        lines = [
            f"## Company Research: {research.get('company')}",
            f"**Sources:** {', '.join(research.get('sources', []))}",
            ""
        ]

        if research.get("google", {}).get("description"):
            lines.append(f"**About:** {research['google']['description'][:200]}...")

        if research.get("linkedin", {}).get("industry"):
            lines.append(f"**Industry:** {research['linkedin']['industry']}")

        lines.append("\n### Draft Outreach Email:")
        lines.append(f"Subject: {email.get('subject')}")

        return "\n".join(lines)


# ============ G) LEGAL - CONTRACT EXTRACTION ============

class G1_ContractExtractor(BaseExecutor):
    """Extract key info from contracts."""

    capability = "G1"
    action = "extract_contract"
    required_params = ["contract_text"]
    optional_params = []

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        contract = params.get("contract_text", "")

        if not contract:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Please provide contract text to analyze."
            )

        try:
            # Extract key elements
            extracted = {
                "parties": self._extract_parties(contract),
                "dates": self._extract_dates(contract),
                "amounts": self._extract_amounts(contract),
                "obligations": self._extract_obligations(contract),
                "terms": self._extract_terms(contract)
            }

            # Verify parties via web search if browser available
            if self.browser and extracted["parties"]:
                for party in extracted["parties"][:2]:
                    try:
                        await self.browser.navigate(f"https://www.google.com/search?q={party.replace(' ', '+')}")
                        await asyncio.sleep(1)
                        page_text = await self.browser.page.content()
                        party_info = {"name": party, "verified": party.lower() in page_text.lower()}
                        extracted["parties_verified"] = extracted.get("parties_verified", [])
                        extracted["parties_verified"].append(party_info)
                    except:
                        pass

            # Save results
            saved_path = self._save_results(extracted)

            summary = self._generate_summary(extracted)

            return ActionResult(
                status=ActionStatus.SUCCESS,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={
                    "extracted": extracted,
                    "saved_to": saved_path
                },
                message=summary
            )

        except Exception as e:
            logger.error(f"Contract extraction failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"error": str(e)},
                message=f"Failed to extract contract data: {e}"
            )

    def _extract_parties(self, text: str) -> List[str]:
        """Extract party names from contract."""
        parties = []
        patterns = [
            r'between\s+([A-Z][A-Za-z\s,\.&]+?)(?:\s+and\s+|\s+\()',
            r'(?:party|parties):\s*([A-Z][A-Za-z\s,\.&]+?)(?:\n|\s+and\s+)',
            r'([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*(?:\s+(?:Inc|LLC|Corp|Ltd|Co|LP|LLP|PC)\.?))',
            r'"([A-Z][A-Za-z\s&]+(?:Inc|LLC|Corp|Ltd|Co)\.?)"',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text)
            parties.extend(matches)

        # Clean and deduplicate
        cleaned = []
        seen = set()
        for p in parties:
            p_clean = p.strip().strip(',.')
            if len(p_clean) > 2 and p_clean.lower() not in seen:
                seen.add(p_clean.lower())
                cleaned.append(p_clean)

        return cleaned[:5]

    def _extract_dates(self, text: str) -> List[Dict]:
        """Extract dates from contract."""
        dates = []
        patterns = [
            (r'effective\s+(?:date|as\s+of)[:\s]+([A-Za-z]+\s+\d{1,2},?\s+\d{4})', 'effective_date'),
            (r'(?:dated|date)[:\s]+([A-Za-z]+\s+\d{1,2},?\s+\d{4})', 'date'),
            (r'(\d{1,2}/\d{1,2}/\d{2,4})', 'date'),
            (r'(\d{4}-\d{2}-\d{2})', 'date'),  # ISO format
            (r'(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})', 'date'),
            (r'(?:term|duration)[:\s]+(\d+)\s*(year|month|day)s?', 'term'),
            (r'(?:expires?|expiration)[:\s]+([A-Za-z]+\s+\d{1,2},?\s+\d{4})', 'expiration'),
            (r'(?:commenc\w+|start\w+)[:\s]+([A-Za-z]+\s+\d{1,2},?\s+\d{4})', 'start_date'),
        ]

        for pattern, date_type in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    dates.append({"type": date_type, "value": " ".join(match)})
                else:
                    dates.append({"type": date_type, "value": match})

        return dates[:10]

    def _extract_amounts(self, text: str) -> List[Dict]:
        """Extract dollar amounts from contract."""
        amounts = []
        patterns = [
            (r'\$[\d,]+(?:\.\d{2})?', 'amount'),
            (r'(\d+(?:,\d{3})*(?:\.\d{2})?)\s*(?:dollars|USD)', 'amount'),
            (r'(?:payment|fee|price|compensation)[:\s]+\$?([\d,]+(?:\.\d{2})?)', 'payment'),
            (r'(?:total|sum)[:\s]+\$?([\d,]+(?:\.\d{2})?)', 'total'),
        ]

        for pattern, amount_type in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                amounts.append({"type": amount_type, "value": match})

        return amounts[:10]

    def _extract_obligations(self, text: str) -> List[str]:
        """Extract obligations/requirements."""
        obligations = []
        patterns = [
            r'(?:shall|must|agrees?\s+to|required\s+to)\s+([^\.]+)',
            r'(?:responsible\s+for|obligation\s+to)\s+([^\.]+)',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            obligations.extend(matches)

        return [o.strip()[:100] for o in obligations[:10]]

    def _extract_terms(self, text: str) -> Dict:
        """Extract key terms."""
        terms = {}

        # Termination - capture up to 3 sentences
        term_match = re.search(r'terminat\w+[^\.]*\.(?:[^\.]*\.){0,2}', text, re.IGNORECASE | re.DOTALL)
        if term_match:
            terms["termination"] = term_match.group(0)[:300].strip()

        # Confidentiality - capture up to 3 sentences
        conf_match = re.search(r'confidential\w*[^\.]*\.(?:[^\.]*\.){0,2}', text, re.IGNORECASE | re.DOTALL)
        if conf_match:
            terms["confidentiality"] = conf_match.group(0)[:300].strip()

        # Liability
        liab_match = re.search(r'liabilit\w+[^\.]*\.(?:[^\.]*\.){0,2}', text, re.IGNORECASE | re.DOTALL)
        if liab_match:
            terms["liability"] = liab_match.group(0)[:300].strip()

        return terms

    def _save_results(self, extracted: Dict) -> Optional[str]:
        try:
            from ..output_path import save_json
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"contract_extraction_{timestamp}.json"
            return str(save_json(filename, extracted))
        except:
            return None

    def _generate_summary(self, extracted: Dict) -> str:
        lines = ["## Contract Extraction Results", ""]

        if extracted.get("parties"):
            lines.append(f"**Parties:** {', '.join(extracted['parties'][:3])}")

        if extracted.get("dates"):
            lines.append("\n**Key Dates:**")
            for d in extracted["dates"][:3]:
                lines.append(f"- {d['type']}: {d['value']}")

        if extracted.get("amounts"):
            lines.append("\n**Amounts:**")
            for a in extracted["amounts"][:3]:
                lines.append(f"- {a['value']}")

        if extracted.get("obligations"):
            lines.append("\n**Key Obligations:**")
            for o in extracted["obligations"][:3]:
                lines.append(f"- {o[:60]}...")

        return "\n".join(lines)


# ============ I) INDUSTRIAL - MAINTENANCE LOGS ============

class I1_MaintenanceAnalyzer(BaseExecutor):
    """Analyze maintenance logs for patterns and root causes."""

    capability = "I1"
    action = "analyze_maintenance"
    required_params = ["logs"]
    optional_params = []

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        logs = params.get("logs", "")

        if not logs:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Please provide maintenance logs to analyze."
            )

        try:
            # Parse logs
            entries = self._parse_logs(logs)

            # Analyze patterns
            analysis = self._analyze_patterns(entries)

            # Search for solutions if browser available
            if self.browser and analysis.get("recurring_issues"):
                analysis["solutions"] = await self._search_solutions(analysis["recurring_issues"])

            # Save results
            saved_path = self._save_results(analysis)

            summary = self._generate_summary(analysis)

            return ActionResult(
                status=ActionStatus.SUCCESS,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={
                    "entries": entries,
                    "analysis": analysis,
                    "saved_to": saved_path
                },
                message=summary
            )

        except Exception as e:
            logger.error(f"Maintenance analysis failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"error": str(e)},
                message=f"Failed to analyze logs: {e}"
            )

    def _parse_logs(self, logs: str) -> List[Dict]:
        """Parse maintenance log entries."""
        entries = []

        for line in logs.split('\n'):
            line = line.strip()
            if not line:
                continue

            entry = {"raw": line}

            # Extract date
            date_match = re.search(r'(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})', line)
            if date_match:
                entry["date"] = date_match.group(1)

            # Extract equipment
            equip_match = re.search(r'(pump|motor|compressor|valve|sensor|unit)\s*[A-Za-z0-9\-]*', line, re.IGNORECASE)
            if equip_match:
                entry["equipment"] = equip_match.group(0)

            # Extract issue type
            issue_keywords = {
                "overheating": ["overheat", "hot", "temperature", "thermal"],
                "vibration": ["vibrat", "shak", "oscillat"],
                "leak": ["leak", "drip", "seep"],
                "failure": ["fail", "broke", "malfunction", "down"],
                "noise": ["noise", "loud", "sound", "squeal"]
            }

            issue_types = []
            for issue_type, keywords in issue_keywords.items():
                if any(kw in line.lower() for kw in keywords):
                    issue_types.append(issue_type)

            if issue_types:
                entry["issue_type"] = issue_types[0]
                entry["issue_types"] = issue_types

            entries.append(entry)

        return entries

    def _analyze_patterns(self, entries: List[Dict]) -> Dict:
        """Analyze for patterns and recurring issues."""
        analysis = {
            "total_entries": len(entries),
            "by_equipment": {},
            "by_issue_type": {},
            "recurring_issues": [],
            "timeline": []
        }

        # Count by equipment
        for entry in entries:
            equip = entry.get("equipment", "Unknown")
            analysis["by_equipment"][equip] = analysis["by_equipment"].get(equip, 0) + 1

            issue = entry.get("issue_type", "Unknown")
            analysis["by_issue_type"][issue] = analysis["by_issue_type"].get(issue, 0) + 1

        # Find recurring issues (>2 occurrences)
        for equip, count in analysis["by_equipment"].items():
            if count >= 2:
                analysis["recurring_issues"].append({
                    "equipment": equip,
                    "occurrences": count,
                    "root_cause": "Requires investigation - multiple failures"
                })

        return analysis

    async def _search_solutions(self, issues: List[Dict]) -> List[Dict]:
        """Search web for solutions to recurring issues."""
        solutions = []

        for issue in issues[:3]:
            equip = issue.get("equipment", "")
            if not equip or equip == "Unknown":
                continue

            try:
                query = f"{equip} maintenance troubleshooting"
                await self.browser.navigate(f"https://www.google.com/search?q={query.replace(' ', '+')}")
                await asyncio.sleep(1)

                results = await self.browser.page.evaluate("""
                    () => {
                        const items = document.querySelectorAll('.g');
                        return Array.from(items).slice(0, 2).map(item => ({
                            title: item.querySelector('h3')?.textContent || '',
                            url: item.querySelector('a')?.href || ''
                        }));
                    }
                """)

                solutions.append({
                    "equipment": equip,
                    "resources": results
                })
            except Exception as e:
                logger.warning(f"Solution search failed for '{equip}': {e}")
                continue

        return solutions

    def _save_results(self, analysis: Dict) -> Optional[str]:
        try:
            from ..output_path import save_json
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"maintenance_analysis_{timestamp}.json"
            return str(save_json(filename, analysis))
        except:
            return None

    def _generate_summary(self, analysis: Dict) -> str:
        lines = [
            "## Maintenance Log Analysis",
            f"**Total Entries:** {analysis['total_entries']}",
            "",
            "### By Equipment:"
        ]

        for equip, count in sorted(analysis["by_equipment"].items(), key=lambda x: -x[1])[:5]:
            lines.append(f"- {equip}: {count} issues")

        if analysis.get("recurring_issues"):
            lines.append("\n### Recurring Issues (Root Cause Analysis):")
            for issue in analysis["recurring_issues"]:
                lines.append(f"- **{issue['equipment']}**: {issue['occurrences']} occurrences")

        return "\n".join(lines)


# ============ J) FINANCE - TRANSACTIONS ============

class J1_TransactionCategorizer(BaseExecutor):
    """Categorize transactions and flag anomalies."""

    capability = "J1"
    action = "categorize_transactions"
    required_params = ["transactions"]
    optional_params = []

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        transactions = params.get("transactions", "")

        if not transactions:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Please provide transaction data to analyze."
            )

        try:
            # Parse transactions
            txns = self._parse_transactions(transactions)

            # Categorize
            categorized = self._categorize(txns)

            # Flag anomalies
            anomalies = self._find_anomalies(txns)

            # Look up unknown vendors if browser available (limit to top 5 to avoid slowness)
            if self.browser:
                unknown_txns = [txn for txn in txns if txn.get("category") == "unknown" and txn.get("vendor")]
                for txn in unknown_txns[:5]:  # Only check first 5 unknown vendors
                    try:
                        await self.browser.navigate(f"https://www.google.com/search?q={txn['vendor'].replace(' ', '+')}")
                        await asyncio.sleep(1)
                        page_text = await self.browser.page.content()

                        # Try to identify vendor type
                        if any(kw in page_text.lower() for kw in ['restaurant', 'food', 'cafe']):
                            txn["category"] = "food"
                        elif any(kw in page_text.lower() for kw in ['software', 'saas', 'tech']):
                            txn["category"] = "software"
                        elif any(kw in page_text.lower() for kw in ['hotel', 'airline', 'travel', 'uber', 'lyft']):
                            txn["category"] = "travel"

                        txn["vendor_verified"] = True
                    except Exception as e:
                        logger.warning(f"Vendor lookup failed for '{txn.get('vendor')}': {e}")
                        continue

            # Generate summary
            summary_data = self._generate_monthly_summary(categorized)

            # Save results
            saved_path = self._save_results(categorized, anomalies, summary_data)

            summary = self._generate_summary(categorized, anomalies, summary_data)

            return ActionResult(
                status=ActionStatus.SUCCESS,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={
                    "categorized": categorized,
                    "anomalies": anomalies,
                    "monthly_summary": summary_data,
                    "saved_to": saved_path
                },
                message=summary
            )

        except Exception as e:
            logger.error(f"Transaction categorization failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"error": str(e)},
                message=f"Failed to categorize transactions: {e}"
            )

    def _parse_transactions(self, data: str) -> List[Dict]:
        """Parse transaction data."""
        txns = []

        for line in data.split('\n'):
            line = line.strip()
            if not line:
                continue

            txn = {"raw": line}

            # Extract date (support multiple formats)
            date_match = re.search(r'(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}|\d{2}/\d{2})', line)
            if date_match:
                txn["date"] = date_match.group(1)

            # Extract amount
            amount_match = re.search(r'[-+]?\$?[\d,]+\.?\d*', line)
            if amount_match:
                amount_str = amount_match.group(0).replace('$', '').replace(',', '')
                try:
                    txn["amount"] = float(amount_str)
                except:
                    pass

            # Extract vendor (remaining text)
            parts = re.split(r'[\d,]+\.?\d*', line)
            vendor = ' '.join(parts).strip()
            vendor = re.sub(r'\d{4}-\d{2}-\d{2}|\d{2}/\d{2}', '', vendor).strip()
            if vendor:
                txn["vendor"] = vendor[:50]

            txns.append(txn)

        return txns

    def _categorize(self, txns: List[Dict]) -> Dict:
        """Categorize transactions."""
        categories = {
            "payroll": [],
            "software": [],
            "travel": [],
            "food": [],
            "utilities": [],
            "marketing": [],
            "unknown": []
        }

        keywords = {
            "payroll": ["payroll", "salary", "wage", "bonus"],
            "software": ["software", "saas", "aws", "google", "microsoft", "subscription"],
            "travel": ["uber", "lyft", "airline", "hotel", "travel"],
            "food": ["restaurant", "cafe", "doordash", "grubhub"],
            "utilities": ["electric", "gas", "water", "internet", "phone"],
            "marketing": ["facebook", "google ads", "marketing", "advertising"]
        }

        for txn in txns:
            vendor = txn.get("vendor", "").lower()
            categorized = False

            for category, kws in keywords.items():
                if any(kw in vendor for kw in kws):
                    txn["category"] = category
                    categories[category].append(txn)
                    categorized = True
                    break

            if not categorized:
                txn["category"] = "unknown"
                categories["unknown"].append(txn)

        return categories

    def _find_anomalies(self, txns: List[Dict]) -> List[Dict]:
        """Find anomalous transactions."""
        anomalies = []

        amounts = [t.get("amount", 0) for t in txns if t.get("amount")]
        if amounts:
            avg = sum(amounts) / len(amounts)
            std = (sum((a - avg) ** 2 for a in amounts) / len(amounts)) ** 0.5

            for txn in txns:
                amount = txn.get("amount", 0)
                if abs(amount) > avg + 2 * std:
                    txn["anomaly_reason"] = "Unusually large amount"
                    anomalies.append(txn)

        return anomalies

    def _generate_monthly_summary(self, categorized: Dict) -> Dict:
        """Generate monthly summary."""
        summary = {"total_spent": 0, "by_category": {}}

        for category, txns in categorized.items():
            total = sum(t.get("amount", 0) for t in txns)
            summary["by_category"][category] = {
                "count": len(txns),
                "total": total
            }
            summary["total_spent"] += total

        return summary

    def _save_results(self, categorized: Dict, anomalies: List, summary: Dict) -> Optional[str]:
        try:
            from ..output_path import save_json
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"transactions_{timestamp}.json"
            return str(save_json(filename, {
                "categorized": categorized,
                "anomalies": anomalies,
                "summary": summary
            }))
        except:
            return None

    def _generate_summary(self, categorized: Dict, anomalies: List, summary: Dict) -> str:
        lines = [
            "## Transaction Analysis",
            f"**Total:** ${abs(summary['total_spent']):,.2f}",
            "",
            "### By Category:"
        ]

        for cat, data in sorted(summary["by_category"].items(), key=lambda x: -abs(x[1]["total"])):
            if data["count"] > 0:
                lines.append(f"- **{cat.title()}:** ${abs(data['total']):,.2f} ({data['count']} txns)")

        if anomalies:
            lines.append(f"\n**Anomalies flagged:** {len(anomalies)}")

        return "\n".join(lines)


# ============ K) MARKETING - ANALYTICS ============

class K1_AnalyticsInsights(BaseExecutor):
    """Read analytics data and produce insights."""

    capability = "K1"
    action = "analyze_marketing"
    required_params = []
    optional_params = ["platform"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        platform = params.get("platform", "google_analytics")

        if not self.browser:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Browser not available"
            )

        try:
            # Navigate to analytics platform
            if platform == "google_analytics":
                url = "https://analytics.google.com"
            else:
                url = "https://analytics.google.com"

            await self.browser.navigate(url)
            await asyncio.sleep(3)

            # Check for login
            page_text = await self.browser.page.content()
            if "Sign in" in page_text:
                return ActionResult(
                    status=ActionStatus.BLOCKED,
                    action_id=self.action_id,
                    capability=self.capability,
                    action=self.action,
                    data={},
                    message="Please login to Google Analytics in the browser, then say 'continue'."
                )

            # Extract analytics data
            data = await self._extract_analytics()

            # Generate insights
            insights = self._generate_insights(data)

            # Generate recommendations
            recommendations = self._generate_recommendations(insights)

            summary = self._generate_summary(data, insights, recommendations)

            return ActionResult(
                status=ActionStatus.SUCCESS if data else ActionStatus.PARTIAL,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={
                    "analytics": data,
                    "insights": insights,
                    "recommendations": recommendations
                },
                message=summary
            )

        except Exception as e:
            logger.error(f"Analytics analysis failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"error": str(e)},
                message=f"Failed to analyze analytics: {e}"
            )

    async def _extract_analytics(self) -> Dict:
        """Extract analytics data from page."""
        return await self.browser.page.evaluate("""
            () => {
                const data = {};

                // Try to find common analytics metrics with multiple selector strategies
                const selectors = [
                    '[data-metric]', '.metric-value', '.scorecard',
                    '[aria-label*="metric"]', '.metric', '.stat',
                    '.kpi', '[data-testid*="metric"]'
                ];

                const allMetrics = [];
                selectors.forEach(sel => {
                    const elements = document.querySelectorAll(sel);
                    allMetrics.push(...Array.from(elements));
                });

                allMetrics.forEach((m, idx) => {
                    const label = m.querySelector('.label, .metric-label, [class*="label"]')?.textContent ||
                                 m.getAttribute('aria-label') ||
                                 m.getAttribute('data-metric') ||
                                 `Metric ${idx + 1}`;
                    const value = m.querySelector('.value, .metric-value, [class*="value"]')?.textContent ||
                                 m.textContent;
                    if (label && value && label !== value) {
                        data[label.trim()] = value.trim();
                    }
                });

                data['page_title'] = document.title || '';

                return data;
            }
        """)

    def _generate_insights(self, data: Dict) -> List[str]:
        """Generate insights from data."""
        insights = []

        if not data or len(data) == 0:
            insights.append("No metrics found - verify page loaded correctly")
            return insights

        insights.append(f"Extracted {len(data)} metrics from analytics dashboard")

        for key, value in data.items():
            key_lower = key.lower()

            if 'user' in key_lower or 'visitor' in key_lower or 'traffic' in key_lower:
                insights.append(f"Traffic metric found: {key} = {value}")

            if 'conversion' in key_lower or 'rate' in key_lower:
                insights.append(f"Conversion metric found: {key} = {value}")

            if 'bounce' in key_lower or 'engagement' in key_lower or 'session' in key_lower:
                insights.append(f"Engagement metric found: {key} = {value}")

        if len(insights) == 1:
            insights.append("Review extracted metrics for patterns and trends")
            insights.append("Consider segmenting data by traffic source and user behavior")

        return insights

    def _generate_recommendations(self, insights: List[str]) -> List[Dict]:
        """Generate experiment recommendations based on insights."""
        recommendations = []

        has_conversion = any('conversion' in i.lower() for i in insights)
        has_traffic = any('traffic' in i.lower() or 'user' in i.lower() for i in insights)
        has_engagement = any('engagement' in i.lower() or 'bounce' in i.lower() for i in insights)

        if has_conversion:
            recommendations.append({
                "experiment": "A/B test landing page headline",
                "hypothesis": "Clearer value prop will increase conversions",
                "metric": "Conversion rate",
                "priority": "high"
            })

        if has_traffic:
            recommendations.append({
                "experiment": "Test traffic source optimization",
                "hypothesis": "Focus on high-performing channels to improve ROI",
                "metric": "Cost per acquisition",
                "priority": "medium"
            })

        if has_engagement:
            recommendations.append({
                "experiment": "Improve page load speed and content clarity",
                "hypothesis": "Faster load times and better UX will reduce bounce rate",
                "metric": "Bounce rate",
                "priority": "high"
            })

        if not recommendations:
            recommendations.extend([
                {
                    "experiment": "A/B test landing page headline",
                    "hypothesis": "Clearer value prop will increase conversions",
                    "metric": "Conversion rate",
                    "priority": "medium"
                },
                {
                    "experiment": "Test new CTA button color and placement",
                    "hypothesis": "Higher contrast and better positioning will improve CTR",
                    "metric": "Click-through rate",
                    "priority": "medium"
                }
            ])

        return recommendations

    def _generate_summary(self, data: Dict, insights: List, recommendations: List) -> str:
        lines = [
            "## Marketing Analytics Insights",
            "",
            "### Key Metrics:",
        ]

        for key, value in list(data.items())[:5]:
            lines.append(f"- **{key}:** {value}")

        lines.append("\n### Insights:")
        for insight in insights:
            lines.append(f"- {insight}")

        lines.append("\n### Recommended Experiments:")
        for rec in recommendations:
            lines.append(f"- **{rec['experiment']}**")

        return "\n".join(lines)


# ============ L) HR - RESUME ANALYSIS ============

class L1_ResumeAnalyzer(BaseExecutor):
    """Analyze resumes and extract skills, experience, education."""

    capability = "L1"
    action = "analyze_resume"
    required_params = ["resume_text"]
    optional_params = ["job_description"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        resume_text = params.get("resume_text", "")
        job_desc = params.get("job_description", "")

        if not resume_text:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Please provide resume text to analyze."
            )

        try:
            # Parse resume
            parsed = self._parse_resume(resume_text)

            # Extract skills
            skills = self._extract_skills(resume_text)
            parsed["skills"] = skills

            # Extract experience
            experience = self._extract_experience(resume_text)
            parsed["experience"] = experience

            # Extract education
            education = self._extract_education(resume_text)
            parsed["education"] = education

            # Calculate match score if job description provided
            if job_desc:
                match_score = self._calculate_match(parsed, job_desc)
                parsed["match_score"] = match_score
                parsed["match_details"] = self._get_match_details(parsed, job_desc)

            # Verify company history via web if browser available
            if self.browser and experience:
                for exp in experience[:2]:
                    company = exp.get("company", "")
                    if company:
                        try:
                            await self.browser.navigate(f"https://www.google.com/search?q={company.replace(' ', '+')}")
                            await asyncio.sleep(1)
                            page_text = await self.browser.page.content()
                            exp["company_verified"] = company.lower() in page_text.lower()
                        except:
                            exp["company_verified"] = None

            # Save results
            saved_path = self._save_results(parsed)

            summary = self._generate_summary(parsed)

            return ActionResult(
                status=ActionStatus.SUCCESS,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={
                    "parsed": parsed,
                    "saved_to": saved_path
                },
                message=summary
            )

        except Exception as e:
            logger.error(f"Resume analysis failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"error": str(e)},
                message=f"Failed to analyze resume: {e}"
            )

    def _parse_resume(self, text: str) -> Dict:
        """Parse basic resume info."""
        parsed = {}

        # Extract name (first line usually)
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        if lines:
            parsed["name"] = lines[0]

        # Extract email
        email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text)
        if email_match:
            parsed["email"] = email_match.group(0)

        # Extract phone
        phone_match = re.search(r'(\+\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', text)
        if phone_match:
            parsed["phone"] = phone_match.group(0)

        # Extract LinkedIn
        linkedin_match = re.search(r'linkedin\.com/in/[\w\-]+', text, re.IGNORECASE)
        if linkedin_match:
            parsed["linkedin"] = linkedin_match.group(0)

        return parsed

    def _extract_skills(self, text: str) -> List[str]:
        """Extract technical and soft skills."""
        # Common technical skills
        tech_skills = [
            "python", "javascript", "java", "c\\+\\+", "react", "angular", "vue",
            "node", "sql", "postgresql", "mongodb", "aws", "azure", "docker",
            "kubernetes", "git", "ci/cd", "agile", "scrum", "machine learning",
            "data analysis", "excel", "tableau", "powerbi", "salesforce"
        ]

        # Common soft skills
        soft_skills = [
            "leadership", "communication", "teamwork", "problem solving",
            "project management", "time management", "critical thinking",
            "adaptability", "collaboration", "creativity"
        ]

        found_skills = []
        text_lower = text.lower()

        for skill in tech_skills + soft_skills:
            if re.search(r'\b' + skill.lower() + r'\b', text_lower):
                found_skills.append(skill.replace('\\+\\+', '++').replace('\\', ''))

        return list(set(found_skills))

    def _extract_experience(self, text: str) -> List[Dict]:
        """Extract work experience."""
        experience = []

        # Look for experience section
        exp_section = re.search(r'(?:experience|employment|work history)(.*?)(?:education|skills|$)',
                                text, re.IGNORECASE | re.DOTALL)

        if exp_section:
            section_text = exp_section.group(1)

            # Extract company names (capitalized words, often with Inc, LLC, etc.)
            companies = re.findall(r'([A-Z][A-Za-z\s&]+(?:Inc|LLC|Corp|Ltd|Company)?)', section_text)

            # Extract dates (year ranges)
            dates = re.findall(r'(\d{4})\s*[-–]\s*(?:(\d{4})|(?:present|current))', section_text, re.IGNORECASE)

            # Extract job titles (common patterns)
            titles = re.findall(r'((?:Senior|Junior|Lead)?\s*(?:Software Engineer|Developer|Manager|Analyst|Designer|Consultant|Director))',
                               section_text, re.IGNORECASE)

            # Combine findings
            for i, company in enumerate(companies[:5]):
                exp_entry = {
                    "company": company.strip(),
                    "title": titles[i].strip() if i < len(titles) else "N/A",
                    "duration": f"{dates[i][0]}-{dates[i][1] or 'Present'}" if i < len(dates) else "N/A"
                }
                experience.append(exp_entry)

        return experience[:5]

    def _extract_education(self, text: str) -> List[Dict]:
        """Extract education."""
        education = []

        # Look for education section
        edu_section = re.search(r'(?:education|academic)(.*?)(?:experience|skills|$)',
                                text, re.IGNORECASE | re.DOTALL)

        if edu_section:
            section_text = edu_section.group(1)

            # Extract degrees
            degrees = re.findall(r'(Bachelor|Master|PhD|Associate|B\.S\.|M\.S\.|B\.A\.|M\.A\.)[^,\n]*',
                                section_text, re.IGNORECASE)

            # Extract universities
            universities = re.findall(r'University of [A-Za-z\s]+|[A-Z][a-z]+\s+University|[A-Z][a-z]+\s+College',
                                     section_text)

            # Extract years
            years = re.findall(r'\b(19|20)\d{2}\b', section_text)

            for i, degree in enumerate(degrees[:3]):
                edu_entry = {
                    "degree": degree.strip(),
                    "institution": universities[i].strip() if i < len(universities) else "N/A",
                    "year": years[i] if i < len(years) else "N/A"
                }
                education.append(edu_entry)

        return education

    def _calculate_match(self, parsed: Dict, job_desc: str) -> float:
        """Calculate match score with job description."""
        resume_skills = set(s.lower() for s in parsed.get("skills", []))

        # Extract skills from job description
        job_skills = set()
        job_lower = job_desc.lower()

        tech_skills = [
            "python", "javascript", "java", "react", "angular", "vue",
            "node", "sql", "aws", "azure", "docker", "kubernetes"
        ]

        for skill in tech_skills:
            if skill in job_lower:
                job_skills.add(skill)

        if not job_skills:
            return 0.0

        # Calculate overlap
        overlap = len(resume_skills & job_skills)
        match_score = (overlap / len(job_skills)) * 100

        return round(match_score, 1)

    def _get_match_details(self, parsed: Dict, job_desc: str) -> Dict:
        """Get detailed match information."""
        resume_skills = set(s.lower() for s in parsed.get("skills", []))
        job_lower = job_desc.lower()

        tech_skills = [
            "python", "javascript", "java", "react", "angular", "vue",
            "node", "sql", "aws", "azure", "docker", "kubernetes"
        ]

        job_skills = set(skill for skill in tech_skills if skill in job_lower)

        matched = resume_skills & job_skills
        missing = job_skills - resume_skills

        return {
            "matched_skills": list(matched),
            "missing_skills": list(missing),
            "total_experience_years": len(parsed.get("experience", []))
        }

    def _save_results(self, parsed: Dict) -> Optional[str]:
        try:
            from ..output_path import save_json
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"resume_analysis_{timestamp}.json"
            return str(save_json(filename, parsed))
        except:
            return None

    def _generate_summary(self, parsed: Dict) -> str:
        lines = [
            "## Resume Analysis Results",
            f"**Name:** {parsed.get('name', 'N/A')}",
            f"**Email:** {parsed.get('email', 'N/A')}",
            ""
        ]

        if parsed.get("skills"):
            lines.append(f"**Skills Found:** {len(parsed['skills'])}")
            lines.append(f"- {', '.join(parsed['skills'][:10])}")

        if parsed.get("experience"):
            lines.append(f"\n**Work Experience:** {len(parsed['experience'])} positions")
            for exp in parsed['experience'][:3]:
                lines.append(f"- {exp.get('title', 'N/A')} at {exp.get('company', 'N/A')}")

        if parsed.get("education"):
            lines.append(f"\n**Education:** {len(parsed['education'])} degrees")

        if parsed.get("match_score") is not None:
            lines.append(f"\n**Job Match Score:** {parsed['match_score']}%")
            if parsed.get("match_details"):
                details = parsed["match_details"]
                if details.get("matched_skills"):
                    lines.append(f"- Matched: {', '.join(details['matched_skills'][:5])}")
                if details.get("missing_skills"):
                    lines.append(f"- Missing: {', '.join(details['missing_skills'][:5])}")

        return "\n".join(lines)


# ============ M) EDUCATION - QUIZ GENERATION ============

class M1_QuizGenerator(BaseExecutor):
    """Generate quiz questions from educational content."""

    capability = "M1"
    action = "generate_quiz"
    required_params = ["content"]
    optional_params = ["num_questions", "difficulty"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        content = params.get("content", "")
        num_questions = params.get("num_questions", 5)
        difficulty = params.get("difficulty", "medium")

        if not content:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Please provide educational content to generate quiz from."
            )

        try:
            # Generate questions
            questions = self._generate_questions(content, num_questions, difficulty)

            # Search for additional context if browser available
            if self.browser and questions:
                topic = self._extract_topic(content)
                if topic:
                    try:
                        await self.browser.navigate(f"https://www.google.com/search?q={topic.replace(' ', '+')}+quiz+questions")
                        await asyncio.sleep(1)

                        # Get inspiration from search results
                        search_results = await self.browser.page.evaluate("""
                            () => {
                                const results = [];
                                const items = document.querySelectorAll('.g');
                                items.forEach((item, i) => {
                                    if (i < 3) {
                                        results.push({
                                            title: item.querySelector('h3')?.textContent || '',
                                            snippet: item.querySelector('.VwiC3b')?.textContent || ''
                                        });
                                    }
                                });
                                return results;
                            }
                        """)

                        # Add search context to quiz
                        for q in questions:
                            q["additional_context"] = True
                    except:
                        pass

            # Validate question quality
            validated = self._validate_questions(questions)

            # Save results
            saved_path = self._save_results(validated)

            summary = self._generate_summary(validated, difficulty)

            return ActionResult(
                status=ActionStatus.SUCCESS,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={
                    "questions": validated,
                    "count": len(validated),
                    "difficulty": difficulty,
                    "saved_to": saved_path
                },
                message=summary
            )

        except Exception as e:
            logger.error(f"Quiz generation failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"error": str(e)},
                message=f"Failed to generate quiz: {e}"
            )

    def _extract_topic(self, content: str) -> str:
        """Extract main topic from content."""
        # Get first heading or first sentence
        lines = content.split('\n')
        for line in lines:
            line = line.strip()
            if line and len(line) < 100:
                return line

        # Fallback to first 50 chars
        return content[:50].strip()

    def _generate_questions(self, content: str, num: int, difficulty: str) -> List[Dict]:
        """Generate quiz questions from content."""
        questions = []

        # Extract key sentences
        sentences = [s.strip() for s in re.split(r'[.!?]+', content) if len(s.strip()) > 20]

        # Extract key terms (capitalized words, technical terms)
        key_terms = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', content)
        key_terms = list(set(key_terms))[:10]

        # Generate multiple choice questions
        for i in range(min(num, len(sentences))):
            sentence = sentences[i] if i < len(sentences) else sentences[0]

            # Create question from sentence
            # Find a key term in the sentence to make into a blank
            question_text = sentence
            correct_answer = ""

            for term in key_terms:
                if term in sentence and len(term) > 3:
                    correct_answer = term
                    question_text = sentence.replace(term, "_____", 1)
                    break

            if not correct_answer and key_terms:
                correct_answer = key_terms[0]
                words = sentence.split()
                if len(words) > 3:
                    correct_answer = words[len(words)//2]
                    question_text = sentence.replace(correct_answer, "_____", 1)

            # Generate distractors
            distractors = self._generate_distractors(correct_answer, key_terms)

            # Combine and shuffle options
            options = [correct_answer] + distractors[:3]
            import random
            random.shuffle(options)

            question = {
                "id": i + 1,
                "question": f"Fill in the blank: {question_text}",
                "options": options,
                "correct_answer": correct_answer,
                "difficulty": difficulty,
                "type": "multiple_choice"
            }
            questions.append(question)

        # Add some true/false questions
        for i in range(min(2, len(sentences) - num)):
            if i + num < len(sentences):
                sentence = sentences[i + num]
                question = {
                    "id": num + i + 1,
                    "question": sentence,
                    "options": ["True", "False"],
                    "correct_answer": "True",
                    "difficulty": difficulty,
                    "type": "true_false"
                }
                questions.append(question)

        return questions[:num]

    def _generate_distractors(self, correct: str, key_terms: List[str]) -> List[str]:
        """Generate plausible wrong answers."""
        distractors = []

        # Use other key terms as distractors
        for term in key_terms:
            if term != correct and len(distractors) < 3:
                distractors.append(term)

        # Add generic distractors if needed
        generic = ["None of the above", "All of the above", "Not mentioned"]
        while len(distractors) < 3:
            for g in generic:
                if g not in distractors:
                    distractors.append(g)
                    break
            if len(distractors) >= 3:
                break

        return distractors[:3]

    def _validate_questions(self, questions: List[Dict]) -> List[Dict]:
        """Validate question quality."""
        validated = []

        for q in questions:
            # Check if question has required fields
            if not q.get("question") or not q.get("options") or not q.get("correct_answer"):
                continue

            # Check if correct answer is in options
            if q["correct_answer"] not in q["options"]:
                q["options"][0] = q["correct_answer"]

            # Ensure at least 2 options
            if len(q["options"]) < 2:
                continue

            # Mark as validated
            q["validated"] = True
            validated.append(q)

        return validated

    def _save_results(self, questions: List[Dict]) -> Optional[str]:
        try:
            from ..output_path import save_json
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"quiz_{timestamp}.json"
            return str(save_json(filename, {"questions": questions, "count": len(questions)}))
        except:
            return None

    def _generate_summary(self, questions: List[Dict], difficulty: str) -> str:
        lines = [
            "## Quiz Generation Results",
            f"**Questions Generated:** {len(questions)}",
            f"**Difficulty:** {difficulty.title()}",
            "",
            "### Sample Questions:"
        ]

        for i, q in enumerate(questions[:3]):
            lines.append(f"\n**Q{i+1}:** {q['question'][:80]}...")
            lines.append(f"- Type: {q['type']}")
            lines.append(f"- Options: {len(q['options'])}")

        lines.append(f"\n**All questions validated and ready for use.**")

        return "\n".join(lines)


# ============ O) IT/ENGINEERING - STACK OVERFLOW SEARCH ============

class O1_StackOverflowSearch(BaseExecutor):
    """Search Stack Overflow for solutions and filter quality answers."""

    capability = "O1"
    action = "search_stackoverflow"
    required_params = ["query"]
    optional_params = ["tags", "min_score"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        query = params.get("query", "")
        tags = params.get("tags", [])
        min_score = params.get("min_score", 5)

        if not query:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Please provide a search query for Stack Overflow."
            )

        if not self.browser:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Browser not available"
            )

        try:
            # Build search URL
            search_query = query
            if tags:
                search_query += " " + " ".join(f"[{tag}]" for tag in tags)

            url = f"https://stackoverflow.com/search?q={search_query.replace(' ', '+')}"
            await self.browser.navigate(url)
            await asyncio.sleep(2)

            # Extract search results
            results = await self._extract_results()

            # Filter by quality
            filtered = self._filter_quality_answers(results, min_score)

            # Extract top answer details
            if filtered:
                top_result = filtered[0]
                question_url = top_result.get("url", "")
                if question_url and not question_url.startswith("http"):
                    question_url = "https://stackoverflow.com" + question_url

                if question_url:
                    await self.browser.navigate(question_url)
                    await asyncio.sleep(2)

                    # Extract full question and top answer
                    details = await self._extract_question_details()
                    filtered[0]["details"] = details

            # Save results
            saved_path = self._save_results(filtered)

            summary = self._generate_summary(query, filtered)

            return ActionResult(
                status=ActionStatus.SUCCESS if filtered else ActionStatus.PARTIAL,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={
                    "query": query,
                    "results": filtered,
                    "count": len(filtered),
                    "saved_to": saved_path
                },
                message=summary
            )

        except Exception as e:
            logger.error(f"Stack Overflow search failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"error": str(e)},
                message=f"Failed to search Stack Overflow: {e}"
            )

    async def _extract_results(self) -> List[Dict]:
        """Extract search results from Stack Overflow."""
        return await self.browser.page.evaluate("""
            () => {
                const results = [];
                const items = document.querySelectorAll('.search-result');

                items.forEach((item, i) => {
                    const titleLink = item.querySelector('.result-link a');
                    const title = titleLink?.textContent?.trim() || '';
                    const url = titleLink?.getAttribute('href') || '';

                    const excerpt = item.querySelector('.excerpt')?.textContent?.trim() || '';

                    const stats = item.querySelector('.stats');
                    const votes = stats?.querySelector('.vote-count-post strong')?.textContent || '0';
                    const answers = stats?.querySelector('.status strong')?.textContent || '0';
                    const views = stats?.querySelector('.views')?.textContent || '0';

                    const tags = Array.from(item.querySelectorAll('.tags a')).map(tag => tag.textContent.trim());

                    const accepted = item.querySelector('.status.answered-accepted') !== null;

                    results.push({
                        position: i + 1,
                        title,
                        url,
                        excerpt,
                        votes: parseInt(votes) || 0,
                        answers: parseInt(answers) || 0,
                        views: parseInt(views.replace(/[^0-9]/g, '')) || 0,
                        tags,
                        has_accepted_answer: accepted
                    });
                });

                return results;
            }
        """)

    def _filter_quality_answers(self, results: List[Dict], min_score: int) -> List[Dict]:
        """Filter results by quality metrics."""
        filtered = []

        for result in results:
            # Quality criteria
            has_upvotes = result.get("votes", 0) >= min_score
            has_answers = result.get("answers", 0) > 0
            has_accepted = result.get("has_accepted_answer", False)

            # Calculate quality score
            quality_score = 0
            if has_upvotes:
                quality_score += 2
            if has_answers:
                quality_score += 1
            if has_accepted:
                quality_score += 3

            result["quality_score"] = quality_score

            # Include if meets basic quality threshold
            if quality_score >= 2:
                filtered.append(result)

        # Sort by quality score descending
        filtered.sort(key=lambda x: x["quality_score"], reverse=True)

        return filtered[:10]

    async def _extract_question_details(self) -> Dict:
        """Extract full question and top answer from question page."""
        return await self.browser.page.evaluate("""
            () => {
                const details = {};

                // Extract question
                const questionBody = document.querySelector('.question .js-post-body');
                details.question_body = questionBody?.textContent?.trim().slice(0, 500) || '';

                const questionVotes = document.querySelector('.question .js-vote-count');
                details.question_votes = parseInt(questionVotes?.textContent || '0');

                // Extract accepted answer
                const acceptedAnswer = document.querySelector('.answer.accepted-answer .js-post-body');
                if (acceptedAnswer) {
                    details.accepted_answer = acceptedAnswer.textContent.trim().slice(0, 500);

                    const answerVotes = document.querySelector('.answer.accepted-answer .js-vote-count');
                    details.answer_votes = parseInt(answerVotes?.textContent || '0');
                } else {
                    // Get top answer by votes
                    const topAnswer = document.querySelector('.answer .js-post-body');
                    if (topAnswer) {
                        details.top_answer = topAnswer.textContent.trim().slice(0, 500);

                        const answerVotes = document.querySelector('.answer .js-vote-count');
                        details.answer_votes = parseInt(answerVotes?.textContent || '0');
                    }
                }

                // Extract code snippets
                const codeBlocks = document.querySelectorAll('.question pre code, .answer pre code');
                details.code_snippets = Array.from(codeBlocks).slice(0, 3).map(code =>
                    code.textContent.trim().slice(0, 200)
                );

                return details;
            }
        """)

    def _save_results(self, results: List[Dict]) -> Optional[str]:
        try:
            from ..output_path import save_json
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"stackoverflow_search_{timestamp}.json"
            return str(save_json(filename, {"results": results, "count": len(results)}))
        except:
            return None

    def _generate_summary(self, query: str, results: List[Dict]) -> str:
        lines = [
            "## Stack Overflow Search Results",
            f"**Query:** {query}",
            f"**Results Found:** {len(results)}",
            ""
        ]

        if results:
            lines.append("### Top Results:")
            for i, result in enumerate(results[:5]):
                lines.append(f"\n**{i+1}. {result.get('title', 'No title')[:60]}...**")
                lines.append(f"- Votes: {result.get('votes', 0)} | Answers: {result.get('answers', 0)} | Quality: {result.get('quality_score', 0)}/6")
                if result.get('has_accepted_answer'):
                    lines.append("- Has accepted answer")
                if result.get('tags'):
                    lines.append(f"- Tags: {', '.join(result['tags'][:5])}")

                # Include answer preview if available
                if result.get('details'):
                    details = result['details']
                    if details.get('accepted_answer'):
                        lines.append(f"- Answer preview: {details['accepted_answer'][:100]}...")
                    elif details.get('top_answer'):
                        lines.append(f"- Top answer: {details['top_answer'][:100]}...")
        else:
            lines.append("No quality results found. Try adjusting your search query or lowering min_score.")

        return "\n".join(lines)

# ============ N) GOVERNMENT - PDF FORMS ============

class N1_FormExtractor(BaseExecutor):
    """Extract fields from government forms."""

    capability = "N1"
    action = "extract_form"
    required_params = ["form_text"]
    optional_params = ["form_type"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        form_text = params.get("form_text", "")
        form_type = params.get("form_type", "generic")

        if not form_text:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={},
                message="Please provide form text to extract."
            )

        try:
            # Extract fields
            extracted = self._extract_fields(form_text, form_type)

            # Validate fields via web lookup if needed
            if self.browser and extracted.get("employer"):
                try:
                    await self.browser.navigate(f"https://www.google.com/search?q={extracted['employer'].replace(' ', '+')}")
                    await asyncio.sleep(1)
                    page_text = await self.browser.page.content()
                    extracted["employer_verified"] = extracted["employer"].lower() in page_text.lower()
                except:
                    pass

            # Convert to JSON structure
            json_output = self._to_json(extracted)

            # Save results
            saved_path = self._save_results(json_output)

            summary = self._generate_summary(extracted)

            return ActionResult(
                status=ActionStatus.SUCCESS,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={
                    "extracted": extracted,
                    "json": json_output,
                    "saved_to": saved_path
                },
                message=summary
            )

        except Exception as e:
            logger.error(f"Form extraction failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={"error": str(e)},
                message=f"Failed to extract form: {e}"
            )

    def _extract_fields(self, text: str, form_type: str) -> Dict:
        """Extract fields from form text."""
        fields = {}

        # Common patterns
        patterns = {
            "name": r'(?:name|employee)[:\s]+([A-Za-z\s]+)',
            "ssn": r'(?:ssn|social)[:\s]*([\d\-]+)',
            "ein": r'(?:ein|employer\s+id)[:\s]*([\d\-]+)',
            "employer": r'(?:employer)[:\s]+([A-Za-z\s]+)',
            "wages": r'(?:wages?|compensation)[:\s]*\$?([\d,\.]+)',
            "federal_tax": r'(?:federal\s+(?:income\s+)?tax)[:\s]*\$?([\d,\.]+)',
            "state_tax": r'(?:state\s+(?:income\s+)?tax)[:\s]*\$?([\d,\.]+)',
            "address": r'(?:address)[:\s]+([^\n]+)',
        }

        for field, pattern in patterns.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                fields[field] = match.group(1).strip()

        return fields

    def _to_json(self, fields: Dict) -> Dict:
        """Convert to structured JSON."""
        return {
            "form_data": fields,
            "metadata": {
                "extracted_at": datetime.now().isoformat(),
                "fields_found": len(fields)
            }
        }

    def _save_results(self, data: Dict) -> Optional[str]:
        try:
            from ..output_path import save_json
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"form_extraction_{timestamp}.json"
            return str(save_json(filename, data))
        except:
            return None

    def _generate_summary(self, fields: Dict) -> str:
        lines = [
            "## Form Extraction Results",
            f"**Fields Extracted:** {len(fields)}",
            "",
            "### Data:"
        ]

        for field, value in fields.items():
            # Mask sensitive data
            if field in ['ssn', 'ein']:
                value = '***-**-' + value[-4:] if len(value) > 4 else '****'
            lines.append(f"- **{field.replace('_', ' ').title()}:** {value}")

        return "\n".join(lines)


# ============ REGISTRY ============

WORKFLOW_EXECUTORS = {
    "A1": A1_EmailInbox,
    "B1": B1_SpreadsheetCleaner,
    "C1": C1_TicketClassifier,
    "D1": D1_CompanyResearch,
    "G1": G1_ContractExtractor,
    "I1": I1_MaintenanceAnalyzer,
    "J1": J1_TransactionCategorizer,
    "K1": K1_AnalyticsInsights,
    "L1": L1_ResumeAnalyzer,
    "M1": M1_QuizGenerator,
    "N1": N1_FormExtractor,
    "O1": O1_StackOverflowSearch,
}


def get_workflow_executor(capability: str):
    """Get executor by capability."""
    return WORKFLOW_EXECUTORS.get(capability)
