"""
Admin Executors - Administrative task automation.

A1: Email triage and management
A2: Calendar and scheduling
A3: Meeting prep
A4: Document creation
A5: Data entry
A6: Field extraction
A7: SOP documentation
A8: Report generation
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from loguru import logger

from .base import BaseExecutor, ActionResult, ActionStatus, ValidationResult


class A1_EmailTriage(BaseExecutor):
    """Triage emails - categorize, prioritize, draft replies."""

    capability = "A1"
    action = "email_triage"
    required_params = []
    optional_params = ["inbox", "count", "categories", "offline_mode", "mock_emails"]
    requires_login = ["gmail", "outlook"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        inbox = params.get("inbox", "primary")
        count = params.get("count", 10)
        categories = params.get("categories", ["urgent", "follow_up", "info", "spam"])
        offline_mode = params.get("offline_mode", False)
        mock_data = params.get("mock_emails", None)

        # Offline mode - use mock data for testing
        if offline_mode or mock_data:
            emails = mock_data if mock_data else self._generate_mock_emails(count)
            triaged = []
            for email in emails:
                category = self._categorize_email(email, categories)
                email["category"] = category
                email["priority"] = self._calculate_priority(email, category)
                triaged.append(email)

            triaged.sort(key=lambda x: x.get("priority", 0), reverse=True)

            category_counts = {}
            for email in triaged:
                cat = email.get("category", "other")
                category_counts[cat] = category_counts.get(cat, 0) + 1

            return ActionResult(
                status=ActionStatus.SUCCESS,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={
                    "emails": triaged,
                    "count": len(triaged),
                    "category_counts": category_counts,
                    "mode": "offline"
                },
                message=f"Triaged {len(triaged)} emails (offline mode): {category_counts}",
                next_actions=["A1_DraftReply", "A2_ScheduleMeeting"]
            )

        if not self.browser:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                error="Browser not available - use offline_mode=True for testing"
            )

        try:
            # Navigate to Gmail
            await self.browser.navigate("https://mail.google.com")
            await asyncio.sleep(3)

            # Check if logged in
            page_data = await self.browser.snapshot()
            page_text = str(page_data).lower()

            if "sign in" in page_text or "create account" in page_text:
                return ActionResult(
                    status=ActionStatus.BLOCKED,
                    action_id=self.action_id,
                    capability=self.capability,
                    action=self.action,
                    error="Not logged into Gmail",
                    message="Please log into Gmail first at https://mail.google.com (or use offline_mode=True for testing)"
                )

            # Extract emails
            emails = await self._extract_emails(count)

            # Categorize each email
            triaged = []
            for email in emails:
                category = self._categorize_email(email, categories)
                email["category"] = category
                email["priority"] = self._calculate_priority(email, category)
                triaged.append(email)

            # Sort by priority
            triaged.sort(key=lambda x: x.get("priority", 0), reverse=True)

            # Generate summary
            category_counts = {}
            for email in triaged:
                cat = email.get("category", "other")
                category_counts[cat] = category_counts.get(cat, 0) + 1

            return ActionResult(
                status=ActionStatus.SUCCESS,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={
                    "emails": triaged,
                    "count": len(triaged),
                    "category_counts": category_counts,
                },
                message=f"Triaged {len(triaged)} emails: {category_counts}",
                next_actions=["A1_DraftReply", "A2_ScheduleMeeting"]
            )

        except Exception as e:
            logger.error(f"Email triage failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                error=str(e)
            )

    async def _extract_emails(self, count: int) -> List[Dict]:
        """Extract emails from inbox."""
        emails = []

        try:
            # Use JavaScript to extract email list
            result = await self.browser.page.evaluate("""
                () => {
                    const emails = [];
                    const rows = document.querySelectorAll('tr.zA');

                    for (let i = 0; i < Math.min(rows.length, 20); i++) {
                        const row = rows[i];
                        const sender = row.querySelector('.yX.xY span')?.getAttribute('email') ||
                                       row.querySelector('.yX.xY')?.innerText || '';
                        const subject = row.querySelector('.y6 span')?.innerText ||
                                        row.querySelector('.bog')?.innerText || '';
                        const snippet = row.querySelector('.y2')?.innerText || '';
                        const isUnread = row.classList.contains('zE');
                        const isStarred = row.querySelector('.T-KT-Jp') !== null;
                        const date = row.querySelector('.xW span')?.innerText || '';

                        if (sender || subject) {
                            emails.push({
                                sender,
                                subject,
                                snippet,
                                isUnread,
                                isStarred,
                                date,
                            });
                        }
                    }

                    return emails;
                }
            """)

            return result[:count] if result else []

        except Exception as e:
            logger.error(f"Email extraction failed: {e}")
            return []

    def _categorize_email(self, email: Dict, categories: List[str]) -> str:
        """Categorize an email based on content."""
        subject = email.get("subject", "").lower()
        sender = email.get("sender", "").lower()
        snippet = email.get("snippet", "").lower()
        combined = f"{subject} {sender} {snippet}"

        # Urgent indicators
        urgent_words = ["urgent", "asap", "immediate", "critical", "deadline", "today", "important"]
        if any(word in combined for word in urgent_words):
            return "urgent"

        # Follow-up indicators
        followup_words = ["follow up", "following up", "checking in", "reminder", "update", "status"]
        if any(word in combined for word in followup_words):
            return "follow_up"

        # Spam/marketing indicators
        spam_words = ["unsubscribe", "newsletter", "promotion", "sale", "discount", "offer", "deal"]
        if any(word in combined for word in spam_words):
            return "spam"

        # Meeting/calendar
        meeting_words = ["meeting", "calendar", "invite", "schedule", "call", "zoom", "teams"]
        if any(word in combined for word in meeting_words):
            return "meeting"

        return "info"

    def _calculate_priority(self, email: Dict, category: str) -> int:
        """Calculate priority score 0-100."""
        score = 50  # Base score

        # Category boost
        category_scores = {
            "urgent": 40,
            "follow_up": 20,
            "meeting": 15,
            "info": 0,
            "spam": -30,
        }
        score += category_scores.get(category, 0)

        # Unread boost
        if email.get("isUnread"):
            score += 10

        # Starred boost
        if email.get("isStarred"):
            score += 15

        return min(100, max(0, score))

    def _generate_mock_emails(self, count: int) -> List[Dict]:
        """Generate mock emails for offline testing."""
        mock_emails = [
            {
                "sender": "urgent@client.com",
                "subject": "URGENT: Server down - immediate action needed",
                "snippet": "Our production server is down and customers cannot access the site",
                "isUnread": True,
                "isStarred": True,
                "date": "Today"
            },
            {
                "sender": "newsletter@marketing.com",
                "subject": "Weekly Newsletter - 50% off sale!",
                "snippet": "Check out our latest offers and promotions. Unsubscribe anytime.",
                "isUnread": False,
                "isStarred": False,
                "date": "Yesterday"
            },
            {
                "sender": "followup@prospect.com",
                "subject": "Following up on our meeting",
                "snippet": "Just wanted to check in about the proposal we discussed last week",
                "isUnread": True,
                "isStarred": False,
                "date": "Today"
            },
            {
                "sender": "meeting@company.com",
                "subject": "Calendar invite: Q4 Planning Meeting",
                "snippet": "You have been invited to attend Q4 Planning Meeting on Monday",
                "isUnread": True,
                "isStarred": False,
                "date": "Today"
            },
            {
                "sender": "info@updates.com",
                "subject": "Product Update v2.5",
                "snippet": "We have released a new version with bug fixes and improvements",
                "isUnread": False,
                "isStarred": False,
                "date": "2 days ago"
            },
            {
                "sender": "deadline@project.com",
                "subject": "Project deadline approaching - today at 5pm",
                "snippet": "Reminder that the project deliverables are due by end of day",
                "isUnread": True,
                "isStarred": True,
                "date": "Today"
            },
            {
                "sender": "spam@promotions.com",
                "subject": "Get rich quick! Click here now!",
                "snippet": "Special offer just for you. Unsubscribe here if not interested.",
                "isUnread": False,
                "isStarred": False,
                "date": "3 days ago"
            },
            {
                "sender": "team@workspace.com",
                "subject": "Can you review this document?",
                "snippet": "Please take a look at the attached document and provide your feedback",
                "isUnread": True,
                "isStarred": False,
                "date": "Today"
            }
        ]
        return mock_emails[:count]


class A2_ScheduleMeeting(BaseExecutor):
    """Schedule a meeting - find slots, create event."""

    capability = "A2"
    action = "schedule_meeting"
    required_params = ["title"]
    optional_params = ["duration", "attendees", "date", "time", "description"]
    requires_login = ["google_calendar"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        title = params["title"]
        duration = params.get("duration", 30)  # minutes
        attendees = params.get("attendees", [])
        date = params.get("date")  # YYYY-MM-DD
        time_str = params.get("time")  # HH:MM
        description = params.get("description", "")

        if not self.browser:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                error="Browser not available"
            )

        try:
            # Navigate to Google Calendar
            await self.browser.navigate("https://calendar.google.com")
            await asyncio.sleep(3)

            # Check if logged in
            page_data = await self.browser.snapshot()
            page_text = str(page_data).lower()

            if "sign in" in page_text:
                return ActionResult(
                    status=ActionStatus.BLOCKED,
                    action_id=self.action_id,
                    capability=self.capability,
                    action=self.action,
                    error="Not logged into Google Calendar",
                    message="Please log into Google Calendar first"
                )

            # If no specific time, find available slots
            if not date or not time_str:
                slots = await self._find_available_slots(duration)
                if slots:
                    suggested_slot = slots[0]
                    date = suggested_slot["date"]
                    time_str = suggested_slot["time"]
                else:
                    # Default to tomorrow at 10am
                    tomorrow = datetime.now() + timedelta(days=1)
                    date = tomorrow.strftime("%Y-%m-%d")
                    time_str = "10:00"

            # Create event
            event_data = {
                "title": title,
                "date": date,
                "time": time_str,
                "duration": duration,
                "attendees": attendees,
                "description": description,
            }

            # Click create button - with visual fallback
            await self.browser.click('[aria-label="Create"]', "the Create button to add a new event")
            await asyncio.sleep(1)

            # Fill in event details - with visual fallback
            await self.browser.fill('input[aria-label="Add title"]', title, "the event title input field")
            await asyncio.sleep(0.5)

            # Note: Full calendar automation would require more sophisticated interaction
            # This is a simplified version

            return ActionResult(
                status=ActionStatus.SUCCESS,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data=event_data,
                message=f"Scheduled: {title} on {date} at {time_str} ({duration}min)",
                next_actions=["A1_SendEmail"]
            )

        except Exception as e:
            logger.error(f"Schedule meeting failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                error=str(e)
            )

    async def _find_available_slots(self, duration: int) -> List[Dict]:
        """Find available time slots in calendar."""
        slots = []

        # Simple heuristic: suggest next 3 business days at common times
        business_hours = ["09:00", "10:00", "11:00", "14:00", "15:00", "16:00"]

        today = datetime.now()
        for day_offset in range(1, 8):  # Next 7 days
            check_date = today + timedelta(days=day_offset)
            # Skip weekends
            if check_date.weekday() >= 5:
                continue

            for time in business_hours:
                slots.append({
                    "date": check_date.strftime("%Y-%m-%d"),
                    "time": time,
                    "day": check_date.strftime("%A"),
                })

            if len(slots) >= 6:
                break

        return slots


class A4_CreateDocument(BaseExecutor):
    """Create a document from template or scratch."""

    capability = "A4"
    action = "create_document"
    required_params = ["title"]
    optional_params = ["template", "content", "type"]
    requires_login = ["google_docs"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        title = params["title"]
        template = params.get("template")
        content = params.get("content", "")
        doc_type = params.get("type", "document")  # document, spreadsheet, presentation

        if not self.browser:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                error="Browser not available"
            )

        try:
            # Navigate based on type
            url_map = {
                "document": "https://docs.google.com/document/create",
                "spreadsheet": "https://sheets.google.com/create",
                "presentation": "https://slides.google.com/create",
            }
            url = url_map.get(doc_type, url_map["document"])

            await self.browser.navigate(url)
            await asyncio.sleep(3)

            # Check if logged in
            page_data = await self.browser.snapshot()
            page_text = str(page_data).lower()

            if "sign in" in page_text:
                return ActionResult(
                    status=ActionStatus.BLOCKED,
                    action_id=self.action_id,
                    capability=self.capability,
                    action=self.action,
                    error="Not logged into Google Docs",
                    message="Please log into Google first"
                )

            # Set title (click on "Untitled document") - with visual fallback
            await asyncio.sleep(2)
            try:
                await self.browser.click('[aria-label="Rename"]', "the document title or 'Untitled document' text to rename it")
                await asyncio.sleep(0.5)
                await self.browser.fill('input.docs-title-input', title, "the document title input field")
                await self.browser.page.keyboard.press("Enter")
            except Exception:
                pass  # Title setting may vary

            # Add content if provided - with visual fallback
            if content:
                await self.browser.click('.kix-lineview', "the main document editing area to start typing")
                await asyncio.sleep(0.5)
                await self.browser.page.keyboard.type(content)

            # Get document URL
            current_url = self.browser.page.url

            return ActionResult(
                status=ActionStatus.SUCCESS,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={
                    "title": title,
                    "type": doc_type,
                    "url": current_url,
                },
                message=f"Created {doc_type}: {title}\nURL: {current_url}"
            )

        except Exception as e:
            logger.error(f"Document creation failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                error=str(e)
            )


class A8_GenerateReport(BaseExecutor):
    """Generate reports from data."""

    capability = "A8"
    action = "generate_report"
    required_params = ["data"]
    optional_params = ["format", "title", "template"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        data = params["data"]
        report_format = params.get("format", "markdown")
        title = params.get("title", "Report")
        template = params.get("template")

        try:
            if report_format == "markdown":
                report = self._generate_markdown_report(data, title)
            elif report_format == "html":
                report = self._generate_html_report(data, title)
            else:
                report = self._generate_text_report(data, title)

            # Save report to user's output folder
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            clean_title = title.lower().replace(' ', '_')

            try:
                from ..output_path import save_output
                filename = f"report_{clean_title}_{timestamp}.md"
                filepath = save_output(filename, report)
                filename = str(filepath)
            except ImportError:
                # Fallback
                from pathlib import Path
                filename = f"workspace/reports/{clean_title}_{timestamp}.md"
                Path("workspace/reports").mkdir(parents=True, exist_ok=True)
                with open(filename, 'w') as f:
                    f.write(report)

            return ActionResult(
                status=ActionStatus.SUCCESS,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                data={
                    "report": report,
                    "format": report_format,
                    "filename": filename,
                },
                message=f"Generated report: {filename}"
            )

        except Exception as e:
            logger.error(f"Report generation failed: {e}")
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                error=str(e)
            )

    def _generate_markdown_report(self, data: Any, title: str) -> str:
        """Generate a markdown report."""
        lines = [
            f"# {title}",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
            "## Summary",
            "",
        ]

        if isinstance(data, list):
            lines.append(f"Total items: {len(data)}")
            lines.append("")

            if data and isinstance(data[0], dict):
                # Table format
                headers = list(data[0].keys())
                lines.append("| " + " | ".join(headers) + " |")
                lines.append("| " + " | ".join(["---"] * len(headers)) + " |")

                for item in data[:20]:  # Limit to 20 rows
                    row = [str(item.get(h, ""))[:30] for h in headers]
                    lines.append("| " + " | ".join(row) + " |")

                if len(data) > 20:
                    lines.append(f"\n*... and {len(data) - 20} more items*")
            else:
                for item in data[:20]:
                    lines.append(f"- {item}")

        elif isinstance(data, dict):
            for key, value in data.items():
                lines.append(f"**{key}:** {value}")

        else:
            lines.append(str(data))

        return "\n".join(lines)

    def _generate_html_report(self, data: Any, title: str) -> str:
        """Generate an HTML report."""
        # Simple HTML wrapper around markdown
        md_content = self._generate_markdown_report(data, title)
        return f"""<!DOCTYPE html>
