# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

from typing import Any

from pydantic import TypeAdapter
from sqlalchemy import Column, Table, insert, select
from sqlalchemy.engine import Connection


class SeedMarkerMixin:
    """
    Common helpers to manage a seed marker row (e.g., '__static_seeded__').
    """

    seed_marker_id: str = "__static_seeded__"

    def seed_marker_exists(self, conn: Connection, pk_column: Column) -> bool:
        stmt = select(pk_column).where(pk_column == self.seed_marker_id).limit(1)
        return conn.execute(stmt).first() is not None

    def insert_seed_marker(
        self, conn: Connection, table: Table, pk_column: Column
    ) -> None:
        conn.execute(insert(table).values({pk_column.name: self.seed_marker_id}))


class PydanticJsonMixin:
    """
    Serialize/deserialize models using a Pydantic v2 TypeAdapter.
    """

    @staticmethod
    def dump_json(adapter: TypeAdapter, model: Any) -> str:
        raw = adapter.dump_json(model, exclude_none=True)
        return raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw)

    @staticmethod
    def load_json(adapter: TypeAdapter, payload: str | bytes | None) -> Any:
        data = (
            payload.decode("utf-8") if isinstance(payload, bytes) else payload or "{}"
        )
        return adapter.validate_json(data)
