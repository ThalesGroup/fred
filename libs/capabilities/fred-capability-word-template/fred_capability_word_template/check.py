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

"""Where the document stands: the places
of each part still holding the template's own text, for the prompt and the
edit replies.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from sqlalchemy.exc import SQLAlchemyError

from fred_capability_word_template.analysis import (
    TemplateAnalysis,
    address_ranges,
    parse_analysis,
)
from fred_capability_word_template.docmap import (
    DocMap,
    MapElement,
    PartCheck,
    UnusedRange,
    build_map,
    check_parts,
    is_toc,
    parts,
    unused_template_ranges,
)
from fred_capability_word_template.documents import (
    Active,
    BaseDoc,
    Documents,
    Lru,
)
from fred_capability_word_template.render import TODO_MARKER_RE
from fred_capability_word_template.store import (
    get_word_template_store,
)

logger = logging.getLogger(__name__)
# The document check per (document bytes, base sha256): read on every model
# call, recomputed only when the document changed.
CHECKS: Lru[tuple[int, int, str, bool], list[PartCheck]] = Lru(128)
# What the check looks for in a base, per (base sha256, has analysis).
_CHECK_BASES: Lru[tuple[str, bool], CheckBasis] = Lru(64)


def touched_checks(
    before: DocMap, after: DocMap, ids: Sequence[str], basis: CheckBasis
) -> list[str]:
    """The checks of the touched parts, found after the batch by title (a
    removal or an insertion renumbers the parts)."""
    titles = {p.part_id: p.title for p in parts(before)}
    checks = check_parts(
        after,
        basis.template,
        basis.fields,
        notes=basis.notes,
        is_marker=lambda text: TODO_MARKER_RE.search(text) is not None,
    )
    by_title = {c.title: c for c in checks}
    by_id = {c.part_id: c for c in checks}
    out: list[str] = []
    for part_id in ids:
        check = by_title.get(titles.get(part_id, "")) or by_id.get(part_id)
        if check is not None and render_part_check(check) not in out:
            out.append(render_part_check(check))
    return out


_MAX_CHECK_PLACES = 10
_LEFTOVER_LABELS = {
    "template": "template text still in place",
    "field": "detail to fill inside fixed wording (replace_text only)",
    "marker": "to complete (raise it with the collaborator)",
    "empty": "nothing written under this heading",
}


def part_status(check: PartCheck) -> str:
    if check.empty:
        return "nothing written under its heading yet"
    markers = len(check.leftovers) - check.places_left
    if check.places_left:
        status = f"{check.places_left} place(s) left"
    else:
        status = "finished"
    return f"{status}, {markers} [À COMPLÉTER] marker(s)" if markers else status


def render_part_check(check: PartCheck) -> str:
    """The check of one part, for the reply of the batch that touched it."""
    lines = [f'CHECK of part {check.part_id} ("{check.title}"): {part_status(check)}.']
    for kind in ("template", "field", "empty", "marker"):
        found = [left for left in check.leftovers if left.kind == kind]
        for left in found[:_MAX_CHECK_PLACES]:
            text = left.text if len(left.text) <= 60 else left.text[:59] + "..."
            where = f"{left.where} - " if left.where else ""
            lines.append(f'- {_LEFTOVER_LABELS[kind]}: {where}{left.address} "{text}"')
        if len(found) > _MAX_CHECK_PLACES:
            lines.append(f"- ... and {len(found) - _MAX_CHECK_PLACES} more")
    return "\n".join(lines)


def _covered_paragraphs(
    base_map: DocMap, address: str, order: Mapping[str, int]
) -> list[MapElement]:
    """The base's paragraphs with text that an analysis address covers,
    directly or inside a covered table, row or cell."""
    picked: list[MapElement] = []
    for first, last in address_ranges(address):
        a, b = order.get(first), order.get(last)
        if a is not None and b is not None:
            picked.extend(base_map.elements[min(a, b) : max(a, b) + 1])
    prefixes = tuple(f"{e.address}." for e in picked)
    own = {e.address for e in picked}
    return [
        e
        for e in base_map.elements
        if e.kind == "paragraph"
        and e.text.strip()
        and (e.address in own or e.address.startswith(prefixes))
    ]


def _paragraphs_with_role(
    base_map: DocMap, analysis: TemplateAnalysis | None, roles: tuple[str, ...]
) -> list[MapElement]:
    """The base's paragraphs with text that the analysis gives one of ``roles``."""
    order = {e.address: i for i, e in enumerate(base_map.elements)}
    return [
        e
        for part in (analysis.parts if analysis is not None else [])
        for role in part.elements
        if role.role in roles
        for e in _covered_paragraphs(base_map, role.address, order)
    ]