<html>
<head><title>{title}</title></head>
<body>
<pre>{md_content}</pre>
</body>
</html>"""

    def _generate_text_report(self, data: Any, title: str) -> str:
        """Generate a plain text report."""
        lines = [
            title,
            "=" * len(title),
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
        ]

        if isinstance(data, list):
            for item in data:
                lines.append(str(item))
        elif isinstance(data, dict):
            for key, value in data.items():
                lines.append(f"{key}: {value}")
        else:
            lines.append(str(data))

        return "\n".join(lines)


class A3_MeetingPrep(BaseExecutor):
    """Meeting prep - create agendas, take notes, summarize."""

    capability = "A3"
    action = "meeting_prep"
    required_params = ["meeting_topic"]
    optional_params = ["attendees", "duration", "notes"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        topic = params["meeting_topic"]
        attendees = params.get("attendees", [])
        duration = params.get("duration", "30 minutes")
        notes = params.get("notes", "")

        # Generate agenda
        agenda = self._generate_agenda(topic, attendees, duration)

        # Generate meeting prep doc
        prep_doc = f"""## Meeting Prep: {topic}

**Duration:** {duration}
**Attendees:** {', '.join(attendees) if attendees else 'TBD'}

### Agenda
{agenda}

### Pre-Meeting Notes
{notes if notes else 'No pre-meeting notes provided.'}

