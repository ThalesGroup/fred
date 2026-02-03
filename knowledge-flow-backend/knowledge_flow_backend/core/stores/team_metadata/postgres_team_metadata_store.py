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

import asyncio
import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlmodel import SQLModel, col, select

from knowledge_flow_backend.core.stores.team_metadata.base_team_metadata_store import (
    BaseTeamMetadataStore,
    TeamMetadataAlreadyExistsError,
    TeamMetadataNotFoundError,
)
from knowledge_flow_backend.core.stores.team_metadata.team_metadata_structures import (
    TeamMetadata,
    TeamMetadataUpdate,
)
from knowledge_flow_backend.features.teams.team_id import TeamId

logger = logging.getLogger(__name__)


class PostgresTeamMetadataStore(BaseTeamMetadataStore):
    """
    PostgreSQL-backed team metadata store using SQLModel with async operations.
    """

    def __init__(self, engine: AsyncEngine):
        self.engine = engine
        self.async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        # Create tables asynchronously during initialization
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._create_tables())
        except RuntimeError:
            # No event loop running, create one
            asyncio.run(self._create_tables())

        logger.info("[TEAM_METADATA][PG] Async store initialized")

    async def _create_tables(self):
        """Create tables if they don't exist."""
        async with self.engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        logger.info("[TEAM_METADATA][PG] Table ready: team_metadata")

    @staticmethod
    def _validate_team_id(team_id: TeamId) -> None:
        """Validate that team_id is not empty."""
        if not team_id or not team_id.strip():
            raise ValueError("team_id must not be empty")

    async def get_by_team_id(self, team_id: TeamId) -> TeamMetadata:
        """
        Retrieve team metadata by team ID.

        Args:
            team_id: The Keycloak group ID

        Returns:
            TeamMetadata object

        Raises:
            TeamMetadataNotFoundError: If the metadata does not exist.
        """
        self._validate_team_id(team_id)

        async with self.async_session_maker() as session:
            metadata = await session.get(TeamMetadata, team_id)
            if not metadata:
                raise TeamMetadataNotFoundError(f"Team metadata for team_id '{team_id}' not found.")
            return metadata

    async def get_by_team_ids(self, team_ids: list[TeamId]) -> dict[TeamId, TeamMetadata]:
        """
        Retrieve multiple team metadata by team IDs in a single query.

        Args:
            team_ids: List of Keycloak group IDs

        Returns:
            Dictionary mapping team_id to TeamMetadata.
            Only includes teams that have metadata; missing teams are not in the dict.
        """
        if not team_ids:
            return {}

        async with self.async_session_maker() as session:
            statement = select(TeamMetadata).where(col(TeamMetadata.id).in_(team_ids))
            result = await session.execute(statement)
            metadata_list = result.scalars().all()
            return {metadata.id: metadata for metadata in metadata_list}

    async def create(self, metadata: TeamMetadata) -> TeamMetadata:
        """
        Create new team metadata.

        Args:
            metadata: The team metadata to create

        Returns:
            The created TeamMetadata

        Raises:
            TeamMetadataAlreadyExistsError: If metadata for this team already exists
        """
        self._validate_team_id(metadata.id)

        async with self.async_session_maker() as session:
            try:
                session.add(metadata)
                await session.commit()
                await session.refresh(metadata)

                logger.info(
                    "[TEAM_METADATA][PG] Created metadata for team_id: %s",
                    metadata.id,
                )
                return metadata
            except IntegrityError as e:
                await session.rollback()
                # Check if it's a primary key violation (duplicate team_id)
                if "duplicate key" in str(e).lower() or "unique constraint" in str(e).lower():
                    raise TeamMetadataAlreadyExistsError(f"Team metadata for team_id '{metadata.id}' already exists.") from e
                # Re-raise other integrity errors (e.g., constraint violations)
                raise

    async def update(self, team_id: TeamId, update_data: TeamMetadataUpdate) -> TeamMetadata:
        """
        Update existing team metadata using SQLModel pattern.

        Args:
            team_id: The Keycloak group ID
            update_data: The partial update data with only fields to change

        Returns:
            The updated TeamMetadata

        Raises:
            TeamMetadataNotFoundError: If the metadata does not exist
        """
        self._validate_team_id(team_id)

        async with self.async_session_maker() as session:
            existing = await session.get(TeamMetadata, team_id)
            if not existing:
                raise TeamMetadataNotFoundError(f"Team metadata for team_id '{team_id}' not found.")

            # Update only fields that were set
            update_dict = update_data.model_dump(exclude_unset=True)
            existing.sqlmodel_update(update_dict)

            session.add(existing)
            await session.commit()
            await session.refresh(existing)

            logger.info("[TEAM_METADATA][PG] Updated metadata for team_id: %s", team_id)
            return existing

    async def upsert(self, team_id: TeamId, update_data: TeamMetadataUpdate) -> TeamMetadata:
        """
        Create or update team metadata (idempotent).

        Args:
            team_id: The Keycloak group ID
            update_data: The partial update data with only fields to change

        Returns:
            The created or updated TeamMetadata
        """
        try:
            await self.get_by_team_id(team_id)
            return await self.update(team_id, update_data)
        except TeamMetadataNotFoundError:
            # Create new metadata with provided fields
            update_dict = update_data.model_dump(exclude_unset=True)
            new_metadata = TeamMetadata(
                id=team_id,
                **update_dict,
            )
            return await self.create(new_metadata)

    async def delete(self, team_id: TeamId) -> None:
        """
        Delete team metadata.

        Args:
            team_id: The Keycloak group ID

        Raises:
            TeamMetadataNotFoundError: If the metadata does not exist
        """
        self._validate_team_id(team_id)

        async with self.async_session_maker() as session:
            metadata = await session.get(TeamMetadata, team_id)
            if not metadata:
                raise TeamMetadataNotFoundError(f"Team metadata for team_id '{team_id}' not found.")

            await session.delete(metadata)
            await session.commit()

            logger.info("[TEAM_METADATA][PG] Deleted metadata for team_id: %s", team_id)

    async def list_all(self) -> list[TeamMetadata]:
        """
        List all team metadata.

        Returns:
            List of all TeamMetadata objects
        """
        async with self.async_session_maker() as session:
            statement = select(TeamMetadata)
            result = await session.execute(statement)
            return list(result.scalars().all())