def _guidance_paragraphs(
    base_map: DocMap, analysis: TemplateAnalysis | None
) -> list[MapElement]:
    """The paragraphs the analysis calls guidance or placeholders. A role
    over a whole table or rows covers its headings and labels too: there,
    only coloured text or a placeholder pattern counts."""
    order = {e.address: i for i, e in enumerate(base_map.elements)}
    out: list[MapElement] = []
    for part in analysis.parts if analysis is not None else []:
        for role in part.elements:
            if role.role not in ("replace", "fill"):
                continue
            whole = any(
                (start := base_map.get(first)) is not None
                and start.kind in ("table", "row")
                for first, _last in address_ranges(role.address)
            )
            out.extend(
                e
                for e in _covered_paragraphs(base_map, role.address, order)
                if not whole
                or e.color is not None
                or _PLACEHOLDER_RE.search(TODO_MARKER_RE.sub("", e.text))
            )
    return out


def fixed_texts(base_map: DocMap, analysis: TemplateAnalysis) -> frozenset[str]:
    """The base's paragraphs the analysis calls fixed wording (headings
    excluded: they are protected on their own). A text the analysis also
    calls guidance, or a body paragraph coloured whole, is not protected; a
    fixed text with only a coloured passage (a link) stays protected."""
    fixed = frozenset(
        e.text.strip()
        for e in _paragraphs_with_role(base_map, analysis, ("fixed",))
        if e.heading_level is None
    )
    contradicted = {e.text.strip() for e in _guidance_paragraphs(base_map, analysis)}
    contradicted.update(
        e.text.strip()
        for e in base_map.elements
        if e.kind == "paragraph"
        and e.container == ""
        and e.color is not None
        and not e.color.startswith("partly")
    )
    return fixed - contradicted


def template_texts(
    base_map: DocMap, analysis: TemplateAnalysis | None
) -> frozenset[str]:
    """The base's texts meant to be replaced: the elements the analysis
    calls guidance/sample ("replace") or placeholders ("fill"), and the body
    paragraphs in a colour other than the body's (table and header labels
    are often coloured, so they count only through the analysis)."""
    texts = {
        e.text.strip()
        for e in _guidance_paragraphs(base_map, analysis)
        if not is_toc(e)
    }
    texts.update(
        e.text.strip()
        for e in base_map.elements
        if e.kind == "paragraph"
        and e.text.strip()
        and e.color is not None
        and e.container == ""
        and not is_toc(e)
    )
    return frozenset(texts | placeholder_texts(base_map))


# Generic signs of a place to fill, whatever the template: a bracketed or
# angle-bracketed field, XXX, lorem ipsum, zero-filled dates or numbers, dot
# or underscore leaders. Never a reason to drop fixed-wording protection.
_PLACEHOLDER_RE = re.compile(
    r"\[[^\[\]\n]{1,80}\]|<[^<>\n]{0,60}>|\bx{3,}\b|lorem ipsum|\b0{2,}\b"
    r"|\b(?:jj|dd)[/.-]mm[/.-](?:aaaa|aa|yyyy|yy)\b|_{4,}|\.{5,}|…{3,}",
    re.IGNORECASE,
)


def placeholder_texts(base_map: DocMap) -> frozenset[str]:
    """The base's paragraphs holding a generic placeholder (TOC lines and
    [À COMPLÉTER] markers aside)."""
    return frozenset(
        e.text.strip()
        for e in base_map.elements
        if e.kind == "paragraph"
        and e.text.strip()
        and not is_toc(e)
        and _PLACEHOLDER_RE.search(TODO_MARKER_RE.sub("", e.text))
    )


