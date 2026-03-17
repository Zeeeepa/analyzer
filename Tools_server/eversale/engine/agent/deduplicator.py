"""
Extraction Deduplicator - Remove duplicate contacts and leads

Features:
- Exact match deduplication
- Fuzzy matching for near-duplicates
- Cross-field deduplication (same company different contacts)
- Merge duplicate records
- Dedup report generation

Usage:
    from agent.deduplicator import Deduplicator, DedupStrategy

    # Basic deduplication
    deduplicator = Deduplicator()
    clean_records = deduplicator.deduplicate(records)

    # With custom strategy
    deduplicator = Deduplicator(strategy=DedupStrategy.MERGE)
    clean_records = deduplicator.deduplicate(records)

    # With progress tracking
    def progress(current, total):
        print(f"Processing {current}/{total}")

    clean_records = deduplicator.deduplicate(records, progress_callback=progress)

    # Get dedup report
    report = deduplicator.get_report()
"""

import re
import logging
from typing import List, Dict, Any, Optional, Callable, Tuple, Set
from enum import Enum
from dataclasses import dataclass, field
from urllib.parse import urlparse, urlunparse
from collections import defaultdict

logger = logging.getLogger(__name__)


class DedupStrategy(Enum):
    """Deduplication strategy"""
    KEEP_FIRST = "keep_first"      # Keep first occurrence
    KEEP_BEST = "keep_best"        # Keep most complete record
    MERGE = "merge"                # Merge all data
    ASK = "ask"                    # Prompt user for ambiguous cases


@dataclass
class DedupReport:
    """Deduplication report"""
    total_records: int = 0
    unique_records: int = 0
    duplicates_found: int = 0
    exact_duplicates: int = 0
    fuzzy_duplicates: int = 0
    merged_records: int = 0
    data_quality_score: float = 0.0
    duplicate_groups: List[List[Dict]] = field(default_factory=list)

    def __str__(self) -> str:
        return f"""
=== Deduplication Report ===
Total records: {self.total_records}
Unique records: {self.unique_records}
Duplicates found: {self.duplicates_found}
  - Exact duplicates: {self.exact_duplicates}
  - Fuzzy duplicates: {self.fuzzy_duplicates}
Merged records: {self.merged_records}
Data quality score: {self.data_quality_score:.1f}%
Deduplication rate: {(self.duplicates_found / max(self.total_records, 1)) * 100:.1f}%
"""


