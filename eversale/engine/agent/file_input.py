"""
File Input System - Read any file type into structured data.

Supports:
- PDF documents
- CSV/Excel spreadsheets
- Text files (txt, log, md)
- Images (via vision model)
- JSON files
"""

import csv
import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass
from loguru import logger


@dataclass
class FileContent:
    """Standardized file content."""
    filename: str
    file_type: str
    text: str  # Main text content
    pages: List[str] = None  # For multi-page docs
    rows: List[Dict] = None  # For tabular data
    metadata: Dict = None
    raw_bytes: bytes = None  # For images


class FileReader:
    """Universal file reader."""

    SUPPORTED_TYPES = {
        'pdf': ['pdf'],
        'spreadsheet': ['csv', 'xlsx', 'xls', 'tsv'],
        'text': ['txt', 'log', 'md', 'json', 'xml', 'html'],
        'image': ['png', 'jpg', 'jpeg', 'gif', 'webp'],
    }

    def __init__(self):
        self._pdf_available = self._check_pdf_support()

    def _check_pdf_support(self) -> bool:
        """Check if PDF libraries are available."""
        try:
            import fitz  # PyMuPDF
            return True
        except ImportError:
            try:
                from pdf2image import convert_from_path
                return True
            except ImportError:
                return False

    def read(self, file_path: Union[str, Path]) -> FileContent:
        """Read any supported file type."""
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        ext = path.suffix.lower().lstrip('.')
        filename = path.name

        # Determine file type
        if ext in self.SUPPORTED_TYPES['pdf']:
            return self._read_pdf(path)
        elif ext in self.SUPPORTED_TYPES['spreadsheet']:
            return self._read_spreadsheet(path, ext)
        elif ext in self.SUPPORTED_TYPES['text']:
            return self._read_text(path, ext)
        elif ext in self.SUPPORTED_TYPES['image']:
            return self._read_image(path)
        else:
            # Try as text
            return self._read_text(path, ext)

    def _read_pdf(self, path: Path) -> FileContent:
        """Read PDF file."""
        try:
            import fitz  # PyMuPDF

            doc = fitz.open(str(path))
            pages = []
            full_text = []

            for page_num, page in enumerate(doc):
                text = page.get_text()
                pages.append(text)
                full_text.append(f"--- Page {page_num + 1} ---\n{text}")

            doc.close()

            return FileContent(
                filename=path.name,
                file_type='pdf',
                text="\n".join(full_text),
                pages=pages,
                metadata={'page_count': len(pages)}
            )

        except ImportError:
            # Fallback: try pdfplumber
            try:
                import pdfplumber

                pages = []
                full_text = []

                with pdfplumber.open(str(path)) as pdf:
                    for page_num, page in enumerate(pdf.pages):
                        text = page.extract_text() or ""
                        pages.append(text)
                        full_text.append(f"--- Page {page_num + 1} ---\n{text}")

                return FileContent(
                    filename=path.name,
                    file_type='pdf',
                    text="\n".join(full_text),
                    pages=pages,
                    metadata={'page_count': len(pages)}
                )

            except ImportError:
                raise ImportError(
                    "PDF reading requires PyMuPDF or pdfplumber.\n"
                    "Install with: pip install pymupdf pdfplumber"
                )

    def _read_spreadsheet(self, path: Path, ext: str) -> FileContent:
        """Read CSV or Excel file."""
        rows = []

        if ext == 'csv':
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                # Detect delimiter
                sample = f.read(4096)
                f.seek(0)

                # Try to detect delimiter
                sniffer = csv.Sniffer()
                try:
                    dialect = sniffer.sniff(sample)
                    delimiter = dialect.delimiter
                except Exception:
                    delimiter = ','

                reader = csv.DictReader(f, delimiter=delimiter)
                for row in reader:
                    rows.append(dict(row))

        elif ext == 'tsv':
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                reader = csv.DictReader(f, delimiter='\t')
                for row in reader:
                    rows.append(dict(row))

        elif ext in ['xlsx', 'xls']:
            try:
                import openpyxl

                wb = openpyxl.load_workbook(str(path), read_only=True)
                sheet = wb.active

                headers = []
                for row_idx, row in enumerate(sheet.iter_rows(values_only=True)):
                    if row_idx == 0:
                        headers = [str(c) if c else f"col_{i}" for i, c in enumerate(row)]
                    else:
                        row_dict = {headers[i]: str(v) if v else "" for i, v in enumerate(row) if i < len(headers)}
                        if any(row_dict.values()):
                            rows.append(row_dict)

                wb.close()

            except ImportError:
                raise ImportError(
                    "Excel reading requires openpyxl.\n"
                    "Install with: pip install openpyxl"
                )

        # Convert to text representation
        text_lines = []
        if rows:
            headers = list(rows[0].keys())
            text_lines.append(" | ".join(headers))
            text_lines.append("-" * 50)
            for row in rows[:100]:  # Limit preview
                text_lines.append(" | ".join(str(row.get(h, "")) for h in headers))

        return FileContent(
            filename=path.name,
            file_type='spreadsheet',
            text="\n".join(text_lines),
            rows=rows,
            metadata={'row_count': len(rows), 'columns': list(rows[0].keys()) if rows else []}
        )

    def _read_text(self, path: Path, ext: str) -> FileContent:
        """Read text file."""
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            text = f.read()

        # Parse JSON if applicable
        metadata = {}
        if ext == 'json':
            try:
                data = json.loads(text)
                metadata['json_type'] = type(data).__name__
                if isinstance(data, list):
                    metadata['item_count'] = len(data)
            except Exception:
                pass

        return FileContent(
            filename=path.name,
            file_type='text',
            text=text,
            metadata=metadata
        )

    def _read_image(self, path: Path) -> FileContent:
        """Read image file (returns bytes for vision processing)."""
        with open(path, 'rb') as f:
            raw_bytes = f.read()

        return FileContent(
            filename=path.name,
            file_type='image',
            text="[Image file - use vision model to analyze]",
            raw_bytes=raw_bytes,
            metadata={'size_bytes': len(raw_bytes)}
        )

    def read_multiple(self, file_paths: List[Union[str, Path]]) -> List[FileContent]:
        """Read multiple files."""
        results = []
        for path in file_paths:
            try:
                results.append(self.read(path))
            except Exception as e:
                logger.warning(f"Failed to read {path}: {e}")
        return results