@dataclass(frozen=True)
class CheckBasis:
    """What the document check looks for, from the base: texts to replace,
    fixed paragraphs holding a placeholder, and the analysis' notes."""

    template: frozenset[str]
    fields: frozenset[str]
    notes: Mapping[str, str]
    # Shown whole to the model: what it keeps or replaces must not be guessed.
    full: frozenset[str] = frozenset()
    # Every text of the base: what is still untouched template content.
    base: frozenset[str] = frozenset()
    # Real titles in every heading (a contract's outline, not sample
    # headings to rename): the model adds no heading of its own there.
    fixed_outline: bool = False


def check_basis(base_map: DocMap, analysis: TemplateAnalysis | None) -> CheckBasis:
    fixed = fixed_texts(base_map, analysis) if analysis is not None else frozenset()
    notes: dict[str, str] = {}
    order = {e.address: i for i, e in enumerate(base_map.elements)}
    for part in analysis.parts if analysis is not None else []:
        for role in part.elements:
            if role.note.strip():
                for e in _covered_paragraphs(base_map, role.address, order):
                    notes.setdefault(e.text.strip(), f'"{role.note.strip()}"')
    template = template_texts(base_map, analysis) - fixed
    headings = [
        text
        for e in base_map.elements
        if e.heading_level is not None
        and e.story == "body"
        and (text := e.text.strip())
    ]
    return CheckBasis(
        template=template,
        fields=fixed & placeholder_texts(base_map),
        notes=notes,
        full=fixed | template,
        base=frozenset(
            text
            for e in base_map.elements
            if e.kind == "paragraph" and (text := e.text.strip())
        ),
        # Unknown without an analysis: the outline is then treated as open.
        fixed_outline=analysis is not None
        and bool(headings)
        and not any(h in template for h in headings),
    )


async def stored_analysis(sha: str) -> TemplateAnalysis | None:
    """The analysis stored in `cap_word_template_analyses`."""
    try:
        cached = await get_word_template_store().get_analysis(sha)
    except (SQLAlchemyError, OSError):
        logger.exception("[WORD_TEMPLATE] failed to read the analysis cache")
        return None
    if not cached:
        return None
    try:
        return parse_analysis(cached)
    except ValueError:
        logger.warning("[WORD_TEMPLATE] cached analysis of %s unusable", sha)
        return None


async def cached_check_basis(
    base: BaseDoc, analysis: TemplateAnalysis | None
) -> CheckBasis:
    key = (base.sha256, analysis is not None)
    cached = _CHECK_BASES.get(key)
    if cached is None:
        cached = await asyncio.to_thread(
            lambda: check_basis(build_map(base.docx), analysis)
        )
        _CHECK_BASES.put(key, cached)
    return cached


async def batch_check_basis(docs: Documents, active: Active) -> CheckBasis | None:
    """The check basis for an edit's reply, from the stored analysis only
    (an edit never starts an analysis); None when the base is unreadable."""
    try:
        base = await docs.base_doc(active.base)
        analysis = (
            active.entry.analysis
            if active.entry is not None and active.entry.analysis is not None
            else await stored_analysis(base.sha256)
        )
        return await cached_check_basis(base, analysis)
    except Exception:  # noqa: BLE001 - the check must never fail an applied edit
        logger.warning(
            "[WORD_TEMPLATE] failed to build the document check", exc_info=True
        )
        return None


def unused_parts(docx: bytes, basis: CheckBasis) -> list[UnusedRange]:
    return unused_template_ranges(
        build_map(docx),
        basis.template,
        basis.base,
        is_marker=lambda text: TODO_MARKER_RE.search(text) is not None,
    )


def document_check(docx: bytes, basis: CheckBasis) -> list[PartCheck]:
    return check_parts(
        build_map(docx),
        basis.template,
        basis.fields,
        notes=basis.notes,
        is_marker=lambda text: TODO_MARKER_RE.search(text) is not None,
    )
