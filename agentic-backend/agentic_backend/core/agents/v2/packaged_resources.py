from __future__ import annotations

from collections.abc import Callable, Sequence
from importlib.resources import files
from importlib.resources.abc import Traversable
from typing import TypeVar

T = TypeVar("T")


def load_packaged_resource(
    *,
    package: str,
    path_parts: Sequence[str],
    decoder: Callable[[Traversable], T],
    missing_resource_kind: str,
) -> T:
    """
    Resolve a package-relative resource path and decode it with one caller-supplied
    decoder while preserving consistent missing-resource handling.
    """

    if not path_parts:
        raise ValueError("path_parts must contain at least one path segment.")

    resource_path = files(package)
    for part in path_parts:
        resource_path = resource_path.joinpath(part)

    try:
        return decoder(resource_path)
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"Missing packaged {missing_resource_kind} resource: {resource_path}"
        ) from exc
