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

from sqlalchemy import DateTime
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    """Shared declarative base for all fred-core ORM models."""


# Portable column types: use JSONB on PostgreSQL, plain JSON on SQLite.
JsonColumn = JSONB().with_variant(JSON(), "sqlite")  # type: ignore[arg-type]
TimestampColumn = TIMESTAMP(timezone=True).with_variant(
    DateTime(timezone=True), "sqlite"
)
