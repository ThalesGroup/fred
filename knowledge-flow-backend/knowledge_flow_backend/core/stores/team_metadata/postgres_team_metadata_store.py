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

import logging

from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, col, select

from knowledge_flow_backend.core.stores.team_metadata.base_team_metadata_store import (
    BaseTeamMetadataStore,
    TeamMetadataAlreadyExistsError,
    TeamMetadataNotFoundError,
)
from knowledge_flow_backend.core.stores.team_metadata.team_metadata_structures import (
    TeamMetadata,
)

logger = logging.getLogger(__name__)


class PostgresTeamMetadataStore(BaseTeamMetadataStore):
    """
    PostgreSQL-backed team metadata store using SQLModel.
    """

    def __init__(self, engine: Engine):
        self.engine = engine

        # Create tables
        SQLModel.metadata.create_all(self.engine)
        logger.info("[TEAM_METADATA][PG] Table ready: team_metadata")

    @staticmethod
    def _validate_team_id(team_id: str) -> None:
        """Validate that team_id is not empty."""
        if not team_id or not team_id.strip():
            raise ValueError("team_id must not be empty")

    def get_by_team_id(self, team_id: str) -> TeamMetadata:
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

        with Session(self.engine) as session:
            metadata = session.get(TeamMetadata, team_id)
            if not metadata:
                raise TeamMetadataNotFoundError(
                    f"Team metadata for team_id '{team_id}' not found."
                )
            return metadata

    def get_by_team_ids(self, team_ids: list[str]) -> dict[str, TeamMetadata]:
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

        with Session(self.engine) as session:
            statement = select(TeamMetadata).where(col(TeamMetadata.team_id).in_(team_ids))
            results = session.exec(statement)
            return {metadata.team_id: metadata for metadata in results.all()}

    def create(self, metadata: TeamMetadata) -> TeamMetadata:
        """
        Create new team metadata.

        Args:
            metadata: The team metadata to create

        Returns:
            The created TeamMetadata

        Raises:
            TeamMetadataAlreadyExistsError: If metadata for this team already exists
        """
        self._validate_team_id(metadata.team_id)

        with Session(self.engine) as session:
            try:
                session.add(metadata)
                session.commit()
                session.refresh(metadata)

                logger.info(
                    "[TEAM_METADATA][PG] Created metadata for team_id: %s",
                    metadata.team_id,
                )
                return metadata
            except IntegrityError as e:
                session.rollback()
                # Check if it's a primary key violation (duplicate team_id)
                if "duplicate key" in str(e).lower() or "unique constraint" in str(
                    e
                ).lower():
                    raise TeamMetadataAlreadyExistsError(
                        f"Team metadata for team_id '{metadata.team_id}' already exists."
                    ) from e
                # Re-raise other integrity errors (e.g., constraint violations)
                raise

    def update(self, team_id: str, metadata: TeamMetadata) -> TeamMetadata:
        """
        Update existing team metadata.

        Args:
            team_id: The Keycloak group ID
            metadata: The updated team metadata

        Returns:
            The updated TeamMetadata

        Raises:
            TeamMetadataNotFoundError: If the metadata does not exist
        """
        self._validate_team_id(team_id)

        with Session(self.engine) as session:
            existing = session.get(TeamMetadata, team_id)
            if not existing:
                raise TeamMetadataNotFoundError(
                    f"Team metadata for team_id '{team_id}' not found."
                )

            # Update fields
            existing.description = metadata.description
            existing.banner_image_url = metadata.banner_image_url
            existing.is_private = metadata.is_private
            existing.updated_at = metadata.updated_at

            session.add(existing)
            session.commit()
            session.refresh(existing)

            logger.info(
                "[TEAM_METADATA][PG] Updated metadata for team_id: %s", team_id
            )
            return existing

    def upsert(self, metadata: TeamMetadata) -> TeamMetadata:
        """
        Create or update team metadata (idempotent).

        Args:
            metadata: The team metadata to create or update

        Returns:
            The created or updated TeamMetadata
        """
        try:
            return self.create(metadata)
        except TeamMetadataAlreadyExistsError:
            return self.update(metadata.team_id, metadata)

    def delete(self, team_id: str) -> None:
        """
        Delete team metadata.

        Args:
            team_id: The Keycloak group ID

        Raises:
            TeamMetadataNotFoundError: If the metadata does not exist
        """
        self._validate_team_id(team_id)

        with Session(self.engine) as session:
            metadata = session.get(TeamMetadata, team_id)
            if not metadata:
                raise TeamMetadataNotFoundError(
                    f"Team metadata for team_id '{team_id}' not found."
                )

            session.delete(metadata)
            session.commit()

            logger.info(
                "[TEAM_METADATA][PG] Deleted metadata for team_id: %s", team_id
            )

    def list_all(self) -> list[TeamMetadata]:
        """
        List all team metadata.

        Returns:
            List of all TeamMetadata objects
        """
        with Session(self.engine) as session:
            statement = select(TeamMetadata)
            results = session.exec(statement)
            return list(results.all())
