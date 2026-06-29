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

"""Format-agnostic inline-Markdown parser shared by the docx export and the PPT filler.

This is the single source of truth for the inline-Markdown SUBSET our document
generators understand: ``**bold**``, ``*italic*`` / ``_italic_``, ``***both***`` and
``` `code` ```. It is pure (no docx/pptx import) so the two consumers — the Word export
([`docx_export.py`](../writable_documents/docx_export.py)) and the PowerPoint filler
([`ppt_filler/traversal.py`](../../integrations/ppt_filler/traversal.py)) — can never
diverge on what a marker means: each only owns the thin step of writing the parsed
:class:`Span` list as its own runs.

Parsing is intentionally FLAT (non-recursive): the first matching span wins and any
markers left inside it (e.g. the ``_x_`` in ``**_x_**``) are stripped rather than
re-interpreted. Stray/mismatched markers anywhere in the text are stripped too, so no
literal ``*`` or ``_`` ever leaks into the output. Code spans are the one exception:
markers inside backticks are literal and are preserved untouched.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

# Inline tokens: **bold**, *italic* / _italic_, `code`. Order matters (bold before
# italic) so ``**x**`` is read as bold, not as two empty italics around ``x``.
_INLINE_RE = re.compile(
    r"(\*\*(?P<bold>.+?)\*\*)"
    r"|(\*(?P<italic_star>.+?)\*)"
    r"|(_(?P<italic_us>.+?)_)"
    r"|(`(?P<code>.+?)`)"
)

# Leftover emphasis markers we strip from text once the outer span is resolved.
# We only do flat (non-recursive) inline parsing, so nested or mismatched markers
# (e.g. `**_x_**`, `_a *b* c_`) would otherwise leak through as literal characters.
# Stripping them keeps clean text — the formatting of the inner span is lost, but
# no stray `*`/`_` ever appears in the output.
_STRAY_MARKER_RE = re.compile(r"\*\*|[*_]")


def _strip_markers(text: str) -> str:
    """Remove stray bold/italic markers that flat parsing left behind."""
    return _STRAY_MARKER_RE.sub("", text)


@dataclass(frozen=True)
class Span:
    """A run of text plus the inline styles to overlay on it.

    ``bold`` / ``italic`` are the styles the document writers apply. ``code`` flags an
    inline-code span: the docx export maps it to a Courier font swap, while the pptx
    filler treats it as plain text (it is outside this feature's bold/italic scope). A
    plain (un-emphasised) run is a span with all flags ``False``.
    """

    text: str
    bold: bool = False
    italic: bool = False
    code: bool = False


def parse_inline_markdown(text: str) -> List[Span]:
    """Parse our inline-Markdown subset into a flat list of styled :class:`Span`.

    The grammar is exactly the one the docx export historically owned: ``**bold**``,
    ``*italic*`` / ``_italic_``, ``***both***`` (read as bold containing a stripped
    italic marker, i.e. bold) and ``` `code` ```. Parsing is flat; stray/nested markers
    are stripped from emphasised and plain text alike (never from code spans).

    Always returns at least one span for non-empty input. Plain text with no markup
    yields a single plain span, so a markup-free value is written as one run — the
    backward-compatible path.
    """
    spans: List[Span] = []
    pos = 0
    for m in _INLINE_RE.finditer(text):
        if m.start() > pos:
            plain = _strip_markers(text[pos : m.start()])
            if plain:
                spans.append(Span(plain))
        if m.group("bold") is not None:
            # Inner text may carry nested markers (e.g. **_x_**); strip them so only the
            # outermost emphasis applies and no markers leak through.
            spans.append(Span(_strip_markers(m.group("bold")), bold=True))
        elif m.group("italic_star") is not None:
            spans.append(Span(_strip_markers(m.group("italic_star")), italic=True))
        elif m.group("italic_us") is not None:
            spans.append(Span(_strip_markers(m.group("italic_us")), italic=True))
        elif m.group("code") is not None:
            # Code spans are literal: do not strip markers inside backticks.
            spans.append(Span(m.group("code"), code=True))
        pos = m.end()
    if pos < len(text):
        plain = _strip_markers(text[pos:])
        if plain:
            spans.append(Span(plain))

    # Guarantee at least one span so consumers always have a run to write. Stripping can
    # reduce a markers-only fragment (e.g. "**") to "", which would otherwise yield none.
    if not spans:
        spans.append(Span(""))
    return spans
