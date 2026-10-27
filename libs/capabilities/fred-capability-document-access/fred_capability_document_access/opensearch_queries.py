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

"""Pure OpenSearch request bodies and response parsing for Weaver vector search.

The space filter is only a prefilter: index metadata proves nothing, so the caller
must pass the candidates to `fred_core.documents.access.verify_candidates` before
any hit reaches the LLM.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from fred_core.documents.access import Candidate
from fred_core.store.vector_search import VectorSearchHit
from fred_sdk.contracts.models import SearchPolicyName

logger = logging.getLogger(__name__)

# Created by the Knowledge Flow vector store at startup; search only references it.
HYBRID_SEARCH_PIPELINE = "hybrid-search-pipeline"

_POLICIES = frozenset({"semantic", "strict", "hybrid"})


def mandatory_filters(space_ids: Sequence[UUID]) -> list[dict[str, Any]]:
    if not space_ids:
        raise ValueError("a search requires at least one space")
    return [
        {"terms": {"metadata.space_id": [str(space_id) for space_id in space_ids]}},
        {"term": {"metadata.retrievable": True}},
    ]


def _match(question: str, space_ids: Sequence[UUID]) -> dict[str, Any]:
    return {
        "bool": {
            "must": [{"match": {"text": {"query": question}}}],
            "filter": mandatory_filters(space_ids),
        }
    }


def _knn(vector: list[float], k: int, space_ids: Sequence[UUID]) -> dict[str, Any]:
    return {
        "knn": {
            "vector_field": {
                "vector": vector,
                "k": k,
                "filter": {"bool": {"filter": mandatory_filters(space_ids)}},
            }
        }
    }


def build_search(
    policy: SearchPolicyName | None,
    *,
    question: str,
    vector: Sequence[float] | None,
    top_k: int,
    space_ids: Sequence[UUID],
) -> tuple[dict[str, Any], dict[str, str]]:
    """Return the search body and request params; `None` means hybrid, as in Knowledge Flow."""
    resolved = policy or "hybrid"
    if resolved not in _POLICIES:
        raise ValueError(f"unknown search policy: {policy!r}")
    if top_k < 1:
        raise ValueError("top_k must be at least 1")
    if not space_ids:
        raise ValueError("a search requires at least one space")
    if resolved == "strict":
        return {"size": top_k, "query": _match(question, space_ids)}, {}
    if not vector:
        raise ValueError(f"{resolved} search requires a query vector")
    embedding = list(vector)
    if resolved == "semantic":
        body = {
            "size": top_k,
            "query": _knn(embedding, top_k, space_ids),
            "_source": True,
        }
        return body, {}
    body = {
        "size": top_k,
        "query": {
            "hybrid": {
                "queries": [
                    _match(question, space_ids),
                    _knn(embedding, top_k * 2, space_ids),
                ]
            }
        },
    }
    return body, {"search_pipeline": HYBRID_SEARCH_PIPELINE}


def _chunk_index(raw: Any) -> int | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int | float):
        return int(raw)
    if isinstance(raw, str):
        try:
            return int(raw)
        except ValueError:
            return None
    return None


def _hit(
    text: str, md: Mapping[str, Any], document_uid: str, score: float, rank: int
) -> VectorSearchHit:
    return VectorSearchHit(
        content=text,
        page=md.get("page"),
        section=md.get("section"),
        viewer_fragment=md.get("viewer_fragment"),
        slide_id=md.get("slide_id"),
        has_visual_evidence=md.get("has_visual_evidence"),
        slide_image_uri=md.get("slide_image_uri"),
        chunk_kind=md.get("chunk_kind"),
        uid=document_uid,
        title=md.get("title") or md.get("document_name") or "Unknown",
        author=md.get("author"),
        created=md.get("created"),
        modified=md.get("modified"),
        file_name=md.get("document_name"),
        file_path=md.get("source") or md.get("file_path"),
        repository=md.get("repository"),
        pull_location=md.get("pull_location"),
        language=md.get("language"),
        mime_type=md.get("mime_type"),
        type=md.get("type") or "document",
        score=score,
        rank=rank,
        chunk_index=_chunk_index(md.get("chunk_index")),
        embedding_model=str(md.get("embedding_model") or "unknown_model"),
        vector_index=md.get("vector_index") or "unknown_index",
        token_count=md.get("token_count"),
    )


def read_response(
    response: Mapping[str, Any],
) -> list[tuple[Candidate, VectorSearchHit]]:
    """Keep hit order; count and drop hits without verifiable provenance or text."""
    hits = response.get("hits", {}).get("hits", [])
    results: list[tuple[Candidate, VectorSearchHit]] = []
    dropped: Counter[str] = Counter()
    for raw in hits:
        chunk_uid = raw.get("_id")
        source = raw.get("_source")
        if (
            not isinstance(chunk_uid, str)
            or not chunk_uid
            or not isinstance(source, Mapping)
        ):
            dropped["missing_chunk_id_or_source"] += 1
            continue
        md = source.get("metadata")
        text = source.get("text")
        if not isinstance(md, Mapping) or not isinstance(text, str) or not text:
            dropped["missing_metadata_or_text"] += 1
            continue
        document_uid = md.get("document_uid")
        if not isinstance(document_uid, str) or not document_uid:
            dropped["missing_document_uid"] += 1
            continue
        # The worker writes the same id in both places; a mismatch is not trusted.
        stored_uid = md.get("chunk_uid")
        if stored_uid is not None and stored_uid != chunk_uid:
            dropped["chunk_uid_mismatch"] += 1
            continue
        score = raw.get("_score")
        hit = _hit(
            text,
            md,
            document_uid,
            float(score) if isinstance(score, int | float) else 0.0,
            len(results) + 1,
        )
        results.append((Candidate(document_uid=document_uid, chunk_uid=chunk_uid), hit))
    logger.info(
        "[VECTOR][PARSE] completed",
        extra={
            "event_name": "vector_response_parsed",
            "raw_hits": len(hits),
            "candidates": len(results),
            "drop_reasons": dict(dropped),
        },
    )
    return results
