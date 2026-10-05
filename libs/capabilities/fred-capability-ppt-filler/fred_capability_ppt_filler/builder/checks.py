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

"""After-render check of duplicated example slides, and the per-slide report.

The renderer records into a :class:`DeckReport` what it truncated or could not
place; :func:`remove_leftovers` adds the example text it had to sweep away.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Collection, Dict, Iterable, List, cast

from pptx.oxml.ns import qn

from fred_capability_ppt_filler.traversal import walk_shapes

# Placeholders the template means to keep on every slide.
_FIELD_PLACEHOLDERS = frozenset({"FOOTER", "DATE", "SLIDE_NUMBER"})


@dataclass
class SlideReport:
    position: int
    # Example text found on the slide after filling, and removed.
    removed: List[str] = field(default_factory=list)
    # Roles of the zones whose text was cut at a word boundary.
    truncated: List[str] = field(default_factory=list)
    # Plan content no zone received ("subtitle", "2 item(s)", ...).
    lost: List[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not (self.removed or self.truncated or self.lost)


@dataclass
class DeckReport:
    slides: Dict[int, SlideReport] = field(default_factory=dict)

    def slide(self, position: int) -> SlideReport:
        return self.slides.setdefault(position, SlideReport(position))

    def issues(self) -> List[SlideReport]:
        """Slides with something to report, in deck order."""
        return [r for _, r in sorted(self.slides.items()) if not r.clean]


def _text(shape) -> str:
    return shape.text_frame.text.replace("\x0b", "\n").strip()


def _is_field(shape) -> bool:
    if shape.is_placeholder:
        kind = shape.placeholder_format.type
        if kind is not None and kind.name in _FIELD_PLACEHOLDERS:
            return True
    return shape.text_frame._txBody.find(f".//{qn('a:fld')}") is not None


def _text_shapes(slide) -> Iterable[tuple[str, Any]]:
    for placed in walk_shapes(slide.shapes):
        shape = cast(Any, placed.shape)
        if getattr(shape, "has_text_frame", False) and not _is_field(shape):
            yield "sp:" + "/".join(str(p) for p in placed.path), shape


def original_texts(slide) -> Dict[str, str]:
    """Shape-id path key → text of each text shape of an example slide."""
    return {key: text for key, shape in _text_shapes(slide) if (text := _text(shape))}


def _clear(shape) -> None:
    txBody = shape.text_frame._txBody
    paragraphs = txBody.findall(qn("a:p"))
    for extra in paragraphs[1:]:
        txBody.remove(extra)
    for child in list(paragraphs[0]):
        if child.tag in (qn("a:r"), qn("a:br"), qn("a:fld")):
            paragraphs[0].remove(child)


def remove_leftovers(
    slide,
    originals: Dict[str, str],
    handled: Collection[Any],
    shared: Collection[str],
) -> List[str]:
    """Remove the example text a duplicated slide still shows; returns it.

    ``handled`` holds the elements of the zones the renderer filled, cleared or
    was told to keep; ``shared`` the template's repeated texts (footers).
    """
    removed: List[str] = []
    for key, shape in list(_text_shapes(slide)):
        text = _text(shape)
        if (
            not text
            or originals.get(key) != text
            or text in shared
            or any(shape._element is element for element in handled)
        ):
            continue
        removed.append(text)
        if shape.is_placeholder:
            # An empty placeholder shows its prompt in PowerPoint: drop it.
            element = shape._element
            element.getparent().remove(element)
        else:
            _clear(shape)
    return removed
