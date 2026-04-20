import enum
from datetime import datetime

from sqlalchemy import Uuid, Enum, DateTime
from sqlalchemy.orm import mapped_column, Mapped

from ..models import Base

class GcuVersionsType(enum.Enum):
  V1 = "v1"


class UserRow(Base):
  __tablename__ = "users"

  id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True)
  gcuVersionAccepted: Mapped[GcuVersionsType] = mapped_column(Enum(GcuVersionsType, name="gcu_version_type"),
                                                              nullable=False)
  gcuAcceptedAt: Mapped[datetime] = mapped_column(DateTime(timezone=True))