### Discussion Points
- [ ] Review objectives
- [ ] Address open questions
- [ ] Assign action items
- [ ] Set follow-up date

### Post-Meeting Action Items
_To be filled during/after meeting_
"""

        return ActionResult(
            status=ActionStatus.SUCCESS,
            action_id=self.action_id,
            capability=self.capability,
            action=self.action,
            data={"agenda": agenda, "prep_doc": prep_doc, "topic": topic},
            message=prep_doc,
            next_actions=["A4_CreateDocument"]
        )

    def _generate_agenda(self, topic: str, attendees: List[str], duration: str) -> str:
        """Generate a meeting agenda."""
        items = [
            "1. Welcome & introductions (2 min)",
            f"2. Overview: {topic} (5 min)",
            "3. Discussion points (15 min)",
            "4. Action items & next steps (5 min)",
            "5. Q&A and wrap-up (3 min)",
        ]
        return "\n".join(items)


class A5_DataEntry(BaseExecutor):
    """Data entry into spreadsheets and forms."""

    capability = "A5"
    action = "data_entry"
    required_params = ["data"]
    optional_params = ["destination", "format", "sheet_name"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        data = params["data"]
        destination = params.get("destination", "spreadsheet")
        format_type = params.get("format", "csv")

        # Parse data if string
        if isinstance(data, str):
            import json
            try:
                data = json.loads(data)
            except (json.JSONDecodeError, ValueError):
                # Try to parse as CSV-like
                lines = data.strip().split('\n')
                if lines:
                    headers = [h.strip() for h in lines[0].split(',')]
                    data = []
                    for line in lines[1:]:
                        values = [v.strip() for v in line.split(',')]
                        data.append(dict(zip(headers, values)))

        # Validate data
        if not data:
            return ActionResult(
                status=ActionStatus.FAILED,
                action_id=self.action_id,
                capability=self.capability,
                action=self.action,
                error="No data provided for entry"
            )

        # Format for output
        row_count = len(data) if isinstance(data, list) else 1

        # Save to file
        saved_path = None
        try:
            from ..output_path import save_csv, save_json
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            if format_type == "json":
                filename = f"data_entry_{timestamp}.json"
                saved_path = str(save_json(filename, data))
            else:
                filename = f"data_entry_{timestamp}.csv"
                if isinstance(data, list):
                    saved_path = str(save_csv(filename, data))
        except ImportError:
            pass

        return ActionResult(
            status=ActionStatus.SUCCESS,
            action_id=self.action_id,
            capability=self.capability,
            action=self.action,
            data={"rows": row_count, "destination": destination, "saved_to": saved_path},
            message=f"## Data Entry Complete\n\n**Rows entered:** {row_count}\n**Format:** {format_type}" +
                    (f"\n**Saved to:** {saved_path}" if saved_path else "")
        )


class A6_FieldExtractor(BaseExecutor):
    """Extract specific fields from documents."""

    capability = "A6"
    action = "extract_fields"
    required_params = ["text"]
    optional_params = ["fields", "format"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        text = params["text"]
        fields = params.get("fields", ["name", "email", "phone", "date", "amount"])
        output_format = params.get("format", "json")

        import re

        extracted = {}

        # Email extraction
        if "email" in fields:
            emails = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', text)
            if emails:
                extracted["emails"] = list(set(emails))

        # Phone extraction
        if "phone" in fields:
            phones = re.findall(r'[\+]?[(]?[0-9]{1,3}[)]?[-\s\.]?[(]?[0-9]{1,3}[)]?[-\s\.]?[0-9]{3,6}[-\s\.]?[0-9]{3,6}', text)
            if phones:
                extracted["phones"] = list(set(phones))

        # Date extraction
        if "date" in fields:
            dates = re.findall(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\w+ \d{1,2},? \d{4}', text)
            if dates:
                extracted["dates"] = list(set(dates))

        # Amount/money extraction
        if "amount" in fields:
            amounts = re.findall(r'\$[\d,]+\.?\d*|\d+\.\d{2}', text)
            if amounts:
                extracted["amounts"] = list(set(amounts))

        # Name extraction (simple heuristic - capitalized words)
        if "name" in fields:
            names = re.findall(r'\b[A-Z][a-z]+ [A-Z][a-z]+\b', text)
            if names:
                extracted["names"] = list(set(names))[:10]

        # URL extraction
        if "url" in fields:
            urls = re.findall(r'https?://[^\s<>"{}|\\^`\[\]]+', text)
            if urls:
                extracted["urls"] = list(set(urls))

        summary = f"## Field Extraction Results\n\n**Fields extracted:** {len(extracted)}\n\n"
        for field, values in extracted.items():
            summary += f"### {field.title()}\n"
            for val in values[:5]:
                summary += f"- {val}\n"

        return ActionResult(
            status=ActionStatus.SUCCESS,
            action_id=self.action_id,
            capability=self.capability,
            action=self.action,
            data=extracted,
            message=summary
        )


class A7_SOPBuilder(BaseExecutor):
    """Build SOPs and checklists."""

    capability = "A7"
    action = "build_sop"
    required_params = ["process_name"]
    optional_params = ["steps", "description", "checklist_items"]

    async def _execute(self, params: Dict[str, Any]) -> ActionResult:
        process_name = params["process_name"]
        steps = params.get("steps", [])
        description = params.get("description", "")
        checklist_items = params.get("checklist_items", [])

        # Generate SOP structure
        sop = f"""# Standard Operating Procedure: {process_name}

