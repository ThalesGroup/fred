from __future__ import annotations

from datetime import datetime
from typing import Any


class Store:
    id: str
    name: str
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None

    def __init__(
        self,
        id: str,
        name: str,
        created_at: datetime,
        updated_at: datetime,
        deleted_at: datetime | None = ...,
        local_vars_configuration: Any | None = ...,
    ) -> None: ...
