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

Shape coverage. A placeholder is fillable wherever python-pptx exposes a text frame, so
the traversal walks, recursively:

- plain text boxes, titles, and other placeholders (``has_text_frame`` shapes);
- **table** cells (each cell is a text frame);
- **grouped** shapes — recursing into the group, so a text box / table nested at any
  depth is reached.

Still out of scope (no clean ``text_frame`` API in python-pptx; text lives in low-level
DrawingML XML): **SmartArt** (``DIAGRAM`` / ``IGX_GRAPHIC``) and **chart** text. Keys
placed there are not seen by the parser and therefore not filled; this is documented in
the RFC rather than silently mis-handled.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Callable, List

if TYPE_CHECKING:  # pragma: no cover - typing only
    from pptx.shapes.base import BaseShape
    from pptx.slide import Slide
    from pptx.text.text import _Paragraph

# A placeholder is ``{{key}}``. The key is everything between the braces that is not a
# closing brace. This matches the RFC/issue contract exactly.
KEY_PATTERN = re.compile(r"\{\{([^}]+)\}\}")


def _iter_shape_paragraphs(shape: "BaseShape") -> List["_Paragraph"]:
    """Yield every text paragraph reachable from ``shape``, recursing as needed.

    Three text-bearing shape kinds are handled, in priority order:

    - a **group** (``shape_type`` GROUP, exposing ``.shapes``): recurse into each child
      so nested text boxes / tables at any depth are reached;
    - a **table** (``has_table``): every cell is a text frame;
    - a plain **text frame** (``has_text_frame``): its own paragraphs.

    Any other shape (pictures, media, OLE, ink, lines, and — for now — SmartArt and
    charts) contributes no paragraphs.
    """
    paragraphs: List["_Paragraph"] = []

    # Group: recurse. Checked first because a group is itself neither has_text_frame nor
    # has_table, but its children may be either.
    if getattr(shape, "shapes", None) is not None and not shape.has_text_frame:
        for child in shape.shapes:  # type: ignore[attr-defined]
            paragraphs.extend(_iter_shape_paragraphs(child))
        return paragraphs

    # Table: each cell carries its own text frame.
    if getattr(shape, "has_table", False):
        for row in shape.table.rows:  # type: ignore[attr-defined]
            for cell in row.cells:
                paragraphs.extend(cell.text_frame.paragraphs)
        return paragraphs

    # Plain text frame (text box, title, other placeholder, auto-shape, ...).
    if shape.has_text_frame:
        paragraphs.extend(shape.text_frame.paragraphs)  # type: ignore[attr-defined]

    return paragraphs


def _iter_text_paragraphs(slide: "Slide") -> List["_Paragraph"]:
    """Yield every fillable paragraph on ``slide``, descending into tables and groups."""
    paragraphs: List["_Paragraph"] = []
    for shape in slide.shapes:
        paragraphs.extend(_iter_shape_paragraphs(shape))
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
