from pydantic import BaseModel, Field

from knowledge_flow_backend.features.users.users_structures import UserSummary


class GroupProfile(BaseModel):
    id: str
    banner_image_url: str | None = None
    is_private: bool | None = None
    description: str | None = None


class GroupSummary(BaseModel):
    id: str
    name: str
    member_count: int | None = None
    total_member_count: int | None = None
    description: str | None = None
    banner_image_url: str | None = None
    is_private: bool | None = None
    owners: list[UserSummary] = Field(default_factory=list)
    is_member: bool | None = None
    sub_groups: list["GroupSummary"] = Field(default_factory=list)


GroupSummary.model_rebuild()
