"""
Optional Fred-specific conveniences for authored Python tools.

Why this module exists:
- the core `ToolContext` should stay generic and small for agent authors
- some Fred projects still want short helpers around the built-in
  `knowledge.search` tool and legacy tuning fields

How to use it:
- access this functionality through `context.helpers`
- prefer the generic `ToolContext.invoke_tool(...)` path for new code

Example:
- `hits = await context.helpers.search_corpus("retention policy", top_k=5)`
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from fred_core.store import VectorSearchHit

if TYPE_CHECKING:
    from .api import ToolContext

_MAX_UNIQUE_CHUNKS = 40


@dataclass(frozen=True)
class SearchBundle:
    """
    Aggregated result bundle for repeated corpus-search calls.

    Why this exists:
    - some Fred-authored tools want both merged excerpt text and raw search
      hits after several calls to the built-in `knowledge.search` tool

    How to use it:
    - call `context.helpers.search_corpus_many(...)` and inspect `text`, `ranked_filenames`,
      and `hits`

    Example:
    - `bundle = await context.helpers.search_corpus_many((("retention policy", 5),))`
    """

    text: str
    ranked_filenames: tuple[str, ...]
    hits: tuple[VectorSearchHit, ...]


class ToolContextHelpers:
    """
    Explicit helper namespace for authored tools that want Fred-specific shortcuts.

    Why this exists:
    - the main `ToolContext` should stay generic
    - some Fred projects still want convenience helpers tied to built-in Fred
      behaviors such as corpus search or legacy tuning fields

    How to use it:
    - access it through `context.helpers`
    - keep usage explicit so authored tools signal when they rely on optional
      Fred shortcuts instead of the generic SDK surface

    Example:
    - `bundle = await context.helpers.search_corpus_many((("retention policy", 5),))`
    """

    def __init__(self, context: "ToolContext") -> None:
        self._context = context

    def setting_text(self, key: str, *, default: str = "") -> str:
        """
        Read one legacy string tuning field from agent settings.

        Why this exists:
        - a few older authored tools still read prompt/config text from the legacy
          `AgentSettings.tuning.fields` shape

        How to use it:
        - use only when a tool still depends on a tuning field stored in agent
          settings
        - prefer explicit tool arguments or resources in new code

        Example:
        - `template_key = context.helpers.setting_text("template_key", default="ppt_template.pptx")`
        """
        tuning = self._context._runtime.settings.tuning
        if tuning is None:
            return default
        for field in tuning.fields:
            if field.key != key:
                continue
            if isinstance(field.default, str) and field.default.strip():
                return field.default.strip()
        return default

    async def search_corpus(
        self,
        query: str,
        *,
        top_k: int = 8,
    ) -> tuple[VectorSearchHit, ...]:
        """
        Call the built-in `knowledge.search` tool and return its hits.

        Why this exists:
        - corpus retrieval is a common Fred pattern, so older or RAG-oriented
          authored tools may want a short explicit helper

        How to use it:
        - pass the natural-language query and the desired `top_k`
        - prefer `context.invoke_tool(...)` for the generic SDK path

        Example:
        - `hits = await context.helpers.search_corpus("retention policy", top_k=5)`
        """
        result = await self._context.invoke_tool(
            "knowledge.search", query=query, top_k=top_k
        )
        return result.sources

    async def search_corpus_many(
        self,
        queries: Sequence[tuple[str, int]],
        *,
        context_hint: str = "",
    ) -> SearchBundle:
        """
        Run several corpus-search queries and merge the best excerpts.

        Why this exists:
        - some Fred RAG-oriented tools want one helper that aggregates repeated
          calls to the built-in `knowledge.search` tool

        How to use it:
        - pass `(query, top_k)` tuples
        - use this only when a Fred-specific merged search bundle is convenient

        Example:
        - `bundle = await context.helpers.search_corpus_many((("retention policy", 5), ("deletion", 3)))`
        """
        all_hits: list[VectorSearchHit] = []
        seen: set[tuple[str, str]] = set()

        for query, top_k in queries:
            rendered_query = (
                f"{query}\nContexte: {context_hint}" if context_hint else query
            )
            hits = await self.search_corpus(rendered_query, top_k=top_k)
            for hit in hits:
                dedupe_key = (hit.uid, hit.content[:100])
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                all_hits.append(hit)

        if not all_hits:
            return SearchBundle(text="", ranked_filenames=(), hits=())

        all_hits.sort(key=lambda hit: hit.score or 0.0, reverse=True)
        top_hits = tuple(all_hits[:_MAX_UNIQUE_CHUNKS])

        filename_scores: dict[str, float] = {}
        for hit in top_hits:
            file_name = hit.file_name or hit.title or hit.uid
            filename_scores[file_name] = filename_scores.get(file_name, 0.0) + float(
                hit.score or 0.0
            )
        ranked_filenames = tuple(
            sorted(
                filename_scores,
                key=lambda name: filename_scores[name],
                reverse=True,
            )
        )

        formatted_chunks = []
        for index, hit in enumerate(top_hits, start=1):
            title = hit.title or hit.file_name or hit.uid
            formatted_chunks.append(
                f"### Extrait {index} (source: {title})\n{hit.content}"
            )
        return SearchBundle(
            text="\n\n".join(formatted_chunks),
            ranked_filenames=ranked_filenames,
            hits=top_hits,
        )


__all__ = [
    "ToolContextHelpers",
    "SearchBundle",
]