class Deduplicator:
    """
    Intelligent contact/lead deduplicator with exact and fuzzy matching
    """

    def __init__(
        self,
        strategy: DedupStrategy = DedupStrategy.KEEP_BEST,
        fuzzy_threshold: float = 0.85,
        enable_fuzzy: bool = True,
        enable_cross_field: bool = True
    ):
        """
        Initialize deduplicator

        Args:
            strategy: Deduplication strategy to use
            fuzzy_threshold: Similarity threshold for fuzzy matching (0.0-1.0)
            enable_fuzzy: Enable fuzzy matching for near-duplicates
            enable_cross_field: Enable cross-field matching (domain, phone prefix)
        """
        self.strategy = strategy
        self.fuzzy_threshold = fuzzy_threshold
        self.enable_fuzzy = enable_fuzzy
        self.enable_cross_field = enable_cross_field
        self.report = DedupReport()

    def deduplicate(
        self,
        records: List[Dict[str, Any]],
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> List[Dict[str, Any]]:
        """
        Deduplicate a list of records

        Args:
            records: List of contact/lead records
            progress_callback: Optional callback(current, total) for progress updates

        Returns:
            List of deduplicated records
        """
        if not records:
            return []

        # Reset report
        self.report = DedupReport()
        self.report.total_records = len(records)

        logger.info(f"Starting deduplication of {len(records)} records")

        # Step 1: Exact deduplication
        records = self._deduplicate_exact(records, progress_callback)

        # Step 2: Fuzzy deduplication (if enabled)
        if self.enable_fuzzy:
            records = self._deduplicate_fuzzy(records, progress_callback)

        # Step 3: Cross-field deduplication (if enabled)
        if self.enable_cross_field:
            records = self._deduplicate_cross_field(records, progress_callback)

        # Calculate data quality score
        self.report.unique_records = len(records)
        self.report.duplicates_found = (
            self.report.exact_duplicates +
            self.report.fuzzy_duplicates
        )
        self.report.data_quality_score = self._calculate_quality_score(records)

        logger.info(f"Deduplication complete: {len(records)} unique records")

        return records

    def _deduplicate_exact(
        self,
        records: List[Dict],
        progress_callback: Optional[Callable] = None
    ) -> List[Dict]:
        """
        Exact match deduplication by email, phone, URL
        """
        seen_emails: Dict[str, int] = {}
        seen_phones: Dict[str, int] = {}
        seen_urls: Dict[str, int] = {}
        unique_records: List[Dict] = []
        duplicate_groups: List[List[Dict]] = []

        for i, record in enumerate(records):
            if progress_callback:
                progress_callback(i + 1, len(records))

            is_duplicate = False
            duplicate_of = -1

            # Check email (case-insensitive)
            email = self._normalize_email(record.get('email', ''))
            if email and email in seen_emails:
                is_duplicate = True
                duplicate_of = seen_emails[email]

            # Check phone (normalized)
            phone = self._normalize_phone(record.get('phone', ''))
            if not is_duplicate and phone and phone in seen_phones:
                is_duplicate = True
                duplicate_of = seen_phones[phone]

            # Check URL (normalized)
            url = self._normalize_url(record.get('url', '') or record.get('website', ''))
            if not is_duplicate and url and url in seen_urls:
                is_duplicate = True
                duplicate_of = seen_urls[url]

            if is_duplicate:
                self.report.exact_duplicates += 1
                # Handle duplicate based on strategy
                if self.strategy == DedupStrategy.MERGE:
                    unique_records[duplicate_of] = self._merge_records(
                        unique_records[duplicate_of],
                        record
                    )
                    self.report.merged_records += 1
                elif self.strategy == DedupStrategy.KEEP_BEST:
                    if self._is_more_complete(record, unique_records[duplicate_of]):
                        unique_records[duplicate_of] = record
                # KEEP_FIRST: do nothing
            else:
                # Add to unique records
                idx = len(unique_records)
                unique_records.append(record)

                # Track in seen sets
                if email:
                    seen_emails[email] = idx
                if phone:
                    seen_phones[phone] = idx
                if url:
                    seen_urls[url] = idx

        logger.info(f"Exact deduplication: {self.report.exact_duplicates} duplicates found")
        return unique_records

    def _deduplicate_fuzzy(
        self,
        records: List[Dict],
        progress_callback: Optional[Callable] = None
    ) -> List[Dict]:
        """
        Fuzzy deduplication using similarity matching
        """
        unique_records: List[Dict] = []

        for i, record in enumerate(records):
            if progress_callback:
                progress_callback(i + 1, len(records))

            # Find similar records
            similar_idx = self._find_similar_record(record, unique_records)

            if similar_idx is not None:
                self.report.fuzzy_duplicates += 1
                # Handle duplicate based on strategy
                if self.strategy == DedupStrategy.MERGE:
                    unique_records[similar_idx] = self._merge_records(
                        unique_records[similar_idx],
                        record
                    )
                    self.report.merged_records += 1
                elif self.strategy == DedupStrategy.KEEP_BEST:
                    if self._is_more_complete(record, unique_records[similar_idx]):
                        unique_records[similar_idx] = record
            else:
                unique_records.append(record)

        logger.info(f"Fuzzy deduplication: {self.report.fuzzy_duplicates} duplicates found")
        return unique_records

    def _deduplicate_cross_field(
        self,
        records: List[Dict],
        progress_callback: Optional[Callable] = None
    ) -> List[Dict]:
        """
        Cross-field deduplication (same domain, phone prefix, etc.)
        """
        # Group by domain
        domain_groups: Dict[str, List[int]] = defaultdict(list)
        phone_prefix_groups: Dict[str, List[int]] = defaultdict(list)

        for i, record in enumerate(records):
            # Group by email domain
            email = record.get('email', '')
            if email and '@' in email:
                domain = email.split('@')[1].lower()
                domain_groups[domain].append(i)

            # Group by phone prefix (first 6 digits)
            phone = self._normalize_phone(record.get('phone', ''))
            if phone and len(phone) >= 6:
                prefix = phone[:6]
                phone_prefix_groups[prefix].append(i)

        # Merge records from same domain/company
        unique_records: List[Dict] = list(records)  # Copy
        merged_indices: Set[int] = set()

        for domain, indices in domain_groups.items():
            if len(indices) > 1:
                # Check if they're from same company
                company_names = [
                    unique_records[i].get('company', '').lower()
                    for i in indices
                ]

                # If same domain and similar company name, merge
                if len(set(company_names)) == 1 and company_names[0]:
                    # Merge into first record
                    base_idx = indices[0]
                    for idx in indices[1:]:
                        if idx not in merged_indices:
                            unique_records[base_idx] = self._merge_records(
                                unique_records[base_idx],
                                unique_records[idx]
                            )
                            merged_indices.add(idx)
                            self.report.merged_records += 1

        # Remove merged records
        unique_records = [
            record for i, record in enumerate(unique_records)
            if i not in merged_indices
        ]

        logger.info(f"Cross-field deduplication: {len(merged_indices)} records merged")
        return unique_records

    def _find_similar_record(
        self,
        record: Dict,
        existing_records: List[Dict]
    ) -> Optional[int]:
        """
        Find similar record using fuzzy matching

        Returns:
            Index of similar record, or None if not found
        """
        for i, existing in enumerate(existing_records):
            # Check company name similarity
            company_sim = self._similarity(
                record.get('company', ''),
                existing.get('company', '')
            )

            # Check person name similarity
            name_sim = self._similarity(
                record.get('name', '') or record.get('person', ''),
                existing.get('name', '') or existing.get('person', '')
            )

            # Check address similarity
            address_sim = self._similarity(
                record.get('address', ''),
                existing.get('address', '')
            )

            # Consider it a match if any field is highly similar
            if (company_sim >= self.fuzzy_threshold or
                name_sim >= self.fuzzy_threshold or
                address_sim >= self.fuzzy_threshold):
                return i

        return None

    def _merge_records(self, base: Dict, other: Dict) -> Dict:
        """
        Merge two records, keeping most complete data
        """
        merged = dict(base)  # Start with base

        for key, value in other.items():
            if key not in merged or not merged[key]:
                # Base doesn't have this field, use other's value
                merged[key] = value
            elif value and len(str(value)) > len(str(merged[key])):
                # Other's value is more detailed, use it
                merged[key] = value
            # Otherwise keep base's value

        # Add metadata about merge
        if '_sources' not in merged:
            merged['_sources'] = []
        merged['_sources'].append(other.get('_source', 'unknown'))

        return merged

    def _is_more_complete(self, record1: Dict, record2: Dict) -> bool:
        """
        Check if record1 is more complete than record2
        """
        score1 = self._completeness_score(record1)
        score2 = self._completeness_score(record2)
        return score1 > score2

    def _completeness_score(self, record: Dict) -> int:
        """
        Calculate completeness score for a record
        """
        score = 0
        important_fields = ['email', 'phone', 'name', 'company', 'website', 'address']

        for field in important_fields:
            if record.get(field):
                score += 1

        # Bonus for longer values (more detailed)
        for value in record.values():
            if value and isinstance(value, str):
                score += len(value) // 100  # 1 point per 100 chars

        return score

    def _calculate_quality_score(self, records: List[Dict]) -> float:
        """
        Calculate overall data quality score (0-100)
        """
        if not records:
            return 0.0

        total_score = 0
        max_score = len(records) * 6  # 6 important fields

        for record in records:
            total_score += self._completeness_score(record)

        return (total_score / max_score) * 100 if max_score > 0 else 0.0

    def _normalize_email(self, email: str) -> str:
        """Normalize email for comparison"""
        if not email or '@' not in email:
            return ''
        return email.lower().strip()

    def _normalize_phone(self, phone: str) -> str:
        """Normalize phone for comparison"""
        if not phone:
            return ''
        # Remove all non-digits
        digits = re.sub(r'\D', '', phone)
        # Remove leading 1 for US numbers
        if digits.startswith('1') and len(digits) == 11:
            digits = digits[1:]
        return digits

    def _normalize_url(self, url: str) -> str:
        """Normalize URL for comparison"""
        if not url:
            return ''

        # Add scheme if missing
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        try:
            parsed = urlparse(url.lower())
            # Remove www., normalize path
            netloc = parsed.netloc.replace('www.', '')
            path = parsed.path.rstrip('/')
            normalized = urlunparse((
                parsed.scheme,
                netloc,
                path,
                '', '', ''
            ))
            return normalized
        except Exception:
            return url.lower()

    def _similarity(self, str1: str, str2: str) -> float:
        """
        Calculate similarity between two strings using Levenshtein distance

        Returns:
            Similarity score (0.0-1.0)
        """
        if not str1 or not str2:
            return 0.0

        str1 = str1.lower().strip()
        str2 = str2.lower().strip()

        if str1 == str2:
            return 1.0

        # Use Levenshtein distance
        distance = self._levenshtein_distance(str1, str2)
        max_len = max(len(str1), len(str2))

        if max_len == 0:
            return 0.0

        return 1.0 - (distance / max_len)

    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """
        Calculate Levenshtein distance between two strings
        """
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)

        if len(s2) == 0:
            return len(s1)

        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                # Cost of insertions, deletions, or substitutions
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        return previous_row[-1]

    def get_report(self) -> DedupReport:
        """Get deduplication report"""
        return self.report


