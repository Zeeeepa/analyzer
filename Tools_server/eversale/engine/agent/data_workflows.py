"""
Data Workflows - Consolidated data processing for Workflows B, G, J, N, O

This module provides structured data processing capabilities for:
- B) Spreadsheet cleaning and normalization
- G) Contract extraction and document parsing
- J) Transaction categorization and financial analysis
- N) Government form extraction to JSON
- O) Log analysis and ticket suggestion

All workflows are designed to be composable, with clear separation between
parsing, processing, and output generation.
"""

import csv
import re
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Union, Tuple
from dataclasses import dataclass
from io import StringIO
from loguru import logger

from .file_input import FileReader, read_file, read_csv, parse_logs, FileContent
from .output_path import get_output_folder, save_output, save_csv


@dataclass
class WorkflowResult:
    """Result from a data workflow execution."""
    success: bool
    summary: str  # Human-readable summary
    data: Any = None  # Structured output data
    files_created: List[str] = None  # Paths to generated files
    statistics: Dict[str, Any] = None  # Metrics about processing
    error: str = ""


class DataWorkflows:
    """
    Consolidated data processing workflows.

    Provides entry points for all data-centric business automation tasks
    with consistent error handling, logging, and output generation.
    """

    def __init__(self):
        self.file_reader = FileReader()
        self._output_dir = get_output_folder()

    # =========================================================================
    # WORKFLOW B: CSV/SPREADSHEET PROCESSING
    # =========================================================================

    def execute_spreadsheet_workflow(
        self,
        file_path: str,
        operations: List[str] = None
    ) -> WorkflowResult:
        """
        Execute spreadsheet cleaning and normalization workflow.

        Operations supported:
        - clean: Normalize headers, trim whitespace, fix common formats
        - deduplicate: Remove duplicate rows
        - validate: Check for empty cells, invalid formats
        - standardize: Standardize phone numbers, emails, dates

        Args:
            file_path: Path to CSV/Excel file
            operations: List of operations to perform (default: all)

        Returns:
            WorkflowResult with cleaned data and statistics
        """
        try:
            logger.info(f"Starting spreadsheet workflow: {file_path}")

            # Default operations
            if operations is None:
                operations = ["clean", "deduplicate", "validate", "standardize"]

            # Parse input file
            rows = self._parse_csv(file_path)
            if not rows:
                return WorkflowResult(
                    success=False,
                    summary="",
                    error="No data found in file"
                )

            original_count = len(rows)
            issues_log = []

            # Apply operations in sequence
            if "clean" in operations:
                rows, clean_issues = self._clean_spreadsheet_data(rows)
                issues_log.extend(clean_issues)

            if "standardize" in operations:
                rows, std_issues = self._standardize_formats(rows)
                issues_log.extend(std_issues)

            if "deduplicate" in operations:
                rows, dup_count = self._remove_duplicates(rows)
                if dup_count > 0:
                    issues_log.append(f"Removed {dup_count} duplicate rows")

            if "validate" in operations:
                validation_issues = self._validate_data(rows)
                issues_log.extend(validation_issues)

            # Generate output filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            input_name = Path(file_path).stem
            output_filename = f"cleaned_{input_name}_{timestamp}.csv"

            # Save cleaned data
            output_path = self._write_csv(output_filename, rows)

            # Compile statistics
            stats = {
                "original_rows": original_count,
                "cleaned_rows": len(rows),
                "rows_removed": original_count - len(rows),
                "issues_fixed": len(issues_log),
                "columns": list(rows[0].keys()) if rows else []
            }

            # Generate summary
            summary = self._generate_spreadsheet_summary(
                input_name, stats, issues_log, output_path
            )

            return WorkflowResult(
                success=True,
                summary=summary,
                data=rows,
                files_created=[str(output_path)],
                statistics=stats
            )

        except Exception as e:
            logger.error(f"Spreadsheet workflow failed: {e}")
            return WorkflowResult(success=False, summary="", error=str(e))

    def _parse_csv(self, file_path: str) -> List[Dict]:
        """Parse CSV file into list of dictionaries."""
        try:
            content = self.file_reader.read(file_path)
            return content.rows or []
        except Exception as e:
            logger.error(f"CSV parsing failed: {e}")
            return []

    def _write_csv(self, filename: str, data: List[Dict]) -> Path:
        """Write data to CSV file in output folder."""
        if not data:
            raise ValueError("No data to write")

        output_path = self._output_dir / filename

        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=list(data[0].keys()))
            writer.writeheader()
            writer.writerows(data)

        logger.info(f"CSV written: {output_path} ({len(data)} rows)")
        return output_path

    def _clean_spreadsheet_data(self, rows: List[Dict]) -> Tuple[List[Dict], List[str]]:
        """
        Clean and normalize spreadsheet data.

        Returns:
            Tuple of (cleaned_rows, issues_found)
        """
        cleaned_rows = []
        issues = []

        for i, row in enumerate(rows):
            cleaned_row = {}

            for key, value in row.items():
                # Normalize column headers
                clean_key = key.strip().lower().replace(" ", "_").replace("-", "_")
                clean_key = re.sub(r'[^\w_]', '', clean_key)

                # Clean value
                if value is None:
                    clean_value = ""
                else:
                    clean_value = str(value).strip()

                # Remove extra whitespace
                clean_value = re.sub(r'\s+', ' ', clean_value)

                # Track if we made changes
                if str(value) != clean_value or key != clean_key:
                    issues.append(f"Row {i+1}: Cleaned column '{key}'")

                cleaned_row[clean_key] = clean_value

            cleaned_rows.append(cleaned_row)

        return cleaned_rows, issues[:10]  # Limit issue log

    def _standardize_formats(self, rows: List[Dict]) -> Tuple[List[Dict], List[str]]:
        """Standardize common formats (phone, email, date)."""
        standardized = []
        issues = []

        for i, row in enumerate(rows):
            std_row = {}

            for key, value in row.items():
                std_value = value

                # Phone number standardization
                if 'phone' in key.lower() and value:
                    digits = re.sub(r'\D', '', value)
                    if len(digits) == 10:
                        std_value = f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
                        if std_value != value:
                            issues.append(f"Row {i+1}: Standardized phone number")
                    elif len(digits) == 11 and digits[0] == '1':
                        std_value = f"+1 ({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
                        if std_value != value:
                            issues.append(f"Row {i+1}: Standardized phone number")

                # Email normalization
                elif 'email' in key.lower() and value:
                    std_value = value.lower().strip()
                    if std_value != value:
                        issues.append(f"Row {i+1}: Normalized email")

                # Date normalization (basic)
                elif 'date' in key.lower() and value:
                    # Convert common separators to dashes
                    std_value = value.replace('/', '-').replace('.', '-')

                std_row[key] = std_value

            standardized.append(std_row)

        return standardized, issues[:10]

    def _remove_duplicates(self, rows: List[Dict]) -> Tuple[List[Dict], int]:
        """Remove duplicate rows, keeping first occurrence."""
        seen = set()
        unique_rows = []
        duplicates = 0

        for row in rows:
            # Create hashable representation
            row_tuple = tuple(sorted(row.items()))

            if row_tuple not in seen:
                seen.add(row_tuple)
                unique_rows.append(row)
            else:
                duplicates += 1

        return unique_rows, duplicates

    def _validate_data(self, rows: List[Dict]) -> List[str]:
        """Validate data quality and return issues."""
        issues = []

        if not rows:
            return ["No data to validate"]

        # Check for empty columns
        columns = list(rows[0].keys())
        for col in columns:
            empty_count = sum(1 for row in rows if not row.get(col))
            if empty_count > len(rows) * 0.5:  # More than 50% empty
                issues.append(f"Warning: Column '{col}' is {empty_count}/{len(rows)} empty")

        # Check for email validity
        email_pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
        for col in columns:
            if 'email' in col.lower():
                invalid_count = 0
                for row in rows:
                    email = row.get(col, "")
                    if email and not email_pattern.match(email):
                        invalid_count += 1
                if invalid_count > 0:
                    issues.append(f"Warning: {invalid_count} invalid emails in '{col}'")

        return issues[:5]  # Limit to top 5 issues

    def _generate_spreadsheet_summary(
        self,
        filename: str,
        stats: Dict,
        issues: List[str],
        output_path: Path
    ) -> str:
        """Generate human-readable summary of spreadsheet processing."""
        lines = [
            f"## Spreadsheet Cleaned: {filename}",
            "",
            f"**Original rows:** {stats['original_rows']}",
            f"**Cleaned rows:** {stats['cleaned_rows']}",
            f"**Rows removed:** {stats['rows_removed']}",
            f"**Issues fixed:** {stats['issues_fixed']}",
            f"**Columns:** {len(stats['columns'])}",
            "",
            "**Changes made:**"
        ]

        if issues:
            for issue in issues[:10]:
                lines.append(f"- {issue}")
            if len(issues) > 10:
                lines.append(f"... and {len(issues) - 10} more")
        else:
            lines.append("- No issues found")

        lines.extend([
            "",
            f"**Saved to:** {output_path}"
        ])

        return "\n".join(lines)

    # =========================================================================
    # WORKFLOW G & N: DOCUMENT PROCESSING (Contracts, Forms)
    # =========================================================================

    def execute_document_processing(
        self,
        file_path: str,
        doc_type: str
    ) -> WorkflowResult:
        """
        Execute document extraction workflow.

        Supported document types:
        - contract: Extract parties, dates, amounts, terms (Workflow G)
        - form: Extract form fields to JSON (Workflow N)
        - invoice: Extract invoice details
        - agreement: Extract agreement terms

        Args:
            file_path: Path to document (PDF, TXT, DOCX)
            doc_type: Type of document to process

        Returns:
            WorkflowResult with extracted structured data
        """
        try:
            logger.info(f"Processing document: {file_path} (type: {doc_type})")

            # Read document
            content = self.file_reader.read(file_path)

            if not content.text:
                return WorkflowResult(
                    success=False,
                    summary="",
                    error="Could not extract text from document"
                )

            # Route to appropriate processor
            if doc_type.lower() in ["contract", "agreement"]:
                extracted_data = self._extract_contract_fields(content.text)
                doc_label = "Contract"
            elif doc_type.lower() in ["form", "government_form"]:
                extracted_data = self._extract_form_fields(content.text)
                doc_label = "Form"
            else:
                # Generic structured extraction
                extracted_data = self._extract_structured_data(
                    content.text,
                    ["date", "name", "amount", "description"]
                )
                doc_label = "Document"

            # Save JSON output
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            input_name = Path(file_path).stem
            json_filename = f"{doc_type}_extract_{input_name}_{timestamp}.json"
            json_path = self._save_json(json_filename, extracted_data)

            # Generate summary
            summary = self._generate_extraction_summary(
                doc_label, input_name, extracted_data, json_path
            )

            stats = {
                "fields_extracted": len(extracted_data),
                "document_type": doc_type,
                "source_file": file_path
            }

            return WorkflowResult(
                success=True,
                summary=summary,
                data=extracted_data,
                files_created=[str(json_path)],
                statistics=stats
            )

        except Exception as e:
            logger.error(f"Document processing failed: {e}")
            return WorkflowResult(success=False, summary="", error=str(e))

    def _extract_contract_fields(self, content: str) -> Dict:
        """
        Extract key fields from contract text (Workflow G).

        Looks for:
        - Parties (individuals, organizations)
        - Dates (effective, termination, signature)
        - Monetary amounts
        - Key obligations and terms
        """
        extracted = {
            "parties": [],
            "dates": {},
            "amounts": [],
            "obligations": [],
            "metadata": {}
        }

        # Extract dates
        date_patterns = [
            (r"effective date[:\s]+(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})", "effective_date"),
            (r"termination date[:\s]+(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})", "termination_date"),
            (r"dated[:\s]+(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})", "document_date"),
            (r"(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})", "other_date")
        ]

        for pattern, label in date_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            if matches:
                extracted["dates"][label] = matches[0]

        # Extract monetary amounts
        money_pattern = r'\$[\d,]+\.?\d*|\d+\s*(?:dollars?|USD|usd)'
        amounts = re.findall(money_pattern, content)
        extracted["amounts"] = list(set(amounts[:10]))  # Limit and dedupe

        # Extract party names (look for "between X and Y" patterns)
        party_patterns = [
            r"between\s+([A-Z][A-Za-z\s&,.]+?)\s+(?:and|,)",
            r"party[:\s]+([A-Z][A-Za-z\s&,.]+?)(?:\.|,|\n)",
            r"(?:by and between|entered into by)\s+([A-Z][A-Za-z\s&,.]+?)(?:and|,)"
        ]

        for pattern in party_patterns:
            matches = re.findall(pattern, content)
            for match in matches:
                party = match.strip().rstrip('.,')
                if len(party) > 3 and party not in extracted["parties"]:
                    extracted["parties"].append(party)

        # Extract obligations (sentences with shall/will/must)
        obligation_pattern = r'[^.!?]*(?:shall|will|must)[^.!?]*[.!?]'
        obligations = re.findall(obligation_pattern, content, re.IGNORECASE)
        extracted["obligations"] = [o.strip() for o in obligations[:5]]

        # Metadata
        extracted["metadata"]["extraction_date"] = datetime.now().isoformat()
        extracted["metadata"]["content_length"] = len(content)

        return extracted

    def _extract_form_fields(self, content: str) -> Dict:
        """
        Extract form fields from government/business forms (Workflow N).

        Looks for labeled fields in format:
        - Field Name: Value
        - Field Name [ ] Value
        - 1. Field Name: Value
        """
        extracted = {}

        # Pattern 1: "Label: Value" format
        label_value_pattern = r'([A-Za-z\s]+?):\s*([^\n]+)'
        matches = re.findall(label_value_pattern, content)

        for label, value in matches:
            clean_label = label.strip().lower().replace(' ', '_')
            clean_value = value.strip()

            # Skip if too long (likely not a field)
            if len(clean_value) < 200 and len(clean_label) < 50:
                extracted[clean_label] = clean_value

        # Pattern 2: Checkbox fields "[ ] Option" or "[X] Option"
        checkbox_pattern = r'\[([ Xx])\]\s*([A-Za-z\s]+)'
        checkboxes = re.findall(checkbox_pattern, content)

        for checked, option in checkboxes:
            clean_option = option.strip().lower().replace(' ', '_')
            extracted[clean_option] = checked.strip().upper() in ['X', 'x']

        # Extract common form fields
        field_patterns = {
            "name": r"(?:name|full name)[:\s]+([A-Za-z\s]+)",
            "email": r"([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})",
            "phone": r"(?:phone|tel)[:\s]+([\d\s\-\(\)]+)",
            "ssn": r"(?:ssn|social security)[:\s]*([\d\-]+)",
            "date": r"(?:date)[:\s]*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})"
        }

        for field_name, pattern in field_patterns.items():
            matches = re.findall(pattern, content, re.IGNORECASE)
            if matches:
                extracted[field_name] = matches[0].strip()

        # Add metadata
        extracted["_metadata"] = {
            "extraction_date": datetime.now().isoformat(),
            "fields_extracted": len(extracted) - 1
        }

        return extracted

    def _extract_structured_data(self, content: str, fields: List[str]) -> Dict:
        """Generic structured data extraction for specified fields."""
        extracted = {}

        # Build patterns for each field
        for field in fields:
            pattern = rf"{field}[:\s]+([^\n]+)"
            matches = re.findall(pattern, content, re.IGNORECASE)
            if matches:
                extracted[field] = matches[0].strip()

        return extracted

    def _save_json(self, filename: str, data: Dict) -> Path:
        """Save JSON data to output folder."""
        output_path = self._output_dir / filename

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"JSON saved: {output_path}")
        return output_path

    def _generate_extraction_summary(
        self,
        doc_type: str,
        filename: str,
        data: Dict,
        json_path: Path
    ) -> str:
        """Generate summary of document extraction."""
        lines = [
            f"## {doc_type} Extraction: {filename}",
            "",
            f"**Fields extracted:** {len(data)}",
            ""
        ]

        # Show key fields
        for key, value in list(data.items())[:10]:
            if not key.startswith('_'):
                value_str = str(value)[:100]
                lines.append(f"**{key}:** {value_str}")

        if len(data) > 10:
            lines.append(f"\n... and {len(data) - 10} more fields")

        lines.extend([
            "",
            f"**Saved to:** {json_path}"
        ])

        return "\n".join(lines)

    # =========================================================================
    # WORKFLOW O: LOG ANALYSIS
    # =========================================================================

    def execute_log_analysis(self, file_path: str) -> WorkflowResult:
        """
        Analyze log files and suggest Jira tickets.

        Processes log files to:
        - Parse log entries and categorize by severity
        - Identify error patterns and frequencies
        - Extract stack traces and error messages
        - Generate suggested Jira tickets for issues

        Args:
            file_path: Path to log file

        Returns:
            WorkflowResult with analysis and ticket suggestions
        """
        try:
            logger.info(f"Analyzing log file: {file_path}")

            # Read log file
            content = self.file_reader.read(file_path)

            if not content.text:
                return WorkflowResult(
                    success=False,
                    summary="",
                    error="Could not read log file"
                )

            # Parse log entries
            log_entries = self._parse_log_entries(content.text)

            # Categorize by severity
            severity_counts = self._categorize_by_severity(log_entries)

            # Analyze error patterns
            error_patterns = self._analyze_error_patterns(log_entries)

            # Generate ticket suggestions
            tickets = self._generate_ticket_suggestions(error_patterns)

            # Compile results
            analysis_data = {
                "log_statistics": {
                    "total_lines": len(content.text.split('\n')),
                    "log_entries": len(log_entries),
                    "severity_breakdown": severity_counts
                },
                "error_patterns": error_patterns,
                "suggested_tickets": tickets
            }

            # Save analysis report
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            input_name = Path(file_path).stem
            report_filename = f"log_analysis_{input_name}_{timestamp}.json"
            report_path = self._save_json(report_filename, analysis_data)

            # Generate summary
            summary = self._generate_log_analysis_summary(
                input_name, analysis_data, report_path
            )

            return WorkflowResult(
                success=True,
                summary=summary,
                data=analysis_data,
                files_created=[str(report_path)],
                statistics=analysis_data["log_statistics"]
            )

        except Exception as e:
            logger.error(f"Log analysis failed: {e}")
            return WorkflowResult(success=False, summary="", error=str(e))

    def _parse_log_entries(self, content: str) -> List[Dict]:
        """Parse log file into structured entries."""
        entries = []
        lines = content.split('\n')

        # Common log patterns
        patterns = [
            # ISO timestamp with level
            r'(\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)\s+(\w+)\s+(.+)',
            # Apache/Nginx style
            r'\[([^\]]+)\]\s+\[(\w+)\]\s+(.+)',
            # Simple timestamp
            r'(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2})\s+(\w+):\s+(.+)'
        ]

        for line in lines:
            if not line.strip():
                continue

            parsed = None
            for pattern in patterns:
                match = re.match(pattern, line)
                if match:
                    parsed = {
                        "timestamp": match.group(1),
                        "level": match.group(2).upper(),
                        "message": match.group(3),
                        "raw": line
                    }
                    break

            if not parsed:
                # Fallback: treat as unstructured
                parsed = {
                    "timestamp": None,
                    "level": "INFO",
                    "message": line,
                    "raw": line
                }

            entries.append(parsed)

        return entries

    def _categorize_log_severity(self, entry: str) -> str:
        """Categorize log entry severity."""
        entry_upper = entry.upper()

        if any(kw in entry_upper for kw in ['ERROR', 'FATAL', 'CRITICAL']):
            return 'ERROR'
        elif any(kw in entry_upper for kw in ['WARN', 'WARNING']):
            return 'WARN'
        elif 'DEBUG' in entry_upper:
            return 'DEBUG'
        else:
            return 'INFO'

    def _categorize_by_severity(self, entries: List[Dict]) -> Dict[str, int]:
        """Count entries by severity level."""
        counts = {"ERROR": 0, "WARN": 0, "INFO": 0, "DEBUG": 0}

        for entry in entries:
            level = entry.get("level", "INFO")
            if level in counts:
                counts[level] += 1
            else:
                counts["INFO"] += 1

        return counts

    def _analyze_error_patterns(self, entries: List[Dict]) -> List[Dict]:
        """Identify patterns in error messages."""
        error_entries = [e for e in entries if e.get("level") in ["ERROR", "FATAL", "CRITICAL"]]

        if not error_entries:
            return []

        # Group similar errors
        error_groups = {}

        for entry in error_entries:
            message = entry.get("message", "")

            # Extract error type (first few words or exception class)
            error_type_match = re.match(r'^([A-Za-z.]+(?:Error|Exception))', message)
            if error_type_match:
                error_type = error_type_match.group(1)
            else:
                # Use first 50 chars as signature
                error_type = message[:50]

            if error_type not in error_groups:
                error_groups[error_type] = {
                    "type": error_type,
                    "count": 0,
                    "sample_message": message[:200],
                    "timestamps": []
                }

            error_groups[error_type]["count"] += 1
            if entry.get("timestamp"):
                error_groups[error_type]["timestamps"].append(entry["timestamp"])

        # Sort by frequency
        patterns = sorted(error_groups.values(), key=lambda x: x["count"], reverse=True)

        return patterns[:10]  # Top 10 patterns

    def _generate_ticket_suggestions(self, error_patterns: List[Dict]) -> List[Dict]:
        """Generate Jira ticket suggestions from error patterns."""
        tickets = []

        for pattern in error_patterns:
            # Determine priority based on frequency
            count = pattern["count"]
            if count >= 100:
                priority = "Critical"
            elif count >= 20:
                priority = "High"
            elif count >= 5:
                priority = "Medium"
            else:
                priority = "Low"

            ticket = {
                "title": f"Investigate: {pattern['type']}",
                "priority": priority,
                "description": f"Error occurring {count} times in logs.\n\nSample:\n{pattern['sample_message']}",
                "labels": ["bug", "production", "automated"],
                "occurrences": count
            }

            tickets.append(ticket)

        return tickets

    def _generate_log_analysis_summary(
        self,
        filename: str,
        data: Dict,
        report_path: Path
    ) -> str:
        """Generate human-readable log analysis summary."""
        stats = data["log_statistics"]
        severity = stats["severity_breakdown"]
        patterns = data["error_patterns"]
        tickets = data["suggested_tickets"]

        lines = [
            f"## Log Analysis: {filename}",
            "",
            "**Statistics:**",
            f"- Total lines: {stats['total_lines']}",
            f"- Log entries parsed: {stats['log_entries']}",
            f"- Errors: {severity.get('ERROR', 0)}",
            f"- Warnings: {severity.get('WARN', 0)}",
            f"- Info: {severity.get('INFO', 0)}",
            "",
            "**Top Error Patterns:**"
        ]

        for pattern in patterns[:5]:
            lines.append(f"- {pattern['type']} (x{pattern['count']})")

        lines.extend([
            "",
            "**Suggested Jira Tickets:**"
        ])

        for ticket in tickets[:5]:
            lines.append(f"- [{ticket['priority']}] {ticket['title']}")

        lines.extend([
            "",
            f"**Full report saved to:** {report_path}"
        ])

        return "\n".join(lines)

    # =========================================================================
    # WORKFLOW J: TRANSACTION CATEGORIZATION
    # =========================================================================

    def execute_data_categorization(
        self,
        file_path: str,
        categories: List[str] = None
    ) -> WorkflowResult:
        """
        Execute transaction categorization workflow.

        Processes financial transactions and categorizes them into:
        - Income
        - Expenses (by type: operational, payroll, marketing, etc.)
        - Transfers

        Args:
            file_path: Path to transactions CSV
            categories: Custom categories (optional)

        Returns:
            WorkflowResult with categorized transactions and summary
        """
        try:
            logger.info(f"Categorizing transactions: {file_path}")

            # Default categories
            if categories is None:
                categories = [
                    "income",
                    "expense_operational",
                    "expense_payroll",
                    "expense_marketing",
                    "expense_travel",
                    "expense_supplies",
                    "expense_other",
                    "transfer"
                ]

            # Parse transactions
            rows = self._parse_csv(file_path)

            if not rows:
                return WorkflowResult(
                    success=False,
                    summary="",
                    error="No transactions found in file"
                )

            # Categorize each transaction
            categorized = []
            for row in rows:
                description = row.get("description", row.get("memo", ""))
                amount_str = row.get("amount", "0")

                # Parse amount
                try:
                    amount = float(str(amount_str).replace('$', '').replace(',', ''))
                except (ValueError, AttributeError):
                    amount = 0.0

                # Categorize
                category = self._categorize_transaction(description, amount, categories)

                categorized_row = {
                    **row,
                    "category": category,
                    "amount": amount
                }
                categorized.append(categorized_row)

            # Generate financial summary
            summary_text = self._generate_financial_summary(categorized)

            # Save categorized transactions
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            input_name = Path(file_path).stem
            output_filename = f"categorized_{input_name}_{timestamp}.csv"
            output_path = self._write_csv(output_filename, categorized)

            # Calculate statistics
            stats = self._calculate_financial_stats(categorized)

            return WorkflowResult(
                success=True,
                summary=summary_text,
                data=categorized,
                files_created=[str(output_path)],
                statistics=stats
            )

        except Exception as e:
            logger.error(f"Transaction categorization failed: {e}")
            return WorkflowResult(success=False, summary="", error=str(e))

    def _categorize_transaction(
        self,
        description: str,
        amount: float,
        categories: List[str]
    ) -> str:
        """
        Categorize a single transaction based on description and amount.

        Uses keyword matching for common transaction patterns.
        """
        desc_lower = description.lower()

        # Income indicators
        if amount > 0 and any(kw in desc_lower for kw in [
            'payment received', 'invoice', 'deposit', 'revenue', 'sales'
        ]):
            return "income"

        # Payroll
        if any(kw in desc_lower for kw in [
            'salary', 'payroll', 'wage', 'employee', 'contractor payment'
        ]):
            return "expense_payroll"

        # Marketing
        if any(kw in desc_lower for kw in [
            'advertising', 'google ads', 'facebook ads', 'marketing',
            'campaign', 'social media', 'seo'
        ]):
            return "expense_marketing"

        # Travel
        if any(kw in desc_lower for kw in [
            'airline', 'hotel', 'uber', 'lyft', 'rental car', 'travel',
            'airbnb', 'expedia', 'booking'
        ]):
            return "expense_travel"

        # Supplies
        if any(kw in desc_lower for kw in [
            'office supplies', 'amazon', 'staples', 'supplies'
        ]):
            return "expense_supplies"

        # Operational
        if any(kw in desc_lower for kw in [
            'software', 'subscription', 'hosting', 'utilities',
            'rent', 'insurance', 'saas', 'aws', 'azure'
        ]):
            return "expense_operational"

        # Transfer
        if any(kw in desc_lower for kw in [
            'transfer', 'xfer', 'internal', 'account transfer'
        ]):
            return "transfer"

        # Default
        if amount < 0:
            return "expense_other"
        else:
            return "income"

    def _generate_financial_summary(self, categorized: List[Dict]) -> str:
        """Generate financial summary report."""
        # Calculate totals by category
        category_totals = {}
        for transaction in categorized:
            category = transaction.get("category", "unknown")
            amount = transaction.get("amount", 0)

            if category not in category_totals:
                category_totals[category] = 0
            category_totals[category] += amount

        # Separate income and expenses
        total_income = sum(v for k, v in category_totals.items() if k == "income")
        total_expenses = sum(v for k, v in category_totals.items() if k.startswith("expense_"))
        net = total_income + total_expenses  # Expenses are negative

        lines = [
            "## Financial Summary",
            "",
            f"**Total Transactions:** {len(categorized)}",
            f"**Total Income:** ${total_income:,.2f}",
            f"**Total Expenses:** ${abs(total_expenses):,.2f}",
            f"**Net:** ${net:,.2f}",
            "",
            "**Breakdown by Category:**"
        ]

        for category in sorted(category_totals.keys()):
            total = category_totals[category]
            lines.append(f"- {category}: ${total:,.2f}")

        return "\n".join(lines)

    def _calculate_financial_stats(self, categorized: List[Dict]) -> Dict:
        """Calculate detailed financial statistics."""
        stats = {
            "total_transactions": len(categorized),
            "by_category": {},
            "income": 0,
            "expenses": 0,
            "net": 0
        }

        for transaction in categorized:
            category = transaction.get("category", "unknown")
            amount = transaction.get("amount", 0)

            if category not in stats["by_category"]:
                stats["by_category"][category] = {"count": 0, "total": 0}

            stats["by_category"][category]["count"] += 1
            stats["by_category"][category]["total"] += amount

            if category == "income":
                stats["income"] += amount
            elif category.startswith("expense_"):
                stats["expenses"] += abs(amount)

        stats["net"] = stats["income"] - stats["expenses"]

        return stats


# =========================================================================
# CONVENIENCE FUNCTIONS
# =========================================================================

def clean_spreadsheet(file_path: str, operations: List[str] = None) -> WorkflowResult:
    """Clean and normalize a spreadsheet."""
    workflows = DataWorkflows()
    return workflows.execute_spreadsheet_workflow(file_path, operations)


def extract_contract(file_path: str) -> WorkflowResult:
    """Extract data from a contract."""
    workflows = DataWorkflows()
    return workflows.execute_document_processing(file_path, "contract")


def extract_form(file_path: str) -> WorkflowResult:
    """Extract data from a government form."""
    workflows = DataWorkflows()
    return workflows.execute_document_processing(file_path, "form")


def analyze_logs(file_path: str) -> WorkflowResult:
    """Analyze log file and suggest tickets."""
    workflows = DataWorkflows()
    return workflows.execute_log_analysis(file_path)


def categorize_transactions(file_path: str, categories: List[str] = None) -> WorkflowResult:
    """Categorize financial transactions."""
    workflows = DataWorkflows()
    return workflows.execute_data_categorization(file_path, categories)
