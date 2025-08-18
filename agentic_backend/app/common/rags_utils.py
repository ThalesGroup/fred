# app/core/rag/rag_utils.py
from typing import List, Optional
from fred_core import VectorSearchHit


def trim_snippet(text: Optional[str], limit: int = 500) -> str:
    if not text:
        return ""
    t = text.strip()
    return t if len(t) <= limit else (t[:limit] + "…")


def sort_hits(hits: List[VectorSearchHit]) -> List[VectorSearchHit]:
    # By explicit rank (None -> very large), then score desc
    return sorted(
        hits,
        key=lambda h: (
            (h.rank if h.rank is not None else 1_000_000),
            -(h.score or 0.0),
        ),
    )


def ensure_ranks(hits: List[VectorSearchHit]) -> None:
    i = 1
    for h in hits:
        if h.rank is None:
            h.rank = i
        i += 1


def format_sources_for_prompt(
    hits: List[VectorSearchHit], snippet_chars: int = 500
) -> str:
    lines: List[str] = []
    for h in hits:
        label_bits = []
        if h.title:
            label_bits.append(h.title)
        if h.section:
            label_bits.append(f"§ {h.section}")
        if h.page is not None:
            label_bits.append(f"p.{h.page}")
        if h.file_name:
            label_bits.append(f"({h.file_name})")
        if h.tag_names:
            label_bits.append(f"tags: {', '.join(h.tag_names)}")

        label = " — ".join(label_bits) if label_bits else h.uid
        snippet = trim_snippet(h.content, snippet_chars)
        n = h.rank if h.rank is not None else "?"
        lines.append(f"[{n}] {label}\n{snippet}")
    return "\n\n".join(lines)


def attach_sources_to_llm_response(answer, hits: List[VectorSearchHit]) -> None:
    meta = getattr(answer, "response_metadata", None)
    if meta is None:
        return
    meta["sources"] = [h.model_dump() for h in hits]
