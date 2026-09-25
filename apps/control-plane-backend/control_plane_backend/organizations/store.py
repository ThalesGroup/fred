"""Organization metadata and one-time administrator migration progress."""

from fred_core.sql import make_session_factory
from fred_core.teams.organization_models import OrganizationRow
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


class OrganizationStore:
    """Read organization metadata; authorization belongs to the API/service."""

    def __init__(self, engine: AsyncEngine):
        self.sessions = make_session_factory(engine)

    async def list(self) -> list[OrganizationRow]:
        """Return registry rows for an already-authorized platform caller."""
        async with self.sessions() as session:
            return list(
                (
                    await session.scalars(
                        select(OrganizationRow).order_by(OrganizationRow.name)
                    )
                ).all()
            )

    async def get(self, organization_id: str) -> OrganizationRow | None:
        """Resolve an identity before an organization-scoped operation."""
        async with self.sessions() as session:
            return await session.get(OrganizationRow, organization_id)

    async def ensure_default(
        self, name: str, *, session: AsyncSession
    ) -> OrganizationRow:
        """Create/update the default label while retaining identity and migration state."""
        row = await session.get(OrganizationRow, "fred", with_for_update=True)
        if row is None:
            row = OrganizationRow(id="fred", name=name)
            session.add(row)
            await session.flush()
        else:
            row.name = name
        return row