class EmailReader:
    """Read emails from various sources."""

    def parse_email_text(self, text: str) -> Dict:
        """Parse email from raw text."""
        lines = text.strip().split('\n')

        email = {
            'from': '',
            'to': '',
            'subject': '',
            'date': '',
            'body': '',
        }

        body_start = 0
        for i, line in enumerate(lines):
            lower = line.lower()
            if lower.startswith('from:'):
                email['from'] = line[5:].strip()
            elif lower.startswith('to:'):
                email['to'] = line[3:].strip()
            elif lower.startswith('subject:'):
                email['subject'] = line[8:].strip()
            elif lower.startswith('date:'):
                email['date'] = line[5:].strip()
            elif line.strip() == '' and body_start == 0:
                body_start = i + 1

        if body_start > 0:
            email['body'] = '\n'.join(lines[body_start:])
        else:
            email['body'] = text

        return email

    def parse_email_list(self, text: str) -> List[Dict]:
        """Parse multiple emails from text (separated by --- or ===)."""
        # Split by common email separators
        parts = re.split(r'\n[-=]{3,}\n', text)

        emails = []
        for part in parts:
            if part.strip():
                emails.append(self.parse_email_text(part))

        return emails


class LogReader:
    """Read and parse log files."""

    LOG_PATTERNS = {
        'timestamp': r'(\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2})',
        'level': r'\b(DEBUG|INFO|WARNING|ERROR|CRITICAL|WARN|ERR)\b',
        'error': r'(?:error|exception|failed|failure|crash)[:=\s](.+)',
    }

    def parse_logs(self, text: str) -> Dict:
        """Parse log file and extract key information."""
        lines = text.strip().split('\n')

        result = {
            'total_lines': len(lines),
            'errors': [],
            'warnings': [],
            'by_level': {},
            'timeline': [],
        }

        for line in lines:
            # Find level
            level_match = re.search(self.LOG_PATTERNS['level'], line, re.IGNORECASE)
            level = level_match.group(1).upper() if level_match else 'INFO'

            result['by_level'][level] = result['by_level'].get(level, 0) + 1

            if level in ['ERROR', 'ERR', 'CRITICAL']:
                result['errors'].append(line.strip())
            elif level in ['WARNING', 'WARN']:
                result['warnings'].append(line.strip())

            # Find timestamp
            ts_match = re.search(self.LOG_PATTERNS['timestamp'], line)
            if ts_match and level in ['ERROR', 'ERR', 'CRITICAL', 'WARNING', 'WARN']:
                result['timeline'].append({
                    'timestamp': ts_match.group(1),
                    'level': level,
                    'message': line.strip()[:200]
                })

        return result


# Convenience functions
_reader = FileReader()
_email_reader = EmailReader()
_log_reader = LogReader()


def read_file(path: Union[str, Path]) -> FileContent:
    """Read any file."""
    return _reader.read(path)


def read_csv(path: Union[str, Path]) -> List[Dict]:
    """Read CSV and return rows."""
    content = _reader.read(path)
    return content.rows or []


def read_pdf(path: Union[str, Path]) -> str:
    """Read PDF and return text."""
    content = _reader.read(path)
    return content.text


def parse_emails(text: str) -> List[Dict]:
    """Parse emails from text."""
    return _email_reader.parse_email_list(text)


def parse_logs(text: str) -> Dict:
    """Parse log file."""
    return _log_reader.parse_logs(text)
