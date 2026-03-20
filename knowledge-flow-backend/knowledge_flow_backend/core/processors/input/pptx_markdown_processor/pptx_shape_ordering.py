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

"""Sorts PPTX shapes in visual reading order."""

from __future__ import annotations

from typing import Any, Iterable, List, Tuple


def _shape_position(shape: Any) -> Tuple[int, int]:
    """
    Return a stable (top, left) tuple for visual reading order.
    Shapes missing coordinates are pushed to the end.
    """
    top = getattr(shape, "top", None)
    left = getattr(shape, "left", None)

    if top is None:
        top = 10**12
    if left is None:
        left = 10**12

    return int(top), int(left)


def sort_shapes_reading_order(shapes: Iterable[Any]) -> List[Any]:
    """
    Sort shapes in a simple reading order:
    top-to-bottom, then left-to-right.
    """
    return sorted(list(shapes), key=_shape_position)
