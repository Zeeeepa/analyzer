"""
Output Generators - Create structured output in various formats.

Formats:
- Tables (markdown, CSV)
- JSON (structured data)
- Reports (formatted documents)
- Quiz/Study materials
"""

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
from io import StringIO
from loguru import logger

from .output_path import get_output_folder, save_output


class TableGenerator:
    """Generate tables in various formats."""

    def to_markdown(self, data: List[Dict], title: str = None) -> str:
        """Generate markdown table."""
        if not data:
            return "*No data*"

        lines = []
        if title:
            lines.append(f"## {title}\n")

        # Get headers
        headers = list(data[0].keys())

        # Header row
        lines.append("| " + " | ".join(str(h) for h in headers) + " |")
        lines.append("| " + " | ".join(["---"] * len(headers)) + " |")

        # Data rows
        for row in data:
            # Don't truncate URL fields - allow full display
            values = []
            for h in headers:
                val = str(row.get(h, ""))
                # Only truncate non-URL fields
                if h.lower() in ['url', 'source_url', 'website', 'linkedin', 'profile_url']:
                    values.append(val)  # Full URL
                else:
                    values.append(val[:80] if len(val) > 80 else val)  # Increased from 50 to 80
            lines.append("| " + " | ".join(values) + " |")

        return "\n".join(lines)

    def to_csv(self, data: List[Dict], filename: str = None) -> str:
        """Generate CSV and optionally save to file."""
        if not data:
            return ""

        output = StringIO()
        headers = list(data[0].keys())

        writer = csv.DictWriter(output, fieldnames=headers)
        writer.writeheader()
        writer.writerows(data)

        csv_content = output.getvalue()

        if filename:
            path = get_output_folder() / filename
            path.write_text(csv_content)
            logger.info(f"Saved CSV: {path}")

        return csv_content

    def to_html(self, data: List[Dict], title: str = None) -> str:
        """Generate HTML table."""
        if not data:
            return "<p>No data</p>"

        headers = list(data[0].keys())

        html = []
        if title:
            html.append(f"<h2>{title}</h2>")

        html.append('<table border="1" cellpadding="5" cellspacing="0">')

        # Header
        html.append("<tr>")
        for h in headers:
            html.append(f"<th>{h}</th>")
        html.append("</tr>")

        # Rows
        for row in data:
            html.append("<tr>")
            for h in headers:
                html.append(f"<td>{row.get(h, '')}</td>")
            html.append("</tr>")

        html.append("</table>")

        return "\n".join(html)


class JSONGenerator:
    """Generate structured JSON output."""

    def format(self, data: Any, indent: int = 2) -> str:
        """Format data as pretty JSON."""
        return json.dumps(data, indent=indent, default=str, ensure_ascii=False)

    def save(self, data: Any, filename: str) -> Path:
        """Save JSON to file."""
        content = self.format(data)
        path = get_output_folder() / filename
        path.write_text(content)
        logger.info(f"Saved JSON: {path}")
        return path


