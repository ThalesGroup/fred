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


# Copyright Thales 2025
# Apache-2.0

from typing import List, Optional
import re
import logging
from collections import Counter

from app.core.processors.output.summarizer.base_summarizer import BaseDocSummarizer

logger = logging.getLogger(__name__)


class CheapExtractiveSummarizer(BaseDocSummarizer):
    """
    Zero-dependency, deterministic fallback summarizer.

    Fred rationale:
    - Guarantees a working summarizer when no utility LLM is configured.
    - Keeps the same interface as BaseDocSummarizer (incl. vocab_hint arg).
    - Optimized for robustness and type safety, not linguistic perfection.

    Behavior:
    - Abstract: pick highest "density" sentences (ratio of alpha tokens) until word budget.
    - Tokens: crude n-gram frequency (2–4 grams) plus strong unigrams, de-duplicated, lowercased.
    """

    _SPLIT = re.compile(r"(?<=[.!?])\s+")
    _WORD_RE = re.compile(r"[a-z0-9_\-]+")
    _ALPHA3_RE = re.compile(r"[a-zA-Z]{3,}")

    # ---- BaseDocSummarizer API ----

    def summarize_abstract(self, text: str, *, max_words: int = 180) -> str:
        sents = [s.strip() for s in self._SPLIT.split(text or "") if s.strip()]
        if not sents:
            return ""

        # Sentence density ~ alphabetic token ratio (cheap salience heuristic)
        def density(s: str) -> float:
            alpha = self._ALPHA3_RE.findall(s)
            return len(alpha) / max(1, len(s))

        ranked = sorted(sents, key=density, reverse=True)

        # Greedy selection under word budget; then restore original order for readability
        out, w = [], 0
        for s in ranked:
            n = len(s.split())
            if w + n > max_words:
                continue
            out.append(s)
            w += n
            if w >= max_words * 0.8:
                break

        out.sort(key=lambda x: sents.index(x))
        return " ".join(out)

    def summarize_tokens(self, text: str, *, top_k: int = 24, vocab_hint: Optional[str] = None) -> List[str]:
        """
        Extractive keywording.
        - `vocab_hint` is accepted to satisfy the interface; ignored here (no LLM).
        """
        words = [w for w in self._WORD_RE.findall((text or "").lower()) if len(w) > 2]
        if not words:
            return []

        # Unigram counts
        tf = Counter(words)

        # N-gram counts (2–4): captures salient short phrases
        phrases = Counter()
        for n in (2, 3, 4):
            for i in range(len(words) - n + 1):
                phrases[" ".join(words[i : i + n])] += 1

        # Score: phrases get a small boost over unigrams
        scored: List[tuple[float, str]] = []
        for t, c in tf.items():
            scored.append((float(c), t))
        for p, c in phrases.items():
            scored.append((c * 1.5, p))  # phrase boost

        ranked = [t for _, t in sorted(scored, reverse=True)]

        # De-duplicate, length-guard (1–4 words), avoid numeric-only tokens
        out, seen = [], set()
        for t in ranked:
            if t not in seen and 1 <= len(t.split()) <= 4 and not t.isdigit():
                seen.add(t)
                out.append(t)
            if len(out) >= top_k:
                break

        return out
