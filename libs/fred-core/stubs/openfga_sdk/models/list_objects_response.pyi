from __future__ import annotations

class ListObjectsResponse:
    objects: list[str]

    def __init__(
        self,
        objects: list[str],
    ) -> None: ...
