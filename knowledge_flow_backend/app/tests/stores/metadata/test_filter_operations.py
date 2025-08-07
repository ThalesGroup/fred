# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Comprehensive test suite for structured filter operations across metadata store implementations.
"""

import pytest
from datetime import datetime, timezone

from fred_core import generate_filter_model
from app.common.document_structures import DocumentMetadata, SourceType
from app.core.stores.metadata.duckdb_metadata_store import DuckdbMetadataStore


# Create dynamic filter model for testing
DocumentFilter = generate_filter_model(DocumentMetadata, name="DocumentFilter")


@pytest.fixture
def sample_documents():
    """Create a diverse set of test documents for filter testing."""
    base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    return [
        DocumentMetadata(
            source_type=SourceType.PUSH,
            document_uid="doc1",
            document_name="Annual Report 2024.pdf",
            title="Annual Financial Report",
            author="Finance Team",
            tags=["finance", "annual", "report"],
            category="Financial",
            keywords="revenue profit analysis",
            created=base_time,
            retrievable=True,
        ),
        DocumentMetadata(
            source_type=SourceType.PULL,
            document_uid="doc2",
            document_name="Quarterly Update Q1.pdf",
            title="Q1 Business Update",
            author="Operations Team",
            tags=["quarterly", "business", "update"],
            category="Business",
            keywords="operations metrics KPIs",
            created=base_time.replace(month=2),
            retrievable=False,
        ),
        DocumentMetadata(
            source_type=SourceType.PUSH,
            document_uid="doc3",
            document_name="Technical Specs v2.1.pdf",
            title="System Technical Specifications",
            author="Engineering Team",
            tags=["technical", "specifications", "system"],
            category="Technical",
            keywords="architecture design patterns",
            created=base_time.replace(month=3),
            retrievable=True,
        ),
        DocumentMetadata(
            source_type=SourceType.PULL,
            document_uid="doc4",
            document_name="Meeting Notes - Jan.pdf",
            title="January Team Meeting Notes",
            author="HR Team",
            tags=["meeting", "notes", "team"],
            category="Administrative",
            keywords="discussion action items",
            created=base_time.replace(month=4),
            retrievable=True,
        ),
        DocumentMetadata(
            source_type=SourceType.PUSH,
            document_uid="doc5",
            document_name="Budget Proposal.pdf",
            title="2024 Budget Allocation Proposal",
            author="Finance Team",
            tags=["budget", "finance", "proposal"],
            category="Financial",
            keywords="allocation spending forecast",
            created=base_time.replace(month=5),
            retrievable=False,
        ),
    ]


@pytest.fixture
def metadata_store_with_data(tmp_path, sample_documents):
    """Create a metadata store populated with test data."""
    store = DuckdbMetadataStore(tmp_path / "test.db")

    for doc in sample_documents:
        store.save_metadata(doc)

    return store


class TestBasicFilterOperations:
    """Test basic filter operations like exact match, in, etc."""

    def test_exact_match_filter(self, metadata_store_with_data):
        """Test exact match filtering (default eq operation)."""
        results = metadata_store_with_data.get_all_metadata({"author": "Finance Team"})
        assert len(results) == 2
        assert all(doc.author == "Finance Team" for doc in results)

    def test_boolean_filter(self, metadata_store_with_data):
        """Test boolean field filtering."""
        results = metadata_store_with_data.get_all_metadata({"retrievable": True})
        assert len(results) == 3
        assert all(doc.retrievable for doc in results)

        results = metadata_store_with_data.get_all_metadata({"retrievable": False})
        assert len(results) == 2
        assert all(not doc.retrievable for doc in results)

    def test_in_operation(self, metadata_store_with_data):
        """Test 'in' operation for multiple values."""
        results = metadata_store_with_data.get_all_metadata({"category__in": ["Financial", "Technical"]})
        assert len(results) == 3
        categories = {doc.category for doc in results}
        assert categories == {"Financial", "Technical"}


class TestStringFilterOperations:
    """Test string-specific filter operations."""

    def test_icontains_operation(self, metadata_store_with_data):
        """Test case-insensitive substring matching."""
        results = metadata_store_with_data.get_all_metadata({"title__icontains": "report"})
        assert len(results) == 1
        assert "Report" in results[0].title

        # Test case insensitivity
        results = metadata_store_with_data.get_all_metadata({"title__icontains": "ANNUAL"})
        assert len(results) == 1
        assert "Annual" in results[0].title


class TestDateTimeFilterOperations:
    """Test datetime comparison operations."""

    def test_date_greater_than(self, metadata_store_with_data):
        """Test greater than date filtering."""
        cutoff_date = datetime(2024, 2, 15, tzinfo=timezone.utc)
        results = metadata_store_with_data.get_all_metadata({"created__gt": cutoff_date})
        assert len(results) == 3
        # Convert to UTC for comparison if needed
        for doc in results:
            doc_created = doc.created
            if doc_created.tzinfo is None:
                doc_created = doc_created.replace(tzinfo=timezone.utc)
            assert doc_created > cutoff_date

    def test_date_less_than_equal(self, metadata_store_with_data):
        """Test less than or equal date filtering."""
        cutoff_date = datetime(2024, 3, 1, tzinfo=timezone.utc)
        results = metadata_store_with_data.get_all_metadata({"created__lte": cutoff_date})
        assert len(results) == 2
        # Convert to UTC for comparison if needed
        for doc in results:
            doc_created = doc.created
            if doc_created.tzinfo is None:
                doc_created = doc_created.replace(tzinfo=timezone.utc)
            assert doc_created <= cutoff_date


class TestArrayFilterOperations:
    """Test array/list filtering operations."""

    def test_tags_contains(self, metadata_store_with_data):
        """Test tags contains operation."""
        results = metadata_store_with_data.get_all_metadata({"tags__contains": "finance"})
        assert len(results) == 2
        assert all("finance" in doc.tags for doc in results)

    def test_tags_overlap(self, metadata_store_with_data):
        """Test tags overlap operation."""
        results = metadata_store_with_data.get_all_metadata({"tags__overlap": ["technical", "meeting", "nonexistent"]})
        assert len(results) == 2

        # Check that results contain at least one of the overlap tags
        for doc in results:
            assert any(tag in doc.tags for tag in ["technical", "meeting"])


class TestCombinedFilterOperations:
    """Test combining multiple filter operations."""

    def test_multiple_filters_and_logic(self, metadata_store_with_data):
        """Test multiple filters work with AND logic."""
        results = metadata_store_with_data.get_all_metadata({"category": "Financial", "retrievable": True})
        assert len(results) == 1
        assert results[0].category == "Financial"
        assert results[0].retrievable is True

    def test_complex_combined_filters(self, metadata_store_with_data):
        """Test complex combination of different filter types."""
        cutoff_date = datetime(2024, 2, 1, tzinfo=timezone.utc)
        results = metadata_store_with_data.get_all_metadata(
            {
                "created__gt": cutoff_date,
                "tags__contains": "team",
                "retrievable": True,
            }
        )
        assert len(results) == 1
        doc = results[0]
        # Handle timezone comparison
        doc_created = doc.created
        if doc_created.tzinfo is None:
            doc_created = doc_created.replace(tzinfo=timezone.utc)
        assert doc_created > cutoff_date
        assert "team" in doc.tags
        assert doc.retrievable is True


class TestEdgeCasesAndErrorHandling:
    """Test edge cases and error conditions."""

    def test_empty_filters(self, metadata_store_with_data):
        """Test empty filter dictionary returns all documents."""
        results = metadata_store_with_data.get_all_metadata({})
        assert len(results) == 5

    def test_none_values_ignored(self, metadata_store_with_data):
        """Test that None filter values are ignored."""
        results = metadata_store_with_data.get_all_metadata({"author": "Finance Team", "nonexistent_field": None})
        assert len(results) == 2
        assert all(doc.author == "Finance Team" for doc in results)

    def test_nonexistent_field_filter(self, metadata_store_with_data):
        """Test filtering on nonexistent fields raises appropriate error."""
        # DuckDB should raise an error for nonexistent columns
        with pytest.raises(Exception):  # Could be BinderException or other DB error
            metadata_store_with_data.get_all_metadata({"nonexistent_field": "some_value"})

    def test_no_matching_results(self, metadata_store_with_data):
        """Test filters that match no documents."""
        results = metadata_store_with_data.get_all_metadata({"author": "Nonexistent Author"})
        assert len(results) == 0
