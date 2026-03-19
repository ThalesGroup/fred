from __future__ import annotations

from typing import Iterable, Sequence

from fred_core import VectorSearchHit

from .models import CitationRecord


def _citation_key(hit: VectorSearchHit) -> str:
    return (
        hit.citation_url
        or hit.preview_at_url
        or hit.uid
        or hit.preview_url
        or hit.repo_url
        or hit.file_name
        or str(id(hit))
    )


def build_citation_index(hits: Iterable[VectorSearchHit]) -> tuple[list[CitationRecord], dict[str, int]]:
    records: list[CitationRecord] = []
    index_map: dict[str, int] = {}
    for hit in hits:
        key = _citation_key(hit)
        if key in index_map:
            continue
        idx = len(records) + 1
        index_map[key] = idx
        snippet = (hit.content or "").strip()
        if len(snippet) > 240:
            snippet = snippet[:240] + "…"
        records.append(
            CitationRecord(
                index=idx,
                uid=hit.uid,
                title=hit.title,
                section=hit.section,
                page=hit.page,
                file_name=hit.file_name,
                snippet=snippet or None,
            )
        )
    return records, index_map


def citations_for_hits(
    hits: Sequence[VectorSearchHit], index_map: dict[str, int]
) -> list[int]:
    numbers: list[int] = []
    for hit in hits:
        key = _citation_key(hit)
        idx = index_map.get(key)
        if idx is None:
            continue
        numbers.append(idx)
    return numbers
