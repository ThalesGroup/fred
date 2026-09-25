"""Organization identity shared with team metadata; migrated by control-plane."""

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from fred_core.models.base import Base


class OrganizationRow(Base):
    """Persist an organization independently of its ReBAC administrator grants."""

    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(180), primary_key=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    admin_migration_completed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
