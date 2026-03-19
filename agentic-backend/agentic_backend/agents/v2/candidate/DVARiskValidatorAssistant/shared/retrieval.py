from __future__ import annotations

from typing import Any, Iterable

from fred_core import VectorSearchHit

from agentic_backend.common.rags_utils import format_sources_for_prompt
from agentic_backend.core.agents.v2 import ToolContentKind, ToolInvocationResult


def extract_hits(result: ToolInvocationResult) -> list[VectorSearchHit]:
    if result.sources:
        return list(result.sources)
    for block in result.blocks:
        if block.kind == ToolContentKind.JSON and isinstance(block.data, dict):
            hits = block.data.get("hits")
            if isinstance(hits, list):
                return [VectorSearchHit.model_validate(hit) for hit in hits]
    return []


def hits_to_prompt_context(hits: Iterable[VectorSearchHit], *, limit: int = 500) -> str:
    return format_sources_for_prompt(list(hits), snippet_chars=limit)


def merge_hits(*hit_lists: Iterable[VectorSearchHit]) -> list[VectorSearchHit]:
    seen: set[str] = set()
    merged: list[VectorSearchHit] = []
    for hits in hit_lists:
        for hit in hits:
            key = hit.uid or hit.citation_url or hit.preview_at_url or str(id(hit))
            if key in seen:
                continue
            seen.add(key)
            merged.append(hit)
    return merged


def hit_to_dict(hit: VectorSearchHit) -> dict[str, Any]:
    if hasattr(hit, "model_dump"):
        return hit.model_dump(mode="json")
    return dict(hit)  # type: ignore[arg-type]


def hits_to_dicts(hits: Iterable[VectorSearchHit]) -> list[dict[str, Any]]:
    return [hit_to_dict(hit) for hit in hits]
