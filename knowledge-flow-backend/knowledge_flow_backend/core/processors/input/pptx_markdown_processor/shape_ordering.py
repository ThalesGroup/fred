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
