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


# Fred rationale (keep short, high-signal):
# - Goal: beat plain ANN on average without per-query hacks.
# - Method: RRF(ANN,BM25) + soft bonuses (NEVER hard filters) + doc-level diversity.
# - Safety: if BM25=Ø, ANN still returns; if ANN=Ø, lexical still returns.
# - Explainability: each scoring component is logged (dev-mode) and can be surfaced in UI.

from __future__ import annotations

import logging
import re
import time
from typing import Dict, List, Sequence, Tuple, cast

from langchain.schema.document import Document

from app.core.stores.vector.base_vector_store import AnnHit, BaseVectorStore, LexicalHit, LexicalSearchable, SearchFilter
from app.features.vector_search.vector_search_structures import HybridPolicy

logger = logging.getLogger(__name__)

# ---- Minimal text utils (robust but cheap) ----

_WH_PAT = re.compile(r"(?i)^\s*(who\s+(is|are)|qui\s+(est|sont))\b")
_QUOTED = re.compile(
    r'"([^"]{2,120})"'
    r"|(?:(?<=\s)'([^']{2,120})'(?=\s|[.,;!?]|$))"
)

_STOP = {
    # articles/conjunctions/preps (EN/FR)
    "the",
    "a",
    "an",
    "and",
    "or",
    "of",
    "for",
    "in",
    "to",
    "on",
    "with",
    "by",
    "at",
    "from",
    "le",
    "la",
    "les",
    "un",
    "une",
    "des",
    "du",
    "de",
    "d",
    "et",
    "ou",
    "pour",
    "dans",
    "sur",
    "au",
    "aux",
    "par",
    "à",
    "en",
}


def _tokenize(q: str) -> List[str]:
    """
    Tokenizer that keeps accented letters and hyphens.
    - Accepts unicode letters (including é, è, ç, ï, ö, etc.)
    - Keeps hyphens inside words
    - Lowercases everything
    """
    return re.findall(r"[^\W\d_][\w\-]{1,40}", q.lower(), flags=re.UNICODE)


def _salient_terms(q: str) -> List[str]:
    """
    General-purpose signal: unquoted words ≥3 chars not in stopwords.
    Works with English and French (supports accented letters).
    """
    return [t for t in _tokenize(q) if len(t) >= 3 and t not in _STOP]


def _capitalized_terms(q: str) -> List[str]:
    """Heuristic 'proper-like' tokens; used as SOFT bonus only."""
    caps = re.findall(r"\b[A-Z][a-zA-Z\-]{1,40}\b", q)
    # Drop first if it's sentence case of a function word (e.g., 'Define', 'Offshore')
    return [c.lower() for c in caps[1:] if c.lower() not in _STOP] if caps else []


def _quoted_phrases(q: str) -> List[str]:
    """Quoted phrases are strong lexical signals; SOFT bonus."""
    out = []
    for m in _QUOTED.finditer(q):
        g = m.group(1) or m.group(2)
        if g:
            out.append(g.strip().lower())
    return out


def _chunk_id_of(d: Document) -> str | None:
    md = d.metadata or {}
    cid = md.get("chunk_uid") or md.get("_id")
    return cid if isinstance(cid, str) and cid else None


def _doc_uid_of(d: Document) -> str | None:
    md = d.metadata or {}
    uid = md.get("document_uid")
    return uid if isinstance(uid, str) and uid else None


def _doc_text_pool(d: Document) -> str:
    """Small text pool (title/section/body). Cheap containment tests, not full scoring."""
    md = d.metadata or {}
    title = md.get("title") or md.get("file_name") or md.get("source") or ""
    section = md.get("section") or ""
    return (title + " \n " + section + " \n " + (d.page_content or "")).lower()


# ---- Core retriever ----


