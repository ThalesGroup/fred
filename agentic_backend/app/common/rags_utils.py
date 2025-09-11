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

from typing import List, Optional
from fred_core import VectorSearchHit

from app.core.chatbot.chat_schema import LinkKind, LinkPart


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


def _extract_url_from_hit(hit: VectorSearchHit) -> Optional[str]:
    """
    Prefer precise, user-facing viewers in this order:
      1) citation_url       — deep link to the cited selection/chunk
      2) preview_at_url     — viewer with anchor (e.g., #sel=...)
      3) preview_url        — viewer root (no anchor)
      4) repo_url           — external repo page, if any
      5) synthesized        — /documents/{uid} or /documents/{uid}#{viewer_fragment}
    """
    if hit.citation_url:
        return hit.citation_url
    if hit.preview_at_url:
        return hit.preview_at_url
    if hit.preview_url:
        return hit.preview_url
    if hit.repo_url:
        return hit.repo_url

    # Synthesize a local viewer URL if we have an uid
    if hit.uid:
        base = f"/documents/{hit.uid}"
        if hit.viewer_fragment:
            return f"{base}#{hit.viewer_fragment}"
        return base

    return None


def _extract_title_from_hit(hit: VectorSearchHit) -> str:
    """
    Human-friendly label fallback chain:
      title → file_name → uid
    """
    if hit.title:
        return hit.title
    if hit.file_name:
        return hit.file_name
    return hit.uid


def hits_to_link_parts(hits: List[VectorSearchHit]) -> List[LinkPart]:
    """
    Turn top-k RAG hits into LinkPart(kind='citation') so the UI can render a Sources list.
    Prefix titles with the numeric marker ([1], [2], …) to match bracket citations in text.
    Enrich titles with section/page info if available so that multiple hits from the same
    document are distinguishable.
    """
    parts: List[LinkPart] = []
    for idx, h in enumerate(hits, start=1):
        href = _extract_url_from_hit(h)
        if not href:
            # Keep the hit in metadata.sources for provenance; skip empty links
            continue

        # Base title comes from doc title or file name/uid
        base_title = _extract_title_from_hit(h)

        # Enrich with section/page hints
        suffix_bits = []
        if h.section:
            suffix_bits.append(f"§ {h.section}")
        if h.page is not None:
            suffix_bits.append(f"p.{h.page}")
        suffix = f" — {' · '.join(suffix_bits)}" if suffix_bits else ""

        title = f"[{idx}] {base_title}{suffix}"

        parts.append(
            LinkPart(
                href=href,
                title=title,
                kind=LinkKind.citation,
                source_id=h.uid,  # stable for hover-sync
                mime=h.mime_type or None,  # optional hint
            )
        )
    return parts


def attach_sources_to_llm_response(answer, hits: List[VectorSearchHit]):
    """
    Keep provenance in additional_kwargs['sources'] for metrics/hover sync,
    and add UI-ready LinkParts under additional_kwargs['fred_parts'].
    StreamTranscoder will hydrate them into ChatMessage.parts.
    """
    answer.additional_kwargs = getattr(answer, "additional_kwargs", {}) or {}
    answer.additional_kwargs["sources"] = [h.model_dump() for h in hits]

    link_parts = hits_to_link_parts(hits)
    if link_parts:
        answer.additional_kwargs["fred_parts"] = [lp.model_dump() for lp in link_parts]
    return answer
