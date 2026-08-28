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
"""Table-aware post-processing shared by every RAG retrieval path.

Similarity ranking returns a large table's chunks shuffled and cut off at top_k,
and the splitter repeats the header on each one so it can stand alone. Handed to
the model as-is, that reads as several small unrelated tables and answers row
questions wrong.

Three retrieval surfaces build LLM content from raw hits - the legacy
`knowledge.search` invoker, `KfVectorSearchToolkit`, and the `DocumentSearchPort`
behind `document_access`. They all need the same repair, so it lives here rather
than being reimplemented a fourth time.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from fred_core.store.vector_search import VectorSearchHit

logger = logging.getLogger(__name__)

# A table chunk is a header row followed by a Markdown separator row. Matching on
# the separator rather than a leading "|" also catches tables written without one.
_TABLE_SEPARATOR_CHARS = set("|-: \t")

# Ceiling for the whole-table fetch. A table is worth completing, but not at the
# cost of an unbounded prompt: one document per call, capped in chunks. When a
# document does not fit under the cap the fetch is abandoned rather than
# truncated - the document's first N chunks are not the ones that matched.
TABLE_EXPANSION_MAX_CHUNKS = 40

# Fetches a document's chunks in index order, capped at `limit`.
ChunkFetcher = Callable[..., Awaitable[list[VectorSearchHit]]]


def table_header_span(content: str) -> int:
    """Length in lines of the leading table header, or 0 when this is not a table chunk."""
    lines = content.split("\n", 2)
    if len(lines) < 2 or "|" not in lines[0]:
        return 0
    separator = lines[1].strip()
    if "|" not in separator or "-" not in separator:
        return 0
    if set(separator) - _TABLE_SEPARATOR_CHARS:
        return 0
    return 2


def restore_document_order(hits: list[VectorSearchHit]) -> list[VectorSearchHit]:
    """Put a table document's chunks back in index order, leaving the rest alone.

    Similarity ranking interleaves a table's chunks, which reads as a shuffled table,
    and the header de-duplication below needs a document's chunks adjacent and in
    order to tell one table's run from the next.

    Only documents that actually contain a table chunk are regrouped. Reordering
    every document would demote the single best-scoring hit of an ordinary prose
    answer behind weak chunks of the same document, for no benefit - a table-free
    hit set is returned exactly as it came in. A regrouped document takes the
    position of its first hit, so cross-document ranking is preserved.
    """
    table_docs = {hit.uid for hit in hits if table_header_span(hit.content)}
    if not table_docs:
        return hits

    per_doc: dict[str, list[VectorSearchHit]] = {uid: [] for uid in table_docs}
    for hit in hits:
        if hit.uid in table_docs:
            per_doc[hit.uid].append(hit)
    for chunks in per_doc.values():
        chunks.sort(key=lambda h: (h.chunk_index is None, h.chunk_index or 0))

    ordered: list[VectorSearchHit] = []
    emitted: set[str] = set()
    for hit in hits:
        if hit.uid not in table_docs:
            ordered.append(hit)
        elif hit.uid not in emitted:
            emitted.add(hit.uid)
            ordered.extend(per_doc[hit.uid])
    return ordered


def strip_repeated_table_headers(hits: list[VectorSearchHit]) -> list[VectorSearchHit]:
    """Drop the header the splitter repeats on every table chunk, except the first.

    Each chunk carries the header so it stands alone, but a run of them reads to the
    model as separate tables. Strips only when the previous chunk of the same document
    opened with the very same header, so a run of one table keeps exactly one header
    and a second, different table in the document keeps its own.
    """
    out: list[VectorSearchHit] = []
    prev_uid: str | None = None
    prev_header: str | None = None
    for hit in hits:
        span = table_header_span(hit.content)
        header = "\n".join(hit.content.split("\n")[:span]) if span else None
        if span and hit.uid == prev_uid and header == prev_header:
            body = "\n".join(hit.content.split("\n")[span:]).lstrip("\n")
            hit = hit.model_copy(update={"content": body})
        out.append(hit)
        prev_uid = hit.uid
        prev_header = header
    return out


async def complete_truncated_table(
    hits: list[VectorSearchHit], fetch: ChunkFetcher
) -> list[VectorSearchHit]:
    """Refetch a whole table when top_k demonstrably cut one short.

    Table chunks from one document at non-contiguous indices mean similarity ranking
    returned a slice with a hole in it, and a sliced table answers row questions
    wrong. Two adjacent chunks, or two separate small tables, are complete already
    and are left alone.

    Best-effort: on a failure, or on a document too large for the cap, the original
    hits stand.
    """
    indices: dict[str, list[int]] = {}
    for hit in hits:
        if table_header_span(hit.content) and hit.chunk_index is not None:
            indices.setdefault(hit.uid, []).append(hit.chunk_index)
    gapped = {
        uid: idx
        for uid, idx in indices.items()
        if len(idx) >= 2 and max(idx) - min(idx) + 1 > len(idx)
    }
    if not gapped:
        return hits
    uid = max(gapped, key=lambda u: len(gapped[u]))

    try:
        chunks = await fetch(document_uid=uid, limit=TABLE_EXPANSION_MAX_CHUNKS)
    except Exception:
        logger.warning("[TABLE] completion failed for uid=%s", uid, exc_info=True)
        return hits

    original = [hit for hit in hits if hit.uid == uid]
    if len(chunks) <= len(original) or len(chunks) >= TABLE_EXPANSION_MAX_CHUNKS:
        logger.info(
            "[TABLE] completion skipped uid=%s fetched=%d had=%d cap=%d",
            uid,
            len(chunks),
            len(original),
            TABLE_EXPANSION_MAX_CHUNKS,
        )
        return hits

    # The fetch has no similarity score of its own. Carry the document's best score
    # over, or citation selection would drop the very table being answered from, and
    # splice in place so the document keeps its rank.
    best = max(hit.score for hit in original)
    chunks = [chunk.model_copy(update={"score": best}) for chunk in chunks]
    at = next(i for i, hit in enumerate(hits) if hit.uid == uid)
    rest = [hit for hit in hits if hit.uid != uid]
    logger.info(
        "[TABLE] completion uid=%s chunks=%d->%d", uid, len(original), len(chunks)
    )
    return rest[:at] + chunks + rest[at:]


async def repair_table_hits(
    hits: list[VectorSearchHit], fetch: ChunkFetcher
) -> list[VectorSearchHit]:
    """Complete, reorder and de-duplicate table hits before they reach the model."""
    hits = await complete_truncated_table(hits, fetch)
    hits = restore_document_order(hits)
    return strip_repeated_table_headers(hits)
