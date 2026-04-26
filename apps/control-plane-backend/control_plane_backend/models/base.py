from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for all control-plane-backend ORM models.

    All model classes must inherit from this Base so that Base.metadata
    captures every table for Alembic autogenerate.
    """

    pass


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
