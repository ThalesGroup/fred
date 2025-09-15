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

from __future__ import annotations
from typing import Dict, List, Sequence, Tuple, cast
import re
import logging

from langchain.schema.document import Document

from app.core.stores.vector.base_vector_store import AnnHit, BaseVectorStore, LexicalHit, LexicalSearchable, SearchFilter
from app.features.vector_search.vector_search_structures import HybridPolicy

logger = logging.getLogger(__name__)

# ---------- lightweight helpers (general-purpose) ----------

_CAPITALIZED_STOP = {
    "Who","Are","Is","The","And","Or","De","La","Le","Les","Des","Du","Pour","Et"
}

def _names_from_query(q: str) -> List[str]:
    """
    Fred rationale:
    - Hybrid must not let semantic look-alikes pass when the user asked for *people*.
    - We extract likely proper names by keeping capitalized tokens (incl. hyphens) and
      dropping trivial function words. Output is lowercased for matching.

    Examples:
      "Who are Sen and Nussbaum?" -> ["sen","nussbaum"]
      "Who is Amartya Sen"        -> ["amartya","sen"]
    """
    toks = re.findall(r"[A-Z][a-zA-Z\-]+", q)
    return [t.lower() for t in toks if t not in _CAPITALIZED_STOP]

def _has_all_names_in_doc(doc: Document, names: List[str]) -> bool:
    """
    Purpose:
      - Name evidence gate: require ALL detected names to appear somewhere in the hit.
      - We check high-signal metadata first (authors/references/title), then body text.

    Why here (in retriever, not store):
      - Zero extra round-trips to OpenSearch. Works with any BaseVectorStore.
      - Deterministic and explainable; you can expose this in UI tooltips.

    Note:
      - Case-insensitive substring matching is sufficient & robust for citations like
        "Sen 1999; Nussbaum 2011" that beat exact-phrase matching.
    """
    if not names:
        return True
    md = doc.metadata or {}
    pools: List[str] = []
    for key in ("authors", "references", "title", "section"):
        v = md.get(key)
        if isinstance(v, str):
            pools.append(v)
        elif isinstance(v, (list, tuple)):
            pools.extend([str(x) for x in v])
    pools.append(doc.page_content or "")
    hay = " \n ".join(pools).lower()
    return all(n in hay for n in names)


class HybridRetriever:
    def __init__(self, vs: BaseVectorStore) -> None:
        self.vs: BaseVectorStore = vs

    def search(
        self,
        *,
        query: str,
        scoped_document_ids: Sequence[str],
        policy: HybridPolicy,
    ) -> List[Tuple[Document, float]]:
        logger.info("Starting search with query: '%s'", query)
        if not scoped_document_ids:
            logger.info("No scoped documents provided, returning empty list")
            return []

        sf = SearchFilter(tag_ids=scoped_document_ids)
        names = _names_from_query(query)
        logger.info("Detected proper names from query: %s", names)

        # 1) ANN branch
        ann_hits: List[AnnHit] = self.vs.ann_search(query, k=policy.fetch_k_ann, search_filter=sf)
        logger.info("ANN hits returned: %s", len(ann_hits))
        ann_hits = [h for h in ann_hits if h.score >= policy.vector_min_cosine]
        logger.info("ANN hits after filtering by min cosine (%s): %s", policy.vector_min_cosine, len(ann_hits))
        if not ann_hits:
            logger.info("No ANN hits above threshold, returning empty list")
            return []

        ann_rank: Dict[str, int] = {}
        ann_map: Dict[str, Tuple[Document, float]] = {}
        for r, h in enumerate(ann_hits, start=1):
            d, s = h.document, h.score
            chunk_id = d.metadata.get("chunk_uid") or d.metadata.get("_id")
            if not isinstance(chunk_id, str) or not chunk_id:
                logger.info("Skipping ANN hit with invalid chunk_id: %s", chunk_id)
                continue
            prev = ann_rank.get(chunk_id)
            ann_rank[chunk_id] = r if prev is None else min(prev, r)
            ann_map[chunk_id] = (d, s)

        logger.info("ANN ranking completed: %s items", len(ann_rank))

        # 2) BM25 branch
        bm25_rank: Dict[str, int] = {}
        if isinstance(self.vs, LexicalSearchable):
            vs_lex = cast(LexicalSearchable, self.vs)
            bm25_hits: List[LexicalHit] = vs_lex.lexical_search(
                query, k=policy.fetch_k_bm25, search_filter=sf, operator_and=True
            )
            logger.info("BM25 hits returned: %s", len(bm25_hits))
            bm25_hits = [h for h in bm25_hits if h.score >= policy.bm25_min_score]
            bm25_rank = {h.chunk_id: r for r, h in enumerate(bm25_hits, start=1)}
            logger.info("BM25 hits after filtering by min score (%s): %s", policy.bm25_min_score, len(bm25_hits))

        if not ann_rank and not bm25_rank:
            logger.info("No ANN or BM25 hits, returning empty list")
            return []

        # 3) RRF fusion
        fused: Dict[str, float] = {}
        def add_rrf(rank_map: Dict[str, int]) -> None:
            for cid, r in rank_map.items():
                fused[cid] = fused.get(cid, 0.0) + 1.0 / (policy.rrf_k + r)

        add_rrf(ann_rank)
        if bm25_rank:
            add_rrf(bm25_rank)
        logger.info("Fused scores computed for %s chunks", len(fused))

        # 4) Sort by fused desc; tie-break with ANN cosine desc when present
        ordered_ids = sorted(
            fused.items(),
            key=lambda kv: (kv[1], ann_map.get(kv[0], (None, -1.0))[1]),
            reverse=True,
        )
        logger.info("Chunks ordered by fused score")

        # 5) De-dup, apply name gate
        out: List[Tuple[Document, float]] = []
        seen_docs: set[str] = set()
        semantic_override = getattr(policy, "name_gate_semantic_override", 0.82)
        enable_name_gate = getattr(policy, "enable_name_gate", True)

        skip_counts = {
            "not_in_ann_map": 0,
            "name_gate": 0,
            "mmr_dup": 0,
        }

        for cid, _ in ordered_ids:
            if cid not in ann_map:
                skip_counts["not_in_ann_map"] += 1
                continue
            d, ann_cos = ann_map[cid]

            if enable_name_gate and names:
                if not _has_all_names_in_doc(d, names) and ann_cos < semantic_override:
                    skip_counts["name_gate"] += 1
                    continue

            uid = d.metadata.get("document_uid")
            if policy.use_mmr:
                if uid is None or uid in seen_docs:
                    skip_counts["mmr_dup"] += 1
                    continue
                seen_docs.add(uid)

            out.append((d, ann_cos))
            if len(out) >= policy.k_final:
                logger.info("Reached k_final (%s), stopping", policy.k_final)
                break

        # Summary of skipped chunks
        for reason, count in skip_counts.items():
            if count > 0:
                logger.info("Skipped %s chunks due to %s", count, reason)

        logger.info("Search completed, returning %s documents", len(out))
        return out
