# Copyright Thales 2026
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

from datetime import datetime, timezone

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for all control-plane-backend ORM models.

    All model classes must inherit from this Base so that Base.metadata
    captures every table for Alembic autogenerate.
    """


def utcnow() -> datetime:
    """
    Return one timezone-aware UTC timestamp for ORM defaults and store queries.

    Why this function exists:
    - control-plane DB code should use timezone-aware UTC values instead of the
      deprecated `datetime.utcnow()`
    - one shared helper keeps ORM defaults and query filters aligned

    How to use it:
    - pass it as a SQLAlchemy `default` / `onupdate` callable
    - call it directly from DB-facing code that needs the current UTC instant

    Example:
    - `created_at = mapped_column(DateTime(timezone=True), default=utcnow)`
    """

    return datetime.now(timezone.utc)
