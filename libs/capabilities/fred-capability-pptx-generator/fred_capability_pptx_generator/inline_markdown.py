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

"""Minimal inline-Markdown parser for `BulletItem.text`: `**bold**` and
`*italic*` only. Local rather than imported, as capability packages do not
cross-import.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Bold before italic so "**x**" reads as bold, not two empty italics around x.
# Flat (non-recursive): the first matching span wins, any markers left inside
# it are stripped rather than re-interpreted.
_INLINE_RE = re.compile(r"(\*\*(?P<bold>.+?)\*\*)|(\*(?P<italic>.+?)\*)")
_STRAY_MARKER_RE = re.compile(r"\*\*|\*")


def _strip_markers(text: str) -> str:
    return _STRAY_MARKER_RE.sub("", text)


@dataclass(frozen=True)
class Span:
    """A run of text plus the bold/italic styles to overlay on it."""

    text: str
    bold: bool = False
    italic: bool = False


def parse_inline_markdown(text: str) -> list[Span]:
    """Parse `**bold**` / `*italic*` into a flat list of styled `Span`.

    Always returns at least one span for non-empty input; markup-free text
    yields a single plain span.
    """

    spans: list[Span] = []
    pos = 0
    for match in _INLINE_RE.finditer(text):
        if match.start() > pos:
            plain = _strip_markers(text[pos : match.start()])
            if plain:
                spans.append(Span(plain))
        if match.group("bold") is not None:
            spans.append(Span(_strip_markers(match.group("bold")), bold=True))
        elif match.group("italic") is not None:
            spans.append(Span(_strip_markers(match.group("italic")), italic=True))
        pos = match.end()
    if pos < len(text):
        plain = _strip_markers(text[pos:])
        if plain:
            spans.append(Span(plain))

    if not spans:
        spans.append(Span(""))
    return spans
