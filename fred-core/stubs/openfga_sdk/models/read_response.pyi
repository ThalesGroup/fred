from __future__ import annotations

from openfga_sdk.models.tuple import Tuple


class ReadResponse:
    tuples: list[Tuple]
    continuation_token: str

    def __init__(
        self,
        tuples: list[Tuple],
        continuation_token: str,
    ) -> None: ...
