# app/core/retrieval/hybrid_retriever.py
from __future__ import annotations
from typing import Dict, List, Sequence, Tuple, cast

from langchain.schema.document import Document

from app.core.stores.vector.base_vector_store import AnnHit, BaseVectorStore, LexicalHit, LexicalSearchable, SearchFilter
from app.features.vector_search.vector_search_structures import HybridPolicy


class HybridRetriever:
    """
    Fred — Hybrid Retriever (default).
    Rationale:
      - Fuse ANN (semantic) with BM25 (lexical) via RRF.
      - Gate weak hits; de-duplicate per document to avoid many slices.
      - If the vector store has no lexical capability, gracefully fall back to Semantic.
    """

    def __init__(self, vs: BaseVectorStore) -> None:
        self.vs: BaseVectorStore = vs

    def search(
        self,
        *,
        query: str,
        scoped_document_ids: Sequence[str],
        policy: HybridPolicy,
    ) -> List[Tuple[Document, float]]:
        if not scoped_document_ids:
            return []

        sf = SearchFilter(tag_ids=scoped_document_ids)

        # 1) ANN branch (with gate)
        ann_hits: List[AnnHit] = self.vs.ann_search(query, k=policy.fetch_k_ann, search_filter=sf)
        ann_hits = [h for h in ann_hits if h.score >= policy.vector_min_cosine]
        if not ann_hits:
            return []

        ann_rank: Dict[str, int] = {}
        ann_map: Dict[str, Tuple[Document, float]] = {}
        for r, h in enumerate(ann_hits, start=1):
            d, s = h.document, h.score
            chunk_id = d.metadata.get("chunk_uid") or d.metadata.get("_id")
            if not isinstance(chunk_id, str) or not chunk_id:
                # skip malformed hits without a stable chunk id
                continue
            # keep best (lowest) rank if chunk_id appears multiple times
            prev = ann_rank.get(chunk_id)
            ann_rank[chunk_id] = r if prev is None else min(prev, r)
            ann_map[chunk_id] = (d, s)

        # 2) BM25 branch (with gate) — only if store supports lexical
        bm25_rank: Dict[str, int] = {}
        if isinstance(self.vs, LexicalSearchable):
            vs_lex = cast(LexicalSearchable, self.vs)
            bm25_hits: List[LexicalHit] = vs_lex.lexical_search(
                query, k=policy.fetch_k_bm25, search_filter=sf, operator_and=True
            )
            # gate BM25
            bm25_hits = [h for h in bm25_hits if h.score >= policy.bm25_min_score]
            bm25_rank = {h.chunk_id: r for r, h in enumerate(bm25_hits, start=1)}

        # If neither branch has anything ranked, bail early
        if not ann_rank and not bm25_rank:
            return []

        # 3) RRF fusion (ANN always contributes; BM25 contributes when present)
        fused: Dict[str, float] = {}
        def add_rrf(rank_map: Dict[str, int]) -> None:
            for cid, r in rank_map.items():
                fused[cid] = fused.get(cid, 0.0) + 1.0 / (policy.rrf_k + r)

        add_rrf(ann_rank)
        if bm25_rank:
            add_rrf(bm25_rank)

        # 4) Sort by fused desc; tie-break with ANN cosine desc when present
        ordered_ids = sorted(
            fused.items(),
            key=lambda kv: (kv[1], ann_map.get(kv[0], (None, -1.0))[1]),
            reverse=True,
        )

        # 5) De-dup per document_uid; return top k_final as (Document, ann_cosine)
        out: List[Tuple[Document, float]] = []
        seen_docs: set[str] = set()

        def _doc_uid(md: dict) -> str | None:
            uid = md.get("document_uid")
            return uid if isinstance(uid, str) and uid else None

        for cid, _ in ordered_ids:
            # only materialize ids that exist in ANN map (we have Documents there)
            if cid not in ann_map:
                continue
            d, ann_cos = ann_map[cid]
            uid = _doc_uid(d.metadata)
            if policy.use_mmr:
                if uid is None or uid in seen_docs:
                    continue
                seen_docs.add(uid)
            out.append((d, ann_cos))
            if len(out) >= policy.k_final:
                break

        return out
