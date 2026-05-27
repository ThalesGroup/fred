from __future__ import annotations

class TupleKey:
    user: str
    relation: str
    object: str
    condition: object | None

    def __init__(
        self,
        user: str,
        relation: str,
        object: str,
        condition: object | None = ...,
    ) -> None: ...
