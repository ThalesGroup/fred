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
Test suite for VectorSearchService in vector_search_service.py.

Covers:
- Similarity search functionality with nominal, failure, and edge cases.
- Behavior when no question is given or k=0.
- Mocked vector store and embedder via DummyContext.
"""

import pytest
from langchain.schema.document import Document
from app.features.vector_search.service import VectorSearchService
from app.features.vector_search import service


class DummyVectorStore:
    """
    Mock vector store that simulates similarity search with dummy results.
    Raises ValueError on empty question.
    """

    def similarity_search_with_score(self, question, k=10):
        if not question:
            raise ValueError("Question must not be empty")
        return [(Document(page_content="answer 1", metadata={}), 0.9)] * min(k, 2)


class DummyContext:
    """
    Mock application context that returns dummy embedder and vector store.
    """

    def get_embedder(self):
        return "dummy_embedder"

    def get_vector_store(self, embedder):
        return DummyVectorStore()


# ----------------------------
# ✅ Nominal Cases
# ----------------------------


def test_similarity_search_success(monkeypatch):
    """Test: performs similarity search with a valid question and k=2.
    Asserts returned objects are Document-score tuples."""
    monkeypatch.setattr(service.ApplicationContext, "get_instance", DummyContext)
    vector_svc = VectorSearchService()
    results = vector_svc.similarity_search_with_score("What is AI?", k=2)
    assert isinstance(results, list)
    assert all(isinstance(doc, tuple) and isinstance(doc[0], Document) for doc in results)
    assert len(results) == 2


# ----------------------------
# ❌ Failure Cases
# ----------------------------


def test_similarity_search_empty_question(monkeypatch):
    """Test: raises ValueError if question is an empty string."""
    monkeypatch.setattr(service.ApplicationContext, "get_instance", DummyContext)
    vector_svc = VectorSearchService()
    with pytest.raises(ValueError):
        vector_svc.similarity_search_with_score("", k=3)


# ----------------------------
# ⚠️ Edge Cases
# ----------------------------


def test_similarity_search_zero_k(monkeypatch):
    """Test: returns empty list when k=0, a valid edge case."""
    monkeypatch.setattr(service.ApplicationContext, "get_instance", DummyContext)
    vector_svc = VectorSearchService()
    results = vector_svc.similarity_search_with_score("Explain edge case.", k=0)
    assert isinstance(results, list)
    assert results == []
