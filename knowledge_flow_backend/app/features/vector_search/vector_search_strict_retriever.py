# app/core/retrieval/strict_retriever.py
# Copyright Thales 2025
# Licensed under the Apache License, Version 2.0 (the "License"); ...

from __future__ import annotations
from typing import List, Sequence, Set, cast
from langchain.schema.document import Document

from app.core.stores.vector.base_vector_store import BaseVectorStore, LexicalSearchable, SearchFilter
from app.features.vector_search.vector_search_structures import SearchPolicy
import logging
import time

logger = logging.getLogger(__name__)

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
        logger.info("[Strict] Initializing with vector store of type %s", type(vs).__name__)
        # Strict requires lexical capability (BM25/phrase).
        if not isinstance(vs, LexicalSearchable):
            logger.error("[Strict] Provided vector store does not support LexicalSearchable features")
            raise TypeError("StrictRetriever requires a LexicalSearchable vector store (e.g., OpenSearch adapter).")
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
        start_time = time.perf_counter()
        logger.info("[Strict] search started for query='%s' with %d scoped docs", query, len(scoped_document_ids))
        if not scoped_document_ids:
            logger.info("[Strict] No scoped documents provided, returning empty list")
            return []

        sf = SearchFilter(tag_ids=scoped_document_ids)

        # 1) ANN candidates (semantic) — gated
        logger.info("[Strict] Running ANN search with fetch_k=%s", policy.fetch_k)
        ann_hits = self._vs_ann.ann_search(query, k=policy.fetch_k, search_filter=sf)
        logger.info("[Strict] ANN hits returned: %s", len(ann_hits))
        ann_hits = [h for h in ann_hits if h.score >= policy.vector_min_cosine]
        logger.info("[Strict] ANN hits after applying vector_min_cosine (%.3f): %s", policy.vector_min_cosine, len(ann_hits))
        if not ann_hits:
            logger.info("[Strict] No ANN hits above threshold, returning empty list")
            logger.info("[Strict] Completed in %.2f ms", (time.perf_counter() - start_time) * 1000)
            return []

        # 2) Lexical evidence (BM25) — gated
        logger.info("[Strict] Running BM25 lexical search with fetch_k=%s", policy.fetch_k)
        bm25_hits = self._vs_lex.lexical_search(query, k=policy.fetch_k, search_filter=sf, operator_and=True)
        bm25_map = {h.chunk_id: h.score for h in bm25_hits if h.score >= policy.bm25_min_score}
        logger.info("[Strict] BM25 hits after applying bm25_min_score (%.3f): %s", policy.bm25_min_score, len(bm25_map))

        # 3) Optional exact phrase agreement
        phrase_ids: Set[str] = set()
        if policy.require_phrase_hit:
            logger.info("[Strict] Running phrase search due to require_phrase_hit")
            phrase_ids = set(
                self._vs_lex.phrase_search(
                    query,
                    fields=["text", "metadata.section", "metadata.title"],
                    k=policy.fetch_k,
                    search_filter=sf,
                )
            )
            logger.info("[Strict] Phrase search returned %s hits", len(phrase_ids))

        # 4) Keep only chunks that pass lexical gates (and phrase if required)
        def accepted(doc: Document) -> bool:
            cid = doc.metadata.get("chunk_uid")
            if cid not in bm25_map:
                return False
            if policy.require_phrase_hit and cid not in phrase_ids:
                return False
            return True

        gated_docs: List[Document] = [h.document for h in ann_hits if accepted(h.document)]
        logger.info("[Strict] Documents passing lexical/phrase gates: %s", len(gated_docs))
        if not gated_docs:
            logger.info("[Strict] No documents passed gates, returning empty list")
            logger.info("[Strict] Completed in %.2f ms", (time.perf_counter() - start_time) * 1000)
            return []

        # 5) De-dup by document_uid (simple MMR-ish pass)
        if policy.use_mmr:
            logger.info("[Strict] Applying MMR de-duplication with k_final=%s", policy.k_final)
            seen: Set[str] = set()
            uniq: List[Document] = []
            # Keep stronger semantic hits first
            for h in sorted(ann_hits, key=lambda x: x.score, reverse=True):
                d = h.document
                if not accepted(d):
                    continue
                uid = d.metadata.get("document_uid")
                if not isinstance(uid, str):
                    logger.info("[Strict] Skipping document with missing document_uid")
                    continue
                if uid in seen:
                    continue
                seen.add(uid)
                uniq.append(d)
                if len(uniq) >= policy.k_final:
                    logger.info("[Strict] Reached k_final limit (%s) during MMR pass", policy.k_final)
                    break
            logger.info("[Strict] Returning %s unique documents after MMR", len(uniq))
            logger.info("[Strict] Completed in %.2f ms", (time.perf_counter() - start_time) * 1000)
            return uniq

        # 6) Truncate
        truncated = gated_docs[: policy.k_final]
        logger.info("[Strict] Returning top %s documents after truncation", len(truncated))
        logger.info("[Strict] Completed in %.2f ms", (time.perf_counter() - start_time) * 1000)
        return truncated
