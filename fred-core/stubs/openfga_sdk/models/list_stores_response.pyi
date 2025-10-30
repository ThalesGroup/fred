from __future__ import annotations

from typing import Any, Sequence

from openfga_sdk.models.store import Store


class ListStoresResponse:
    stores: list[Store]
    continuation_token: str

    def __init__(
        self,
        stores: Sequence[Store],
        continuation_token: str,
        local_vars_configuration: Any | None = ...,
    ) -> None: ...
