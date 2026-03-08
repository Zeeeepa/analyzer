"""
Tests for Deduplicator module

Run with: python -m pytest agent/test_deduplicator.py -v
Or: python agent/test_deduplicator.py
"""

import pytest
from agent.deduplicator import (
    Deduplicator,
    DedupStrategy,
    StreamingDeduplicator,
    DedupReport
)


class TestExactDeduplication:
    """Test exact match deduplication"""

    def test_email_deduplication_case_insensitive(self):
        """Email deduplication should be case-insensitive"""
        records = [
            {"email": "john@example.com", "name": "John"},
            {"email": "JOHN@example.com", "name": "John Duplicate"},
            {"email": "jane@example.com", "name": "Jane"},
        ]

        deduplicator = Deduplicator(strategy=DedupStrategy.KEEP_FIRST)
        unique = deduplicator.deduplicate(records)

        assert len(unique) == 2
        assert unique[0]["email"] == "john@example.com"
        assert unique[1]["email"] == "jane@example.com"

    def test_phone_normalization(self):
        """Phone deduplication should normalize formats"""
        records = [
            {"phone": "555-123-4567", "name": "John"},
            {"phone": "(555) 123-4567", "name": "John Duplicate"},
            {"phone": "5551234567", "name": "John Duplicate 2"},
            {"phone": "1-555-123-4567", "name": "John Duplicate 3"},
        ]

        deduplicator = Deduplicator(strategy=DedupStrategy.KEEP_FIRST)
        unique = deduplicator.deduplicate(records)

        assert len(unique) == 1

    def test_url_normalization(self):
        """URL deduplication should normalize URLs"""
        records = [
            {"url": "https://www.example.com", "name": "Site 1"},
            {"url": "http://example.com", "name": "Site 2"},
            {"url": "example.com", "name": "Site 3"},
            {"url": "https://example.com/", "name": "Site 4"},
        ]

        deduplicator = Deduplicator(strategy=DedupStrategy.KEEP_FIRST)
        unique = deduplicator.deduplicate(records)

        assert len(unique) == 1

    def test_multiple_fields_deduplication(self):
        """Should deduplicate if ANY field matches"""
        records = [
            {"email": "john@example.com", "phone": "5551234567", "name": "John"},
            {"email": "different@example.com", "phone": "5551234567", "name": "Same Phone"},
            {"email": "john@example.com", "phone": "9999999999", "name": "Same Email"},
        ]

        deduplicator = Deduplicator(strategy=DedupStrategy.KEEP_FIRST)
        unique = deduplicator.deduplicate(records)

        # All are duplicates of the first record
        assert len(unique) == 1


class TestFuzzyDeduplication:
    """Test fuzzy matching deduplication"""

    def test_company_name_similarity(self):
        """Should match similar company names"""
        records = [
            {"company": "Acme Inc", "email": "info@acme.com"},
            {"company": "Acme Incorporated", "email": "contact@acme.com"},
            {"company": "TechCorp", "email": "info@techcorp.com"},
        ]

        deduplicator = Deduplicator(
            strategy=DedupStrategy.KEEP_FIRST,
            enable_fuzzy=True,
            fuzzy_threshold=0.80
        )
        unique = deduplicator.deduplicate(records)

        # Acme Inc and Acme Incorporated should be merged
        assert len(unique) == 2

    def test_person_name_similarity(self):
        """Should match similar person names"""
        records = [
            {"name": "John Smith", "company": "Acme"},
            {"name": "Jon Smith", "company": "Acme"},
            {"name": "Jane Doe", "company": "TechCo"},
        ]

        deduplicator = Deduplicator(
            strategy=DedupStrategy.KEEP_FIRST,
            enable_fuzzy=True,
            fuzzy_threshold=0.85
        )
        unique = deduplicator.deduplicate(records)

        # John and Jon should be merged
        assert len(unique) == 2

    def test_fuzzy_threshold(self):
        """Fuzzy threshold should control matching strictness"""
        records = [
            {"company": "Microsoft Corporation", "email": "info@microsoft.com"},
            {"company": "Microsoft Corp", "email": "contact@microsoft.com"},
        ]

        # Strict threshold - no match
        deduplicator_strict = Deduplicator(
            strategy=DedupStrategy.KEEP_FIRST,
            enable_fuzzy=True,
            fuzzy_threshold=0.99
        )
        unique_strict = deduplicator_strict.deduplicate(records)
        assert len(unique_strict) == 2

        # Lenient threshold - match
        deduplicator_lenient = Deduplicator(
            strategy=DedupStrategy.KEEP_FIRST,
            enable_fuzzy=True,
            fuzzy_threshold=0.80
        )
        unique_lenient = deduplicator_lenient.deduplicate(records)
        assert len(unique_lenient) == 1


