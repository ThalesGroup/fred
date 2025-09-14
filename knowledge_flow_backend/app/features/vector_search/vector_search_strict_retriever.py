# app/core/retrieval/strict_retriever.py
# Copyright Thales 2025
# Licensed under the Apache License, Version 2.0 (the "License"); ...

from __future__ import annotations
from typing import List, Sequence, Set, cast
from langchain.schema.document import Document

from app.core.stores.vector.base_vector_store import BaseVectorStore, LexicalSearchable, SearchFilter
from app.features.vector_search.vector_search_structures import SearchPolicy  # your pydantic/dataclass with thresholds


class StrictRetriever:
    """
    Fred — Strict Retriever (precision-first).
    Why:
      - We’d rather return nothing than surface off-topic chunks.
      - Require agreement between ANN (semantic) and BM25 (lexical),
        and optionally an exact phrase hit.
      - Hard-scope by document_uids (library scope) provided at call site.
    Contract:
      - Depends on a vector store that supports lexical search (LexicalSearchable).
      - Returns ≤ policy.k_final high-confidence chunks, else [].
    """

    def __init__(self, vs: BaseVectorStore):
        # Strict requires lexical capability (BM25/phrase).
        if not isinstance(vs, LexicalSearchable):
            raise TypeError(
                "StrictRetriever requires a LexicalSearchable vector store "
                "(e.g., OpenSearch adapter)."
            )
        # For the type checker, keep both views: BaseVectorStore (ANN) + LexicalSearchable (lexical/phrase)
        self._vs_ann: BaseVectorStore = vs
        self._vs_lex: LexicalSearchable = cast(LexicalSearchable, vs)

    def search(
        self,
        *,
        query: str,
        scoped_document_ids: Sequence[str],
        policy: SearchPolicy,
    ) -> List[Document]:
        """
        Returns a short, high-confidence list of Documents or [] if below threshold.

        Gates:
          - ANN cosine >= policy.vector_min_cosine
          - BM25 score >= policy.bm25_min_score
          - If policy.require_phrase_hit: exact phrase match in text/title/section
        De-dup:
          - Keep at most one chunk per document_uid when policy.use_mmr is True.
        """
        if not scoped_document_ids:
            return []

        sf = SearchFilter(tag_ids=scoped_document_ids)

        # 1) ANN candidates (semantic) — gated
        ann_hits = self._vs_ann.ann_search(query, k=policy.fetch_k, search_filter=sf)
        ann_hits = [h for h in ann_hits if h.score >= policy.vector_min_cosine]
        if not ann_hits:
            return []

        # 2) Lexical evidence (BM25) — gated
        bm25_map = {
            h.chunk_id: h.score
            for h in self._vs_lex.lexical_search(query, k=policy.fetch_k, search_filter=sf, operator_and=True)
            if h.score >= policy.bm25_min_score
        }

        # 3) Optional exact phrase agreement
        phrase_ids: Set[str] = set()
        if policy.require_phrase_hit:
            phrase_ids = set(
                self._vs_lex.phrase_search(
                    query,
                    fields=["text", "metadata.section", "metadata.title"],
                    k=policy.fetch_k,
                    search_filter=sf,
                )
            )

        # 4) Keep only chunks that pass lexical gates (and phrase if required)
        def accepted(doc: Document) -> bool:
            cid = doc.metadata.get("chunk_uid")
            if cid not in bm25_map:
                return False
            if policy.require_phrase_hit and cid not in phrase_ids:
                return False
            return True

        gated_docs: List[Document] = [h.document for h in ann_hits if accepted(h.document)]
        if not gated_docs:
            return []

        # 5) De-dup by document_uid (simple MMR-ish pass)
        if policy.use_mmr:
            seen: Set[str] = set()
            uniq: List[Document] = []
            # Keep stronger semantic hits first
            for h in sorted(ann_hits, key=lambda x: x.score, reverse=True):
                d = h.document
                if not accepted(d):
                    continue
                uid = d.metadata.get("document_uid")
                if not isinstance(uid, str):
                    continue
                if uid in seen:
                    continue
                seen.add(uid)
                uniq.append(d)
                if len(uniq) >= policy.k_final:
                    break
            return uniq

        # 6) Truncate
        return gated_docs[: policy.k_final]
