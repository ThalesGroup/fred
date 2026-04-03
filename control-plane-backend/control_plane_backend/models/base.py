from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for all control-plane-backend ORM models.

    All model classes must inherit from this Base so that Base.metadata
    captures every table for Alembic autogenerate.
    """

    pass