class TestDedupStrategies:
    """Test different deduplication strategies"""

    def test_keep_first_strategy(self):
        """KEEP_FIRST should keep first occurrence"""
        records = [
            {"email": "john@example.com", "name": "John", "company": ""},
            {"email": "john@example.com", "name": "John Doe", "company": "Acme Inc"},
        ]

        deduplicator = Deduplicator(strategy=DedupStrategy.KEEP_FIRST)
        unique = deduplicator.deduplicate(records)

        assert len(unique) == 1
        assert unique[0]["name"] == "John"  # First record kept
        assert unique[0]["company"] == ""

    def test_keep_best_strategy(self):
        """KEEP_BEST should keep most complete record"""
        records = [
            {"email": "john@example.com", "name": "John", "company": ""},
            {"email": "john@example.com", "name": "John Doe", "company": "Acme Inc", "phone": "555-1234"},
        ]

        deduplicator = Deduplicator(strategy=DedupStrategy.KEEP_BEST)
        unique = deduplicator.deduplicate(records)

        assert len(unique) == 1
        assert unique[0]["name"] == "John Doe"  # More complete record kept
        assert unique[0]["company"] == "Acme Inc"
        assert unique[0]["phone"] == "555-1234"

    def test_merge_strategy(self):
        """MERGE should combine data from all records"""
        records = [
            {"email": "john@example.com", "name": "John", "company": ""},
            {"email": "john@example.com", "name": "John Doe", "company": "Acme Inc"},
            {"email": "john@example.com", "phone": "555-1234", "address": "123 Main St"},
        ]

        deduplicator = Deduplicator(strategy=DedupStrategy.MERGE)
        unique = deduplicator.deduplicate(records)

        assert len(unique) == 1
        # Should have fields from all records
        assert unique[0]["name"] == "John Doe"  # Longest value
        assert unique[0]["company"] == "Acme Inc"
        assert unique[0]["phone"] == "555-1234"
        assert unique[0]["address"] == "123 Main St"


class TestCrossFieldDeduplication:
    """Test cross-field deduplication"""

    def test_same_domain_merging(self):
        """Should merge records from same email domain"""
        records = [
            {"email": "john@acme.com", "name": "John", "company": "Acme Inc"},
            {"email": "jane@acme.com", "name": "Jane", "company": "Acme Inc"},
            {"email": "bob@acme.com", "name": "Bob", "company": "Acme Inc"},
        ]

        deduplicator = Deduplicator(
            strategy=DedupStrategy.MERGE,
            enable_cross_field=True
        )
        unique = deduplicator.deduplicate(records)

        # Should merge records from same company
        assert len(unique) == 1
        assert "_sources" in unique[0]

    def test_different_companies_no_merge(self):
        """Should NOT merge records from different companies"""
        records = [
            {"email": "john@gmail.com", "name": "John", "company": "Acme Inc"},
            {"email": "jane@gmail.com", "name": "Jane", "company": "TechCo"},
        ]

        deduplicator = Deduplicator(
            strategy=DedupStrategy.MERGE,
            enable_cross_field=True
        )
        unique = deduplicator.deduplicate(records)

        # Should keep separate (different companies)
        assert len(unique) == 2


class TestDedupReport:
    """Test deduplication reporting"""

    def test_report_statistics(self):
        """Report should track correct statistics"""
        records = [
            {"email": "john@example.com", "name": "John"},
            {"email": "john@example.com", "name": "John Duplicate"},
            {"email": "jane@example.com", "name": "Jane"},
        ]

        deduplicator = Deduplicator(strategy=DedupStrategy.KEEP_FIRST)
        unique = deduplicator.deduplicate(records)
        report = deduplicator.get_report()

        assert report.total_records == 3
        assert report.unique_records == 2
        assert report.duplicates_found == 1
        assert report.exact_duplicates == 1

    def test_data_quality_score(self):
        """Report should calculate data quality score"""
        # Complete records
        complete_records = [
            {
                "email": "john@example.com",
                "phone": "555-1234",
                "name": "John Doe",
                "company": "Acme Inc",
                "website": "https://acme.com",
                "address": "123 Main St"
            }
        ]

        # Incomplete records
        incomplete_records = [
            {"email": "john@example.com", "name": "John"}
        ]

        deduplicator = Deduplicator()

        unique_complete = deduplicator.deduplicate(complete_records)
        report_complete = deduplicator.get_report()

        unique_incomplete = deduplicator.deduplicate(incomplete_records)
        report_incomplete = deduplicator.get_report()

        assert report_complete.data_quality_score > report_incomplete.data_quality_score


