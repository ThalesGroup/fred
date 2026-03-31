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
    Resolve and decode one packaged resource by explicit package-relative path.

    Why this helper exists:
    - several author-facing helpers need the same strict packaged-resource lookup
    - callers should get one consistent error when a packaged file is missing

    How to use it:
    - pass the owning Python package
    - pass the relative path segments inside that package
    - pass a decoder that turns the resolved resource into the desired type

    Example:
    - `text = load_packaged_resource(package="my_pkg", path_parts=("prompts", "system.md"), decoder=lambda p: p.read_text("utf-8"), missing_resource_kind="Markdown")`
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