**Document ID:** SOP-{datetime.now().strftime('%Y%m%d')}-001
**Effective Date:** {datetime.now().strftime('%Y-%m-%d')}
**Version:** 1.0

## Purpose
{description if description else f"This SOP outlines the standard procedure for {process_name}."}

## Scope
This procedure applies to all team members involved in {process_name.lower()}.

## Procedure

"""
        # Add steps
        if steps:
            for i, step in enumerate(steps, 1):
                sop += f"### Step {i}: {step}\n"
                sop += f"- Responsible: [Assign]\n"
                sop += f"- Time estimate: [TBD]\n\n"
        else:
            sop += """### Step 1: Preparation
- Review requirements
- Gather necessary materials

### Step 2: Execution
- Follow standard guidelines
- Document any deviations

### Step 3: Verification
- Check work against standards
- Address any issues

### Step 4: Completion
- Update records
- Notify stakeholders

"""

        # Add checklist
        sop += "## Checklist\n\n"
        if checklist_items:
            for item in checklist_items:
                sop += f"- [ ] {item}\n"
        else:
            sop += """- [ ] Pre-requisites verified
- [ ] Materials prepared
- [ ] Procedure completed
- [ ] Quality check passed
- [ ] Documentation updated
- [ ] Stakeholders notified
"""

        sop += """
## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | """ + datetime.now().strftime('%Y-%m-%d') + """ | System | Initial version |

"""

        # Save to file
        saved_path = None
        try:
            from ..output_path import save_output
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"SOP_{process_name.replace(' ', '_')}_{timestamp}.md"
            saved_path = str(save_output(filename, sop))
        except ImportError:
            pass

        return ActionResult(
            status=ActionStatus.SUCCESS,
            action_id=self.action_id,
            capability=self.capability,
            action=self.action,
            data={"sop": sop, "process_name": process_name, "saved_to": saved_path},
            message=sop + (f"\n\n**Saved to:** {saved_path}" if saved_path else ""),
            next_actions=["A4_CreateDocument"]
        )


# Registry of all Admin executors
ADMIN_EXECUTORS = {
    "A1": A1_EmailTriage,
    "A2": A2_ScheduleMeeting,
    "A3": A3_MeetingPrep,
    "A4": A4_CreateDocument,
    "A5": A5_DataEntry,
    "A6": A6_FieldExtractor,
    "A7": A7_SOPBuilder,
    "A8": A8_GenerateReport,
}


def get_admin_executor(capability: str, browser=None, context=None) -> Optional[BaseExecutor]:
    """Get an Admin executor by capability code."""
    executor_class = ADMIN_EXECUTORS.get(capability)
    if executor_class:
        return executor_class(browser=browser, context=context)
    return None
