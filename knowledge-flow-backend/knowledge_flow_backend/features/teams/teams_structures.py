from pydantic import BaseModel, Field

from knowledge_flow_backend.core.stores.team_metadata.team_metadata_structures import TeamMetadataBase, TeamMetadataUpdate
from knowledge_flow_backend.features.users.users_structures import UserSummary


class TeamNotFoundError(Exception):
    """Raised when a team is not found."""

    def __init__(self, team_id: str):
        self.team_id = team_id
        super().__init__(f"Team with id '{team_id}' not found")


class KeycloakGroupSummary(BaseModel):
    id: str
    name: str | None
    member_count: int


class Team(TeamMetadataBase):
    # From Keycloak
    id: str
    name: str
    member_count: int | None = None
    # From OpenFGA
    owners: list[UserSummary] = Field(default_factory=list)
    is_member: bool = False


class TeamUpdate(TeamMetadataUpdate):
    """For now, when updating a team, you can only update its metadata"""

    pass
