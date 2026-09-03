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

"""
Exhaustive, instruction-steered document extraction (DOCREAD-01 Phase 2).

Why this is NOT `SmartDocSummarizer`: the summarizer is deliberately LOSSY and
SELECTIVE — it ranks shards by salience, keeps only the top-N, caps input, and
its reduce COMPRESSES to a word budget. That is exactly wrong for "list ALL the
requirements": items in dropped shards vanish, and the reduce merges away
duplicates the user may want counted. This extractor instead:

- maps over EVERY chunk of the document (no salience pruning),
- asks the model to extract matching items verbatim, one per line, or `NONE`,
- reduces by CONCATENATING + de-duplicating (never summarizing).

The map phase is the heavy, rate-limit-sensitive part: a big document is many
chunks = many LLM calls. It is run with **bounded concurrency** and a
**429-aware retry/backoff** so a throttling provider slows the extraction down
instead of failing the whole turn (DOCREAD-01 #2). This all happens server-side
in ONE agent tool call, so the agent no longer bursts N model calls of its own
(the cause of the original client-side 429).
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from dataclasses import dataclass

from fred_core import is_rate_limit
from langchain_core.documents import Document

from knowledge_flow_backend.application_context import ApplicationContext

logger = logging.getLogger(__name__)

# Tuning knobs. Deliberately conservative defaults — the map phase is throttled
# by the model provider, so we favour "slow but complete" over "fast but 429".
# Candidates to promote to configuration once live tuning settles them.
#
# The vectorization splitter yields ~1.5k-char shards — one LLM call per shard
# would mean hundreds of calls for a real spec (609k chars → 471 calls, observed
# live: 4 min AND it exhausted the provider's rate limit for following turns).
# So consecutive shards are PACKED into large map windows: one LLM call per
# ~24k-char window keeps table/semantic boundaries (from the splitter) while
# cutting the call count ~18× (471 → ~26). De-dup across the small window overlap
# is handled by the reduce.
_MAP_WINDOW_CHARS = 24_000
_MAP_CONCURRENCY = 3
_MAX_RETRIES = 5
_BACKOFF_BASE_S = 2.0
_BACKOFF_CAP_S = 30.0
# Hard safety cap on characters actually processed (protects cost/latency on a
# runaway input). Generous — most specs are well under this; a document above it
# is head+tail-windowed and flagged `truncated`.
_INPUT_CHAR_CAP = 2_000_000

_EXTRACT_SYS = "You are a precise information-extraction engine. You extract items exactly as they appear in the source. You never summarize, never merge distinct items, and never invent content."

_NONE_MARKER = "NONE"


@dataclass(frozen=True)
class ExtractionResult:
    text: str
    item_count: int
    chunks_processed: int
    truncated: bool


def _parse_items(raw: str) -> list[str]:
    """Parse one chunk's model output into a list of extracted items.

    The model is asked for one item per line (optionally bullet-prefixed) or the
    literal `NONE`. We strip bullets/numbering and drop empties and the NONE
    sentinel; everything else is kept verbatim.
    """

    items: list[str] = []
    for line in (raw or "").splitlines():
        s = line.strip()
        if not s:
            continue
        # Strip a leading bullet/number marker ("- ", "* ", "1. ", "1) ").
        s = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s+", "", s).strip()
        if not s or s.upper() == _NONE_MARKER:
            continue
        items.append(s)
    return items


def _pack_windows(chunks: list[str], window_chars: int) -> list[str]:
    """Greedily pack consecutive splitter shards into map windows of at most
    `window_chars`, so one LLM call covers many shards instead of one call per
    tiny shard. Keeps the splitter's table/semantic boundaries; a single shard
    already larger than the window becomes its own window."""

    windows: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for c in chunks:
        if cur and cur_len + len(c) > window_chars:
            windows.append("\n\n".join(cur))
            cur, cur_len = [], 0
        cur.append(c)
        cur_len += len(c)
    if cur:
        windows.append("\n\n".join(cur))
    return windows


class DocumentExtractor:
    """Exhaustive map-reduce extraction over a document's full text."""

    def __init__(self) -> None:
        self.context = ApplicationContext.get_instance()
        self.model = self.context.get_utility_model()
        if self.model is None:
            raise RuntimeError("No utility LLM configured; exhaustive extraction requires a model.")
        self.splitter = self.context.get_text_splitter()

    def _prompt_for(self, instruction: str, chunk: str) -> list[tuple[str, str]]:
        user = (
            "From the document excerpt below, extract EVERY item matching this "
            f"request:\n{instruction}\n\n"
            "Rules:\n"
            '- Output each matching item on its own line, prefixed with "- ".\n'
            "- Quote the source verbatim or as closely as possible; do NOT "
            "summarize, shorten, or merge items.\n"
            "- Include every occurrence, in order; do not stop early.\n"
            f"- If the excerpt contains NO matching item, output exactly: {_NONE_MARKER}\n"
            "- Output only the list (or the single word above). No preamble, no "
            "commentary, no headings.\n\n"
            "--- EXCERPT ---\n"
            f"{chunk}"
        )
        return [("system", _EXTRACT_SYS), ("user", user)]

    async def _extract_chunk(self, instruction: str, chunk: str, sem: asyncio.Semaphore) -> list[str]:
        """One map call, guarded by the concurrency semaphore and a 429-aware
        retry/backoff. Non-rate-limit failures degrade to an empty item list
        (one bad chunk must not sink the whole extraction)."""

        messages = self._prompt_for(instruction, chunk)
        async with sem:
            for attempt in range(_MAX_RETRIES + 1):
                try:
                    result = await self.model.ainvoke(messages)
                    content = getattr(result, "content", result)
                    text = content if isinstance(content, str) else str(content)
                    return _parse_items(text)
                except Exception as exc:  # noqa: BLE001 — see below
                    is_rl, retry_after = is_rate_limit(exc)
                    if is_rl and attempt < _MAX_RETRIES:
                        delay = retry_after if retry_after is not None else min(_BACKOFF_CAP_S, _BACKOFF_BASE_S * (2**attempt))
                        # Jitter avoids a thundering herd of retried chunks all
                        # waking at the same instant and re-tripping the limit.
                        delay += random.uniform(0, 0.5)  # nosec B311 — retry jitter, not security-sensitive
                        logger.warning(
                            "[EXTRACT] rate-limited on chunk (attempt %d/%d); backing off %.1fs",
                            attempt + 1,
                            _MAX_RETRIES,
                            delay,
                        )
                        await asyncio.sleep(delay)
                        continue
                    if is_rl:
                        # Retries exhausted on a genuine rate limit — this one is
                        # worth surfacing so the caller can report a partial risk.
                        logger.error(
                            "[EXTRACT] rate limit persisted after %d retries; dropping one chunk's items",
                            _MAX_RETRIES,
                        )
                    else:
                        logger.warning("[EXTRACT] chunk extraction failed (continuing): %r", exc)
                    return []
        return []

    async def extract(self, *, text: str, instruction: str) -> ExtractionResult:
        """Run exhaustive extraction over `text` steered by `instruction`."""

        truncated = False
        if len(text) > _INPUT_CHAR_CAP:
            half = _INPUT_CHAR_CAP // 2
            text = text[:half] + "\n\n[...]\n\n" + text[-half:]
            truncated = True

        shards = self.splitter.split(Document(page_content=text, metadata={}))
        chunks = [s.page_content or "" for s in shards if (s.page_content or "").strip()]
        if not chunks:
            return ExtractionResult(text="", item_count=0, chunks_processed=0, truncated=truncated)
        windows = _pack_windows(chunks, _MAP_WINDOW_CHARS)

        sem = asyncio.Semaphore(_MAP_CONCURRENCY)
        started = time.monotonic()
        per_chunk = await asyncio.gather(*(self._extract_chunk(instruction, w, sem) for w in windows))
        elapsed_ms = (time.monotonic() - started) * 1000

        # REDUCE: concatenate in document order, de-duplicate case-insensitively
        # while preserving first-seen order. No LLM merge pass — that would risk
        # dropping items, which is the whole failure this capability avoids.
        seen: set[str] = set()
        items: list[str] = []
        for chunk_items in per_chunk:
            for it in chunk_items:
                key = it.casefold()
                if key not in seen:
                    seen.add(key)
                    items.append(it)

        logger.info(
            "[EXTRACT] windows=%d (shards=%d) items=%d chars_in=%d elapsed_ms=%.0f truncated=%s",
            len(windows),
            len(chunks),
            len(items),
            len(text),
            elapsed_ms,
            truncated,
        )
        body = "\n".join(f"- {it}" for it in items)
        return ExtractionResult(
            text=body,
            item_count=len(items),
            chunks_processed=len(windows),
            truncated=truncated,
        )