# Streaming deduplicator for large datasets
class StreamingDeduplicator:
    """
    Memory-efficient deduplicator for large datasets
    """

    def __init__(
        self,
        batch_size: int = 1000,
        strategy: DedupStrategy = DedupStrategy.KEEP_BEST
    ):
        """
        Initialize streaming deduplicator

        Args:
            batch_size: Number of records to process per batch
            strategy: Deduplication strategy
        """
        self.batch_size = batch_size
        self.deduplicator = Deduplicator(strategy=strategy)
        self.seen_emails: Set[str] = set()
        self.seen_phones: Set[str] = set()
        self.seen_urls: Set[str] = set()

    def process_stream(
        self,
        records_iterator,
        progress_callback: Optional[Callable] = None
    ):
        """
        Process records in batches from an iterator

        Args:
            records_iterator: Iterator yielding records
            progress_callback: Optional progress callback

        Yields:
            Deduplicated records
        """
        batch = []
        total_processed = 0

        for record in records_iterator:
            batch.append(record)

            if len(batch) >= self.batch_size:
                # Deduplicate batch
                unique = self.deduplicator.deduplicate(batch)

                # Update seen sets
                for rec in unique:
                    email = self.deduplicator._normalize_email(rec.get('email', ''))
                    if email:
                        self.seen_emails.add(email)

                    phone = self.deduplicator._normalize_phone(rec.get('phone', ''))
                    if phone:
                        self.seen_phones.add(phone)

                    url = self.deduplicator._normalize_url(
                        rec.get('url', '') or rec.get('website', '')
                    )
                    if url:
                        self.seen_urls.add(url)

                # Yield unique records
                for rec in unique:
                    yield rec

                total_processed += len(batch)
                if progress_callback:
                    progress_callback(total_processed, total_processed)

                batch = []

        # Process remaining records
        if batch:
            unique = self.deduplicator.deduplicate(batch)
            for rec in unique:
                yield rec


