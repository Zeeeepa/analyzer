"""
Document Processor - Handles PDFs, emails, spreadsheets, logs, and text files
Supports all business automation use cases A-O
"""

import os
import re
import json
import csv
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, asdict
from collections import Counter

logger = logging.getLogger(__name__)

# Rust acceleration bridge
try:
    from .rust_bridge import (
        fast_json_parse,
        fast_json_dumps,
        extract_emails as rust_extract_emails,
        extract_phones as rust_extract_phones,
        is_rust_available
    )
    USE_RUST_CORE = is_rust_available()
except ImportError:
    USE_RUST_CORE = False

if USE_RUST_CORE:
    logger.info("Document processor: Rust acceleration enabled for JSON parsing")
else:
    logger.info("Document processor: Using Python JSON parser")

# ============================================================================
# DATA CLASSES FOR STRUCTURED OUTPUT
# ============================================================================

@dataclass
class Email:
    sender: str
    recipient: str
    subject: str
    date: str
    body: str
    needs_action: bool = False
    action_type: str = ""  # reply, forward, archive, schedule
    priority: str = "normal"  # high, normal, low
    summary: str = ""
    draft_reply: str = ""

@dataclass
class SupportTicket:
    id: str
    customer: str
    subject: str
    body: str
    category: str = ""  # billing, technical, general, complaint, feature_request
    priority: str = "normal"
    sentiment: str = "neutral"  # positive, neutral, negative, angry
    suggested_reply: str = ""

@dataclass
class Transaction:
    date: str
    description: str
    amount: float
    category: str = ""
    is_anomaly: bool = False
    anomaly_reason: str = ""

@dataclass
class Resume:
    name: str
    email: str
    phone: str
    skills: List[str]
    experience_years: float
    education: str
    job_titles: List[str]
    fit_score: float = 0.0
    fit_reasons: List[str] = None

@dataclass
class ContractEntity:
    parties: List[str]
    effective_date: str
    expiration_date: str
    dollar_amounts: List[Dict[str, Any]]
    obligations: List[str]
    key_terms: List[str]

@dataclass
class LogEntry:
    timestamp: str
    level: str  # ERROR, WARN, INFO, DEBUG
    message: str
    source: str = ""
    count: int = 1

# ============================================================================
# DOCUMENT PROCESSOR CLASS
# ============================================================================

