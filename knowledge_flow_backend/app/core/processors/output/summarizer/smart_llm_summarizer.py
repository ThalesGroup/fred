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
Smart, size-aware document summarizer for the vectorization pipeline.

Fred rationale:
- Keep orchestration logic out of the pipeline: one call returns (abstract, keywords).
- Internally adapts to doc size with a bounded, salience-aware map-reduce.
- Prefers a small utility LLM when configured; falls back to extractive methods.
- Never throws: failures degrade to empty results so vectorization can proceed.
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional, Protocol, Tuple

from langchain.schema.document import Document

from app.common.structures import ModelConfiguration

# Contracts + concrete summarizers
from app.core.processors.output.summarizer.base_summarizer import BaseDocSummarizer
from app.core.processors.output.summarizer.cheap_extractive_summarizer import CheapExtractiveSummarizer
from app.core.processors.output.summarizer.llm_summarizer import LLMBasedDocSummarizer
from app.core.stores.vector.base_text_splitter import BaseTextSplitter

logger = logging.getLogger(__name__)

# Pre-compiled hints used in shard salience
HINTS = re.compile(
    r"\b(abstract|overview|introduction|intro|summary|conclusion|results|discussion)\b",
    re.I,
)


class SupportsSplit(Protocol):
    """Tiny protocol so we can type the splitter without importing its concrete class."""

    def split(self, doc: Document) -> List[Document]: ...


