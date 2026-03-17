"""
Eversale Capabilities A-AE

All 31 business capabilities wired up and ready to use.

A) Admin - Inbox triage and reply drafting
B) Back-office - Spreadsheet cleaning/normalization
C) Customer Operations - Ticket classification and replies
D) Sales/SDR - Research, contacts, outbound emails
E) E-commerce - Product descriptions from images/specs
F) Real Estate - Report summaries, MLS listings
G) Legal/Admin - Contract extraction
H) Logistics - Shipping updates and delay detection
I) Industrial - Maintenance log analysis
J) Finance - Transaction categorization
K) Marketing - Analytics insights
L) HR/Recruiting - Resume comparison
M) Education - Quiz generation
N) Government - PDF form extraction
O) IT/Engineering - Log summarization
P) Insurance - Claims processing, policy comparison
Q) Banking - Account monitoring, fraud detection
R) Procurement - Vendor research, RFP analysis
S-AE) Extended workflows (route to ReAct)
"""

import json
import asyncio
from typing import Dict, List, Any, Optional, Union
from pathlib import Path
from dataclasses import dataclass
from loguru import logger

from .file_input import FileReader, read_file, read_csv, parse_emails, parse_logs, FileContent
from .text_processing import TextProcessor, processor
from .output_generators import (
    table_gen, json_gen, report_gen, quiz_gen, finance_gen,
    make_table, make_report, make_quiz, save_json
)
from .output_path import get_output_folder, save_output, save_csv


@dataclass
class CapabilityResult:
    """Result from a capability."""
    success: bool
    output: str  # Human-readable output
    data: Any = None  # Structured data
    files_created: List[str] = None
    error: str = ""