class DocumentProcessor:
    """Processes various document types for business automation"""

    def __init__(self):
        self.supported_extensions = {
            'text': ['.txt', '.md', '.log', '.csv', '.json'],
            'email': ['.eml', '.msg'],
            'spreadsheet': ['.csv', '.tsv', '.xlsx', '.xls'],
            'pdf': ['.pdf'],
            'image': ['.png', '.jpg', '.jpeg', '.gif', '.webp']
        }

    # ========================================================================
    # A) EMAIL PROCESSING
    # ========================================================================

    def parse_emails(self, content: str) -> List[Email]:
        """Parse email content (raw text or structured)"""
        emails = []

        # Try to parse as structured email dump
        email_blocks = re.split(r'\n(?=From:|Subject:|---+\s*Email)', content)

        for block in email_blocks:
            if not block.strip():
                continue

            email = self._parse_single_email(block)
            if email:
                emails.append(email)

        return emails

    def _parse_single_email(self, block: str) -> Optional[Email]:
        """Parse a single email block"""
        # Extract fields using regex patterns
        from_match = re.search(r'From:\s*(.+?)(?:\n|$)', block, re.I)
        to_match = re.search(r'To:\s*(.+?)(?:\n|$)', block, re.I)
        subject_match = re.search(r'Subject:\s*(.+?)(?:\n|$)', block, re.I)
        date_match = re.search(r'Date:\s*(.+?)(?:\n|$)', block, re.I)

        # Body is everything after headers
        body_match = re.search(r'\n\n(.+)', block, re.S)

        if not (from_match or subject_match):
            return None

        email = Email(
            sender=from_match.group(1).strip() if from_match else "",
            recipient=to_match.group(1).strip() if to_match else "",
            subject=subject_match.group(1).strip() if subject_match else "",
            date=date_match.group(1).strip() if date_match else "",
            body=body_match.group(1).strip() if body_match else block
        )

        # Analyze email for action needed
        email = self._analyze_email(email)
        return email

    def _analyze_email(self, email: Email) -> Email:
        """Analyze email to determine if action is needed"""
        body_lower = email.body.lower()
        subject_lower = email.subject.lower()
        combined = body_lower + " " + subject_lower

        # Priority detection
        urgent_keywords = ['urgent', 'asap', 'immediately', 'critical', 'emergency', 'deadline']
        if any(k in combined for k in urgent_keywords):
            email.priority = "high"

        # Action detection
        action_keywords = {
            'reply': ['please respond', 'please reply', 'let me know', 'your thoughts', 'what do you think', 'can you', 'could you', 'would you'],
            'schedule': ['schedule', 'meeting', 'calendar', 'availability', 'book a time'],
            'review': ['please review', 'take a look', 'feedback', 'approve'],
            'forward': ['fyi', 'for your information', 'sharing this'],
        }

        email.needs_action = False
        for action_type, keywords in action_keywords.items():
            if any(k in combined for k in keywords):
                email.needs_action = True
                email.action_type = action_type
                break

        # Generate summary
        sentences = re.split(r'[.!?]+', email.body)
        email.summary = sentences[0][:200] if sentences else ""

        return email

    def draft_email_replies(self, emails: List[Email]) -> List[Email]:
        """Generate draft replies for emails that need action"""
        for email in emails:
            if not email.needs_action:
                continue

            # Generate contextual reply
            email.draft_reply = self._generate_reply(email)

        return emails

    def _generate_reply(self, email: Email) -> str:
        """Generate a draft reply based on email context"""
        templates = {
            'reply': f"Hi,\n\nThank you for your email regarding \"{email.subject}\".\n\n[Your response here]\n\nBest regards",
            'schedule': f"Hi,\n\nThank you for reaching out about scheduling. I'm available:\n\n- [Option 1]\n- [Option 2]\n\nPlease let me know what works best.\n\nBest regards",
            'review': f"Hi,\n\nThank you for sharing this for review. I've looked it over and [your feedback here].\n\nBest regards",
            'forward': "",  # No reply needed for FYI
        }

        return templates.get(email.action_type, templates['reply'])

    def summarize_inbox(self, emails: List[Email]) -> Dict[str, Any]:
        """Generate inbox summary with actionable insights"""
        total = len(emails)
        needs_action = [e for e in emails if e.needs_action]
        high_priority = [e for e in emails if e.priority == "high"]

        by_action = Counter(e.action_type for e in needs_action)

        return {
            "total_emails": total,
            "needs_action": len(needs_action),
            "high_priority": len(high_priority),
            "action_breakdown": dict(by_action),
            "summaries": [
                {
                    "subject": e.subject,
                    "from": e.sender,
                    "priority": e.priority,
                    "action": e.action_type,
                    "summary": e.summary
                }
                for e in emails[:15]  # Top 15
            ]
        }

    # ========================================================================
    # B) SPREADSHEET PROCESSING
    # ========================================================================

    def clean_spreadsheet(self, content: str, delimiter: str = None) -> Dict[str, Any]:
        """Clean and normalize messy spreadsheet data"""
        # Auto-detect delimiter
        if delimiter is None:
            delimiter = self._detect_delimiter(content)

        lines = content.strip().split('\n')
        if not lines:
            return {"error": "Empty content"}

        # Parse CSV
        reader = csv.reader(lines, delimiter=delimiter)
        rows = list(reader)

        if not rows:
            return {"error": "No data rows"}

        # Detect and clean headers
        headers = self._clean_headers(rows[0])

        # Clean data rows
        cleaned_rows = []
        issues = []

        for i, row in enumerate(rows[1:], start=2):
            cleaned_row, row_issues = self._clean_row(row, headers, i)
            cleaned_rows.append(cleaned_row)
            issues.extend(row_issues)

        # Generate normalized CSV
        output = self._generate_csv(headers, cleaned_rows)

        return {
            "success": True,
            "original_rows": len(rows) - 1,
            "cleaned_rows": len(cleaned_rows),
            "headers": headers,
            "issues_found": len(issues),
            "issues": issues[:20],  # First 20 issues
            "normalized_csv": output,
            "sample_data": cleaned_rows[:5]
        }

    def _detect_delimiter(self, content: str) -> str:
        """Auto-detect CSV delimiter"""
        first_line = content.split('\n')[0]
        delimiters = [',', '\t', ';', '|']
        counts = {d: first_line.count(d) for d in delimiters}
        return max(counts, key=counts.get)

    def _clean_headers(self, headers: List[str]) -> List[str]:
        """Normalize column headers"""
        cleaned = []
        for h in headers:
            # Remove special chars, normalize whitespace
            h = re.sub(r'[^\w\s]', '', h)
            h = re.sub(r'\s+', '_', h.strip().lower())
            h = h or f"column_{len(cleaned)}"

            # Handle duplicates
            base = h
            counter = 1
            while h in cleaned:
                h = f"{base}_{counter}"
                counter += 1

            cleaned.append(h)
        return cleaned

    def _clean_row(self, row: List[str], headers: List[str], row_num: int) -> Tuple[Dict, List[str]]:
        """Clean a single data row"""
        issues = []
        cleaned = {}

        # Pad row if needed
        while len(row) < len(headers):
            row.append("")
            issues.append(f"Row {row_num}: Missing columns, padded with empty values")

        for i, header in enumerate(headers):
            value = row[i] if i < len(row) else ""

            # Clean value
            original = value
            value = value.strip()

            # Normalize common patterns
            value = self._normalize_value(value, header)

            if value != original.strip():
                issues.append(f"Row {row_num}, {header}: Normalized '{original}' → '{value}'")

            cleaned[header] = value

        return cleaned, issues

    def _normalize_value(self, value: str, header: str) -> str:
        """Normalize a cell value based on context"""
        if not value or value.lower() in ['n/a', 'na', 'null', 'none', '-', '']:
            return ""

        # Email normalization
        if 'email' in header:
            value = value.lower().strip()

        # Phone normalization
        if 'phone' in header or 'tel' in header:
            digits = re.sub(r'\D', '', value)
            if len(digits) == 10:
                value = f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
            elif len(digits) == 11 and digits[0] == '1':
                value = f"+1 ({digits[1:4]}) {digits[4:7]}-{digits[7:]}"

        # Date normalization
        if 'date' in header:
            value = self._normalize_date(value)

        # Currency normalization
        if 'amount' in header or 'price' in header or 'cost' in header:
            value = self._normalize_currency(value)

        return value

    def _normalize_date(self, value: str) -> str:
        """Try to normalize date to YYYY-MM-DD"""
        patterns = [
            (r'(\d{1,2})/(\d{1,2})/(\d{4})', lambda m: f"{m.group(3)}-{m.group(1).zfill(2)}-{m.group(2).zfill(2)}"),
            (r'(\d{1,2})-(\d{1,2})-(\d{4})', lambda m: f"{m.group(3)}-{m.group(1).zfill(2)}-{m.group(2).zfill(2)}"),
            (r'(\d{4})/(\d{1,2})/(\d{1,2})', lambda m: f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"),
        ]

        for pattern, transform in patterns:
            match = re.match(pattern, value)
            if match:
                return transform(match)

        return value

    def _normalize_currency(self, value: str) -> str:
        """Normalize currency to plain number"""
        # Remove currency symbols and commas
        value = re.sub(r'[$€£¥,]', '', value)
        try:
            num = float(value)
            return f"{num:.2f}"
        except ValueError:
            return value

    def _generate_csv(self, headers: List[str], rows: List[Dict]) -> str:
        """Generate clean CSV output"""
        output = [','.join(headers)]
        for row in rows:
            values = [str(row.get(h, '')).replace(',', ';') for h in headers]
            output.append(','.join(values))
        return '\n'.join(output)

    # ========================================================================
    # C) SUPPORT TICKET CLASSIFICATION
    # ========================================================================

    def classify_tickets(self, tickets_content: str) -> List[SupportTicket]:
        """Parse and classify support tickets"""
        tickets = self._parse_tickets(tickets_content)

        for ticket in tickets:
            ticket = self._classify_ticket(ticket)
            ticket.suggested_reply = self._generate_ticket_reply(ticket)

        return tickets

    def _parse_tickets(self, content: str) -> List[SupportTicket]:
        """Parse tickets from various formats"""
        tickets = []

        # Try JSON format first (use Rust-accelerated parsing if available)
        try:
            if USE_RUST_CORE:
                try:
                    data = fast_json_parse(content)
                except Exception as e:
                    logger.debug(f"Rust JSON parse failed, using Python: {e}")
                    data = json.loads(content)
            else:
                data = json.loads(content)

            if isinstance(data, list):
                for item in data:
                    tickets.append(SupportTicket(
                        id=str(item.get('id', len(tickets))),
                        customer=item.get('customer', item.get('email', '')),
                        subject=item.get('subject', ''),
                        body=item.get('body', item.get('message', item.get('content', '')))
                    ))
                return tickets
        except json.JSONDecodeError:
            pass

        # Try parsing as text blocks
        blocks = re.split(r'\n(?=Ticket|ID:|#\d+|---)', content)
        for i, block in enumerate(blocks):
            if not block.strip():
                continue

            id_match = re.search(r'(?:Ticket|ID|#)\s*:?\s*(\d+)', block, re.I)
            customer_match = re.search(r'(?:Customer|From|Email)\s*:?\s*(.+?)(?:\n|$)', block, re.I)
            subject_match = re.search(r'Subject\s*:?\s*(.+?)(?:\n|$)', block, re.I)

            # Body is the rest
            body = re.sub(r'^.*?(?:\n\n|\n(?=[A-Z]))', '', block, flags=re.S)

            tickets.append(SupportTicket(
                id=id_match.group(1) if id_match else str(i),
                customer=customer_match.group(1).strip() if customer_match else "",
                subject=subject_match.group(1).strip() if subject_match else "",
                body=body.strip()
            ))

        return tickets

    def _classify_ticket(self, ticket: SupportTicket) -> SupportTicket:
        """Classify ticket category, priority, and sentiment"""
        text = (ticket.subject + " " + ticket.body).lower()

        # Category classification
        category_keywords = {
            'billing': ['bill', 'charge', 'payment', 'invoice', 'refund', 'subscription', 'cancel', 'price'],
            'technical': ['error', 'bug', 'crash', 'not working', 'broken', 'issue', 'problem', 'cant', "can't", 'failed'],
            'feature_request': ['feature', 'suggestion', 'would be nice', 'wish', 'could you add', 'request'],
            'complaint': ['frustrated', 'angry', 'disappointed', 'terrible', 'worst', 'unacceptable'],
            'general': ['question', 'how do i', 'help', 'information', 'where can i']
        }

        for category, keywords in category_keywords.items():
            if any(k in text for k in keywords):
                ticket.category = category
                break
        else:
            ticket.category = 'general'

        # Sentiment analysis
        negative_words = ['angry', 'frustrated', 'terrible', 'awful', 'worst', 'hate', 'unacceptable', 'ridiculous']
        positive_words = ['thanks', 'great', 'love', 'excellent', 'amazing', 'helpful', 'appreciate']

        neg_count = sum(1 for w in negative_words if w in text)
        pos_count = sum(1 for w in positive_words if w in text)

        if neg_count > pos_count + 1:
            ticket.sentiment = 'angry' if neg_count > 2 else 'negative'
        elif pos_count > neg_count:
            ticket.sentiment = 'positive'
        else:
            ticket.sentiment = 'neutral'

        # Priority
        urgent_keywords = ['urgent', 'asap', 'immediately', 'critical', 'emergency', 'down', 'blocked']
        if any(k in text for k in urgent_keywords) or ticket.sentiment == 'angry':
            ticket.priority = 'high'
        elif ticket.category == 'billing' or ticket.category == 'complaint':
            ticket.priority = 'medium'

        return ticket

    def _generate_ticket_reply(self, ticket: SupportTicket) -> str:
        """Generate suggested reply based on ticket classification"""
        templates = {
            ('billing', 'angry'): """Hi {customer},

I sincerely apologize for the billing issue you've experienced. I understand how frustrating this must be.

I've escalated this to our billing team for immediate review. You can expect a resolution within 24 hours.

If you have any specific transaction IDs or dates, please share them so we can investigate faster.

We truly value your business and are committed to making this right.

Best regards""",

            ('billing', 'neutral'): """Hi {customer},

Thank you for reaching out about your billing inquiry.

I'd be happy to help you with this. Could you please provide:
- Your account email or ID
- The specific charge or invoice in question

Once I have these details, I can look into this right away.

Best regards""",

            ('technical', 'angry'): """Hi {customer},

I'm sorry you're experiencing technical difficulties. I understand how disruptive this can be.

Our team is treating this as a priority. To help resolve this quickly, could you please share:
- Steps to reproduce the issue
- Any error messages you're seeing
- Your browser/device information

We're committed to getting this fixed for you ASAP.

Best regards""",

            ('technical', 'neutral'): """Hi {customer},

Thank you for reporting this issue. I'd like to help you resolve it.

To investigate further, could you please provide:
- Steps to reproduce the issue
- Screenshots if available
- Your browser and operating system

I'll look into this and get back to you shortly.

Best regards""",

            ('feature_request', 'neutral'): """Hi {customer},

Thank you for your feature suggestion! We really appreciate customers who take the time to share ideas.

I've logged your request and shared it with our product team. While I can't guarantee a timeline, customer feedback like yours directly influences our roadmap.

Is there anything else I can help you with in the meantime?

Best regards""",

            ('complaint', 'angry'): """Hi {customer},

I'm truly sorry about your experience. This is not the level of service we strive to provide.

I'd like to personally look into this and make it right. Could you share more details about what happened?

Your satisfaction is important to us, and I'm committed to resolving this issue.

Best regards""",
        }

        # Find best matching template
        key = (ticket.category, ticket.sentiment)
        if key not in templates:
            key = (ticket.category, 'neutral')
        if key not in templates:
            key = ('general', 'neutral')
            templates[key] = """Hi {customer},

Thank you for contacting us. I'd be happy to help you with your inquiry.

Could you please provide more details so I can assist you better?

Best regards"""

        return templates[key].format(customer=ticket.customer.split('@')[0] or 'there')

    # ========================================================================
    # G) CONTRACT EXTRACTION
    # ========================================================================

    def extract_contract_entities(self, content: str) -> ContractEntity:
        """Extract key entities from contract text"""
        # Extract parties
        parties = self._extract_parties(content)

        # Extract dates
        effective_date, expiration_date = self._extract_contract_dates(content)

        # Extract dollar amounts
        amounts = self._extract_dollar_amounts(content)

        # Extract obligations
        obligations = self._extract_obligations(content)

        # Extract key terms
        key_terms = self._extract_key_terms(content)

        return ContractEntity(
            parties=parties,
            effective_date=effective_date,
            expiration_date=expiration_date,
            dollar_amounts=amounts,
            obligations=obligations,
            key_terms=key_terms
        )

    def _extract_parties(self, content: str) -> List[str]:
        """Extract party names from contract"""
        parties = []

        # Common patterns
        patterns = [
            r'between\s+([A-Z][A-Za-z\s,]+(?:Inc\.|LLC|Corp\.|Ltd\.)?)(?:\s+\(|,|\s+and)',
            r'(?:Party|Parties):\s*([A-Z][A-Za-z\s,]+)',
            r'(?:hereinafter|")\s*([A-Z][a-z]+)"',
            r'([A-Z][A-Za-z\s]+(?:Inc\.|LLC|Corp\.|Ltd\.))',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, content)
            parties.extend(m.strip() for m in matches if m.strip())

        # Deduplicate
        return list(dict.fromkeys(parties))[:10]

    def _extract_contract_dates(self, content: str) -> Tuple[str, str]:
        """Extract effective and expiration dates"""
        effective = ""
        expiration = ""

        # Effective date patterns
        eff_patterns = [
            r'effective\s+(?:date|as of)[:\s]+([A-Za-z]+\s+\d{1,2},?\s+\d{4})',
            r'(?:dated|entered into)[:\s]+([A-Za-z]+\s+\d{1,2},?\s+\d{4})',
            r'effective[:\s]+(\d{1,2}/\d{1,2}/\d{4})',
        ]

        for pattern in eff_patterns:
            match = re.search(pattern, content, re.I)
            if match:
                effective = match.group(1)
                break

        # Expiration patterns
        exp_patterns = [
            r'(?:expires?|expiration|termination)\s+(?:date)?[:\s]+([A-Za-z]+\s+\d{1,2},?\s+\d{4})',
            r'(?:until|through)[:\s]+([A-Za-z]+\s+\d{1,2},?\s+\d{4})',
            r'term\s+of\s+(\d+)\s+(?:months?|years?)',
        ]

        for pattern in exp_patterns:
            match = re.search(pattern, content, re.I)
            if match:
                expiration = match.group(1)
                break

        return effective, expiration

    def _extract_dollar_amounts(self, content: str) -> List[Dict[str, Any]]:
        """Extract all dollar amounts with context"""
        amounts = []

        # Find dollar amounts
        pattern = r'(\$[\d,]+(?:\.\d{2})?|\d+(?:,\d{3})*(?:\.\d{2})?\s*(?:dollars?|USD))'

        for match in re.finditer(pattern, content, re.I):
            amount_str = match.group(1)

            # Get context (surrounding text)
            start = max(0, match.start() - 50)
            end = min(len(content), match.end() + 50)
            context = content[start:end].strip()

            # Parse amount
            amount_num = re.sub(r'[^\d.]', '', amount_str.split()[0])
            try:
                amount_num = float(amount_num)
            except ValueError:
                amount_num = 0

            # Determine purpose
            purpose = "unspecified"
            context_lower = context.lower()
            if 'payment' in context_lower or 'fee' in context_lower:
                purpose = "payment/fee"
            elif 'penalty' in context_lower or 'damage' in context_lower:
                purpose = "penalty/damages"
            elif 'deposit' in context_lower:
                purpose = "deposit"
            elif 'total' in context_lower:
                purpose = "total"

            amounts.append({
                "amount": amount_num,
                "raw": amount_str,
                "purpose": purpose,
                "context": context
            })

        return amounts

    def _extract_obligations(self, content: str) -> List[str]:
        """Extract party obligations"""
        obligations = []

        # Patterns for obligation language
        patterns = [
            r'(?:shall|must|agrees? to|will|is required to)\s+([^.;]+)',
            r'(?:responsible for|obligated to)\s+([^.;]+)',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, content, re.I)
            obligations.extend(m.strip()[:200] for m in matches if len(m.strip()) > 10)

        return obligations[:20]  # Top 20

    def _extract_key_terms(self, content: str) -> List[str]:
        """Extract key contract terms"""
        terms = []

        # Look for defined terms (capitalized or in quotes)
        defined = re.findall(r'"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)"', content)
        terms.extend(defined)

        # Look for section headers
        sections = re.findall(r'(?:^|\n)\s*\d+\.?\s*([A-Z][A-Z\s]+)(?:\n|:)', content)
        terms.extend(s.strip().title() for s in sections)

        return list(dict.fromkeys(terms))[:15]

    # ========================================================================
    # J) FINANCIAL TRANSACTION PROCESSING
    # ========================================================================

    def categorize_transactions(self, content: str) -> Dict[str, Any]:
        """Categorize transactions and detect anomalies"""
        transactions = self._parse_transactions(content)

        # Categorize each transaction
        for tx in transactions:
            tx.category = self._categorize_transaction(tx)

        # Detect anomalies
        transactions = self._detect_anomalies(transactions)

        # Generate summary
        summary = self._generate_financial_summary(transactions)

        return {
            "transactions": [asdict(tx) for tx in transactions],
            "summary": summary
        }

    def _parse_transactions(self, content: str) -> List[Transaction]:
        """Parse transactions from CSV or text"""
        transactions = []

        # Try CSV parsing
        lines = content.strip().split('\n')
        if ',' in lines[0]:
            reader = csv.DictReader(lines)
            for row in reader:
                # Find amount field
                amount = 0
                for key in ['amount', 'Amount', 'AMOUNT', 'value', 'Value']:
                    if key in row:
                        try:
                            amount = float(re.sub(r'[^\d.-]', '', row[key]))
                        except ValueError:
                            pass
                        break

                # Find date field
                date = ""
                for key in ['date', 'Date', 'DATE', 'transaction_date']:
                    if key in row:
                        date = row[key]
                        break

                # Find description
                desc = ""
                for key in ['description', 'Description', 'DESC', 'memo', 'Memo', 'name', 'Name']:
                    if key in row:
                        desc = row[key]
                        break

                transactions.append(Transaction(
                    date=date,
                    description=desc,
                    amount=amount
                ))

        return transactions

    def _categorize_transaction(self, tx: Transaction) -> str:
        """Categorize a transaction based on description"""
        desc_lower = tx.description.lower()

        categories = {
            'payroll': ['salary', 'payroll', 'wages', 'bonus', 'commission'],
            'utilities': ['electric', 'gas', 'water', 'utility', 'power', 'internet', 'phone'],
            'rent': ['rent', 'lease', 'property'],
            'supplies': ['office', 'supplies', 'staples', 'amazon'],
            'travel': ['airline', 'hotel', 'uber', 'lyft', 'travel', 'flight'],
            'meals': ['restaurant', 'food', 'lunch', 'dinner', 'cafe', 'coffee'],
            'software': ['software', 'subscription', 'saas', 'cloud', 'aws', 'google'],
            'marketing': ['marketing', 'advertising', 'ads', 'facebook', 'google ads'],
            'professional': ['legal', 'accounting', 'consulting', 'professional'],
            'insurance': ['insurance', 'policy', 'premium'],
            'taxes': ['tax', 'irs', 'state tax'],
        }

        for category, keywords in categories.items():
            if any(k in desc_lower for k in keywords):
                return category

        return 'other'

    def _detect_anomalies(self, transactions: List[Transaction]) -> List[Transaction]:
        """Detect anomalous transactions"""
        if not transactions:
            return transactions

        amounts = [abs(tx.amount) for tx in transactions if tx.amount != 0]
        if not amounts:
            return transactions

        avg = sum(amounts) / len(amounts)

        # Calculate standard deviation
        variance = sum((a - avg) ** 2 for a in amounts) / len(amounts)
        std_dev = variance ** 0.5

        for tx in transactions:
            # Flag if more than 2 standard deviations from mean
            if abs(tx.amount) > avg + 2 * std_dev:
                tx.is_anomaly = True
                tx.anomaly_reason = f"Unusually large amount (avg: ${avg:.2f})"

            # Flag round numbers (potential manual entry)
            if tx.amount != 0 and tx.amount % 1000 == 0 and abs(tx.amount) > 5000:
                tx.is_anomaly = True
                tx.anomaly_reason = "Large round number - verify"

            # Flag duplicate descriptions on same day
            same_day_same_desc = [t for t in transactions
                                  if t.date == tx.date and t.description == tx.description]
            if len(same_day_same_desc) > 1:
                tx.is_anomaly = True
                tx.anomaly_reason = "Possible duplicate transaction"

        return transactions

    def _generate_financial_summary(self, transactions: List[Transaction]) -> Dict[str, Any]:
        """Generate monthly financial summary"""
        income = sum(tx.amount for tx in transactions if tx.amount > 0)
        expenses = sum(tx.amount for tx in transactions if tx.amount < 0)

        by_category = {}
        for tx in transactions:
            if tx.category not in by_category:
                by_category[tx.category] = 0
            by_category[tx.category] += tx.amount

        anomalies = [tx for tx in transactions if tx.is_anomaly]

        return {
            "total_income": income,
            "total_expenses": abs(expenses),
            "net": income + expenses,
            "by_category": by_category,
            "anomaly_count": len(anomalies),
            "anomalies": [
                {"description": tx.description, "amount": tx.amount, "reason": tx.anomaly_reason}
                for tx in anomalies
            ]
        }

    # ========================================================================
    # L) RESUME PROCESSING
    # ========================================================================

    def parse_resumes(self, content: str, job_requirements: Dict = None) -> List[Resume]:
        """Parse and score resumes against job requirements"""
        resumes = self._split_resumes(content)
        parsed = []

        for resume_text in resumes:
            resume = self._parse_single_resume(resume_text)
            if job_requirements:
                resume = self._score_resume(resume, job_requirements)
            parsed.append(resume)

        # Sort by fit score
        parsed.sort(key=lambda r: r.fit_score, reverse=True)
        return parsed

    def _split_resumes(self, content: str) -> List[str]:
        """Split content into individual resumes"""
        # Try common separators
        separators = [
            r'\n(?=RESUME|Resume|---+|===+|Name:|CANDIDATE)',
            r'\f',  # Form feed
        ]

        for sep in separators:
            parts = re.split(sep, content)
            if len(parts) > 1:
                return [p.strip() for p in parts if p.strip()]

        return [content]

    def _parse_single_resume(self, text: str) -> Resume:
        """Parse a single resume"""
        # Extract email (use Rust acceleration if available)
        if USE_RUST_CORE:
            try:
                emails = rust_extract_emails(text)
                email = emails[0] if emails else ""
            except Exception as e:
                logger.debug(f"Rust email extraction failed: {e}")
                email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
                email = email_match.group(0) if email_match else ""
        else:
            email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
            email = email_match.group(0) if email_match else ""

        # Extract phone (use Rust acceleration if available)
        if USE_RUST_CORE:
            try:
                phones = rust_extract_phones(text)
                phone = phones[0] if phones else ""
            except Exception as e:
                logger.debug(f"Rust phone extraction failed: {e}")
                phone_match = re.search(r'[\+]?[(]?[0-9]{1,3}[)]?[-\s\.]?[0-9]{3}[-\s\.]?[0-9]{4,6}', text)
                phone = phone_match.group(0) if phone_match else ""
        else:
            phone_match = re.search(r'[\+]?[(]?[0-9]{1,3}[)]?[-\s\.]?[0-9]{3}[-\s\.]?[0-9]{4,6}', text)
            phone = phone_match.group(0) if phone_match else ""

        # Extract name (usually first line or after "Name:")
        name_match = re.search(r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)', text, re.M)
        name = name_match.group(1) if name_match else ""

        # Extract skills
        skills = self._extract_skills(text)

        # Calculate experience
        experience = self._calculate_experience(text)

        # Extract education
        education = self._extract_education(text)

        # Extract job titles
        titles = self._extract_job_titles(text)

        return Resume(
            name=name,
            email=email,
            phone=phone,
            skills=skills,
            experience_years=experience,
            education=education,
            job_titles=titles,
            fit_reasons=[]
        )

    def _extract_skills(self, text: str) -> List[str]:
        """Extract skills from resume"""
        skills = []

        # Common tech skills
        tech_skills = [
            'python', 'javascript', 'java', 'c++', 'sql', 'aws', 'azure', 'docker',
            'kubernetes', 'react', 'angular', 'vue', 'node', 'django', 'flask',
            'machine learning', 'data science', 'ai', 'tensorflow', 'pytorch',
            'excel', 'powerpoint', 'word', 'salesforce', 'hubspot', 'sap'
        ]

        text_lower = text.lower()
        for skill in tech_skills:
            if skill in text_lower:
                skills.append(skill.title())

        # Look for skills section
        skills_section = re.search(r'(?:skills|technologies|competencies)[:\s]*([^\n]+(?:\n[^\n]+)*?)(?:\n\n|\n[A-Z])', text, re.I)
        if skills_section:
            section_skills = re.findall(r'[A-Za-z]+(?:\s+[A-Za-z]+)?', skills_section.group(1))
            skills.extend(s for s in section_skills if len(s) > 2)

        return list(dict.fromkeys(skills))[:20]

    def _calculate_experience(self, text: str) -> float:
        """Calculate years of experience"""
        # Look for explicit statement - multiple patterns
        patterns = [
            r'(\d+)\+?\s*years?\s*(?:of\s*)?experience',  # 8 years experience, 8+ years of experience
            r'(\d+)\+?\s*years?\s*(?:in\s+)',              # 8 years in software
            r'experience[:\s]+(\d+)\+?\s*years?',          # EXPERIENCE: 8 years
            r'(\d+)\+?\s*years?\s*(?:of\s+)?(?:professional|work|industry)', # 8 years professional
        ]

        for pattern in patterns:
            exp_match = re.search(pattern, text, re.I)
            if exp_match:
                return float(exp_match.group(1))

        # Calculate from job dates (year ranges like 2018-2020)
        years = re.findall(r'((?:19|20)\d{2})', text)
        if len(years) >= 2:
            years = sorted(set(int(y) for y in years))
            return years[-1] - years[0]

        return 0

    def _extract_education(self, text: str) -> str:
        """Extract highest education level"""
        education_levels = [
            ('PhD', r'ph\.?d|doctorate'),
            ('Masters', r'master|mba|m\.s\.|m\.a\.'),
            ('Bachelors', r'bachelor|b\.s\.|b\.a\.|undergraduate'),
            ('Associates', r'associate|a\.s\.|a\.a\.'),
        ]

        text_lower = text.lower()
        for level, pattern in education_levels:
            if re.search(pattern, text_lower):
                return level

        return "Not specified"

    def _extract_job_titles(self, text: str) -> List[str]:
        """Extract job titles from resume"""
        titles = []

        # Common title patterns
        title_patterns = [
            r'(?:^|\n)([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*(?:at|@|-)',
            r'(?:Position|Title|Role)[:\s]+([A-Za-z\s]+)',
        ]

        for pattern in title_patterns:
            matches = re.findall(pattern, text)
            titles.extend(m.strip() for m in matches)

        return list(dict.fromkeys(titles))[:5]

    def _score_resume(self, resume: Resume, requirements: Dict) -> Resume:
        """Score resume against job requirements"""
        score = 0
        reasons = []

        # Required skills match
        req_skills = requirements.get('required_skills', [])
        matched_skills = [s for s in resume.skills if any(r.lower() in s.lower() for r in req_skills)]
        skill_score = len(matched_skills) / max(len(req_skills), 1) * 40
        score += skill_score
        if matched_skills:
            reasons.append(f"Matched skills: {', '.join(matched_skills)}")

        # Experience match
        min_exp = requirements.get('min_experience', 0)
        if resume.experience_years >= min_exp:
            score += 30
            reasons.append(f"Meets experience requirement ({resume.experience_years} years)")
        elif resume.experience_years >= min_exp * 0.7:
            score += 15
            reasons.append(f"Close to experience requirement ({resume.experience_years} years)")

        # Education match
        req_education = requirements.get('education', '')
        education_rank = {'PhD': 4, 'Masters': 3, 'Bachelors': 2, 'Associates': 1}
        if education_rank.get(resume.education, 0) >= education_rank.get(req_education, 0):
            score += 20
            reasons.append(f"Education: {resume.education}")

        # Nice-to-have skills
        nice_skills = requirements.get('nice_to_have', [])
        nice_matched = [s for s in resume.skills if any(n.lower() in s.lower() for n in nice_skills)]
        if nice_matched:
            score += min(len(nice_matched) * 5, 10)
            reasons.append(f"Bonus skills: {', '.join(nice_matched)}")

        resume.fit_score = min(score, 100)
        resume.fit_reasons = reasons
        return resume

    # ========================================================================
    # O) LOG FILE PROCESSING
    # ========================================================================

    def analyze_logs(self, content: str) -> Dict[str, Any]:
        """Analyze log files for errors and patterns"""
        entries = self._parse_log_entries(content)

        # Aggregate errors
        error_summary = self._summarize_errors(entries)

        # Detect patterns
        patterns = self._detect_log_patterns(entries)

        # Generate Jira tickets
        tickets = self._generate_jira_tickets(error_summary)

        return {
            "total_entries": len(entries),
            "by_level": self._count_by_level(entries),
            "error_summary": error_summary,
            "patterns": patterns,
            "suggested_jira_tickets": tickets
        }

    def _parse_log_entries(self, content: str) -> List[LogEntry]:
        """Parse log file into entries"""
        entries = []

        # Common log patterns
        patterns = [
            # Standard: 2024-01-15 10:30:45 ERROR [module] message
            r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(ERROR|WARN|INFO|DEBUG)\s+\[?([^\]]*)\]?\s*(.*)',
            # Simple: ERROR: message
            r'()(ERROR|WARN|WARNING|INFO|DEBUG)[:\s]+()(.*)',
        ]

        for line in content.split('\n'):
            if not line.strip():
                continue

            for pattern in patterns:
                match = re.match(pattern, line, re.I)
                if match:
                    entries.append(LogEntry(
                        timestamp=match.group(1),
                        level=match.group(2).upper().replace('WARNING', 'WARN'),
                        source=match.group(3),
                        message=match.group(4).strip()
                    ))
                    break

        return entries

    def _summarize_errors(self, entries: List[LogEntry]) -> List[Dict[str, Any]]:
        """Group and count similar errors"""
        error_entries = [e for e in entries if e.level in ('ERROR', 'WARN')]

        # Group similar messages
        groups = {}
        for entry in error_entries:
            # Normalize message (remove specific values)
            normalized = re.sub(r'\d+', 'N', entry.message)
            normalized = re.sub(r'[a-f0-9-]{36}', 'UUID', normalized)
            normalized = re.sub(r'"[^"]*"', '"..."', normalized)

            key = (entry.level, normalized[:100])
            if key not in groups:
                groups[key] = {
                    'level': entry.level,
                    'message': entry.message[:200],
                    'count': 0,
                    'sources': set(),
                    'first_seen': entry.timestamp,
                    'last_seen': entry.timestamp
                }

            groups[key]['count'] += 1
            if entry.source:
                groups[key]['sources'].add(entry.source)
            if entry.timestamp:
                groups[key]['last_seen'] = entry.timestamp

        # Convert to list and sort by count
        summary = []
        for group in groups.values():
            group['sources'] = list(group['sources'])
            summary.append(group)

        summary.sort(key=lambda x: x['count'], reverse=True)
        return summary[:20]

    def _detect_log_patterns(self, entries: List[LogEntry]) -> List[Dict[str, Any]]:
        """Detect patterns in logs"""
        patterns = []

        # Error burst detection
        error_times = [e.timestamp for e in entries if e.level == 'ERROR' and e.timestamp]
        if len(error_times) > 5:
            patterns.append({
                'type': 'error_burst',
                'description': f"High error volume detected ({len(error_times)} errors)",
                'severity': 'high' if len(error_times) > 50 else 'medium'
            })

        # Recurring error detection
        error_messages = [e.message[:50] for e in entries if e.level == 'ERROR']
        if error_messages:
            most_common = Counter(error_messages).most_common(1)[0]
            if most_common[1] > 5:
                patterns.append({
                    'type': 'recurring_error',
                    'description': f"Recurring error: '{most_common[0]}...' ({most_common[1]} times)",
                    'severity': 'high'
                })

        # Source concentration
        sources = [e.source for e in entries if e.level == 'ERROR' and e.source]
        if sources:
            most_common_source = Counter(sources).most_common(1)[0]
            if most_common_source[1] > len(entries) * 0.3:
                patterns.append({
                    'type': 'source_concentration',
                    'description': f"Most errors from: {most_common_source[0]}",
                    'severity': 'medium'
                })

        return patterns

    def _generate_jira_tickets(self, error_summary: List[Dict]) -> List[Dict[str, Any]]:
        """Generate suggested Jira tickets from errors"""
        tickets = []

        for error in error_summary[:5]:  # Top 5 errors
            priority = 'High' if error['count'] > 10 else 'Medium'

            ticket = {
                'title': f"[{error['level']}] {error['message'][:60]}...",
                'type': 'Bug',
                'priority': priority,
                'description': f"""
**Error Details:**
- Message: {error['message']}
- Occurrences: {error['count']}
- Sources: {', '.join(error['sources']) or 'Unknown'}
- First seen: {error['first_seen'] or 'Unknown'}
- Last seen: {error['last_seen'] or 'Unknown'}

**Suggested Investigation:**
1. Review recent deployments
2. Check related services
3. Review error stack traces in logs

**Probable Cause:**
{self._guess_probable_cause(error['message'])}
""",
                'labels': ['auto-generated', 'log-analysis']
            }
            tickets.append(ticket)

        return tickets

    def _guess_probable_cause(self, message: str) -> str:
        """Guess probable cause from error message"""
        message_lower = message.lower()

        causes = {
            'timeout': "Network latency or service unavailability",
            'connection refused': "Target service is down or network issue",
            'null pointer': "Missing data or uninitialized variable",
            'out of memory': "Memory leak or insufficient resources",
            'permission denied': "Missing permissions or credentials",
            'not found': "Missing resource or incorrect path",
            'invalid': "Input validation failure or data corruption",
            'duplicate': "Constraint violation or race condition",
        }

        for keyword, cause in causes.items():
            if keyword in message_lower:
                return cause

        return "Requires investigation - no common pattern detected"

    def _count_by_level(self, entries: List[LogEntry]) -> Dict[str, int]:
        """Count entries by log level"""
        counts = Counter(e.level for e in entries)
        return dict(counts)

    # ========================================================================
    # UTILITY METHODS
    # ========================================================================

    def get_tools(self) -> Dict[str, Dict]:
        """Return tool definitions for MCP-style interface"""
        return {
            # A) Email
            "process_emails": {
                "description": "Parse inbox emails, summarize, identify action items, and draft replies",
                "parameters": {"content": {"type": "string", "description": "Email content (raw or formatted)"}}
            },
            # B) Spreadsheet
            "clean_spreadsheet": {
                "description": "Clean and normalize messy spreadsheet data, output structured CSV",
                "parameters": {"content": {"type": "string", "description": "CSV/spreadsheet content"}}
            },
            # C) Support tickets
            "classify_tickets": {
                "description": "Classify support tickets by category, priority, sentiment and draft replies",
                "parameters": {"content": {"type": "string", "description": "Support ticket content"}}
            },
            # G) Contract extraction
            "extract_contract": {
                "description": "Extract parties, dates, amounts, obligations from contract text",
                "parameters": {"content": {"type": "string", "description": "Contract text"}}
            },
            # J) Financial
            "process_transactions": {
                "description": "Categorize transactions, detect anomalies, generate monthly summary",
                "parameters": {"content": {"type": "string", "description": "Transaction data (CSV)"}}
            },
            # L) Resumes
            "analyze_resumes": {
                "description": "Parse resumes, extract skills/experience, score against job requirements",
                "parameters": {
                    "content": {"type": "string", "description": "Resume content"},
                    "requirements": {"type": "object", "description": "Job requirements for scoring"}
                }
            },
            # O) Logs
            "analyze_logs": {
                "description": "Analyze log files, summarize errors, detect patterns, generate Jira tickets",
                "parameters": {"content": {"type": "string", "description": "Log file content"}}
            }
        }

    async def call_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a document processing tool"""
        content = params.get('content', '')

        if tool_name == "process_emails":
            emails = self.parse_emails(content)
            emails = self.draft_email_replies(emails)
            summary = self.summarize_inbox(emails)
            return {
                "success": True,
                "summary": summary,
                "emails": [asdict(e) for e in emails]
            }

        elif tool_name == "clean_spreadsheet":
            return self.clean_spreadsheet(content)

        elif tool_name == "classify_tickets":
            tickets = self.classify_tickets(content)
            return {
                "success": True,
                "tickets": [asdict(t) for t in tickets]
            }

        elif tool_name == "extract_contract":
            entities = self.extract_contract_entities(content)
            return {"success": True, **asdict(entities)}

        elif tool_name == "process_transactions":
            return self.categorize_transactions(content)

        elif tool_name == "analyze_resumes":
            requirements = params.get('requirements', {})
            resumes = self.parse_resumes(content, requirements)
            return {
                "success": True,
                "resumes": [asdict(r) for r in resumes],
                "comparison_table": self._generate_comparison_table(resumes)
            }

        elif tool_name == "analyze_logs":
            return self.analyze_logs(content)

        else:
            return {"error": f"Unknown tool: {tool_name}"}

    def _generate_comparison_table(self, resumes: List[Resume]) -> str:
        """Generate markdown comparison table for resumes"""
        if not resumes:
            return ""

        headers = ["Name", "Experience", "Education", "Skills", "Fit Score"]
        rows = []

        for r in resumes:
            rows.append([
                r.name,
                f"{r.experience_years} years",
                r.education,
                ", ".join(r.skills[:5]),
                f"{r.fit_score:.0f}%"
            ])

        # Generate markdown table
        table = "| " + " | ".join(headers) + " |\n"
        table += "| " + " | ".join(["---"] * len(headers)) + " |\n"
        for row in rows:
            table += "| " + " | ".join(str(c) for c in row) + " |\n"

        return table
