# Copyright Thales 2026
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

"""Offline tests for the OpenSearch request bodies and response parsing."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from fred_capability_document_access.opensearch_queries import (
    HYBRID_SEARCH_PIPELINE,
    build_search,
    mandatory_filters,
    read_response,
)
from fred_core.documents.access import Candidate

ORG = UUID("00000000-0000-0000-0000-000000000001")
TEAM = UUID("00000000-0000-0000-0000-000000000002")
SPACES = (ORG, TEAM)
VECTOR = [0.1, 0.2, 0.3]

FILTERS = [
    {"terms": {"metadata.space_id": [str(ORG), str(TEAM)]}},
    {"term": {"metadata.retrievable": True}},
]
MATCH = {
    "bool": {
        "must": [{"match": {"text": {"query": "budget"}}}],
        "filter": FILTERS,
    }
}


def _knn(k: int) -> dict[str, Any]:
    return {
        "knn": {
            "vector_field": {
                "vector": VECTOR,
                "k": k,
                "filter": {"bool": {"filter": FILTERS}},
            }
        }
    }


def _search(policy: Any, **overrides: Any) -> tuple[dict[str, Any], dict[str, str]]:
    arguments: dict[str, Any] = {
        "question": "budget",
        "vector": VECTOR,
        "top_k": 5,
        "space_ids": SPACES,
    }
    arguments.update(overrides)
    return build_search(policy, **arguments)


def test_mandatory_filters_restrict_space_and_retrievable() -> None:
    assert mandatory_filters(SPACES) == FILTERS


def test_semantic_body() -> None:
    assert _search("semantic") == ({"size": 5, "query": _knn(5), "_source": True}, {})


def test_strict_body_ignores_vector() -> None:
    assert _search("strict", vector=None) == ({"size": 5, "query": MATCH}, {})


def test_hybrid_body_filters_each_subquery_and_uses_pipeline() -> None:
    body, params = _search("hybrid")

    assert body == {"size": 5, "query": {"hybrid": {"queries": [MATCH, _knn(10)]}}}
    assert params == {"search_pipeline": HYBRID_SEARCH_PIPELINE}
    match, knn = body["query"]["hybrid"]["queries"]
    assert match["bool"]["filter"] == FILTERS
    assert knn["knn"]["vector_field"]["filter"]["bool"]["filter"] == FILTERS


def test_missing_policy_defaults_to_hybrid() -> None:
    assert _search(None) == _search("hybrid")


@pytest.mark.parametrize(
    ("policy", "overrides"),
    [
        ("hybrid", {"space_ids": ()}),
        ("strict", {"space_ids": ()}),
        ("fuzzy", {}),
        ("semantic", {"vector": None}),
        ("hybrid", {"vector": []}),
        ("strict", {"top_k": 0}),
    ],
)
def test_invalid_requests_are_rejected(policy: Any, overrides: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        _search(policy, **overrides)


def test_mandatory_filters_reject_empty_spaces() -> None:
    with pytest.raises(ValueError):
        mandatory_filters(())


def _raw(
    chunk_uid: str | None,
    *,
    score: Any = 1.0,
    text: Any = "chunk text",
    **metadata: Any,
) -> dict[str, Any]:
    md: dict[str, Any] = {"document_uid": "doc-1", "chunk_uid": chunk_uid}
    md.update(metadata)
    raw: dict[str, Any] = {"_score": score, "_source": {"text": text, "metadata": md}}
    if chunk_uid is not None:
        raw["_id"] = chunk_uid
    return raw


def _response(*hits: dict[str, Any]) -> dict[str, Any]:
    return {"hits": {"hits": list(hits)}}


def test_read_response_maps_hit_fields() -> None:
    raw = _raw(
        "c-1",
        score=0.75,
        title="Budget 2026",
        document_name="budget.pdf",
        page=3,
        section="Totals",
        chunk_index="7",
        mime_type="application/pdf",
        source="finance/budget.pdf",
        embedding_model="text-embedding-3-small",
        vector_index="vectors",
        token_count=12,
        tag_ids=["legacy-tag"],
    )

    [(candidate, hit)] = read_response(_response(raw))

    assert candidate == Candidate(document_uid="doc-1", chunk_uid="c-1")
    assert hit.content == "chunk text"
    assert hit.uid == "doc-1"
    assert hit.title == "Budget 2026"
    assert hit.file_name == "budget.pdf"
    assert hit.file_path == "finance/budget.pdf"
    assert (hit.page, hit.section, hit.mime_type, hit.type) == (
        3,
        "Totals",
        "application/pdf",
        "document",
    )
    assert (hit.score, hit.rank, hit.chunk_index) == (0.75, 1, 7)
    assert (hit.embedding_model, hit.vector_index, hit.token_count) == (
        "text-embedding-3-small",
        "vectors",
        12,
    )
    assert hit.tag_ids == [] and hit.tag_names == [] and hit.tag_full_paths == []
    assert (
        hit.preview_url is None
        and hit.preview_at_url is None
        and hit.citation_url is None
    )
    assert hit.retrieved_at is None


def test_read_response_keeps_order_and_ranks_kept_hits() -> None:
    results = read_response(
        _response(
            _raw("c-1", score=0.9),
            _raw(None),
            _raw("c-2", score=0.8, document_name="b.pdf"),
            _raw("c-3", score=0.7, chunk_index="x"),
        )
    )

    assert [candidate.chunk_uid for candidate, _ in results] == ["c-1", "c-2", "c-3"]
    assert [hit.rank for _, hit in results] == [1, 2, 3]
    assert results[1][1].title == "b.pdf"
    assert results[0][1].title == "Unknown"
    assert results[2][1].chunk_index is None


def test_read_response_accepts_missing_metadata_chunk_uid() -> None:
    raw = _raw("c-1")
    del raw["_source"]["metadata"]["chunk_uid"]

    assert [candidate.chunk_uid for candidate, _ in read_response(_response(raw))] == [
        "c-1"
    ]


@pytest.mark.parametrize(
    "raw",
    [
        _raw(None),
        _raw("c-1", document_uid=None),
        _raw("c-1", text=""),
        _raw("c-1", text=None),
        {
            "_id": "c-1",
            "_score": 1.0,
            "_source": {"metadata": {"document_uid": "doc-1"}},
        },
        {
            "_id": "c-1",
            "_score": 1.0,
            "_source": {
                "text": "t",
                "metadata": {"document_uid": "doc-1", "chunk_uid": "c-2"},
            },
        },
    ],
    ids=[
        "no-id",
        "no-document-uid",
        "empty-text",
        "null-text",
        "missing-text",
        "chunk-uid-mismatch",
    ],
)
def test_read_response_drops_unverifiable_hits(raw: dict[str, Any]) -> None:
    assert read_response(_response(raw)) == []


def test_read_response_handles_empty_hits() -> None:
    assert read_response(_response()) == []
    assert read_response({}) == []