class ReportGenerator:
    """Generate formatted reports."""

    def generate(
        self,
        title: str,
        sections: List[Dict],
        metadata: Dict = None,
        format: str = "markdown"
    ) -> str:
        """
        Generate a report.

        Args:
            title: Report title
            sections: List of {"heading": str, "content": str/list}
            metadata: Optional metadata (date, author, etc.)
            format: "markdown" or "html"
        """
        if format == "html":
            return self._generate_html(title, sections, metadata)
        return self._generate_markdown(title, sections, metadata)

    def _generate_markdown(self, title: str, sections: List[Dict], metadata: Dict = None) -> str:
        """Generate markdown report."""
        lines = [f"# {title}", ""]

        # Metadata
        if metadata:
            lines.append("---")
            for key, value in metadata.items():
                lines.append(f"**{key}:** {value}")
            lines.append("---")
            lines.append("")

        lines.append(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
        lines.append("")

        # Sections
        for section in sections:
            heading = section.get("heading", "Section")
            content = section.get("content", "")

            lines.append(f"## {heading}")
            lines.append("")

            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        for k, v in item.items():
                            lines.append(f"- **{k}:** {v}")
                    else:
                        lines.append(f"- {item}")
            else:
                lines.append(str(content))

            lines.append("")

        return "\n".join(lines)

    def _generate_html(self, title: str, sections: List[Dict], metadata: Dict = None) -> str:
        """Generate HTML report."""
        html = [
            "<!DOCTYPE html>",
            "<html>",
            "<head>",
            f"<title>{title}</title>",
            "<style>",
            "body { font-family: Arial, sans-serif; max-width: 800px; margin: 40px auto; padding: 20px; }",
            "h1 { color: #333; border-bottom: 2px solid #00D4AA; padding-bottom: 10px; }",
            "h2 { color: #555; }",
            ".metadata { background: #f5f5f5; padding: 10px; border-radius: 5px; margin-bottom: 20px; }",
            "ul { line-height: 1.8; }",
            ".generated { color: #999; font-size: 0.9em; }",
            "</style>",
            "</head>",
            "<body>",
            f"<h1>{title}</h1>",
        ]

        if metadata:
            html.append('<div class="metadata">')
            for key, value in metadata.items():
                html.append(f"<strong>{key}:</strong> {value}<br>")
            html.append("</div>")

        html.append(f'<p class="generated">Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")}</p>')

        for section in sections:
            heading = section.get("heading", "Section")
            content = section.get("content", "")

            html.append(f"<h2>{heading}</h2>")

            if isinstance(content, list):
                html.append("<ul>")
                for item in content:
                    if isinstance(item, dict):
                        html.append("<li>")
                        for k, v in item.items():
                            html.append(f"<strong>{k}:</strong> {v}<br>")
                        html.append("</li>")
                    else:
                        html.append(f"<li>{item}</li>")
                html.append("</ul>")
            else:
                html.append(f"<p>{content}</p>")

        html.extend(["</body>", "</html>"])

        return "\n".join(html)

    def save(self, content: str, filename: str) -> Path:
        """Save report to file."""
        path = get_output_folder() / filename
        path.write_text(content)
        logger.info(f"Saved report: {path}")
        return path


class QuizGenerator:
    """Generate educational materials."""

    def generate_quiz(self, questions: List[Dict], title: str = "Quiz") -> str:
        """
        Generate a quiz document.

        Args:
            questions: List of question dicts with question, options, correct_answer
            title: Quiz title
        """
        lines = [f"# {title}", "", f"*{len(questions)} Questions*", ""]

        for i, q in enumerate(questions, 1):
            lines.append(f"### Question {i}")
            lines.append(q.get("question", ""))
            lines.append("")

            options = q.get("options", [])
            if options:
                for opt in options:
                    lines.append(f"- {opt}")
                lines.append("")

        return "\n".join(lines)

    def generate_answer_key(self, questions: List[Dict], title: str = "Answer Key") -> str:
        """Generate answer key."""
        lines = [f"# {title}", ""]

        for i, q in enumerate(questions, 1):
            answer = q.get("correct_answer", "N/A")
            explanation = q.get("explanation", "")

            lines.append(f"**{i}.** {answer}")
            if explanation:
                lines.append(f"   *{explanation}*")
            lines.append("")

        return "\n".join(lines)

    def generate_study_guide(self, content: Dict) -> str:
        """
        Generate study guide.

        Args:
            content: Dict with summary, key_points, questions
        """
        lines = ["# Study Guide", ""]

        if content.get("summary"):
            lines.extend(["## Summary", content["summary"], ""])

        if content.get("key_points"):
            lines.append("## Key Points")
            for point in content["key_points"]:
                lines.append(f"- {point}")
            lines.append("")

        if content.get("vocabulary"):
            lines.append("## Vocabulary")
            for term, definition in content["vocabulary"].items():
                lines.append(f"- **{term}:** {definition}")
            lines.append("")

        if content.get("questions"):
            lines.append("## Review Questions")
            for i, q in enumerate(content["questions"], 1):
                if isinstance(q, dict):
                    lines.append(f"{i}. {q.get('question', q)}")
                else:
                    lines.append(f"{i}. {q}")
            lines.append("")

        return "\n".join(lines)


class TransactionSummary:
    """Generate financial transaction summaries."""

    def categorize_transactions(self, transactions: List[Dict]) -> Dict:
        """Categorize and summarize transactions."""
        categories = {}
        total_income = 0
        total_expense = 0
        anomalies = []

        for tx in transactions:
            amount = float(tx.get("amount", 0))
            category = tx.get("category", "uncategorized")
            description = tx.get("description", "")

            if category not in categories:
                categories[category] = {"total": 0, "count": 0, "transactions": []}

            categories[category]["total"] += amount
            categories[category]["count"] += 1
            categories[category]["transactions"].append(tx)

            if amount > 0:
                total_income += amount
            else:
                total_expense += abs(amount)

            # Flag anomalies (large transactions)
            if abs(amount) > 10000:
                anomalies.append({
                    "description": description,
                    "amount": amount,
                    "reason": "Large transaction"
                })

        return {
            "by_category": categories,
            "total_income": total_income,
            "total_expense": total_expense,
            "net": total_income - total_expense,
            "anomalies": anomalies,
            "transaction_count": len(transactions)
        }

    def generate_summary(self, data: Dict, title: str = "Financial Summary") -> str:
        """Generate financial summary report."""
        lines = [f"# {title}", ""]

        lines.append("## Overview")
        lines.append(f"- **Total Income:** ${data.get('total_income', 0):,.2f}")
        lines.append(f"- **Total Expenses:** ${data.get('total_expense', 0):,.2f}")
        lines.append(f"- **Net:** ${data.get('net', 0):,.2f}")
        lines.append(f"- **Transactions:** {data.get('transaction_count', 0)}")
        lines.append("")

        if data.get("by_category"):
            lines.append("## By Category")
            for cat, info in data["by_category"].items():
                lines.append(f"- **{cat}:** ${info['total']:,.2f} ({info['count']} transactions)")
            lines.append("")

        if data.get("anomalies"):
            lines.append("## Flagged Transactions")
            for anomaly in data["anomalies"]:
                lines.append(f"- {anomaly['description']}: ${anomaly['amount']:,.2f} - {anomaly['reason']}")
            lines.append("")

        return "\n".join(lines)


# Convenience instances
table_gen = TableGenerator()
json_gen = JSONGenerator()
report_gen = ReportGenerator()
quiz_gen = QuizGenerator()
finance_gen = TransactionSummary()


# Convenience functions
def make_table(data: List[Dict], format: str = "markdown") -> str:
    """Generate table in specified format."""
    if format == "csv":
        return table_gen.to_csv(data)
    elif format == "html":
        return table_gen.to_html(data)
    return table_gen.to_markdown(data)


def make_report(title: str, sections: List[Dict]) -> str:
    """Generate a report."""
    return report_gen.generate(title, sections)


def make_quiz(questions: List[Dict]) -> str:
    """Generate quiz from questions."""
    return quiz_gen.generate_quiz(questions)


def save_json(data: Any, filename: str) -> Path:
    """Save data as JSON."""
    return json_gen.save(data, filename)
