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

"""How wide a text runs, in em (multiples of the font size).

The one place that answers "does this text fit": the analysis' capacity
estimate, the overflow control and the no-wrap box sizing all measure through
it, so a deck is judged by one ruler.

Measured with the font the renderer will actually use — resolved through
fontconfig, which maps a template's font to the substitute the server has, the
same mapping LibreOffice applies for the preview. The fontconfig
lookup is cached per process (it is a subprocess); the font faces are cached
per thread and by file, because one FreeType face must not be measured from
two threads at once. Measuring costs microseconds either way — the cache is
there for safety and allocation, not for parallelism.
Without fontconfig or the font file (a bare test container), a conservative
average per character stands in.
"""

from __future__ import annotations

import logging
import subprocess  # nosec: fixed argv, shell=False
import threading
from functools import lru_cache
from typing import Dict, Optional

from PIL import ImageFont

logger = logging.getLogger(__name__)

# Width per character when no font can be measured, in em. Errs wide: shrinking
# a title that would have fitted is cheaper than clipping one that does not.
FALLBACK_CHAR_EM = 0.62

# PowerPoint's default text padding, in EMU. A box lays its text inside them, so
# they come off the usable width and height before anything is measured.
DEFAULT_INSET_EMU = 91440
DEFAULT_V_INSET_EMU = 45720
# A line advances this much more than the font size, before the paragraph's own
# line spacing multiplies it.
LINE_HEIGHT = 1.2
# Greedy wrapping leaves about half a word unused at the end of every line but
# the last, which a "characters × lines" product would otherwise hand out.
WRAP_WASTE_CHARS = 3.0
# Covers the difference between the substitute font measured here and the one
# PowerPoint draws with on the author's machine.
SAFETY = 0.95

# Measuring at a large size keeps hinting and integer rounding out of the ratio.
_REF_SIZE = 1000
_FC_TIMEOUT_S = 5.0
# A face costs ~230 KB and worker threads live for the pod's lifetime.
_MAX_FACES_PER_THREAD = 16
# Representative of prose in the languages decks are written in; the average is
# what a capacity estimate needs, since the real text is not known yet.
_SAMPLE = "Les présentations montrent des phrases ordinaires, the usual mix."


_FC_SPECIAL = str.maketrans({c: f"\\{c}" for c in "-:,\\"})


@lru_cache(maxsize=64)
def _font_file(family: str, bold: bool) -> Optional[str]:
    # fontconfig reads "-", ":" and "," as pattern syntax: a family named
    # "Gotham-12" would resolve by size instead of by name.
    query = family.translate(_FC_SPECIAL)
    if bold:
        query += ":bold"
    try:
        found = subprocess.run(  # nosec: fixed argv, shell=False
            ["fc-match", "-f", "%{file}", query],
            capture_output=True,
            text=True,
            timeout=_FC_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        logger.info("[PPT][METRICS] fontconfig unavailable, estimating text widths")
        return None
    path = found.stdout.strip()
    return path or None


_local = threading.local()


def _font(family: Optional[str], bold: bool) -> Optional[ImageFont.FreeTypeFont]:
    # An empty family still resolves: fontconfig answers with its default font,
    # which is also what the renderer falls back to. Keyed by the resolved file,
    # so the dozens of families a template names share the few faces installed.
    path = _font_file(family or "sans-serif", bold)
    if path is None:
        return None
    faces: Dict[str, Optional[ImageFont.FreeTypeFont]] = (
        getattr(_local, "faces", None) or {}
    )
    _local.faces = faces
    if path not in faces:
        if len(faces) >= _MAX_FACES_PER_THREAD:
            faces.clear()
        try:
            faces[path] = ImageFont.truetype(path, _REF_SIZE)
        except OSError:
            logger.info("[PPT][METRICS] cannot read %s, estimating text widths", path)
            faces[path] = None
    return faces[path]


def width_em(text: str, family: Optional[str] = None, bold: bool = False) -> float:
    """Width of ``text`` in em: multiply by the font size to get points."""
    if not text:
        return 0.0
    font = _font(family, bold)
    if font is None:
        return len(text) * FALLBACK_CHAR_EM
    return font.getlength(text) / _REF_SIZE


def char_em(family: Optional[str] = None, bold: bool = False) -> float:
    """Average width of one character in em, for a capacity estimate."""
    return width_em(_SAMPLE, family, bold) / len(_SAMPLE) or FALLBACK_CHAR_EM


def chars_per_line(
    width_pt: float, font_pt: float, family: Optional[str], bold: bool
) -> int:
    """How many average characters fit on one line of ``width_pt``."""
    if font_pt <= 0:
        return 1
    return max(1, int(width_pt / (font_pt * char_em(family, bold))))
