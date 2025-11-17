from __future__ import annotations

from datetime import datetime

from openfga_sdk.models.tuple_key import TupleKey


class Tuple:
    key: TupleKey
    timestamp: datetime

    def __init__(self, key: TupleKey, timestamp: datetime) -> None: ...
