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

"""Picture preparation: a picture's declared size is bounded before decoding."""

from __future__ import annotations

import pytest
from deck_builders import declared_png, png_bytes
from fred_capability_ppt_filler.images import (
    PictureTooLargeError,
    open_picture,
    prepare_picture,
)


@pytest.mark.parametrize("side", [8_000, 20_000])  # over the cap; over Pillow's own
def test_a_picture_declaring_too_many_pixels_is_refused_unread(side):
    content = declared_png(side, side)
    assert len(content) < 100
    with pytest.raises(PictureTooLargeError, match="too large"):
        prepare_picture(content)


def test_an_ordinary_picture_opens_and_prepares():
    content = png_bytes(40, 20, "red")
    with open_picture(content) as image:
        assert image.size == (40, 20)
    assert prepare_picture(content)[1:] == (40, 20)
