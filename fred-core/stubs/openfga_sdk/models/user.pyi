from __future__ import annotations

from typing import Any

from openfga_sdk.models.fga_object import FgaObject


class User:
    object: FgaObject | None
    userset: Any
    wildcard: Any

    def __init__(
        self,
        object: FgaObject | None = ...,
        userset: Any = ...,
        wildcard: Any = ...,
    ) -> None: ...