class Capabilities:
    """All 15 Eversale capabilities."""

    def __init__(self, model: str = "llama3.1:8b-instruct-q8_0"):
        self.file_reader = FileReader()
        self.processor = TextProcessor(model=model)

    # =========== A) ADMIN ===========

    def admin_triage_inbox(self, emails: Union[str, List[Dict]]) -> CapabilityResult:
        """
        A) Triage inbox - categorize emails and draft replies.

        Args:
            emails: Raw email text or list of email dicts
        """
        try:
            # Parse emails if string
            if isinstance(emails, str):
                email_list = parse_emails(emails)
            else:
                email_list = emails

            if not email_list:
                return CapabilityResult(success=False, output="", error="No emails found")

            results = []
            for email in email_list:
                # Classify priority
                email_text = f"From: {email.get('from', '')}\nSubject: {email.get('subject', '')}\n{email.get('body', '')}"

                priority_result = self.processor.classify_priority(email_text)
                priority = priority_result.data.get("category", "medium") if priority_result.success else "medium"

                # Classify action needed
                action_result = self.processor.classify(
                    email_text,
                    ["needs_reply", "needs_action", "fyi_only", "spam"]
                )
                action = action_result.data.get("category", "fyi_only") if action_result.success else "fyi_only"

                # Draft reply if needed
                draft = ""
                if action in ["needs_reply", "needs_action"]:
                    reply_result = self.processor.draft_reply(email_text)
                    if reply_result.success:
                        draft = reply_result.data.get("reply", "")

                results.append({
                    "from": email.get("from", ""),
                    "subject": email.get("subject", ""),
                    "priority": priority,
                    "action": action,
                    "draft_reply": draft[:500] if draft else ""
                })

            # Generate output
            output_lines = [f"## Inbox Triage ({len(results)} emails)\n"]

            # Sort by priority
            priority_order = {"high": 0, "medium": 1, "low": 2}
            results.sort(key=lambda x: priority_order.get(x["priority"], 1))

            for r in results:
                priority_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(r["priority"], "⚪")
                output_lines.append(f"{priority_icon} **{r['subject']}** (from: {r['from']})")
                output_lines.append(f"   Action: {r['action']}")
                if r["draft_reply"]:
                    output_lines.append(f"   Draft: {r['draft_reply'][:100]}...")
                output_lines.append("")

            return CapabilityResult(
                success=True,
                output="\n".join(output_lines),
                data=results
            )

        except Exception as e:
            logger.error(f"Admin triage failed: {e}")
            return CapabilityResult(success=False, output="", error=str(e))

    # =========== B) BACK-OFFICE ===========

    def backoffice_clean_spreadsheet(self, file_path: str) -> CapabilityResult:
        """
        B) Clean and normalize a messy spreadsheet.

        Args:
            file_path: Path to CSV/Excel file
        """
        try:
            content = self.file_reader.read(file_path)

            if not content.rows:
                return CapabilityResult(success=False, output="", error="No data found in file")

            # Analyze and clean
            cleaned_rows = []
            issues_found = []

            for i, row in enumerate(content.rows):
                cleaned_row = {}
                for key, value in row.items():
                    # Normalize key
                    clean_key = key.strip().lower().replace(" ", "_")

                    # Clean value
                    clean_value = str(value).strip() if value else ""

                    # Normalize common formats
                    if clean_value:
                        # Normalize phone numbers
                        if "phone" in clean_key:
                            digits = ''.join(c for c in clean_value if c.isdigit())
                            if len(digits) == 10:
                                clean_value = f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
                                if clean_value != str(value).strip():
                                    issues_found.append(f"Row {i+1}: Normalized phone number")

                        # Normalize emails
                        if "email" in clean_key:
                            clean_value = clean_value.lower()

                        # Normalize dates (basic)
                        if "date" in clean_key:
                            clean_value = clean_value.replace("/", "-")

                    cleaned_row[clean_key] = clean_value

                cleaned_rows.append(cleaned_row)

            # Remove duplicates
            seen = set()
            unique_rows = []
            for row in cleaned_rows:
                row_tuple = tuple(sorted(row.items()))
                if row_tuple not in seen:
                    seen.add(row_tuple)
                    unique_rows.append(row)
                else:
                    issues_found.append(f"Removed duplicate row")

            # Save cleaned output
            timestamp = __import__('datetime').datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"cleaned_{Path(file_path).stem}_{timestamp}.csv"
            save_csv(output_filename, unique_rows)

            output_path = get_output_folder() / output_filename

            output = f"""## Spreadsheet Cleaned

**Original rows:** {len(content.rows)}
**Cleaned rows:** {len(unique_rows)}
**Issues fixed:** {len(issues_found)}

**Changes made:**
{chr(10).join(f'- {issue}' for issue in issues_found[:10])}
{'...' if len(issues_found) > 10 else ''}

**Saved to:** {output_path}
"""

            return CapabilityResult(
                success=True,
                output=output,
                data=unique_rows,
                files_created=[str(output_path)]
            )

        except Exception as e:
            logger.error(f"Spreadsheet cleaning failed: {e}")
            return CapabilityResult(success=False, output="", error=str(e))

    # =========== C) CUSTOMER OPERATIONS ===========

    def custops_classify_tickets(self, tickets: Union[str, List[Dict]]) -> CapabilityResult:
        """
        C) Classify support tickets and draft replies.

        Args:
            tickets: Ticket text or list of ticket dicts
        """
        try:
            # Parse if string
            if isinstance(tickets, str):
                # Split by common separators
                parts = tickets.split("---")
                ticket_list = [{"id": i+1, "content": p.strip()} for i, p in enumerate(parts) if p.strip()]
            else:
                ticket_list = tickets

            categories = ["billing", "technical", "account", "feature_request", "complaint", "general"]

            results = []
            for ticket in ticket_list:
                content = ticket.get("content", ticket.get("body", str(ticket)))

                # Classify
                cat_result = self.processor.classify(content, categories)
                category = cat_result.data.get("category", "general") if cat_result.success else "general"

                # Classify urgency
                urgency_result = self.processor.classify_priority(content)
                urgency = urgency_result.data.get("category", "medium") if urgency_result.success else "medium"

                # Draft reply
                reply_result = self.processor.draft_reply(content, tone="professional")
                draft = reply_result.data.get("reply", "") if reply_result.success else ""

                results.append({
                    "id": ticket.get("id", ""),
                    "category": category,
                    "urgency": urgency,
                    "summary": content[:100],
                    "draft_reply": draft
                })

            # Generate output
            output_lines = [f"## Ticket Classification ({len(results)} tickets)\n"]

            # Group by category
            by_category = {}
            for r in results:
                cat = r["category"]
                if cat not in by_category:
                    by_category[cat] = []
                by_category[cat].append(r)

            for cat, items in by_category.items():
                output_lines.append(f"### {cat.upper()} ({len(items)})")
                for item in items:
                    urgency_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(item["urgency"], "⚪")
                    output_lines.append(f"{urgency_icon} Ticket #{item['id']}: {item['summary'][:50]}...")
                output_lines.append("")

            return CapabilityResult(
                success=True,
                output="\n".join(output_lines),
                data=results
            )

        except Exception as e:
            logger.error(f"Ticket classification failed: {e}")
            return CapabilityResult(success=False, output="", error=str(e))

    # =========== D) SALES/SDR ===========

    def sales_research_company(self, company_name: str, additional_info: str = "") -> CapabilityResult:
        """
        D) Research a company and generate outreach.

        Args:
            company_name: Company to research
            additional_info: Any additional context
        """
        try:
            # Use LLM for research synthesis
            prompt = f"""Research this company and provide key information:

Company: {company_name}
{f'Additional context: {additional_info}' if additional_info else ''}

Provide:
1. Company overview (what they do)
2. Likely decision makers (titles)
3. Potential pain points
4. Personalized outreach angle

Return JSON: {{
    "company": "{company_name}",
    "overview": "what they do",
    "industry": "industry",
    "decision_makers": ["CEO", "CTO", "VP Sales"],
    "pain_points": ["pain1", "pain2"],
    "outreach_angle": "how to approach them",
    "email_subject": "suggested subject line",
    "email_body": "draft cold email"
}}"""

            response = self.processor._call_llm(prompt)
            data = self.processor._parse_json(response)

            if not data:
                data = {
                    "company": company_name,
                    "overview": "Research needed",
                    "email_body": response
                }

            output = f"""## Company Research: {company_name}

**Overview:** {data.get('overview', 'N/A')}
**Industry:** {data.get('industry', 'N/A')}

**Decision Makers:**
{chr(10).join(f'- {dm}' for dm in data.get('decision_makers', []))}

**Pain Points:**
{chr(10).join(f'- {pp}' for pp in data.get('pain_points', []))}

**Outreach Angle:** {data.get('outreach_angle', 'N/A')}

---

**Draft Email:**
Subject: {data.get('email_subject', 'N/A')}

{data.get('email_body', 'N/A')}
"""

            return CapabilityResult(
                success=True,
                output=output,
                data=data
            )

        except Exception as e:
            logger.error(f"Company research failed: {e}")
            return CapabilityResult(success=False, output="", error=str(e))

    # =========== E) E-COMMERCE ===========

    def ecommerce_product_description(
        self,
        product_name: str,
        specs: Dict = None,
        image_path: str = None
    ) -> CapabilityResult:
        """
        E) Create product description from specs/images.

        Args:
            product_name: Product name
            specs: Product specifications dict
            image_path: Optional product image
        """
        try:
            # Build context
            context = f"Product: {product_name}\n"
            if specs:
                context += f"Specifications:\n{json.dumps(specs, indent=2)}\n"

            # Use vision model to analyze product image
            if image_path:
                try:
                    from .vision_analyzer import VisionAnalyzer
                    vision = VisionAnalyzer()
                    vision_result = vision.analyze_product(image_path)

                    if vision_result.success:
                        context += f"\n**Image Analysis:**\n{vision_result.description}\n"
                        if vision_result.details:
                            keywords = vision_result.details.get('keywords', [])
                            if keywords:
                                context += f"Detected keywords: {', '.join(keywords[:10])}\n"
                    else:
                        context += f"[Image provided but analysis failed: {image_path}]\n"
                except Exception as e:
                    logger.warning(f"Vision analysis skipped: {e}")
                    context += f"[Product image provided: {image_path}]\n"

            prompt = f"""{context}

Create e-commerce content for this product:

Return JSON: {{
    "title": "SEO-optimized product title",
    "short_description": "1-2 sentence hook",
    "bullet_points": ["feature 1", "feature 2", "feature 3", "feature 4", "feature 5"],
    "full_description": "2-3 paragraph product description",
    "faq": [
        {{"question": "Q1?", "answer": "A1"}},
        {{"question": "Q2?", "answer": "A2"}},
        {{"question": "Q3?", "answer": "A3"}}
    ],
    "meta_description": "SEO meta description under 160 chars",
    "keywords": ["keyword1", "keyword2", "keyword3"]
}}"""

            response = self.processor._call_llm(prompt)
            data = self.processor._parse_json(response)

            if not data:
                return CapabilityResult(success=False, output="", error="Failed to generate product content")

            output = f"""## Product Content: {product_name}

**Title:** {data.get('title', product_name)}

**Short Description:**
{data.get('short_description', '')}

**Key Features:**
{chr(10).join(f'• {bp}' for bp in data.get('bullet_points', []))}

**Full Description:**
{data.get('full_description', '')}

**FAQ:**
{chr(10).join(f"Q: {faq['question']}{chr(10)}A: {faq['answer']}{chr(10)}" for faq in data.get('faq', []))}

**SEO:**
- Meta: {data.get('meta_description', '')}
- Keywords: {', '.join(data.get('keywords', []))}
"""

            return CapabilityResult(
                success=True,
                output=output,
                data=data
            )

        except Exception as e:
            logger.error(f"Product description failed: {e}")
            return CapabilityResult(success=False, output="", error=str(e))

    # =========== F) REAL ESTATE ===========

    def realestate_summarize_report(self, report_path: str) -> CapabilityResult:
        """
        F) Summarize inspection report and create MLS listing.

        Args:
            report_path: Path to inspection report (PDF/text)
        """
        try:
            content = self.file_reader.read(report_path)

            # Summarize for real estate
            summary_result = self.processor.summarize_for_domain(content.text, "real_estate")

            if not summary_result.success:
                return CapabilityResult(success=False, output="", error="Failed to summarize report")

            summary_data = summary_result.data

            # Generate MLS listing
            listing_prompt = f"""Based on this property inspection summary, create an MLS listing description:

{json.dumps(summary_data, indent=2)}

Return JSON: {{
    "headline": "Attention-grabbing headline",
    "description": "MLS listing description (2-3 paragraphs)",
    "highlights": ["highlight1", "highlight2", "highlight3"],
    "disclosures": ["any issues to disclose"]
}}"""

            listing_response = self.processor._call_llm(listing_prompt)
            listing_data = self.processor._parse_json(listing_response)

            output = f"""## Property Report Summary

**Summary:**
{summary_data.get('summary', 'N/A')}

**Key Findings:**
{chr(10).join(f'- {f}' for f in summary_data.get('key_findings', []))}

**Concerns:**
{chr(10).join(f'- {c}' for c in summary_data.get('concerns', []))}

---

## MLS Listing Draft

**Headline:** {listing_data.get('headline', 'N/A') if listing_data else 'N/A'}

**Description:**
{listing_data.get('description', 'N/A') if listing_data else 'N/A'}

**Highlights:**
{chr(10).join(f'• {h}' for h in listing_data.get('highlights', [])) if listing_data else 'N/A'}
"""

            return CapabilityResult(
                success=True,
                output=output,
                data={"summary": summary_data, "listing": listing_data}
            )

        except Exception as e:
            logger.error(f"Real estate report failed: {e}")
            return CapabilityResult(success=False, output="", error=str(e))

    # =========== G) LEGAL/ADMIN ===========

    def legal_extract_contract(self, contract_path: str) -> CapabilityResult:
        """
        G) Extract parties, dates, amounts from contract.

        Args:
            contract_path: Path to contract (PDF/text)
        """
        try:
            content = self.file_reader.read(contract_path)

            # Extract key fields
            fields = [
                "parties", "effective_date", "termination_date",
                "total_value", "payment_terms", "key_obligations",
                "termination_clause", "governing_law"
            ]

            extract_result = self.processor.extract_fields(content.text, fields)

            if not extract_result.success:
                return CapabilityResult(success=False, output="", error="Failed to extract contract data")

            data = extract_result.data

            # Also extract entities
            entity_result = self.processor.extract_entities(content.text, ["person", "organization", "date", "money"])
            entities = entity_result.data.get("entities", {}) if entity_result.success else {}

            # Generate structured output
            output_table = []
            for field, value in data.items():
                if value:
                    output_table.append({"Field": field.replace("_", " ").title(), "Value": str(value)[:100]})

            table_md = make_table(output_table)

            output = f"""## Contract Analysis

{table_md}

### Extracted Entities

**Organizations:** {', '.join(entities.get('organization', ['N/A']))}
**People:** {', '.join(entities.get('person', ['N/A']))}
**Dates:** {', '.join(entities.get('date', ['N/A']))}
**Amounts:** {', '.join(entities.get('money', ['N/A']))}
"""

            # Save JSON
            timestamp = __import__('datetime').datetime.now().strftime("%Y%m%d_%H%M%S")
            json_path = save_json({"fields": data, "entities": entities}, f"contract_extract_{timestamp}.json")

            return CapabilityResult(
                success=True,
                output=output,
                data={"fields": data, "entities": entities},
                files_created=[str(json_path)]
            )

        except Exception as e:
            logger.error(f"Contract extraction failed: {e}")
            return CapabilityResult(success=False, output="", error=str(e))

    # =========== H) LOGISTICS ===========

    def logistics_shipping_summary(self, updates: Union[str, List[Dict]]) -> CapabilityResult:
        """
        H) Analyze shipping updates and detect delays.

        Args:
            updates: Shipping update text or list of updates
        """
        try:
            # Parse if string
            if isinstance(updates, str):
                update_list = [{"content": updates}]
            else:
                update_list = updates

            all_content = "\n".join(u.get("content", str(u)) for u in update_list)

            # Extract shipment info
            extract_result = self.processor.extract_fields(all_content, [
                "tracking_numbers", "origins", "destinations",
                "expected_dates", "current_status", "delays"
            ])

            # Classify for delays
            delay_result = self.processor.classify(
                all_content,
                ["on_time", "minor_delay", "major_delay", "critical_delay"]
            )

            delay_status = delay_result.data.get("category", "unknown") if delay_result.success else "unknown"

            # Generate summary
            summary_result = self.processor.summarize(all_content, style="executive")
            summary = summary_result.data.get("summary", "") if summary_result.success else all_content[:500]

            # Determine next steps
            next_steps = []
            if "delay" in delay_status:
                next_steps = [
                    "Contact carrier for updated ETA",
                    "Notify affected customers",
                    "Check for alternative routing options"
                ]
            else:
                next_steps = ["Monitor for updates", "Confirm delivery on arrival"]

            output = f"""## Shipping Status Summary

**Overall Status:** {delay_status.replace('_', ' ').upper()}

**Summary:**
{summary}

**Extracted Details:**
{json.dumps(extract_result.data, indent=2) if extract_result.success else 'N/A'}

**Recommended Next Steps:**
{chr(10).join(f'- {step}' for step in next_steps)}
"""

            return CapabilityResult(
                success=True,
                output=output,
                data={"status": delay_status, "details": extract_result.data, "next_steps": next_steps}
            )

        except Exception as e:
            logger.error(f"Logistics summary failed: {e}")
            return CapabilityResult(success=False, output="", error=str(e))

    # =========== I) INDUSTRIAL ===========

    def industrial_maintenance_analysis(self, log_path: str) -> CapabilityResult:
        """
        I) Analyze maintenance logs for patterns.

        Args:
            log_path: Path to maintenance log file
        """
        try:
            content = self.file_reader.read(log_path)

            # Parse as logs
            log_data = parse_logs(content.text)

            # Use LLM for deeper analysis
            analysis_prompt = f"""Analyze these maintenance logs for patterns and issues:

{content.text[:4000]}

Return JSON: {{
    "recurring_issues": [
        {{"issue": "description", "frequency": "how often", "affected_equipment": "what"}},
    ],
    "root_causes": ["cause1", "cause2"],
    "recommendations": ["recommendation1", "recommendation2"],
    "priority_actions": ["urgent action1", "action2"],
    "patterns_detected": "summary of patterns"
}}"""

            analysis_response = self.processor._call_llm(analysis_prompt)
            analysis = self.processor._parse_json(analysis_response)

            output = f"""## Maintenance Log Analysis

**Log Statistics:**
- Total entries: {log_data.get('total_lines', 0)}
- Errors: {len(log_data.get('errors', []))}
- Warnings: {len(log_data.get('warnings', []))}

**Recurring Issues:**
{chr(10).join(f"- {i['issue']} ({i.get('frequency', 'unknown')})" for i in analysis.get('recurring_issues', [])) if analysis else 'Analysis pending'}

**Root Causes:**
{chr(10).join(f"- {c}" for c in analysis.get('root_causes', [])) if analysis else 'N/A'}

**Recommendations:**
{chr(10).join(f"- {r}" for r in analysis.get('recommendations', [])) if analysis else 'N/A'}

**Priority Actions:**
{chr(10).join(f"⚠️ {a}" for a in analysis.get('priority_actions', [])) if analysis else 'N/A'}
"""

            return CapabilityResult(
                success=True,
                output=output,
                data={"log_stats": log_data, "analysis": analysis}
            )

        except Exception as e:
            logger.error(f"Maintenance analysis failed: {e}")
            return CapabilityResult(success=False, output="", error=str(e))

    # =========== J) FINANCE/ACCOUNTING ===========

    def finance_categorize_transactions(self, file_path: str) -> CapabilityResult:
        """
        J) Categorize transactions and produce summary.

        Args:
            file_path: Path to transaction CSV
        """
        try:
            rows = read_csv(file_path)

            if not rows:
                return CapabilityResult(success=False, output="", error="No transactions found")

            # Categorize each transaction
            categories = ["income", "expense_operational", "expense_payroll",
                         "expense_marketing", "expense_travel", "expense_other", "transfer"]

            categorized = []
            for row in rows:
                desc = row.get("description", row.get("memo", str(row)))
                amount = float(row.get("amount", 0))

                cat_result = self.processor.classify(desc, categories)
                category = cat_result.data.get("category", "expense_other") if cat_result.success else "expense_other"

                categorized.append({
                    **row,
                    "category": category,
                    "amount": amount
                })

            # Generate summary
            summary = finance_gen.categorize_transactions(categorized)
            report = finance_gen.generate_summary(summary)

            # Save
            timestamp = __import__('datetime').datetime.now().strftime("%Y%m%d_%H%M%S")
            report_path = save_output(f"financial_summary_{timestamp}.md", report)

            return CapabilityResult(
                success=True,
                output=report,
                data=summary,
                files_created=[str(report_path)]
            )

        except Exception as e:
            logger.error(f"Transaction categorization failed: {e}")
            return CapabilityResult(success=False, output="", error=str(e))

    # =========== K) MARKETING ===========

    def marketing_analytics_insights(self, data: Union[str, Dict, List]) -> CapabilityResult:
        """
        K) Analyze marketing data and produce insights.

        Args:
            data: Analytics data (file path, dict, or text)
        """
        try:
            # Load data if file path
            if isinstance(data, str) and Path(data).exists():
                content = self.file_reader.read(data)
                data_text = content.text
            elif isinstance(data, (dict, list)):
                data_text = json.dumps(data, indent=2)
            else:
                data_text = str(data)

            prompt = f"""Analyze this marketing data and provide insights:

{data_text[:4000]}

Return JSON: {{
    "key_metrics": {{"metric1": "value1", "metric2": "value2"}},
    "trends": ["trend1", "trend2"],
    "insights": ["insight1", "insight2", "insight3"],
    "opportunities": ["opportunity1", "opportunity2"],
    "recommended_experiments": [
        {{"name": "experiment name", "hypothesis": "what we expect", "success_metric": "how to measure"}}
    ],
    "action_items": ["action1", "action2"]
}}"""

            response = self.processor._call_llm(prompt)
            analysis = self.processor._parse_json(response)

            if not analysis:
                analysis = {"insights": [response]}

            output = f"""## Marketing Analytics Insights

**Key Metrics:**
{chr(10).join(f"- {k}: {v}" for k, v in analysis.get('key_metrics', {}).items())}

**Trends:**
{chr(10).join(f"- {t}" for t in analysis.get('trends', []))}

**Insights:**
{chr(10).join(f"💡 {i}" for i in analysis.get('insights', []))}

**Opportunities:**
{chr(10).join(f"🎯 {o}" for o in analysis.get('opportunities', []))}

**Recommended Experiments:**
{chr(10).join(f"- {e['name']}: {e.get('hypothesis', '')}" for e in analysis.get('recommended_experiments', []))}

**Action Items:**
{chr(10).join(f"☐ {a}" for a in analysis.get('action_items', []))}
"""

            return CapabilityResult(
                success=True,
                output=output,
                data=analysis
            )

        except Exception as e:
            logger.error(f"Marketing analysis failed: {e}")
            return CapabilityResult(success=False, output="", error=str(e))

    # =========== L) HR/RECRUITING ===========

    def hr_compare_resumes(self, resume_paths: List[str], job_requirements: str = "") -> CapabilityResult:
        """
        L) Compare resumes and score candidates.

        Args:
            resume_paths: List of resume file paths
            job_requirements: Job description or requirements
        """
        try:
            candidates = []

            for path in resume_paths:
                content = self.file_reader.read(path)

                # Extract key info
                extract_result = self.processor.extract_fields(content.text, [
                    "name", "email", "phone", "years_experience",
                    "education", "skills", "current_role", "companies"
                ])

                candidate_data = extract_result.data if extract_result.success else {}
                candidate_data["file"] = Path(path).name
                candidate_data["raw_text"] = content.text[:2000]

                candidates.append(candidate_data)

            # Compare candidates
            if job_requirements:
                compare_prompt = f"""Compare these candidates for the following role:

Job Requirements:
{job_requirements}

Candidates:
{json.dumps(candidates, indent=2)[:4000]}

Return JSON: {{
    "comparison": [
        {{"name": "candidate1", "strengths": ["s1"], "weaknesses": ["w1"], "fit_score": 85, "recommendation": "text"}}
    ],
    "ranking": ["best candidate", "second", "third"],
    "overall_recommendation": "who to interview first and why"
}}"""

                compare_response = self.processor._call_llm(compare_prompt)
                comparison = self.processor._parse_json(compare_response)
            else:
                comparison = self.processor.compare(candidates, ["experience", "skills", "education"])
                comparison = comparison.data if comparison.success else {}

            # Generate comparison table
            table_data = []
            for c in comparison.get("comparison", candidates):
                table_data.append({
                    "Candidate": c.get("name", c.get("file", "Unknown")),
                    "Experience": c.get("years_experience", "N/A"),
                    "Skills": str(c.get("skills", []))[:50],
                    "Fit Score": c.get("fit_score", "N/A")
                })

            table_md = make_table(table_data)

            output = f"""## Resume Comparison

{table_md}

**Ranking:**
{chr(10).join(f"{i+1}. {name}" for i, name in enumerate(comparison.get('ranking', [])))}

**Recommendation:**
{comparison.get('overall_recommendation', 'Review all candidates')}
"""

            return CapabilityResult(
                success=True,
                output=output,
                data=comparison
            )

        except Exception as e:
            logger.error(f"Resume comparison failed: {e}")
            return CapabilityResult(success=False, output="", error=str(e))

    # =========== M) EDUCATION ===========

    def education_create_quiz(self, content_path: str, num_questions: int = 10) -> CapabilityResult:
        """
        M) Create quiz, answer key, and study guide from content.

        Args:
            content_path: Path to chapter/content file
            num_questions: Number of questions to generate
        """
        try:
            content = self.file_reader.read(content_path)

            # Generate questions
            questions_result = self.processor.generate_questions(
                content.text,
                count=num_questions,
                question_type="mixed"
            )

            if not questions_result.success:
                return CapabilityResult(success=False, output="", error="Failed to generate questions")

            questions = questions_result.data.get("questions", [])

            # Generate study guide
            summary_result = self.processor.summarize(content.text, style="bullet")
            summary = summary_result.data if summary_result.success else {}

            study_guide_content = {
                "summary": summary.get("summary", ""),
                "key_points": summary.get("key_points", []),
                "questions": [q.get("question") for q in questions]
            }

            # Generate outputs
            quiz = quiz_gen.generate_quiz(questions, "Quiz")
            answer_key = quiz_gen.generate_answer_key(questions, "Answer Key")
            study_guide = quiz_gen.generate_study_guide(study_guide_content)

            # Save files
            timestamp = __import__('datetime').datetime.now().strftime("%Y%m%d_%H%M%S")
            quiz_path = save_output(f"quiz_{timestamp}.md", quiz)
            key_path = save_output(f"answer_key_{timestamp}.md", answer_key)
            guide_path = save_output(f"study_guide_{timestamp}.md", study_guide)

            output = f"""## Educational Materials Generated

**Quiz:** {num_questions} questions generated
**Answer Key:** Created
**Study Guide:** Created

### Files Created:
- {quiz_path}
- {key_path}
- {guide_path}

### Preview (First 3 Questions):
{chr(10).join(f"{i+1}. {q['question']}" for i, q in enumerate(questions[:3]))}
"""

            return CapabilityResult(
                success=True,
                output=output,
                data={"questions": questions, "study_guide": study_guide_content},
                files_created=[str(quiz_path), str(key_path), str(guide_path)]
            )

        except Exception as e:
            logger.error(f"Quiz generation failed: {e}")
            return CapabilityResult(success=False, output="", error=str(e))

    # =========== N) GOVERNMENT ===========

    def government_extract_form(self, form_path: str) -> CapabilityResult:
        """
        N) Extract fields from government form to JSON.

        Args:
            form_path: Path to government form (PDF)
        """
        try:
            content = self.file_reader.read(form_path)

            # Extract all fields
            prompt = f"""Extract ALL fields from this government form:

{content.text[:5000]}

Return JSON with field names as keys and extracted values. Include:
- Form name/number
- All labeled fields and their values
- Dates, names, addresses, IDs, amounts
- Checkboxes (true/false)
- Any signatures or certifications

Use null for empty fields. Be thorough."""

            response = self.processor._call_llm(prompt)
            data = self.processor._parse_json(response)

            if not data:
                # Fallback to entity extraction
                entity_result = self.processor.extract_entities(content.text)
                data = entity_result.data if entity_result.success else {"raw_text": content.text}

            # Save JSON
            timestamp = __import__('datetime').datetime.now().strftime("%Y%m%d_%H%M%S")
            json_path = save_json(data, f"form_extract_{timestamp}.json")

            # Generate readable output
            output_lines = ["## Government Form Extraction\n"]
            for key, value in data.items():
                if value is not None:
                    output_lines.append(f"**{key}:** {value}")

            output_lines.append(f"\n**Saved to:** {json_path}")

            return CapabilityResult(
                success=True,
                output="\n".join(output_lines),
                data=data,
                files_created=[str(json_path)]
            )

        except Exception as e:
            logger.error(f"Form extraction failed: {e}")
            return CapabilityResult(success=False, output="", error=str(e))

    # =========== O) IT/ENGINEERING ===========

    def it_summarize_logs(self, log_path: str) -> CapabilityResult:
        """
        O) Summarize log files with errors and suggested tickets.

        Args:
            log_path: Path to log file
        """
        try:
            content = self.file_reader.read(log_path)

            # Parse logs
            log_data = parse_logs(content.text)

            # Analyze with LLM
            prompt = f"""Analyze these application logs:

Errors found: {len(log_data.get('errors', []))}
Sample errors:
{chr(10).join(log_data.get('errors', [])[:10])}

Warnings: {len(log_data.get('warnings', []))}

Full log sample:
{content.text[:3000]}

Return JSON: {{
    "summary": "overall health assessment",
    "error_analysis": [
        {{"error_type": "type", "frequency": 5, "probable_cause": "why", "suggested_fix": "how"}}
    ],
    "suggested_tickets": [
        {{"title": "JIRA title", "priority": "high/medium/low", "description": "ticket description", "labels": ["bug", "backend"]}}
    ],
    "immediate_actions": ["action1", "action2"],
    "monitoring_recommendations": ["what to watch"]
}}"""

            response = self.processor._call_llm(prompt)
            analysis = self.processor._parse_json(response)

            if not analysis:
                analysis = {"summary": response}

            output = f"""## Log Analysis Summary

**Overall:** {analysis.get('summary', 'Analysis complete')}

**Statistics:**
- Total lines: {log_data.get('total_lines', 0)}
- Errors: {len(log_data.get('errors', []))}
- Warnings: {len(log_data.get('warnings', []))}

**Error Analysis:**
{chr(10).join(f"- {e['error_type']}: {e.get('probable_cause', '')} (x{e.get('frequency', 1)})" for e in analysis.get('error_analysis', []))}

**Suggested JIRA Tickets:**
{chr(10).join(f"[{t['priority'].upper()}] {t['title']}" for t in analysis.get('suggested_tickets', []))}

**Immediate Actions:**
{chr(10).join(f"⚠️ {a}" for a in analysis.get('immediate_actions', []))}

**Monitoring Recommendations:**
{chr(10).join(f"👁️ {m}" for m in analysis.get('monitoring_recommendations', []))}
"""

            return CapabilityResult(
                success=True,
                output=output,
                data={"log_stats": log_data, "analysis": analysis}
            )

        except Exception as e:
            logger.error(f"Log summarization failed: {e}")
            return CapabilityResult(success=False, output="", error=str(e))

    # =========== P-AE) EXTENDED CAPABILITIES ===========

    def insurance_process_claim(self, claim_data: str = None) -> CapabilityResult:
        """
        P) Insurance - Process claims, verify details, check for fraud.
        Uses P1_ClaimsProcessor and P2_PolicyComparator executors.
        """
        try:
            from .workflows_extended import P1_ClaimsProcessor, P2_PolicyComparator

            # Detect if comparing policies or processing claim
            if claim_data and any(word in claim_data.lower() for word in ['compare', 'policy', 'policies', 'quote']):
                executor = P2_PolicyComparator(browser=None, llm_caller=self.processor._call_llm)
                result = asyncio.run(executor.execute({"policy_type": "auto"}))
            else:
                executor = P1_ClaimsProcessor(browser=None, llm_caller=self.processor._call_llm)
                result = asyncio.run(executor.execute({"claim_data": claim_data or ""}))

            return CapabilityResult(
                success=result.status.value == "success",
                output=result.message,
                data=result.data
            )
        except Exception as e:
            logger.error(f"Insurance capability failed: {e}")
            return CapabilityResult(success=False, output="", error=str(e))

    def banking_monitor_account(self, transactions: str = None) -> CapabilityResult:
        """
        Q) Banking - Monitor accounts, detect fraud, analyze transactions.
        Uses Q1_AccountMonitor executor.
        """
        try:
            from .workflows_extended import Q1_AccountMonitor

            executor = Q1_AccountMonitor(browser=None, llm_caller=self.processor._call_llm)
            result = asyncio.run(executor.execute({"transactions": transactions or ""}))

            return CapabilityResult(
                success=result.status.value == "success",
                output=result.message,
                data=result.data
            )
        except Exception as e:
            logger.error(f"Banking capability failed: {e}")
            return CapabilityResult(success=False, output="", error=str(e))

    def procurement_research_vendors(self, product_category: str = None) -> CapabilityResult:
        """
        R) Procurement - Research vendors, compare suppliers, analyze RFPs.
        Uses R1_VendorResearcher executor.
        """
        try:
            from .workflows_extended import R1_VendorResearcher

            executor = R1_VendorResearcher(browser=None, llm_caller=self.processor._call_llm)
            result = asyncio.run(executor.execute({"product_category": product_category or ""}))

            return CapabilityResult(
                success=result.status.value == "success",
                output=result.message,
                data=result.data
            )
        except Exception as e:
            logger.error(f"Procurement capability failed: {e}")
            return CapabilityResult(success=False, output="", error=str(e))

    # S-AE: Placeholder workflows that route to ReAct loop with context

    def enterprise_admin_workflow(self) -> CapabilityResult:
        """S) Enterprise Admin - User provisioning, SaaS management, access audits."""
        return CapabilityResult(
            success=False,
            output="",
            error="enterprise_admin_workflow_needs_react"
        )

    def contractor_permit_workflow(self) -> CapabilityResult:
        """T) Contractor - Permit research, license verification, bid tracking."""
        return CapabilityResult(
            success=False,
            output="",
            error="contractor_permit_workflow_needs_react"
        )

    def recruiting_pipeline_workflow(self) -> CapabilityResult:
        """U) Recruiting - Candidate sourcing, outreach, interview scheduling."""
        return CapabilityResult(
            success=False,
            output="",
            error="recruiting_pipeline_workflow_needs_react"
        )

    def audit_compliance_workflow(self) -> CapabilityResult:
        """V) Audit & Compliance - Compliance checks, audit trails, evidence gathering."""
        return CapabilityResult(
            success=False,
            output="",
            error="audit_compliance_workflow_needs_react"
        )

    def content_moderation_workflow(self) -> CapabilityResult:
        """W) Content Moderation - Content review, policy enforcement, queue processing."""
        return CapabilityResult(
            success=False,
            output="",
            error="content_moderation_workflow_needs_react"
        )

    def inventory_reconciliation_workflow(self) -> CapabilityResult:
        """X) Inventory - Stock monitoring, reorder alerts, warehouse sync."""
        return CapabilityResult(
            success=False,
            output="",
            error="inventory_reconciliation_workflow_needs_react"
        )

    def research_automation_workflow(self) -> CapabilityResult:
        """Y) Research Automation - Literature review, citation gathering, source verification."""
        return CapabilityResult(
            success=False,
            output="",
            error="research_automation_workflow_needs_react"
        )

    def enterprise_monitoring_workflow(self) -> CapabilityResult:
        """Z) Enterprise Monitoring - Log aggregation, alert correlation, incident response."""
        return CapabilityResult(
            success=False,
            output="",
            error="enterprise_monitoring_workflow_needs_react"
        )

    def healthcare_admin_workflow(self) -> CapabilityResult:
        """AA) Healthcare - Patient lookup, insurance verification, appointment scheduling."""
        return CapabilityResult(
            success=False,
            output="",
            error="healthcare_admin_workflow_needs_react"
        )

    def travel_management_workflow(self) -> CapabilityResult:
        """AB) Travel - Flight monitoring, price alerts, itinerary building."""
        return CapabilityResult(
            success=False,
            output="",
            error="travel_management_workflow_needs_react"
        )

    def food_service_workflow(self) -> CapabilityResult:
        """AC) Food Service - Menu aggregation, supplier pricing, inventory tracking."""
        return CapabilityResult(
            success=False,
            output="",
            error="food_service_workflow_needs_react"
        )

    def nonprofit_fundraising_workflow(self) -> CapabilityResult:
        """AD) Non-Profit - Grant searching, donor research, campaign tracking."""
        return CapabilityResult(
            success=False,
            output="",
            error="nonprofit_fundraising_workflow_needs_react"
        )

    def media_pr_workflow(self) -> CapabilityResult:
        """AE) Media & PR - Press monitoring, journalist outreach, coverage tracking."""
        return CapabilityResult(
            success=False,
            output="",
            error="media_pr_workflow_needs_react"
        )


# Convenience instance
caps = Capabilities()


# Quick access functions for each capability
def admin_triage(emails): return caps.admin_triage_inbox(emails)
def backoffice_clean(file_path): return caps.backoffice_clean_spreadsheet(file_path)
def custops_tickets(tickets): return caps.custops_classify_tickets(tickets)
def sales_research(company): return caps.sales_research_company(company)
def ecommerce_product(name, specs=None): return caps.ecommerce_product_description(name, specs)
def realestate_report(path): return caps.realestate_summarize_report(path)
def legal_extract(path): return caps.legal_extract_contract(path)
def logistics_summary(updates): return caps.logistics_shipping_summary(updates)
def industrial_maintenance(path): return caps.industrial_maintenance_analysis(path)
def finance_categorize(path): return caps.finance_categorize_transactions(path)
def marketing_insights(data): return caps.marketing_analytics_insights(data)
def hr_compare(paths, job=""): return caps.hr_compare_resumes(paths, job)
def education_quiz(path, n=10): return caps.education_create_quiz(path, n)
def government_form(path): return caps.government_extract_form(path)
def it_logs(path): return caps.it_summarize_logs(path)