class TestStreamingDeduplication:
    """Test streaming deduplication for large datasets"""

    def test_streaming_deduplication(self):
        """Should handle large datasets efficiently"""
        def generate_records():
            for i in range(100):
                yield {"email": f"user{i % 50}@example.com", "name": f"User {i}"}

        streaming_dedup = StreamingDeduplicator(batch_size=10)
        unique_records = list(streaming_dedup.process_stream(generate_records()))

        # 100 records with 50 unique emails
        assert len(unique_records) == 50

    def test_streaming_with_progress(self):
        """Should support progress callbacks"""
        def generate_records():
            for i in range(50):
                yield {"email": f"user{i}@example.com"}

        progress_calls = []

        def progress_callback(current, total):
            progress_calls.append((current, total))

        streaming_dedup = StreamingDeduplicator(batch_size=10)
        list(streaming_dedup.process_stream(generate_records(), progress_callback))

        # Should have progress updates
        assert len(progress_calls) > 0


class TestHelperFunctions:
    """Test helper functions"""

    def test_levenshtein_distance(self):
        """Test Levenshtein distance calculation"""
        deduplicator = Deduplicator()

        # Identical strings
        assert deduplicator._levenshtein_distance("hello", "hello") == 0

        # One character difference
        assert deduplicator._levenshtein_distance("hello", "hallo") == 1

        # Completely different
        assert deduplicator._levenshtein_distance("hello", "world") == 4

    def test_similarity_score(self):
        """Test similarity score calculation"""
        deduplicator = Deduplicator()

        # Identical strings
        assert deduplicator._similarity("Acme Inc", "Acme Inc") == 1.0

        # Similar strings
        similarity = deduplicator._similarity("Acme Inc", "Acme Incorporated")
        assert 0.7 <= similarity <= 0.9

        # Different strings
        similarity = deduplicator._similarity("Acme Inc", "TechCorp")
        assert similarity < 0.5

    def test_completeness_score(self):
        """Test record completeness scoring"""
        deduplicator = Deduplicator()

        complete = {
            "email": "john@example.com",
            "phone": "555-1234",
            "name": "John Doe",
            "company": "Acme Inc",
            "website": "https://acme.com",
            "address": "123 Main St"
        }

        incomplete = {
            "email": "john@example.com",
            "name": "John"
        }

        assert deduplicator._completeness_score(complete) > deduplicator._completeness_score(incomplete)


class TestEdgeCases:
    """Test edge cases and error handling"""

    def test_empty_records(self):
        """Should handle empty record list"""
        deduplicator = Deduplicator()
        unique = deduplicator.deduplicate([])
        assert unique == []

    def test_single_record(self):
        """Should handle single record"""
        records = [{"email": "john@example.com"}]
        deduplicator = Deduplicator()
        unique = deduplicator.deduplicate(records)
        assert len(unique) == 1

    def test_records_with_missing_fields(self):
        """Should handle records with missing fields"""
        records = [
            {"email": "john@example.com"},
            {"phone": "555-1234"},
            {"name": "Jane"},
            {},  # Empty record
        ]

        deduplicator = Deduplicator()
        unique = deduplicator.deduplicate(records)
        assert len(unique) == 4  # All unique (no common fields)

    def test_records_with_none_values(self):
        """Should handle None values gracefully"""
        records = [
            {"email": None, "name": "John"},
            {"email": None, "name": "Jane"},
        ]

        deduplicator = Deduplicator()
        unique = deduplicator.deduplicate(records)
        assert len(unique) == 2  # Both kept (None != None for dedup)


class TestRealWorldScenarios:
    """Test real-world deduplication scenarios"""

    def test_lead_generation_deduplication(self):
        """Test typical lead generation scenario"""
        leads = [
            {
                "email": "john.doe@acme.com",
                "name": "John Doe",
                "company": "Acme Inc",
                "source": "LinkedIn"
            },
            {
                "email": "john.doe@acme.com",
                "phone": "555-1234",
                "company": "Acme Inc",
                "source": "Website"
            },
            {
                "email": "jane.smith@techcorp.com",
                "name": "Jane Smith",
                "company": "TechCorp",
                "source": "Facebook"
            },
        ]

        deduplicator = Deduplicator(strategy=DedupStrategy.MERGE)
        unique = deduplicator.deduplicate(leads)

        assert len(unique) == 2
        # John's merged record should have both email and phone
        john_record = next(r for r in unique if r["email"] == "john.doe@acme.com")
        assert "phone" in john_record
        assert "_sources" in john_record

    def test_contact_enrichment_deduplication(self):
        """Test contact enrichment scenario"""
        contacts = [
            {
                "email": "ceo@startup.com",
                "name": "Alice Johnson",
                "title": "CEO"
            },
            {
                "email": "alice@startup.com",
                "name": "Alice J.",
                "company": "Startup Inc"
            },
            {
                "phone": "555-9999",
                "name": "Alice Johnson",
                "company": "Startup Inc"
            },
        ]

        deduplicator = Deduplicator(
            strategy=DedupStrategy.MERGE,
            enable_fuzzy=True,
            fuzzy_threshold=0.85
        )
        unique = deduplicator.deduplicate(contacts)

        # Alice's records should be merged (fuzzy name match)
        assert len(unique) <= 2


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
