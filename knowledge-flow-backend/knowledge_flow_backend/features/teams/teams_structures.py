from pydantic import BaseModel, Field

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


class Team(BaseModel):
    id: str
    name: str
    description: str | None = None
    banner_image_url: str | None = None
    owners: list[UserSummary] = Field(default_factory=list)
    member_count: int | None = None
    is_private: bool
    is_member: bool = False