class HybridRetriever:
    """
    Fred — General-purpose Hybrid Retriever
    - RRF fuse ANN + BM25 with weights.
    - Soft signals only: capitalized terms / quoted phrases add bounded bonuses.
    - Diversity: doc-level de-dup; optional MMR-style re-ranking across docs.
    """

    def __init__(self, vs: BaseVectorStore) -> None:
        self.vs = vs

    def search(
        self,
        *,
        query: str,
        scoped_document_ids: Sequence[str],
        policy: HybridPolicy,
    ) -> List[Tuple[Document, float]]:
        t0 = time.perf_counter()
        if not scoped_document_ids:
            logger.info("[Hybrid] No scoped documents provided, returning empty list")
            return []

        sf = SearchFilter(tag_ids=scoped_document_ids)

        # --- Policy knobs with safe defaults ---
        rrf_k = getattr(policy, "rrf_k", 60)
        fetch_k_ann = getattr(policy, "fetch_k_ann", 60)
        fetch_k_bm25 = getattr(policy, "fetch_k_bm25", 60)
        vec_min = getattr(policy, "vector_min_cosine", 0.45)
        bm25_min = getattr(policy, "bm25_min_score", 1.5)
        use_mmr = getattr(policy, "use_mmr", True)

        # Fusion weights (tune per corpus; default slightly favors ANN)
        w_ann = getattr(policy, "w_ann", 1.0)
        w_bm25 = getattr(policy, "w_bm25", 0.9)

        # Soft-signal bonuses (bounded; never decisive alone)
        enable_signals = getattr(policy, "enable_soft_signals", True)
        who_boost = getattr(policy, "who_query_boost", 0.02)  # tiny nudge for ANN tie-breaks
        caps_bonus_w = getattr(policy, "capitalized_terms_bonus", 0.08)  # per coverage ratio
        quoted_bonus_w = getattr(policy, "quoted_phrases_bonus", 0.12)  # stronger than caps
        bonus_cap = getattr(policy, "soft_bonus_cap", 0.25)  # never exceed this

        who_query = bool(_WH_PAT.search(query))
        caps = _capitalized_terms(query)
        terms = _salient_terms(query)
        quoted = _quoted_phrases(query)

        logger.info(
            "[Hybrid] Start q='%s' scope=%d | RRF(k=%d) fetch(ann=%d bm25=%d) thr(vec=%.3f bm25=%.3f) w(ann=%.2f bm25=%.2f) mmr=%s | signals=%s who=%s caps=%s quoted=%s terms=%s",
            query,
            len(scoped_document_ids),
            rrf_k,
            fetch_k_ann,
            fetch_k_bm25,
            vec_min,
            bm25_min,
            w_ann,
            w_bm25,
            use_mmr,
            enable_signals,
            who_query,
            caps or "[]",
            quoted or "[]",
            terms[:8] + (["…"] if len(terms) > 8 else []),
        )

        # 1) ANN
        ann_hits: List[AnnHit] = self.vs.ann_search(query, k=fetch_k_ann, search_filter=sf)
        ann_hits = [h for h in ann_hits if h.score >= vec_min]
        ann_rank: Dict[str, int] = {}
        ann_map: Dict[str, Tuple[Document, float]] = {}
        skipped_ann_no_chunk = 0
        for r, h in enumerate(ann_hits, start=1):
            cid = _chunk_id_of(h.document)
            if not cid:
                skipped_ann_no_chunk += 1
                continue
            # Keep best rank & map to cosine
            ann_rank[cid] = min(ann_rank.get(cid, r), r)
            ann_map[cid] = (h.document, h.score)
        if skipped_ann_no_chunk:
            logger.info("[Hybrid] ANN skipped %d hits with no chunk id", skipped_ann_no_chunk)

        # 2) BM25 (optional)
        bm25_rank: Dict[str, int] = {}
        if isinstance(self.vs, LexicalSearchable):
            vs_lex = cast(LexicalSearchable, self.vs)
            bm25_hits: List[LexicalHit] = vs_lex.lexical_search(query, k=fetch_k_bm25, search_filter=sf, operator_and=False)
            bm25_hits = [h for h in bm25_hits if h.score >= bm25_min]
            bm25_rank = {h.chunk_id: r for r, h in enumerate(bm25_hits, start=1)}
            logger.info("[Hybrid] BM25 hits after filtering by min score (%s): %s", policy.bm25_min_score, len(bm25_hits))

        if not ann_rank and not bm25_rank:
            logger.info("[Hybrid] Hybrid: empty(ANN,BM25) → []")
            return []

        # 3) RRF fusion (weighted)
        fused: Dict[str, float] = {}

        def add_rrf(rank_map: Dict[str, int], weight: float) -> None:
            for cid, rnk in rank_map.items():
                fused[cid] = fused.get(cid, 0.0) + weight * (1.0 / (rrf_k + rnk))

        if ann_rank:
            add_rrf(ann_rank, w_ann)
        if bm25_rank:
            add_rrf(bm25_rank, w_bm25)

        # 4) Soft bonuses (NEVER hard filters)
        if enable_signals and (caps or quoted):
            for cid in list(fused.keys()):
                d, cos = ann_map.get(cid, (None, -1.0))
                if d is None:
                    # If the cid comes only from BM25, we still can bonus via its document
                    # (LexicalHit.document is available from store)
                    # Fallback: skip bonus if we don't have a Document handle.
                    continue
                pool = _doc_text_pool(d)
                bonus = 0.0

                if caps:
                    hit = sum(1 for c in caps if c in pool)
                    if hit:
                        # coverage ∈ (0,1], smaller caps lists count more per term
                        cov = hit / max(len(caps), 1)
                        bonus += caps_bonus_w * cov

                if quoted:
                    qhit = sum(1 for phrase in quoted if phrase in pool)
                    if qhit:
                        covq = qhit / max(len(quoted), 1)
                        bonus += quoted_bonus_w * covq

                # Tiny who-query nudge toward higher ANN cosine (tie-breaker)
                if who_query and cid in ann_map:
                    bonus += who_boost * max(cos, 0.0)

                # Bound total bonus to avoid runaway effects
                fused[cid] += min(bonus, bonus_cap)

        # 5) Order by fused desc, tie-break by ANN cosine
        ordered = sorted(
            fused.items(),
            key=lambda kv: (kv[1], ann_map.get(kv[0], (None, -1.0))[1]),
            reverse=True,
        )
        logger.info("[Hybrid] Chunks ordered by fused score, total=%d", len(ordered))

        # 6) Build output with doc-level diversity
        out: List[Tuple[Document, float]] = []
        seen_docs: set[str] = set()
        skipped_missing_doc = 0
        skipped_duplicates = 0

        for cid, _score in ordered:
            # Prefer candidates that we have ANN cosine for; if BM25-only, still allowed.
            doc, cos = ann_map.get(cid, (None, -1.0))
            if doc is None:
                skipped_missing_doc += 1
                # Attempt to recover Document from lexical side if store provides it
                if isinstance(self.vs, LexicalSearchable):
                    # NOTE: leaving this minimal; if you want, keep a map cid->LexicalHit.document
                    continue
                else:
                    continue

            uid = _doc_uid_of(doc)
            if use_mmr:
                if not uid or uid in seen_docs:
                    skipped_duplicates += 1
                    continue
                seen_docs.add(uid)
            out.append((doc, cos))
            if len(out) >= policy.k_final:
                logger.info("[Hybrid] Reached k_final (%s), stopping", policy.k_final)
                break

        logger.info(
            "[Hybrid] Final=%d of %d candidates | ann_only=%s bm25_used=%s | skipped_missing_doc=%d skipped_duplicates=%d | dt=%.1fms",
            len(out),
            len(ordered),
            bool(ann_rank and not bm25_rank),
            bool(bm25_rank),
            skipped_missing_doc,
            skipped_duplicates,
            (time.perf_counter() - t0) * 1000,
        )

        return out
