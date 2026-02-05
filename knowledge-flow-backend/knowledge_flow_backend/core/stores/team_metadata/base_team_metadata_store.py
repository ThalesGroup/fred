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

from abc import ABC, abstractmethod

from knowledge_flow_backend.core.stores.team_metadata.team_metadata_structures import (
    TeamMetadata,
    TeamMetadataUpdate,
)
from knowledge_flow_backend.features.teams.team_id import TeamId


class TeamMetadataNotFoundError(Exception):
    """Raised when team metadata is not found."""

    pass


class TeamMetadataAlreadyExistsError(Exception):
    """Raised when trying to create team metadata that already exists."""

    pass


class TeamMetadataDeserializationError(Exception):
    """Raised when stored team metadata cannot be deserialized."""

    pass


class BaseTeamMetadataStore(ABC):
    """
    Abstract base class for storing and retrieving team metadata.

    Team metadata is additional information stored on top of Keycloak groups.
    Keycloak provides: id, name
    This store manages: description, banner_image_url, is_private, timestamps

    Exceptions:
        - get_by_team_id: TeamMetadataNotFoundError if metadata does not exist
        - get_by_team_ids: (should not throw - returns only found metadata)
        - create: TeamMetadataAlreadyExistsError if metadata already exists
        - update: TeamMetadataNotFoundError if metadata does not exist
        - delete: TeamMetadataNotFoundError if metadata does not exist
        - upsert: (should not throw - creates or updates)
        - list_all: (should not throw)
    """

    @abstractmethod
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
        pass

    @abstractmethod
    async def get_by_team_ids(self, team_ids: list[TeamId]) -> dict[TeamId, TeamMetadata]:
        """
        Retrieve multiple team metadata by team IDs in a single query.

        Args:
            team_ids: List of Keycloak group IDs

        Returns:
            Dictionary mapping team_id to TeamMetadata.
            Only includes teams that have metadata; missing teams are not in the dict.
        """
        pass

    @abstractmethod
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
        pass

    @abstractmethod
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
        pass

    @abstractmethod
    async def upsert(self, team_id: TeamId, update_data: TeamMetadataUpdate) -> TeamMetadata:
        """
        Create or update team metadata (idempotent).

        Args:
            team_id: The Keycloak group ID
            update_data: The partial update data with only fields to change

        Returns:
            The created or updated TeamMetadata
        """
        pass

    @abstractmethod
    async def delete(self, team_id: TeamId) -> None:
        """
        Delete team metadata.

        Args:
            team_id: The Keycloak group ID

        Raises:
            TeamMetadataNotFoundError: If the metadata does not exist
        """
        pass

    @abstractmethod
    async def list_all(self) -> list[TeamMetadata]:
        """
        List all team metadata.

        Returns:
            List of all TeamMetadata objects
        """
        pass
