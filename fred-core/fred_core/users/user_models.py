import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from fred_core.models import Base


class GcuVersionsType(enum.Enum):
    V1 = "v1"


class UserRow(Base):
    __tablename__ = "users"
    __table_args__ = {"extend_existing": True}

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True)
    gcuVersionAccepted: Mapped[GcuVersionsType] = mapped_column(
        Enum(GcuVersionsType, name="gcu_version_type"), nullable=False
    )
    gcuAcceptedAt: Mapped[datetime] = mapped_column(DateTime(timezone=True))