# Example usage and tests
if __name__ == "__main__":
    # Example 1: Basic deduplication
    print("Example 1: Basic exact deduplication")
    print("=" * 50)

    records = [
        {"email": "john@acme.com", "name": "John Doe", "company": "Acme Inc"},
        {"email": "JOHN@acme.com", "name": "John D.", "company": "Acme Inc"},  # Duplicate
        {"email": "jane@acme.com", "name": "Jane Smith", "company": "Acme Inc"},
        {"phone": "555-1234", "name": "Bob Wilson", "company": "TechCo"},
        {"phone": "5551234", "name": "Robert Wilson", "company": "TechCo"},  # Duplicate
    ]

    deduplicator = Deduplicator(strategy=DedupStrategy.KEEP_FIRST)
    unique = deduplicator.deduplicate(records)

    print(f"Original: {len(records)} records")
    print(f"Unique: {len(unique)} records")
    print(deduplicator.get_report())

    # Example 2: Fuzzy deduplication
    print("\nExample 2: Fuzzy deduplication")
    print("=" * 50)

    records = [
        {"company": "Acme Inc", "email": "info@acme.com"},
        {"company": "Acme Incorporated", "email": "contact@acme.com"},  # Similar
        {"company": "TechCorp", "email": "info@techcorp.com"},
        {"company": "Tech Corp", "email": "hello@techcorp.com"},  # Similar
    ]

    deduplicator = Deduplicator(
        strategy=DedupStrategy.MERGE,
        enable_fuzzy=True,
        fuzzy_threshold=0.85
    )
    unique = deduplicator.deduplicate(records)

    print(f"Original: {len(records)} records")
    print(f"Unique: {len(unique)} records")
    print(deduplicator.get_report())

    for i, record in enumerate(unique, 1):
        print(f"\n{i}. {record}")

    # Example 3: Cross-field deduplication
    print("\nExample 3: Cross-field deduplication (same company)")
    print("=" * 50)

    records = [
        {"email": "john@acme.com", "name": "John Doe", "company": "Acme Inc"},
        {"email": "jane@acme.com", "name": "Jane Smith", "company": "Acme Inc"},
        {"email": "bob@acme.com", "name": "Bob Wilson", "company": "Acme Inc"},
    ]

    deduplicator = Deduplicator(
        strategy=DedupStrategy.MERGE,
        enable_cross_field=True
    )
    unique = deduplicator.deduplicate(records)

    print(f"Original: {len(records)} records")
    print(f"Unique: {len(unique)} records")
    print(deduplicator.get_report())

    # Example 4: Progress callback
    print("\nExample 4: With progress tracking")
    print("=" * 50)

    records = [
        {"email": f"user{i}@example.com", "name": f"User {i}"}
        for i in range(100)
    ]
    # Add some duplicates
    records.extend([
        {"email": "user1@example.com", "name": "User 1 Duplicate"},
        {"email": "user2@example.com", "name": "User 2 Duplicate"},
    ])

    def progress(current, total):
        if current % 20 == 0:
            print(f"Progress: {current}/{total} ({current/total*100:.1f}%)")

    deduplicator = Deduplicator()
    unique = deduplicator.deduplicate(records, progress_callback=progress)

    print(deduplicator.get_report())

    # Example 5: Streaming deduplication
    print("\nExample 5: Streaming deduplication (large dataset)")
    print("=" * 50)

    def generate_records():
        """Simulate large dataset"""
        for i in range(1000):
            yield {"email": f"user{i % 500}@example.com", "name": f"User {i}"}

    streaming_dedup = StreamingDeduplicator(batch_size=100)
    unique_count = 0

    for record in streaming_dedup.process_stream(generate_records()):
        unique_count += 1

    print(f"Processed 1000 records with duplicates")
    print(f"Unique records: {unique_count}")

    print("\n" + "=" * 50)
    print("All examples complete!")
