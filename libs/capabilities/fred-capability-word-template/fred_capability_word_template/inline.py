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

"""Inline-Markdown parser (``**bold**``, ``*italic*``, `` `code` ``), copied from
``fred_capability_writable_document.inline``.

Parsing is flat: the first matching span wins, stray markers are stripped, and
markers inside backticks are kept literally.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Inline tokens: **bold**, *italic* / _italic_, `code`. Order matters (bold before
# italic) so ``**x**`` is read as bold, not as two empty italics around ``x``.
_INLINE_RE = re.compile(
    r"(\*\*(?P<bold>.+?)\*\*)"
    r"|(\*(?P<italic_star>.+?)\*)"
    # Intra-word underscores are literal (CommonMark): "PRJ_0001" is a code.
    r"|((?<![A-Za-z0-9])_(?P<italic_us>.+?)_(?![A-Za-z0-9]))"
    r"|(`(?P<code>.+?)`)"
)

# Parsing is flat: nested or mismatched markers (`**_x_**`) are stripped, so no
# stray `*`/`_` reaches the document (the inner span loses its formatting).
_STRAY_MARKER_RE = re.compile(r"\*\*|\*|(?<![A-Za-z0-9])_|_(?![A-Za-z0-9])")


# Markdown backslash escapes (``\[``, ``\]``, ``\#`` ...). The editor and
# the model both emit them; without this, "\[" would reach the Word export.
_ESCAPE_RE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!|~>])")
# An escaped character is held as a private-use placeholder while the spans
# are parsed, so ``\*`` is a literal star and never an emphasis marker (the
# "Rédaction" view sends literal ``*``, ``_`` and backticks this way). Plane-15 private use: never in real text.
_HOLD_BASE = 0xF0000
_HELD_RE = re.compile("[\U000f0000-\U000f007f]")


def _hold_escapes(text: str) -> str:
    return _ESCAPE_RE.sub(lambda m: chr(_HOLD_BASE + ord(m.group(1))), text)


def _release(text: str) -> str:
    return _HELD_RE.sub(lambda m: chr(ord(m.group()) - _HOLD_BASE), text)


def _strip_markers(text: str) -> str:
    """Remove stray bold/italic markers that flat parsing left behind, and
    resolve backslash escapes to the literal character."""
    return _release(_STRAY_MARKER_RE.sub("", text))


@dataclass(frozen=True)
class Span:
    """A run of text plus the inline styles to overlay on it.

    ``bold`` / ``italic`` are the styles the document writer applies. ``code`` flags
    an inline-code span, which the docx export maps to a Courier font swap. A plain
    (un-emphasised) run is a span with all flags ``False``.
    """

    text: str
    bold: bool = False
    italic: bool = False
    code: bool = False


def parse_inline_markdown(text: str) -> list[Span]:
    """Parse our inline-Markdown subset into a flat list of styled :class:`Span`.

    The grammar is ``**bold**``, ``*italic*`` / ``_italic_``, ``***both***`` (read as
    bold containing a stripped italic marker, i.e. bold) and ``` `code` ``. Parsing is
    flat; stray/nested markers are stripped from emphasised and plain text alike (never
    from code spans).

    Always returns at least one span for non-empty input. Plain text with no markup
    yields a single plain span, so a markup-free value is written as one run - the
    backward-compatible path.
    """
    spans: list[Span] = []
    pos = 0
    text = _hold_escapes(text)
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
            spans.append(Span(_release(m.group("code")), code=True))
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
