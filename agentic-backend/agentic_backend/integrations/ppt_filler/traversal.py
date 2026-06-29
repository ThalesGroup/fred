"""Shared text-frame traversal for the PPT Filler toolkit.

This is the single seam reused by BOTH directions of the feature:

- **List** (used by the parser, PPTFILL-01): find every ``{{key}}`` occurrence on a
  slide.
- **Replace** (used by the filler, PPTFILL-05): replace every ``{{key}}`` occurrence on
  a slide with a provided value.

Both directions share the same run-merging logic so they can never diverge: any key the
parser surfaces is guaranteed fillable, and vice versa. The round-trip test
(``parse → fill → re-parse``) is the regression guard for that invariant.

PowerPoint frequently splits a single ``{{key}}`` placeholder across several runs inside
one paragraph (e.g. because of autocorrect or spell-check spans). Both directions
therefore merge the run texts of a paragraph, operate on the merged string, and map the
result back onto the runs.

Scope limit (matches the POC and the RFC): only ``has_text_frame`` shapes are walked.
Table cells and grouped shapes are intentionally **not** traversed in v1 — they are
documented as out of scope rather than silently dropped.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Callable, List

if TYPE_CHECKING:  # pragma: no cover - typing only
    from pptx.slide import Slide
    from pptx.text.text import _Paragraph

# A placeholder is ``{{key}}``. The key is everything between the braces that is not a
# closing brace. This matches the RFC/issue contract exactly.
KEY_PATTERN = re.compile(r"\{\{([^}]+)\}\}")


def _iter_text_paragraphs(slide: "Slide") -> List["_Paragraph"]:
    """Yield every paragraph of every ``has_text_frame`` shape on ``slide``.

    Table cells and grouped shapes are intentionally skipped (v1 scope limit).
    """
    paragraphs: List["_Paragraph"] = []
    for shape in slide.shapes:
        if not shape.has_text_frame:
            continue
        for paragraph in shape.text_frame.paragraphs:  # type: ignore[attr-defined]
            paragraphs.append(paragraph)
    return paragraphs


def list_keys_on_slide(slide: "Slide") -> List[str]:
    """Return every ``{{key}}`` key found in the text-frame shapes of ``slide``.

    Keys are returned in document order with duplicates preserved; de-duplication (when
    needed) is the caller's responsibility. Keys are reconstructed even when PowerPoint
    splits a placeholder across multiple runs within a paragraph, because the run texts
    of each paragraph are merged before matching.
    """
    keys: List[str] = []
    for paragraph in _iter_text_paragraphs(slide):
        merged = "".join(run.text for run in paragraph.runs)
        for match in KEY_PATTERN.finditer(merged):
            keys.append(match.group(1).strip())
    return keys


def replace_keys_on_slide(slide: "Slide", value_for: Callable[[str], str]) -> None:
    """Replace every ``{{key}}`` occurrence in the text-frame shapes of ``slide``.

    ``value_for`` maps a (stripped) key to its replacement string. It is called once per
    placeholder occurrence; every occurrence of a key on the slide is filled
    consistently as long as ``value_for`` is deterministic.

    The same run-merging logic as :func:`list_keys_on_slide` is used, so a key split
    across runs is correctly replaced. After substitution, the rewritten text is written
    back onto the paragraph's first run and the remaining runs of that paragraph are
    cleared, which preserves the first run's formatting for the whole paragraph.
    """
    for paragraph in _iter_text_paragraphs(slide):
        runs = list(paragraph.runs)
        if not runs:
            continue
        merged = "".join(run.text for run in runs)
        if not KEY_PATTERN.search(merged):
            continue

        replaced = KEY_PATTERN.sub(
            lambda match: value_for(match.group(1).strip()), merged
        )
        if replaced == merged:
            continue

        # Collapse the paragraph onto its first run. Merging runs means we cannot keep
        # per-run formatting for the substituted region, so we keep the first run's
        # formatting for the whole paragraph (matches the POC behavior).
        runs[0].text = replaced
        for extra_run in runs[1:]:
            extra_run.text = ""
