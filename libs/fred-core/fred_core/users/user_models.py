import enum
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from fred_core.models import Base


class GcuVersionsType(enum.Enum):
    V1 = "v1"


class UserRow(Base):
    __tablename__ = "users"
    __table_args__ = {"extend_existing": True}

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True)
    gcuVersionAccepted: Mapped[GcuVersionsType | None] = mapped_column(
        Enum(GcuVersionsType, name="gcu_version_type"), nullable=True
    )
    gcuAcceptedAt: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    current_resources_storage_size: Mapped[int | None] = mapped_column(
        BigInteger, nullable=False, default=0
    )