class SmartDocSummarizer(BaseDocSummarizer):
    """
    Facade used by the pipeline.
    Use: abstract, keywords = SmartDocSummarizer(...).summarize_document(document)

    - Encapsulates:
        • model selection (LLM or fallback)
        • size-aware policy (single pass vs. map-reduce)
        • shard salience ranking
        • bounded budgets (chars/words)
    """

    def __init__(
        self,
        *,
        model_config: ModelConfiguration,  # your Configuration.model (can be None)
        splitter: BaseTextSplitter,  # reuse the pipeline splitter to align shard boundaries
        opts: Optional[dict] = None,  # temporary hardcoded opts; move to config later
    ):
        # Default knobs — safe, predictable, cheap
        self.opts = {
            "sum_enabled": True,
            "sum_input_cap": 120_000,  # hard cap on chars considered
            "sum_abs_words": 180,
            "sum_kw_top_k": 24,
            # map-reduce specifics
            "mr_top_shards": 24,  # summarize at most N shards
            "mr_shard_words": 80,  # per-shard mini-abstract budget
            # thresholds
            "small_threshold": 50_000,  # chars → single pass
            "large_threshold": 1_200_000,  # chars → head/tail policy
            **(opts or {}),
        }

        self.splitter = splitter
        # Always provide a working summarizer (LLM or cheap extractive fallback).
        try:
            self._summarizer: BaseDocSummarizer = LLMBasedDocSummarizer(model_config)
            self.model_name = model_config.name if model_config else "default"
            logger.info("SmartDocSummarizer: using LLM-based summarizer (%s)", self._summarizer.__class__.__name__)
        except Exception as e:
            self._summarizer = CheapExtractiveSummarizer()
            self.model_name = "extractive-fallback"
            logger.info("SmartDocSummarizer: using built-in extractive fallback due to %r", e)

    # ------------------------ Public API (orchestration) ------------------------
    def get_model_name(self) -> str:
        """Name of the underlying model, or 'extractive-fallback'."""
        return self.model_name or "extractive-fallback"

    def summarize_document(self, document: Document) -> Tuple[Optional[str], Optional[List[str]]]:
        """
        Single entrypoint used by the pipeline.
        Returns (abstract, keywords). Never raises.
        """
        if not self.opts["sum_enabled"]:
            return None, None

        try:
            text = document.page_content or ""
            L = len(text)

            # Global cap to bound cost/latency
            cap = int(self.opts["sum_input_cap"])
            if cap > 0 and L > cap:
                # Representative window: head + tail
                head = text[: cap // 2]
                tail = text[-cap // 2 :]
                text = head + "\n\n[...] \n\n" + tail
                L = len(text)

            if L <= int(self.opts["small_threshold"]):
                return self._single_pass(text)

            if L <= int(self.opts["large_threshold"]):
                return self._map_reduce(text)

            # Extreme docs: map-reduce head and tail then reduce abstracts
            head = text[: int(self.opts["large_threshold"] // 2)]
            tail = text[-int(self.opts["large_threshold"] // 2) :]
            abs1, kw1 = self._map_reduce(head)
            abs2, kw2 = self._map_reduce(tail)
            final_abs = ""
            if abs1 or abs2:
                final_abs = self._summarizer.summarize_abstract(
                    f"Part A:\n{abs1}\n\nPart B:\n{abs2}",
                    max_words=int(self.opts["sum_abs_words"]),
                )
            merged = self._merge_keywords((kw1 or []), (kw2 or []), limit=int(self.opts["sum_kw_top_k"]))
            return final_abs, merged

        except Exception as e:
            logger.warning("SmartDocSummarizer failed (continuing): %r", e)
            return None, None

    # ------------------------ ABC delegation (BaseDocSummarizer) ------------------------

    def summarize_abstract(self, text: str, *, max_words: int = 180) -> str:
        """
        Delegate: SmartDocSummarizer is also a BaseDocSummarizer.
        Useful if callers want a simple per-text abstract outside of map-reduce.
        """
        return self._summarizer.summarize_abstract(text, max_words=max_words)

    def summarize_tokens(self, text: str, *, top_k: int = 24, vocab_hint: Optional[str] = None) -> List[str]:
        """
        Delegate: keep the BaseDocSummarizer contract (including optional vocab_hint).
        """
        return self._summarizer.summarize_tokens(text, top_k=top_k, vocab_hint=vocab_hint)

    # ------------------------ Internal: strategies ------------------------

    def _single_pass(self, text: str) -> Tuple[str, List[str]]:
        abs_ = self._summarizer.summarize_abstract(text, max_words=int(self.opts["sum_abs_words"]))
        kws = self._summarizer.summarize_tokens(
            text,
            top_k=int(self.opts["sum_kw_top_k"]),
            vocab_hint=None,
        )
        return abs_, kws

    def _map_reduce(self, text: str) -> Tuple[str, List[str]]:
        # Split into shards using the SAME splitter as vectorization
        shards = self.splitter.split(Document(page_content=text, metadata={}))
        if not shards:
            return "", []

        # Rank shards by salience; take top-N
        top_idx = self._rank_shards_by_salience(shards, top_k=int(self.opts["mr_top_shards"]))
        picked = [shards[i] for i in top_idx]

        # MAP: summarize selected shards
        shard_summaries: List[str] = []
        for d in picked:
            try:
                shard_summaries.append(
                    self._summarizer.summarize_abstract(
                        d.page_content or "",
                        max_words=int(self.opts["mr_shard_words"]),
                    )
                )
            except Exception:
                logger.warning("Shard summarization failed (continuing).")
                pass

        if not shard_summaries:
            return "", []

        # REDUCE: summarize the summaries → final abstract
        concat = "\n\n".join(shard_summaries)
        if len(concat) > 80_000:  # keep reduce context bounded
            concat = concat[:80_000]

        final_abs = ""
        try:
            final_abs = self._summarizer.summarize_abstract(concat, max_words=int(self.opts["sum_abs_words"]))
        except Exception:
            logger.warning("Final abstract summarization failed (continuing).")
            pass

        # Keywords: use full text if smallish, else use reduced concat to stay bounded
        kw_source = text if len(text) <= int(self.opts["sum_input_cap"]) else concat
        kws: List[str] = []
        try:
            kws = self._summarizer.summarize_tokens(
                kw_source,
                top_k=int(self.opts["sum_kw_top_k"]),
                vocab_hint=None,
            )
        except Exception:
            logger.warning("Keyword summarization failed (continuing).")
            pass

        return final_abs, kws

    # ------------------------ Internal: helpers ------------------------

    def _rank_shards_by_salience(self, shards: List[Document], top_k: int) -> List[int]:
        """
        Not all parts of a document are equally informative. We up-rank:
          - shards whose section/title hints 'abstract/intro/overview/summary/conclusion/results'
          - shards with higher token density
        Cheap heuristics; deterministic; no extra model calls.
        """
        scores = []
        for i, d in enumerate(shards):
            t = d.page_content or ""
            # density ~ informative token ratio
            alpha = re.findall(r"[a-zA-Z]{3,}", t)
            density = len(alpha) / max(1, len(t))
            section = (d.metadata or {}).get("section") or ""
            boost = 1.0
            if HINTS.search(section) or HINTS.search(t[:400]):
                boost += 0.8
            if len(t) < 400:  # down-rank tiny boilerplate
                boost -= 0.5
            scores.append((density * boost, i))
        scores.sort(reverse=True)
        return [i for _, i in scores[: max(1, min(top_k, len(shards)))]]

    def _merge_keywords(self, *lists: List[str], limit: int) -> List[str]:
        seen, out = set(), []
        for L in lists:
            for t in L:
                if t not in seen:
                    seen.add(t)
                    out.append(t)
                if len(out) >= limit:
                    return out
        return out
