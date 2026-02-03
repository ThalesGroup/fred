from enum import Enum
from typing import Literal

from fred_core import RelationType
from pydantic import BaseModel, Field

from knowledge_flow_backend.core.stores.team_metadata.team_metadata_structures import TeamMetadataBase, TeamMetadataUpdate
from knowledge_flow_backend.features.teams.team_id import TeamId
from knowledge_flow_backend.features.users.users_structures import UserSummary


class TeamNotFoundError(Exception):
    """Raised when a team is not found."""

    def __init__(self, team_id: TeamId):
        self.team_id = team_id
        super().__init__(f"Team with id '{team_id}' not found")


class KeycloakGroupSummary(BaseModel):
    id: TeamId
    name: str | None
    member_count: int


class Team(TeamMetadataBase):
    # From Keycloak
    id: TeamId
    name: str
    member_count: int | None = None
    # From OpenFGA
    owners: list[UserSummary] = Field(default_factory=list)
    is_member: bool = False


class TeamUpdate(TeamMetadataUpdate):
    """For now, when updating a team, you can only update its metadata"""

    pass


# Subset of RelationType for user-tag relations
class UserTeamRelation(str, Enum):
    OWNER = RelationType.OWNER.value
    MANAGER = RelationType.MANAGER.value
    MEMBER = RelationType.MEMBER.value

    def to_relation(self) -> RelationType:
        return RelationType(self.value)


class TeamMember(BaseModel):
    type: Literal["user"] = "user"
    relation: UserTeamRelation
    user: UserSummary
